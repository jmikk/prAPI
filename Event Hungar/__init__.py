from .Hungar import Hungar


async def setup(bot):
    await bot.add_cog(Hungar(bot))
