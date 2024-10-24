import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import aiohttp

NPC_ROLE_NAME = "NPC"  # Change this if needed


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

    def _init_config(self):
        self.config.register_guild(allowed_channels=[], npc_characters={})
        self.config.register_user(credits=0, completed_personal_projects={}, characters={})

    async def cog_load(self):
        await self.bot.tree.sync()  # Sync commands globally
        
        # Send a message to a specific channel
        channel = self.bot.get_channel(1098673276064120842)  # Channel ID to send message to
        if channel:
            await channel.send(f"Commands synced.")
        else:
            print("Channel not found. Cannot send sync message.")
    
    async def has_npc_role(self, interaction: discord.Interaction):
        npc_role = discord.utils.get(interaction.guild.roles, name=NPC_ROLE_NAME)
        return npc_role in interaction.user.roles if npc_role else False


    @discord.app_commands.command(name="createnpc", description="Create an NPC with a name and profile picture URL.")
    async def create_npc(self, interaction: discord.Interaction, name: str, pfp_url: str):
        """Create a new NPC with a custom name and profile picture."""
        if not await self.has_npc_role(interaction):
            await interaction.response.send_message("You don't have permission to create NPCs.", ephemeral=True)
            return

        npc_characters = await self.config.guild(interaction.guild).npc_characters()

        if name in npc_characters:
            await interaction.response.send_message(f"An NPC named `{name}` already exists.", ephemeral=True)
            return

        npc_characters[name] = {"pfp_url": pfp_url, "name": name}
        await self.config.guild(interaction.guild).npc_characters.set(npc_characters)
        await interaction.response.send_message(f"NPC `{name}` created with profile picture!", ephemeral=True)

    @discord.app_commands.command(name="listnpc", description="List all NPCs.")
    async def list_npcs(self, interaction: discord.Interaction):
        """List all NPCs in the guild."""
        if not await self.has_npc_role(interaction):
            await interaction.response.send_message("You don't have permission to list NPCs.", ephemeral=True)
            return

        npc_characters = await self.config.guild(interaction.guild).npc_characters()

        if not npc_characters:
            await interaction.response.send_message("No NPCs found.", ephemeral=True)
            return

        npc_list = "\n".join([f"- {npc}" for npc in npc_characters])
        await interaction.response.send_message(f"NPCs in this server:\n{npc_list}", ephemeral=True)
    # Speak as NPC Slash Command with Autocomplete
    @discord.app_commands.command(name="speaknpc", description="Speak as one of the NPCs.")
    async def speak_npc(self, interaction: discord.Interaction, name: str, message: str):
        """Speak as an NPC."""
        if not await self.has_npc_role(interaction):
            await interaction.response.send_message("You don't have permission to speak as an NPC.", ephemeral=True)
            return
    
        npc_characters = await self.config.guild(interaction.guild).npc_characters()
    
        if name not in npc_characters:
            await interaction.response.send_message(f"NPC `{name}` not found.", ephemeral=True)
            return
    
        character_info = npc_characters[name]
        webhook = await self._get_webhook(interaction.channel)
    
        if webhook:
            await self.send_as_npc(interaction, character_info, message, webhook)
        else:
            await interaction.response.send_message("Failed to retrieve or create a webhook.", ephemeral=True)


        # Attach the autocomplete function to the 'name' parameter
    @speak_npc.autocomplete("name")
    async def npc_name_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete function to provide NPC names for speakNPC."""
        npc_characters = await self.config.guild(interaction.guild).npc_characters()
        return [
            discord.app_commands.Choice(name=npc_name, value=npc_name)
            for npc_name in npc_characters if current.lower() in npc_name.lower()
        ]
    
    async def send_as_npc(self, interaction, character_info, message, webhook):
        """Helper function to send a message as an NPC using the webhook."""
        try:
            async with aiohttp.ClientSession() as session:
                webhook_url = webhook.url
                json_data = {
                    "content": message,
                    "username": character_info["name"],
                    "avatar_url": character_info["pfp_url"],
                    "allowed_mentions": {
                        "parse": ["users"]  # Prevent @everyone and @here pings
                    }
                }
                await session.post(webhook_url, json=json_data)
    
            await interaction.response.send_message(f"Message sent as `{character_info['name']}`!", ephemeral=True)
    
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    async def _get_webhook(self, channel: discord.TextChannel):
        """Creates or retrieves a webhook for the channel."""
        try:
            webhooks = await channel.webhooks()
            bot_webhook = discord.utils.get(webhooks, name="CharacterWebhook")

            if not bot_webhook:
                bot_webhook = await channel.create_webhook(name="CharacterWebhook")

            return bot_webhook
        except discord.Forbidden:
            return None
        except Exception as e:
            print(f"Failed to create webhook: {e}")
            return None

    # Attach the autocomplete function to the 'name' parameter
    @delete_character.autocomplete("name")
    async def character_name_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete function to provide character names for deletion."""
        characters = await self.config.user(interaction.user).characters()
        return [
            discord.app_commands.Choice(name=char_name, value=char_name)
            for char_name in characters.keys() if current.lower() in char_name.lower()
        ]

    @discord.app_commands.command(name="createcharacter", description="Create a character with a name and profile picture URL.")
    async def create_character(self, interaction: discord.Interaction, name: str, pfp_url: str):
        """Create a new character with a custom name and profile picture."""
        characters = await self.config.user(interaction.user).characters()

        if len(characters) >= 2:
            await interaction.response.send_message("You already have 2 characters! Delete one before creating a new one.", ephemeral=True)
            return

        characters[name] = {"pfp_url": pfp_url, "name": name}
        await self.config.user(interaction.user).characters.set(characters)
        await interaction.response.send_message(f"Character `{name}` created with profile picture!", ephemeral=True)

    # Delete Character Slash Command with Autocomplete
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


    @discord.app_commands.command(name="speak", description="Show a dropdown to select a character.")
    async def select_character(self, interaction: discord.Interaction, message: str = None):
        """Show a dropdown to select a character, or if only one character, skip to modal or directly post."""
        characters = await self.config.user(interaction.user).characters()

        if not characters:
            await interaction.response.send_message("You don't have any characters created.", ephemeral=True)
            return

        if len(characters) == 1:
            character_name = list(characters.keys())[0]
            character_info = characters[character_name]

            if message:
                webhook = await self._get_webhook(interaction.channel)
                if webhook:
                    await self.send_as_character(interaction, character_name, character_info, message, webhook)
                return

            webhook = await self._get_webhook(interaction.channel)
            if webhook:
                modal = TWERPModal(self, character_name, webhook, interaction, character_info)
                await interaction.response.send_modal(modal)
            return

        view = CharacterSelectView(self, characters, interaction)
        await interaction.response.send_message("Select a character to speak as:", view=view, ephemeral=True)

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
                        "parse": ["users"]
                    }
                }
                await session.post(webhook_url, json=json_data)

            await interaction.response.send_message(f"Message sent as `{character_name}`!", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
