from .EventCasino import EventCasino


async def setup(bot):
    await bot.add_cog(EventCasino(bot))
