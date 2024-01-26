from redbot.core import commands, Config
import asyncio
import datetime

class FarmingGame(commands.Cog):
    """Farming Game Cog for Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=12345789630, force_registration=True)

        default_user = {
            "inventory": {},
            "fields": {}
        }
        self.config.register_user(**default_user)

    @commands.group()
    async def farm(self, ctx):
        """Farming commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `plant`, `status`, or `harvest` commands to play.")

    @farm.command()
    async def plant(self, ctx, crop_name: str):
        """Plant a crop."""
        await self._plant_crop(ctx.author, crop_name)
        await ctx.send(f"{crop_name} planted!")

    async def _plant_crop(self, user, crop_name):
        now = datetime.datetime.now().timestamp()
        async with self.config.user(user).fields() as fields:
            fields[crop_name] = now

    @farm.command()
    async def status(self, ctx):
        """Check the status of your crops."""
        fields = await self.config.user(ctx.author).fields()
        status_messages = await self._get_crop_statuses(fields)
        await ctx.send("\n".join(status_messages))

    async def _get_crop_statuses(self, fields):
        now = datetime.datetime.now().timestamp()
        messages = []
        for crop, planted_time in fields.items():
            growth_time = self._get_growth_time(crop)  # Define this method based on your crop types
            remaining = growth_time - (now - planted_time)
            if remaining > 0:
                messages.append(f"{crop} will be ready in {remaining / 3600:.2f} hours.")
            else:
                messages.append(f"{crop} is ready to harvest!")
        return messages

    def _get_growth_time(self, crop_name):
        """Get the growth time for a crop in seconds."""
        growth_times = {
            "potatoes": 60,  # 1 minute in seconds
            "tacos": 86400   # 1 day in seconds (24 hours * 60 minutes * 60 seconds)
        }
        return growth_times.get(crop_name, 0)  # Returns 0 if the crop is not defined


    @farm.command()
    async def harvest(self, ctx, crop_name: str):
        """Harvest a ready crop."""
        success = await self._harvest_crop(ctx.author, crop_name)
        if success:
            await ctx.send(f"{crop_name} harvested successfully!")
        else:
            await ctx.send(f"{crop_name} is not ready yet.")

    async def _harvest_crop(self, user, crop_name):
        fields = await self.config.user(user).fields()
        if crop_name in fields:
            now = datetime.datetime.now().timestamp()
            planted_time = fields[crop_name]
            growth_time = self._get_growth_time(crop_name)  # Define this method
            if now - planted_time >= growth_time:
                async with self.config.user(user).fields() as fields:
                    del fields[crop_name]
                return True
        return False
