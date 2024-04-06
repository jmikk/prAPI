from redbot.core import commands
import asyncio
from redbot.core import commands, Config


def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False

    return commands.permissions_check(predicate)


class DisWonder(commands.Cog):
    """My custom cog"""
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890,force_registration=True)

    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    # great once your done messing with the bot.
    #   async def cog_command_error(self, ctx, error):
    #       await ctx.send(" ".join(error.args))

    @commands.command()
    @commands.is_owner()
    async def myCom1(self, ctx):
        recruitomatic_cog = self.bot.get_cog("Recruitomatic9003")
        if recruitomatic_cog is None:
            await ctx.send("Recruitomatic9003 cog is not loaded.")
            return

        # Access the config from the other cog
        user_settings = await recruitomatic_cog.config.user(ctx.author).all()
        guild_settings = await recruitomatic_cog.config.guild(ctx.guild).all()

        # Send the fetched data
        await ctx.send("I work")
        await ctx.send(f"User Settings: {user_settings}")
        await ctx.send(f"Guild Settings: {guild_settings}")

    @commands.command()
    @is_owner_overridable()
    async def myCom2(self, ctx):
        await ctx.send("I still work!")
