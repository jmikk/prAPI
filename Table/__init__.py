from .Farmland import Farmland


async def setup(bot):
    await bot.add_cog(Farmland(bot))
