import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import aiohttp

class TWERP(commands.Cog):
    """A cog that allows users to create characters, delete them, and send messages as characters using webhooks."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=23456789648)

        self._init_config()
        self.bot.tree.add_command(self.speakas)  # Register the 'speakas' command
        self.bot.tree.add_command(self.create_character)  # Register the 'createcharacter' command
        self.bot.tree.add_command(self.delete_character)  # Register the 'deletecharacter' command
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
        """Sync the slash commands to ensure they're correctly associated with the cog."""
        guild = discord.Object(id=1098644885797609492)  # Replace with your server's ID
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

    @discord.app_commands.command(name="speakas", description="Speak as one of your characters.")
    async def speakas(self, interaction: discord.Interaction, message: str = None):
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

    @discord.app_commands.command(name="createcharacter", description="Create a character with a name and profile picture URL.")
    async def create_character(self, interaction: discord.Interaction, name: str, pfp_url: str):
        """Create a new character with a custom name and profile picture."""
        try:
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
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="deletecharacter", description="Delete one of your characters.")
    async def delete_character(self, interaction: discord.Interaction, name: str):
        """Delete one of your characters."""
        try:
            characters = await self.config.user(interaction.user).characters()

            if name not in characters:
                await interaction.response.send_message(f"Character `{name}` not found.", ephemeral=True)
                return

            del characters[name]
            await self.config.user(interaction.user).characters.set(characters)
            await interaction.response.send_message(f"Character `{name}` deleted.", ephemeral=True)
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
