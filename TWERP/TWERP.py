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
        try:
            character_name = self.values[0]  # Get selected character
            characters = await self.cog.config.user(interaction.user).characters()
            character_info = characters[character_name]
            webhook = await self.cog._get_webhook(interaction.channel)

            if webhook:
                modal = TWERPModal(self.cog, character_name, webhook, interaction, character_info)
                await interaction.response.send_modal(modal)
            else:
                await interaction.response.send_message("Failed to retrieve or create a webhook.", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)


class CharacterSelectView(discord.ui.View):
    def __init__(self, cog, characters, interaction):
        super().__init__(timeout=180)  # View timeout after 180 seconds
        self.add_item(CharacterSelect(cog, characters, interaction))


class TWERPModal(discord.ui.Modal, title="Enter your message here"):
    def __init__(self, cog, character_name, webhook, interaction, character_info, message=None):
        super().__init__(title=f"Enter your message here")
        self.cog = cog
        self.character_name = character_name
        self.webhook = webhook
        self.interaction = interaction
        self.character_info = character_info
        self.message_content = message

        self.message = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.paragraph,
            placeholder="Enter your message here..." if not message else message,
            required=True,
            max_length=2000
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        """Send the message via the webhook when the modal is submitted."""
        try:
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
        except Exception as e:
            pass  # Silently handle benign errors


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
        guild = discord.Object(id=1098644885797609492)  # Replace with your server's ID
        self.bot.tree.copy_global_to(guild=guild)
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

    # Speak Command (combines character selection and message sending)
    @discord.app_commands.command(name="speak", description="Speak as one of your characters.")
    async def speak(self, interaction: discord.Interaction, message: str = None):
        """Speak as a character. If the user has only one character, use it directly. If they have multiple, prompt them to select."""
        try:
            characters = await self.config.user(interaction.user).characters()

            if not characters:
                await interaction.response.send_message("You don't have any characters created.", ephemeral=True)
                return

            # If the user has only one character and no message provided, open the modal immediately
            if len(characters) == 1:
                character_name = list(characters.keys())[0]
                character_info = characters[character_name]
                webhook = await self._get_webhook(interaction.channel)

                if message:
                    # If the user has only one character and provides a message, send it directly
                    async with aiohttp.ClientSession() as session:
                        combined_name = f"{character_info['name']} ({interaction.user.name})"
                        json_data = {
                            "content": message,
                            "username": combined_name,
                            "avatar_url": character_info["pfp_url"],
                            "allowed_mentions": {
                                "parse": ["users"]
                            }
                        }
                        await session.post(webhook.url, json=json_data)
                        await interaction.response.send_message(f"Message sent as `{character_name}`.", ephemeral=True)
                else:
                    # If no message provided, open the modal
                    modal = TWERPModal(self, character_name, webhook, interaction, character_info)
                    await interaction.response.send_modal(modal)

            else:
                # If multiple characters, prompt user to select one
                if message:
                    # If message is provided, open modal after selection
                    view = CharacterSelectView(self, characters, interaction)
                    await interaction.response.send_message(f"Select a character to speak as, and your message will be sent after.", view=view, ephemeral=True)
                else:
                    # If no message, just open modal after selection
                    view = CharacterSelectView(self, characters, interaction)
                    await interaction.response.send_message(f"Select a character to speak as:", view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    async def _get_webhook(self, channel: discord.TextChannel):
        """Creates or retrieves a webhook for the channel."""
        try:
            webhooks = await channel.webhooks()
            bot_webhook = discord.utils.get(webhooks, name="CharacterWebhook")

            if not bot_webhook:
                try:
                    bot_webhook = await channel.create_webhook(name="CharacterWebhook")
                except discord.Forbidden:
                    return None

            return bot_webhook
        except Exception as e:
            return None
