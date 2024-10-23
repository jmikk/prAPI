from .TWERP import TWERP
from redbot.core import commands

@commands.Cog.listener()
async def on_ready(self):
    guild_id = YOUR_GUILD_ID  # Replace with your guild ID if you want to test commands in a specific server
    guild = discord.Object(id=guild_id)
    await self.bot.tree.sync(guild=guild)
    print("Commands synced!")


async def setup(bot):
    await bot.add_cog(TWERP(bot))
