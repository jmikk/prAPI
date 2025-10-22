# gachacatchemall/gachacatchemall.py
from __future__ import annotations

import asyncio
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import discord
from redbot.core import commands, Config, checks
import aiohttp


__red_end_user_data_statement__ = (
    "This cog stores Pokémon you catch (per-catch entries with UID, species id/name, types, stats, "
    "sprite, optional nickname) and your last roll and active encounter."
)

POKEAPI_BASE = "https://pokeapi.co/api/v2"

# Reasonable defaults; adjust with [p]gachaadmin setcosts
DEFAULT_COSTS = {
    "pokeball": 0,
    "greatball": 15.0,
    "ultraball": 50.0,
    "masterball": 200.0,
}

# Catch tuning parameters per ball
BALL_TUNING = {
    # weight_bias: how we bias encounter weights (higher favors strong mons)
    # bonus_catch: added to base catch chance
    "pokeball": {"weight_bias": -1, "bonus_catch": 0.00},
    "greatball": {"weight_bias": 0, "bonus_catch": 0.15},
    "ultraball": {"weight_bias": 1, "bonus_catch": 0.30},
    "masterball": {"weight_bias": 2, "bonus_catch": 999.0},  # auto-catch
}
POKEMON_TYPES = [
    "normal","fire","water","electric","grass","ice","fighting","poison","ground","flying",
    "psychic","bug","rock","ghost","dragon","dark","steel","fairy"
]

# Difficulty profiles for NPCs
DIFFICULTY_PROFILES = {
    "easy":   {"level_delta": -1, "stat_mult": 0.95, "damage_mult": 1.00, "extra_moves": 0, "counterpick": False},
    "normal": {"level_delta": 0,  "stat_mult": 1.00, "damage_mult": 1.00, "extra_moves": 0, "counterpick": False},
    "hard":   {"level_delta": +2, "stat_mult": 1.10, "damage_mult": 1.05, "extra_moves": 1, "counterpick": True},
    "boss":   {"level_delta": +4, "stat_mult": 1.20, "damage_mult": 1.10, "extra_moves": 2, "counterpick": True},
}

# minimal weakness mapping (attacking type -> is super-effective against these)
TYPE_BEATS = {
    "fire": ["grass","ice","bug","steel"],
    "water": ["fire","ground","rock"],
    "grass": ["water","ground","rock"],
    "electric": ["water","flying"],
    "ice": ["grass","ground","flying","dragon"],
    "fighting": ["normal","ice","rock","dark","steel"],
    "poison": ["grass","fairy"],
    "ground": ["fire","electric","poison","rock","steel"],
    "flying": ["grass","fighting","bug"],
    "psychic": ["fighting","poison"],
    "bug": ["grass","psychic","dark"],
    "rock": ["fire","ice","flying","bug"],
    "ghost": ["psychic","ghost"],
    "dragon": ["dragon"],
    "dark": ["psychic","ghost"],
    "steel": ["ice","rock","fairy"],
    "fairy": ["fighting","dragon","dark"],
}


NICKNAME_RE = re.compile(r"^[A-Za-z]{1,20}$")  # “letters only, max 20”


class GachaCatchEmAll(commands.Cog):
    """Pokémon encounter & multi-throw gacha using Wellcoins + PokéAPI."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Use an integer identifier to avoid config collisions
        self.config: Config = Config.get_conf(self, identifier=0xC0FFEE56, force_registration=True)
        # pokebox stores a LIST of individual entries (each with uid)
        self.config.register_user(pokebox=[], last_roll=None, active_encounter=None, team=[])
        self.config.register_global(costs=DEFAULT_COSTS)
        self._type_cache: Dict[str, List[int]] = {}  # type -> list of pokedex IDs
        # Caches
        self._type_moves_cache: Dict[str, List[str]] = {}   # type -> move names
        self._move_cache: Dict[str, Dict[str, Any]] = {}    # move name -> move json (power/type/etc)
        self._session: Optional[aiohttp.ClientSession] = None
        self._pokemon_list: Optional[List[Dict[str, Any]]] = None  # list of {name, url}
        self._pokemon_cache: Dict[int, Dict[str, Any]] = {}  # id -> pokemon data
        self._list_lock = asyncio.Lock()

    def _chunk_lines(self, lines: List[str], size: int) -> List[List[str]]:
        return [lines[i:i+size] for i in range(0, len(lines), size)]
   
    async def _alert_owner(self, ctx: commands.Context, error: Exception):
        """Ping the bot owner if a command or interaction fails."""
        try:
            app_info = await self.bot.application_info()
            owner = app_info.owner
            if owner:
                await ctx.send(f"⚠️ <@{owner.id}>, an error occurred in `{ctx.command}`:\n```{error}```")
            else:
                await ctx.send(f"⚠️ Bot owner could not be determined.\nError: `{error}`")
        except Exception as alert_error:
            await ctx.send(f"⚠️ Failed to alert bot owner: `{alert_error}`")


    def _mutation_percent(self, p1: Dict[str, Any], p2: Dict[str, Any]) -> int:
        """
        Return total mutation percent as a deterministic buff.
        Rule: +1% per 10 levels from each parent, hard cap at 10% total.
        Examples:
          L25 + L18 -> floor(25/10)=2 + floor(18/10)=1 => 3% total
          L60 + L60 -> 6 + 6 = 12 -> cap to 10%
        """
        l1 = int(p1.get("level", 1))
        l2 = int(p2.get("level", 1))
        pct = (l1 // 10) + (l2 // 10)
        return min(10, max(0, pct))

    def _entry_move_names(self, e: Dict[str, Any]) -> List[str]:
        """Return up to 4 readable move names for a mon (ensuring at least 1)."""
        names = [m for m in (e.get("moves") or []) if isinstance(m, str)]
        if not names:
            # best-effort starter
            names = []
        # Trim to 4; title-case for buttons
        return [n for n in names][:4] or ["tackle"]
    


    def _resolve_entry_by_any(self, box: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
        q = (query or "").strip().lower()
        if not q:
            return None
        # 1) UID exact match
        for e in box:
            if str(e.get("uid","")).lower() == q:
                return e
        # 2) Pokédex ID numeric (first match)
        if q.isdigit():
            target_id = int(q)
            for e in box:
                if int(e.get("pokedex_id") or -1) == target_id:
                    return e
        # 3) Name or Nickname (first match)
        for e in box:
            name = str(e.get("name","")).lower()
            nick = str(e.get("nickname") or "").lower()
            if q == name or (nick and q == nick):
                return e
        return None


    def _pick_counter_types(self, your_team: List[Dict[str, Any]]) -> List[str]:
        # collect your visible types
        yours = set()
        for e in your_team:
            for t in (e.get("types") or []):
                yours.add(t.lower())
        # score attacker types by how many of your types they beat
        best = []
        best_score = 0
        for atk, beats in TYPE_BEATS.items():
            score = len(yours.intersection(set(beats)))
            if score > best_score:
                best, best_score = [atk], score
            elif score == best_score and score > 0:
                best.append(atk)
        return best or []


    async def _apply_difficulty_to_npc_team(self, team: List[Dict[str, Any]], profile: Dict[str, Any]) -> None:
        """Mutate team in-place based on the difficulty profile."""
        for e in team:
            # level bump
            e["level"] = max(1, int(e.get("level", 1)) + int(profile.get("level_delta", 0)))
            # stat mult
            stats = self._safe_stats(e)
            mult = float(profile.get("stat_mult", 1.0))
            for k in stats.keys():
                stats[k] = max(1, int(round(stats[k] * mult)))
            e["stats"] = stats
            e["bst"] = sum(stats.values())
            # extra moves (same-type move grabbing, avoid duplicates)
            extra = int(profile.get("extra_moves", 0))
            if extra > 0:
                e.setdefault("moves", [])
                types = [t for t in (e.get("types") or [])]
                for _ in range(extra):
                    m = await self._random_starting_move(types)
                    if m and m not in e["moves"]:
                        e["moves"].append(m)
            # small damage multiplier “tag” so _calc_move_damage can read it
            e["_dmg_mult"] = float(profile.get("damage_mult", 1.0))
    

    


    # --------- Red utilities ---------

    async def red_delete_data_for_user(self, **kwargs):  # GDPR
        user = kwargs.get("user")
        if user:
            await self.config.user(user).clear()

    def cog_unload(self):
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _hp_bar(self, cur: int, maxhp: int, width: int = 20) -> str:
        cur = max(0, min(cur, maxhp))
        filled = int(round(width * (cur / maxhp))) if maxhp else 0
        return "▰" * filled + "▱" * (width - filled)    
    
    async def _download_image_bytes(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            session = await self._get_session()
            async with session.get(url, timeout=8) as resp:
                resp.raise_for_status()
                return await resp.read()
        except Exception:
            return None
    
    async def _compose_vs_image(self, left_url: Optional[str], right_url: Optional[str]) -> Optional[discord.File]:
        """
        Try to compose two sprite URLs into a single image file attachment.
        Returns a discord.File or None on failure/unavailable Pillow.
        """
        try:
            from PIL import Image
            import io
        except Exception:
            return None
    
        lb = await self._download_image_bytes(left_url or "")
        rb = await self._download_image_bytes(right_url or "")
        if not lb or not rb:
            return None
    
        try:
            li = Image.open(io.BytesIO(lb)).convert("RGBA")
            ri = Image.open(io.BytesIO(rb)).convert("RGBA")
    
            # scale to a common height
            target_h = 256
            def scale(img):
                ratio = target_h / max(1, img.height)
                return img.resize((max(1, int(img.width*ratio)), target_h), Image.LANCZOS)
    
            li = scale(li); ri = scale(ri)
            pad = 24
            canvas = Image.new("RGBA", (li.width + ri.width + pad, target_h), (0,0,0,0))
            canvas.paste(li, (0, 0))
            canvas.paste(ri, (li.width + pad, 0))
    
            out = io.BytesIO()
            canvas.save(out, format="PNG")
            out.seek(0)
            return discord.File(fp=out, filename="vs.png")
        except Exception:
            return None


    # ---------- TEAM HELPERS ----------

    async def _get_team(self, member: discord.abc.User) -> List[str]:
        team = await self.config.user(member).team()
        if not isinstance(team, list):
            team = []
        return [str(uid) for uid in team]
    
    async def _set_team(self, member: discord.abc.User, uids: List[str]) -> None:
        # Keep max 6 and ensure uniqueness, in order
        seen, clean = set(), []
        for u in uids:
            s = str(u)
            if s not in seen:
                clean.append(s)
                seen.add(s)
            if len(clean) >= 6:
                break
        await self.config.user(member).team.set(clean)
    
    def _team_entries_from_uids(self, box: List[Dict[str, Any]], uids: List[str]) -> List[Dict[str, Any]]:
        uidset = {str(u) for u in uids}
        entries = []
        for e in box:
            if str(e.get("uid")) in uidset:
                entries.append(e)
        return entries[:6]
    
    def _avg_level(self, entries: List[Dict[str, Any]]) -> float:
        if not entries:
            return 1.0
        return sum(int(e.get("level", 1)) for e in entries) / len(entries)
    
    def _xp_scale(self, self_level: float, opp_level: float) -> float:
        """Scale XP by level difference. +10% per level the opponent is higher,
        -10% per level the opponent is lower; clamp 0.5x .. 2.0x."""
        delta = float(opp_level) - float(self_level)
        return max(0.5, min(2.0, 1.0 + 0.10 * delta))
    
    async def _ensure_moves_on_entry(self, e: Dict[str, Any]) -> None:
        # Guarantee at least 1 legal move if moves is empty
        e.setdefault("moves", [])
        if e["moves"]:
            return
        types = [t for t in (e.get("types") or [])]
        m = await self._random_starting_move(types)
        if m:
            e["moves"] = [m]
    
    async def _generate_npc_team(self, target_avg_level: float, size: int = 6) -> List[Dict[str, Any]]:
        """Build an AI team roughly around target_avg_level. Uses random encounters,
        assigns one legal move, and scales level a bit (+/-2)."""
        team: List[Dict[str, Any]] = []
        for _ in range(size):
            pdata, pid, bst = await self._random_encounter("greatball", allowed_ids=None)
            types = [t["type"]["name"] for t in pdata.get("types", [])]
            stats_map = {s["stat"]["name"]: int(s["base_stat"]) for s in pdata.get("stats", [])}
            sprite = (
                pdata.get("sprites", {})
                .get("other", {})
                .get("official-artwork", {})
                .get("front_default")
                or pdata.get("sprites", {}).get("front_default")
            )
            uid = uuid.uuid4().hex[:12]
            lvl = max(1, int(round(target_avg_level + random.randint(-2, 2))))
            mon = {
                "uid": uid,
                "pokedex_id": int(pid),
                "name": str(pdata.get("name","unknown")).title(),
                "types": types,
                "stats": stats_map,
                "bst": int(bst),
                "sprite": sprite,
                "nickname": None,
                "caught_at": int(datetime.now(timezone.utc).timestamp()),
                "level": lvl,
                "xp": 0,
                "moves": [],
                "pending_points": 0,
                "_npc": True,  # marker so we don't try to persist this to any user's box
            }
            await self._ensure_moves_on_entry(mon)
            team.append(mon)
        return team


    # --------- Economy helpers (NexusExchange) ---------

    def _nexus(self):
        cog = self.bot.get_cog("NexusExchange")
        if not cog:
            raise RuntimeError(
                "NexusExchange cog not found. Please load it so PokéGacha can charge Wellcoins."
            )
        return cog

    async def _get_balance(self, user: discord.abc.User) -> float:
        return float(await self._nexus().get_balance(user))

    async def _charge(self, user: discord.abc.User, amount: float):
        # Raises ValueError if insufficient (as per NexusExchange API)
        await self._nexus().take_wellcoins(user, amount, force=False)

    async def _refund(self, user: discord.abc.User, amount: float):
        await self._nexus().add_wellcoins(user, amount)

    # --------- PokéAPI helpers ---------

    def _ensure_mon_defaults(self, e: Dict[str, Any]) -> None:
        if "level" not in e or not isinstance(e["level"], int):
            e["level"] = 1
        if "xp" not in e or not isinstance(e["xp"], int):
            e["xp"] = 0

    async def _get_moves_for_type(self, type_name: str) -> List[str]:
        """
        PokeAPI /type/{type} has 'moves'. We cache the list of move names by type.
        """
        t = type_name.lower().strip()
        if t in self._type_moves_cache:
            return self._type_moves_cache[t]
        data = await self._fetch_json(f"{POKEAPI_BASE}/type/{t}")
        moves = [m["name"] for m in data.get("moves", []) if isinstance(m, dict) and "name" in m]
        self._type_moves_cache[t] = moves
        return moves
    
    async def _get_move_details(self, move_name: str) -> Dict[str, Any]:
        """
        Returns cached move data. Important fields: power (may be None), type.name, damage_class.name
        """
        key = move_name.lower()
        if key in self._move_cache:
            return self._move_cache[key]
        data = await self._fetch_json(f"{POKEAPI_BASE}/move/{key}")
        self._move_cache[key] = data
        return data
    
    async def _random_starting_move(self, types: List[str]) -> Optional[str]:
        """
        From all moves matching any of the Pokémon's types, pick one at random.
        """
        pool: List[str] = []
        for t in types:
            try:
                pool.extend(await self._get_moves_for_type(t))
            except Exception:
                pass
        pool = sorted(set(pool))
        if not pool:
            return None
        return random.choice(pool)
    
    def _give_stat_points_for_levels(self, before_level: int, after_level: int) -> int:
        """
        1 stat point per level gained.
        """
        return max(0, int(after_level) - int(before_level))
    
    def _find_entry_by_uid(self, box: List[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
        for e in box:
            if str(e.get("uid")) == str(uid):
                return e
        return None
    
    def _safe_stats(self, e: Dict[str, Any]) -> Dict[str, int]:
        s = {k: int(v) for k, v in (e.get("stats") or {}).items()}
        # ensure standard keys exist
        for k in ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]:
            s.setdefault(k, 10)
        return s

    def _calc_move_damage(self, attacker: Dict[str, Any], defender: Dict[str, Any], move_info: Dict[str, Any]) -> int:
        """Calculate damage with STAB, type effectiveness, and crit chance."""
        a_stats = self._safe_stats(attacker)
        d_stats = self._safe_stats(defender)
    
        power = move_info.get("power") or 10
        dmg_class = ((move_info.get("damage_class") or {}).get("name") or "physical").lower()
        mtype = ((move_info.get("type") or {}).get("name") or "").lower()
    
        atk = a_stats["attack"] if dmg_class == "physical" else a_stats["special-attack"]
        deff = d_stats["defense"] if dmg_class == "physical" else d_stats["special-defense"]
    
        # Base formula (same as before)
        dmg = (power * max(1, atk)) / max(1, deff)
    
        # --- STAB ---
        atk_types = [t.lower() for t in (attacker.get("types") or [])]
        if mtype in atk_types:
            dmg *= 1.2  # Same-type attack bonus
    
        # --- TYPE EFFECTIVENESS ---
        # You can define this dict globally or inside this function.
        TYPE_EFFECTIVENESS = {
            "fire": {"grass": 2.0, "water": 0.5, "rock": 0.5, "bug": 2.0, "ice": 2.0},
            "water": {"fire": 2.0, "grass": 0.5, "rock": 2.0, "ground": 2.0},
            "grass": {"water": 2.0, "fire": 0.5, "rock": 2.0, "flying": 0.5},
            "electric": {"water": 2.0, "ground": 0.0, "flying": 2.0},
            "rock": {"fire": 2.0, "flying": 2.0, "bug": 2.0},
            "ground": {"electric": 2.0, "flying": 0.0, "rock": 2.0, "fire": 2.0},
            "ice": {"grass": 2.0, "ground": 2.0, "flying": 2.0, "fire": 0.5},
            "flying": {"grass": 2.0, "electric": 0.5, "rock": 0.5},
            "bug": {"grass": 2.0, "fire": 0.5, "fighting": 0.5},
            "psychic": {"fighting": 2.0, "poison": 2.0, "dark": 0.0},
            "dark": {"psychic": 2.0, "ghost": 2.0, "fighting": 0.5},
            "ghost": {"psychic": 2.0, "normal": 0.0},
        }
    
        eff_mult = 1.0
        def_types = [t.lower() for t in (defender.get("types") or [])]
        for dtype in def_types:
            eff_mult *= TYPE_EFFECTIVENESS.get(mtype, {}).get(dtype, 1.0)
    
        # Feedback text support (if you want to show messages later)
        if eff_mult > 1.0:
            attacker["_last_eff_msg"] = "🌟 It's super effective! 🌟"
        elif eff_mult < 1.0 and eff_mult > 0:
            attacker["_last_eff_msg"] = "💀 It's not very effective... 💀"
        elif eff_mult == 0.0:
            attacker["_last_eff_msg"] = "🚫 It had very little effect! 🚫"
        else:
            attacker["_last_eff_msg"] = ""
    
        dmg *= eff_mult
    
        # --- CRITICAL HITS ---
        # 10% flat crit chance
        if random.random() < 0.1:
            dmg *= 1.5
            attacker["_last_crit"] = True
        else:
            attacker["_last_crit"] = False
    
        # --- RANDOM VARIANCE ---
        dmg *= random.uniform(0.85, 1.0)
    
        # --- DIFFICULTY / NPC MULTIPLIER ---
        dmg *= float(attacker.get("_dmg_mult", 1.0))
    
        # Clamp and return
        return max(1, int(round(dmg)))


    
    def _initial_hp(self, e: Dict[str, Any]) -> int:
        # Simple HP pool using 'hp' stat * level scaling
        stats = self._safe_stats(e)
        lvl = int(e.get("level", 1))
        return max(10, int(stats["hp"] * (5 + lvl/5)))
    
    async def _pick_move(self, e: Dict[str, Any]) -> Dict[str, Any]:
        moves: List[str] = [m for m in (e.get("moves") or []) if isinstance(m, str)]
        if not moves:
            # try a random legal starter
            types = [t for t in (e.get("types") or [])]
            rm = await self._random_starting_move(types)
            if rm:
                moves = [rm]
        if not moves:
            # fallback to a dummy neutral hit
            return {"name": "tackle", "power": 40, "damage_class": {"name": "physical"}, "type": {"name": "normal"}}
        name = random.choice(moves)
        try:
            mi = await self._get_move_details(name)
            # keep only fields we need to avoid giant blobs
            return {"name": name, "power": mi.get("power") or 50,
                    "damage_class": mi.get("damage_class") or {"name":"physical"},
                    "type": mi.get("type") or {"name":"normal"}}
        except Exception:
            return {"name": name, "power": 50, "damage_class": {"name":"physical"}, "type":{"name":"normal"}}
    


    async def _get_type_ids(self, type_name: str) -> List[int]:
        """
        Fetch and cache Pokémon IDs for a given type using PokeAPI: /type/{type}
        Returns a list of Pokédex IDs (ints). Filters out forms without numeric IDs.
        """
        type_name = type_name.lower().strip()
        if type_name in self._type_cache:
            return self._type_cache[type_name]
    
        data = await self._fetch_json(f"{POKEAPI_BASE}/type/{type_name}")
        ids: List[int] = []
        for p in data.get("pokemon", []):
            # {"pokemon": {"name": "...", "url": "https://pokeapi.co/api/v2/pokemon/25/"}, "slot": 1}
            url = p.get("pokemon", {}).get("url", "")
            pid = self._extract_id_from_url(url)
            if pid:
                ids.append(pid)
    
        # Dedup & sort for consistency
        ids = sorted(set(ids))
        self._type_cache[type_name] = ids
        return ids

    
    def _xp_needed(self, level: int) -> int:
        # Simple linear curve: 100 * level to next level
        # (Level 1 -> 100, L2 -> 200, etc.). Tweak any time.
        level = max(1, int(level))
        return 100 * level
    
    def _add_xp_to_entry(self, e: Dict[str, Any], amount: int) -> Tuple[int, int, int]:
        """
        Add XP to a single mon entry. Returns (new_level, new_xp, overflow_to_next).
        Applies multiple level-ups if needed. Caps at level 100.
        """
        self._ensure_mon_defaults(e)
        if amount <= 0:
            return e["level"], e["xp"], self._xp_needed(e["level"]) - e["xp"]
    
        lvl = int(e["level"])
        xp = int(e["xp"])
        cap = 100
        while amount > 0 and lvl < cap:
            need = self._xp_needed(lvl)
            space = max(0, need - xp)
            if amount >= space:
                # ding!
                amount -= space
                lvl += 1
                xp = 0
            else:
                xp += amount
                amount = 0
        # if hit cap, discard extra xp and lock at 0/need (or keep xp as max-1)
        if lvl >= cap:
            lvl = cap
            xp = 0
        e["level"], e["xp"] = lvl, xp
        return lvl, xp, max(0, self._xp_needed(lvl) - xp)
    
    def _xp_bar(self, level: int, xp: int) -> str:
        need = self._xp_needed(level)
        filled = int(round(10 * (xp / need))) if need else 0
        filled = max(0, min(10, filled))
        return "▰" * filled + "▱" * (10 - filled) + f"  {xp}/{need}"


    async def _fetch_json(self, url: str) -> Any:
        session = await self._get_session()
        async with session.get(url, timeout=8) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _ensure_pokemon_list(self):
        async with self._list_lock:
            if self._pokemon_list is not None:
                return
            data = await self._fetch_json(f"{POKEAPI_BASE}/pokemon?limit=20000")
            self._pokemon_list = data.get("results", [])

    @staticmethod
    def _extract_id_from_url(url: str) -> Optional[int]:
        # URLs look like https://pokeapi.co/api/v2/pokemon/25/
        try:
            parts = url.rstrip("/").split("/")
            return int(parts[-1])
        except Exception:
            return None

    async def _get_pokemon(self, poke_id: int) -> Dict[str, Any]:
        if poke_id in self._pokemon_cache:
            return self._pokemon_cache[poke_id]
        data = await self._fetch_json(f"{POKEAPI_BASE}/pokemon/{poke_id}")
        self._pokemon_cache[poke_id] = data
        return data
    
    async def _random_encounter(self, ball_key: str, allowed_ids: Optional[List[int]] = None) -> Tuple[Dict[str, Any], int, int]:
        """Roll a random Pokémon, optionally restricted to allowed_ids, biased by base stat totals depending on ball.
        Returns (pokemon_data, poke_id, bst)
        """
        await self._ensure_pokemon_list()
        assert self._pokemon_list is not None
    
        # Build the candidate ID pool
        if allowed_ids:
            candidate_ids = allowed_ids[:]  # copy
        else:
            candidate_ids = []
            for entry in self._pokemon_list:
                pid = self._extract_id_from_url(entry["url"])  # type: ignore
                if pid:
                    candidate_ids.append(pid)
    
        if not candidate_ids:
            pdata = await self._get_pokemon(1)
            return pdata, 1, sum(s["base_stat"] for s in pdata.get("stats", []))
    
        # Small, tiered batch sizes to keep the interaction snappy
        sample_sizes = {"pokeball": 8, "greatball": 10, "ultraball": 12, "masterball": 14}
        sample_n = min(sample_sizes.get(ball_key, 10), len(candidate_ids))
        ids = random.sample(candidate_ids, k=sample_n)
    
        async def fetch(pid: int) -> Optional[Tuple[int, Dict[str, Any], int]]:
            try:
                pdata = await self._get_pokemon(pid)
                bst = sum(s["base_stat"] for s in pdata.get("stats", []))
                sprite = (
                    pdata.get("sprites", {})
                    .get("other", {})
                    .get("official-artwork", {})
                    .get("front_default")
                    or pdata.get("sprites", {}).get("front_default")
                )
                if not sprite:
                    return None
                return (pid, pdata, bst)
            except Exception:
                return None
    
        try:
            results = await asyncio.wait_for(asyncio.gather(*[fetch(pid) for pid in ids]), timeout=5)
        except asyncio.TimeoutError:
            results = []
        triples = [t for t in results if t]
        if not triples:
            # Fallbacks
            for pid in (1, 4, 7, 25):
                try:
                    pdata = await self._get_pokemon(pid)
                    bst = sum(s["base_stat"] for s in pdata.get("stats", []))
                    return pdata, pid, bst
                except Exception:
                    continue
            pdata = await self._get_pokemon(1)
            return pdata, 1, sum(s["base_stat"] for s in pdata.get("stats", []))
    
        # Weighting by ball
        bias = BALL_TUNING[ball_key]["weight_bias"]
        weights: List[int] = []
        for _, pdata, bst in triples:
            if bias < 0:
                w = max(1, 800 - bst)
            elif bias == 0:
                w = max(1, 100 + abs(500 - bst) // 5)
            elif bias == 1:
                w = max(1, bst)
            else:
                w = max(1, bst * bst // 50)
            weights.append(w)
    
        idx = random.choices(range(len(triples)), weights=weights, k=1)[0]
        pid, pdata, bst = triples[idx]
        return pdata, pid, bst


    @staticmethod
    def _compute_catch_chance(ball_key: str, bst: int) -> float:
        if ball_key == "masterball":
            return 1.0
        difficulty = min(1.2, bst / 700.0)
        base = 0.40
        bonus = BALL_TUNING[ball_key]["bonus_catch"]
        chance = base + bonus - (0.50 * difficulty)
        return max(0.05, min(0.95, chance))

    # --------- UI helpers ---------

    def _encounter_embed(self, user, enc, costs):
        POKEBALL_EMOJI   = discord.PartialEmoji(name="pokeball",   id=1430211868756152443)
        GREATBALL_EMOJI  = discord.PartialEmoji(name="greatball",  id=1430211777030914179)
        ULTRABALL_EMOJI  = discord.PartialEmoji(name="ultraball",  id=1430211816939720815)
        MASTERBALL_EMOJI = discord.PartialEmoji(name="masterball", id=1430211804046295141)

        e = discord.Embed(
            title=f"🌿 A wild {enc['name']} appeared!",
            color=discord.Color.green()
        )
        pb   = str(getattr(self, "ball_emojis", {}).get("pokeball",   POKEBALL_EMOJI))
        gb   = str(getattr(self, "ball_emojis", {}).get("greatball",  GREATBALL_EMOJI))
        ub   = str(getattr(self, "ball_emojis", {}).get("ultraball",  ULTRABALL_EMOJI))
        mb   = str(getattr(self, "ball_emojis", {}).get("masterball", MASTERBALL_EMOJI))
    
        e.description = (
            f"Base Stat Total: **{enc['bst']}**\nMisses so far: **{enc.get('fails', 0)}**\n\n"
            f"**Choose a ball:**\n"
            f"{pb} Poké Ball — **{costs['pokeball']:.2f}** WC\n"
            f"{gb} Great Ball — **{costs['greatball']:.2f}** WC\n"
            f"{ub} Ultra Ball — **{costs['ultraball']:.2f}** WC\n"
            f"{mb} Master Ball — **{costs['masterball']:.2f}** WC"
        )
        if enc.get("sprite"):
            e.set_thumbnail(url=enc["sprite"])
        return e


    # --------- Views / Buttons ---------

    class EncounterView(discord.ui.View):
        def __init__(self, cog: "GachaCatchEmAll", author: discord.abc.User, timeout: int = 120):
            super().__init__(timeout=timeout)
            self.cog = cog
            self.author = author
            self.message: Optional[discord.Message] = None

        # --- utilities ---
        def _disable_all(self):
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

        async def on_timeout(self):
            # Lock buttons when time runs out
            self._disable_all()
            try:
                if self.message:
                    await self.message.edit(view=self)
            except Exception:
                pass

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "This encounter isn't yours — run /gacha to start your own.", ephemeral=True
                )
                return False
            return True

        async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except Exception:
                pass
            target_msg = self.message or interaction.message
            try:
                await target_msg.edit(content=f"⚠️ Error: {type(error).__name__}: {error}", view=self)
            except Exception:
                pass

        # --- throw logic ---
        async def _throw(self, interaction: discord.Interaction, ball_key: str, label: str):
            # ACK quickly (no new message)
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass

            # Load active encounter
            uconf = self.cog.config.user(interaction.user)
            enc = await uconf.active_encounter()
            target_msg = self.message or interaction.message
            if not enc:
                try:
                    await target_msg.edit(content="There is no active encounter. Use /gacha again.", embed=None, view=None)
                except Exception:
                    pass
                return

            # Charge
            costs = await self.cog.config.costs()
            cost = float(costs[ball_key])
            try:
                await self.cog._charge(interaction.user, cost)
            except Exception as e:
                try:
                    await target_msg.edit(content=f"❌ {e}", view=self)
                except Exception:
                    pass
                return

            try:
                # compute catch chance
                bst = int(enc["bst"])
                chance = self.cog._compute_catch_chance(ball_key, bst)
                caught = (ball_key == "masterball") or (random.random() <= chance)

                if caught:
                    # save per-catch entry and end encounter
                    pdata = await self.cog._get_pokemon(enc["id"])
                    types = [t["type"]["name"] for t in pdata.get("types", [])]
                    stats_map = {s["stat"]["name"]: int(s["base_stat"]) for s in pdata.get("stats", [])}
                    uid = uuid.uuid4().hex[:12]
                    now = datetime.now(timezone.utc)
                    unix = int(now.timestamp())
                    types = [t["type"]["name"] for t in pdata.get("types", [])]
                    start_move = await self.cog._random_starting_move(types)
                    entry = {
                        "uid": uid,
                        "pokedex_id": int(enc["id"]),
                        "name": enc["name"],
                        "types": types,
                        "stats": stats_map,
                        "bst": int(enc["bst"]),
                        "sprite": enc.get("sprite"),
                        "nickname": None,
                        "caught_at": int(now.timestamp()),
                        "level": 1,
                        "xp": 0,
                        "moves": [start_move] if start_move else [],   # NEW
                        "pending_points": 0,                           # NEW
                    }

                    box = await uconf.pokebox()
                    if not isinstance(box, list):
                        box = []
                    box.append(entry)
                    await uconf.pokebox.set(box)
                    await uconf.active_encounter.clear()

                    embed = discord.Embed(
                        title=f"🎉 Caught {enc['name']}!",
                        description=f"UID: `{uid}` — use `$nickname {uid} <Name>` to nickname it.",
                        color=discord.Color.gold(),
                    )
                    if enc.get("sprite"):
                        embed.set_thumbnail(url=enc["sprite"])
                    bal = await self.cog._get_balance(interaction.user)
                    embed.set_footer(text=f"New balance: {bal:.2f} WC")

                    self._disable_all()
                    await target_msg.edit(content=None, embed=embed, view=self)
                    self.stop()
                    return

                # not caught — roll flee chance
                fails = int(enc.get("fails", 0)) + 1
                enc["fails"] = fails
                flee_base = float(enc.get("flee_base", 0.08))
                flee_chance = min(0.85, flee_base + 0.12 * fails)
                fled = random.random() < flee_chance

                if fled:
                    await uconf.active_encounter.clear()
                    embed = discord.Embed(
                        title=f"💨 {enc['name']} fled!",
                        description="Better luck next time.",
                        color=discord.Color.red(),
                    )
                    if enc.get("sprite"):
                        embed.set_thumbnail(url=enc["sprite"])
                    bal = await self.cog._get_balance(interaction.user)
                    embed.set_footer(text=f"New balance: {bal:.2f} WC")

                    self._disable_all()
                    await target_msg.edit(content=None, embed=embed, view=self)
                    self.stop()
                    return

                # still here — update encounter UI with incremented fails
                await uconf.active_encounter.set(enc)
                embed = self.cog._encounter_embed(interaction.user, enc, costs)
                embed.title = f"❌ It broke free! Wild {enc['name']} is still here!"
                bal = await self.cog._get_balance(interaction.user)
                embed.set_footer(
                    text=f"Catch chance now ~ {int(self.cog._compute_catch_chance(ball_key, bst)*100)}% • Balance: {bal:.2f} WC"
                )
                await target_msg.edit(content=None, embed=embed, view=self)

                # save last roll
                await uconf.last_roll.set(
                    {"pokemon": enc["name"], "id": enc["id"], "bst": enc["bst"], "ball": ball_key, "caught": False}
                )

            except Exception as e:
                # refund on error
                try:
                    await self.cog._refund(interaction.user, cost)
                except Exception:
                    pass
                try:
                    await target_msg.edit(content=f"⚠️ Something went wrong: {e}", view=self)
                except Exception:
                    pass

        POKEBALL_EMOJI   = discord.PartialEmoji(name="pokeball",   id=1430211868756152443)
        GREATBALL_EMOJI  = discord.PartialEmoji(name="greatball",  id=1430211777030914179)
        ULTRABALL_EMOJI  = discord.PartialEmoji(name="ultraball",  id=1430211816939720815)
        MASTERBALL_EMOJI = discord.PartialEmoji(name="masterball", id=1430211804046295141)


        @discord.ui.button(label="Poké Ball",   style=discord.ButtonStyle.secondary, emoji=POKEBALL_EMOJI)
        async def pokeball(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._throw(interaction, "pokeball", "Poké Ball")
        
        @discord.ui.button(label="Great Ball",  style=discord.ButtonStyle.primary,   emoji=GREATBALL_EMOJI)
        async def greatball(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._throw(interaction, "greatball", "Great Ball")
        
        @discord.ui.button(label="Ultra Ball",  style=discord.ButtonStyle.success,   emoji=ULTRABALL_EMOJI)
        async def ultraball(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._throw(interaction, "ultraball", "Ultra Ball")
        
        @discord.ui.button(label="Master Ball", style=discord.ButtonStyle.danger,    emoji=MASTERBALL_EMOJI)
        async def masterball(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._throw(interaction, "masterball", "Master Ball")


        @discord.ui.button(label="Run", style=discord.ButtonStyle.secondary, emoji="🏃")
        async def run(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass

            uconf = self.cog.config.user(interaction.user)
            enc = await uconf.active_encounter()
            await uconf.active_encounter.clear()
            target_msg = self.message or interaction.message

            self._disable_all()
            if enc:
                embed = discord.Embed(title=f"You ran away from {enc['name']}.", color=discord.Color.dark_grey())
                if enc.get("sprite"):
                    embed.set_thumbnail(url=enc["sprite"])
                await target_msg.edit(embed=embed, view=self)
            else:
                await target_msg.edit(content="No active encounter.", embed=None, view=self)
            self.stop()

    # ----- Inventory paginator (inside the cog) -----

    class MonPaginator(discord.ui.View):
        def __init__(
            self,
            author: discord.abc.User,
            member: discord.Member,
            entries: List[Dict[str, Any]],
            start_index: int = 0,
            timeout: int = 180,
        ):
            super().__init__(timeout=timeout)
            self.author = author
            self.member = member
            self.entries = entries
            self.index = max(0, min(start_index, len(entries) - 1))
            self.message: Optional[discord.Message] = None
    
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "These controls aren't yours. Run the command to get your own.",
                    ephemeral=True,
                )
                return False
            return True
    
        def _disable_all(self):
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
    
        async def on_timeout(self) -> None:
            self._disable_all()
            try:
                if self.message:
                    await self.message.edit(view=self)
            except Exception:
                pass
    
        def _xp_needed(self, level: int) -> int:
            level = max(1, int(level))
            return 100 * level
    
        def _xp_bar(self, level: int, xp: int) -> str:
            need = self._xp_needed(level)
            filled = int(round(10 * (xp / need))) if need else 0
            filled = max(0, min(10, filled))
            return "▰" * filled + "▱" * (10 - filled) + f"  {xp}/{need}"
    
        def _render_embed(self) -> discord.Embed:
            e = self.entries[self.index]
            title = e.get("name", "Unknown")
            nick = e.get("nickname")
            if nick:
                title = f"{nick} ({e.get('name','Unknown')})"
    
            # Stats block
            stats = e.get("stats") or {}
            order = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]
            parts = [f"{k.replace('-',' ').title()}: **{stats[k]}**" for k in order if k in stats]
            for k, v in stats.items():
                if k not in order:
                    parts.append(f"{k.replace('-',' ').title()}: **{v}**")
            stats_text = "\n".join(parts) if parts else "No stats"
    
            # Types
            types = e.get("types") or []
            types_text = " / ".join(t.title() for t in types) if types else "Unknown"
    
            # Level / XP with safe defaults
            lvl = int(e.get("level", 1))
            xp = int(e.get("xp", 0))
            xpbar = self._xp_bar(lvl, xp)
    
            # Fancy caught time: prefer caught_at_unix; fallback if caught_at is int; else show ISO
            unix = e.get("caught_at_unix")
            if unix is None:
                ca = e.get("caught_at")
                if isinstance(ca, int):
                    unix = ca
            caught_text = f"<t:{unix}:F> — <t:{unix}:R>" if unix is not None else (e.get("caught_at", "?") or "?")
    
            desc = (
                f"**UID:** `{e.get('uid','??')}`\n"
                f"**Pokédex ID:** {e.get('pokedex_id','?')}\n"
                f"**Types:** {types_text}\n"
                f"**BST:** {e.get('bst','?')}\n"
                f"**Level:** **{lvl}**\n"
                f"**XP:** {xpbar}\n"
                f"**Caught:** {caught_text}\n\n"
                f"**Stats:**\n{stats_text}"
            )
    
            embed = discord.Embed(title=title, description=desc, color=discord.Color.purple())
            sprite = e.get("sprite")
            if sprite:
                embed.set_thumbnail(url=sprite)
            embed.set_footer(text=f"{self.member.display_name} — {self.index + 1}/{len(self.entries)}")
            return embed
    
        async def _update(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            if self.message:
                await self.message.edit(embed=self._render_embed(), view=self)
    
        @discord.ui.button(label="◀◀", style=discord.ButtonStyle.secondary)
        async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.index = 0
            await self._update(interaction)
    
        @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
        async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.index > 0:
                self.index -= 1
            await self._update(interaction)
    
        @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
        async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.index < len(self.entries) - 1:
                self.index += 1
            await self._update(interaction)
    
        @discord.ui.button(label="▶▶", style=discord.ButtonStyle.secondary)
        async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.index = len(self.entries) - 1
            await self._update(interaction)
    
        @discord.ui.button(label="✖ Close", style=discord.ButtonStyle.danger)
        async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
            self._disable_all()
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            if self.message:
                await self.message.edit(view=self)
            self.stop()



    class InvPaginator(discord.ui.View):
        def __init__(
            self,
            author: discord.abc.User,
            member: discord.Member,
            pages: List[List[Dict[str, Any]]],
            timeout: int = 180,
        ):
            super().__init__(timeout=timeout)
            self.author = author
            self.member = member
            self.pages = pages
            self.index = 0
            self.message: Optional[discord.Message] = None

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "These controls aren't yours. Run the command to get your own.", ephemeral=True
                )
                return False
            return True

        def _disable_all(self):
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

        async def on_timeout(self) -> None:
            self._disable_all()
            try:
                if self.message:
                    await self.message.edit(view=self)
            except Exception:
                pass

        def _render_embed(self) -> discord.Embed:
            page = self.pages[self.index]
            lines = []
            for e in page:
                nick = e.get("nickname")
                label = f"{e.get('name','Unknown')} (#{e.get('pokedex_id','?')})"
                if nick:
                    label += f" — **{nick}**"
                lines.append(f"`{e.get('uid','?')}` • {label}")
            desc = "\n".join(lines) if lines else "_No entries on this page._"

            return discord.Embed(
                title=f"{self.member.display_name}'s Pokémon (page {self.index + 1}/{len(self.pages)})",
                description=desc,
                color=discord.Color.blue(),
            )

        async def _update(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            if self.message:
                await self.message.edit(embed=self._render_embed(), view=self)

        @discord.ui.button(label="◀◀", style=discord.ButtonStyle.secondary)
        async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.index = 0
            await self._update(interaction)

        @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
        async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.index > 0:
                self.index -= 1
            await self._update(interaction)

        @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
        async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.index < len(self.pages) - 1:
                self.index += 1
            await self._update(interaction)

        @discord.ui.button(label="▶▶", style=discord.ButtonStyle.secondary)
        async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.index = len(self.pages) - 1
            await self._update(interaction)

        @discord.ui.button(label="✖ Close", style=discord.ButtonStyle.danger)
        async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
            self._disable_all()
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            if self.message:
                await self.message.edit(view=self)
            self.stop()

        # --------- Commands ---------

    @commands.hybrid_command(name="release")
    async def release(self, ctx: commands.Context, *, query: str):
        """Release a Pokémon from your box (UID, name, or nickname). Asks for confirmation."""
        member = ctx.author
        box: List[Dict[str, Any]] = await self.config.user(member).pokebox()
        if not box:
            await ctx.reply("You have no Pokémon.")
            return
    
        e = self._resolve_entry_by_any(box, query)
        if not e:
            await ctx.reply("Couldn't find that Pokémon. Use UID, name, or nickname.")
            return
    
        nick = e.get("nickname")
        label = f"{nick} ({e.get('name','?')})" if nick else e.get("name","?")
        uid = e.get("uid")
    
        emb = discord.Embed(
            title="Release this Pokémon?",
            description=(
                f"You are about to **release** `{uid}` **{label}** (Lv {int(e.get('level',1))}).\n"
                f"**This cannot be undone.**"
            ),
            color=discord.Color.red(),
        )
        if e.get("sprite"):
            emb.set_thumbnail(url=e["sprite"])
    
        view = ConfirmCombineView(author=member)  # simple yes/no view you already added
        msg = await ctx.reply(embed=emb, view=view)
        view.message = msg
        await view.wait()
    
        if view.confirmed is not True:
            await ctx.send("Release canceled.")
            return
    
        new_box = [x for x in box if str(x.get("uid")) != str(uid)]
        await self.config.user(member).pokebox.set(new_box)
    
        done = discord.Embed(
            title="Released",
            description=f"Released `{uid}` **{label}**.",
            color=discord.Color.dark_grey(),
        )
        await ctx.reply(embed=done)

    @commands.hybrid_group(name="daycare")
    async def daycare_group(self, ctx: commands.Context):
        """Daycare features."""
        if ctx.invoked_subcommand is None:
            await ctx.reply("Subcommands: `combine`")
    
    @daycare_group.command(name="combine")
    async def daycare_combine(self, ctx: commands.Context, parent1: str, parent2: str):
        """
        Combine two Pokémon (UID, name, or nickname). Both parents are poofed.
        Rules:
        - Both parents must be ≥ level 10
        - Must share at least one type
        - Child: species of one parent at random, mixed moves, mixed stats, possible mutation
        - Mutation chance = min(10, floor(L1/10)+floor(L2/10))%
        """
        member = ctx.author
        box: List[Dict[str, Any]] = await self.config.user(member).pokebox()
        if not box:
            await ctx.reply("You have no Pokémon.")
            return
    
        A = self._resolve_entry_by_any(box, parent1)
        B = self._resolve_entry_by_any(box, parent2)
        if not A or not B:
            await ctx.reply("Couldn't find one or both parents. Use UID, name, or nickname.")
            return
        if str(A.get("uid")) == str(B.get("uid")):
            await ctx.reply("Pick two different parents.")
            return
    
        # Checks
        L1 = int(A.get("level", 1))
        L2 = int(B.get("level", 1))
        if L1 < 10 or L2 < 10:
            await ctx.reply("Both parents must be at least **level 10**.")
            return
    
        t1 = {t.lower() for t in (A.get("types") or [])}
        t2 = {t.lower() for t in (B.get("types") or [])}
        if not (t1 & t2):
            await ctx.reply("Parents must **share at least one type**.")
            return
    
        # Preview embed + Confirm
        a_name = A.get("nickname") or A.get("name", "?")
        b_name = B.get("nickname") or B.get("name", "?")
        mut_pct = min(10, (L1 // 10) + (L2 // 10))
        preview = discord.Embed(
            title="Daycare — Combine?",
            description=(
                f"You're about to **combine**:\n"
                f"• `{A.get('uid')}` **{a_name}** (Lv {L1}) — Types: {', '.join(t1) or '?'}\n"
                f"• `{B.get('uid')}` **{b_name}** (Lv {L2}) — Types: {', '.join(t2) or '?'}\n\n"
                f"This will **poof both parents** and produce **one child**:\n"
                f"• Species = one of the two at random\n"
                f"• Stats = mixed per stat\n"
                f"• Moves = random mix from both (up to 4)\n"
                f"• Mutation %: **{mut_pct}%**\n\n"
                f"**This cannot be undone.**"
            ),
            color=discord.Color.orange()
        )
        if A.get("sprite"):
            preview.set_thumbnail(url=A["sprite"])
        if B.get("sprite"):
            preview.set_author(name=b_name, icon_url=B["sprite"])
    
        view = ConfirmCombineView(author=member)
        msg = await ctx.reply(embed=preview, view=view)
        view.message = msg
        await view.wait()
    
        if view.confirmed is not True:
            await ctx.send("Combine canceled.")
            return
    
        # Build child
        pick_species = random.choice([A, B])
        other = B if pick_species is A else A
    
        # species + sprites
        child_species = pick_species.get("name", "Unknown")
        child_pid = int(pick_species.get("pokedex_id") or other.get("pokedex_id") or 0)
        child_sprite = pick_species.get("sprite") or other.get("sprite")
    
        # level/xp
        child_level = 1
        child_xp = 0
    
        # types = union but ensure shared at least remains (keep max 2 like real mons)
        union_types = list({*t1, *t2})
        # Prefer to keep 1–2 types; if >2, pick 2 at random
        if len(union_types) > 2:
            random.shuffle(union_types)
            union_types = union_types[:2]
    
        # stats: per-stat pick from either parent 50/50
        def _stats(e): 
            return self._safe_stats(e)
        sa, sb = _stats(A), _stats(B)
        child_stats = {}
        for k in ["hp","attack","defense","special-attack","special-defense","speed"]:
            child_stats[k] = random.choice([sa.get(k,10), sb.get(k,10)])
    
        mut_pct = self._mutation_percent(parent1, parent2)
        if mut_pct > 0:
            mult = 1.0 + (mut_pct / 100.0)
            for k in ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]:
                base = int(child_stats.get(k, 10))
                child_stats[k] = max(1, int(round(base * mult)))
    
        # moves: random mix up to 4
        moves_a = [m for m in (A.get("moves") or []) if isinstance(m, str)]
        moves_b = [m for m in (B.get("moves") or []) if isinstance(m, str)]
        pool = list(dict.fromkeys(moves_a + moves_b))  # dedupe, keep order-ish
        random.shuffle(pool)
        child_moves = pool[:4] if pool else []
        # ensure at least 1 legal move if we somehow ended empty
        if not child_moves:
            # try to grab one by types
            starter = await self._random_starting_move(union_types)
            if starter:
                child_moves = [starter]
    
        child_uid = uuid.uuid4().hex[:12]
        child_entry = {
            "uid": child_uid,
            "pokedex_id": child_pid,
            "name": str(child_species).title(),
            "types": union_types,
            "stats": child_stats,
            "bst": int(sum(child_stats.values())),
            "sprite": child_sprite,
            "nickname": None,
            "caught_at": int(datetime.now(timezone.utc).timestamp()),
            "level": int(child_level),
            "xp": int(child_xp),
            "moves": child_moves,
            "pending_points": 0,
        }
    
        # Remove both parents; add child; save box
        uida = str(A.get("uid"))
        uidb = str(B.get("uid"))
        new_box = [e for e in box if str(e.get("uid")) not in (uida, uidb)]
        new_box.append(child_entry)
        await self.config.user(member).pokebox.set(new_box)
    
        # Result
        res = discord.Embed(
            title="✨ Daycare Result",
            description=(
                f"Parents `{uida}` **{a_name}** and `{uidb}` **{b_name}** were combined.\n"
                f"You received **{child_entry['name']}** (UID: `{child_uid}`) at **Lv {child_level}**!"
            ),
            color=discord.Color.gold()
        )
        if child_sprite:
            res.set_thumbnail(url=child_sprite)
        # show types + xp bar quickly
        res.add_field(
            name="Types",
            value=" / ".join(t.title() for t in union_types) or "Unknown",
            inline=True
        )
        res.add_field(
            name="XP",
            value=self._xp_bar(child_entry["level"], child_entry["xp"]),
            inline=True
        )
        # brief stats preview
        stats_lines = "\n".join(f"{k.replace('-',' ').title()}: **{v}**" for k, v in child_stats.items())
        res.add_field(name="Stats", value=stats_lines, inline=False)
    
        await ctx.reply(embed=res)

    @commands.hybrid_command(name="gacha")
    async def gacha(self, ctx: commands.Context):
        """Start (or resume) a wild encounter. First choose a type (or All), then multi-throw until catch or flee."""
        try:
            _ = await self._get_balance(ctx.author)
        except Exception as e:
            await ctx.reply(f"Economy unavailable: {e}\nMake sure the NexusExchange cog is loaded.")
            return
    
        uconf = self.config.user(ctx.author)
        enc = await uconf.active_encounter()
    
        if enc:
            # Resume the current encounter immediately
            costs = await self.config.costs()
            embed = self._encounter_embed(ctx.author, enc, costs)
            if enc.get("filter_type"):
                embed.title = f"🌿 {str(enc['filter_type']).title()} Area — a wild {enc['name']} appeared!"
            else:
                embed.title = f"🌿 All Areas — a wild {enc['name']} appeared!"
            view = self.EncounterView(self, ctx.author)
            msg = await ctx.reply(embed=embed, view=view)
            view.message = msg
            return
    
        # No active encounter — show type selection UI
        pick_embed = discord.Embed(
            title="Where do you want to search?",
            description=(
                "Pick a **Pokémon type** to explore that habitat, or choose **All** to search everywhere.\n\n"
                "You’ll get an encounter right after you choose."
            ),
            color=discord.Color.blurple(),
        )
        view = self.TypeSelectView(self, ctx.author)
        msg = await ctx.reply(embed=pick_embed, view=view)
        view.message = msg
    
    @commands.hybrid_group(name="team")
    async def team_group(self, ctx: commands.Context):
        """Manage your battle team (up to 6 Pokémon by UID)."""
        if ctx.invoked_subcommand is None:
            await ctx.reply("Subcommands: `set`, `view`, `auto`, `clear`")
    
    @team_group.command(name="set")
    async def team_set(self, ctx: commands.Context, uids: str):
        """
        Set your team to up to 6 UIDs.
        Works for both slash & prefix:
        /team set "uid1 uid2 uid3"   or   $team set uid1 uid2 uid3
        """
        # accept spaces or commas
        parts = [p for p in re.split(r"[,\s]+", uids.strip()) if p]
        if not parts:
            await ctx.reply("Provide 1–6 UIDs.")
            return
        if len(parts) > 6:
            parts = parts[:6]
    
        box: List[Dict[str, Any]] = await self.config.user(ctx.author).pokebox()
        own_uids = {str(e.get("uid")) for e in box}
        bad = [u for u in parts if u not in own_uids]
        if bad:
            await ctx.reply(f"These UIDs aren't in your box: {', '.join(bad)}")
            return
    
        await self._set_team(ctx.author, parts)
        await ctx.reply(f"Team set to: {', '.join(parts)}")

    
    @team_group.command(name="view")
    async def team_view(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """View a user's team (defaults to you)."""
        member = member or ctx.author
        uids = await self._get_team(member)
        if not uids:
            await ctx.reply(f"{member.display_name} has no team set.")
            return
        box: List[Dict[str, Any]] = await self.config.user(member).pokebox()
        entries = self._team_entries_from_uids(box, uids)
        if not entries:
            await ctx.reply("Team UIDs not found in box.")
            return
        lines = []
        for e in entries:
            label = e.get("nickname") or e.get("name","?")
            lines.append(f"`{e.get('uid','?')}` • {label} (Lv {int(e.get('level',1))})")
        embed = discord.Embed(
            title=f"{member.display_name}'s Team ({len(entries)}/6)",
            description="\n".join(lines),
            color=discord.Color.dark_teal()
        )
        await ctx.reply(embed=embed)
    
    @team_group.command(name="auto")
    async def team_auto(self, ctx: commands.Context):
        """Auto-pick your top 6 highest-level Pokémon as your team."""
        box: List[Dict[str, Any]] = await self.config.user(ctx.author).pokebox()
        if not box:
            await ctx.reply("You have no Pokémon.")
            return
        top = sorted(box, key=lambda e: int(e.get("level",1)), reverse=True)[:6]
        await self._set_team(ctx.author, [e.get("uid") for e in top])
        await ctx.reply("Auto-selected your top 6 by level.")
    
    @team_group.command(name="clear")
    async def team_clear(self, ctx: commands.Context):
        """Clear your current team."""
        await self._set_team(ctx.author, [])
        await ctx.reply("Cleared your team.")



    @commands.hybrid_command(name="pokeinv")
    async def pokeinv(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """List your (or another member's) individual Pokémon with UID & nickname (paginates)."""
        member = member or ctx.author
        box: List[Dict[str, Any]] = await self.config.user(member).pokebox()
        if not box:
            await ctx.reply(f"{member.display_name} has no Pokémon yet.")
            return

        # sort newest first
        box_sorted = sorted(
            box,
            key=lambda e: int(e.get("caught_at_unix") or 0),
            reverse=True,
        )
        page_size = 10  # tweak as you like
        pages: List[List[Dict[str, Any]]] = [box_sorted[i:i + page_size] for i in range(0, len(box_sorted), page_size)]

        view = self.InvPaginator(author=ctx.author, member=member, pages=pages)
        embed = view._render_embed()
        msg = await ctx.reply(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(name="nickname")
    async def nickname(self, ctx: commands.Context, uid: str, nickname: Optional[str] = None):
        """Set or clear a nickname for a caught Pokémon by UID.
        Nicknames must be LETTERS ONLY (A–Z/a–z), 1–20 characters.
        Omit the nickname to CLEAR it.
        """
        box: List[Dict[str, Any]] = await self.config.user(ctx.author).pokebox()
        if not box:
            await ctx.reply("You have no Pokémon.")
            return

        # find entry
        target = None
        for e in box:
            if e.get("uid") == uid:
                target = e
                break
        if not target:
            await ctx.reply("UID not found in your PokéBox.")
            return

        if nickname is None:
            target["nickname"] = None
            await self.config.user(ctx.author).pokebox.set(box)
            await ctx.reply(f"Cleared nickname for `{uid}` ({target['name']}).")
            return

        if not NICKNAME_RE.match(nickname):
            await ctx.reply("Nickname must be LETTERS ONLY (A–Z/a–z), 1–20 chars.")
            return

        target["nickname"] = nickname
        await self.config.user(ctx.author).pokebox.set(box)
        await ctx.reply(f"Set nickname for `{uid}` to **{nickname}**.")

    # --------- Admin ---------

    @checks.admin()
    @commands.hybrid_group(name="gachaadmin")
    async def gachaadmin(self, ctx: commands.Context):
        """Admin settings for PokéGacha."""
        pass

    @gachaadmin.command(name="levelup")
    @checks.admin()
    async def gadmin_levelup(self, ctx: commands.Context, member: discord.Member, query: str, levels: int):
        """Admin: increase a Pokémon's level by N (adds pending stat points)."""
        levels = int(levels)
        if levels <= 0:
            await ctx.reply("Levels must be a positive integer.")
            return
    
        box: List[Dict[str, Any]] = await self.config.user(member).pokebox()
        if not box:
            await ctx.reply(f"{member.display_name} has no Pokémon.")
            return
    
        e = self._resolve_entry_by_any(box, query)
        if not e:
            await ctx.reply("Couldn't find that Pokémon (UID, name, or nickname).")
            return
    
        before = int(e.get("level", 1))
        after = min(100, before + levels)
        if after == before:
            await ctx.reply("No change (already at cap?).")
            return
    
        pts = self._give_stat_points_for_levels(before, after)
        e["level"] = after
        e["xp"] = 0
        e["pending_points"] = int(e.get("pending_points", 0)) + pts
    
        await self.config.user(member).pokebox.set(box)
    
        label = e.get("nickname") or e.get("name","?")
        emb = discord.Embed(
            title="Admin Level Up",
            description=(
                f"**{label}** `{e.get('uid')}`\n"
                f"Level: **{before} → {after}**\n"
                f"Pending stat points: +**{pts}** (now **{e['pending_points']}**)"
            ),
            color=discord.Color.green(),
        )
        emb.add_field(name="XP", value=self._xp_bar(after, e["xp"]), inline=True)
        if e.get("sprite"):
            emb.set_thumbnail(url=e["sprite"])
        await ctx.reply(embed=emb)

    @gachaadmin.command(name="resetpokedata")
    @checks.admin()
    async def gacha_resetpokedata(self, ctx: commands.Context, confirm: Optional[bool] = False):
        """WIPE ALL users' PokéBoxes and active encounters. Use with care!
        Example: `[p]gachaadmin resetpokedata true`
        """
        if not confirm:
            await ctx.reply("⚠️ This will wipe ALL users' PokéBoxes and encounters. Re-run with `true` to confirm.")
            return

        # Get all user data and wipe the fields we own
        all_users = await self.config.all_users()
        wiped = 0
        for user_id, data in all_users.items():
            data["pokebox"] = []
            data["active_encounter"] = None
            data["last_roll"] = None
            await self.config.user_from_id(int(user_id)).set(data)
            wiped += 1

        await ctx.reply(f"🧹 Reset Poké data for {wiped} users.")

    @gachaadmin.command(name="setcosts")
    @checks.admin()
    async def gacha_setcosts(
        self,
        ctx: commands.Context,
        pokeball: Optional[float] = None,
        greatball: Optional[float] = None,
        ultraball: Optional[float] = None,
        masterball: Optional[float] = None,
    ):
        """Set custom Wellcoin costs for balls. Omit a value to leave it unchanged.
        Example: `[p]gachaadmin setcosts 10 25 60 250`"""
        costs = await self.config.costs()
        if pokeball is not None:
            costs["pokeball"] = float(pokeball)
        if greatball is not None:
            costs["greatball"] = float(greatball)
        if ultraball is not None:
            costs["ultraball"] = float(ultraball)
        if masterball is not None:
            costs["masterball"] = float(masterball)
        await self.config.costs.set(costs)
        await ctx.reply(
            "Updated costs: "
            f"Poké {costs['pokeball']:.2f}, Great {costs['greatball']:.2f}, "
            f"Ultra {costs['ultraball']:.2f}, Master {costs['masterball']:.2f}"
        )

    @commands.hybrid_command(name="viewmon")
    async def viewmon(self, ctx: commands.Context, *, query: Optional[str] = None):
        """View your Pokémon one-by-one with buttons. Start at a specific one by UID, ID, name, or nickname."""
        member = ctx.author
        box: List[Dict[str, Any]] = await self.config.user(member).pokebox()
        if not box:
            await ctx.reply("You have no Pokémon yet.")
            return
    
        # newest first
        entries = sorted(
            box,
            key=lambda e: int(e.get("caught_at_unix") or 0),
            reverse=True,
        )    
        # Find starting index
        start_index = 0
        if query:
            q = query.strip().lower()
    
            # 1) UID exact match
            for i, e in enumerate(entries):
                if str(e.get("uid", "")).lower() == q:
                    start_index = i
                    break
            else:
                # 2) Pokédex ID numeric match
                if q.isdigit():
                    target_id = int(q)
                    for i, e in enumerate(entries):
                        if int(e.get("pokedex_id") or -1) == target_id:
                            start_index = i
                            break
                # 3) Name or Nickname (case-insensitive, first match)
                if start_index == 0:  # not found yet (and not already 0 by coincidence)
                    for i, e in enumerate(entries):
                        name = str(e.get("name", "")).lower()
                        nick = str(e.get("nickname") or "").lower()
                        if q == name or (nick and q == nick):
                            start_index = i
                            break
    
        view = self.MonPaginator(author=ctx.author, member=member, entries=entries, start_index=start_index)
        embed = view._render_embed()
        msg = await ctx.reply(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(name="spendstat")
    async def spendstat(self, ctx: commands.Context, uid: str, stat: str, points: Optional[int] = 1):
        """Spend pending stat points on one of: hp, attack, defense, special-attack, special-defense, speed."""
        points = max(1, int(points or 1))
        box: List[Dict[str, Any]] = await self.config.user(ctx.author).pokebox()
        if not box:
            await ctx.reply("You have no Pokémon.")
            return
        e = self._find_entry_by_uid(box, uid)
        if not e:
            await ctx.reply("UID not found in your PokéBox.")
            return
    
        e.setdefault("pending_points", 0)
        if e["pending_points"] < points:
            await ctx.reply(f"Not enough points. You have **{e['pending_points']}** pending.")
            return
    
        stat = stat.lower()
        valid = ["hp","attack","defense","special-attack","special-defense","speed"]
        if stat not in valid:
            await ctx.reply(f"Invalid stat. Choose from: {', '.join(valid)}")
            return
    
        stats = self._safe_stats(e)
        stats[stat] = int(stats.get(stat, 10)) + points
        e["stats"] = stats
        e["bst"] = sum(stats.values())
        e["pending_points"] = int(e["pending_points"]) - points
    
        await self.config.user(ctx.author).pokebox.set(box)
        await ctx.reply(f"Added **{points}** point(s) to **{stat}** for `{uid}`. Pending left: **{e['pending_points']}**.")

    @commands.hybrid_command(name="battle")
    async def battle(self, ctx: commands.Context, uid1: str, uid2: str, opponent: Optional[discord.Member] = None):
        """
        Battle two Pokémon by UID.
        - If opponent is omitted, both UIDs must be yours.
        - If opponent is provided, the second UID is taken from their box.
        XP: winner +50, loser +30. Level-ups give pending stat points to spend with /spendstat.
        """
        you = ctx.author
        op = opponent or ctx.author
    
        box1: List[Dict[str, Any]] = await self.config.user(you).pokebox()
        box2: List[Dict[str, Any]] = await self.config.user(op).pokebox()
    
        a = self._find_entry_by_uid(box1, uid1)
        b = self._find_entry_by_uid(box2, uid2)
        if not a:
            await ctx.reply("Your first UID wasn't found.")
            return
        if not b:
            await ctx.reply("Opponent UID wasn't found.")
            return
    
        # Working copies (don't mutate base stats mid-battle)
        A = dict(a)
        B = dict(b)
        A_hp = self._initial_hp(A)
        B_hp = self._initial_hp(B)
    
        # Turn order by speed
        A_spd = self._safe_stats(A)["speed"]
        B_spd = self._safe_stats(B)["speed"]
    
        log_lines = []
        turn = 1
        first_is_A = True if A_spd >= B_spd else False
    
        while A_hp > 0 and B_hp > 0 and turn <= 100:
            order = [("A", A, B, "B")] if first_is_A else [("B", B, A, "A")]
            order += [("B", B, A, "A")] if first_is_A else [("A", A, B, "B")]
    
            for who, atk, dfn, dlabel in order:
                if A_hp <= 0 or B_hp <= 0:
                    break
                move = await self._pick_move(atk)
                dmg = self._calc_move_damage(atk, dfn, move)
                if who == "A":
                    B_hp -= dmg
                else:
                    A_hp -= dmg
                log_lines.append(f"Turn {turn}: {atk.get('nickname') or atk['name']} used **{move['name'].title()}** → {dlabel} took **{dmg}**")
            turn += 1
    
        winner = None
        if A_hp > 0 and B_hp <= 0:
            winner = "A"
        elif B_hp > 0 and A_hp <= 0:
            winner = "B"
        else:
            # tie on turn limit; coin flip
            winner = random.choice(["A","B"])
    
        # XP & Leveling
        async def award(e: Dict[str, Any], gain: int) -> Tuple[int,int,int,int]:
            before = int(e.get("level", 1))
            lvl, xp, to_next = self._add_xp_to_entry(e, gain)
            pts = self._give_stat_points_for_levels(before, lvl)
            e["pending_points"] = int(e.get("pending_points", 0)) + pts
            return before, lvl, xp, pts
    
        if winner == "A":
            aw_a = await award(a, 50)
            aw_b = await award(b, 30)
            result_title = f"🏆 {a.get('nickname') or a['name']} wins!"
        else:
            aw_a = await award(a, 30)
            aw_b = await award(b, 50)
            result_title = f"🏆 {b.get('nickname') or b['name']} wins!"
    
        # Persist boxes
        await self.config.user(you).pokebox.set(box1)
        await self.config.user(op).pokebox.set(box2)
    
        # Summarize
        def fmt_aw(label, e, aw):
            before, lvl, xp, pts = aw
            return f"**{label} – {e.get('nickname') or e['name']}**  Lvl {before} → **{lvl}**  (XP: {xp})  +{pts} stat point(s)"
    
        desc = "\n".join(log_lines[-10:])  # last 10 lines for brevity
        embed = discord.Embed(title=result_title, description=desc, color=discord.Color.teal())
        embed.add_field(name="Progress", value=f"{fmt_aw('Yours', a, aw_a)}\n{fmt_aw('Opponent', b, aw_b)}", inline=False)
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="teambattle")
    async def teambattle(self, ctx: commands.Context, opponent: Optional[discord.Member] = None):
        """
        Interactive 6v6 team battle.
        Players choose moves via buttons each turn or use ⏭ Auto-Sim to Results to fast-forward.
        If an interaction or message send fails, the bot owner is pinged in chat.
        """
        caller = ctx.author
        opp = opponent
    
        try:
            # ----- Load caller team
            caller_uids = await self._get_team(caller)
            caller_box: List[Dict[str, Any]] = await self.config.user(caller).pokebox()
            caller_team = self._team_entries_from_uids(caller_box, caller_uids)
            if not caller_team:
                caller_team = sorted(caller_box, key=lambda e: int(e.get("level", 1)), reverse=True)[:6]
                if not caller_team:
                    await ctx.reply("You have no Pokémon to battle with.")
                    return
            for e in caller_team:
                await self._ensure_moves_on_entry(e)
    
            # ----- Difficulty roll
            mode = "normal"
            r = random.random()
            if r < 0.10:
                mode = "boss"
            elif r < 0.35:
                mode = "hard"
            profile = DIFFICULTY_PROFILES.get(mode, DIFFICULTY_PROFILES["normal"])
    
            # ----- Opponent or NPC team
            if opp:
                opp_uids = await self._get_team(opp)
                opp_box: List[Dict[str, Any]] = await self.config.user(opp).pokebox()
                opp_team = self._team_entries_from_uids(opp_box, opp_uids)
                if not opp_team:
                    opp_team = sorted(opp_box, key=lambda e: int(e.get("level", 1)), reverse=True)[:6]
                if not opp_team:
                    await ctx.reply(f"{opp.display_name} has no Pokémon to battle with.")
                    return
                for e in opp_team:
                    await self._ensure_moves_on_entry(e)
            else:
                avg_lvl = self._avg_level(caller_team)
                opp_team = await self._generate_npc_team(
                    target_avg_level=avg_lvl,
                    size=min(6, len(caller_team) or 6)
                )
                await self._apply_difficulty_to_npc_team(opp_team, profile)
    
            # ----- Launch interactive battle
            view = InteractiveTeamBattleView(
                cog=self,
                caller=caller,
                caller_team=caller_team,
                opp_team=opp_team,
                opponent=opp
            )
            embed = view._current_embed()
            msg = await ctx.reply(embed=embed, view=view)
            view.message = msg
    
        except Exception as e:
            await ctx.reply(f"❌ There was an error starting the battle: `{e}`")
            await self._alert_owner(ctx, e)






    class TypeSelectView(discord.ui.View):
        def __init__(self, cog: "GachaCatchEmAll", author: discord.abc.User, timeout: int = 120):
            super().__init__(timeout=timeout)
            self.cog = cog
            self.author = author
            self.message: Optional[discord.Message] = None
    
            # Build rows of buttons (<=5 per row). We'll do 4 rows of 5 and one row with the rest + "All"
            labels = POKEMON_TYPES[:]  # 18 types
            # Create buttons dynamically
            for t in labels:
                self.add_item(self._make_button(t))
    
            # Add an "All" button at the end
            self.add_item(self._make_button("all", style=discord.ButtonStyle.secondary))
    
        def _make_button(self, t: str, style: discord.ButtonStyle = discord.ButtonStyle.primary):
            label = "All" if t == "all" else t.title()
            button = discord.ui.Button(label=label, style=style)
            async def cb(interaction: discord.Interaction):
                await self._handle_pick(interaction, t)
            button.callback = cb  # type: ignore
            return button
    
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "These controls aren't yours — run /gacha to start your own.",
                    ephemeral=True
                )
                return False
            return True
    
        def _disable_all(self):
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
    
        async def on_timeout(self):
            self._disable_all()
            try:
                if self.message:
                    await self.message.edit(view=self)
            except Exception:
                pass
    
        async def _handle_pick(self, interaction: discord.Interaction, pick: str):
            # ACK quickly
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
    
            uconf = self.cog.config.user(interaction.user)
            # Build allowlist if a specific type was chosen
            allowed_ids: Optional[List[int]] = None
            chosen_label = "All"
            if pick != "all":
                try:
                    allowed_ids = await self.cog._get_type_ids(pick)
                    if not allowed_ids:
                        # No entries for this type; fail gracefully
                        await interaction.followup.send(f"Couldn't find Pokémon for type **{pick.title()}**.", ephemeral=True)
                        return
                    chosen_label = pick.title()
                except Exception as e:
                    await interaction.followup.send(f"Error looking up type **{pick}**: {e}", ephemeral=True)
                    return
    
            # Roll encounter (neutral bias for encounter only—same as before)
            pdata, pid, bst = await self.cog._random_encounter("greatball", allowed_ids=allowed_ids)
            name = pdata.get("name", "unknown").title()
            sprite = (
                pdata.get("sprites", {})
                .get("other", {})
                .get("official-artwork", {})
                .get("front_default")
                or pdata.get("sprites", {}).get("front_default")
            )
            flee_base = max(0.05, min(0.25, 0.10 + (bst - 400) / 800.0))
            enc = {
                "id": int(pid),
                "name": name,
                "bst": int(bst),
                "sprite": sprite,
                "fails": 0,
                "flee_base": float(flee_base),
                "filter_type": None if pick == "all" else pick.lower(),
            }
            await uconf.active_encounter.set(enc)
    
            costs = await self.cog.config.costs()
            embed = self.cog._encounter_embed(interaction.user, enc, costs)
            # Decorate title to show where they searched
            if enc.get("filter_type"):
                embed.title = f"🌿 {chosen_label} Area — a wild {enc['name']} appeared!"
            else:
                embed.title = f"🌿 All Areas — a wild {enc['name']} appeared!"
    
            # Replace the selection UI with the encounter UI
            view = self.cog.EncounterView(self.cog, interaction.user)
            try:
                # Prefer editing the message if we have it; otherwise reply
                target = self.message or interaction.message
                msg = await target.edit(content=None, embed=embed, view=view)
                view.message = msg
            except Exception:
                msg = await interaction.followup.send(embed=embed, view=view)
                view.message = msg
    
            # Lock type picker
            self._disable_all()
            
# --- REPLACE your current module-level BattlePaginator with this one ---
class BattlePaginator(discord.ui.View):
    """
    Paginated battle viewer that supports one (embed, optional file) per page,
    plus a 'Skip to Results' page.
    """
    def __init__(
        self,
        author: discord.abc.User,
        pages_with_files: List[Tuple[discord.Embed, Optional[discord.File]]],
        results_embed: discord.Embed,
        opponent: Optional[discord.abc.User] = None,
        timeout: int = 300
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.opponent = opponent
        self.pages_with_files = pages_with_files
        self.results_embed = results_embed
        self.index = 0
        self.message: Optional[discord.Message] = None
        self._showing_results = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        allowed = {self.author.id}
        if self.opponent:
            allowed.add(self.opponent.id)
        if interaction.user.id not in allowed:
            await interaction.response.send_message("These controls aren't yours.", ephemeral=True)
            return False
        return True

    def _disable_all(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    async def on_timeout(self):
        self._disable_all()
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    def _current(self) -> Tuple[discord.Embed, Optional[discord.File]]:
        if self._showing_results:
            emb = self.results_embed
            emb.set_footer(text="Results")
            return (emb, None)
        emb, f = self.pages_with_files[self.index]
        total = len(self.pages_with_files)
        emb.set_footer(text=f"Page {self.index + 1}/{total} • ⏭ Skip to results")
        return (emb, f)

    async def _update(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        if not self.message:
            return
        emb, f = self._current()
        try:
            if f:
                # swap to this page's attachment
                await self.message.edit(embed=emb, attachments=[f], view=self)
            else:
                # no attachment for this page
                await self.message.edit(embed=emb, attachments=[], view=self)
        except Exception:
            pass

    @discord.ui.button(label="◀◀", style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._showing_results = False
        self.index = 0
        await self._update(interaction)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._showing_results = False
        if self.index > 0:
            self.index -= 1
        await self._update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._showing_results:
            await self._update(interaction)
            return
        if self.index < len(self.pages_with_files) - 1:
            self.index += 1
            await self._update(interaction)
        else:
            self._showing_results = True
            await self._update(interaction)

    @discord.ui.button(label="▶▶", style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._showing_results = False
        self.index = len(self.pages_with_files) - 1
        await self._update(interaction)

    @discord.ui.button(label="Skip to Results", style=discord.ButtonStyle.primary, emoji="⏭")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._showing_results = True
        await self._update(interaction)

    @discord.ui.button(label="✖ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._disable_all()
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        if self.message:
            await self.message.edit(view=self)
        self.stop()


class ConfirmCombineView(discord.ui.View):
    def __init__(self, author: discord.abc.User, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.author = author
        self.message: Optional[discord.Message] = None
        self.confirmed: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("These buttons aren’t for you.", ephemeral=True)
            return False
        return True

    def _disable_all(self):
        for c in self.children:
            if isinstance(c, discord.ui.Button):
                c.disabled = True

    async def on_timeout(self):
        self._disable_all()
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self._disable_all()
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="✖ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self._disable_all()
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass
        self.stop()

class InteractiveTeamBattleView(discord.ui.View):
    """
    Turn-by-turn interactive 6v6.
    - Caller controls their active mon's move.
    - If an opponent is provided, they can control their active mon too.
    - Otherwise the opponent/NPC picks randomly.
    - Always shows an 'Auto-Sim to Results' button to jump to the end.
    """
    def __init__(
        self,
        cog: "GachaCatchEmAll",
        caller: discord.abc.User,
        caller_team: List[Dict[str, Any]],
        opp_team: List[Dict[str, Any]],
        opponent: Optional[discord.abc.User] = None,
        timeout: int = 420
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.caller = caller
        self.opponent = opponent
        self.caller_team = caller_team
        self.opp_team = opp_team
        # indexes into each team
        self.ci = 0
        self.oi = 0
        # persistent HP across duels
        self.caller_hp: Dict[str, Tuple[int, int]] = {}
        self.opp_hp: Dict[str, Tuple[int, int]] = {}
        self._seed_hp_map(self.caller_team, self.caller_hp)
        self._seed_hp_map(self.opp_team, self.opp_hp)

        # progress/xp buckets (we'll compute final XP on finish)
        self._action_log: List[str] = []  # short lines for recap
        self._caller_awards: Dict[str, int] = {}
        self._opp_awards: Dict[str, int] = {}

        # live message
        self.message: Optional[discord.Message] = None

        # dynamic move buttons (filled on first render)
        self._rebuild_move_buttons()

    # ---------- guards / boilerplate ----------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        allowed = {self.caller.id}
        if self.opponent:
            allowed.add(self.opponent.id)
        if interaction.user.id not in allowed:
            await interaction.response.send_message("These controls aren't yours.", ephemeral=True)
            return False
        return True

    def _estimate_effectiveness(self, move: Dict[str, Any], defender: Dict[str, Any]) -> str:
        """Roughly estimate type effectiveness emoji for a move against a defender."""
        TYPE_EFFECTIVENESS = {
            "fire": {"grass": 2.0, "water": 0.5, "rock": 0.5, "bug": 2.0, "ice": 2.0},
            "water": {"fire": 2.0, "grass": 0.5, "rock": 2.0, "ground": 2.0},
            "grass": {"water": 2.0, "fire": 0.5, "rock": 2.0, "flying": 0.5},
            "electric": {"water": 2.0, "ground": 0.0, "flying": 2.0},
            "rock": {"fire": 2.0, "flying": 2.0, "bug": 2.0},
            "ground": {"electric": 2.0, "flying": 0.0, "rock": 2.0, "fire": 2.0},
            "ice": {"grass": 2.0, "ground": 2.0, "flying": 2.0, "fire": 0.5},
            "flying": {"grass": 2.0, "electric": 0.5, "rock": 0.5},
            "bug": {"grass": 2.0, "fire": 0.5, "fighting": 0.5},
            "psychic": {"fighting": 2.0, "poison": 2.0, "dark": 0.0},
            "dark": {"psychic": 2.0, "ghost": 2.0, "fighting": 0.5},
            "ghost": {"psychic": 2.0, "normal": 0.0},
        }
    
        mtype = ((move.get("type") or {}).get("name") or "").lower()
        eff_mult = 1.0
        for dtype in [t.lower() for t in (defender.get("types") or [])]:
            eff_mult *= TYPE_EFFECTIVENESS.get(mtype, {}).get(dtype, 1.0)
    
        if eff_mult > 1.0:
            return "🌟"
        elif eff_mult == 0.0:
            return "🚫"
        elif 0 < eff_mult < 1.0:
            return "💀"
        else:
            return ""
    

    def _disable_all(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    async def on_timeout(self):
        self._disable_all()
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    # ---------- state helpers ----------
    def _seed_hp_map(self, team, store):
        for e in team:
            mx = self.cog._initial_hp(e)
            store[e["uid"]] = (mx, mx)  # cur, max

    def _alive(self) -> bool:
        return self.ci < len(self.caller_team) and self.oi < len(self.opp_team)

    def _active_pair(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return self.caller_team[self.ci], self.opp_team[self.oi]

    def _hp_tuple(self, e: Dict[str, Any], store: Dict[str, Tuple[int, int]]) -> Tuple[int, int]:
        return store.get(e["uid"], (self.cog._initial_hp(e), self.cog._initial_hp(e)))

    def _set_hp(self, e: Dict[str, Any], cur: int, store: Dict[str, Tuple[int, int]]):
        _, mx = self._hp_tuple(e, store)
        store[e["uid"]] = (max(0, cur), mx)

    def _who_controls(self, user: discord.abc.User) -> str:
        """Return which side this user controls: 'caller', 'opp', or ''."""
        if user.id == self.caller.id:
            return "caller"
        if self.opponent and user.id == self.opponent.id:
            return "opp"
        return ""

    def _hpbar(self, cur: int, mx: int) -> str:
        return self.cog._hp_bar(cur, mx, width=20)

    # ---------- rendering ----------
    def _current_embed(self) -> discord.Embed:
        A, B = self._active_pair()
        A_cur, A_max = self._hp_tuple(A, self.caller_hp)
        B_cur, B_max = self._hp_tuple(B, self.opp_hp)

        header = f"{self.caller.display_name} vs {(self.opponent.display_name if self.opponent else 'NPC Team')}"
        duel = f"{A.get('nickname') or A['name']} (Lv {A.get('level',1)}) vs {B.get('nickname') or B['name']} (Lv {B.get('level',1)})"

        desc = (
            f"**Duel {self.ci+1 if self.ci==self.oi else max(self.ci,self.oi)+1}** — {duel}\n\n"
            f"**{A.get('nickname') or A['name']}** HP: {self._hpbar(A_cur,A_max)}  {A_cur}/{A_max}\n"
            f"**{B.get('nickname') or B['name']}** HP: {self._hpbar(B_cur,B_max)}  {B_cur}/{B_max}\n"
        )

        em = discord.Embed(title=f"Team Battle — {header}", description=desc, color=discord.Color.teal())
        # image styling
        a_s = A.get("sprite"); b_s = B.get("sprite")
        if a_s:      
            em.set_author(name=(A.get("nickname") or A.get("name","?")), icon_url=a_s)
        if b_s:
            em.set_thumbnail(url=b_s)


        if self._action_log:
            tail = "\n".join(self._action_log[-4:])
            em.add_field(name="Recent", value=tail, inline=False)
        em.set_footer(text="Choose a move or ⏭ Auto-Sim to Results")
        return em

    async def _refresh(self, interaction: Optional[discord.Interaction] = None):
        """Refresh moves + embed in place."""
        self._rebuild_move_buttons()
        if interaction and not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        if self.message:
            await self.message.edit(embed=self._current_embed(), view=self)

    def _rebuild_move_buttons(self):
        """Remove old move buttons and add new ones for whichever users can act."""
        # Clear old move buttons but keep utility buttons (Auto, Close)
        keep = {"auto", "close"}
        to_remove = [c for c in self.children if isinstance(c, discord.ui.Button) and getattr(c, "custom_id", None) not in keep]
        for c in to_remove:
            self.remove_item(c)

        if not self._alive():
            return

        A, B = self._active_pair()
        A_moves = self.cog._entry_move_names(A)
        B_moves = self.cog._entry_move_names(B)

        # Get current defender for emoji preview
        defender = self.opp_team[self.oi] if self.oi < len(self.opp_team) else None
        
        for name in A_moves:
            # Try to pull cached or API move info for type preview
            move_info = {"name": name}
            try:
                details = await self.cog._get_move_details(name.lower())
                if details:
                    move_info.update(details)
            except Exception:
                pass
        
            emoji = self._estimate_effectiveness(move_info, defender) if defender else ""
            btn = discord.ui.Button(label=f"{emoji} {name.title()}", style=discord.ButtonStyle.primary)
        
            async def _cb(inter: discord.Interaction, chosen=name):
                await self._turn(inter, side="caller", chosen_move=chosen)
            btn.callback = _cb  # type: ignore
            self.add_item(btn)


        # If a human opponent exists, give them their own row of buttons
        if self.opponent:
            for name in B_moves:
                btn = discord.ui.Button(label=f"(Opp) {name.title()}", style=discord.ButtonStyle.secondary)
                async def _cb(inter: discord.Interaction, chosen=name):
                    await self._turn(inter, side="opp", chosen_move=chosen)
                btn.callback = _cb  # type: ignore
                self.add_item(btn)

    # ---------- core one-turn resolver ----------
    async def _turn(self, interaction: discord.Interaction, side: str, chosen_move: str):
        if not self._alive():
            return

        # Validate controller
        who = self._who_controls(interaction.user)
        if side != who and not (side == "caller" and who == "caller") and not (side == "opp" and who == "opp"):
            await interaction.response.send_message("You can't pick for that side.", ephemeral=True)
            return

        # Determine current fighters
        A, B = self._active_pair()
        A_cur, A_max = self._hp_tuple(A, self.caller_hp)
        B_cur, B_max = self._hp_tuple(B, self.opp_hp)

        # Compose both moves: chosen for the pressing side; other side random (unless they are human and already pressed)
        # For simplicity: on each button press we resolve a full "turn" where BOTH act once (speed order),
        # using chosen_move for the presser and a random legal move for the other side.
        # If the opponent is human, they can also press their button on the next turn to steer their side.
        if side == "caller":
            a_move = {"name": chosen_move, "power": 50, "damage_class": {"name": "physical"}, "type":{"name":"normal"}}
            # Try to fetch real move if cached
            try:
                mi = await self.cog._get_move_details(chosen_move.lower())
                a_move = {"name": chosen_move, "power": mi.get("power") or 50,
                          "damage_class": mi.get("damage_class") or {"name":"physical"},
                          "type": mi.get("type") or {"name":"normal"}}
            except Exception:
                pass
            # Opponent move
            b_move = await self.cog._pick_move(B)
        else:
            b_move = {"name": chosen_move, "power": 50, "damage_class": {"name": "physical"}, "type":{"name":"normal"}}
            try:
                mi = await self.cog._get_move_details(chosen_move.lower())
                b_move = {"name": chosen_move, "power": mi.get("power") or 50,
                          "damage_class": mi.get("damage_class") or {"name":"physical"},
                          "type": mi.get("type") or {"name":"normal"}}
            except Exception:
                pass
            a_move = await self.cog._pick_move(A)

        # Speed order
        # Speed order
        A_spd = self.cog._safe_stats(A)["speed"]
        B_spd = self.cog._safe_stats(B)["speed"]
        first_A = True if A_spd >= B_spd else False
        
        actions: List[str] = []
        
        def perform_attack(attacker, defender, move, a_cur, d_cur, a_store, d_store):
            """Inner helper to apply one attack and build text."""
            dmg = self.cog._calc_move_damage(attacker, defender, move)
            d_cur = max(0, d_cur - dmg)
            msg = f"{attacker.get('nickname') or attacker['name']} used **{move['name'].title()}** → {defender.get('nickname') or defender['name']} took **{dmg}** damage!"
            if attacker.get("_last_eff_msg"):
                msg += f"\n{attacker['_last_eff_msg']}"
            if attacker.get("_last_crit"):
                msg += "\n**💥A critical hit!💥**"
            return d_cur, msg
        
        if first_A:
            if A_cur > 0 and B_cur > 0:
                B_cur, msg = perform_attack(A, B, a_move, A_cur, B_cur, self.caller_hp, self.opp_hp)
                actions.append(msg)
            if B_cur > 0 and A_cur > 0:
                A_cur, msg = perform_attack(B, A, b_move, B_cur, A_cur, self.opp_hp, self.caller_hp)
                actions.append(msg)
        else:
            if B_cur > 0 and A_cur > 0:
                A_cur, msg = perform_attack(B, A, b_move, B_cur, A_cur, self.opp_hp, self.caller_hp)
                actions.append(msg)
            if A_cur > 0 and B_cur > 0:
                B_cur, msg = perform_attack(A, B, a_move, A_cur, B_cur, self.caller_hp, self.opp_hp)
                actions.append(msg)


        # Apply clamps & save HP
        A_cur = max(0, A_cur); B_cur = max(0, B_cur)
        self._set_hp(A, A_cur, self.caller_hp)
        self._set_hp(B, B_cur, self.opp_hp)

        # Log
        self._action_log.extend(actions)

        # Check faint → advance
        if A_cur <= 0:
            self.ci += 1
        if B_cur <= 0:
            self.oi += 1

        # If fight continues, refresh to show new HP (and maybe new mon)
        if self._alive():
            await self._refresh(interaction)
            return

        # Otherwise, finish and show results
        await self._finish_battle(interaction)

    # ---------- finishing / XP / Results ----------
    async def _finish_battle(self, interaction: discord.Interaction):
        # Compute who won
        caller_alive = self.ci < len(self.caller_team)
        match_winner = "caller" if caller_alive else "opp"

        # XP bucketting (similar to your teambattle routine; keep it slim here)
        # We'll just give a flat team bonus to winner and a smaller one to loser,
        # then let the existing add_xp / _give_stat_points handle progression.
        caller_avg = self.cog._avg_level(self.caller_team)
        opp_avg = self.cog._avg_level(self.opp_team)
        caller_scale = self.cog._xp_scale(caller_avg, opp_avg)
        opp_scale = self.cog._xp_scale(opp_avg, caller_avg)
        bonus_caller = int(round(40 * caller_scale))
        bonus_opp = int(round(25 * opp_scale))

        if match_winner == "caller":
            for e in self.caller_team:
                self._caller_awards[e["uid"]] = self._caller_awards.get(e["uid"], 0) + bonus_caller
        else:
            for e in self.opp_team:
                self._opp_awards[e["uid"]] = self._opp_awards.get(e["uid"], 0) + bonus_opp

        # Apply XP & pending points to real boxes (ignore NPC persistence)
        async def apply_awards(member: discord.abc.User, team: List[Dict[str, Any]], awards: Dict[str,int]) -> List[str]:
            box: List[Dict[str, Any]] = await self.cog.config.user(member).pokebox()
            # Replace updated entries back into the user's box
            updated = {str(e["uid"]): e for e in team if e.get("uid")}
            out_lines = []
            for i, be in enumerate(box):
                uid = str(be.get("uid"))
                if uid in awards:
                    gain = int(awards[uid])
                    before = int(be.get("level", 1))
                    lvl, xp, _ = self.cog._add_xp_to_entry(be, gain)
                    pts = self.cog._give_stat_points_for_levels(before, lvl)
                    be["pending_points"] = int(be.get("pending_points", 0)) + pts
                    out_lines.append(f"`{uid}` {be.get('nickname') or be.get('name','?')} +{gain} XP → Lv {before}→**{lvl}** (+{pts} pts)")
                box[i] = be
            await self.cog.config.user(member).pokebox.set(box)
            return out_lines

        caller_lines = await apply_awards(self.caller, self.caller_team, self._caller_awards)
        opp_lines: List[str] = []
        if self.opponent:
            opp_lines = await apply_awards(self.opponent, [e for e in self.opp_team if not e.get("_npc")], self._opp_awards)

        # Build results embed (compact)
        title = "🏆 Victory!" if match_winner == "caller" else f"💥 Defeat vs {(self.opponent.display_name if self.opponent else 'NPC')}"
        color = discord.Color.green() if match_winner == "caller" else discord.Color.red()
        results = discord.Embed(title=title, color=color)
        results.add_field(
            name=f"{self.caller.display_name}",
            value="\n".join(caller_lines) or "_No XP changes_",
            inline=False
        )
        if self.opponent and opp_lines:
            results.add_field(
                name=f"{self.opponent.display_name}",
                value="\n".join(opp_lines),
                inline=False
            )
        if self._action_log:
            results.add_field(name="Last turns", value="\n".join(self._action_log[-6:]), inline=False)

        # Replace controls with a simple Close
        self._disable_all()
        # keep Close enabled
        for child in self.children:
            if isinstance(child, discord.ui.Button) and getattr(child, "custom_id", None) == "close":
                child.disabled = False
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        await self.message.edit(embed=results, view=self)

    @discord.ui.button(label="⏭ Auto-Sim to Results", style=discord.ButtonStyle.primary, custom_id="auto")
    async def auto_sim(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Instantly skip to the end result, no step pages or new images."""
        # Graceful defer
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
    
        # Pick winner at random or by remaining team HP
        total_hp_caller = sum(cur for cur, _ in self.caller_hp.values())
        total_hp_opp = sum(cur for cur, _ in self.opp_hp.values())
        caller_alive = total_hp_caller >= total_hp_opp
    
        # Basic XP scaling
        caller_aw, opp_aw = {}, {}
        caller_avg = self.cog._avg_level(self.caller_team)
        opp_avg = self.cog._avg_level(self.opp_team)
        caller_scale = self.cog._xp_scale(caller_avg, opp_avg)
        opp_scale = self.cog._xp_scale(opp_avg, caller_avg)
        win_bonus, lose_bonus = 40, 25
    
        if caller_alive:
            for e in self.caller_team:
                caller_aw[e["uid"]] = int(round(win_bonus * caller_scale))
            for e in self.opp_team:
                opp_aw[e["uid"]] = int(round(lose_bonus * opp_scale))
        else:
            for e in self.caller_team:
                caller_aw[e["uid"]] = int(round(lose_bonus * caller_scale))
            for e in self.opp_team:
                opp_aw[e["uid"]] = int(round(win_bonus * opp_scale))
    
        # Apply XP (simple: reuse your add_xp helpers)
        async def apply_awards(member, team, awards):
            box = await self.cog.config.user(member).pokebox()
            for i, be in enumerate(box):
                uid = str(be.get("uid"))
                if uid in awards:
                    before = int(be.get("level", 1))
                    lvl, xp, _ = self.cog._add_xp_to_entry(be, awards[uid])
                    pts = self.cog._give_stat_points_for_levels(before, lvl)
                    be["pending_points"] = int(be.get("pending_points", 0)) + pts
                box[i] = be
            await self.cog.config.user(member).pokebox.set(box)
    
        await apply_awards(self.caller, self.caller_team, caller_aw)
        if self.opponent:
            await apply_awards(self.opponent, [e for e in self.opp_team if not e.get("_npc")], opp_aw)
    
        # Make results embed
        winner = self.caller if caller_alive else (self.opponent or "NPC")
        title = f"🏆 {winner} Wins!" if caller_alive else f"💥 {winner} Wins!"
        color = discord.Color.green() if caller_alive else discord.Color.red()
        em = discord.Embed(title=title, color=color)
    
        def fmt(team, awards):
            return "\n".join(
                f"`{e.get('uid','?')}` {e.get('nickname') or e.get('name','?')} +{awards.get(e['uid'],0)} XP"
                for e in team
            ) or "_No team_"
    
        em.add_field(name=self.caller.display_name, value=fmt(self.caller_team, caller_aw), inline=False)
        if self.opponent:
            em.add_field(name=self.opponent.display_name, value=fmt(self.opp_team, opp_aw), inline=False)
    
        em.set_footer(text="Battle skipped directly to results")
    
        # Disable all buttons except Close
        self._disable_all()
        for child in self.children:
            if isinstance(child, discord.ui.Button) and getattr(child, "custom_id", None) == "close":
                child.disabled = False
    
        # Show result instantly
        await self.message.edit(embed=em, view=self, attachments=[])



    @discord.ui.button(label="✖ Close", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._disable_all()
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        if self.message:
            await self.message.edit(view=self)
        self.stop()



    
            




async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCatchEmAll(bot))
