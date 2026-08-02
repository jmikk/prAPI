from .SimpleEconomy import SimpleEconomy


async def setup(bot):
    await bot.add_cog(SimpleEconomy(bot))
