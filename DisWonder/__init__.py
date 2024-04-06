from .DisWonder import DisWonder


async def setup(bot):
    await bot.add_cog(DisWonder(bot))
