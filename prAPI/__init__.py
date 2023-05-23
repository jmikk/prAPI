from .prAPI import pAPI


async def setup(bot):
    await bot.add_cog(pAPI(bot))
