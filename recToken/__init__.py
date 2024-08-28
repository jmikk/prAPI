from .recToken import recToken


async def setup(bot):
    await bot.add_cog(recToken(bot))
