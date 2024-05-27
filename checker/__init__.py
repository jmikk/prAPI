from .checker import checker


async def setup(bot):
    await bot.add_cog(checker(bot))
