from .CardMarket import CardMarket


async def setup(bot):
    await bot.add_cog(CardMarket(bot))
