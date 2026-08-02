from .EventHungar import EventHungar


async def setup(bot):
    await bot.add_cog(EventHungar(bot))
