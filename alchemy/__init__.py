from .alchemy import alchemy


async def setup(bot):
    await bot.add_cog(alchemy(bot))
