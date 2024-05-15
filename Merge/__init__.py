from .Merge import Merge


async def setup(bot):
    await bot.add_cog(Merge(bot))
