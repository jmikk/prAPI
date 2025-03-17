from .APIRecruiter.py import APIRecruiter.py


async def setup(bot):
    await bot.add_cog(APIRecruiter.py(bot))
