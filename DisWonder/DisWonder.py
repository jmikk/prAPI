from redbot.core import commands
import asyncio


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

    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    # great once your done messing with the bot.
    #   async def cog_command_error(self, ctx, error):
    #       await ctx.send(" ".join(error.args))

    @commands.command()
    @commands.is_owner()
    async def myCom1(self, ctx):
        await ctx.send("I work")

    @commands.command()
    @is_owner_overridable()
    async def myCom2(self, ctx):
        await ctx.send("I still work!")
