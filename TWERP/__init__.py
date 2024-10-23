from .TWERP import TWERP


async def setup(bot):
    await bot.add_cog(TWERP(bot))
