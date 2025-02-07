from .NexusExchange import NexusExchange


async def setup(bot):
    await bot.add_cog(NexusExchange(bot))
