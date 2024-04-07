from redbot.core import commands, Config
import random
import discord
from discord.ui import Select, View

class CraftView(View):
    def __init__(self, user_items, bot, ctx, recipes, parent_cog):
        super().__init__()
        self.bot = bot
        self.ctx = ctx
        self.recipes = recipes
        self.parent_cog = parent_cog  # Store the DisWonder instance

        # Add the dropdowns and pass the parent_cog to ItemSelect
        self.add_item(ItemSelect('Choose your first item...', user_items, self.parent_cog, 'first_item'))
        self.add_item(ItemSelect('Choose your second item...', user_items, self.parent_cog, 'second_item'))
        self.values = []

    async def interaction_check(self, interaction):
        # Ensure that only the user who invoked the command can use the dropdowns
        return interaction.user == self.ctx.author

class ItemSelect(Select):
    def __init__(self, placeholder, user_items, parent_cog, custom_id):
        self.parent_cog = parent_cog  # Store the DisWonder instance
        options = [
            discord.SelectOption(label=item, description=f"You have {count}") for item, count in user_items.items() if count > 0
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id=custom_id)

    async def callback(self, interaction):
        self.view.values.append(self.values[0])  # Store selected value
        if len(self.view.values) == 2:
            await interaction.response.edit_message(content="Combining your items...", view=None)
            # Use parent_cog to call craft_items
            result_message = await self.parent_cog.craft_items(self.view.values, self.view.ctx.author)
            await interaction.followup.send(result_message, ephemeral=True)
        else:
            await interaction.response.send_message(f"You selected {self.values[0]}. Select another item.", ephemeral=True)

class DisWonder(commands.Cog):
    """My custom cog"""
    def __init__(self, bot):
        self.recipes = {
            ('stone', 'stone'): {'result': 'stone wall'},
        }
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

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
            }
        }
        self.config.register_user(**default_user)

    @commands.command()
    async def build(self, ctx):
        user_items = await self.config.user(ctx.author).default_items()  # Fetch user's items
        await ctx.send("Select items to combine:", view=CraftView(user_items, self.bot, ctx, self.recipes, self))

    async def craft_items(self, selected_items, user):
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

    # Other methods and commands as previously defined...
    
    def remove_random_ingredient(self, selected_items, user_items):
        # Randomly select one of the used ingredients to remove
        removed_item = random.choice(selected_items)
        user_items[removed_item] -= 1
        if user_items[removed_item] <= 0:
            del user_items[removed_item]
        result_message = f"Failed to craft. {removed_item} was lost in the process."
        return result_message



