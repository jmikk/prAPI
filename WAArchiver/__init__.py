from .WAArchiver import WAArchiver


async def setup(bot):
    await bot.add_cog(WAArchiver(bot))
