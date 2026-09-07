from .Alchemy import Alchemy


async def setup(bot):
    await bot.add_cog(Alchemy(bot))
