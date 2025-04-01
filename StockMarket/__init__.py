from .StockMarket import StockMarket


async def setup(bot):
    await bot.add_cog(StockMarket(bot))
