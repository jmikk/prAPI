from redbot.core import commands
import asyncio
from redbot.core import commands, Config
import random


def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False

    return commands.permissions_check(predicate)


class DisWonder(commands.Cog):
    """My custom cog"""
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890,force_registration=True)
                # Define the default items structure

        # Define default user settings structure
        default_user = {
            "default_items": {
                "Logistics": 0,
                "Knowledge": 0,
                "Chemicals": 0,
                "Textiles": 0,
                "Food": 0,
                "Metal": 0,
                "Wood": 0,
                "Stone": 0
                # Add the rest of your items here...
            }
    }        
        self.default_items = {
            
        }
        self.config.register_user(**default_user)

    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    # great once your done messing with the bot.
    #   async def cog_command_error(self, ctx, error):
    #       await ctx.send(" ".join(error.args))

    @commands.command()
    @commands.is_owner()
    async def myCom1(self, ctx):
        recruitomatic_cog = self.bot.get_cog("Recruitomatic9003")
        if recruitomatic_cog is None:
            await ctx.send("Recruitomatic9003 cog is not loaded.")
            return

        # Access the config from the other cog
        user_settings = await recruitomatic_cog.config.user(ctx.author).all()
        guild_settings = await recruitomatic_cog.config.guild(ctx.guild).all()

        # Send the fetched data
        await ctx.send("I work")
        await ctx.send(f"User Settings: {user_settings}")
        await ctx.send(f"Guild Settings: {guild_settings}")

    async def ensure_user_items(self, user):
        # Try to get the user's items; if not set, this will be None
        user_items = await self.config.user(user).default_items()

        if user_items is None:
            # If user_items doesn't exist, initialize it with default_items
            await self.config.user(user).default_items.set(self.default_items)
            
    @commands.command()
    async def buy_random(self, ctx, tokens: int):
        # Ensure the user has the items initialized in their config
        await self.ensure_user_items(ctx.author)

        # Now proceed with your command, knowing the user has the items dictionary initialized
        user_items = await self.config.user(ctx.author).default_items()
        await ctx.send(user_items)

        # Example logic for modifying item quantities
        if tokens > 0:
            # Select a random item to increment
            random_item = random.choice(list(user_items.keys()))
            user_items[random_item] += tokens  # Increment by the number of tokens spent

            # Save the updated items back to the user's config
            await ctx.send(f"You spent {tokens} tokens and received {tokens} units of {random_item}.")
        else:
            await ctx.send("You must spend at least 1 token.")

    def emed_pager(message,ctx,count=10):
        return message

    @commands.command()
    async def view_items(self,ctx,rarity="no"):
        rarity = rarity.lower()
        if rarity == "no":
            stuff = await self.config.user(ctx.author).default_items.set(user_items)
            emed_pager(stuff,ctx) 
            return
        else:
            await ctx.send("Try with Basic, Common, Rare, Epic, Legendary"

