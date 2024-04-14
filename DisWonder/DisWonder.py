from redbot.core import commands, Config
import discord
import random
import json
from redbot.core.data_manager import cog_data_path
import os
import asyncio

class ItemSelect(discord.ui.Select):
    def __init__(self, items):
        super().__init__(placeholder="Choose an item...", min_values=1, max_values=1, options=[
            discord.SelectOption(label=item[0], description=f"You have {items[item]} of these", value=str(item))
            for item in items if items[item] > 0
        ])

class CraftingView(discord.ui.View):
    def __init__(self, item_type, user_data, cog, ctx):
        super().__init__()
        self.cog = cog
        self.values = {}
        self.item_type = item_type

        # Determine the item type to show based on the crafting target
        tier_mapping = {
            "basic": "common",
            "common": "uncommon",
            "uncommon": "rare",
            "rare": "epic",
            "epic": "legendary"
        }
        # Get the item type to show in the select menus
        mini_item_type = tier_mapping.get(item_type, "")
        # Filter items that the user has which match the required type for crafting
        filtered_items = {k: v for k, v in user_data.items() if k.lower().endswith(mini_item_type) and v > 0}

        if filtered_items:
            self.add_item(ItemSelect(filtered_items))
            self.add_item(ItemSelect(filtered_items))
        else:
            # If no items available, inform the user and stop the view
            self.stop()

    async def on_submit(self, interaction: discord.Interaction):
        item1 = self.values.get("item1")
        item2 = self.values.get("item2")
        result = await self.process_crafting(item1, item2, interaction.user)
        await interaction.response.send_message(result, ephemeral=True)



    async def process_crafting(self, item1, item2, user):
        base_path = cog_data_path(self.cog)
        # Use the specified item type to find the right recipe file
        file_path = base_path / f"{self.item_type.lower()}_recipes.json"
        
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
        chosen_item, category = random.choice(basic_items)  # Unpack the tuple directly
    
        if tokens <= 0:  # Check if tokens are less than or equal to zero first
            await ctx.send("You must spend at least 1 token.")
            return
    
        user_data = await self.config.user(ctx.author).all()
    
        # Simplify key by using only the item name or a combination like "itemname_category"
        chosen_item_key = f"{chosen_item}_{category}"  # E.g., "Logistics_basic"
    
        # Increment the item count
        user_data[chosen_item_key] = user_data.get(chosen_item_key, 0) + 1
    
        # Save the updated data back to the user's config
        await self.config.user(ctx.author).set(user_data)
    
        # Inform the user of their purchase
        await ctx.send(f"You spent {tokens} tokens and received {tokens} unit(s) of {chosen_item}.")


    @commands.command()
    async def build(self, ctx, item_type: str):
        item_type = item_type.lower()
        user_data = await self.config.user(ctx.author).all()
        await ctx.send(user_data)
        view = CraftingView(item_type, user_data, self,ctx)
        
        if view.is_finished():
            await ctx.send("No items available to craft this type of product.")
        else:
            await ctx.send("Select two items to combine:", view=view)



    async def get_user_tokens(self, user):
        tokens_cog = self.bot.get_cog("Recruitomatic9003")
        if tokens_cog:
            return await tokens_cog.get_tokens(user)
        else:
            return 0

    @commands.command()
    async def view_inventory(self, ctx):
        """Displays the user's inventory with pagination."""
        user_data = await self.config.user(ctx.author).all()
        items = [(item, qty) for item, qty in user_data.items() if qty > 0]

        if not items:
            await ctx.send("Your inventory is empty.")
            return

        pages = self.chunk_items(items, 10)  # Split items into pages, 10 items per page
        message = await ctx.send(embed=self.create_inventory_embed(pages[0], 1, len(pages)))
        await self.add_pagination_reactions(message, len(pages))

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⏮️", "⏭️"]

        current_page = 1
        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", check=check, timeout=60.0)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break
            else:
                if str(reaction.emoji) == "⏮️" and current_page > 1:
                    current_page -= 1
                elif str(reaction.emoji) == "⏭️" and current_page < len(pages):
                    current_page += 1
                await message.edit(embed=self.create_inventory_embed(pages[current_page - 1], current_page, len(pages)))
                await message.remove_reaction(reaction, user)

    def chunk_items(self, items, items_per_page):
        """Helper function to divide the items into manageable pages."""
        return [items[i:i + items_per_page] for i in range(0, len(items), items_per_page)]

    def create_inventory_embed(self, items, page_number, total_pages):
        """Helper function to create an inventory embed."""
        embed = discord.Embed(title="Inventory", color=discord.Color.blue())
        embed.set_footer(text=f"Page {page_number} of {total_pages}")
        for item, quantity in items:
            embed.add_field(name=item, value=f"Quantity: {quantity}", inline=False)
        return embed

    async def add_pagination_reactions(self, message, num_pages):
        """Adds pagination reactions to the message if there are multiple pages."""
        if num_pages > 1:
            await message.add_reaction("⏮️")
            await message.add_reaction("⏭️")

    @commands.command()
    async def reset_user_config(self, ctx):
        """Resets the user's configuration data to default values."""
        await self.config.user(ctx.author).set(self.config.defaults["USER"])
        await ctx.send(f"Configuration data has been reset to default values for {ctx.author.name}.")


