# File: fishing/fishing.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Protocol

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

__all__ = ["Fishing"]

# ---------- Data Models ----------
@dataclass(frozen=True)
class Rod:
    key: str
    name: str
    power: int            # affects chance for higher rarity
    durability: int       # max durability
    price: float

@dataclass(frozen=True)
class Bait:
    key: str
    name: str
    rarity_boost: float   # additive/multiplicative boost to non-common rarities
    price: float

@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    unlock_price: float
    sell_multiplier: float  # improves sell price of fish
    base_table: Dict[str, float]  # rarity -> weight override/boost

@dataclass(frozen=True)
class Catch:
    rarity: str
    species: str


# ---------- Static Data ----------
RARITY_PRICES: Dict[str, float] = {
    "common": 1.00,
    "uncommon": 2.50,
    "rare": 6.00,
    "epic": 15.00,
    "legendary": 40.00,
}

BASE_RARITY_TABLE: Dict[str, float] = {
    "common": 70.0,
    "uncommon": 22.0,
    "rare": 6.0,
    "epic": 1.8,
    "legendary": 0.2,
}

RODS: Dict[str, Rod] = {
    "twig":   Rod("twig",   "Twig Rod",        power=0, durability=30,  price=0.0),
    "oak":    Rod("oak",    "Oak Rod",         power=1, durability=60,  price=25.0),
    "steel":  Rod("steel",  "Steel Rod",       power=2, durability=120, price=120.0),
    "myth":   Rod("myth",   "Mythril Rod",     power=4, durability=240, price=500.0),
}

BAITS: Dict[str, Bait] = {
    "worm":    Bait("worm",    "Worm Bait",     rarity_boost=0.01,  price=1.0),
    "minnow":  Bait("minnow",  "Minnow Bait",   rarity_boost=0.02,  price=2.5),
    "shrimp":  Bait("shrimp",  "Shrimp Bait",   rarity_boost=0.035, price=5.0),
    "goldfly": Bait("goldfly", "Goldfly Bait",  rarity_boost=0.06,  price=10.0),
}

ZONES: Dict[str, Zone] = {
    "pond": Zone(
        "pond", "Quiet Pond", unlock_price=0.0, sell_multiplier=1.0,
        base_table={"common": +5.0}
    ),
    "river": Zone(
        "river", "Swift River", unlock_price=50.0, sell_multiplier=1.1,
        base_table={"uncommon": +3.0, "rare": +1.0}
    ),
    "coast": Zone(
        "coast", "Rocky Coast", unlock_price=200.0, sell_multiplier=1.25,
        base_table={"rare": +2.0, "epic": +0.5}
    ),
    "abyss": Zone(
        "abyss", "Midnight Abyss", unlock_price=1000.0, sell_multiplier=1.5,
        base_table={"epic": +0.8, "legendary": +0.2}
    ),
}

# Zone-specific species names per rarity (flavor-only; does not affect pricing)
SPECIES: Dict[str, Dict[str, List[str]]] = {
    "pond": {
        "common":    ["Bluegill", "Muddy Carp", "Lilypad Perch"],
        "uncommon":  ["Speckled Sunfish", "Dusk Minnow"],
        "rare":      ["Moonlit Koi"],
        "epic":      ["Verdant Arowana"],
        "legendary": ["Pond Guardian"],
    },
    "river": {
        "common":    ["River Perch", "Stone Shiner"],
        "uncommon":  ["Silver Chub", "Swift Darter"],
        "rare":      ["Bronze Trout"],
        "epic":      ["Runebrook Salmon"],
        "legendary": ["King of Currents"],
    },
    "coast": {
        "common":    ["Tide Sardine", "Pebble Mackerel"],
        "uncommon":  ["Sea Bream", "Glimmer Hake"],
        "rare":      ["Opal Snapper"],
        "epic":      ["Storm Marlin"],
        "legendary": ["Leviathan Fry"],
    },
    "abyss": {
        "common":    ["Gloom Smelt"],
        "uncommon":  ["Twilight Cod"],
        "rare":      ["Nightfang Eel"],
        "epic":      ["Phantom Angler"],
        "legendary": ["Abyssal Sovereign"],
    },
}


# ---------- Loot Table Logic ----------
def _weighted_choice(table: Dict[str, float]) -> str:
    items = list(table.items())
    total = sum(w for _, w in items)
    pick = random.random() * total if total > 0 else 0.0
    upto = 0.0
    for rarity, w in items:
        if upto + w >= pick:
            return rarity
        upto += w
    return items[-1][0] if items else "common"


def _compose_table(*, rod: Rod, bait: Optional[Bait], zone: Zone) -> Dict[str, float]:
    # Start with base table
    table = dict(BASE_RARITY_TABLE)

    # Zone tweaks (additive to weights)
    for r, delta in zone.base_table.items():
        table[r] = max(0.0, table.get(r, 0.0) + delta)

    # Rod power shifts weight upward in small percentages
    for _ in range(rod.power):
        for (src, dst, frac) in [
            ("common", "uncommon", 0.02),
            ("uncommon", "rare", 0.01),
            ("rare", "epic", 0.005),
        ]:
            amt = table[src] * frac
            table[src] -= amt
            table[dst] += amt

    # Bait slightly boosts non-common rarities, then renormalize to original magnitude
    if bait:
        boost = bait.rarity_boost
        for r in ("uncommon", "rare", "epic", "legendary"):
            table[r] *= (1.0 + boost)
        scale = sum(BASE_RARITY_TABLE.values()) / max(sum(table.values()), 1e-9)
        for k in table:
            table[k] *= scale

    # No negatives
    for k in list(table.keys()):
        table[k] = max(0.0, table[k])
    return table


def roll_catch(*, rod: Rod, bait: Optional[Bait], zone: Zone) -> Catch:
    table = _compose_table(rod=rod, bait=bait, zone=zone)
    rarity = _weighted_choice(table)
    species_pool = SPECIES.get(zone.key, {}).get(rarity, [rarity.title()])
    species = random.choice(species_pool)
    return Catch(rarity=rarity, species=species)


# ---------- Economy Protocol ----------
class Economy(Protocol):
    async def get_balance(self, user): ...
    async def add_wellcoins(self, user, amount: float): ...
    async def take_wellcoins(self, user, amount: float, force: bool = False): ...


def _get_economy(bot: Red) -> Economy:
    econ = bot.get_cog("NexusExchange")
    if not econ:
        raise RuntimeError("NexusExchange cog not found. Please load it so Fishing can use Wellcoins.")
    for fn in ("get_balance", "add_wellcoins", "take_wellcoins"):
        if not hasattr(econ, fn):
            raise RuntimeError(f"NexusExchange is missing required method `{fn}`.")
    return econ  # type: ignore[return-value]


# ---------- Embeds ----------
RARITY_COLOR = {
    "common": discord.Colour.light_grey(),
    "uncommon": discord.Colour.green(),
    "rare": discord.Colour.blue(),
    "epic": discord.Colour.purple(),
    "legendary": discord.Colour.gold(),
}

def _catch_embed(*, zone: Zone, rod: Rod, bait: Bait | None, catch: Catch, durability_now: int) -> discord.Embed:
    e = discord.Embed(
        title=f"You fished in {zone.name}!",
        description=f"**{catch.species}** (*{catch.rarity.title()}*)",
        colour=RARITY_COLOR.get(catch.rarity, discord.Colour.blurple()),
    )
    e.add_field(name="Rod", value=f"{rod.name} ({durability_now}/{rod.durability})", inline=True)
    e.add_field(name="Zone", value=zone.name, inline=True)
    e.add_field(name="Bait", value=bait.name if bait else "None", inline=True)
    return e

def _inventory_embed(*, rod: Rod, zone: Zone, inv: Dict[str, int], bait_inv: Dict[str, int], dur: int) -> discord.Embed:
    e = discord.Embed(
        title="Tackle Box",
        description=f"Rod: **{rod.name}** ({dur}/{rod.durability})\nZone: **{zone.name}**",
        colour=discord.Colour.teal(),
    )
    fish_lines = "\n".join(f"{r.title()}: **{inv.get(r,0)}**" for r in RARITY_PRICES)
    bait_lines = "\n".join(f"{k.title()}: **{v}**" for k, v in bait_inv.items()) or "None"
    e.add_field(name="Fish", value=fish_lines, inline=False)
    e.add_field(name="Bait", value=bait_lines, inline=False)
    return e

def _prices_embed(*, zone: Zone) -> discord.Embed:
    e = discord.Embed(title=f"Prices • {zone.name}", colour=discord.Colour.orange())
    for r, p in RARITY_PRICES.items():
        e.add_field(name=r.title(), value=f"{p:.2f} → {(p*zone.sell_multiplier):.2f} WC", inline=True)
    e.set_footer(text=f"Zone Multiplier ×{zone.sell_multiplier:.2f}")
    return e

def _sell_embed(*, zone: Zone, sold: List[Tuple[str, int, float]], total: float) -> discord.Embed:
    e = discord.Embed(title=f"Sold at {zone.name}", colour=discord.Colour.dark_gold())
    for rarity, qty, amt in sold:
        e.add_field(name=rarity.title(), value=f"× {qty} → {amt:.2f} WC", inline=False)
    e.add_field(name="Total", value=f"**{total:.2f} WC**", inline=False)
    e.set_footer(text=f"Zone Multiplier ×{zone.sell_multiplier:.2f}")
    return e


# ---------- The Cog ----------
class Fishing(commands.Cog):
    """Catch fish, buy rods/bait/zones, and sell for Wellcoins (single-file embed edition)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=324234324234, force_registration=True)

        default_user = {
            "rod": "twig",
            "rod_durability": RODS["twig"].durability,
            "bait": {k: 0 for k in BAITS.keys()},
            "zone": "pond",
            "unlocked_zones": ["pond"],
            "inventory": {r: 0 for r in RARITY_PRICES.keys()},
        }
        self.config.register_user(**default_user)
        self._locks: Dict[int, asyncio.Lock] = {}

    # ---------- Helpers ----------
    def _lock_for(self, user_id: int) -> asyncio.Lock:
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
        return lock

    # ---------- Commands ----------
    @commands.hybrid_group(name="fish", invoke_without_command=True)
    @commands.cooldown(1, 30.0, commands.BucketType.user)
    async def fish_cmd(self, ctx: commands.Context):
        """Go fishing! Cooldown: 30s."""
        async with self._lock_for(ctx.author.id):
            user = self.config.user(ctx.author)
            data = await user.all()

            # Validate rod
            rod: Rod = RODS.get(data["rod"], RODS["twig"])
            if data["rod_durability"] <= 0:
                return await ctx.reply(
                    embed=discord.Embed(
                        description=f"⛔ Your **{rod.name}** is broken. Repair or buy a new rod.",
                        colour=discord.Colour.red(),
                    )
                )

            # Auto-consume best bait if available
            bait: Optional[Bait] = None
            if any(qty > 0 for qty in data["bait"].values()):
                owned = [(BAITS[k], q) for k, q in data["bait"].items() if q > 0 and k in BAITS]
                owned.sort(key=lambda t: BAITS[t[0].key].rarity_boost, reverse=True)
                bait = owned[0][0]
                data["bait"][bait.key] -= 1

            zone: Zone = ZONES.get(data["zone"], ZONES["pond"])

            catch: Catch = roll_catch(rod=rod, bait=bait, zone=zone)

            # Update inv & durability
            data["inventory"][catch.rarity] = int(data["inventory"].get(catch.rarity, 0)) + 1
            data["rod_durability"] = max(0, int(data["rod_durability"]) - 1)
            await user.set(data)

            emb = _catch_embed(zone=zone, rod=rod, bait=bait, catch=catch, durability_now=data["rod_durability"])
            await ctx.reply(embed=emb)

    @fish_cmd.command(name="inventory")
    async def fish_inventory(self, ctx: commands.Context):
        data = await self.config.user(ctx.author).all()
        rod = RODS.get(data["rod"], RODS["twig"])
        zone = ZONES.get(data["zone"], ZONES["pond"])
        inv = dict(data["inventory"])
        bait_inv = data["bait"]
        await ctx.reply(embed=_inventory_embed(rod=rod, zone=zone, inv=inv, bait_inv=bait_inv, dur=data["rod_durability"]))

    @fish_cmd.command(name="sell")
    async def fish_sell(self, ctx: commands.Context, rarity: Optional[str] = None, amount: Optional[int] = None):
        econ = _get_economy(self.bot)
        async with self._lock_for(ctx.author.id):
            data = await self.config.user(ctx.author).all()
            zone = ZONES.get(data["zone"], ZONES["pond"])
            inv = data["inventory"]

            def price_for(r: str, qty: int) -> float:
                return RARITY_PRICES.get(r, 0.0) * zone.sell_multiplier * qty

            total = 0.0
            sold_detail: List[Tuple[str, int, float]] = []

            if rarity is None:
                for r, qty in list(inv.items()):
                    qty = int(qty)
                    if qty <= 0:
                        continue
                    p = price_for(r, qty)
                    total += p
                    sold_detail.append((r, qty, p))
                    inv[r] = 0
            else:
                r = rarity.lower()
                if r not in inv:
                    return await ctx.reply(embed=discord.Embed(description="Unknown rarity. Use common/uncommon/rare/epic/legendary.", colour=discord.Colour.red()))
                have = int(inv[r])
                if have <= 0:
                    return await ctx.reply(embed=discord.Embed(description=f"You have no **{r}** fish to sell.", colour=discord.Colour.red()))
                qty = have if amount is None else max(0, min(have, int(amount)))
                if qty == 0:
                    return await ctx.reply(embed=discord.Embed(description="Nothing to sell.", colour=discord.Colour.red()))
                p = price_for(r, qty)
                total += p
                sold_detail.append((r, qty, p))
                inv[r] = have - qty

            data["inventory"] = inv
            await self.config.user(ctx.author).set(data)

            if total > 0:
                await econ.add_wellcoins(ctx.author, float(total))
            if total <= 0:
                return await ctx.reply(embed=discord.Embed(description="No fish sold.", colour=discord.Colour.red()))

            await ctx.reply(embed=_sell_embed(zone=zone, sold=sold_detail, total=total))

    # ---------- Shop & Loadout ----------
    @fish_cmd.group(name="shop", invoke_without_command=True)
    async def fish_shop(self, ctx: commands.Context):
        e = discord.Embed(title="Shop", description="Choose a category", colour=discord.Colour.blurple())
        e.add_field(name="Rods", value="`[p]fish shop rods`", inline=True)
        e.add_field(name="Bait", value="`[p]fish shop bait`", inline=True)
        e.add_field(name="Zones", value="`[p]fish shop zones`", inline=True)
        await ctx.reply(embed=e)

    @fish_shop.command(name="rods")
    async def shop_rods(self, ctx: commands.Context):
        e = discord.Embed(title="Shop • Rods", colour=discord.Colour.blue())
        for r in RODS.values():
            e.add_field(name=f"{r.name} (`{r.key}`)", value=f"{r.price:.2f} WC • Power {r.power} • Durability {r.durability}", inline=False)
        await ctx.reply(embed=e)

    @fish_shop.command(name="bait")
    async def shop_bait(self, ctx: commands.Context):
        e = discord.Embed(title="Shop • Bait", colour=discord.Colour.green())
        for b in BAITS.values():
            e.add_field(name=f"{b.name} (`{b.key}`)", value=f"{b.price:.2f} WC • Rarity boost {b.rarity_boost:.3f}", inline=False)
        await ctx.reply(embed=e)

    @fish_shop.command(name="zones")
    async def shop_zones(self, ctx: commands.Context):
        e = discord.Embed(title="Shop • Zones", colour=discord.Colour.dark_teal())
        for z in ZONES.values():
            e.add_field(name=f"{z.name} (`{z.key}`)", value=f"Unlock {z.unlock_price:.2f} WC • Sell ×{z.sell_multiplier:.2f}", inline=False)
        await ctx.reply(embed=e)

    @fish_cmd.group(name="buy")
    async def fish_buy(self, ctx: commands.Context):
        """Buy rods, bait, or zones."""
        pass

    @fish_buy.command(name="rod")
    async def buy_rod(self, ctx: commands.Context, rod_key: str):
        econ = _get_economy(self.bot)
        rod_key = rod_key.lower()
        if rod_key not in RODS:
            return await ctx.reply(embed=discord.Embed(description="Unknown rod.", colour=discord.Colour.red()))
        rod = RODS[rod_key]
        async with self._lock_for(ctx.author.id):
            data = await self.config.user(ctx.author).all()
            if rod.price > 0:
                try:
                    await econ.take_wellcoins(ctx.author, rod.price, force=False)
                except ValueError:
                    return await ctx.reply(embed=discord.Embed(description=f"Insufficient funds. Need {rod.price:.2f} WC.", colour=discord.Colour.red()))
            data["rod"] = rod.key
            data["rod_durability"] = rod.durability
            await self.config.user(ctx.author).set(data)
        e = discord.Embed(description=f"🪝 You bought and equipped **{rod.name}** (Durability {rod.durability}).", colour=discord.Colour.blue())
        await ctx.reply(embed=e)

    @fish_buy.command(name="bait")
    async def buy_bait(self, ctx: commands.Context, bait_key: str, amount: int = 1):
        econ = _get_economy(self.bot)
        bait_key = bait_key.lower()
        if bait_key not in BAITS:
            return await ctx.reply(embed=discord.Embed(description="Unknown bait.", colour=discord.Colour.red()))
        if amount <= 0:
            return await ctx.reply(embed=discord.Embed(description="Amount must be positive.", colour=discord.Colour.red()))
        bait = BAITS[bait_key]
        cost = bait.price * amount
        try:
            await econ.take_wellcoins(ctx.author, cost, force=False)
        except ValueError:
            return await ctx.reply(embed=discord.Embed(description=f"Insufficient funds. Need {cost:.2f} WC.", colour=discord.Colour.red()))
        async with self._lock_for(ctx.author.id):
            have = await self.config.user(ctx.author).bait()
            have[bait_key] = int(have.get(bait_key, 0)) + amount
            await self.config.user(ctx.author).bait.set(have)
        await ctx.reply(embed=discord.Embed(description=f"🪱 Purchased **{amount}× {bait.name}** for {cost:.2f} WC.", colour=discord.Colour.green()))

    @fish_buy.command(name="zone")
    async def buy_zone(self, ctx: commands.Context, zone_key: str):
        econ = _get_economy(self.bot)
        zone_key = zone_key.lower()
        if zone_key not in ZONES:
            return await ctx.reply(embed=discord.Embed(description="Unknown zone.", colour=discord.Colour.red()))
        zone = ZONES[zone_key]
        async with self._lock_for(ctx.author.id):
            data = await self.config.user(ctx.author).all()
            if zone_key in set(data["unlocked_zones"]):
                return await ctx.reply(embed=discord.Embed(description="You already unlocked this zone.", colour=discord.Colour.orange()))
            price = zone.unlock_price
            if price > 0:
                try:
                    await econ.take_wellcoins(ctx.author, price, force=False)
                except ValueError:
                    return await ctx.reply(embed=discord.Embed(description=f"Insufficient funds. Need {price:.2f} WC.", colour=discord.Colour.red()))
            data["unlocked_zones"].append(zone_key)
            await self.config.user(ctx.author).set(data)
        await ctx.reply(embed=discord.Embed(description=f"🗺️ Unlocked **{zone.name}** for {zone.unlock_price:.2f} WC!", colour=discord.Colour.dark_teal()))

    @fish_cmd.command(name="zone")
    async def fish_zone(self, ctx: commands.Context, zone_key: Optional[str] = None):
        if zone_key is None:
            data = await self.config.user(ctx.author).all()
            unlocked = data["unlocked_zones"]
            current = data["zone"]
            names = ", ".join(ZONES[z].name for z in unlocked if z in ZONES)
            e = discord.Embed(title="Zones", description=f"Current: **{ZONES[current].name}**\nUnlocked: {names or 'None'}")
            return await ctx.reply(embed=e)
        zone_key = zone_key.lower()
        if zone_key not in ZONES:
            return await ctx.reply(embed=discord.Embed(description="Unknown zone.", colour=discord.Colour.red()))
        data = await self.config.user(ctx.author).all()
        if zone_key not in data["unlocked_zones"]:
            return await ctx.reply(embed=discord.Embed(description="You haven't unlocked that zone yet.", colour=discord.Colour.red()))
        await self.config.user(ctx.author).zone.set(zone_key)
        await ctx.reply(embed=discord.Embed(description=f"✅ Active zone set to **{ZONES[zone_key].name}**.", colour=discord.Colour.green()))

    @fish_cmd.command(name="repair")
    async def fish_repair(self, ctx: commands.Context):
        econ = _get_economy(self.bot)
        data = await self.config.user(ctx.author).all()
        rod = RODS.get(data["rod"], RODS["twig"])
        price = rod.price
        if price > 0:
            try:
                await econ.take_wellcoins(ctx.author, price, force=False)
            except ValueError:
                return await ctx.reply(embed=discord.Embed(description=f"Insufficient funds. Need {price:.2f} WC.", colour=discord.Colour.red()))
        await self.config.user(ctx.author).rod_durability.set(rod.durability)
        await ctx.reply(embed=discord.Embed(description=f"🔧 Repaired **{rod.name}** to full durability ({rod.durability}).", colour=discord.Colour.blue()))

    @fish_cmd.command(name="prices")
    async def fish_prices(self, ctx: commands.Context):
        data = await self.config.user(ctx.author).all()
        zone = ZONES.get(data["zone"], ZONES["pond"])
        await ctx.reply(embed=_prices_embed(zone=zone))


async def setup(bot: Red):
    await bot.add_cog(Fishing(bot))
