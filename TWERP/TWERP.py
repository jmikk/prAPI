import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
import aiohttp

class TWERP(commands.Cog):
    """A cog that allows users to post as custom characters using webhooks"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)  # Unique ID for your cog
        self.config.register_user(characters={})  # Stores user characters

    @commands.hybrid_command(name="createcharacter")
    @app_commands.describe(name="The name of your character", pfp_url="URL to the character's profile picture")
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

    @commands.hybrid_command(name="deletecharacter")
    @app_commands.describe(name="The name of the character to delete")
    async def delete_character(self, ctx: commands.Context, name: str):
        """Delete one of your characters."""
        async with self.config.user(ctx.author).characters() as characters:
            if name in characters:
                del characters[name]
                await ctx.send(f"Character `{name}` deleted.")
            else:
                await ctx.send(f"Character `{name}` not found.")

    @commands.hybrid_command(name="characters")
    async def list_characters(self, ctx: commands.Context):
        """List your characters."""
        characters = await self.config.user(ctx.author).characters()
        if not characters:
            await ctx.send("You don't have any characters yet.")
            return
        
        character_list = "\n".join([f"{char['name']}" for char in characters.values()])
        await ctx.send(f"Your characters:\n{character_list}")

    @commands.hybrid_command(name="speakas")
    @app_commands.describe(name="The name of your character", message="The message you want to send as the character")
    async def speak_as(self, ctx: commands.Context, name: str, *, message: str):
        """Speak as one of your characters."""
        characters = await self.config.user(ctx.author).characters()
        if name not in characters:
            await ctx.send(f"Character `{name}` not found.")
            return
        
        # Set up webhook to send the message as the character
        character = characters[name]
        webhook = await self._get_webhook(ctx)
        if webhook:
            async with aiohttp.ClientSession() as session:
                webhook_url = webhook.url
                json_data = {
                    "content": message,
                    "username": character["name"],
                    "avatar_url": character["pfp_url"]
                }
                await session.post(webhook_url, json=json_data)

    async def _get_webhook(self, ctx):
        """Creates or retrieves a webhook for the channel."""
        webhooks = await ctx.channel.webhooks()
        bot_webhook = discord.utils.get(webhooks, name="CharacterWebhook")

        if not bot_webhook:
            try:
                bot_webhook = await ctx.channel.create_webhook(name="CharacterWebhook")
            except discord.Forbidden:
                await ctx.send("I don't have permission to create a webhook.")
                return None

        return bot_webhook
