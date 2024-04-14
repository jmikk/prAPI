from redbot.core import commands, Config
import discord
import random
import json
from redbot.core.data_manager import cog_data_path
import os

class ItemSelect(discord.ui.Select):
    def __init__(self, items):
        super().__init__(placeholder="Choose an item...", min_values=1, max_values=1, options=[
            discord.SelectOption(label=item[0], description=f"You have {items[item]} of these", value=str(item))
            for item in items if items[item] > 0
        ])

class CraftingView(discord.ui.View):
    def __init__(self, item_type, user_data, cog):
        super().__init__()
        self.cog = cog
        self.values = {}
        self.item_type = item_type
        filtered_items = {k: v for k, v in user_data.items() if k.endswith(item_type)}
        
        # Create two ItemSelect instances and add them to the view
        item_select1 = ItemSelect(filtered_items)
        item_select1.custom_id = "item1"  # Set custom_id after creation if needed
        self.add_item(item_select1)
        
        item_select2 = ItemSelect(filtered_items)
        item_select2.custom_id = "item2"  # Set custom_id after creation if needed
        self.add_item(item_select2)

    async def on_submit(self, interaction: discord.Interaction):
        item1 = self.values.get("item1")
        item2 = self.values.get("item2")
        result = await self.process_crafting(item1, item2, interaction.user)
        await interaction.response.send_message(result, ephemeral=True)


    async def process_crafting(self, item1, item2, user):
        base_path = cog_data_path(self.cog)
        file_path = base_path / f"{self.item_type}_recipes.json"
        
        try:
            with open(file_path, "r") as file:
                recipes = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            return f"Failed to load recipes: {str(e)}"
    
        # Sort and join the item names to form the key
        recipe_key = ','.join(sorted([item1, item2]))
    
        # Look up the recipe result using the sorted key
        recipe_result = recipes.get(recipe_key)
        user_data = await self.cog.config.user(user).all()
    
        if recipe_result and user_data.get(item1, 0) > 0 and user_data.get(item2, 0) > 0:
            user_data[item1] -= 1
            user_data[item2] -= 1
            user_data[recipe_result] = user_data.get(recipe_result, 0) + 1
            await self.cog.config.user(user).set(user_data)
            return f"Crafted a {recipe_result}!"
        elif recipe_result:
            return "You don't have enough items to craft this."
        else:
            removed_item = random.choice([item1, item2])
            user_data[removed_item] = max(user_data.get(removed_item, 1) - 1, 0)  # Ensure no negative counts
            await self.cog.config.user(user).set(user_data)
            return f"No recipe found. Removed one {removed_item}."




class DisWonder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="DisWonder", force_registration=True)
        default_user = {}
        self.config.register_user(**default_user)

    @commands.command()
    async def buy_basic(self, ctx, tokens=1):
        basic_items = [("Logistics", "basic"), ("Knowledge", "basic"), ("Chemicals", "basic"), ("Textiles", "basic"), ("Food", "basic"), ("Metal", "basic"), ("Wood", "basic"), ("Stone", "basic")]
        chosen_item = random.choice(basic_items)
        user_data = await self.config.user(ctx.author).all()

        if tokens > 0:
            chosen_item_key = str(chosen_item)
            user_data[chosen_item_key] = user_data.get(chosen_item_key, 0) + 1
            await self.config.user(ctx.author).set(user_data)
            await ctx.send(f"You spent {tokens} tokens and received {tokens} units of {chosen_item}.")
        else:
            await ctx.send("You must spend at least 1 token.")

    @commands.command()
    async def build(self, ctx, item_type: str):
        user_data = await self.config.user(ctx.author).all()
        view = CraftingView(item_type, user_data,self)
        await ctx.send("Select two items to combine:", view=view)



    async def get_user_tokens(self, user):
        tokens_cog = self.bot.get_cog("Recruitomatic9003")
        if tokens_cog:
            return await tokens_cog.get_tokens(user)
        else:
            return 0

