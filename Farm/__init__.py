from .Farm import Farm


async def setup(bot):
    await bot.add_cog(Farm(bot))
