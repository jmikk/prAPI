from .log import log


async def setup(bot):
    await bot.add_cog(log(bot))
