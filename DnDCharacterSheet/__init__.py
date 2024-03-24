from .issues import issues


async def setup(bot):
    await bot.add_cog(issues(bot))
