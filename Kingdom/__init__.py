from .Kingdom import Kingdom


async def setup(bot):
    await bot.add_cog(Kingdom(bot))
