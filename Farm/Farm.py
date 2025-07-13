import asyncio
import datetime
from discord.ext import tasks
import math
import datetime
import random
import discord
from discord import Embed
import os
import json
from redbot.core import commands, Config
from discord.ext import commands as ext_commands

class FightView(discord.ui.View):
    def __init__(self, round_messages, author, enemy_name, loot_items_path, config, start_life, rep_change, ctx):       
        super().__init__(timeout=60)
        self.round_messages = round_messages
        self.current_page = 0
        self.message = None
        self.author = author
        self.enemy_name = enemy_name
        self.loot_items_path = loot_items_path
        self.config = config
        self.start_life = start_life
        self.rep_change = rep_change
        self.combat_result = None
        self.ctx = ctx  # to send fallback errors

    async def send_loss_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Fight Result", description=f"{self.author.mention}, you lost the fight!", color=discord.Color.red())
        embed.add_field(name="Opponent", value=self.enemy_name, inline=False)
        embed.add_field(name="Better luck next time!", value="Consider upgrading your gear or strategizing differently.", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=False)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if self.current_page > 0:
                self.current_page -= 1
                await interaction.response.edit_message(embed=self.round_messages[self.current_page], view=self)
        except Exception as e:
            await self.ctx.send(f"⚠️ Error in ◀ button: `{e}`")


    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if self.current_page < len(self.round_messages) - 1:
                self.current_page += 1
                await interaction.response.edit_message(embed=self.round_messages[self.current_page], view=self)
    
                if self.current_page == len(self.round_messages) - 1:
                    await asyncio.sleep(0.5)
                    await self.claim.callback(interaction)
            else:
                await interaction.response.defer()
        except Exception as e:
            await self.ctx.send(f"⚠️ Error in ▶ button: `{e}`")

    @discord.ui.button(label="🎁 Claim", style=discord.ButtonStyle.success)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.stop()
            if self.rep_change > 0:
                with open(self.loot_items_path, 'r') as file:
                    loot_items = json.load(file)['items']
                loot_box_item = random.choice(loot_items)
                item_name = loot_box_item['name']
                stats = loot_box_item['stats']
                await interaction.response.send_message(f"**Congratulations!** You've received a **{item_name}** from the loot box!", ephemeral=True)
                await self._add_loot_to_inventory(interaction, self.author, loot_box_item, stats)
                await interaction.followup.send(f"{self.author.mention} defeated **{self.enemy_name}** and earned a loot box!", ephemeral=False)
            else:
                await interaction.response.defer()
                await self.send_loss_embed(interaction)
        except Exception as e:
            await self.ctx.send(f"⚠️ Error in 🎁 claim: `{e}`")

    async def _add_loot_to_inventory(self,ctx, user, item, stats):
        user_data = await self.config.user(user).all()
        current_item = user_data[item['slot']]

        player_rep = user_data['rep']  # Get the player's current rep
        new_item_stats_with_bonus = {stat: math.floor(value + player_rep/2) for stat, value in stats.items()}
        new_item_stats = "\n" + '\n'.join([f"{stat.replace('_', ' ').capitalize()}: {value}" for stat, value in new_item_stats_with_bonus.items()]) + "\n\n"
        
    
        if current_item:
            # Create an embed object
            embed = discord.Embed(title="Congratulations you won!", color=discord.Color.blue())
            
            # Add the current item's name and stats to the embed
            current_item_stats = "\n".join([f"{stat.replace('_', ' ').capitalize()}: {value}" for stat, value in current_item.get('stats', {}).items()])
            
            current_item_stats = current_item_stats.replace("Strength","⚔️Strength⚔️").replace("Defense","🛡️Defense🛡️").replace("Speed","🏃Speed🏃‍♀️").replace("Luck","🍀Luck🍀").replace("Health","❤️Health❤️").replace("Critical chance","💥Critical Chance💥")
           
            embed.add_field(name=f"Current Item: {current_item['name']}", value=current_item_stats, inline=False)
            item['stats'] = new_item_stats_with_bonus

            # Add the new item's name and stats to the embed
            new_item_stats = "\n".join([f"{stat.replace('_', ' ').capitalize()}: {value}" for stat, value in item.get('stats', {}).items()])

            new_item_stats = new_item_stats.replace("Strength","⚔️Strength⚔️").replace("Defense","🛡️Defense🛡️").replace("Speed","🏃Speed🏃‍♀️").replace("Luck","🍀Luck🍀").replace("Health","❤️Health❤️").replace("Critical chance","💥Critical Chance💥")

            
            embed.add_field(name=f"New Item: {item['name']}", value=new_item_stats, inline=False)
            
            # Set footer instructions
            embed.set_footer(text="React with ✅ to swap or ❌ to keep.")
            
            # Send the embed in the channel
            message = await ctx.send(embed=embed)
            
            # Add reaction options for user decision
            await message.add_reaction("✅")
            await message.add_reaction("❌")

            
    
            def check(reaction, user_reacted):
                return user_reacted == user and str(reaction.emoji) in ["✅", "❌"]
    
            try:
                reaction, user_reacted = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
    
                if str(reaction.emoji) == "✅":
                    # User chose to swap the item
                    item['stats'] = new_item_stats_with_bonus
                    
                    user_data[item['slot']] = item
                    await ctx.send(f"You've equipped **{item['name']}** in your {item['slot']} slot.")

                    #unequip
                    for stat, bonus in current_item.get("stats", {}).items():
                        if stat in user_data:
                            user_data[stat] = user_data[stat] - bonus


                    #add the new stats to the player.
                    #reepuip
                    for stat, bonus in item['stats'].items():
                        if stat in user_data:
                            user_data[stat] = user_data[stat] + bonus
                        

                    
                    await self.config.user(user).set(user_data)

                
                else:
                    # User chose to keep the old item
                    await ctx.send("You've kept your current item.")
    
            except asyncio.TimeoutError:
                await ctx.send("No response. Keeping your current item.")
    
        else:
            # The slot is empty, simply add the new item
            item['stats'] = new_item_stats_with_bonus
            user_data[item['slot']] = item
            
            for stat, bonus in item['stats'].items():
                if stat in user_data:
                    user_data[stat] = user_data[stat] + bonus
            
            await self.config.user(user).set(user_data)
            await ctx.send(f"You've equipped {item['name']} in your {item['slot']}.")





class Farm(commands.Cog):
    """Farming Game Cog for Discord."""
    
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=12345789631, force_registration=True)

        default_user = {
            "inventory": {},
            "fields": [],
            "gold": 0,
            "field_size": 1,  # Default field size allowing only 1 crop at a time
            "last_activity":0,

            #need to be added 
            "scrap":0,
            
            "rep":1,
            "strength":1,
            "defense":1,
            "speed":1,
            "luck":1,
            "Health":10,
            "Critical_chance":1,
            
            "helmet":{},
            "body":{},
            "boots":{},
            "gloves":{},
            "ring":{},
            "weapon":{},
            "artifact":{},
            "belt":{},
            "loot":[],
        }
        
        self.config.register_user(**default_user)
        #working traits are fast_grow, slow_grow, high_yeild
        self.items = {
            "potato": {"emoji": "🥔", "min_price": 1, "max_price": 10, "current_price": 7, "growth_time": 60, "trait_out":"slow_grow", "trait_out_%":90, "traits": ["base"]},  # 1 minute
            "carrot": {"emoji": "🥕", "min_price": 1, "max_price": 16, "current_price": 12, "growth_time": 300 , "trait_out":"slow_grow", "trait_out_%":70, "traits": ["base"]},  # 5 minutes
            "corn": {"emoji": "🌽", "min_price": 1, "max_price": 40, "current_price": 30, "growth_time": 10800 , "trait_out":"slow_grow", "trait_out_%":40, "traits": ["base"]},  # 3 hours
            "tomato": {"emoji": "🍅", "min_price": 1, "max_price": 60, "current_price": 45, "growth_time": 21600 , "trait_out":"slow_grow", "trait_out_%":20, "traits": ["base"]},  # 6 hours
            "grapes": {"emoji": "🍇", "min_price": 1, "max_price": 80, "current_price": 60, "growth_time": 43200 , "trait_out": "high_yeild" , "trait_out_%":20, "traits": ["base"]},  # 12 hours
            "apple": {"emoji": "🍎", "min_price": 1, "max_price": 100, "current_price": 75, "growth_time": 86400, "trait_out":"glow", "trait_out_%":10, "traits": ["base"]},  # 1 day
            "strawberry": {"emoji": "🍓", "min_price": 1, "max_price": 30, "current_price": 22, "growth_time": 1800 , "trait_out":"golden", "trait_out_%":10, "traits": ["base"]},  # 30 minutes
            "peach": {"emoji": "🍑", "min_price": 1, "max_price": 120, "current_price": 90, "growth_time": 129600 , "trait_out":"golden", "trait_out_%":10, "traits": ["base"]},  # 1.5 days
            "cherries": {"emoji": "🍒", "min_price": 1, "max_price": 70, "current_price": 52, "growth_time": 57600 , "trait_out":"fast_grow", "trait_out_%":5, "traits": ["base"]},  # 16 hours
            "lemon": {"emoji": "🍋", "min_price": 1, "max_price": 90, "current_price": 67, "growth_time": 172800 , "trait_out":"fast_grow", "trait_out_%":20, "traits": ["base"]},  # 2 days
            "taco": {"emoji": "🌮", "min_price": 1, "max_price": 200, "current_price": 150, "growth_time": 604800, "trait_out":"fast_grow", "trait_out_%":30, "traits": ["base"]},  # 1 week
            "zombie": {"emoji": "🧟", "min_price": 1, "max_price": 100,  "current_price": 75, "growth_time": 86400, "trait_out":"rot", "trait_out_%":20, "traits": ["base"]},
            "rot": {"emoji": "🧪", "min_price": 1, "max_price": 40,  "current_price": 75, "growth_time": "n/a", "trait_out":"rot", "trait_out_%":50, "traits": ["rot"]} 

        }

        default_global = {
            "donations": {},
            "donation_goal": {}
        }
        self.config.register_global(**default_global)

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
            if self.items[crop]["trait_out_%"]/100 > random.random():
                traits.append(self.items[crop]["trait_out"])  
        return traits

    def cog_load(self):
        self.price_update_task.start()

    def cog_unload(self):
        self.price_update_task.cancel()

    @tasks.loop(hours=8)
    async def price_update_task(self):
        all_users = await self.config.all_users()
        # Determine active users (activity in the last 30 days)
        active_users = {user_id: data for user_id, data in all_users.items() if datetime.datetime.now().timestamp() - data.get("last_activity", 0) <= 30 * 24 * 60 * 60}
    
        # Calculate total inventory for each crop among active users
        total_inventory = {crop: 0 for crop in self.items.keys()}
        for user_id, data in active_users.items():
            inventory = data.get("inventory", {})
            for crop, quantity in inventory.items():
                if crop in total_inventory:
                    total_inventory[crop] += quantity
    
        # Calculate total number of crops in active inventories
        total_crops = sum(total_inventory.values())
    
        # Adjust price based on inventory percentage
        for item, data in self.items.items():
            if total_crops > 0:  # Avoid division by zero
                crop_percentage = total_inventory[item] / total_crops * 100  # Percentage of total
    
                # Determine price adjustment direction
                if crop_percentage > 20:
                    price_direction = -1  # Decrease price
                elif crop_percentage < 10:
                    price_direction = 1  # Increase price
                else:
                    price_direction = random.choice([-1, 1.2,])  # 50-50 chance
    
                # Calculate price change
                modifier_range = self.market_conditions[self.current_market_condition]
                base_change = random.randint(*modifier_range) * price_direction
    
                # Apply the price change
                new_price = data["current_price"] + base_change
                # Ensure new price is within min and max bounds
                new_price = max(min(new_price, data["max_price"]), data["min_price"])
                self.items[item]["current_price"] = new_price
            else:
                pass


    @commands.group()
    async def farm(self, ctx):
        """Farming commands."""
        if ctx.invoked_subcommand is None:
            prefix = await self.bot.get_prefix(ctx.message)
            await ctx.send(f"Use `{prefix[0]}farm plant potato` to get started.")




    @farm.command()
    async def fight(self, ctx):
        user_data = await self.config.user(ctx.author).all()

        zombie_names_path = os.path.join(os.path.dirname(__file__), 'zombie_names.txt')
        with open(zombie_names_path, 'r') as file:
            zombie_names = [line.strip() for line in file.readlines()]
        enemy_name = random.choice(zombie_names)

        user_rep = user_data['rep']
        low_mod = 1
        high_mod = 2
        enemy_stats = {
            "strength": random.randint(math.floor(1 + user_rep / low_mod), math.ceil((user_rep + 1) * high_mod)),
            "defense": random.randint(math.floor(1 + user_rep / low_mod), math.ceil((user_rep + 1) * high_mod)),
            "speed": random.randint(math.floor(1 + user_rep / low_mod), math.ceil((user_rep + 1) * high_mod)),
            "luck": random.randint(math.floor(1 + user_rep / low_mod), math.ceil((user_rep + 1) * high_mod)),
            "Health": random.randint(math.floor(1 + user_rep / low_mod), math.ceil((user_rep + 1) * high_mod)),
            "Critical_chance": random.randint(math.floor(1 + user_rep / low_mod), math.ceil((user_rep + 1) * high_mod)),
        }

        round_messages = []
        round_count = 0
        start_life = user_data['Health']
        bad_start_life = enemy_stats['Health']

        while user_data['Health'] > 0 and enemy_stats['Health'] > 0:
            round_count += 1
            player_attack = user_data['strength'] + random.randint(1, user_data['luck'])
            enemy_attack = enemy_stats['strength'] + random.randint(1, enemy_stats['luck'])
            player_defense = user_data['defense'] * (1 + user_data['speed'] / 100)
            enemy_defense = enemy_stats['defense'] * (1 + enemy_stats['speed'] / 100)

            player_damage = max(round_count, player_attack - enemy_defense)
            enemy_damage = max((round_count ** 2) / 2, enemy_attack - player_defense)

            for _ in range(user_data['Critical_chance'] // 100):
                player_damage *= 2
            if random.random() < (user_data['Critical_chance'] % 100) / 100:
                player_damage *= 2

            for _ in range(enemy_stats['Critical_chance'] // 100):
                enemy_damage *= 2
            if random.random() < (enemy_stats['Critical_chance'] % 100) / 100:
                enemy_damage *= 2

            player_damage = math.ceil(player_damage)
            enemy_damage = math.floor(enemy_damage)

            user_data['Health'] -= enemy_damage
            enemy_stats['Health'] -= player_damage

            player_bar = "❤️" * math.ceil(10 * user_data['Health'] / start_life) + "🖤" * (10 - math.ceil(10 * user_data['Health'] / start_life))
            enemy_bar = "💚" * math.ceil(10 * enemy_stats['Health'] / bad_start_life) + "🖤" * (10 - math.ceil(10 * enemy_stats['Health'] / bad_start_life))

            embed = discord.Embed(title=f"Round {round_count} - {enemy_name}", color=discord.Color.blue())
            embed.add_field(name=f"{enemy_name}", value=f"Damage Taken: **{player_damage}**\nHealth: {enemy_bar}", inline=False)
            embed.add_field(name="You", value=f"Damage Taken: **{enemy_damage}**\nHealth: {player_bar}", inline=False)
            round_messages.append(embed)

        result = "won" if user_data['Health'] > 0 else "lost"
        rep_change = 1 if result == "won" else -1
        user_data['rep'] = max(1, user_data['rep'] + rep_change)
        user_data['Health'] = start_life  # Reset for future fights
        await self.config.user(ctx.author).set(user_data)

        if result == "lost":
            embed = discord.Embed(title="Fight Result", description=f"{ctx.author.mention}, you lost the fight!", color=discord.Color.red())
            embed.add_field(name="Opponent", value=enemy_name, inline=False)
            embed.add_field(name="Better luck next time!", value="Consider upgrading your gear or strategizing differently.", inline=False)
            await ctx.send(embed=embed)

        loot_items_path = os.path.join(os.path.dirname(__file__), 'loot.json')
        view = FightView(round_messages, ctx.author, enemy_name, loot_items_path, self.config, start_life, rep_change, ctx)
        view.message = await ctx.send(embed=round_messages[0], view=view)


    @farm.command()
    async def plant(self, ctx, crop_name: str, quantity: int = 1):
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())
    
        if crop_name == "rot":
            await ctx.send("You can't plant rot!")
            return
    
        if crop_name not in self.items:
            available_crops = ', '.join([f"{name} {info['emoji']}" for name, info in self.items.items()])
            await ctx.send(f"{crop_name.capitalize()} is not available for planting. Available crops are: {available_crops}.")
            return
    
        user_fields = await self.config.user(ctx.author).fields()
        max_fields = await self.config.user(ctx.author).field_size()
    
        if len(user_fields) + quantity > max_fields:
            await ctx.send(f"You don't have enough space in your field to plant {quantity} more crops.")
            return
    
    
        for _ in range(quantity):  # Loop to plant multiple crops
            planted_time = datetime.datetime.now().timestamp()
            surrounding_crops = [crop["name"] for crop in user_fields]  # Get names of crops in the field
            traits = self.inherit_traits(surrounding_crops)  # Determine traits based on surrounding crops
    
            if "slow_grow" in traits:
                # Apply logic for slow_grow trait
                reduction_percentage = 0.3  # Initial reduction percentage
                for i in range(traits.count("slow_grow")):
                    reduction_amount = self.items[crop_name]["growth_time"] * reduction_percentage
                    planted_time += reduction_amount  # Increase planted time for slow growth
                    reduction_percentage *= 0.5  # Diminish the reduction for each additional trait
    
            if "fast_grow" in traits:
                # Apply logic for fast_grow trait
                reduction_percentage = 0.3  # Initial reduction percentage
                for i in range(traits.count("fast_grow")):
                    reduction_amount = self.items[crop_name]["growth_time"] * reduction_percentage
                    planted_time -= reduction_amount  # Decrease planted time for fast growth
                    reduction_percentage *= 0.5  # Diminish the reduction for each additional trait
    
            user_fields.append({"name": crop_name, "planted_time": planted_time, "emoji": self.items[crop_name]["emoji"], "traits": traits})
    
        await self.config.user(ctx.author).fields.set(user_fields)
        if crop_name == "zombie" and len(traits) > 1:
            await ctx.send(f"Zombie {self.items[crop_name]['emoji']} planted successfully with traits: {', '.join(traits[1:])}!")
        else:
            await ctx.send(f"{quantity} {crop_name.capitalize()} {self.items[crop_name]['emoji']} planted successfully!")





    async def _plant_crop(self, user, crop_name):
        now = datetime.datetime.now().timestamp()
        async with self.config.user(user).fields() as fields:
            fields[crop_name] = now

    @farm.command()
    async def status(self, ctx):
        """Check the status of your crops with pagination."""
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

        fields = await self.config.user(ctx.author).fields()
        field_size = await self.config.user(ctx.author).field_size()

        # Split fields into pages of 10, ensuring at least one page exists
        pages = [fields[i:i + 10] for i in range(0, len(fields), 10)] if fields else [[]]

        # Function to create the embed for each page
        def get_embed(page, page_number, total_pages):
            embed = Embed(title="Crop Status", description=f"Current field size: {len(fields)}/{field_size}.  Your fields are {math.floor((len(fields)/field_size)*100)}% full", color=0x00FF00)
            for crop_instance in page:
                crop_name = crop_instance["name"]
                emoji = crop_instance["emoji"]
                growth_time = self._get_growth_time(crop_name)
                ready_time = crop_instance["planted_time"] + growth_time
                now = datetime.datetime.now().timestamp()
                if now < ready_time:
                    embed.add_field(name=f"{crop_name} {emoji}", value=f"Will be ready <t:{int(ready_time)}:R>.", inline=False)
                else:
                    embed.add_field(name=f"{crop_name} {emoji}", value="Ready to harvest!", inline=False)
            embed.set_footer(text=f"Page {page_number+1}/{total_pages}")
            return embed

        # Function to control page navigation
        async def status_pages(ctx, pages):
            current_page = 0
            message = await ctx.send(embed=get_embed(pages[current_page], current_page, len(pages)))

            # Add reactions for navigation
            navigation_emojis = ['⬅️', '➡️']
            await message.add_reaction('⬅️')
            await message.add_reaction('➡️')

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in navigation_emojis and reaction.message.id == message.id

            while True:
                try:
                    reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

                    # Handle navigation
                    if str(reaction.emoji) == '⬅️' and current_page > 0:
                        current_page -= 1
                    elif str(reaction.emoji) == '➡️' and current_page < len(pages) - 1:
                        current_page += 1

                    # Update the embed
                    await message.edit(embed=get_embed(pages[current_page], current_page, len(pages)))
                    await message.remove_reaction(reaction, user)
                except asyncio.TimeoutError:
                    break  # End pagination after timeout

        # Start pagination
        await status_pages(ctx, pages)


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
    async def harvest(self, ctx):
        """Harvest all ready crops."""
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

        fields = await self.config.user(ctx.author).fields()
        now = datetime.datetime.now().timestamp()
        harvested_crops = []  # List to store harvested crop emojis
        remaining_fields = []  # List to store crops that are not ready for harvest
    
        for crop_instance in fields:
            growth_time = self._get_growth_time(crop_instance["name"])
            ready_time = crop_instance["planted_time"] + growth_time
    
            if now >= ready_time:
                if "high_yeild" in crop_instance["traits"]:
                    harvested_crops.append(crop_instance["emoji"])  # Add emoji to harvested list
                    await self._add_to_inventory(ctx.author, crop_instance["name"])  # Add crop to inventory
                if "golden" in crop_instance["traits"]:
                    harvested_crops.append(":coin:")  # Add emoji to harvested list
                    current_gold = await self.config.user(ctx.author).gold()
                    new_gold = current_gold + 5
                    await self.config.user(ctx.author).gold.set(new_gold)
                if "rot" in crop_instance["traits"]:
                    harvested_crops.append("🧪")  # Add emoji to harvested list
                    await self._add_to_inventory(ctx.author, "rot")  # Add crop to inventory
                else:
                    harvested_crops.append(crop_instance["emoji"])  # Add emoji to harvested list
                    await self._add_to_inventory(ctx.author, crop_instance["name"])  # Add crop to inventory
            else:
                remaining_fields.append(crop_instance)  # Crop is not ready, keep it in fields
    
        # Update fields to only include crops that weren't harvested
        await self.config.user(ctx.author).fields.set(remaining_fields)
    
        if harvested_crops:
            harvested_message = ''.join(harvested_crops) + " harvested successfully!"
            await ctx.send(harvested_message)
        else:
            await ctx.send("No ready crops to harvest.")
    
            

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
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

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
        inventory_lines.append(f"Gold: :coin:: {math.floor(gold)}")
        for crop, quantity in inventory.items():
            inventory_lines.append(f"{crop.title()} {self.items[crop]['emoji']}: {quantity}")
        inventory_message = "\n".join(inventory_lines)
        return f"**Your Inventory:**\n{inventory_message}"

    
    @farm.command()
    async def sell(self, ctx, item_name: str, quantity: int):
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

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
        new_gold_total = math.floor(user_gold + total_sale)
        await self.config.user(ctx.author).gold.set(new_gold_total)
        
        price_decrease = item["current_price"] * (.01 * quantity)  # Example: decrease price by 5%
        new_price = max(item["min_price"], item["current_price"] - price_decrease)  # Ensure price doesn't go below min
        self.items[item_name]["current_price"] = math.floor(new_price)  # Round down the new price

        await ctx.send(f"Sold {quantity} {item_name}(s) for {total_sale} gold. You now have {new_gold_total} gold.\nThe new market price for {item_name} is {self.items[item_name]['current_price']} gold.")

    @farm.command()
    async def check_market(self, ctx):
        """Check the current market prices of items."""
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

        if not self.items:  # Check if the items dictionary is empty
            await ctx.send("The market is currently empty.")
            return

        prices_message = "**Current Market Prices:**\n"
        for item_name, item_info in self.items.items():
            prices_message += f"{item_name.title()} {self.items[item_name]['emoji']}: {math.floor(item_info['current_price'])} gold, {item_info['growth_time']} seconds to grow\n"

        await ctx.send(prices_message)

    @farm.command()
    async def field_upgrade(self, ctx):
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

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
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

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

    @farm.command()
    async def donate(self, ctx, item_name: str, quantity: int):
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

        if quantity <= 0:
            await ctx.send("Please specify a valid quantity to donate.")
            return
    
        inventory = await self.config.user(ctx.author).inventory()
        if inventory.get(item_name, 0) < quantity:
            await ctx.send(f"You do not have enough {item_name} to donate.")
            return
    
        # Deduct the item from the user's inventory
        inventory[item_name] -= quantity
        if inventory[item_name] <= 0:
            del inventory[item_name]  # Remove the item from the inventory if quantity is 0
        await self.config.user(ctx.author).inventory.set(inventory)
    
        # Add the donated items to the donation count
        current_donations = await self.config.donations()
        current_donations[item_name] = current_donations.get(item_name, 0) + quantity
        await self.config.donations.set(current_donations)
    
        await ctx.send(f"Thank you for donating {quantity} {item_name}!")
    
        # Check if the donation goal is reached
        donation_goal = await self.config.donation_goal()
        if current_donations[item_name] >= donation_goal[item_name]:
            await ctx.send(f"The donation goal for {item_name} has been reached!")
            # Implement what happens when the goal is reached

    @farm.command()
    async def donation_progress(self, ctx):
        await self.config.user(ctx.author).last_activity.set(datetime.datetime.now().timestamp())

        current_donations = await self.config.donations()
        donation_goal = await self.config.donation_goal()
        progress_messages = []
    
        for item, goal in donation_goal.items():
            donated = current_donations.get(item, 0)
            progress_messages.append(f"{item.capitalize()}: {donated}/{goal} donated")
    
        if progress_messages:
            await ctx.send("\n".join(progress_messages))
        else:
            await ctx.send("There are currently no donation goals.")




    @commands.command()
    @commands.is_owner()
    async def set_donation_goal(self, ctx, item: str, quantity: int):
        """
        Set a donation goal with custom messages.
    
        Args:
        item (str): The item name for the donation goal.
        quantity (int): The donation goal quantity.    
        """
        # Split the messages string into the thank-you message and the goal reached message
    
        # Set up the donation goal in the config
        await self.config.donation_goal.set({item: quantity})    
        await ctx.send(f"Donation goal for {item} set to {quantity}.")

    @commands.command()
    @commands.is_owner()
    async def givegold(self, ctx, member: discord.Member, amount: int):
        """
        Give a specified amount of gold to a player.

        Args:
        member (discord.Member): The member to give gold to.
        amount (int): The amount of gold to give.
        """
        if amount < 0:
            await ctx.send("Amount of gold must be positive.")
            return

        # Fetch the current gold amount for the member
        current_gold = await self.config.user(member).gold()

        # Add the specified amount to the member's current gold
        new_gold = current_gold + amount

        # Update the member's gold in the config
        await self.config.user(member).gold.set(new_gold)

        # Confirm the transaction
        await ctx.send(f"{amount} gold has been added to {member.display_name}'s account. They now have {new_gold} gold.")


    @commands.command(name="init_last_activity")
    @commands.is_owner()
    async def init_last_activity(self, ctx):
        """
        Initialize the last_activity field for all users in the config.
        """
        all_users = await self.config.all_users()
    
        for user_id, data in all_users.items():
            # Check if the user already has a last_activity field
            if "last_activity" not in data:
                # Set the last_activity to the current timestamp
                await self.config.user_from_id(user_id).last_activity.set(datetime.datetime.now().timestamp())
    
        await ctx.send("Initialized last_activity for all users.")

       
    @farm.command()
    async def view_stats(self,ctx):
        rep = await self.config.user(ctx.author).rep()
        str = await self.config.user(ctx.author).strength()
        defense = await self.config.user(ctx.author).defense()
        speed = await self.config.user(ctx.author).speed()
        luck = await self.config.user(ctx.author).luck()
        life  = await self.config.user(ctx.author).Health()
        crit = await self.config.user(ctx.author).Critical_chance()

        
        await ctx.send(f"Your ⚔️**Strength** is {str}\n Your **🛡️Defense** is {defense} \n Your **🏆Rep** is {rep} \n Your 🏃**Speed** is: {speed} \n Your 🍀**Luck** is {luck} \n Your ❤️**Life** is {life} \n Your 💥**Crit Chance** is {crit}")

    @commands.command(name='setstat')
    @commands.is_owner()  # Ensure only the bot owner can use this command
    async def set_stat(self, ctx, member: discord.Member, stat: str, value: int):
        """
        Command to forcefully set a player's stat, restricted to the bot owner.
    
        Args:
        member (discord.Member): The member whose stat is to be set.
        stat (str): The name of the stat to set (e.g., 'strength', 'Health').
        value (int): The new value for the stat.
        """
        # Validate the stat
        valid_stats = ['rep', 'strength', 'defense', 'speed', 'luck', 'Health', 'Critical_chance']
        if stat not in valid_stats:
            await ctx.send(f"Invalid stat. Valid stats are: {', '.join(valid_stats)}")
            return
    
        # Fetch the current user data
        user_data = await self.config.user(member).all()
    
        # Check if the stat exists in user data
        if stat in user_data:
            # Update the stat
            user_data[stat] = value
            await self.config.user(member).set(user_data)
            await ctx.send(f"{member.display_name}'s {stat} has been set to {value}.")
        else:
            await ctx.send(f"Stat {stat} not found.")


    @farm.command(name='reset')
    @commands.is_owner()  # Ensure only the bot owner can use this command
    async def reset_player_stats(self, ctx, member: discord.Member):
        user_data = await self.config.user(member).all()

        # Resetting base stats
        user_data['rep'] = 1
        user_data['strength'] = 1
        user_data['defense'] = 1
        user_data['speed'] = 1
        user_data['luck'] = 1
        user_data['Health'] = 10
        user_data['Critical_chance'] = 1
    
        # Clearing equipment slots
        user_data['helmet'] = {}
        user_data['body'] = {}
        user_data['boots'] = {}
        user_data['gloves'] = {}
        user_data['ring'] = {}
        user_data['weapon'] = {}
        user_data['artifact'] = {}
        user_data['belt'] = {}
    
        # Clearing loot
        user_data['loot'] = []
    
        await self.config.user(member).set(user_data)
        await ctx.send("all done")

    
    @farm.command(name="view_gear")
    async def view_gear(self, ctx):
        user_data = await self.config.user(ctx.author).all()

        # List of gear slots to check in the user's data
        gear_slots = ["helmet", "body", "boots", "gloves", "ring", "weapon", "artifact", "belt"]

        gear_messages = []
        for slot in gear_slots:
            item = user_data.get(slot, {})
            if item:  # Check if there's an item equipped in the slot
                item_name = item.get("name", "Unknown Item")
                item_stats = item.get("stats", {})
                stats_message = ', '.join([f"**{stat.capitalize()}**: {value}" for stat, value in item_stats.items()])
                #stats_message = stats_message.replace("Strength","⚔️Strength⚔️").replace("Defense","🛡️Defense🛡️").replace("Speed","🏃Speed🏃‍♀️").replace("Luck","🍀Luck🍀").replace("Health","❤️Health❤️").replace("Critical_chance","💥Critical Chance💥")

                gear_messages.append(f"**{slot.capitalize()}**: {item_name} ({stats_message})")
            else:
                gear_messages.append(f"**{slot.capitalize()}**: No item equipped")

        # Combine all the gear messages into one message
        gear_summary = "\n".join(gear_messages)

        # Send the gear summary to the player
        await ctx.send(f"**Your Gear:**\n{gear_summary}")
    

    @farm.command(name="upgrade_gear")
    async def upgrade_item(self, ctx, slot):
        user_data = await self.config.user(ctx.author).all()
    
        # Check if the slot is valid and has an item
        if slot.lower() not in user_data or not user_data[slot.lower()]:
            await ctx.send("Invalid slot or no item equipped in this slot.")
            return
    
        item = user_data[slot.lower()]  # The item to upgrade
        stats = item.get("stats", {})  # Item stats
    
        # Calculate upgrade cost: 100 gold for each 100 points in item stats
        total_stats = sum(stats.values())
        cost = (total_stats // 200) * 100
        if cost < 100:
            cost = 100
    
        if user_data["gold"] < cost:
            await ctx.send(f"Not enough gold. Upgrade costs {cost} gold.")
            return
    
        # Confirmation message
        confirm_msg = await ctx.send(f"Upgrading will cost {cost} gold. Do you wish to proceed? React with ✅ to confirm or ❌ to cancel.")
    
        # Add reactions for confirmation
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")
    
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
    
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
    
            # If the player cancels the upgrade
            if str(reaction.emoji) == "❌":
                await ctx.send("Upgrade cancelled.")
                return
    
            # If the player confirms the upgrade
            if str(reaction.emoji) == "✅":
                # Randomly choose a stat to upgrade
                stat_to_upgrade = random.choice(list(stats.keys()))
                stats[stat_to_upgrade] += 1  # Increment the chosen stat by 1
    
                # Deduct the cost from player's gold
                user_data["gold"] -= cost
    
                # Save changes
                await self.config.user(ctx.author).set(user_data)
    
                await ctx.send(f"Upgraded {stat_to_upgrade} on your {slot}. New value: {stats[stat_to_upgrade]}. Cost: {cost} gold.")
    
        except asyncio.TimeoutError:
            await ctx.send("Upgrade request timed out.")


    async def get_leaderboard_page(self, ctx, attribute="rep", page=1):
        guild = ctx.guild
        members = guild.members

        leaderboard_data = []
        for member in members:
            member_data = await self.config.user(member).all()
            leaderboard_data.append((member.display_name, member_data.get(attribute, 0)))

        leaderboard_data.sort(key=lambda x: x[1], reverse=True)

        items_per_page = 10
        total_pages = len(leaderboard_data) // items_per_page + (1 if len(leaderboard_data) % items_per_page > 0 else 0)
        start_index = (page - 1) * items_per_page
        end_index = start_index + items_per_page
        page_data = leaderboard_data[start_index:end_index]

        return page_data, total_pages

    async def update_leaderboard_embed(self, message, ctx, attribute, page, total_pages):
        page_data, _ = await self.get_leaderboard_page(ctx, attribute, page)
        embed = discord.Embed(title=f"Leaderboard: {attribute.capitalize()}", color=discord.Color.blue())
        
        items_per_page = 10
        start_rank = (page - 1) * items_per_page + 1  # Calculate the starting rank for the current page
    
        for index, (name, value) in enumerate(page_data, start=start_rank):
            embed.add_field(name=f"{index}. {name}", value=f"{attribute} {value}", inline=False)
        
        embed.set_footer(text=f"Page {page}/{total_pages}")
        await message.edit(embed=embed)


    @farm.command()
    async def leaderboard(self, ctx, attribute: str = "rep",page=1):
        attribute = attribute.lower().replace(" ","_")
        stats=["rep","strength","defense","speed","luck","health","critical_chance"]
        if attribute not in stats:
            ctx.send(f"Try doing one of the following {stats.join(', ')}")
            attribute = "rep"
        attribute.replace("health","Health").replace("critical_chance","Critical_chance")
        
        
        page_data, total_pages = await self.get_leaderboard_page(ctx, attribute, page)
        if not page_data:
            await ctx.send("No data available.")
            return

        embed = discord.Embed(title=f"Leaderboard: {attribute.capitalize()}", color=discord.Color.blue())
        
        for index, (name, value) in enumerate(page_data):
            embed.add_field(name=f"{index+1}. {name}", value=f"{attribute} {value}", inline=False)
        embed.set_footer(text=f"Page {page}/{total_pages}")

        message = await ctx.send(embed=embed)

        # Add reactions for pagination
        await message.add_reaction("⬅️")
        await message.add_reaction("➡️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

                if str(reaction.emoji) == "⬅️" and page > 1:
                    page -= 1
                elif str(reaction.emoji) == "➡️" and page < total_pages:
                    page += 1
                else:
                    continue

                await self.update_leaderboard_embed(message, ctx, attribute, page, total_pages)
                await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                break  # End the loop if there's no reaction within the timeout period
