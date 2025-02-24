from .RCV import RCV


async def setup(bot):
    await bot.add_cog(RCV(bot))
