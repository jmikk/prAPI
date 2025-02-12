from .ReactDay import ReactDay


async def setup(bot):
    await bot.add_cog(ReactDay(bot))
