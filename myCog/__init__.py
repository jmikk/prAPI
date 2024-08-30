from .CardRequestCog import CardRequestCog


async def setup(bot):
    await bot.add_cog(CardRequestCog(bot))
