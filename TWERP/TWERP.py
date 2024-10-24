import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import aiohttp


class CharacterSelectView(discord.ui.View):
    def __init__(self, cog, characters, interaction):
        super().__init__(timeout=180)  # View timeout after 180 seconds
        self.add_item(CharacterSelect(cog, characters, interaction))


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


class TWERPModal(discord.ui.Modal, title="Enter your message here"):
    def __init__(self, cog, character_name, webhook, interaction, character_info):
        super().__init__(title=f"Enter your message here")
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
            await interaction.response.defer()  # Close the modal
        except discord.errors.InteractionResponded:
            pass
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)


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

        guild_id = 1098644885797609492  # Replace with your guild ID
        
        # Step 1: Clear old guild-specific commands
        await self.clear_guild_commands(guild_id)
        
        # Step 2: Sync global commands
        await self.bot.tree.sync()  # Sync globally now that the guild-specific commands are cleared
        print("Synced commands globally.")

    async def clear_guild_commands(self, guild_id: int):
        """Clears commands from a specific guild."""
        guild = discord.Object(id=guild_id)
        await self.bot.tree.sync(guild=guild)  # Syncing an empty list of commands to clear them
        print(f"Cleared commands for guild: {guild_id}")
            # Autocomplete Function for Character Names
        async def character_name_autocomplete(self, interaction: discord.Interaction, current: str):
            """Autocomplete function to provide character names for deletion."""
            characters = await self.config.user(interaction.user).characters()
            if not characters:
                return []
            
            # Return matching character names based on the user's input (current)
            return [
                discord.app_commands.Choice(name=char_name, value=char_name)
                for char_name in characters.keys() if current.lower() in char_name.lower()
            ]

    # Create Character Slash Command
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
            await interaction.response.send_message(f"Character {name} created with profile picture!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    # Delete Character Slash Command
    @discord.app_commands.command(name="deletecharacter", description="Delete one of your characters.")
    @discord.app_commands.autocomplete(name=character_name_autocomplete)
    async def delete_character(self, interaction: discord.Interaction, name: str):
        """Delete one of your characters."""
        try:
            characters = await self.config.user(interaction.user).characters()

            if name not in characters:
                await interaction.response.send_message(f"Character {name} not found.", ephemeral=True)
                return

            del characters[name]
            await self.config.user(interaction.user).characters.set(characters)
            await interaction.response.send_message(f"Character {name} deleted.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    # Select Character Slash Command
    @discord.app_commands.command(name="speak", description="Show a dropdown to select a character.")
    async def select_character(self, interaction: discord.Interaction, message: str = None):
        """Show a dropdown to select a character, or if only one character, skip to modal or directly post."""
        try:
            characters = await self.config.user(interaction.user).characters()

            # No characters found
            if not characters:
                await interaction.response.send_message("You don't have any characters created.", ephemeral=True)
                return

            # If the user has only one character
            if len(characters) == 1:
                character_name = list(characters.keys())[0]
                character_info = characters[character_name]

                # If the user provided a message, skip the modal and send it directly
                if message:
                    webhook = await self._get_webhook(interaction.channel)
                    if webhook:
                        await self.send_as_character(interaction, character_name, character_info, message, webhook)
                        return

                # Otherwise, open the modal for them to enter a message
                webhook = await self._get_webhook(interaction.channel)
                if webhook:
                    modal = TWERPModal(self, character_name, webhook, interaction, character_info)
                    await interaction.response.send_modal(modal)
                return

            # If more than one character, show the dropdown to select a character
            view = CharacterSelectView(self, characters, interaction)
            await interaction.response.send_message("Select a character to speak as:", view=view, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    async def send_as_character(self, interaction, character_name, character_info, message, webhook):
        """Helper function to send a message as a character using the webhook."""
        try:
            async with aiohttp.ClientSession() as session:
                webhook_url = webhook.url
                combined_name = f"{character_info['name']} ({interaction.user.name})"
                json_data = {
                    "content": message,
                    "username": combined_name,
                    "avatar_url": character_info["pfp_url"],
                    "allowed_mentions": {
                        "parse": ["users"]  # Prevent @everyone and @here pings
                    }
                }
                await session.post(webhook_url, json=json_data)
    
            # Properly acknowledge the interaction to prevent the "thinking" state
            await interaction.response.send_message(f"Message sent as {character_name}!", ephemeral=True)
    
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
