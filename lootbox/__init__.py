from .lootbox import lootbox


async def setup(bot):
    await bot.add_cog(lootbox(bot))
