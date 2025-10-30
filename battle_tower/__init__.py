from .battle_tower import battle_tower


async def setup(bot):
    await bot.add_cog(battle_tower(bot))
