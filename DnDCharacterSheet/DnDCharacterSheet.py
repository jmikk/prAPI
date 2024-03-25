import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Modal, TextInput

class DnDCharacterModal(Modal):
    def __init__(self, *args, **kwargs):
        super().__init__("D&D Character Attributes", *args, **kwargs)
        
        self.add_item(TextInput(label="Strength", placeholder="Enter Strength (STR)"))
        self.add_item(TextInput(label="Dexterity", placeholder="Enter Dexterity (DEX)"))
        self.add_item(TextInput(label="Constitution", placeholder="Enter Constitution (CON)"))
        self.add_item(TextInput(label="Intelligence", placeholder="Enter Intelligence (INT)"))
        self.add_item(TextInput(label="Wisdom", placeholder="Enter Wisdom (WIS)"))
        self.add_item(TextInput(label="Charisma", placeholder="Enter Charisma (CHA)"))

    async def callback(self, interaction: discord.Interaction):
        # Process the character attributes here
        # For example, you could save them to a database or send them back to the user
        attributes = [self.children[i].value for i in range(6)]
        await interaction.response.send_message(f"Character attributes: {attributes}", ephemeral=True)

class DnDCharacterSheet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_user(character_sheet={})

    async def setup_hook(self):
        self.tree.add_command(create_character)
        await bot.tree.sync()

async def create_character(interaction: discord.Interaction):
    modal = DnDCharacterModal()
    await interaction.response.send_modal(modal)

create_character = app_commands.Command(name="create_character", description="Create a new D&D character", callback=create_character)

