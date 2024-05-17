from redbot.core import commands
from redbot.core.commands import Cooldown, BucketType, CooldownMapping
import datetime


class sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def my_command(self, ctx):
        await ctx.send("This command has a role-based cooldown!")

    async def my_com11(self, ctx):
        await ctx.send("This command does not have a role-based cooldown!")


def setup(bot):
    bot.add_cog(sheets(bot))
