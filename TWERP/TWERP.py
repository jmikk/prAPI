import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
import aiohttp

class TWERPModal(discord.ui.Modal, title="Speak as Character"):
    def __init__(self, cog, character_name, webhook, interaction, character_info):
        super().__init__()
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
                "content": self.message.value,  # The multi-line message from the modal
                "username": combined_name,
                "avatar_url": self.character_info["pfp_url"],
                "allowed_mentions": {
                    "parse": ["users"]  # This prevents @everyone and @here from being pinged
                }
            }
            await session.post(webhook_url, json=json_data)
            await self.interaction.response.send_message(f"Message sent as `{self.character_name}`!", ephemeral=True)

class TWERP(commands.Cog):
    """A cog that allows users to post as custom characters using webhooks and earn credits by speaking."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=23456789648)

        # Register new fields if they don't exist yet
        self._init_config()

        bot.loop.create_task(self.sync_commands())

    def _init_config(self):
        """Dynamically add new fields to the existing config without overwriting."""
        if not hasattr(self.config.GUILD, "allowed_channels"):
            self.config.register_guild(allowed_channels=[])
        if not hasattr(self.config.USER, "credits"):
            self.config.register_user(credits=0)
        if not hasattr(self.config.USER, "completed_personal_projects"):
            self.config.register_user(completed_personal_projects={})

    async def sync_commands(self):
        guild_id = 1098644885797609492  # Replace with your test server's ID
        guild = discord.Object(id=guild_id)
        await self.bot.tree.sync(guild=guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen to messages and reward credits based on word count."""
        if message.author.bot:
            return  # Ignore bot messages

        allowed_channels = await self.config.guild(message.guild).allowed_channels()
        if message.channel.id not in allowed_channels:
            return  # Ignore if not in an allowed channel

        word_count = len(message.content.split())
        if word_count >= 10:
            credits_to_add = word_count // 10
            async with self.config.user(message.author).credits() as credits:
                credits += credits_to_add
            await message.channel.send(f"{message.author.mention} earned {credits_to_add} credits!")

    @commands.hybrid_command(name="createcharacter")
    async def create_character(self, ctx: commands.Context, name: str, pfp_url: str):
        """Create a new character with a custom name and profile picture."""
        characters = await self.config.user(ctx.author).characters()
        if characters is None:
            characters = {}

        if len(characters) >= 2:
            await ctx.send("You already have 2 characters! Delete one before creating a new one.")
            return

        characters[name] = {
            "pfp_url": pfp_url,
            "name": name
        }

        await self.config.user(ctx.author).characters.set(characters)
        await ctx.send(f"Character `{name}` created with profile picture!")

    # Define the autocomplete function before it's used
    async def character_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for the character names."""
        characters = await self.config.user(interaction.user).characters()
        return [
            app_commands.Choice(name=char_name, value=char_name)
            for char_name in characters.keys() if current.lower() in char_name.lower()
        ][:25]  # Limit to 25 choices

    @app_commands.command(name="speakas", description="Speak as one of your characters.")
    @app_commands.autocomplete(name=character_autocomplete)
    async def speak_as(self, interaction: discord.Interaction, name: str):
        """Trigger the modal for the user to enter a multi-line message as their character."""
        characters = await self.config.user(interaction.user).characters()
        if name not in characters:
            await interaction.response.send_message(f"Character `{name}` not found.", ephemeral=True)
            return

        character = characters[name]
        webhook = await self._get_webhook(interaction.channel)
        if webhook:
            modal = TWERPModal(self, name, webhook, interaction, character)
            await interaction.response.send_modal(modal)

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
