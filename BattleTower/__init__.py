from .BattleTower import BattleTower


async def setup(bot):
    await bot.add_cog(BattleTower(bot))
