from .APIRecruiter import APIRecruiter


async def setup(bot):
    await bot.add_cog(APIRecruiter.py(bot))
