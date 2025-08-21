from .CityBuilder import CityBuilder


async def setup(bot):
    await bot.add_cog(CityBuilder(bot))
