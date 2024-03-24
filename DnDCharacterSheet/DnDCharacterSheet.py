import discord
from redbot.core import commands, Config
from discord.ui import Modal, TextInput

class CharacterSheetModal(Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_item(TextInput(label="Character Name", placeholder="Enter your character's name", required=True))
        self.add_item(TextInput(label="AC", placeholder="Enter your character's Armor Class", required=True))
        # Add more fields as needed

    async def callback(self, interaction: discord.Interaction):
        char_name = self.children[0].value
        ac = self.children[1].value
        # Process other fields...
        

        # Save the data to the user's config
        user_data = {"name": char_name, "ac": ac}
        await self.cog.config.user(interaction.user).set_raw("character_sheet", value=user_data)

        await interaction.response.send_message(f"Character {char_name} created with AC {ac}!", ephemeral=True)

class DnDCharacterSheet(commands.Cog):
    """A cog for D&D 5e character sheets using modals and RedBot Config."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_user(character_sheet={})

    @commands.command(name="newchar")
    async def new_character(self, ctx: commands.Context):
        modal = CharacterSheetModal(title="New Character Sheet")
        modal.cog = self  # Pass the cog reference to the modal
        await ctx.send_modal(modal)

    @commands.command(name="showchar")
    async def show_character(self, ctx: commands.Context):
        # Fetch the character sheet from the user's config
        char_sheet = await self.config.user(ctx.author).character_sheet()

        if not char_sheet:
            await ctx.send("You don't have a character sheet yet. Use `newchar` to create one.")
            return

        embed = discord.Embed(title=f"{char_sheet['name']}'s Character Sheet", color=0x00FF00)
        embed.add_field(name="AC", value=char_sheet['ac'], inline=True)
        # Add more fields as you included in your modal

        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(DnDCharacterSheet(bot))
