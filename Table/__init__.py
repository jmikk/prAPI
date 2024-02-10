from .Table import Table


async def setup(bot):
    await bot.add_cog(Table(bot))
