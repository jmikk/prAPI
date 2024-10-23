import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
import aiohttp


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
        # Check and register new fields for guild-level config
        if not hasattr(self.config.GUILD, "allowed_channels"):
            self.config.register_guild(allowed_channels=[])

        # Check and register new fields for user-level config
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

        # Fetch the allowed channels for this guild
        allowed_channels = await self.config.guild(message.guild).allowed_channels()
        if message.channel.id not in allowed_channels:
            return  # Ignore if not in an allowed channel

        # Calculate word count and give credits accordingly
        word_count = len(message.content.split())
        if word_count >= 10:
            credits_to_add = word_count // 10
            async with self.config.user(message.author).credits() as credits:
                credits += credits_to_add
            await message.channel.send(f"{message.author.mention} earned {credits_to_add} credits!")

    @commands.hybrid_command(name="createcharacter")
    async def create_character(self, ctx: commands.Context, name: str, pfp_url: str):
        """Create a new character with a custom name and profile picture."""
        # Fetch the user's character list, or initialize it if it's None
        characters = await self.config.user(ctx.author).characters()
        
        if characters is None:
            characters = {}  # Initialize as an empty dictionary if it doesn't exist
    
        if len(characters) >= 2:
            await ctx.send("You already have 2 characters! Delete one before creating a new one.")
            return
    
        # Add the new character
        characters[name] = {
            "pfp_url": pfp_url,
            "name": name
        }
    
        # Save the updated characters list
        await self.config.user(ctx.author).characters.set(characters)
    
        await ctx.send(f"Character `{name}` created with profile picture!")



    @app_commands.command(name="speakas", description="Speak as one of your characters.")
    async def speak_as(self, interaction: discord.Interaction, name: str, message: str):
        """Speak as one of your characters."""
        characters = await self.config.user(interaction.user).characters()
        if name not in characters:
            await interaction.response.send_message(f"Character `{name}` not found.", ephemeral=True)
            return

        # Set up webhook to send the message as the character
        character = characters[name]
        webhook = await self._get_webhook(interaction.channel)
        if webhook:
            async with aiohttp.ClientSession() as session:
                webhook_url = webhook.url
                json_data = {
                    "content": message,
                    "username": character["name"],
                    "avatar_url": character["pfp_url"]
                }
                await session.post(webhook_url, json=json_data)
                await interaction.response.send_message(f"Message sent as `{name}`!", ephemeral=True)

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

    # Admin command to set allowed channels
    @commands.admin_or_permissions(manage_channels=True)
    @commands.hybrid_command(name="setallowedchannel")
    async def set_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set a channel where users can earn credits for speaking."""
        async with self.config.guild(ctx.guild).allowed_channels() as allowed_channels:
            if channel.id not in allowed_channels:
                allowed_channels.append(channel.id)
                await ctx.send(f"Channel {channel.mention} is now set to allow earning credits.")
            else:
                await ctx.send(f"Channel {channel.mention} is already set to allow earning credits.")

    @commands.admin_or_permissions(manage_channels=True)
    @commands.hybrid_command(name="removeallowedchannel")
    async def remove_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Remove a channel from the list of allowed credit-earning channels."""
        async with self.config.guild(ctx.guild).allowed_channels() as allowed_channels:
            if channel.id in allowed_channels:
                allowed_channels.remove(channel.id)
                await ctx.send(f"Channel {channel.mention} removed from earning credits.")
            else:
                await ctx.send(f"Channel {channel.mention} is not set to allow earning credits.")
