from .DailyNationTracker import DailyNationTracker


async def setup(bot):
    await bot.add_cog(DailyNationTracker(bot))
