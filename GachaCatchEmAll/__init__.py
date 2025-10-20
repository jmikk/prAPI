from .GachaCatchEmAll import GachaCatchEmAll


async def setup(bot):
    await bot.add_cog(GachaCatchEmAll(bot))
