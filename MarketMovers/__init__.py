from .MarketMovers import MarketMovers

async def setup(bot):
    await bot.add_cog(MarketMovers(bot))
