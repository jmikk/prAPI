from redbot.core import commands
from redbot.core.commands import Cooldown, BucketType, CooldownMapping
import datetime

def role_based_cooldown(cooldown_mapping):
    def decorator(func):
        async def wrapped(ctx, *args, **kwargs):
            user_roles = {role.id for role in ctx.author.roles}
            cooldown = Cooldown(rate=1, per=7*24*3600, type=BucketType.user)  # Default cooldown: 1 use per week
            
            # Check for specific roles and set the most permissive cooldown
            for role_id, cd in cooldown_mapping.items():
                if role_id in user_roles:
                    rate, per = cd
                    if rate > cooldown.rate:
                        cooldown = Cooldown(rate=rate, per=per, type=BucketType.user)
            
            # Apply cooldown
            func.__commands_cooldown__ = CooldownMapping.from_cooldown(
                rate=cooldown.rate, per=cooldown.per, type=BucketType.user
            )
            return await func(ctx, *args, **kwargs)
        
        return wrapped
    return decorator

class sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @role_based_cooldown({
        1098646004250726420: (2, 7*24*3600),  # Role ID 1098646004250726420: 2 uses per week
        1098673767858843648: (3, 7*24*3600),  # Role ID 1098673767858843648: 3 uses per week
    })
    @commands.command()
    async def my_command(self, ctx):
        await ctx.send("This command has a role-based cooldown!")

    async def my_com11(self, ctx):
        await ctx.send("This command does not have a role-based cooldown!")


def setup(bot):
    bot.add_cog(sheets(bot))
