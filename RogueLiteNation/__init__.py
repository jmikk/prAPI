from .RogueLiteNation import RogueLiteNation


async def setup(bot):
    await bot.add_cog(RogueLiteNation(bot))
