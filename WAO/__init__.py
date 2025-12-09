from .WAO import WAO


async def setup(bot):
    await bot.add_cog(WAO(bot))
