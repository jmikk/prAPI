from redbot.core import commands, Config
import asyncio
import datetime
from discord.ext import tasks
import math
import datetime
#from redbot.core import tasks

class Farm(commands.Cog):
    """Farming Game Cog for Discord."""
    
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=12345789630, force_registration=True)

        default_user = {
            "inventory": {},
            "fields": {},
            "gold": 0,
            "field_size": 1  # Default field size allowing only 1 crop at a time
        }
        self.config.register_user(**default_user)

        self.items = {
            "potato": {"emoji": "🥔", "min_price": 10, "max_price": 30, "current_price": 20, "growth_time": 60},
            "carrot": {"emoji": "🥕", "min_price": 10, "max_price": 20, "current_price": 15, "growth_time": 1},
            "corn": {"emoji": "🌽", "min_price": 15, "max_price": 35, "current_price": 25, "growth_time": 18000},
            "tomato": {"emoji": "🍅", "min_price": 20, "max_price": 40, "current_price": 30, "growth_time": 21600},
            "grapes": {"emoji": "🍇", "min_price": 25, "max_price": 45, "current_price": 40, "growth_time": 28800},
            "apple": {"emoji": "🍎", "min_price": 30, "max_price": 50, "current_price": 50, "growth_time": 36000},
            "strawberry": {"emoji": "🍓", "min_price": 5, "max_price": 15, "current_price": 10, "growth_time": 7200},
            "peach": {"emoji": "🍑", "min_price": 35, "max_price": 55, "current_price": 60, "growth_time": 43200},
            "cherries": {"emoji": "🍒", "min_price": 22, "max_price": 42, "current_price": 35, "growth_time": 25200},
            "lemon": {"emoji": "🍋", "min_price": 28, "max_price": 48, "current_price": 45, "growth_time": 32400},
            "taco": {"emoji": "🌮", "min_price": 28, "max_price": 48, "current_price": 45, "growth_time": 32400},

        }


        self.market_conditions = {
            "calm": (1, 3),
            "normal": (3, 7),
            "wild": (7, 10)
        }

        self.current_market_condition = "normal"  # Default market condition

    def cog_load(self):
        self.price_update_task.start()

    def cog_unload(self):
        self.price_update_task.cancel()

    @tasks.loop(hours=1)
    async def price_update_task(self):
        modifier_range = self.market_conditions[self.current_market_condition]
        for item, data in self.items.items():
            change = random.randint(*modifier_range) * random.choice([-1, 1])  # Randomly decide to increase or decrease
            new_price = data["current_price"] + change
            # Ensure new price stays within min and max bounds
            new_price = max(min(new_price, data["max_price"]), data["min_price"])
            self.items[item]["current_price"] = new_price

    @commands.group()
    async def farm(self, ctx):
        """Farming commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `$farm plant potato` to get started.")

    @farm.command()
    async def plant(self, ctx, crop_name: str):
        if crop_name not in self.items:
            await ctx.send(f"{crop_name.capitalize()} is not available for planting.")
            return
    
        user_fields = await self.config.user(ctx.author).fields()
        if len(user_fields) >= await self.config.user(ctx.author).field_size():
            await ctx.send("You don't have enough space in your field to plant more crops.")
            return
    
        planted_time = datetime.datetime.now().timestamp()
        user_fields.append({"name": crop_name, "planted_time": planted_time, "emoji": self.items[crop_name]["emoji"]})
        await self.config.user(ctx.author).fields.set(user_fields)
    
        await ctx.send(f"{crop_name.capitalize()} {self.items[crop_name]['emoji']} planted successfully!")


    async def _plant_crop(self, user, crop_name):
        now = datetime.datetime.now().timestamp()
        async with self.config.user(user).fields() as fields:
            fields[crop_name] = now

    @farm.command()
    async def status(self, ctx):
        """Check the status of your crops."""
        fields = await self.config.user(ctx.author).fields()
        status_messages = await self._get_crop_statuses(fields)
        status_messages.append(f"Your field can hold {await self.config.user(ctx.author).field_size()} crops in total.")
        await ctx.send("\n".join(status_messages)) 

    async def _get_crop_statuses(self, fields):
        now = datetime.datetime.now().timestamp()
        messages = []
        for crop, planted_time in fields.items():
            growth_time = self._get_growth_time(crop)  # Ensure this method returns growth time in seconds
            ready_time = planted_time + growth_time  # Calculate when the crop will be ready
    
            if now < ready_time:
                # Use Discord's Timestamp Styling, 'R' for relative time
                messages.append(f"{crop} {self.items[crop]['emoji']} will be ready <t:{int(ready_time)}:R>.")
            else:
                # Use 'f' for short date/time format since the crop is ready
                messages.append(f"{crop} {self.items[crop]['emoji']} is ready to harvest!")
        return messages

    def _get_growth_time(self, crop_name):
        """Get the growth time for a crop in seconds from the items dictionary."""
        # Check if the crop exists in the items dictionary
        if crop_name in self.items:
            # Return the growth time for the specified crop
            return self.items[crop_name]['growth_time']
        else:
            # Return a default growth time or raise an error if the crop is not found
            return None  # or raise ValueError(f"Crop {crop_name} not found")



    @farm.command()
    async def harvest(self, ctx, crop_name: str):
        """Harvest a ready crop."""
        success = await self._harvest_crop(ctx.author, crop_name)
        if success:
            await ctx.send(f"{crop_name} harvested successfully!")
        else:
            await ctx.send(f"{crop_name} is not ready yet.")
            
    async def _harvest_crop(self, user, crop_name):
        fields = await self.config.user(user).fields()
        if crop_name in fields:
            now = datetime.datetime.now().timestamp()
            planted_time = fields[crop_name]
            growth_time = self._get_growth_time(crop_name)
            if now - planted_time >= growth_time:
                async with self.config.user(user).fields() as fields:
                    del fields[crop_name]
                await self._add_to_inventory(user, crop_name)
                return True
        return False

    async def _add_to_inventory(self, user, crop_name):
        """Add harvested crop to the user's inventory."""
        async with self.config.user(user).inventory() as inventory:
            if crop_name in inventory:
                inventory[crop_name] += 1
            else:
                inventory[crop_name] = 1

    @farm.command(name="inventory", aliases=["inv"])
    async def view_inventory(self, ctx):
        """View your inventory of harvested crops."""
        inventory = await self.config.user(ctx.author).inventory()
        gold = await self.config.user(ctx.author).gold()
        if not inventory and not gold:
            await ctx.send("Your inventory is empty.")
            return

        inventory_message = self._format_inventory(inventory,gold)
        await ctx.send(inventory_message)
    
    def _format_inventory(self, inventory,gold):
        """Format the inventory into a string for display."""
        inventory_lines = []
        inventory_lines.append(f"Gold: :coin:: {gold}")
        for crop, quantity in inventory.items():
            inventory_lines.append(f"{crop.title()} {self.items[crop]['emoji']}: {quantity}")
        inventory_message = "\n".join(inventory_lines)
        return f"**Your Inventory:**\n{inventory_message}"

    @farm.command()
    async def upgrade_field(self, ctx):
        """Upgrade the field size by spending gold."""
        # Placeholder values for cost and upgrade increment
        upgrade_cost = 100  # Cost to upgrade the field
        upgrade_increment = 1  # Increase field size by 1
    
        gold = await self.config.user(ctx.author).gold()  # Assuming gold is tracked in the user's config
    
        if gold >= upgrade_cost:
            async with self.config.user(ctx.author) as user_data:
                user_data["gold"] -= upgrade_cost  # Deduct the cost
                user_data["field_size"] += upgrade_increment  # Increase field size
            await ctx.send(f"Field upgraded! You can now plant {user_data['field_size']} crops at a time.")
        else:
            await ctx.send("You don't have enough gold to upgrade your field.")
    
    @farm.command()
    @commands.is_owner()
    async def update_user_configs(self,ctx):
        await ctx.send("starting to update folks")
        all_members = [member for guild in self.bot.guilds for member in guild.members]
        for member in all_members:
            user_config = await self.config.user(member).all()
    
            # Check and update field_size
            if "field_size" not in user_config:
                await self.config.user(member).field_size.set(1)
                await ctx.send("adding Field_size")
            if "gold" not in user_config:
                await self.config.user(member).gold.set(0)
        await ctx.send("All done") 
            # Repeat for other new fields as necessary

    @farm.command()
    async def sell(self, ctx, item_name: str, quantity: int):
        if item_name not in self.items:
            await ctx.send(f"{item_name.capitalize()} is not a valid item.")
            return

        if quantity <= 0:
            await ctx.send("Quantity must be greater than zero.")
            return

        user_inventory = await self.config.user(ctx.author).inventory()
        if item_name not in user_inventory or user_inventory[item_name] < quantity:
            await ctx.send(f"You do not have enough {item_name}(s) to sell.")
            return

        item = self.items[item_name]
        total_sale = item["current_price"] * quantity

        # Update user inventory
        async with self.config.user(ctx.author).inventory() as inventory:
            inventory[item_name] -= quantity
            if inventory[item_name] <= 0:
                del inventory[item_name]  # Remove the item if quantity is zero

        
        # Update user gold
        user_gold = await self.config.user(ctx.author).gold()
        new_gold_total = user_gold + total_sale
        await self.config.user(ctx.author).gold.set(new_gold_total)
        
        price_decrease = item["current_price"] * (.01 * quantity)  # Example: decrease price by 5%
        new_price = max(item["min_price"], item["current_price"] - price_decrease)  # Ensure price doesn't go below min
        self.items[item_name]["current_price"] = math.floor(new_price)  # Round down the new price

        await ctx.send(f"Sold {quantity} {item_name}(s) for {total_sale} gold. You now have {new_gold_total} gold.\nThe new market price for {item_name} is {self.items[item_name]['current_price']} gold.")

    @farm.command()
    async def check_market(self, ctx):
        """Check the current market prices of items."""
        if not self.items:  # Check if the items dictionary is empty
            await ctx.send("The market is currently empty.")
            return

        prices_message = "**Current Market Prices:**\n"
        for item_name, item_info in self.items.items():
            prices_message += f"{item_name.title()} {self.items[item_name]['emoji']}: {item_info['current_price']} gold\n"

        await ctx.send(prices_message)

    @farm.command()
    async def field_upgrade(self, ctx):
        base_cost = 100  # Starting cost for the first upgrade
        multiplier = 1.2  # Cost multiplier for each subsequent upgrade
    
        user_data = await self.config.user(ctx.author).all()
        current_field_size = user_data['field_size']
        user_gold = user_data['gold']
    
        upgrade_cost = math.floor(base_cost * (multiplier ** current_field_size))  # Calculate the cost for the next upgrade
    
        if user_gold >= upgrade_cost:
            new_field_size = current_field_size + 1
            new_gold_total = user_gold - upgrade_cost
    
            # Update the user's gold and field size
            await self.config.user(ctx.author).gold.set(new_gold_total)
            await self.config.user(ctx.author).field_size.set(new_field_size)
    
            await ctx.send(f"Field upgraded to size {new_field_size}! It cost you {upgrade_cost} gold. You now have {new_gold_total} gold.")
        else:
            await ctx.send(f"You need {upgrade_cost} gold to upgrade your field, but you only have {user_gold} gold.")

    @farm.command()
    async def clear_field(self, ctx):
        """Clears all crops from your field after confirmation."""
        confirmation_message = await ctx.send("Are you sure you want to clear your field? React with ✅ to confirm.")
    
        # React to the message with a checkmark
        await confirmation_message.add_reaction("✅")
    
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirmation_message.id
    
        try:
            # Wait for the user to react with the checkmark
            await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
    
            # Clear the field after confirmation
            await self.config.user(ctx.author).fields.set({})
            await ctx.send("All crops in your field have been cleared.")
    
        except asyncio.TimeoutError:
            await ctx.send("Field clear canceled.")




    
