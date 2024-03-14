from .Recruitomatic9003 import Recruitomatic9003


async def setup(bot):
    await bot.add_cog(Recruitomatic9003(bot))
