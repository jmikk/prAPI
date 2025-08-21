import asyncio
from redbot.core import commands, Config
import discord

BUILDINGS = {
    "farm": {"cost": 100, "upkeep": 2, "produces": {"food": 5}},
    "mine": {"cost": 200, "upkeep": 3, "produces": {"metal": 2}},
    "factory": {"cost": 500, "upkeep": 5, "produces": {"goods": 1}},
}

class CityBuilder(commands.Cog):
    """City planning game with resource management"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=34567890876, force_registration=True)
        self.config.register_user(resources={}, buildings={})
        self.task = bot.loop.create_task(self.resource_tick())

    async def cog_unload(self):
        self.task.cancel()
   
    # ========== Tick Logic ==========
    async def process_tick(self, user):
        """Run upkeep + production for a single user."""
        nexus = self.bot.get_cog("NexusExchange")
        if not nexus:
            return

        user_data = await self.config.user(user).all()
        buildings = user_data["buildings"]

        if not buildings:
            return  # no buildings → nothing to do

        # Calculate upkeep
        total_upkeep = sum(
            BUILDINGS[b]["upkeep"] * data["count"]
            for b, data in buildings.items()
        )

        try:
            await nexus.take_wellcoins(user, total_upkeep, force=False)
            # Produce resources
            new_resources = user_data["resources"].copy()
            for b, data in buildings.items():
                for res, amt in BUILDINGS[b]["produces"].items():
                    new_resources[res] = new_resources.get(res, 0) + amt * data["count"]
            await self.config.user(user).resources.set(new_resources)
        except ValueError:
            # Not enough Wellcoins → skip production
            pass

    async def process_all_ticks(self):
        """Process a tick for all registered users."""
        all_users = await self.config.all_users()
        for user_id in all_users:
            user = self.bot.get_user(user_id)
            if user:
                await self.process_tick(user)

    async def resource_tick(self):
        """Automatic background tick (hourly)."""
        await self.bot.wait_until_ready()
        while True:
            await self.process_all_ticks()
            await asyncio.sleep(3600)  # 1 hour


    # ========== Commands ==========

    
    @commands.command()
    async def nextday(self, ctx):
        """Force everyone forward by one tick (testing only)."""
        await self.process_all_ticks()
        await ctx.send("⏩ Advanced the world by one day (one tick).")
        
    @commands.command()
    async def build(self, ctx, building: str, amount: int = 1):
        """Construct a building with Wellcoins."""
        building = building.lower()
        if building not in BUILDINGS:
            return await ctx.send("❌ Unknown building.")

        nexus = self.bot.get_cog("NexusExchange")
        if not nexus:
            return await ctx.send("⚠️ NexusExchange cog not loaded.")

        cost = BUILDINGS[building]["cost"] * amount
        try:
            await nexus.take_wellcoins(ctx.author, cost, force=False)
        except ValueError:
            return await ctx.send("❌ You don’t have enough Wellcoins!")

        # Add building to player
        data = await self.config.user(ctx.author).buildings()
        data[building] = {"count": data.get(building, {}).get("count", 0) + amount}
        await self.config.user(ctx.author).buildings.set(data)

        await ctx.send(f"🏗️ Built {amount} {building}(s)!")

    @commands.command()
    async def city(self, ctx):
        """View your city resources and buildings."""
        data = await self.config.user(ctx.author).all()
        res = ", ".join(f"{k}: {v}" for k, v in data["resources"].items()) or "None"
        bld = ", ".join(f"{b} x{info['count']}" for b, info in data["buildings"].items()) or "None"
        await ctx.send(
            f"🌆 **Your City**\n"
            f"Resources: {res}\n"
            f"Buildings: {bld}"
        )
