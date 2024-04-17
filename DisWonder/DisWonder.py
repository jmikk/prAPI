from redbot.core import commands, Config
import discord
import random
import json
from redbot.core.data_manager import cog_data_path
import os
import asyncio
import datetime




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
        repMod = 1
        if item1 == item2:
            return f"Sorry you can't make super {item1.split('_')[0]} by combining two of them together,"
        if rarity == "basic":
            repMod = 2
            recipes = await self.cog.config.common()
        if rarity == "legendary":
            repMod = 32
            recipes = await self.cog.config.mythic()        
        if rarity == "common":
            repMod = 4
            recipes = await self.cog.config.rare()
        if rarity == "rare":
            repMod = 8
            recipes = await self.cog.config.epic()
        if rarity == "epic":
            repMod = 16
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
                #return f"Crafted {quantity} of {recipe_result.replace('_', ' ').capitalize()}!"
                return f"Crafted {quantity} of {recipe_result.capitalize()}!"

            else:
                return f"You do not have enough items to craft {quantity}."
        else:
            available_item1 = self.user_data.get(item1, 0)
            available_item2 = self.user_data.get(item2, 0)
    
                # Calculate maximum if quantity is 'max'
            if quantity == 'max':
                quantity = min(available_item1, available_item2)
                    
            if available_item1 >= quantity and available_item2 >= quantity:
    
                self.user_data[item1] -= quantity
                self.user_data[item2] -= quantity
                trashed = self.user_data.get("trash_trash", 0) + quantity * repMod
                self.user_data["trash_trash"] = trashed
                await self.cog.config.user(user).set(self.user_data)
                await self.cog.config.user(user).set(self.user_data)
                return f"No vaild recipe found but you did make a nice pile of {trashed} trash!"
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
            "mythic":{},
            "trash":{}
        }
        default_guild = {
            "last_claimed": datetime.datetime.utcnow().isoformat(),
            "multiplier": 1.0
        }
        self.config.register_guild(**default_guild)
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
        #await ctx.send(f"You spent {tokens} tokens and received {tokens} unit(s) of {chosen_item}.")
        await ctx.send(f"You received 1 unit of {chosen_item}.")


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
    async def DisWonder_leaderboard(self, ctx):
        """Displays a leaderboard of user points in the server."""
        members = ctx.guild.members  # Get list of members in the guild
        user_points = []

        point_values = {
        'trash': -1,
        'basic': 1,
        'common': 3,
        'rare': 18,
        'epic': 162,
        'legendary': 1944,
        'mythic': 29160
    }
    
        # Loop through each member and get their points
        for member in members:
            if not member.bot:  # Skip bots
                user_data = await self.config.user(member).all()
                items = [(item, qty) for item, qty in user_data.items() if qty > 0]
                points = sum(point_values.get(item.split('_')[1].lower(), 0) * qty for item, qty in items)
                if points == 0:
                    continue
                user_points.append((member.display_name, points))
    
        # Sort the list by points in descending order
        user_points.sort(key=lambda x: x[1], reverse=True)
    
        # Chunk the sorted user points list into pages, 10 users per page
        pages = self.chunk_items(user_points, 10)
    
        # Send the first page and add reactions for pagination
        if pages:
            message = await ctx.send(embed=self.create_leaderboard_embed(pages[0], 1, len(pages)))
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
                    await message.edit(embed=self.create_leaderboard_embed(pages[current_page - 1], current_page, len(pages)))
                    await message.remove_reaction(reaction, user)
        else:
            await ctx.send("No points data available to display.")
    
    def create_leaderboard_embed(self, user_points, page_number, total_pages):
        """Helper function to create an embed for the leaderboard page."""
        embed = discord.Embed(title="Leaderboard", color=discord.Color.gold())
        embed.set_footer(text=f"Page {page_number} of {total_pages}")
        for name, points in user_points:
            embed.add_field(name=name, value=f"Points: {points}", inline=False)
        return embed


    @commands.command()
    async def view_inventory(self, ctx, rarity: str = None):
        """Displays the user's inventory with pagination, optionally filtered by item rarity."""
        if not rarity:
            await ctx.send("You can also specifiy a rarity to just search for those items")
            
        user_data = await self.config.user(ctx.author).all()
        items = [(item, qty) for item, qty in user_data.items() if qty > 0]
    
        if rarity:
            items = [(item, qty) for item, qty in items if item.lower().endswith(rarity.lower())]
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

        point_values = {
        'trash': -1,
        'basic': 1,
        'common': 3,
        'rare': 18,
        'epic': 162,
        'legendary': 1944,
        'mythic': 29160
    }

        total_points = sum(point_values.get(item.split('_')[1].lower(), 0) * qty for item, qty in items)
        title = "Inventory" if not rarity else f"Inventory - {rarity.title()} Items"
        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.set_footer(text=f"Page {page_number} of {total_pages} - Total Points: {total_points}")
        for item, quantity in items:
            embed.add_field(name=item.replace("_",": ").capitalize(), value=f"Quantity: {quantity}", inline=False)
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
            if rarity == "rare":
                await self.config.rare.set(data)

            await ctx.send("Recipes successfully updated globally.")
        except json.JSONDecodeError:
            await ctx.send("The provided file contains invalid JSON.")
        except Exception as e:
            await ctx.send(f"Failed to load recipes: {str(e)}")
        
    @commands.command()
    async def throw_trash(self, ctx, trash_amount: int, target: discord.Member = None):
        # Fetch the user data safely
        user_data = await self.config.user(ctx.author).all()
        current_trash = user_data.get("trash_trash", 0)  # Default to 0 if not set
    
        # Check if the user has enough trash to throw
        if current_trash < trash_amount:
            await ctx.send("You don't have that much trash to throw!")
            return
    
        # Deduct the trash from the sender
        user_data["trash_trash"] = current_trash - trash_amount
        await self.config.user(ctx.author).set(user_data)
    
        # If a target is specified, add trash to their total
        if target:
            target_data = await self.config.user(target).all()
            target_trash = target_data.get("trash_trash", 0)
            target_data["trash_trash"] = target_trash + trash_amount
            await self.config.user(target).set(target_data)
    
        # Send a confirmation message
        if target:
            await ctx.send(f"You threw {trash_amount} trash at {target.display_name}!")
        else:
            await ctx.send(f"You threw away {trash_amount} trash!")

    @commands.command(name="grab")
    @commands.cooldown(1, 600, commands.BucketType.guild)  # Cooldown of 1 hour per guild
    async def grab(self, ctx):
        """Steal the pot."""
        valid_resources = ["logistics", "knowledge", "chemicals", "textiles", "food", "metal", "wood", "stone"]
        guild_data = await self.config.guild(ctx.guild).all()

        last_claimed_time = datetime.datetime.fromisoformat(guild_data["last_claimed"])
        current_time = datetime.datetime.utcnow()
        hours_passed = (current_time - last_claimed_time).total_seconds() / 3600

        # Calculate the new multiplier based on the hours passed
        if hours_passed >= 1:
            guild_data["multiplier"] *= 1.5 ** int(hours_passed)  # Multiply by 1.5 for each full hour passed

        resource = random.choice(valid_resources)
        base_reward = 10
        reward = int(base_reward * guild_data["multiplier"])

        # Update user's inventory
        user_data = await self.config.user(ctx.author).all()
        resource_key = f"{resource}_basic"
        user_data[resource_key] = user_data.get(resource_key, 0) + reward
        await self.config.user(ctx.author).set(user_data)

        # Reset the last claimed time and multiplier
        guild_data["last_claimed"] = datetime.datetime.utcnow().isoformat()
        guild_data["multiplier"] = 1.0  # Reset multiplier
        await self.config.guild(ctx.guild).set(guild_data)

        await ctx.send(f"You've successfully gathered {reward} units of {resource.capitalize()}.")

    @commands.command()
    @commands.is_owner()
    async def view_recipe(self,ctx):
        await ctx.send(len(await self.config.common()))
        await ctx.send(len(await self.config.rare()))
        await ctx.send(len(await self.config.epic()))
        await ctx.send(len(await self.config.legendary()))
        await ctx.send(len(await self.config.mythic()))


    @commands.command()
    @commands.is_owner()
    async def reset_commons(self,ctx):
        guild = ctx.guild  # Gets the guild where the command was called
        if not guild:
            await ctx.send("This command can only be used within a server.")
            return
    
        for member in guild.members:
            if member.bot:
                continue  # Skip bot accounts

            user_data = await self.config.user(member).all()

            filtered_inventory = {item: count for item, count in user_data.items() if not item.endswith('_common')}

            await self.config.user(member).set(filtered_inventory)
        await ctx.send("All Done")
















            
    
    
