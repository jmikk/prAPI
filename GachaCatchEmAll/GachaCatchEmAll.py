# -*- coding: utf-8 -*-
"""
GachaCatchEmAll — a lightweight gacha/monster-collector cog for Redbot v3.

Features
- Reads a mons.json file (array of objects) with fields:
  Name, Type, Total, HP, Attack, Defense, Sp. Atk, Sp. Def, Speed, rarity
- Catch command with nets (normal/great/ultra/master) that cost Wellcoins via NexusExchange.
- Collection (dex) tracking and team of up to 6.
- Level/XP system with per-level stat allocation (points to assign by the player).
- Simple NPC battle (team of 6 vs generated NPC team) with XP rewards.
- Combine duplicates of the same species to merge XP and blend stats.

Notes
- Place your species file as data/{cog_name}/mons.json (see admin command [p]GachaCatchEmAll loadmons).
- Rarity is expected as one of: "common", "uncommon", "rare", "epic", "legendary" (case-insensitive).
- You can customize net costs and rarity weights with admin commands.

"""
from __future__ import annotations

import asyncio
import json
import math
import os
import random
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

import discord
from redbot.core import commands, Config
from redbot.core.data_manager import cog_data_path
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_number


DEFAULT_NETS = {
    # cost in Wellcoins; weights multiply base rarity odds (higher favors rarer mons)
    "normal": {"cost": 10.0, "rarity_boost": {"common": 1.0, "uncommon": 1.0, "rare": 0.8, "epic": 0.6, "legendary": 0.4}},
    "great": {"cost": 50.0, "rarity_boost": {"common": 0.9, "uncommon": 1.0, "rare": 1.1, "epic": 1.2, "legendary": 1.3}},
    "ultra": {"cost": 200.0, "rarity_boost": {"common": 0.7, "uncommon": 0.9, "rare": 1.3, "epic": 1.5, "legendary": 1.8}},
    "master": {"cost": 1000.0, "rarity_boost": {"common": 0.5, "uncommon": 0.7, "rare": 1.5, "epic": 2.0, "legendary": 3.0}},
}

# Baseline appearance weights by rarity; multiplied by net's rarity_boost
BASE_RARITY_POOL = {"common": 60, "uncommon": 25, "rare": 10, "epic": 4, "legendary": 1}

# XP and leveling
XP_PER_BATTLE_WIN = 120
XP_PER_BATTLE_LOSS = 60
XP_CURVE_A = 80  # base xp per level
XP_CURVE_B = 1.25  # growth
STAT_POINTS_PER_LEVEL = 3


@dataclass
class MonSpec:
    name: str
    type: str
    total: int
    hp: int
    attack: int
    defense: int
    sp_atk: int
    sp_def: int
    speed: int
    rarity: str  # common | uncommon | rare | epic | legendary

    @staticmethod
    def from_json(obj: dict) -> "MonSpec":
        # Accept a few possible keys (case/spacing variants)
        key = lambda *opts: next((obj[k] for k in opts if k in obj), None)
        rarity = str(key("rarity", "Rarity")).lower()
        return MonSpec(
            name=str(key("Name", "name")),
            type=str(key("Type", "type")),
            total=int(key("Total", "total")),
            hp=int(key("HP", "hp")),
            attack=int(key("Attack", "attack")),
            defense=int(key("Defense", "defense")),
            sp_atk=int(key("Sp. Atk", "SpAtk", "sp_atk", "sp.atk", "sp_atk")),
            sp_def=int(key("Sp. Def", "SpDef", "sp_def", "sp.def", "sp_def")),
            speed=int(key("Speed", "speed")),
            rarity=rarity,
        )


@dataclass
class OwnedMon:
    oid: str  # unique per owner
    species: str
    level: int
    xp: int
    stats: Dict[str, int]  # hp/attack/defense/sp_atk/sp_def/speed
    origin_net: str

    def power(self) -> int:
        base = self.stats["hp"] + self.stats["attack"] + self.stats["defense"] + self.stats["sp_atk"] + self.stats["sp_def"] + self.stats["speed"]
        # Mild level scaling
        return int(base * (1 + (self.level - 1) * 0.07))


class GachaCatchEmAll(commands.Cog):
    """Gacha-style monster collection using Wellcoins and NexusExchange."""

    __author__ = "chatgpt"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xBEEFCAFE1234, force_registration=True)
        self.config.register_global(
            nets=DEFAULT_NETS,
            base_rarity_pool=BASE_RARITY_POOL,
        )
        self.config.register_user(
            mons={},  # oid -> OwnedMon as dict
            team=[],  # list of oids (max 6)
            dex={},   # species name -> count caught
            pending_points=0,  # stat points awaiting allocation (spend via allocate)
        )
        self._specs: Dict[str, MonSpec] = {}
        self._load_lock = asyncio.Lock()

    # ---------- DATA PATHS ----------
    # Using Red's official data manager helper (cog_data_path). No private attrs used.

    async def red_delete_data_for_user(self, **kwargs):
        """GDPR compliance: wipe a user's data."""
        uid = kwargs.get("user_id")
        if uid is None:
            return
        await self.config.user_from_id(uid).clear()

    # ---------- SPEC LOADING ----------
    async def load_specs(self) -> None:
        """Load species from mons.json located in this cog's data folder."""
        async with self._load_lock:
            datapath = cog_data_path(self)
            datapath.mkdir(parents=True, exist_ok=True)
            file_path = datapath / "mons.json"
            if not file_path.exists():
                self._specs = {}
                return
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                self._specs = {}
                raise e

            specs: Dict[str, MonSpec] = {}
            for obj in raw:
                try:
                    spec = MonSpec.from_json(obj)
                    if spec.rarity not in BASE_RARITY_POOL:
                        # default to common if unknown
                        spec.rarity = "common"
                    specs[spec.name] = spec
                except Exception:
                    continue
            self._specs = specs

    # ---------- HELPER: NEXUS EXCHANGE ----------
    def _nexus(self):
        return self.bot.get_cog("NexusExchange")

    async def _charge(self, user: discord.abc.User, amount: float):
        ne = self._nexus()
        if ne is None:
            raise RuntimeError("NexusExchange cog not found. Install/Load it first.")
        # Raises ValueError if insufficient funds when force=False
        await ne.take_wellcoins(user, amount, force=False)

    # ---------- HELPER: XP / LEVELS ----------
    def _xp_needed(self, level: int) -> int:
        return int(XP_CURVE_A * (XP_CURVE_B ** (level - 1)))

    def _apply_level_ups(self, mon: OwnedMon) -> int:
        """Increase levels if XP exceeds thresholds. Returns number of levels gained; adds pending points to user's balance in calling context."""
        levels = 0
        while True:
            need = self._xp_needed(mon.level)
            if mon.xp >= need:
                mon.xp -= need
                mon.level += 1
                levels += 1
            else:
                break
        return levels

    # ---------- HELPER: STATS ----------
    def _base_stats_for(self, spec: MonSpec) -> Dict[str, int]:
        return {
            "hp": spec.hp,
            "attack": spec.attack,
            "defense": spec.defense,
            "sp_atk": spec.sp_atk,
            "sp_def": spec.sp_def,
            "speed": spec.speed,
        }

    # ---------- ADMIN COMMANDS ----------
    @commands.group(name="GachaCatchEmAll")
    @commands.admin_or_permissions(manage_guild=True)
    async def admin_group(self, ctx: commands.Context):
        """Admin controls for GachaCatchEmAll."""
        pass

    @admin_group.command(name="upload")
    @commands.admin_or_permissions(manage_guild=True)
    async def upload_mons(self, ctx: commands.Context):
        """
        Upload a new mons.json file directly from Discord.
        Attach mons.json to this command.
        """
        if not ctx.message.attachments:
            return await ctx.send("❌ Please attach a `mons.json` file to upload.")
    
        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith(".json"):
            return await ctx.send("❌ File must be a `.json` file.")
    
        try:
            data = await attachment.read()
            # Validate json before saving
            json_data = json.loads(data.decode("utf-8"))
        except Exception as e:
            return await ctx.send(f"❌ Failed to read JSON: `{e}`")
    
        # Save file
        save_path = cog_data_path(self) / "mons.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)
    
        await ctx.send(f"✅ Successfully uploaded `{attachment.filename}` to `{save_path}`.\n"
                       f"Run `nexusmon loadmons` to reload species into memory.")

    @admin_group.command(name="loadmons")
    async def loadmons(self, ctx: commands.Context):
        """Reload species from data folder's mons.json.

        Path: {data_path}/mons.json  (use `[p]GachaCatchEmAll whereis` to see your exact path)
        """
        await self.load_specs()
        if not self._specs:
            await ctx.send("No mons loaded. Ensure mons.json exists and is valid.")
            return
        await ctx.send(f"Loaded {len(self._specs)} species.")

    @admin_group.command(name="setnetcost")
    async def set_net_cost(self, ctx: commands.Context, net: str, cost: float):
        """Set the Wellcoin cost for a net (normal/great/ultra/master)."""
        net = net.lower()
        nets = await self.config.nets()
        if net not in nets:
            await ctx.send("Unknown net. Choose: normal, great, ultra, master")
            return
        nets[net]["cost"] = max(0.0, float(cost))
        await self.config.nets.set(nets)
        await ctx.send(f"{net.title()} Net now costs {cost} WC.")

    @admin_group.command(name="setrarityweight")
    async def set_rarity_weight(self, ctx: commands.Context, rarity: str, weight: int):
        """Set base appearance weight for a rarity (affects catch odds)."""
        rarity = rarity.lower()
        brp = await self.config.base_rarity_pool()
        if rarity not in brp:
            await ctx.send("Unknown rarity. Use: common, uncommon, rare, epic, legendary")
            return
        brp[rarity] = max(0, int(weight))
        await self.config.base_rarity_pool.set(brp)
        await ctx.send(f"Base weight for {rarity} set to {weight}.")

    @admin_group.command(name="whereis")
    async def whereis(self, ctx: commands.Context):
        """Show the exact folder path for mons.json."""
        path = cog_data_path(self)
        await ctx.send(f"Place your file at: `{path / 'mons.json'}`")

    # ---------- PUBLIC COMMANDS ----------
    @commands.hybrid_group(name="mon")
    async def mon_group(self, ctx: commands.Context):
        """Collect, manage, and battle your GachaCatchEmAll!"""
        pass

    # CATCH
    @mon_group.command(name="catch")
    async def catch(self, ctx: commands.Context, net: str):
        """Spend Wellcoins to catch a random mon.

        Nets: normal, great, ultra, master
        """
        await self._ensure_specs(ctx)
        net = net.lower()
        nets = await self.config.nets()
        if net not in nets:
            await ctx.send("Unknown net. Choose: normal, great, ultra, master")
            return
        cost = float(nets[net]["cost"])
        try:
            await self._charge(ctx.author, cost)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return
        except RuntimeError as e:
            await ctx.send(f"❌ {e}")
            return

        species = self._roll_species(net, nets)
        spec = self._specs[species]
        mon = OwnedMon(
            oid=str(uuid.uuid4())[:8],
            species=spec.name,
            level=1,
            xp=0,
            stats=self._base_stats_for(spec),
            origin_net=net,
        )
        uconf = self.config.user(ctx.author)
        data = await uconf.all()
        mons: Dict[str, dict] = data.get("mons", {})
        mons[mon.oid] = asdict(mon)
        # Update dex
        dex: Dict[str, int] = data.get("dex", {})
        dex[spec.name] = dex.get(spec.name, 0) + 1
        # Autofill team if space
        team: List[str] = data.get("team", [])
        if len(team) < 6:
            team.append(mon.oid)
        await uconf.mons.set(mons)
        await uconf.dex.set(dex)
        await uconf.team.set(team)

        await ctx.send(
            f"🕸️ You cast a **{net.title()} Net** and caught **{spec.name}** (Lv.1)!\n"
            f"Type: {spec.type} | Rarity: {spec.rarity.title()} | OID: `{mon.oid}`"
        )

    def _roll_species(self, net_name: str, nets: dict) -> str:
        # Build a rarity weighted pool first
        brp = BASE_RARITY_POOL.copy()
        brp.update(nets.get("base_rarity_pool", {}))  # just in case
        # Use config global value for base rarity pool
        # (pull sync since this is a helper called within catch; we cached defaults)
        # We'll rely on class constant here; admin cmd updates config for future runtime

        # Count species by rarity and build weighted list per rarity, then overall
        rar_to_species: Dict[str, List[str]] = {r: [] for r in BASE_RARITY_POOL}
        for spec in self._specs.values():
            rar_to_species.setdefault(spec.rarity, []).append(spec.name)

        # Rarity selection weights boosted by net settings
        net_boost = nets[net_name]["rarity_boost"]
        rarities = []
        weights = []
        for r, base_w in BASE_RARITY_POOL.items():
            boost = net_boost.get(r, 1.0)
            rarities.append(r)
            weights.append(base_w * boost)
        chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]
        pool = rar_to_species.get(chosen_rarity) or [s.name for s in self._specs.values()]
        return random.choice(pool)

    async def _ensure_specs(self, ctx: commands.Context):
        if not self._specs:
            await self.load_specs()
            if not self._specs:
                raise commands.UserFeedbackCheckFailure("No mons loaded. Ask an admin to run `[p]GachaCatchEmAll loadmons`.")

    # LIST OWNED
    @mon_group.command(name="mons")
    async def list_mons(self, ctx: commands.Context):
        """List your owned mons."""
        data = await self.config.user(ctx.author).all()
        mons: Dict[str, dict] = data.get("mons", {})
        if not mons:
            await ctx.send("You don't own any mons yet. Try `mon catch normal`. 🪤")
            return
        lines = []
        for oid, m in mons.items():
            lines.append(f"`{oid}` — {m['species']} Lv.{m['level']} (PWR {OwnedMon(**m).power()})")
        await ctx.send(box("\n".join(lines), "ini"))

    # INFO
    @mon_group.command(name="info")
    async def mon_info(self, ctx: commands.Context, oid: str):
        """View detailed info for a mon by OID."""
        u = self.config.user(ctx.author)
        mons = await u.mons()
        m = mons.get(oid)
        if not m:
            await ctx.send("No mon with that OID.")
            return
        mon = OwnedMon(**m)
        embed = discord.Embed(title=f"{mon.species} — OID {mon.oid}")
        embed.add_field(name="Level", value=str(mon.level))
        embed.add_field(name="XP", value=str(mon.xp))
        embed.add_field(name="Origin", value=mon.origin_net.title())
        stats = mon.stats
        s = "\n".join([
            f"HP {stats['hp']}",
            f"Atk {stats['attack']} | Def {stats['defense']}",
            f"SpA {stats['sp_atk']} | SpD {stats['sp_def']}",
            f"Spe {stats['speed']}",
            f"Power {mon.power()}"
        ])
        embed.add_field(name="Stats", value=box(s, "ini"), inline=False)
        await ctx.send(embed=embed)

    # TEAM MANAGEMENT
    @mon_group.group(name="team")
    async def team_group(self, ctx: commands.Context):
        """Manage your active team (max 6)."""
        pass

    @team_group.command(name="view")
    async def team_view(self, ctx: commands.Context):
        u = self.config.user(ctx.author)
        data = await u.all()
        team: List[str] = data.get("team", [])
        mons: Dict[str, dict] = data.get("mons", {})
        if not team:
            await ctx.send("No active team. Add with `mon team add <oid>`.")
            return
        lines = []
        for oid in team:
            m = mons.get(oid)
            if not m:
                continue
            mon = OwnedMon(**m)
            lines.append(f"`{oid}` — {mon.species} Lv.{mon.level} (PWR {mon.power()})")
        await ctx.send(box("\n".join(lines), "ini"))

    @team_group.command(name="add")
    async def team_add(self, ctx: commands.Context, oid: str):
        u = self.config.user(ctx.author)
        data = await u.all()
        team: List[str] = data.get("team", [])
        mons: Dict[str, dict] = data.get("mons", {})
        if oid not in mons:
            await ctx.send("You don't own that OID.")
            return
        if oid in team:
            await ctx.send("That mon is already in your team.")
            return
        if len(team) >= 6:
            await ctx.send("Team is full (max 6). Remove one first.")
            return
        team.append(oid)
        await u.team.set(team)
        await ctx.send("Added to team.")

    @team_group.command(name="remove")
    async def team_remove(self, ctx: commands.Context, oid: str):
        u = self.config.user(ctx.author)
        team = await u.team()
        if oid not in team:
            await ctx.send("That OID isn't on your team.")
            return
        team.remove(oid)
        await u.team.set(team)
        await ctx.send("Removed from team.")

    # DEX / COLLECTION
    @mon_group.command(name="dex")
    async def dex(self, ctx: commands.Context):
        await self._ensure_specs(ctx)
        u = self.config.user(ctx.author)
        dex: Dict[str, int] = await u.dex()
        caught = len([s for s in self._specs if dex.get(s)])
        total = len(self._specs)
        pct = (caught / total * 100) if total else 0
        await ctx.send(f"📘 Dex: {caught}/{total} species ({pct:.1f}%).")

    # ALLOCATE STAT POINTS
    @mon_group.command(name="allocate")
    async def allocate(self, ctx: commands.Context, oid: str, stat: str, points: int = 1):
        """Allocate pending stat points to one of: hp, attack, defense, sp_atk, sp_def, speed."""
        stat = stat.lower()
        if stat not in {"hp", "attack", "defense", "sp_atk", "sp_def", "speed"}:
            await ctx.send("Invalid stat.")
            return
        u = self.config.user(ctx.author)
        data = await u.all()
        mons: Dict[str, dict] = data.get("mons", {})
        m = mons.get(oid)
        if not m:
            await ctx.send("No mon with that OID.")
            return
        pending = int(data.get("pending_points", 0))
        if pending <= 0:
            await ctx.send("You have no pending stat points. Battle to level up!")
            return
        to_spend = min(points, pending)
        m.setdefault("stats", {})
        m["stats"][stat] = int(m["stats"].get(stat, 0)) + to_spend
        pending -= to_spend
        mons[oid] = m
        await u.mons.set(mons)
        await u.pending_points.set(pending)
        await ctx.send(f"Allocated {to_spend} point(s) to {stat}. Remaining points: {pending}.")

    # COMBINE DUPLICATES
    @mon_group.command(name="combine")
    async def combine(self, ctx: commands.Context, target_oid: str, source_oid: str):
        """Combine two mons of the same species. Source is consumed.

        - XP is summed.
        - Stats are averaged (rounded), then +1 to the highest stat.
        """
        u = self.config.user(ctx.author)
        data = await u.all()
        mons: Dict[str, dict] = data.get("mons", {})
        t = mons.get(target_oid)
        s = mons.get(source_oid)
        if not t or not s:
            await ctx.send("Invalid OIDs.")
            return
        if t["species"] != s["species"]:
            await ctx.send("Species must match to combine.")
            return
        # Merge xp and stats
        t["xp"] = int(t.get("xp", 0)) + int(s.get("xp", 0))
        for key in ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]:
            avg = round((t["stats"][key] + s["stats"][key]) / 2)
            t["stats"][key] = avg
        # small bonus to highest stat
        highest = max(t["stats"], key=lambda k: t["stats"][k])
        t["stats"][highest] += 1
        # Delete source
        mons.pop(source_oid, None)
        # Remove from team if present
        team: List[str] = data.get("team", [])
        if source_oid in team:
            team.remove(source_oid)
        # Apply potential level ups and pending points
        mon = OwnedMon(**t)
        levels = self._apply_level_ups(mon)
        t = asdict(mon)
        mons[target_oid] = t
        await u.mons.set(mons)
        await u.team.set(team)
        if levels:
            await u.pending_points.set(int(data.get("pending_points", 0)) + levels * STAT_POINTS_PER_LEVEL)
        await ctx.send(f"Combined! {levels} level(s) gained; +{levels * STAT_POINTS_PER_LEVEL} pending points.")
        
    @mon_group.command(name="battle2")
    async def battle2(self, ctx: commands.Context):
        """(Stable) Battle an NPC team of 6 with level/XP and pending-points accounting."""
        await self._ensure_specs(ctx)
        u = self.config.user(ctx.author)
        data = await u.all()
        team_ids: List[str] = data.get("team", [])
        mons: Dict[str, dict] = data.get("mons", {})
        if not team_ids:
            await ctx.send("You need an active team. Use `mon team add <oid>`." )
            return
        team = [OwnedMon(**mons[i]) for i in team_ids if i in mons]
        if not team:
            await ctx.send("Your team data seems empty. Add mons again.")
            return
        avg_lvl = max(1, round(sum(m.level for m in team) / len(team)))
        npc_team: List[OwnedMon] = []
        for _ in range(6):
            spec = random.choice(list(self._specs.values()))
            base_stats = self._base_stats_for(spec)
            for k in base_stats:
                base_stats[k] = max(1, int(base_stats[k] * random.uniform(0.9, 1.1)))
            npc_team.append(OwnedMon(oid="NPC", species=spec.name, level=max(1, int(avg_lvl + random.choice([-1,0,0,1]))), xp=0, stats=base_stats, origin_net="npc"))

        your_power = sum(m.power() for m in team)
        npc_power = sum(m.power() for m in npc_team)
        your_roll = int(your_power * random.uniform(0.9, 1.1))
        npc_roll = int(npc_power * random.uniform(0.9, 1.1))
        win = your_roll >= npc_roll

        # Distribute XP with reliable point tracking
        pending_add = 0
        lines = [f"Your roll: {your_roll} vs NPC: {npc_roll}"]
        for m in team:
            xp_gain = XP_PER_BATTLE_WIN if win else XP_PER_BATTLE_LOSS
            m.xp += xp_gain
            before = m.level
            levels = self._apply_level_ups(m)
            mons[m.oid] = asdict(m)
            pending_add += levels * STAT_POINTS_PER_LEVEL
            if levels:
                lines.append(f"{m.species} +{xp_gain} XP, +{levels} level(s)!")
            else:
                lines.append(f"{m.species} +{xp_gain} XP.")
        await u.mons.set(mons)
        if pending_add:
            await u.pending_points.set(int(data.get("pending_points", 0)) + pending_add)
        result = "🏆 Victory!" if win else "⚔️ Defeat (good effort)"
        lines.insert(0, result)
        await ctx.send("\n".join(lines))

    # ECONOMY HELPERS
    @mon_group.command(name="balance")
    async def balance(self, ctx: commands.Context):
        ne = self._nexus()
        if not ne:
            await ctx.send("NexusExchange cog not enabled.")
            return
        bal = await ne.get_balance(ctx.author)
        await ctx.send(f"You have {bal} Wellcoins.")
    


async def setup(bot: Red):
    cog = GachaCatchEmAll(bot)
    await bot.add_cog(cog)
