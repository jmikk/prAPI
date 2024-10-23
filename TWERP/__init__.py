from .HOTW import HOTW


async def setup(bot):
    await bot.add_cog(HOTW(bot))
