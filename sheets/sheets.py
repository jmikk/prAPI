from redbot.core import commands
from redbot.core.commands import Cooldown, BucketType, CooldownMapping
import datetime

def role_based_cooldown(cooldown_mapping):
    def decorator(func):
        async def predicate(ctx):
            user_roles = [role.id for role in ctx.author.roles]
            for role_id, cooldown in cooldown_mapping.items():
                if role_id in user_roles:
                    return Cooldown(rate=cooldown[0], per=cooldown[1], type=BucketType.user)
            return Cooldown(rate=1, per=7*24*3600, type=BucketType.user)  # Default cooldown if no role matches
        
        func.__commands_cooldown__ = CooldownMapping.from_cooldown(
            rate=predicate, per=1, type=BucketType.user)
        return func
    return decorator

class sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @role_based_cooldown({
        1098646004250726420: (2, 7*24*3600),  # Role ID 123456789012345678 has a cooldown of 2 uses per 30 seconds
        1098673767858843648: (3, 7*24*3600),  # Role ID 234567890123456789 has a cooldown of 5 uses per 60 seconds
    })
    @commands.command()
    async def my_command(self, ctx):
        await ctx.send("This command has a role-based cooldown!")






