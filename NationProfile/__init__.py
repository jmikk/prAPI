from .NationProfile import NationProfile


async def setup(bot):
    await bot.add_cog(NationProfile(bot))
