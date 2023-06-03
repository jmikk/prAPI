from .GiveAway import GiveAway


async def setup(bot):
    await bot.add_cog(GiveAway(bot))
