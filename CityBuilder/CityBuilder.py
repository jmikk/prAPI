import asyncio
import math
from typing import Dict
from redbot.core import commands, Config, checks
import discord

# ---- Game balance knobs ----
BUILDINGS: Dict[str, Dict] = {
    "farm":    {"cost": 100.0, "upkeep": 2.0, "produces": {"food": 5}},   # per building per tick
    "mine":    {"cost": 200.0, "upkeep": 3.0, "produces": {"metal": 2}},
    "factory": {"cost": 500.0, "upkeep": 5.0, "produces": {"goods": 1}},
}

TICK_SECONDS = 3600  # hourly

def trunc2(x: float) -> float:
    # truncate (not round) to 2 decimals
    return math.trunc(float(x) * 100) / 100.0

class CityBuilder(commands.Cog):
    """City planning game with resource management (Wellcoin wages via Bank)."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        self.config.register_user(
            resources={},     # {"food": 0, "metal": 0, ...}
            buildings={},     # {"farm": {"count": int}, ...}
            bank=0.0          # Wellcoins reserved for upkeep/wages
        )
        self.task = bot.loop.create_task(self.resource_tick())

    async def cog_unload(self):
        self.task.cancel()

    # ========= Core tick logic =========
    async def process_tick(self, user: discord.abc.User):
        """Upkeep comes ONLY from the user's Bank. If paid, produce resources."""
        nexus = self.bot.get_cog("NexusExchange")
        if not nexus:
            return

        data = await self.config.user(user).all()
        buildings = data.get("buildings", {})
        if not buildings:
            return

        # total upkeep owed this tick
        total_upkeep = sum(
            BUILDINGS[b]["upkeep"] * info.get("count", 0)
            for b, info in buildings.items()
            if b in BUILDINGS and info.get("count", 0) > 0
        )
        total_upkeep = trunc2(total_upkeep)

        # pull ONLY from bank; do NOT auto-pull from wallet
        bank = float(data.get("bank", 0.0))
        if bank + 1e-9 < total_upkeep:  # insufficient → halt
            return

        # pay wages from bank
        bank = trunc2(bank - total_upkeep)

        # produce resources
        new_resources = dict(data.get("resources", {}))
        for b, info in buildings.items():
            if b not in BUILDINGS:
                continue
            cnt = info.get("count", 0)
            if cnt <= 0:
                continue
            for res, amt in BUILDINGS[b]["produces"].items():
                new_resources[res] = int(new_resources.get(res, 0)) + int(amt * cnt)

        # persist
        await self.config.user(user).resources.set(new_resources)
        await self.config.user(user).bank.set(bank)

    async def process_all_ticks(self):
        all_users = await self.config.all_users()
        for user_id in all_users:
            user = self.bot.get_user(user_id)
            if user:
                await self.process_tick(user)

    async def resource_tick(self):
        await self.bot.wait_until_ready()
        while True:
            await self.process_all_ticks()
            await asyncio.sleep(TICK_SECONDS)

    # ========= Command group =========
    @commands.group(name="city")
    async def city(self, ctx):
        """City-building commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `city view`, `city build <name> [amount]`, or `city bank ...`")

    # ---- City → view ----
    @city.command(name="view")
    async def city_view(self, ctx: commands.Context, member: discord.Member = None):
        """View your (or another player's) city."""
        member = member or ctx.author
        data = await self.config.user(member).all()
        res = data.get("resources", {})
        bld = data.get("buildings", {})
        bank = trunc2(float(data.get("bank", 0.0)))

        res_str = ", ".join(f"{k}: {v}" for k, v in res.items()) or "None"
        bld_str = ", ".join(f"{k} x{info.get('count', 0)}" for k, info in bld.items()) or "None"

        # compute current upkeep per tick
        upkeep = sum(
            BUILDINGS[b]["upkeep"] * info.get("count", 0)
            for b, info in bld.items() if b in BUILDINGS
        )
        upkeep = trunc2(upkeep)

        await ctx.send(
            f"🌆 **{member.display_name}'s City**\n"
            f"🏦 Bank: {bank:.2f} Wellcoins\n"
            f"⏳ Upkeep per tick: {upkeep:.2f} Wellcoins\n"
            f"🏗️ Buildings: {bld_str}\n"
            f"📦 Resources: {res_str}"
        )

    # ---- City → build ----
    @city.command(name="build")
    async def city_build(self, ctx: commands.Context, building: str, amount: int = 1):
        """Buy buildings with Wellcoins (from your wallet)."""
        building = building.lower()
        if building not in BUILDINGS:
            return await ctx.send("❌ Unknown building. Try: " + ", ".join(BUILDINGS.keys()))
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")

        nexus = self.bot.get_cog("NexusExchange")
        if not nexus:
            return await ctx.send("⚠️ NexusExchange cog not loaded.")

        cost = trunc2(BUILDINGS[building]["cost"] * amount)
        try:
            # Pay from WALLET (not bank)
            await nexus.take_wellcoins(ctx.author, cost, force=False)
        except ValueError:
            return await ctx.send(f"❌ You don’t have enough Wellcoins for {amount} {building}(s). Cost: {cost:.2f}")

        # add buildings
        bld = await self.config.user(ctx.author).buildings()
        cur = bld.get(building, {}).get("count", 0)
        bld[building] = {"count": int(cur + amount)}
        await self.config.user(ctx.author).buildings.set(bld)

        await ctx.send(f"🏗️ Built {amount} **{building}**(s) for {cost:.2f} Wellcoins!")

    # ========= Bank subcommands =========
    @city.group(name="bank")
    async def city_bank(self, ctx):
        """Bank operations (used to pay upkeep)."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `city bank deposit <amount>`, `city bank withdraw <amount>`, or `city bank balance`")

    @city_bank.command(name="balance")
    async def city_bank_balance(self, ctx: commands.Context, member: discord.Member = None):
        """Check bank balance."""
        member = member or ctx.author
        bank = trunc2(float(await self.config.user(member).bank()))
        await ctx.send(f"🏦 {member.display_name}'s Bank: {bank:.2f} Wellcoins")

    @city_bank.command(name="deposit")
    async def city_bank_deposit(self, ctx: commands.Context, amount: float):
        """Deposit Wellcoins from your wallet into your Bank."""
        amount = trunc2(amount)
        if amount <= 0:
            return await ctx.send("❌ Deposit amount must be positive.")
        nexus = self.bot.get_cog("NexusExchange")
        if not nexus:
            return await ctx.send("⚠️ NexusExchange cog not loaded.")
        try:
            # remove from wallet
            await nexus.take_wellcoins(ctx.author, amount, force=False)
        except ValueError:
            return await ctx.send("❌ Not enough Wellcoins in your wallet.")

        # add to bank
        bank = trunc2(float(await self.config.user(ctx.author).bank()) + amount)
        await self.config.user(ctx.author).bank.set(bank)
        await ctx.send(f"✅ Deposited {amount:.2f} to bank. New bank: {bank:.2f}")

    @city_bank.command(name="withdraw")
    async def city_bank_withdraw(self, ctx: commands.Context, amount: float):
        """Withdraw Wellcoins from your Bank back to your wallet."""
        amount = trunc2(amount)
        if amount <= 0:
            return await ctx.send("❌ Withdraw amount must be positive.")
        nexus = self.bot.get_cog("NexusExchange")
        if not nexus:
            return await ctx.send("⚠️ NexusExchange cog not loaded.")

        bank = trunc2(float(await self.config.user(ctx.author).bank()))
        if bank + 1e-9 < amount:
            return await ctx.send("❌ Not enough in bank to withdraw that much.")

        # deduct from bank
        bank = trunc2(bank - amount)
        await self.config.user(ctx.author).bank.set(bank)

        # add to wallet
        await nexus.add_wellcoins(ctx.author, amount)
        await ctx.send(f"✅ Withdrew {amount:.2f}. New bank: {bank:.2f}")

    # ========= Admin: advance world =========
    @city.command(name="nextday")
    @checks.admin_or_permissions(manage_guild=True)
    async def city_nextday(self, ctx: commands.Context):
        """Advance EVERYONE one tick (testing/admin)."""
        await self.process_all_ticks()
        await ctx.send("⏩ Advanced the world by one day (one tick).")
