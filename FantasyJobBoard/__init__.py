from .FantasyJobBoard import FantasyJobBoard


async def setup(bot):
    await bot.add_cog(Quest(bot))
