from __future__ import annotations
import asyncio
import json
import math
import random
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.chat_formatting import humanize_timedelta
from redbot.core.utils import chat_formatting as cf
from redbot.core.data_manager import cog_data_path

__all__ = ["setup"]

# ---------------------------
# Data Models
# ---------------------------

RARITIES = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]

@dataclass
class Move:
    name: str
    power: int
    accuracy: int = 95
    crit: float = 0.05

@dataclass
class Species:
    name: str
    rarity: str
    base_hp: int
    base_atk: int
    base_def: int
    base_spd: int
    moves: List[str]

@dataclass
class Mon:
    id: str
    species: str
    rarity: str
    level: int
    xp: int
    max_hp: int
    hp: int
    atk: int
    defn: int
    spd: int
    moves: List[str]
    fainted: bool = False
    last_fought: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())

    @classmethod
    def from_species(cls, sp: Species, level: int) -> "Mon":
        def scale(base: int, lvl: int, mult: float = 1.0) -> int:
            return max(1, int(base + (lvl ** 1.2) * mult))
        rarity_mult = {
            "COMMON": 1.00,
            "UNCOMMON": 1.05,
            "RARE": 1.10,
            "EPIC": 1.18,
            "LEGENDARY": 1.28,
        }[sp.rarity]
        max_hp = scale(sp.base_hp, level, 2.0)
        atk = int(scale(sp.base_atk, level, 1.0) * rarity_mult)
        defn = int(scale(sp.base_def, level, 1.0) * rarity_mult)
        spd = int(scale(sp.base_spd, level, 0.8) * rarity_mult)
        return cls(
            id=str(uuid.uuid4())[:8],
            species=sp.name,
            rarity=sp.rarity,
            level=level,
            xp=0,
            max_hp=max_hp,
            hp=max_hp,
            atk=atk,
            defn=defn,
            spd=spd,
            moves=sp.moves[:2],
        )

    def gain_xp(self, amount: int) -> Tuple[int, bool]:
        self.xp += amount
        needed = 50 + (self.level ** 1.4) * 10
        leveled = False
        while self.xp >= needed and self.level < 100:
            self.xp -= int(needed)
            self.level += 1
            growth = 1.04
            self.max_hp = int(self.max_hp * growth)
            self.atk = int(self.atk * growth)
            self.defn = int(self.defn * growth)
            self.spd = int(self.spd * growth)
            self.hp = self.max_hp
            needed = 50 + (self.level ** 1.4) * 10
        return self.level, leveled

# ---------------------------
# Defaults for auto-created files
# ---------------------------

DEFAULT_MOVES = {
    "Tackle": {"name": "Tackle", "power": 40, "accuracy": 95, "crit": 0.05},
    "Gust": {"name": "Gust", "power": 40, "accuracy": 100, "crit": 0.05},
    "Water Gun": {"name": "Water Gun", "power": 50, "accuracy": 95, "crit": 0.05},
    "Quick Attack": {"name": "Quick Attack", "power": 40, "accuracy": 100, "crit": 0.08},
    "Wing Attack": {"name": "Wing Attack", "power": 60, "accuracy": 95, "crit": 0.05},
    "Slash": {"name": "Slash", "power": 70, "accuracy": 95, "crit": 0.12},
}

DEFAULT_SPECIES = {
    "Wingull": {"name": "Wingull", "rarity": "COMMON", "base_hp": 30, "base_atk": 30, "base_def": 25, "base_spd": 60, "moves": ["Gust", "Water Gun", "Quick Attack", "Wing Attack"]},
    "Zigzagoon": {"name": "Zigzagoon", "rarity": "COMMON", "base_hp": 38, "base_atk": 35, "base_def": 30, "base_spd": 60, "moves": ["Tackle", "Quick Attack", "Slash"]},
    "Ralts": {"name": "Ralts", "rarity": "UNCOMMON", "base_hp": 28, "base_atk": 25, "base_def": 25, "base_spd": 40, "moves": ["Tackle", "Quick Attack"]},
    "Beldum": {"name": "Beldum", "rarity": "RARE", "base_hp": 40, "base_atk": 55, "base_def": 50, "base_spd": 30, "moves": ["Tackle"]},
    "Dratini": {"name": "Dratini", "rarity": "EPIC", "base_hp": 41, "base_atk": 64, "base_def": 45, "base_spd": 50, "moves": ["Tackle", "Quick Attack", "Slash"]},
    "Latios": {"name": "Latios", "rarity": "LEGENDARY", "base_hp": 80, "base_atk": 90, "base_def": 80, "base_spd": 110, "moves": ["Quick Attack", "Slash", "Wing Attack"]},
}

DEFAULT_BALLS = {
    "pokeball": {"price": 50, "level_range": [1, 20], "rates": {"COMMON": 0.72, "UNCOMMON": 0.22, "RARE": 0.05, "EPIC": 0.01, "LEGENDARY": 0.0}},
    "greatball": {"price": 200, "level_range": [10, 40], "rates": {"COMMON": 0.60, "UNCOMMON": 0.26, "RARE": 0.10, "EPIC": 0.04, "LEGENDARY": 0.0}},
    "ultraball": {"price": 750, "level_range": [25, 70], "rates": {"COMMON": 0.45, "UNCOMMON": 0.30, "RARE": 0.16, "EPIC": 0.08, "LEGENDARY": 0.01}},
    "masterball": {"price": 5000, "level_range": [50, 100], "rates": {"COMMON": 0.00, "UNCOMMON": 0.20, "RARE": 0.35, "EPIC": 0.35, "LEGENDARY": 0.10}},
}

# Healing & battle constants
HEAL_TIME_PER_MISSING_HP_SEC = 18
HEAL_INSTANT_COST_PER_MISSING_HP = 1
BATTLE_INTERVAL_MINUTES = 5
BATTLE_TEAM_SIZE = 6
XP_PER_WIN = 40
XP_PER_LOSS = 20
WC_REWARD_WIN = 20
WC_REWARD_LOSS = 8
DAMAGE_VARIANCE = 0.12

# ---------------------------
# File I/O helpers
# ---------------------------

class ContentStore:
    def __init__(self, cog: "GachaCatchEmAll"):
        self.cog = cog
        self.base = cog_data_path(raw_name=cog.__class__.__name__)
        self.moves_path = self.base / "moves.json"
        self.species_path = self.base / "species.json"
        self.balls_path = self.base / "balls.json"
        self.base.mkdir(parents=True, exist_ok=True)
        

    def _ensure_file(self, path, default_dict):
        if not path.exists():
            path.write_text(json.dumps(default_dict, indent=2))

    def ensure_defaults(self):
        self._ensure_file(self.moves_path, DEFAULT_MOVES)
        self._ensure_file(self.species_path, DEFAULT_SPECIES)
        self._ensure_file(self.balls_path, DEFAULT_BALLS)

    def load_moves(self) -> Dict[str, Move]:
        data = json.loads(self.moves_path.read_text())
        return {k: Move(**v) for k, v in data.items()}

    def load_species(self) -> Dict[str, Species]:
        data = json.loads(self.species_path.read_text())
        return {k: Species(**v) for k, v in data.items()}

    def load_balls(self) -> Dict[str, dict]:
        return json.loads(self.balls_path.read_text())

    def export_all(self) -> Dict[str, dict]:
        return {
            "moves": json.loads(self.moves_path.read_text()),
            "species": json.loads(self.species_path.read_text()),
            "balls": json.loads(self.balls_path.read_text()),
        }

# ---------------------------
# Economy Adapter (official Wellcoins first; fallback to local wallet)
# ---------------------------

class EconomyAdapter:
    def __init__(self, bot: Red, config: Config):
        self.bot = bot
        self.config = config
        # Name of the other cog exposing the API. Admin can change via /pokeadmin_seteconomy
        self.service_cog_name: str = "WellcoinService"

    async def set_service_name(self, name: str):
        await self.config.service_cog_name.set(name)
        self.service_cog_name = name

    async def _service(self):
        # Reload configured name if present
        try:
            name = await self.config.service_cog_name()
            if name:
                self.service_cog_name = name
        except Exception:
            pass
        return self.bot.get_cog(self.service_cog_name)

    # ---- Official path (preferred) ----
    async def wc_get(self, user: discord.abc.User) -> float:
        svc = await self._service()
        if svc and hasattr(svc, "get_balance"):
            return float(await svc.get_balance(user))
        # Fallback to local wallet
        return float(await self.config.user(user).wallet())

    async def wc_add(self, user: discord.abc.User, amount: float) -> float:
        svc = await self._service()
        if svc and hasattr(svc, "add_wellcoins"):
            return float(await svc.add_wellcoins(user, float(amount)))
        async with self.config.user(user).wallet() as w:
            w += max(0, int(amount))
            return float(w)

    async def wc_take(self, user: discord.abc.User, amount: float, *, force: bool=False) -> Tuple[bool, float]:
        svc = await self._service()
        if svc and hasattr(svc, "take_wellcoins"):
            try:
                new_bal = await svc.take_wellcoins(user, float(amount), force=force)
                return True, float(new_bal)
            except Exception:
                return False, await self.wc_get(user)
        # Fallback local wallet
        async with self.config.user(user).wallet() as w:
            if not force and w < amount:
                return False, float(w)
            w -= int(amount)
            return True, float(w)

# ---------------------------
# Battle Engine
# ---------------------------

def _hit(move: Move, attacker: Mon, defender: Mon) -> Tuple[int, bool, bool]:
    if random.random() > (move.accuracy / 100.0):
        return 0, False, False
    crit = random.random() < move.crit
    base = max(1, int((attacker.atk / max(1, defender.defn)) * move.power))
    roll = 1.0 + random.uniform(-DAMAGE_VARIANCE, DAMAGE_VARIANCE)
    dmg = int(base * roll * (1.6 if crit else 1.0))
    return max(1, dmg), True, crit

async def simulate_match(team_a: List[Mon], team_b: List[Mon]) -> Tuple[bool, List[Mon], List[Mon], List[str]]:
    log: List[str] = []
    a = [Mon(**asdict(m)) for m in team_a]
    b = [Mon(**asdict(m)) for m in team_b]
    ai = bi = 0
    while ai < len(a) and bi < len(b):
        mon_a = a[ai]
        mon_b = b[bi]
        if mon_a.hp <= 0:
            ai += 1
            continue
        if mon_b.hp <= 0:
            bi += 1
            continue
        first, second = (mon_a, mon_b) if mon_a.spd >= mon_b.spd else (mon_b, mon_a)
        for attacker, defender in ((first, second), (second, first)):
            if attacker.hp <= 0 or defender.hp <= 0:
                continue
            move_name = random.choice(attacker.moves)
            mv = GachaCatchEmAll.MOVES.get(move_name, Move("Tackle", 40))
            dmg, hit, crit = _hit(mv, attacker, defender)
            if hit:
                defender.hp = max(0, defender.hp - dmg)
                if defender.hp <= 0:
                    defender.fainted = True
            if defender.hp <= 0 and defender is second:
                break
        if mon_a.hp <= 0:
            ai += 1
        if mon_b.hp <= 0:
            bi += 1
        if (ai + bi) > 120:
            break
    a_alive = sum(1 for m in a if m.hp > 0)
    b_alive = sum(1 for m in b if m.hp > 0)
    a_wins = a_alive >= b_alive
    return a_wins, a, b, log

# ---------------------------
# Cog
# ---------------------------

class GachaCatchEmAll(commands.Cog):
    MOVES: Dict[str, Move] = {}
    SPECIES: Dict[str, Species] = {}
    BALLS: Dict[str, dict] = {}

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xA17AB0A, force_registration=True)
        self.config.register_global(enabled=True, service_cog_name="WellcoinService")
        self.config.register_user(mons={}, team=[], wallet=500, elo=1000, last_heal={}, autobattle=True)
        self.content = ContentStore(self)
        self.content.ensure_defaults()
        self._load_content()
        self.econ = EconomyAdapter(bot, self.config)
        self._task = asyncio.create_task(self._battle_loop())
        self.dev_guild_id: int | None = None  # set a guild for instant dev sync

    # ---- content loading ----
    def _load_content(self):
        GachaCatchEmAll.MOVES = self.content.load_moves()
        GachaCatchEmAll.SPECIES = self.content.load_species()
        GachaCatchEmAll.BALLS = self.content.load_balls()

    # ---- Red lifecycle ----
    def cog_unload(self):
        if self._task:
            self._task.cancel()
    
    async def cog_load(self):
        # Add your slash commands to the tree
        cmds = [
            self.roll, self.balls, self.mons, self.inspect, self.team,
            self.heal, self.healsync, self.balance, self.ladder,
            self.toggleautobattle, self.pokeadmin_reload, self.pokeadmin_export,
            self.pokeadmin_seteconomy, self.pokeadmin_setball,
        ]
        for cmd in cmds:
            try:
                self.bot.tree.add_command(cmd)
            except Exception:
                pass

        # Sync: guild-specific = instant; global can take a while
        try:
            if self.dev_guild_id:
                guild = discord.Object(id=self.dev_guild_id)
                await self.bot.tree.sync(guild=guild)
            else:
                await self.bot.tree.sync()
        except Exception as e:
            print(f"[GachaCatchEmAll] tree sync failed: {e}")

    # -------------------
    # Helpers
    # -------------------

    async def ac_ball(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        keys = list(PokeAutoBattler.BALLS.keys())
        if current:
            keys = [k for k in keys if current.lower() in k.lower()]
        keys = keys[:25]
        return [app_commands.Choice(name=k.title(), value=k) for k in keys]

    async def _get_user_mons(self, user: discord.User) -> Dict[str, dict]:
        return await self.config.user(user).mons()

    async def _save_mon(self, user: discord.User, mon: Mon) -> None:
        async with self.config.user(user).mons() as mons:
            mons[mon.id] = asdict(mon)

    async def _get_team(self, user: discord.User) -> List[str]:
        return await self.config.user(user).team()

    async def _set_team(self, user: discord.User, team: List[str]) -> None:
        await self.config.user(user).team.set(team[:BATTLE_TEAM_SIZE])

    def _choose_rarity(self, rates: Dict[str, float]) -> str:
        roll = random.random()
        cum = 0.0
        for r in RARITIES:
            p = rates.get(r, 0.0)
            cum += p
            if roll <= cum:
                return r
        return "COMMON"

    async def _roll_one(self, ball_key: str) -> Optional[Mon]:
        ball = GachaCatchEmAll.BALLS.get(ball_key)
        if not ball:
            return None
        rarity = self._choose_rarity(ball["rates"])
        candidates = [sp for sp in GachaCatchEmAll.SPECIES.values() if sp.rarity == rarity]
        if not candidates:
            candidates = list(GachaCatchEmAll.SPECIES.values())
        sp = random.choice(candidates)
        lvl = random.randint(ball["level_range"][0], ball["level_range"][1])
        return Mon.from_species(sp, lvl)

    async def _eligible_users(self) -> List[int]:
        ids: List[int] = []
        all_conf = await self.config.all_users()
        for uid, data in all_conf.items():
            if data.get("autobattle", True) and len(data.get("team", [])) >= 1:
                ids.append(int(uid))
        random.shuffle(ids)
        return ids

    async def _load_team_objs(self, user_id: int) -> List[Mon]:
        user = self.bot.get_user(user_id)
        if not user:
            return []
        mons = await self._get_user_mons(user)
        team_ids = (await self._get_team(user))[:BATTLE_TEAM_SIZE]
        team: List[Mon] = []
        for mid in team_ids:
            d = mons.get(mid)
            if not d:
                continue
            m = Mon(**d)
            if m.hp > 0:
                team.append(m)
        return team

    async def _apply_post_battle(self, user_id: int, before: List[Mon], after: List[Mon], *, win: bool):
        user = self.bot.get_user(user_id)
        if not user:
            return
        async with self.config.user(user).mons() as mons:
            for m_before, m_after in zip(before, after):
                if m_before.id not in mons:
                    continue
                d = mons[m_before.id]
                d["hp"] = max(0, int(m_after.hp))
                d["fainted"] = d["hp"] <= 0
                mon_obj = Mon(**d)
                mon_obj.gain_xp(XP_PER_WIN if win else XP_PER_LOSS)
                mons[m_before.id] = asdict(mon_obj)
        wc = WC_REWARD_WIN if win else WC_REWARD_LOSS
        await self.econ.wc_add(user, wc)

    async def _battle_loop(self):
        await self.bot.wait_until_ready()
        try:
            while True:
                if not await self.config.enabled():
                    await asyncio.sleep(60)
                    continue
                ids = await self._eligible_users()
                if len(ids) >= 2:
                    for i in range(0, len(ids)-1, 2):
                        a_id, b_id = ids[i], ids[i+1]
                        a_team = await self._load_team_objs(a_id)
                        b_team = await self._load_team_objs(b_id)
                        if not a_team or not b_team:
                            continue
                        a_wins, a_after, b_after, _ = await simulate_match(a_team, b_team)
                        await self._apply_post_battle(a_id, a_team, a_after, win=a_wins)
                        await self._apply_post_battle(b_id, b_team, b_after, win=not a_wins)
                await asyncio.sleep(BATTLE_INTERVAL_MINUTES * 60)
        except asyncio.CancelledError:
            pass

    # -------------------
    # Commands (slash)
    # -------------------

    @app_commands.command(name="balls", description="View ball prices and rates.")
    async def balls(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Gacha Balls", color=discord.Color.blurple())
        for k, v in GachaCatchEmAll.BALLS.items():
            rates = ", ".join(f"{r}: {int(p*100)}%" for r, p in v["rates"].items())
            embed.add_field(name=k.title(), value=f"Price: {v['price']} WC Levels: {v['level_range'][0]}–{v['level_range'][1]} Rates: {rates}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.describe(ball="pokeball/greatball/ultraball/masterball", count="1-10")
    @app_commands.autocomplete(ball=ac_ball)
    async def roll(self, interaction: discord.Interaction, ball: str, count: app_commands.Range[int,1,10]=1):
        ball = ball.lower()
        if ball not in GachaCatchEmAll.BALLS:
            await interaction.response.send_message("Unknown ball.", ephemeral=True)
            return
        total_cost = GachaCatchEmAll.BALLS[ball]["price"] * count
        ok, bal = await self.econ.wc_take(interaction.user, total_cost, force=False)
        if not ok:
            cur = await self.econ.wc_get(interaction.user)
            await interaction.response.send_message(f"Not enough Wellcoins. Need {total_cost}, you have {cur}.", ephemeral=True)
            return
        obtained: List[Mon] = []
        for _ in range(count):
            m = await self._roll_one(ball)
            if m:
                await self._save_mon(interaction.user, m)
                obtained.append(m)
        if not obtained:
            await interaction.response.send_message("You rolled… nothing? (Contact an admin.)", ephemeral=True)
            return
        lines = [f"You spent **{total_cost} WC** and obtained:"]
        for m in obtained:
            lines.append(f"`{m.id}` • Lv{m.level} **{m.species}** [{m.rarity.title()}] — HP {m.hp}/{m.max_hp}")
        await interaction.response.send_message("".join(lines))

    @app_commands.command(name="mons", description="List your collected monsters.")
    async def mons(self, interaction: discord.Interaction):
        mons = await self._get_user_mons(interaction.user)
        if not mons:
            await interaction.response.send_message("You don't own any monsters yet. Use /roll!", ephemeral=True)
            return
        lines = [f"`{d['id']}` • Lv{d['level']} **{d['species']}** [{d['rarity'].title()}] — HP {d['hp']}/{d['max_hp']}" for d in mons.values()]
        pages = list(pagify("".join(lines), page_length=1000))
        await interaction.response.send_message(pages[0])
        for p in pages[1:]:
            await interaction.followup.send(p)

    @app_commands.command(name="inspect", description="Inspect one of your monsters by ID.")
    async def inspect(self, interaction: discord.Interaction, mon_id: str):
        mons = await self._get_user_mons(interaction.user)
        d = mons.get(mon_id)
        if not d:
            await interaction.response.send_message("No such monster ID.", ephemeral=True)
            return
        m = Mon(**d)
        embed = discord.Embed(title=f"{m.species} • Lv {m.level} [{m.rarity.title()}]", color=discord.Color.green())
        embed.add_field(name="HP", value=f"{m.hp}/{m.max_hp}")
        embed.add_field(name="ATK", value=str(m.atk))
        embed.add_field(name="DEF", value=str(m.defn))
        embed.add_field(name="SPD", value=str(m.spd))
        embed.add_field(name="Moves", value=", ".join(m.moves), inline=False)
        embed.set_footer(text=f"ID: {m.id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="team", description="View or modify your team (max 6).")
    @app_commands.describe(action="view/add/remove/clear", mon_id="Required for add/remove")
    async def team(self, interaction: discord.Interaction, action: str, mon_id: Optional[str] = None):
        action = action.lower()
        if action not in {"view", "add", "remove", "clear"}:
            await interaction.response.send_message("Use action: view/add/remove/clear", ephemeral=True)
            return
        if action in {"add", "remove"} and not mon_id:
            await interaction.response.send_message("Provide a mon_id.", ephemeral=True)
            return
        user = interaction.user
        mons = await self._get_user_mons(user)
        team = await self._get_team(user)
        if action == "view":
            if not team:
                await interaction.response.send_message("Your team is empty. Use /team add <id>.", ephemeral=True)
                return
            lines = []
            for i, tid in enumerate(team, 1):
                d = mons.get(tid)
                if not d:
                    continue
                lines.append(f"{i}. `{d['id']}` • Lv{d['level']} **{d['species']}** — HP {d['hp']}/{d['max_hp']}")
            await interaction.response.send_message("".join(lines))
            return
        if action == "add":
            if mon_id not in mons:
                await interaction.response.send_message("You don't own that ID.", ephemeral=True)
                return
            if mon_id in team:
                await interaction.response.send_message("It's already on your team.", ephemeral=True)
                return
            if len(team) >= BATTLE_TEAM_SIZE:
                await interaction.response.send_message(f"Team full. Remove one first (max {BATTLE_TEAM_SIZE}).", ephemeral=True)
                return
            team.append(mon_id)
            await self._set_team(user, team)
            await interaction.response.send_message("Added to your team.")
            return
        if action == "remove":
            if mon_id not in team:
                await interaction.response.send_message("That ID isn't on your team.", ephemeral=True)
                return
            team.remove(mon_id)
            await self._set_team(user, team)
            await interaction.response.send_message("Removed from your team.")
            return
        if action == "clear":
            await self._set_team(user, [])
            await interaction.response.send_message("Cleared your team.")
            return

    @app_commands.command(name="heal", description="Heal a monster (time or instant with Wellcoins).")
    @app_commands.describe(mon_id="ID to heal", mode="time/instant")
    async def heal(self, interaction: discord.Interaction, mon_id: str, mode: str):
        mode = mode.lower()
        mons = await self._get_user_mons(interaction.user)
        d = mons.get(mon_id)
        if not d:
            await interaction.response.send_message("No such monster.", ephemeral=True)
            return
        m = Mon(**d)
        missing = max(0, m.max_hp - m.hp)
        if missing == 0:
            await interaction.response.send_message("Already at full HP!", ephemeral=True)
            return
        if mode == "time":
            secs = missing * HEAL_TIME_PER_MISSING_HP_SEC
            eta = datetime.now(timezone.utc) + timedelta(seconds=secs)
            async with self.config.user(interaction.user).last_heal() as heals:
                heals[mon_id] = eta.timestamp()
            await interaction.response.send_message(f"Healing started. Ready in {humanize_timedelta(seconds=secs)}.")
            return
        elif mode == "instant":
            cost = missing * HEAL_INSTANT_COST_PER_MISSING_HP
            ok, _ = await self.econ.wc_take(interaction.user, cost, force=False)
            if not ok:
                cur = await self.econ.wc_get(interaction.user)
                await interaction.response.send_message(f"Need {cost} WC, you have {cur}.", ephemeral=True)
                return
            m.hp = m.max_hp
            m.fainted = False
            await self._save_mon(interaction.user, m)
            await interaction.response.send_message(f"Healed instantly for {cost} WC.")
            return
        else:
            await interaction.response.send_message("Mode must be 'time' or 'instant'.", ephemeral=True)

    @app_commands.command(name="healsync", description="Complete any time-based heals that are ready.")
    async def healsync(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc).timestamp()
        changed = 0
        async with self.config.user(interaction.user).last_heal() as heals:
            for mid, ts in list(heals.items()):
                if ts <= now:
                    mons = await self._get_user_mons(interaction.user)
                    d = mons.get(mid)
                    if not d:
                        heals.pop(mid, None)
                        continue
                    m = Mon(**d)
                    m.hp = m.max_hp
                    m.fainted = False
                    await self._save_mon(interaction.user, m)
                    heals.pop(mid, None)
                    changed += 1
        await interaction.response.send_message(f"Completed {changed} heals.")

    @app_commands.command(name="balance", description="Check your Wellcoins.")
    async def balance(self, interaction: discord.Interaction):
        bal = await self.econ.wc_get(interaction.user)
        await interaction.response.send_message(f"You have **{bal}** WC.")

    @app_commands.command(name="ladder", description="Show top players by ELO (simple).")
    async def ladder(self, interaction: discord.Interaction):
        users = await self.config.all_users()
        rows = []
        for uid, d in users.items():
            rows.append((int(uid), d.get("elo", 1000)))
        rows.sort(key=lambda x: x[1], reverse=True)
        desc = []
        for rank, (uid, elo) in enumerate(rows[:20], 1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            desc.append(f"#{rank} — {name}: **{elo}** ELO")
        embed = discord.Embed(title="Ladder", description="".join(desc) or "No players yet.", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="toggleautobattle", description="Enable/disable passive auto-battles for you.")
    async def toggleautobattle(self, interaction: discord.Interaction):
        cur = await self.config.user(interaction.user).autobattle()
        await self.config.user(interaction.user).autobattle.set(not cur)
        await interaction.response.send_message(f"Auto-battles {'enabled' if not cur else 'disabled'}.")

    # -------------------
    # Admin / Content management
    # -------------------

    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="pokeadmin_reload", description="Reload moves/species/balls from JSON files.")
    async def pokeadmin_reload(self, interaction: discord.Interaction):
        self._load_content()
        await interaction.response.send_message("Reloaded moves/species/balls from JSON.")

    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="pokeadmin_export", description="Export current content as JSON (files are already on disk).")
    async def pokeadmin_export(self, interaction: discord.Interaction):
        data = self.content.export_all()
        # Summarize keys to avoid dumping huge blobs in chat
        summary = (f"moves: {len(data['moves'])} keys, species: {len(data['species'])} keys, balls: {len(data['balls'])} keys")
        await interaction.response.send_message(f"Export present on disk in the cog data folder. Summary: {summary}")

    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="pokeadmin_seteconomy", description="Set the Wellcoin service cog name (default: WellcoinService).")
    async def pokeadmin_seteconomy(self, interaction: discord.Interaction, cog_name: str):
        await self.econ.set_service_name(cog_name)
        await interaction.response.send_message(f"Economy service set to: {cog_name}")

    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="pokeadmin_setball", description="Edit a ball tier and save to balls.json.")
    async def pokeadmin_setball(self, interaction: discord.Interaction, key: str, price: int, lvl_min: int, lvl_max: int,
                                common: float, uncommon: float, rare: float, epic: float, legendary: float):
        balls = self.content.load_balls()
        balls[key.lower()] = {
            "price": price,
            "level_range": [lvl_min, lvl_max],
            "rates": {"COMMON": float(common), "UNCOMMON": float(uncommon), "RARE": float(rare), "EPIC": float(epic), "LEGENDARY": float(legendary)},
        }
        self.content.balls_path.write_text(json.dumps(balls, indent=2))
        self._load_content()
        await interaction.response.send_message(f"Ball '{key}' saved to JSON and reloaded.")
    



# ---------------------------
# Setup
# ---------------------------

async def setup(bot: Red) -> None:
    await bot.add_cog(GachaCatchEmAll(bot))
