from .Casino import Casino


async def setup(bot):
    await bot.add_cog(Casino(bot))
