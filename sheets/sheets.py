from redbot.core import commands
from redbot.core.commands import BucketType, CommandOnCooldown
import time

class Sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}

    def get_cooldown(self, user_id, role_id):
        now = time.time()
        if user_id not in self.cooldowns:
            self.cooldowns[user_id] = {}
        
        user_cooldowns = self.cooldowns[user_id]
        if role_id in user_cooldowns and user_cooldowns[role_id] > now:
            raise CommandOnCooldown(commands.Cooldown(rate=1, per=user_cooldowns[role_id] - now, type=BucketType.user))
        else:
            return now

    @commands.command()
    async def my_command(self, ctx):
        user_id = ctx.author.id
        user_roles = [role.id for role in ctx.author.roles]

        # Default cooldown: 1 use per week
        cooldown_period = 7 * 24 * 3600
        max_uses = 1

        # Adjust cooldown based on roles
        if 1098646004250726420 in user_roles:  # Role A
            max_uses = 2
        if 1098673767858843648 in user_roles:  # Role B
            max_uses = 3

        role_id = 'default'
        if 1098646004250726420 in user_roles:
            role_id = 'role_a'
        if 1098673767858843648 in user_roles:
            role_id = 'role_b'

        last_used = self.get_cooldown(user_id, role_id)

        if role_id not in self.cooldowns[user_id]:
            self.cooldowns[user_id][role_id] = last_used + cooldown_period / max_uses
        else:
            self.cooldowns[user_id][role_id] += cooldown_period / max_uses

        await ctx.send("This command has a role-based cooldown!")

def setup(bot):
    bot.add_cog(Sheets(bot))

