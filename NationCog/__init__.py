from .NationCog import NationCog


async def setup(bot):
    await bot.add_cog(NationCog(bot))
