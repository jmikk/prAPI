from .DiceOfKalma import DiceOfKalma


async def setup(bot):
    await bot.add_cog(DiceOfKalma(bot))
