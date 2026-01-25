from .Quest import Quest


async def setup(bot):
    await bot.add_cog(Quest(bot))
