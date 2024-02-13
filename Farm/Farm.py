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
        self.config = Config.get_conf(self, identifier=12345789631, force_registration=True)

        default_user = {
            "inventory": {},
            "fields": [],
            "gold": 0,
            "field_size": 1  # Default field size allowing only 1 crop at a time
        }
        self.config.register_user(**default_user)

        self.items = {
            "potato": {"emoji": "🥔", "min_price": 5, "max_price": 10, "current_price": 7, "growth_time": 60},  # 1 minute
            "carrot": {"emoji": "🥕", "min_price": 8, "max_price": 16, "current_price": 12, "growth_time": 300},  # 5 minutes
            "corn": {"emoji": "🌽", "min_price": 20, "max_price": 40, "current_price": 30, "growth_time": 10800},  # 3 hours
            "tomato": {"emoji": "🍅", "min_price": 30, "max_price": 60, "current_price": 45, "growth_time": 21600},  # 6 hours
            "grapes": {"emoji": "🍇", "min_price": 40, "max_price": 80, "current_price": 60, "growth_time": 43200},  # 12 hours
            "apple": {"emoji": "🍎", "min_price": 50, "max_price": 100, "current_price": 75, "growth_time": 86400},  # 1 day
            "strawberry": {"emoji": "🍓", "min_price": 15, "max_price": 30, "current_price": 22, "growth_time": 1800},  # 30 minutes
            "peach": {"emoji": "🍑", "min_price": 60, "max_price": 120, "current_price": 90, "growth_time": 129600},  # 1.5 days
            "cherries": {"emoji": "🍒", "min_price": 35, "max_price": 70, "current_price": 52, "growth_time": 57600},  # 16 hours
            "lemon": {"emoji": "🍋", "min_price": 45, "max_price": 90, "current_price": 67, "growth_time": 172800},  # 2 days
            "taco": {"emoji": "🌮", "min_price": 100, "max_price": 200, "current_price": 150, "growth_time": 604800},  # 1 week
            "zombie": {"emoji": "🧟", "min_price": 50, "max_price": 100,  "current_price": 75, "growth_time": 86400, "traits": ["base"]} 
        }



        self.market_conditions = {
            "calm": (1, 3),
            "normal": (3, 7),
            "wild": (7, 10)
        }

        self.current_market_condition = "normal"  # Default market condition


    # Step 3: Trait inheritance logic
    def inherit_traits(self, surrounding_crops):
        traits = ["base"]  # All zombies start with the base trait
        for crop in surrounding_crops:
            if crop in ["corn", "tomato"]:  # Example: certain crops influence zombie traits
                traits.append("fast_grower")  # Example trait
            elif crop in ["strawberry", "peach"]:
                traits.append("high_value")  # Example trait
        return traits

    def cog_load(self):
        self.price_update_task.start()

    def cog_unload(self):
        self.price_update_task.cancel()

    @tasks.loop(hours=1)
    async def price_update_task(self):
        modifier_range = self.market_conditions[self.current_market_condition]
        for item, data in self.items.items():
            change = random.randint(*modifier_range) * random.choice([-1, 1, 1, 1])  # Randomly decide to increase or decrease
            new_price = data["current_price"] + change
            # Ensure new price stays within min and max bounds
            new_price = max(min(new_price, data["max_price"]), data["min_price"])
            self.items[item]["current_price"] = new_price

    @commands.group()
    async def farm(self, ctx):
        """Farming commands."""
        if ctx.invoked_subcommand is None:
            prefix = await self.bot.get_prefix(ctx.message)
            await ctx.send(f"Use `{prefix[0]}farm plant potato` to get started.")

    # Update the plant command to include zombie trait logic
    @farm.command()
    async def plant(self, ctx, crop_name: str):
        if crop_name not in self.items:
            available_crops = ', '.join([f"{name} {info['emoji']}" for name, info in self.items.items()])
            await ctx.send(f"{crop_name.capitalize()} is not available for planting. Available crops are: {available_crops}.")
            return
    
        user_fields = await self.config.user(ctx.author).fields()
        if len(user_fields) >= await self.config.user(ctx.author).field_size():
            await ctx.send("You don't have enough space in your field to plant more crops.")
            return
    
        planted_time = datetime.datetime.now().timestamp()
        if crop_name == "zombie":
            surrounding_crops = [crop["name"] for crop in user_fields]  # Get names of crops in the field
            traits = self.inherit_traits(surrounding_crops)  # Determine traits based on surrounding crops
            user_fields.append({"name": crop_name, "planted_time": planted_time, "emoji": self.items[crop_name]["emoji"], "traits": traits})
        else:
            user_fields.append({"name": crop_name, "planted_time": planted_time, "emoji": self.items[crop_name]["emoji"]})
    
        await self.config.user(ctx.author).fields.set(user_fields)
        if crop_name == "zombie" and len(traits) > 1:
            await ctx.send(f"Zombie {self.items[crop_name]['emoji']} planted successfully with traits: {', '.join(traits[1])}!")
        else:
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
        for crop_instance in fields:
            crop_name = crop_instance["name"]
            planted_time = crop_instance["planted_time"]
            growth_time = self._get_growth_time(crop_name)
            ready_time = planted_time + growth_time
            emoji = crop_instance["emoji"]
    
            if now < ready_time:
                messages.append(f"{crop_name} {emoji} will be ready <t:{int(ready_time)}:R>.")
            else:
                messages.append(f"{crop_name} {emoji} is ready to harvest! <t:{int(ready_time)}:R>")
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
        fields = await self.config.user(ctx.author).fields()
        now = datetime.datetime.now().timestamp()
        harvested = False
    
        for i, crop_instance in enumerate(fields):
            if crop_instance["name"] == crop_name:
                growth_time = self._get_growth_time(crop_name)
                ready_time = crop_instance["planted_time"] + growth_time
                
                if now >= ready_time:
                    harvested = True
                    await self._add_to_inventory(ctx.author, crop_name)
                    del fields[i]  # Remove the harvested crop from the fields
                    break  # Assuming we harvest the first ready crop of this type
    
        if harvested:
            await self.config.user(ctx.author).fields.set(fields)  # Update the fields without the harvested crop
            await ctx.send(f"{crop_name} harvested successfully!")
        else:
            await ctx.send(f"No ready {crop_name} crops to harvest.")

            
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
            prices_message += f"{item_name.title()} {self.items[item_name]['emoji']}: {item_info['current_price']} gold, {item_info['growth_time']} seconds to grow\n"

        await ctx.send(prices_message)

    @farm.command()
    async def field_upgrade(self, ctx):
        base_cost = 50  # Starting cost for the first upgrade
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
            await self.config.user(ctx.author).fields.set([])
            await ctx.send("All crops in your field have been cleared.")
    
        except asyncio.TimeoutError:
            await ctx.send("Field clear canceled.")

    @commands.command(name="migrate_fields")
    @commands.is_owner()
    async def migrate_fields(self, ctx):
        all_users = await self.config.all_users()
    
        for user_id, data in all_users.items():
            user_fields = data.get("fields", None)
            
            # Check if the fields are in the old dictionary format and migrate to list
            if isinstance(user_fields, dict):
                new_fields_list = [{"name": crop_name, "planted_time": planted_time, "emoji": self.items[crop_name]["emoji"]} for crop_name, planted_time in user_fields.items()]
                await self.config.user_from_id(user_id).fields.set(new_fields_list)
                await ctx.send(f"Migrated fields for user ID {user_id}.")
        
        await ctx.send("Migration complete.")

    




    
