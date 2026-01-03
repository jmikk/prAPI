from .NationStatesLinker2 import NationStatesLinker2

async def setup(bot):
    await bot.add_cog(NationStatesLinker2(bot))
