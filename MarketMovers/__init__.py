from .MarketMovers import MarketMovers

def setup(bot):
    bot.add_cog(MarketMovers(bot))
