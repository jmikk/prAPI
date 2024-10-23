import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red

class TWERP(commands.Cog):
    """A cog that allows users to post as custom characters using webhooks"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_user(characters={})
        bot.loop.create_task(self.sync_commands())

    async def sync_commands(self):
        guild_id = YOUR_GUILD_ID  # Replace with your test server's ID
        guild = discord.Object(id=guild_id)
        await self.bot.tree.sync(guild=guild)

    # Autocomplete for character names
    async def character_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for the character names."""
        characters = await self.config.user(interaction.user).characters()
        return [
            app_commands.Choice(name=char_name, value=char_name)
            for char_name in characters.keys() if current.lower() in char_name.lower()
        ][:25]  # Limit to 25 choices

    @commands.hybrid_command(name="createcharacter")
    async def create_character(self, ctx: commands.Context, name: str, pfp_url: str):
        """Create a new character with a custom name and profile picture."""
        async with self.config.user(ctx.author).characters() as characters:
            if len(characters) >= 2:
                await ctx.send("You already have 2 characters! Delete one before creating a new one.")
                return
            
            characters[name] = {
                "pfp_url": pfp_url,
                "name": name
            }
            await ctx.send(f"Character `{name}` created with profile picture!")

    @app_commands.command(name="speakas", description="Speak as one of your characters.")
    @app_commands.autocomplete(name=character_autocomplete)
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
