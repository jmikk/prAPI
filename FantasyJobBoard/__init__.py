from .FantasyJobBoard import FantasyJobBoard


async def setup(bot):
    await bot.add_cog(FantasyJobBoard(bot))
