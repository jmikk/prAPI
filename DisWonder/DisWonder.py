from redbot.core import commands
import asyncio
from redbot.core import commands, Config
import random
import discord
from discord.ui import Select, View


class CraftView(View):
    def __init__(self, user_items, bot, ctx, recipes):
        super().__init__()
        self.bot = bot
        self.ctx = ctx
        self.recipes = recipes
        # Add the first dropdown
        self.add_item(ItemSelect(placeholder='Choose your first item...', user_items=user_items, custom_id='first_item'))
        # Add the second dropdown
        self.add_item(ItemSelect(placeholder='Choose your second item...', user_items=user_items, custom_id='second_item'))
        self.values = []

    async def interaction_check(self, interaction):
        # Ensure that only the user who invoked the command can use the dropdowns
        return interaction.user == self.ctx.author

class ItemSelect(Select):
    def __init__(self, user_items, **kwargs):
        options = [
            discord.SelectOption(label=item, description=f"You have {count}") for item, count in user_items.items() if count > 0
        ]
        kwargs.pop('placeholder', None)
        super().__init__(placeholder='Choose an item...', min_values=1, max_values=1, options=options, **kwargs)

    async def callback(self, interaction):
        self.view.values.append(self.values[0])  # Store selected value
        if len(self.view.values) == 2:  # If both dropdowns have been used
            await interaction.response.edit_message(content="Combining your items...", view=None)
            result_message = await self.view.bot.craft_items(self.view.values, self.view.ctx.author, self.view.recipes)
            await interaction.followup.send(result_message, ephemeral=True)
        else:
            await interaction.response.send_message(f"You selected {self.values[0]}. Select another item.", ephemeral=True)



def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False

    return commands.permissions_check(predicate)


class DisWonder(commands.Cog):
    """My custom cog"""
    def __init__(self, bot):
        self.recipes = {
            ('stone', 'stone'): {'result': 'stone wall'},
        }
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

    async def embed_pager(self, items, ctx, count=10):
        # Convert dictionary items to a list of (key, value) tuples
        items_list = list(items.items())
    
        # Split items into pages
        pages = [items_list[i:i + count] for i in range(0, len(items_list), count)]
    
        # Function to create an embed from a list of items
        def get_embed(page_items, page, total_pages):
            embed = discord.Embed(title="Items", color=discord.Color.blue())
            for key, value in page_items:
                embed.add_field(name=key, value=str(value), inline=False)
            embed.set_footer(text=f"Page {page+1}/{total_pages}")
            return embed
    
        total_pages = len(pages)
        current_page = 0
    
        # Send the initial message with the first page
        message = await ctx.send(embed=get_embed(pages[current_page], current_page, total_pages))
    
        # Add reactions to the message for pagination controls
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")
    
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"]
    
        while True:
            try:
                # Wait for a reaction to be added that passes the check
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
    
                # Previous page
                if str(reaction.emoji) == "◀️" and current_page > 0:
                    current_page -= 1
                    await message.edit(embed=get_embed(pages[current_page], current_page, total_pages))
                    await message.remove_reaction(reaction, user)
    
                # Next page
                elif str(reaction.emoji) == "▶️" and current_page < total_pages - 1:
                    current_page += 1
                    await message.edit(embed=get_embed(pages[current_page], current_page, total_pages))
                    await message.remove_reaction(reaction, user)
    
                else:
                    await message.remove_reaction(reaction, user)
    
            except asyncio.TimeoutError:
                break  # End the loop if no reaction within the timeout period
    
        # Optionally clear the reactions after the timeout
        await message.clear_reactions()


    @commands.command()
    async def view_items(self, ctx, rarity="no"):
        rarity = rarity.lower()
        if rarity == "no":
            stuff = await self.config.user(ctx.author).default_items()
            await self.embed_pager(stuff, ctx)  # Use embed_pager here
        else:
            await ctx.send("Try with Basic, Common, Rare, Epic, Legendary")

    @commands.command()
    async def build(self, ctx):
        user_items = await self.config.user(ctx.author).default_items()  # Assuming this returns a dict of items and their counts
        await ctx.send("Select items to combine:", view=CraftView(user_items, self.bot, ctx, self.recipes))

    async def craft_items(self, selected_items, user):
        # Sort the items to ensure consistent order for recipe lookup
        selected_items.sort()
        item_tuple = tuple(selected_items)  # Convert to tuple for recipe lookup
    
        user_items = await self.config.user(user).default_items()  # Fetch user's current inventory
    
        if item_tuple in self.recipes:  # Check if the combination exists in the recipes
            result_item = self.recipes[item_tuple]['result']
            user_items[result_item] = user_items.get(result_item, 0) + 1  # Add the result item to inventory
    
            # Remove both ingredients used in crafting
            for item in selected_items:
                user_items[item] -= 1
                if user_items[item] <= 0:
                    del user_items[item]  # Remove the item if count falls to 0
    
            result_message = f"Success! Crafted a {result_item}."
        else:  # Crafting attempt failed due to an invalid recipe
            removed_item = random.choice(selected_items)
            user_items[removed_item] -= 1
            if user_items[removed_item] <= 0:
                del user_items[removed_item]  # Remove the item if count falls to 0
    
            result_message = f"Failed to craft. {removed_item} was lost in the process."
    
        # Save the updated inventory back to the user's config
        await self.config.user(user).default_items.set(user_items)
    
        return result_message

    
    def remove_random_ingredient(self, selected_items, user_items):
        # Randomly select one of the used ingredients to remove
        removed_item = random.choice(selected_items)
        user_items[removed_item] -= 1
        if user_items[removed_item] <= 0:
            del user_items[removed_item]
        result_message = f"Failed to craft. {removed_item} was lost in the process."
        return result_message



