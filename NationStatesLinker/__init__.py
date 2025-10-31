from .NationStatesLinker import NationStatesLinker

async def setup(bot):
    await bot.add_cog(NationStatesLinker(bot))
