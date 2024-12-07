from .weekly import WeeklyEmbedScheduler


async def setup(bot):
    await bot.add_cog(WeeklyEmbedScheduler(bot))
