from .rota import rota


async def setup(bot):
    await bot.add_cog(rota(bot))
