from .GiveawayCog import GiveawayCog


async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))
