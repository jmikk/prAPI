from .CardsAuction import CardsAuction


async def setup(bot):
    await bot.add_cog(CardsAuction(bot))
