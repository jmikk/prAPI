from .Recruitomatic9006 import Recruitomatic9006


async def setup(bot):
    await bot.add_cog(Recruitomatic9006(bot))
