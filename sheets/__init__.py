from .sheets import sheets


async def setup(bot):
    await bot.add_cog(sheets(bot))
