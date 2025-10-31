from .CardsAuctionWatcher import CardsAuctionWatcher




async def setup(bot):
    await bot.add_cog(CardsAuctionWatcher(bot))
