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
        a_stats = self._safe_stats(attacker)
        d_stats = self._safe_stats(defender)
    
        power = move_info.get("power") or 50
        dmg_class = ((move_info.get("damage_class") or {}).get("name") or "physical").lower()
        mtype = ((move_info.get("type") or {}).get("name") or "").lower()
    
        atk = a_stats["attack"] if dmg_class == "physical" else a_stats["special-attack"]
        deff = d_stats["defense"] if dmg_class == "physical" else d_stats["special-defense"]
    
        dmg = (power * max(1, atk)) / max(1, deff)
    
        # STAB
        atk_types = [t.lower() for t in (attacker.get("types") or [])]
        if mtype in atk_types:
            dmg *= 1.2
    
        # small variance
        dmg *= random.uniform(0.85, 1.0)
    
        # difficulty tag (e.g., NPC “boss”)
        dmg *= float(attacker.get("_dmg_mult", 1.0))
    
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
        Battle with teams of up to 6. If opponent is omitted, you'll fight an NPC team
        near your team's average level. Everyone gains XP, scaled by level difference.
        """
        await ctx.send("searching for oppenent this can take a moment or two...")
        caller = ctx.author
        opp = opponent
    
        # ----- Load caller team (fallback = top 6 by level)
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

        mode = "normal"
        r = random.random()
        if r < 0.10:
            mode = "boss"
        elif r < 0.35:
            mode = "hard"
        profile = DIFFICULTY_PROFILES.get(mode, DIFFICULTY_PROFILES["normal"])
        
        # ----- Load opponent team or generate NPC team
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
            opp_team = await self._generate_npc_team(target_avg_level=avg_lvl, size=min(6, len(caller_team) or 6))
            await self._apply_difficulty_to_npc_team(opp_team, profile)
    
        # ----- Team vs Team (frontline KO → next)
        ci = oi = 0
        duel_count = 0
    
        caller_awards: Dict[str, int] = {}
        opp_awards: Dict[str, int] = {}
    
        # collect per-duel actions for page rendering & short recap
        duel_action_packets: List[Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]] = []
        brief_recap: List[str] = []
        
# after caller_team / opp_team are finalized
        caller_hp: Dict[str, Tuple[int, int]] = {}
        opp_hp: Dict[str, Tuple[int, int]] = {}
        
        def _seed_hp_map(team, store):
            for e in team:
                mx = self._initial_hp(e)
                store[e["uid"]] = (mx, mx)  # (cur, max)
        
        _seed_hp_map(caller_team, caller_hp)
        _seed_hp_map(opp_team, opp_hp)

    
        while ci < len(caller_team) and oi < len(opp_team):
            A = caller_team[ci]
            B = opp_team[oi]
        
            A_cur, A_max = caller_hp[A["uid"]]
            B_cur, B_max = opp_hp[B["uid"]]
        
            winner, actions, A_end, B_end = await self._simulate_duel(A, B, A_start=A_cur, B_start=B_cur)
            duel_action_packets.append((A, B, actions))
        
            # Update carried HP
            caller_hp[A["uid"]] = (A_end, A_max)
            opp_hp[B["uid"]]   = (B_end, B_max)
        
            # Recap line (optional)
            if actions:
                first = actions[0]
                brief_recap.append(
                    f"— Duel {len(duel_action_packets)}: {A.get('nickname') or A['name']} (Lv {A.get('level',1)}) "
                    f"vs {B.get('nickname') or B['name']} (Lv {B.get('level',1)}) • first move: **{first['move_name']}**"
                )
        
            # XP scaling (unchanged)
            A_lvl = int(A.get("level", 1))
            B_lvl = int(B.get("level", 1))
            A_scale = self._xp_scale(A_lvl, B_lvl)
            B_scale = self._xp_scale(B_lvl, A_lvl)
            A_win_xp = int(round(40 * A_scale))
            A_lose_xp = int(round(25 * A_scale))
            B_win_xp = int(round(40 * B_scale))
            B_lose_xp = int(round(25 * B_scale))
        
            # Advance indexes based on who fainted (winner keeps remaining HP)
            if winner == "A":
                caller_awards[A["uid"]] = caller_awards.get(A["uid"], 0) + A_win_xp
                opp_awards[B["uid"]]   = opp_awards.get(B["uid"], 0) + B_lose_xp
                oi += 1  # B fainted; A stays with A_end HP
            else:
                caller_awards[A["uid"]] = caller_awards.get(A["uid"], 0) + A_lose_xp
                opp_awards[B["uid"]]   = opp_awards.get(B["uid"], 0) + B_win_xp
                ci += 1  # A fainted; B stays with B_end HP
        
            
        # ----- Match winner & team bonus
        caller_alive = ci < len(caller_team)
        match_winner = "caller" if caller_alive else "opp"
    
        caller_avg = self._avg_level(caller_team)
        opp_avg = self._avg_level(opp_team)
        caller_match_scale = self._xp_scale(caller_avg, opp_avg)
        opp_match_scale = self._xp_scale(opp_avg, caller_avg)
        bonus_caller = int(round(20 * caller_match_scale))
        bonus_opp = int(round(20 * opp_match_scale))
    
        if match_winner == "caller":
            for e in caller_team:
                caller_awards[e["uid"]] = caller_awards.get(e["uid"], 0) + bonus_caller
        else:
            for e in opp_team:
                opp_awards[e["uid"]] = opp_awards.get(e["uid"], 0) + bonus_opp
    
        # ----- Apply XP & pending points (ignore NPC persistence)
        def _apply_awards(entries: List[Dict[str, Any]], awards: Dict[str, int]) -> List[str]:
            lines = []
            for e in entries:
                uid = e.get("uid")
                if not uid or uid not in awards:
                    continue
                gain = int(awards[uid])
                before = int(e.get("level", 1))
                lvl, xp, _ = self._add_xp_to_entry(e, gain)
                pts = self._give_stat_points_for_levels(before, lvl)
                e["pending_points"] = int(e.get("pending_points", 0)) + pts
                lines.append(f"`{uid}` {e.get('nickname') or e.get('name','?')} +{gain} XP → Lv {before}→**{lvl}** (+{pts} pts)")
            return lines
    
        caller_progress = _apply_awards(caller_team, caller_awards)
        opp_progress = _apply_awards([e for e in opp_team if not e.get("_npc")], opp_awards)
    
        # persist boxes
        await self.config.user(caller).pokebox.set(caller_box)
        if opp and opp_progress:
            opp_box_full = await self.config.user(opp).pokebox()
            opp_map = {str(e.get("uid")): e for e in opp_team}
            new_opp_box = []
            for e in opp_box_full:
                uid = str(e.get("uid"))
                new_opp_box.append(opp_map.get(uid, e))
            await self.config.user(opp).pokebox.set(new_opp_box)
    
        # ----- Results page
        # ----- Results page (REPLACE OLD BLOCK WITH THIS) -----
        caller_won = (ci < len(caller_team))
        title = "🏆 Victory!" if caller_won else f"💥 Defeat vs {(opp.display_name if opp else 'NPC')}"
        color = discord.Color.green() if caller_won else discord.Color.red()
        results = discord.Embed(title=title, color=color)
        
        def _fmt_team_block(team: List[Dict[str, Any]], awards: Dict[str, int]) -> str:    
            lines: List[str] = []
            for e in team:
                lvl = int(e.get("level", 1))
                xp  = int(e.get("xp", 0))
                gained = int(awards.get(e.get("uid", ""), 0))
                bar = self._xp_bar(lvl, xp)  # uses your existing helper
                name = e.get("nickname") or e.get("name", "?")
                uid = e.get("uid", "?")
                # each mon: name + level on one line, XP bar on next
                lines.append(f"`{uid}` **{name}** — Lv **{lvl}** (+{gained} XP)\n{bar}")   
            return "\n".join(lines) if lines else "_No Pokémon_"
        
        # Caller team block
        results.add_field(
            name=f"{caller.display_name}",
            value=_fmt_team_block(caller_team),
            inline=False
        )
    
        
        # (Optional) keep your thumbnails/author icons after this, unchanged.

    
        # ----- Build one page per action (HP bars + BOTH sprites composited side-by-side)
        def hpbar(cur: int, mx: int) -> str:
            return self._hp_bar(cur, mx, width=20)
    
        header_base = f"{caller.display_name} vs {(opp.display_name if opp else 'NPC Team')}"
        pages_with_files: List[Tuple[discord.Embed, Optional[discord.File]]] = []
    
        for A, B, actions in duel_action_packets:
            duel_header = f"— {A.get('nickname') or A['name']} (Lv {A.get('level',1)}) vs {B.get('nickname') or B['name']} (Lv {B.get('level',1)})"
            for act in actions:
                a_bar = hpbar(act["A_hp"], act["A_max"])
                b_bar = hpbar(act["B_hp"], act["B_max"])
                desc = (
                    f"{duel_header}\n\n"
                    f"**Turn {act['turn']}** — "
                    f"{(caller.display_name + ' ') if act['attacker']=='A' else ((opp.display_name if opp else 'Opponent') + ' ')}"
                    f"{'(' + (act['A_name'] if act['attacker']=='A' else act['B_name']) + ')'} used **{act['move_name']}** "
                    f"for **{act['damage']}**\n\n"
                    f"**{act['A_name']}** HP: {a_bar}  {act['A_hp']}/{act['A_max']}\n"
                    f"**{act['B_name']}** HP: {b_bar}  {act['B_hp']}/{act['B_max']}\n"
                )
    
                em = discord.Embed(title=f"Battle — {header_base}", description=desc, color=discord.Color.teal())
    
                # Make a side-by-side image (if Pillow available & both URLs OK)
                file = await self._compose_vs_image(act["A_sprite"], act["B_sprite"])
                if file:
                    em.set_image(url="attachment://vs.png")
                else:
                    # Fallback: put A as thumb, B as author icon
                    if act["A_sprite"]:
                        em.set_thumbnail(url=act["A_sprite"])
                    if act["B_sprite"]:
                        em.set_author(name=act["B_name"], icon_url=act["B_sprite"])
    
                pages_with_files.append((em, file))
    
        if not pages_with_files:
            pages_with_files.append(
                (discord.Embed(title="Battle", description="Battle begins!", color=discord.Color.teal()), None)
            )
    
        # ----- Send paginator (NOTE: module-level BattlePaginator; no `self.`)
        view = BattlePaginator(
            author=caller,
            pages_with_files=pages_with_files,
            results_embed=results,
            opponent=opp
        )
    
        first_emb, first_file = view._current()
        if first_file:
            msg = await ctx.reply(embed=first_emb, file=first_file, view=view)
        else:
            msg = await ctx.reply(embed=first_emb, view=view)
        view.message = msg

        
        # Thumbnails (use first team sprites if available)
        def _first_sprite(team: List[Dict[str, Any]]) -> Optional[str]:
            for e in team:
                s = e.get("sprite")
                if s:
                    return s
            return None
        
        caller_thumb = _first_sprite(caller_team)
        opp_thumb = _first_sprite(opp_team)
        if caller_thumb:
            results.set_thumbnail(url=caller_thumb)
        if opp_thumb:
            # Put opponent sprite into the author icon if available (neat visual)
            results.set_author(name=(opp.display_name if opp else "NPC Team"), icon_url=opp_thumb)
        
        # ----- Build play-by-play pages -----
        # We already appended duel headlines and last 4 lines of each duel into battle_log.
        # Let's paginate the FULL play-by-play from all duels for a better story:
        full_lines: List[str] = []
        # Re-sim-summary: already in your loop you had per-duel 'log' (list of turn lines).
        # If you didn't store all, you can just use `battle_log` too. We'll use battle_log as-is:
        #full_lines = battle_log[:] if battle_log else ["Battle started."]
        
       #page_lines = self._chunk_lines(full_lines, size=6)  # 6 lines per page
        pages: List[discord.Embed] = []
        
        def _mk_page(lines: List[str], header: str, left_img: Optional[str], right_img: Optional[str]) -> discord.Embed:
            embed = discord.Embed(title=header, description="\n".join(lines), color=discord.Color.teal())
            if left_img:
                embed.set_thumbnail(url=left_img)
            if right_img:
                embed.set_author(name=(opp.display_name if opp else "NPC Team"), icon_url=right_img)
            return embed
        
        header_base = f"{caller.display_name} vs {(opp.display_name if opp else 'NPC Team')}"
        #for i, chunk in enumerate(page_lines, start=1):
            #pages.append(_mk_page(chunk, f"Battle — {header_base}", caller_thumb, opp_thumb))
        
        # Safety: at least one page
        if not pages:
        # Fallback: at least one generic page
            pages = [(discord.Embed(title="Battle", description="Battle begins!", color=discord.Color.teal()), None)]

    async def _simulate_duel(
        self,
        A: Dict[str, Any],
        B: Dict[str, Any],
        A_start: Optional[int] = None,
        B_start: Optional[int] = None
    ) -> Tuple[str, List[Dict[str, Any]], int, int]:
        a = dict(A); b = dict(B)
        A_max = self._initial_hp(a)
        B_max = self._initial_hp(b)
        
        A_hp = A_max if A_start is None else max(0, min(A_start, A_max))
        B_hp = B_max if B_start is None else max(0, min(B_start, B_max))
        
        A_spd = self._safe_stats(a)["speed"]
        B_spd = self._safe_stats(b)["speed"]
        first_is_A = True if A_spd >= B_spd else False
        
        actions: List[Dict[str, Any]] = []
        turn = 1
        while A_hp > 0 and B_hp > 0 and turn <= 100:
            order = [("A", a, b), ("B", b, a)] if first_is_A else [("B", b, a), ("A", a, b)]
            for who, atk, dfn in order:
                if A_hp <= 0 or B_hp <= 0:
                    break
                move = await self._pick_move(atk)
                dmg = self._calc_move_damage(atk, dfn, move)
                if who == "A":
                    B_hp -= dmg
                else:
                    A_hp -= dmg
                actions.append({
                        "attacker": who,
                        "move_name": str(move.get("name","")).title() or "Move",
                        "damage": int(dmg),
                        "A_hp": max(0, A_hp),
                        "B_hp": max(0, B_hp),
                        "A_max": int(A_max),
                        "B_max": int(B_max),
                        "A_name": a.get("nickname") or a.get("name", "?"),
                        "B_name": b.get("nickname") or b.get("name", "?"),
                        "A_sprite": a.get("sprite"),
                        "B_sprite": b.get("sprite"),
                        "turn": turn,
                })
            turn += 1
        
        winner = "A" if A_hp > 0 else ("B" if B_hp > 0 else random.choice(["A","B"]))
        return winner, actions, max(0, A_hp), max(0, B_hp)





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


    
            




async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCatchEmAll(bot))
