from .PortalChat import PortalChat


async def setup(bot):
    await bot.add_cog(PortalChat(bot))
