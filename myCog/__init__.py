from .cardMini import cardMini


async def setup(bot):
    await bot.add_cog(cardMini(bot))
