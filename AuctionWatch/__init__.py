from .AuctionWatch import AuctionWatch


async def setup(bot):
    await bot.add_cog(AuctionWatch(bot))
