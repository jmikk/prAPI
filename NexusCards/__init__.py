from .NexusCards import NexusCards

async def setup(bot):
    await bot.add_cog(NexusCards(bot))
