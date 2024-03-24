from .DnDCharacterSheet import DnDCharacterSheet


async def setup(bot):
    await bot.add_cog(DnDCharacterSheet(bot))
