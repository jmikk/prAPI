from .Run import Run


async def setup(bot):
    await bot.add_cog(Run(bot))
