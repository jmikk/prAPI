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
from discord import Message
import time
from datetime import timedelta

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
        await self.ctx.send(embed=embed, ephemeral=False)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author
    
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.current_page = (self.current_page - 1) % len(self.round_messages)
            await interaction.response.edit_message(embed=self.round_messages[self.current_page], view=self)
        except Exception as e:
            await self.ctx.send(f"⚠️ Error in ◀ button: `{e}`")

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.current_page = (self.current_page + 1) % len(self.round_messages)
            await interaction.response.edit_message(embed=self.round_messages[self.current_page], view=self)
        except Exception as e:
            await self.ctx.send(f"⚠️ Error in ▶ button: `{e}`")

    @discord.ui.button(label="🎁 Claim", style=discord.ButtonStyle.success)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Disable buttons
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            
            await interaction.message.edit(view=self)
            #self.stop()
            if self.rep_change > 0:
                with open(self.loot_items_path, 'r') as file:
                    loot_items = json.load(file)['items']
                loot_box_item = random.choice(loot_items)
                item_name = loot_box_item['name']
                stats = loot_box_item['stats']
                await self._add_loot_to_inventory(self.ctx, self.author, loot_box_item, stats)
                await interaction.response.defer()
            else:
                await self.send_loss_embed(interaction)
                await interaction.response.defer()

            
        except Exception as e:
            await self.ctx.send(f"⚠️ Error in 🎁 claim: `{e}`")
            

    async def _add_loot_to_inventory(self, ctx, user, item, stats):
        user_data = await self.config.user(user).all()
        current_item = user_data[item['slot']]
        player_rep = user_data['rep']
        new_item_stats_with_bonus = {stat: math.floor(value + player_rep / 2) for stat, value in stats.items()}
    
        if current_item:
            embed = discord.Embed(title="🎁 You found a new item!", color=discord.Color.gold())
    
            def fmt(stats_dict):
                s = "\n".join([f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in stats_dict.items()])
                return (s.replace("Strength","⚔️Strength⚔️")
                         .replace("Defense","🛡️Defense🛡️")
                         .replace("Speed","🏃Speed🏃‍♀️")
                         .replace("Luck","🍀Luck🍀")
                         .replace("Health","❤️Health❤️")
                         .replace("Critical chance","💥Critical Chance💥"))
    
            embed.add_field(name=f"New: {item['name']}", value=fmt(new_item_stats_with_bonus), inline=True)
            embed.add_field(name=f"Current: {current_item['name']}", value=fmt(current_item.get("stats", {})), inline=True)
            embed.set_footer(text="Choose to equip the new item or keep your current one.")
    
            view = LootDecisionView(self, ctx, user, item, current_item, new_item_stats_with_bonus)
            view.message = await ctx.send(embed=embed, view=view)
    
        else:
            # Equip directly
            item['stats'] = new_item_stats_with_bonus
            user_data[item['slot']] = item
    
            for stat, bonus in item['stats'].items():
                if stat in user_data:
                    user_data[stat] += bonus
    
            await self.config.user(user).set(user_data)
            await ctx.send(f"You've equipped **{item['name']}** in your empty **{item['slot']}** slot.")
    

class LootDecisionView(discord.ui.View):
    def __init__(self, cog, ctx, user, item, current_item, new_item_stats_with_bonus):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.user = user
        self.item = item
        self.current_item = current_item
        self.new_item_stats_with_bonus = new_item_stats_with_bonus
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.user:
            await interaction.response.send_message("❌ These buttons aren't for you!", ephemeral=True)
            return False
        return True


    @discord.ui.button(label="✅ Equip New Item", style=discord.ButtonStyle.success)
    async def equip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user_data = await self.cog.config.user(self.user).all()

            self.item["stats"] = self.new_item_stats_with_bonus
            user_data[self.item['slot']] = self.item

            # Remove old item stats
            for stat, bonus in self.current_item.get("stats", {}).items():
                if stat in user_data:
                    user_data[stat] -= bonus

            # Add new item stats
            for stat, bonus in self.item['stats'].items():
                if stat in user_data:
                    user_data[stat] += bonus

            await self.cog.config.user(self.user).set(user_data)
            await interaction.response.send_message(f"You've equipped **{self.item['name']}** in your **{self.item['slot']}** slot.", ephemeral=False)
            # Disable buttons
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            
            await interaction.message.edit(view=self)
            self.stop()
        except Exception as e:
                await self.ctx.send(f"❌ Error equipping item: `{e}`")

    @discord.ui.button(label="❌ Keep Current", style=discord.ButtonStyle.danger)
    async def keep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You've kept your current item.", ephemeral=False)
 # Disable buttons
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
            
        await interaction.message.edit(view=self)
        self.stop()



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

    def hearts_bar(self, current_hp, max_hp, full="❤️", empty="🖤", slots=10):
        # Guard against bad max values
        max_hp = max(1, int(max_hp))
        # Clamp current to [0, max_hp]
        current_hp = max(0, min(current_hp, max_hp))
        # Compute filled hearts (0..slots) and build the string
        ratio = current_hp / max_hp
        filled = min(slots, max(0, math.floor(slots * ratio + 1e-9)))
        return full * filled + empty * (slots - filled)



    @commands.group(hidden=True)
    async def farm(self, ctx):
        """Farming commands."""
        if ctx.invoked_subcommand is None:
            prefix = await self.bot.get_prefix(ctx.message)
            await ctx.send(
                f"🌾 **Welcome to the Farming Game!** 🌾\n\n"
                f"Here's what you can do:\n"
                f"- `{prefix[0]}farm plant <crop>` – Plant a crop to grow over time.\n"
                f"- `{prefix[0]}farm harvest` – Harvest your ready crops for rewards.\n"
                f"- `{prefix[0]}farm inventory` – View what you've harvested.\n"
                f"- `{prefix[0]}farm sell <crop> <amount>` – Sell your crops for gold.\n"
                f"- `{prefix[0]}farm status` – Check what's growing and when it will be ready.\n"
                f"- `{prefix[0]}farm field_upgrade` – Expand your field to plant more crops.\n"
                f"- `{prefix[0]}farm check_market` – See current crop prices.\n"
                f"- `{prefix[0]}farm fight` – Fight zombies to earn loot and rep!\n"
                f"- `{prefix[0]}farm view_stats` – View your character's stats.\n"
                f"- `{prefix[0]}farm view_gear` – See your equipped items.\n"
                f"- `{prefix[0]}farm upgrade_gear <slot>` – Upgrade one piece of gear.\n"
                f"- `{prefix[0]}farm casino <game>` – Gamble your gold in coinflip, dice, slots, or roulette.\n"
                f"- `{prefix[0]}farm leaderboard` – See who has the most rep, strength, or other stats.\n\n"
                f"💰 Earn gold by chatting or harvesting crops.\n"
                f"🧠 Use it wisely to gear up, gamble, or expand your farm!"
            )
            return



    @commands.command(name="gold_balance")
    async def balance(self, ctx):
        """Check your gold balance."""
        user = ctx.author
        gold = await self.config.user(user).gold()
        await ctx.send(f"💰 {user.mention}, you currently have **{gold} gold**.")
        
    @farm.command()
    async def fight(self, ctx):
        user_data = await self.config.user(ctx.author).all()
    
        # --- Random enemy name ---
        zombie_names_path = os.path.join(os.path.dirname(__file__), 'zombie_names.txt')
        with open(zombie_names_path, 'r') as file:
            zombie_names = [line.strip() for line in file.readlines()]
        enemy_name = random.choice(zombie_names)
    
        # --- Crit probability with diminishing returns (cap < 100%) ---
        def crit_probability(stat_value: int, scale: float = 50.0, max_prob: float = 0.95) -> float:
            p = 1.0 - math.exp(-float(stat_value) / float(scale))
            return min(p, max_prob)
    
        # --- Enemy stat generation helpers ---
        def scale_stat(base: int, is_boss: bool) -> int:
            base = max(1, int(base))
            if is_boss:
                return max(1, math.ceil(base * 1.20))  # +20% for bosses
            low  = max(1, math.floor(base * 0.70))    # ±10% for normal enemies
            high = max(low, math.ceil(base * 1.10))
            return random.randint(low, high)
    
        # Boss chance
        boss_chance = 0.15
        is_boss = random.random() < boss_chance
    
        # --- Build enemy as a reflection of the player's stats ---
        enemy_stats = {
            "strength":        scale_stat(user_data.get("strength", 1),        is_boss),
            "defense":         scale_stat(user_data.get("defense", 1),         is_boss),
            "speed":           scale_stat(user_data.get("speed", 1),           is_boss),
            "luck":            scale_stat(user_data.get("luck", 1),            is_boss),
            "Health":          scale_stat(user_data.get("Health", 10),         is_boss),
            "Critical_chance": scale_stat(user_data.get("Critical_chance", 1), is_boss),
        }
    
        # --- Levels (both use same formula now) ---
        stat_keys = ["strength", "defense", "speed", "luck", "Health", "Critical_chance"]
    
        # Player level
        player_avg = sum(user_data.get(k, 0) for k in stat_keys) / len(stat_keys)
        player_level = max(1, int(round(player_avg / 10.0)))
    
        # Enemy level
        enemy_avg = sum(enemy_stats[k] for k in stat_keys) / len(stat_keys)
        enemy_level = max(1, int(round(enemy_avg / 10.0)))
    
        # Precompute crit probabilities
        player_crit_p = crit_probability(user_data.get('Critical_chance', 0))
        enemy_crit_p  = crit_probability(enemy_stats.get('Critical_chance', 0))
    
        # --- Round loop ---
        round_messages = []
        round_count = 0
        start_life = user_data['Health']
        bad_start_life = enemy_stats['Health']
    
        # Heart styles
        enemy_full_heart = "💜" if is_boss else "💚"
        enemy_empty_heart = "🖤"
        player_full_heart = "❤️"

        # --- Tunables ---
        ROUND_PACING_STEP = 3   # every N rounds...
        ROUND_PACING_ADD  = 1   # ...add this much flat damage to both sides
        LEVEL_ADV_PER_LVL = 0.05  # ~5% per level gap
        MULT_MIN, MULT_MAX = 0.85, 1.15  # clamp total level advantage to ±15%
        
        def level_adv_multiplier(attacker_level: int, defender_level: int) -> float:
            mult = 1.0 + LEVEL_ADV_PER_LVL * (attacker_level - defender_level)
            return max(MULT_MIN, min(MULT_MAX, mult))
        
        def compute_damage(attacker_stats: dict, defender_stats: dict, round_count: int,
                           atk_level: int, def_level: int, crit_p: float) -> int:
            atk_roll = attacker_stats['strength'] + random.randint(1, attacker_stats['luck'])
            def_roll = defender_stats['defense'] + random.randint(1, defender_stats['speed'])
        
            # Base damage can never be lower than 1 (prevents stalemates)
            base = max(1, atk_roll - def_roll)
        
            # Gentle pacing to avoid never-ending fights (symmetric)
            pacing = (round_count // ROUND_PACING_STEP) * ROUND_PACING_ADD
        
            dmg = base + pacing
        
            # Small edge to the higher-level side
            dmg *= level_adv_multiplier(atk_level, def_level)
        
            # Single-roll crit: double damage
            if random.random() < crit_p:
                dmg *= 2
        
            return max(1, int(math.ceil(dmg)))

    
        while user_data['Health'] > 0 and enemy_stats['Health'] > 0:
            round_count += 1
    
            player_damage = compute_damage(user_data, enemy_stats, round_count,
                                           player_level, enemy_level, player_crit_p)
            enemy_damage  = compute_damage(enemy_stats, user_data, round_count,
                                           enemy_level, player_level, enemy_crit_p)
        
            user_data['Health']   -= enemy_damage
            enemy_stats['Health'] -= player_damage

    
            player_bar = self.hearts_bar(user_data['Health'], start_life, full=player_full_heart, empty="🖤", slots=10)
            enemy_bar  = self.hearts_bar(enemy_stats['Health'], bad_start_life, full=enemy_full_heart, empty=enemy_empty_heart, slots=10)
    
            # --- Headers with levels ---
            if is_boss:
                title = f"👑 BOSS Lv {enemy_level}: {enemy_name}"
                color = discord.Color.purple()
                enemy_header = f"👑 {enemy_name} (Lv {enemy_level})"
            else:
                title = f"Round {round_count} - {enemy_name} (Lv {enemy_level})"
                color = discord.Color.green()
                enemy_header = f"{enemy_name} (Lv {enemy_level})"
    
            player_header = f"{ctx.author.display_name} (Lv {player_level})"
    
            embed = discord.Embed(title=title, color=color)
            if is_boss:
                embed.set_author(name="An ominous presence looms...")
                embed.set_footer(text="Bosses are ~20% stronger ✨")
    
            embed.add_field(
                name=enemy_header,
                value=f"Damage Taken: **{player_damage}**\nHealth: {enemy_bar}",
                inline=False
            )
            embed.add_field(
                name=player_header,
                value=f"Damage Taken: **{enemy_damage}**\nHealth: {player_bar}",
                inline=False
            )
    
            round_messages.append(embed)
    
        # --- Outcome & persistence ---
        result = "won" if user_data['Health'] > 0 else "lost"
        rep_change = 1 if result == "won" else -1
        user_data['rep'] = max(1, user_data['rep'] + rep_change)
        user_data['Health'] = start_life
        await self.config.user(ctx.author).set(user_data)
    
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


    @commands.command()
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: int):
        """Pay another player some gold."""
        author = ctx.author

        if member.id == author.id:
            return await ctx.send("You cannot pay yourself.")
        if amount <= 0:
            return await ctx.send("Amount must be a positive number.")

        author_gold = await self.config.user(author).gold()

        if author_gold < amount:
            return await ctx.send("You don't have enough gold to complete this transaction.")

        # Deduct and add gold
        await self.config.user(author).gold.set(author_gold - amount)
        recipient_gold = await self.config.user(member).gold()
        await self.config.user(member).gold.set(recipient_gold + amount)

        await ctx.send(
            f"{author.mention} paid {humanize_number(amount)} gold to {member.mention}!"
        )
    
    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot or message.guild is None:
            return
    
        user = message.author
        now = int(time.time())
        data = await self.config.user(user).all()
    
        if now - data.get("last_activity", 0) < 60:  # 1-minute cooldown
            return
    
        await self.config.user(user).gold.set(data["gold"] + 1)
        await self.config.user(user).last_activity.set(now)

    @farm.command(name="payday")
    @commands.cooldown(1, 3600, commands.BucketType.user)  # 1 hour cooldown
    async def payday(self, ctx):
        """Claim your hourly payday, influenced by rep and luck."""
        user_data = await self.config.user(ctx.author).all()
    
        # Extract relevant stats
        rep = user_data.get("rep", 1)
        luck = user_data.get("luck", 1)
    
        # Base calculation with randomness
        base = 1 + rep
        luck_bonus = random.randint(0, int(luck/2))
    
        # Final amount with ceiling and floor
        payday_amount = base + luck_bonus
        payday_amount = max(100, min(payday_amount, 1000))  # Floor: 100, Ceiling: 1000
    
        # Update gold
        new_gold = user_data["gold"] + payday_amount
        await self.config.user(ctx.author).gold.set(new_gold)
    
        await ctx.send(
            f"💰 You received **{payday_amount:,}** gold based on your **Rep ({rep})** and **Luck ({luck})**!\n"
            f"Your new balance is **{new_gold:,}** gold."
        )

    
    @farm.command(name="richest")
    async def richest(self, ctx):
        """See the top 3 richest players by gold."""
        all_users = await self.config.all_users()
        
        # Sort users by gold
        sorted_users = sorted(
            all_users.items(),
            key=lambda x: x[1].get("gold", 0),
            reverse=True
        )

        top_3 = sorted_users[:3]
        if not top_3:
            await ctx.send("No data found.")
            return

        lines = []
        for idx, (user_id, data) in enumerate(top_3, start=1):
            user = self.bot.get_user(user_id)
            name = user.name if user else f"User {user_id}"
            lines.append(f"**#{idx}** - {name}: **{data['gold']:,}** gold")

        embed = discord.Embed(
            title="🏆 Top 3 Richest Farmers",
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    
    @farm.group(hidden=True)
    async def casino(self, ctx):
        """Play gambling games from your farm."""
        if ctx.invoked_subcommand is None:
            prefix = await self.bot.get_prefix(ctx.message)
            await ctx.send(
                f"🎰 **Welcome to the Farm Casino!** 🎲\n\n"
                f"Try your luck and grow your gold stash! Here are your options:\n"
                f"- `{prefix[0]}farm casino coinflip <bet> <heads/tails>` – 50/50 shot to double your gold.\n"
                f"- `{prefix[0]}farm casino dice <bet>` – Roll a die against the house. Highest roll wins.\n"
                f"- `{prefix[0]}farm casino slots <bet>` – Spin a 3x3 slot machine. Match symbols to win big.\n"
                f"- `{prefix[0]}farm casino roulette <bet> <call>` – Bet on colors, ranges, or numbers (0–36).\n\n"
                f"💡 Gold is shared with your farm balance. Don’t bet what you can’t grow back!\n"
                f"🧪 Try using your farm earnings to gamble smartly or recklessly – up to you!"
            )


    @casino.command()
    @commands.cooldown(1, 3, commands.BucketType.guild)
    async def coinflip(self, ctx, bet: float, call: str = None):
        """Flip a coin using your farm gold."""
        user = ctx.author
        gold = await self.config.user(user).gold()
    
        if not call:
            call = random.choice(["heads", "tails"])
    
        if call.lower() in ["head"]:
            call = "heads"
        elif call.lower() in ["tail"]:
            call = "tails"
    
        if call not in ["heads", "tails"]:
            return await ctx.send("❌ Invalid call. Please use `heads` or `tails`.")
    
        if bet <= 0 or bet > gold:
            return await ctx.send("❌ Invalid bet amount or insufficient gold.")
    
        message = await ctx.send("Flipping the coin... 🪙")
        await asyncio.sleep(1)
    
        # Coin outcome logic
        outcome = random.choices(["win", "lose"], weights=[48, 52])[0]
        if outcome == "win":
            final_flip = "🪙 Heads" if call == "heads" else "🪙 Tails"
        else:
            final_flip = "🪙 Tails" if call == "heads" else "🪙 Heads"
    
        result_text = f"You called **{call.capitalize()}**. "
        if outcome == "win":
            winnings = bet
            result_text += "You win! 🎉"
        else:
            winnings = -bet
            result_text += "You lost! 😢"
    
        new_gold = max(0, gold + winnings)
        await self.config.user(user).gold.set(new_gold)
    
        await message.edit(content=f"{final_flip}\n{result_text} New balance: **{new_gold:,.2f}** gold.")

    @casino.command()
    @commands.cooldown(1, 3, commands.BucketType.guild)
    async def dice(self, ctx, bet: float):
        """Roll a die against the house. Higher roll wins! Uses your farm gold."""
        user = ctx.author
        gold = await self.config.user(user).gold()
    
        if bet <= 0 or bet > gold:
            return await ctx.send("❌ Invalid bet amount or insufficient gold.")
    
        dice_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
        message = await ctx.send("🎲 Rolling dice... 🎲")
        
        # Simulate 3 pre-roll animations
        for _ in range(3):
            temp_player = random.choice(dice_emojis)
            temp_house = random.choice(dice_emojis)
            await message.edit(content=f"Player: {temp_player} | House: {temp_house}\nRolling...")
            await asyncio.sleep(0.5)
    
        # Final rolls
        player_roll = random.randint(1, 6)
        house_roll = random.choices([1, 2, 3, 4, 5, 6], weights=[5, 10, 15, 20, 25, 30])[0]  # House advantage
        player_emoji = dice_emojis[player_roll - 1]
        house_emoji = dice_emojis[house_roll - 1]
    
        # Outcome
        if player_roll > house_roll:
            winnings = bet * 2
            result_text = "You win! 🎉"
        else:
            winnings = -bet
            result_text = "You lost! 😢"
    
        new_gold = max(0, gold + winnings)
        await self.config.user(user).gold.set(new_gold)
    
        await message.edit(content=f"🎲 Player: {player_emoji} | House: {house_emoji}\n{result_text} New balance: **{new_gold:,.2f}** gold.")

    @casino.command()
    @commands.cooldown(1, 3, commands.BucketType.guild)
    async def slots(self, ctx, bet: float):
        """Play a 3x3 slot machine. Uses your farm gold."""
        user = ctx.author
        gold = await self.config.user(user).gold()
    
        if bet <= 0 or bet > gold:
            return await ctx.send("❌ Invalid bet amount or insufficient gold.")
    
        emojis = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎", "🌸"]
        weighted_emojis = (
            ["🍒"] * 8 + ["🍋"] * 15 + ["🍊"] * 18 + ["🍉"] * 20 +
            ["⭐"] * 22 + ["💎"] * 22 + ["🌸"] * 3 + ["🍍"] * 10
        )
    
        message = await ctx.send("🎰 Rolling the slots... 🎰")
    
        # Generate a real 3x3 grid
        grid = [[random.choice(weighted_emojis) for _ in range(3)] for _ in range(3)]
    
        # Simulated spin animation
        for _ in range(3):
            temp_grid = [[random.choice(emojis) for _ in range(3)] for _ in range(3)]
            temp_display = "\n".join(" | ".join(row) for row in temp_grid)
            await message.edit(content=f"{temp_display}\n🎰 Spinning...")
            await asyncio.sleep(0.3)
    
        display = "\n".join(" | ".join(row) for row in grid)
        flat_grid = [emoji for row in grid for emoji in row]
    
        payout = 0
        result_text = "You lost! 😢"
    
        # Reward logic
        if flat_grid.count("🍒") >= 2:
            payout = bet * 1.5
            result_text = "Two or more cherries! 🍒 You win 1.5x your bet!"
        if any(row.count(row[0]) == 3 for row in grid) or any(col.count(col[0]) == 3 for col in zip(*grid)):
            payout = max(payout, bet * 4)
            result_text = "Three of a kind in a row or column! 🎉 You win 4x your bet!"
        if flat_grid.count("🌸") == 3:
            payout = bet * 20
            result_text = "JACKPOT! 🌸🌸🌸 You hit the cherry blossoms jackpot!"
    
        if payout == 0:
            payout = -bet
    
        new_gold = max(0, gold + payout)
        await self.config.user(user).gold.set(new_gold)
    
        await message.edit(content=f"{display}\n{result_text} New balance: **{new_gold:,.2f}** gold.")

    @casino.command()
    @commands.cooldown(1, 3, commands.BucketType.guild)
    async def roulette(self, ctx, bet: float, call: str):
        """Play roulette. Bet on a number (0–36), red, black, even, odd, high, mid, or low. Uses your farm gold."""
        user = ctx.author
        gold = await self.config.user(user).gold()
    
        if bet <= 0 or bet > gold:
            return await ctx.send("❌ Invalid bet amount or insufficient gold.")
    
        call = call.lower()
        valid_calls = ["red", "black", "green", "even", "odd", "high", "mid", "low"] + [str(i) for i in range(0, 37)]
        if call not in valid_calls:
            return await ctx.send("❌ Invalid bet. Use a number (0–36) or one of: red, black, green, even, odd, high, mid, low.")
    
        # Spin logic
        number = random.randint(0, 36)
        red = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        black = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}
        color = "green" if number == 0 else "red" if number in red else "black"
        parity = "even" if number % 2 == 0 and number != 0 else "odd" if number != 0 else "neither"
    
        color_emoji = {
            "red": "🟥",
            "black": "⬛",
            "green": "🟩"
        }
    
        # Simulate spin animation
        message = await ctx.send("🎡 Spinning the roulette wheel...")
        for _ in range(3):
            temp_num = random.randint(0, 36)
            temp_color = "red" if temp_num in red else "black" if temp_num in black else "green"
            await message.edit(content=f"🎡 {color_emoji[temp_color]} {temp_num}\nSpinning...")
            await asyncio.sleep(0.5)
    
        result_text = f"🎡 {color_emoji[color]} {number}\n"
        payout = 0
    
        if call.isdigit():
            if int(call) == number:
                payout = bet * 17.5
                result_text += f"🎯 Direct hit! You win 17.5x your bet!"
        elif call == color:
            payout = bet
            result_text += f"✅ Correct color ({color.capitalize()})! You win 1x your bet."
        elif call in ["even", "odd"] and call == parity:
            payout = bet
            result_text += f"✅ Correct parity ({call})! You win 1x your bet."
        elif call == "low" and 1 <= number <= 12:
            payout = bet * 1.5
            result_text += "⬇️ Low (1–12)! You win 1.5x your bet."
        elif call == "mid" and 13 <= number <= 24:
            payout = bet * 1.5
            result_text += "↔️ Mid (13–24)! You win 1.5x your bet."
        elif call == "high" and 25 <= number <= 36:
            payout = bet * 1.5
            result_text += "⬆️ High (25–36)! You win 1.5x your bet."
        else:
            payout = -bet
            result_text += "❌ No match. You lost!"
    
        new_gold = max(0, gold + payout)
        await self.config.user(user).gold.set(new_gold)
    
        await message.edit(content=f"{result_text}\n💰 New balance: **{new_gold:.2f}** gold.")



    
    
    
    
