# fishing/fishing.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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
    rarity_boost: float   # additive boost to rarity roll (0..1 small)
    price: float

@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    unlock_price: float
    sell_multiplier: float  # improves sell price of fish
    base_table: Dict[str, float]  # rarity -> weight override/boost

# Rarity sell base prices (before zone multiplier)
RARITY_PRICES = {
    "common": 1.00,
    "uncommon": 2.50,
    "rare": 6.00,
    "epic": 15.00,
    "legendary": 40.00,
}

# Default rarity table weights; modified by rod/zone/bait
BASE_RARITY_TABLE = {
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
    "worm":    Bait("worm",    "Worm Bait",     rarity_boost=0.01, price=1.0),
    "minnow":  Bait("minnow",  "Minnow Bait",   rarity_boost=0.02, price=2.5),
    "shrimp":  Bait("shrimp",  "Shrimp Bait",   rarity_boost=0.035, price=5.0),
    "goldfly": Bait("goldfly", "Goldfly Bait",  rarity_boost=0.06, price=10.0),
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

# ---------- Cog ----------

class Fishing(commands.Cog):
    """Catch fish, buy rods/bait/zones, and sell for Wellcoins."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="324234324234", force_registration=True)

        default_user = {
            "rod": "twig",
            "rod_durability": RODS["twig"].durability,
            "bait": {"worm": 0, "minnow": 0, "shrimp": 0, "goldfly": 0},
            "zone": "pond",
            "unlocked_zones": ["pond"],
            "inventory": {  # rarity buckets
                "common": 0,
                "uncommon": 0,
                "rare": 0,
                "epic": 0,
                "legendary": 0,
            },
            "last_fished_ts": 0.0,  # reserved if you want per-second throttling later
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

    def _get_economy(self):
        econ = self.bot.get_cog("NexusExchange")
        if not econ:
            raise RuntimeError(
                "NexusExchange cog not found. Please load it so Fishing can use Wellcoins."
            )
        # Must provide: get_balance(user), add_wellcoins(user, amount), take_wellcoins(user, amount, force=False)
        for fn in ("get_balance", "add_wellcoins", "take_wellcoins"):
            if not hasattr(econ, fn):
                raise RuntimeError(f"NexusExchange is missing required method `{fn}`.")
        return econ

    def _weighted_choice(self, table: Dict[str, float]) -> str:
        items = list(table.items())
        rarities, weights = zip(*items)
        pick = random.random() * sum(weights)
        upto = 0.0
        for rarity, w in items:
            if upto + w >= pick:
                return rarity
            upto += w
        return rarities[-1]  # fallback

    def _compose_table(
        self, *, rod: Rod, bait: Optional[Bait], zone: Zone
    ) -> Dict[str, float]:
        # Start with base table
        table = dict(BASE_RARITY_TABLE)

        # Zone tweaks (additive to weights)
        for r, delta in zone.base_table.items():
            table[r] = max(0.0, table.get(r, 0.0) + delta)

        # Rod "power" shifts weight from lower rarities to higher ones
        # Simple approach: each power point nudges a bit
        for _ in range(rod.power):
            # shift 2% of common -> uncommon, 1% of uncommon -> rare, 0.5% rare -> epic
            for (src, dst, frac) in [
                ("common", "uncommon", 0.02),
                ("uncommon", "rare", 0.01),
                ("rare", "epic", 0.005),
            ]:
                amt = table[src] * frac
                table[src] -= amt
                table[dst] += amt

        # Bait rarity boost (as a small multiplicative on non-common buckets)
        if bait:
            boost = bait.rarity_boost
            for r in ("uncommon", "rare", "epic", "legendary"):
                table[r] *= (1.0 + boost)
            # renormalize to keep overall magnitude similar
            scale = sum(BASE_RARITY_TABLE.values()) / max(sum(table.values()), 1e-9)
            for k in table:
                table[k] *= scale

        # Ensure no negatives
        for k, v in list(table.items()):
            table[k] = max(0.0, v)

        return table

    def _rarity_to_price(self, rarity: str) -> float:
        return RARITY_PRICES.get(rarity, 0.5)

    # ---------- Commands ----------

    @commands.hybrid_group(name="fish", invoke_without_command=True)
    @commands.cooldown(1, 30.0, commands.BucketType.user)  # 30s cooldown per user
    async def fish_cmd(self, ctx: commands.Context):
        """Go fishing! Cooldown: 30s."""
        async with self._lock_for(ctx.author.id):
            data = await self.config.user(ctx.author).all()

            # Validate rod durability
            rod_key = data["rod"]
            rod = RODS.get(rod_key, RODS["twig"])
            if data["rod_durability"] <= 0:
                return await ctx.reply(
                    f"⛔ Your **{rod.name}** is broken. Repair by rebuying it or purchase a new rod."
                )

            # Use bait if available (auto-consume strongest bait you have)
            bait_key = None
            bait: Optional[Bait] = None
            if any(qty > 0 for qty in data["bait"].values()):
                # choose the best you own
                owned = [(BAITS[k], q) for k, q in data["bait"].items() if q > 0 and k in BAITS]
                owned.sort(key=lambda t: BAITS[t[0].key].rarity_boost, reverse=True)
                bait = owned[0][0]
                bait_key = bait.key
                data["bait"][bait_key] -= 1

            # Zone
            zone_key = data["zone"]
            zone = ZONES.get(zone_key, ZONES["pond"])

            # Compose rarity table and roll
            table = self._compose_table(rod=rod, bait=bait, zone=zone)
            rarity = self._weighted_choice(table)

            # Update inventory & durability
            data["inventory"][rarity] = int(data["inventory"].get(rarity, 0)) + 1
            data["rod_durability"] = max(0, int(data["rod_durability"]) - 1)
            await self.config.user(ctx.author).set(data)

            bait_text = f" using **{bait.name}**" if bait else ""
            await ctx.reply(
                f"🎣 You fish in **{zone.name}** with your **{rod.name}**{bait_text}…\n"
                f"✨ You caught a **{rarity.title()}** fish!\n"
                f"🪵 Rod Durability: {data['rod_durability']}/{rod.durability}"
            )

    @fish_cmd.command(name="inventory")
    async def fish_inventory(self, ctx: commands.Context):
        """Show your fish inventory, rod, bait, and zone."""
        data = await self.config.user(ctx.author).all()
        rod = RODS.get(data["rod"], RODS["twig"])
        zone = ZONES.get(data["zone"], ZONES["pond"])
        inv = data["inventory"]
        bait_inv = data["bait"]

        rarity_lines = " • ".join(f"{r.title()}: **{inv.get(r,0)}**" for r in RARITY_PRICES.keys())
        bait_lines = " • ".join(
            f"{BAITS[k].name}: **{qty}**" for k, qty in bait_inv.items() if k in BAITS
        ) or "None"

        await ctx.reply(
            f"**Rod:** {rod.name} ({data['rod_durability']}/{rod.durability})\n"
            f"**Zone:** {zone.name}\n"
            f"**Fish:** {rarity_lines}\n"
            f"**Bait:** {bait_lines}"
        )

    @fish_cmd.command(name="sell")
    async def fish_sell(self, ctx: commands.Context, rarity: Optional[str] = None, amount: Optional[int] = None):
        """
        Sell fish for Wellcoins.
        - No args: sell all.
        - With `rarity`: sell that rarity. Optionally specify `amount`.
        """
        econ = self._get_economy()

        async with self._lock_for(ctx.author.id):
            data = await self.config.user(ctx.author).all()
            zone = ZONES.get(data["zone"], ZONES["pond"])
            inv = data["inventory"]

            def price_for(r: str, qty: int) -> float:
                return self._rarity_to_price(r) * zone.sell_multiplier * qty

            total = 0.0
            sold_detail: List[Tuple[str, int, float]] = []

            if rarity is None:
                # sell everything
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
                    return await ctx.reply("Unknown rarity. Use: common, uncommon, rare, epic, legendary.")
                have = int(inv[r])
                if have <= 0:
                    return await ctx.reply(f"You have no **{r}** fish to sell.")
                qty = have if amount is None else max(0, min(have, int(amount)))
                if qty == 0:
                    return await ctx.reply("Nothing to sell.")
                p = price_for(r, qty)
                total += p
                sold_detail.append((r, qty, p))
                inv[r] = have - qty

            # Save updated inventory
            data["inventory"] = inv
            await self.config.user(ctx.author).set(data)

            # Pay user (truncate via Nexus logic)
            if total > 0:
                await econ.add_wellcoins(ctx.author, float(total))

            if total <= 0:
                return await ctx.reply("No fish sold.")

            lines = "\n".join(
                f"- {r.title()} × {qty}: {p:.2f} WC" for (r, qty, p) in sold_detail
            )
            await ctx.reply(
                f"💰 Sold fish in **{zone.name}** (multiplier ×{zone.sell_multiplier:.2f}):\n{lines}\n"
                f"**Total:** {total:.2f} WC"
            )

    # ---------- Shop & Loadout ----------

    @fish_cmd.group(name="shop", invoke_without_command=True)
    async def fish_shop(self, ctx: commands.Context):
        """Browse shop categories."""
        await ctx.reply(
            "**Shop Categories**\n"
            "- `[p]fish shop rods`\n"
            "- `[p]fish shop bait`\n"
            "- `[p]fish shop zones`"
        )

    @fish_shop.command(name="rods")
    async def shop_rods(self, ctx: commands.Context):
        lines = []
        for r in RODS.values():
            lines.append(f"- **{r.name}** (`{r.key}`): {r.price:.2f} WC | Power {r.power} | Durability {r.durability}")
        await ctx.reply("\n".join(lines))

    @fish_shop.command(name="bait")
    async def shop_bait(self, ctx: commands.Context):
        lines = []
        for b in BAITS.values():
            lines.append(f"- **{b.name}** (`{b.key}`): {b.price:.2f} WC each | Rarity boost {b.rarity_boost:.3f}")
        await ctx.reply("\n".join(lines))

    @fish_shop.command(name="zones")
    async def shop_zones(self, ctx: commands.Context):
        lines = []
        for z in ZONES.values():
            lines.append(
                f"- **{z.name}** (`{z.key}`): Unlock {z.unlock_price:.2f} WC | Sell ×{z.sell_multiplier:.2f}"
            )
        await ctx.reply("\n".join(lines))

    @fish_cmd.group(name="buy")
    async def fish_buy(self, ctx: commands.Context):
        """Buy rods, bait, or zones."""
        pass

    @fish_buy.command(name="rod")
    async def buy_rod(self, ctx: commands.Context, rod_key: str):
        econ = self._get_economy()
        rod_key = rod_key.lower()
        if rod_key not in RODS:
            return await ctx.reply("Unknown rod. Use `[p]fish shop rods` to see options.")
        rod = RODS[rod_key]

        async with self._lock_for(ctx.author.id):
            data = await self.config.user(ctx.author).all()

            # charge
            if rod.price > 0:
                try:
                    await econ.take_wellcoins(ctx.author, rod.price, force=False)
                except ValueError:
                    return await ctx.reply(f"Insufficient funds. Need {rod.price:.2f} WC.")

            # equip and set fresh durability
            data["rod"] = rod.key
            data["rod_durability"] = rod.durability
            await self.config.user(ctx.author).set(data)

        await ctx.reply(f"🪝 You bought and equipped **{rod.name}** (Durability {rod.durability}).")

    @fish_buy.command(name="bait")
    async def buy_bait(self, ctx: commands.Context, bait_key: str, amount: int = 1):
        econ = self._get_economy()
        bait_key = bait_key.lower()
        if bait_key not in BAITS:
            return await ctx.reply("Unknown bait. Use `[p]fish shop bait` to see options.")
        if amount <= 0:
            return await ctx.reply("Amount must be positive.")
        bait = BAITS[bait_key]
        cost = bait.price * amount

        try:
            await econ.take_wellcoins(ctx.author, cost, force=False)
        except ValueError:
            return await ctx.reply(f"Insufficient funds. Need {cost:.2f} WC.")

        async with self._lock_for(ctx.author.id):
            have = await self.config.user(ctx.author).bait()
            have[bait_key] = int(have.get(bait_key, 0)) + amount
            await self.config.user(ctx.author).bait.set(have)

        await ctx.reply(f"🪱 Purchased **{amount}× {bait.name}** for {cost:.2f} WC.")

    @fish_buy.command(name="zone")
    async def buy_zone(self, ctx: commands.Context, zone_key: str):
        econ = self._get_economy()
        zone_key = zone_key.lower()
        if zone_key not in ZONES:
            return await ctx.reply("Unknown zone. Use `[p]fish shop zones` to see options.")
        zone = ZONES[zone_key]

        async with self._lock_for(ctx.author.id):
            data = await self.config.user(ctx.author).all()
            if zone_key in set(data["unlocked_zones"]):
                return await ctx.reply("You already unlocked this zone.")
            price = zone.unlock_price
            if price > 0:
                try:
                    await econ.take_wellcoins(ctx.author, price, force=False)
                except ValueError:
                    return await ctx.reply(f"Insufficient funds. Need {price:.2f} WC.")
            data["unlocked_zones"].append(zone_key)
            await self.config.user(ctx.author).set(data)

        await ctx.reply(f"🗺️ Unlocked **{zone.name}** for {zone.unlock_price:.2f} WC!")

    @fish_cmd.command(name="zone")
    async def fish_zone(self, ctx: commands.Context, zone_key: Optional[str] = None):
        """
        View or set your active fishing zone.
        - No args: shows your unlocked zones and current.
        - With `zone_key`: switches to that zone (must be unlocked).
        """
        if zone_key is None:
            data = await self.config.user(ctx.author).all()
            unlocked = data["unlocked_zones"]
            current = data["zone"]
            names = ", ".join(ZONES[z].name for z in unlocked if z in ZONES)
            return await ctx.reply(
                f"Current zone: **{ZONES[current].name}**\nUnlocked: {names or 'None'}"
            )

        zone_key = zone_key.lower()
        if zone_key not in ZONES:
            return await ctx.reply("Unknown zone.")
        data = await self.config.user(ctx.author).all()
        if zone_key not in data["unlocked_zones"]:
            return await ctx.reply("You haven't unlocked that zone yet.")
        await self.config.user(ctx.author).zone.set(zone_key)
        await ctx.reply(f"✅ Active zone set to **{ZONES[zone_key].name}**.")

    @fish_cmd.command(name="repair")
    async def fish_repair(self, ctx: commands.Context):
        """
        Quick repair: re-buy your current rod to restore durability (cost = rod price).
        """
        econ = self._get_economy()
        data = await self.config.user(ctx.author).all()
        rod = RODS.get(data["rod"], RODS["twig"])
        price = rod.price
        if price > 0:
            try:
                await econ.take_wellcoins(ctx.author, price, force=False)
            except ValueError:
                return await ctx.reply(f"Insufficient funds. Need {price:.2f} WC.")
        await self.config.user(ctx.author).rod_durability.set(rod.durability)
        await ctx.reply(f"🔧 Repaired **{rod.name}** to full durability ({rod.durability}).")

    @fish_cmd.command(name="prices")
    async def fish_prices(self, ctx: commands.Context):
        """Show base prices by rarity and your zone multiplier."""
        data = await self.config.user(ctx.author).all()
        zone = ZONES.get(data["zone"], ZONES["pond"])
        lines = [f"**Zone Multiplier:** ×{zone.sell_multiplier:.2f} ({zone.name})"]
        for r, p in RARITY_PRICES.items():
            lines.append(f"- {r.title()}: {p:.2f} base → {(p*zone.sell_multiplier):.2f} in {zone.name}")
        await ctx.reply("\n".join(lines))


async def setup(bot: Red):
    await bot.add_cog(Fishing(bot))
