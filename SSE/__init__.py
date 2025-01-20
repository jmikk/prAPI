from .SSE import SSE


async def setup(bot):
    await bot.add_cog(SSE(bot))
