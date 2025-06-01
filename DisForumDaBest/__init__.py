from .DisForumDaBest import DisForumDaBest


async def setup(bot):
    await bot.add_cog(DisForumDaBest.py(bot))
