from redbot.core import commands, Config
import discord
import random
import json
from redbot.core.data_manager import cog_data_path
import os
import asyncio



class CraftButton(discord.ui.Button):
    def __init__(self, label, quantity, ctx):
        super().__init__(label=label, style=discord.ButtonStyle.green)
        self.invoker = ctx.author
        self.quantity = quantity  # The quantity to craft when this button is pressed

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.invoker:
            await interaction.response.send_message("You are not authorized to use these buttons.", ephemeral=True)
            return
        try:
            view = self.view  # Access the view to which this button belongs
    
            # Ensure that the necessary items have been selected
            item1 = view.values.get("item1")
            item2 = view.values.get("item2")
            if not item1 or not item2:
                await interaction.response.send_message("Please select two items to craft.", ephemeral=True)
                return
            
            # Start the crafting process
            result = await view.process_crafting(item1, item2, interaction.user, self.quantity)

            for item in self.view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            
            # Since this is likely the first response, use `interaction.response.edit_message`
            await interaction.response.edit_message(content=result, view=view)

        except Exception as e:
            # Properly handle the exception by using interaction.response or followup based on the state
            if interaction.response.is_done():
                await interaction.followup.send_message(str(e), ephemeral=True)
            else:
                await interaction.response.send_message(str(e), ephemeral=True)



class ItemSelect(discord.ui.Select):
    def __init__(self, items, ctx, placeholder="Choose an item...", custom_id=None):
        options = [
            discord.SelectOption(label=item.split("_")[0], description=f"You have {items[item]} of these", value=item)
            for item in items if items[item] > 0
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id=custom_id)
        self.invoker = ctx.author

    async def callback(self, interaction: discord.Interaction):
        # Save the selection to the view's state
        if interaction.user != self.invoker:
            await interaction.response.send_message("You are not authorized to use these buttons.", ephemeral=True)
            return
        self.view.values[self.custom_id] = self.values[0]
        await interaction.response.send_message(f"You selected: {self.values[0].split('_')[0]}", ephemeral=True)

class CraftingView(discord.ui.View):
    def __init__(self, item_type, user_data, cog, ctx):
        super().__init__()
        self.cog = cog
        self.ctx = ctx
        self.values = {}  # Stores selected items
        self.item_type = item_type
        self.user_data = user_data

        tier_mapping = {
            "common": "basic",
            "rare": "common",
            "epic": "rare",
            "legendary": "epic",
            "legendary": "mythic",
        }
        mini_item_type = tier_mapping.get(item_type, "")
        self.rarity = mini_item_type
        filtered_items = {k: v for k, v in user_data.items() if k.lower().endswith(mini_item_type) and v > 0}

        if filtered_items:
            self.add_item(ItemSelect(filtered_items, custom_id="item1",ctx=ctx))
            self.add_item(ItemSelect(filtered_items, custom_id="item2",ctx=ctx))
            #self.add_item(CraftButton())  # Add the craft button to the view
            self.add_item(CraftButton(label='Craft 1', quantity=1, ctx=ctx))
            self.add_item(CraftButton(label='Craft 2', quantity=2, ctx=ctx))
            self.add_item(CraftButton(label='Craft 4', quantity=4, ctx=ctx))
            self.add_item(CraftButton(label='Craft 6', quantity=6, ctx=ctx))
            self.add_item(CraftButton(label='Craft 10', quantity=10, ctx=ctx))
            self.add_item(CraftButton(label='Craft Max', quantity='max', ctx=ctx))
        else:
            asyncio.create_task(ctx.send("No items available to craft this type of product."))


    async def callback(self, interaction: discord.Interaction):
        item1 = self.values.get("item1")
        item2 = self.values.get("item2")
        result = await self.process_crafting(item1, item2, interaction.user, self.rarity)
        await interaction.response.send_message(result, ephemeral=True)

    async def process_crafting(self, item1, item2, user, quantity):
        rarity = item1.split("_")[1]
        if item1 == item2:
            return f"Sorry you can't make super {item1.split('_')[0]} by combining two of them together,"
        if rarity == "basic":
            recipes = await self.cog.config.common()
        if rarity == "mythic":
            recipes = await self.cog.config.mythic()        
        if rarity == "common":
            recipes = await self.cog.config.rare()
        if rarity == "rare":
            recipes = await self.cog.config.epic()
        if rarity == "epic":
            recipes = await self.cog.config.legendary()
        
        recipe_key = ','.join(sorted([item1.split("_")[0].lower(), item2.split("_")[0].lower()]))
        recipe_result = recipes.get(recipe_key)
        if recipe_result:
            available_item1 = self.user_data.get(item1, 0)
            available_item2 = self.user_data.get(item2, 0)
    
            # Calculate maximum if quantity is 'max'
            if quantity == 'max':
                quantity = min(available_item1, available_item2)
    
            if available_item1 >= quantity and available_item2 >= quantity:
                self.user_data[item1] -= quantity
                self.user_data[item2] -= quantity
                self.user_data[recipe_result] = self.user_data.get(recipe_result, 0) + quantity
                await self.cog.config.user(user).set(self.user_data)
                return f"Crafted {quantity} of {recipe_result}!"
            else:
                return f"You do not have enough items to craft {quantity}."
        else:
            return "No valid recipe found."







class DisWonder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="DisWonder", force_registration=True)
        default_user = {}
        self.config.register_user(**default_user)
        default_global = {
            "common": {},
            "rare":{},
            "epic":{},
            "legendary":{},
            "mythic":{}
        }
        self.config.register_global(**default_global)

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
    async def view_inventory(self, ctx, rarity: str = None):
        """Displays the user's inventory with pagination, optionally filtered by item rarity."""
        user_data = await self.config.user(ctx.author).all()
        items = [(item, qty) for item, qty in user_data.items() if qty > 0]
    
        if rarity:
            items = [(item, qty) for item, qty in items if item.lower().startswith(rarity.lower())]
            if not items:
                await ctx.send(f"No items of rarity '{rarity}' found in your inventory.")
                return
    
        if not items:
            await ctx.send("Your inventory is empty.")
            return
    
        pages = self.chunk_items(items, 10)  # Split items into pages, 10 items per page
        message = await ctx.send(embed=self.create_inventory_embed(pages[0], 1, len(pages), rarity))
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
                await message.edit(embed=self.create_inventory_embed(pages[current_page - 1], current_page, len(pages), rarity))
                await message.remove_reaction(reaction, user)


    def chunk_items(self, items, items_per_page):
        """Helper function to divide the items into manageable pages."""
        return [items[i:i + items_per_page] for i in range(0, len(items), items_per_page)]

    def create_inventory_embed(self, items, page_number, total_pages, rarity=None):
        """Helper function to create an inventory embed."""
        total_points = sum(point_values.get(item.split('_')[0].lower(), 0) * qty for item, qty in items)
        title = "Inventory" if not rarity else f"Inventory - {rarity.title()} Items"
        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.set_footer(text=f"Page {page_number} of {total_pages} - Total Points: {total_points}")
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

    @commands.command(name="loadrecipes")
    async def load_recipes(self, ctx, rarity):
        """Loads recipes from an attached JSON file into the bot's global config."""
        if not ctx.message.attachments:
            await ctx.send("Please attach a JSON file with the recipes.")
            return

        attachment = ctx.message.attachments[0]  # Get the first attachment
        if not attachment.filename.endswith('.json'):
            await ctx.send("Please make sure the file is a JSON file.")
            return

        try:
            # Download the attachment
            file_content = await attachment.read()
            # Load JSON data from the file content
            data = json.loads(file_content.decode('utf-8'))  # decode bytes to string
            # Set the data into the global config
            if rarity == "common":
                await self.config.common.set(data)
            if rarity == "mythic":
                await self.config.mythic.set(data)
            if rarity == "epic":
                await self.config.epic.set(data)
            if rarity == "legendary":
                await self.config.legendary.set(data)

            await ctx.send("Recipes successfully updated globally.")
        except json.JSONDecodeError:
            await ctx.send("The provided file contains invalid JSON.")
        except Exception as e:
            await ctx.send(f"Failed to load recipes: {str(e)}")

    @commands.command()
    async def view_recipes(self,ctx,rarity):
        if rarity == "common":
            recipes = await self.config.common()
        if rarity == "mythic":
            recipes = await self.config.mythic()        
        if rarity == "rare":
            recipes = await self.config.rare()
        if rarity == "epic":
            recipes = await self.config.epic()
        if rarity == "legendary":
            recipes = await self.config.legendary()
        await ctx.send(recipes)
