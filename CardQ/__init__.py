from .CardQ import CardQ


async def setup(bot):
    await bot.add_cog(CardQ(bot))
