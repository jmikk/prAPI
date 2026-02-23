from .NSCards import NSCards


async def setup(bot):
    await bot.add_cog(NSCards(bot))
