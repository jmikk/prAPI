from redbot.core import commands
from redbot.core.commands import BucketType, Cooldown
import time

def dynamic_cooldown(ctx):
    user_roles = [role.id for role in ctx.author.roles]

    # Default cooldown: 1 use per week
    cooldown_period = 7 * 24 * 3600
    rate = 1

    # Adjust cooldown based on roles
    if 1098646004250726420 in user_roles:  # Role A
        rate = 2
    if 1098673767858843648 in user_roles:  # Role B
        rate = 3

    return Cooldown(rate=rate, per=cooldown_period, type=BucketType.user)

class sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.dynamic_cooldown(dynamic_cooldown, type=BucketType.user)
    @commands.command()
    async def my_command(self, ctx):
        await ctx.send("This command has a role-based cooldown!")

def setup(bot):
    bot.add_cog(sheets(bot))
