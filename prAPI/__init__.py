from .prAPI import prAPI


async def setup(bot):
    await bot.add_cog(prAPI(bot))
