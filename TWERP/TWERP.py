import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import aiohttp

class CharacterSelect(discord.ui.Select):
    def __init__(self, cog, characters, interaction):
        self.cog = cog
        self.interaction = interaction
        options = [
            discord.SelectOption(label=char_name, value=char_name)
            for char_name in characters.keys()
        ]
        super().__init__(placeholder="Select a character...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        """Trigger the modal after a character is selected."""
        character_name = self.values[0]  # Get selected character
        characters = await self.cog.config.user(interaction.user).characters()
        character_info = characters[character_name]
        webhook = await self.cog._get_webhook(interaction.channel)

        if webhook:
            modal = TWERPModal(self.cog, character_name, webhook, interaction, character_info)
            await interaction.response.send_modal(modal)

class CharacterSelectView(discord.ui.View):
    def __init__(self, cog, characters, interaction):
        super().__init__(timeout=180)  # View timeout after 180 seconds
        self.add_item(CharacterSelect(cog, characters, interaction))

class TWERPModal(discord.ui.Modal, title="Speak as Character"):
    def __init__(self, cog, character_name, webhook, interaction, character_info):
        super().__init__(title=f"Speak as {character_name}")  # Modal title shows the character name
        self.cog = cog
        self.character_name = character_name
        self.webhook = webhook
        self.interaction = interaction
        self.character_info = character_info

        self.message = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.paragraph,  # Multiline text area
            placeholder="Enter your message here...",
            required=True,
            max_length=2000  # Discord limit for message length
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        """Send the message via the webhook when the modal is submitted."""
        async with aiohttp.ClientSession() as session:
            webhook_url = self.webhook.url
            combined_name = f"{self.character_info['name']} ({interaction.user.name})"
            json_data = {
                "content": self.message.value,
                "username": combined_name,
                "avatar_url": self.character_info["pfp_url"],
                "allowed_mentions": {
                    "parse": ["users"]  # Prevent @everyone and @here pings
                }
            }
            await session.post(webhook_url, json=json_data)
            await self.interaction.response.send_message(f"Message sent as `{self.character_name}`!", ephemeral=True)

class TWERP(commands.Cog):
    """A cog that allows users to create characters, delete them, and send messages as characters using webhooks."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=23456789648)

        self._init_config()
        bot.loop.create_task(self.sync_commands())

    def _init_config(self):
        if not hasattr(self.config.GUILD, "allowed_channels"):
            self.config.register_guild(allowed_channels=[])
        if not hasattr(self.config.USER, "credits"):
            self.config.register_user(credits=0)
        if not hasattr(self.config.USER, "completed_personal_projects"):
            self.config.register_user(completed_personal_projects={})
        if not hasattr(self.config.USER, "characters"):
            self.config.register_user(characters={})

    async def sync_commands(self):
        guild_id = 1098644885797609492  # Replace with your test server's ID
        guild = discord.Object(id=guild_id)
        await self.bot.tree.sync(guild=guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen to messages and reward credits based on word count."""
        if message.author.bot:
            return

        allowed_channels = await self.config.guild(message.guild).allowed_channels()
        if message.channel.id not in allowed_channels:
            return

        word_count = len(message.content.split())
        if word_count >= 10:
            credits_to_add = word_count // 10
            async with self.config.user(message.author).credits() as credits:
                credits += credits_to_add
            await message.channel.send(f"{message.author.mention} earned {credits_to_add} credits!")

    # Create Character Slash Command
    @discord.app_commands.command(name="createcharacter", description="Create a character with a name and profile picture URL.")
    async def create_character(self, interaction: discord.Interaction, name: str, pfp_url: str):
        """Create a new character with a custom name and profile picture."""
        characters = await self.config.user(interaction.user).characters()
        if characters is None:
            characters = {}

        if len(characters) >= 2:
            await interaction.response.send_message("You already have 2 characters! Delete one before creating a new one.", ephemeral=True)
            return

        characters[name] = {
            "pfp_url": pfp_url,
            "name": name
        }

        await self.config.user(interaction.user).characters.set(characters)
        await interaction.response.send_message(f"Character `{name}` created with profile picture!", ephemeral=True)

    # Delete Character Slash Command
    @discord.app_commands.command(name="deletecharacter", description="Delete one of your characters.")
    async def delete_character(self, interaction: discord.Interaction, name: str):
        """Delete one of your characters."""
        characters = await self.config.user(interaction.user).characters()

        if name not in characters:
            await interaction.response.send_message(f"Character `{name}` not found.", ephemeral=True)
            return

        del characters[name]
        await self.config.user(interaction.user).characters.set(characters)
        await interaction.response.send_message(f"Character `{name}` deleted.", ephemeral=True)

    # Select Character Slash Command
    @discord.app_commands.command(name="selectcharacter", description="Show a dropdown to select a character.")
    async def select_character(self, interaction: discord.Interaction):
        """Show a dropdown to select a character, then open a modal to enter a message."""
        characters = await self.config.user(interaction.user).characters()
        if not characters:
            await interaction.response.send_message("You don't have any characters created.", ephemeral=True)
            return

        view = CharacterSelectView(self, characters, interaction)
        await interaction.response.send_message("Select a character to speak as:", view=view, ephemeral=True)

    async def _get_webhook(self, channel: discord.TextChannel):
        """Creates or retrieves a webhook for the channel."""
        webhooks = await channel.webhooks()
        bot_webhook = discord.utils.get(webhooks, name="CharacterWebhook")

        if not bot_webhook:
            try:
                bot_webhook = await channel.create_webhook(name="CharacterWebhook")
            except discord.Forbidden:
                return None

        return bot_webhook
