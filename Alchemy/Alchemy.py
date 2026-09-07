import json
import random
from pathlib import Path
import discord
from redbot.core import app_commands, commands, Config

class Alchemy(commands.Cog):
    """Skyrim-style Alchemy game with EXP levels, scaling actions, file configuration, and lightweight leaderboard."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210, force_registration=True
        )
        
        default_guild = {
            "alert_channel": None,
            "discovered_potions": [],
            "players": {} # Format: {str(user_id): {"name": "Username", "exp": 0, "unlocked": []}}
        }
        self.config.register_guild(**default_guild)
        
        # Load data files from cog directory
        self.path = Path(__file__).parent
        self.effects_data = self.load_json("effects.json")
        self.words_data = self.load_json("ingredient_words.json")
        self.effect_lines_data = self.load_json("Effect_lines.json")

    def load_json(self, filename: str):
        file_path = self.path / filename
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # --- Helper: Generate Ingredient from User String ---
    def generate_ingredient(self, seed_text: str):
        clean_seed = seed_text.strip().lower()
        rng = random.Random(clean_seed)
        
        name = seed_text.strip().title()
        
        effects = [
            rng.choice(self.effects_data.get("common", ["Restore Health"])),
            rng.choice(self.effects_data.get("rare", ["Fortify Attack"])),
            rng.choice(self.effects_data.get("epic", ["Cure Disease"])),
            rng.choice(self.effects_data.get("legendary", ["Absorb Health"]))
        ]
        rng.shuffle(effects)
        
        return name, effects

    # --- Leveling Math Helpers ---
    def get_level_and_progress(self, exp: int):
        """Calculates level using an escalating curve where each level takes longer."""
        level = 1
        exp_needed = 100  # EXP required to reach level 2
        
        while exp >= exp_needed:
            exp -= exp_needed
            level += 1
            exp_needed = int(exp_needed * 1.35)  # Each level scales up by 35%
            
        return level, exp, exp_needed

    async def add_exp(self, guild: discord.Guild, user: discord.abc.User, amount: int):
        guild_data = await self.config.guild(guild).all()
        players = guild_data["players"]
        user_id_str = str(user.id)

        if user_id_str not in players:
            players[user_id_str] = {"name": user.display_name, "exp": 0, "unlocked": []}

        players[user_id_str]["exp"] += amount
        players[user_id_str]["name"] = user.display_name  # Keep name updated
        await self.config.guild(guild).players.set(players)

    # --- Configuration Commands ---
    @commands.group(name="alchemy")
    @commands.admin_or_permissions(manage_guild=True)
    async def alchemy(self, ctx):
        """Alchemy game configuration."""
        pass

    @alchemy.command(name="channel")
    async def alchemy_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel where 'first discovery' alerts are broadcasted."""
        await self.config.guild(ctx.guild).alert_channel.set(channel.id)
        await ctx.send(f"✅ Alchemy discovery alerts will now be sent to {channel.mention}.")

    # --- Slash Command: Random Ingredient Generator ---
    @app_commands.command(name="randomingredient", description="Generates a random ingredient name using words from the file list.")
    async def randomingredient(self, interaction: discord.Interaction):
        adjectives = self.words_data.get("adjectives", ["Mystic"])
        nouns = self.words_data.get("nouns", ["Herb"])
        
        adj = random.choice(adjectives)
        noun = random.choice(nouns)
        generated_name = f"{adj} {noun}"
        
        name, effects = self.generate_ingredient(generated_name)
        
        embed = discord.Embed(
            title="🌿 Foraged Random Ingredient",
            description=f"You scout the wilderness and find: **{name}**",
            color=discord.Color.teal()
        )
        embed.add_field(name="Tip", value=f"You can use `{name}` as a seed in `/brew` or test it out with `/eat`!", inline=False)
        
        await interaction.response.send_message(embed=embed)

    # --- Slash Command: Eat Ingredient ---
    @app_commands.command(name="eat", description="Eat an ingredient to publicly taste and discover its primary common effect!")
    @app_commands.describe(ingredient="The text seed/name of the ingredient you want to eat")
    async def eat(self, interaction: discord.Interaction, ingredient: str):
        name, effects = self.generate_ingredient(ingredient)
        common_effect = effects[0]

        # Give a small amount of EXP for tasting/eating
        await self.add_exp(interaction.guild, interaction.user, 15)

        tasting_templates = self.effect_lines_data.get("tasting_lines", [
            "Their tongue tingles as they realize this ingredient possesses the **{effect}** property."
        ])
        tasting_message = random.choice(tasting_templates).format(effect=common_effect)

        embed = discord.Embed(
            title="🍽️ Experimental Tasting",
            description=f"{interaction.user.mention} takes a bold bite out of **{name}**...",
            color=discord.Color.orange()
        )
        embed.add_field(name="👅 Effect Discovered!", value=tasting_message, inline=False)
        embed.set_footer(text="+15 EXP gained!")
        
        await interaction.response.send_message(embed=embed)

    # --- Slash Command: Brew Potion ---
    @app_commands.command(name="brew", description="Mix up to 4 custom ingredient text seeds to brew a potion!")
    @app_commands.describe(
        ing1="First ingredient",
        ing2="Second ingredient (optional)",
        ing3="Third ingredient (optional)",
        ing4="Fourth ingredient (optional)"
    )
    async def brew(
        self, 
        interaction: discord.Interaction, 
        ing1: str, 
        ing2: str = None, 
        ing3: str = None, 
        ing4: str = None
    ):
        await interaction.response.defer(thinking=False)

        seeds = [s for s in [ing1, ing2, ing3, ing4] if s]
        if len(seeds) < 2:
            await interaction.followup.send("❌ You need to mix at least **2 ingredients** to brew a potion!")
            return

        ingredients = []
        for seed in seeds:
            name, effects = self.generate_ingredient(seed)
            ingredients.append({"seed": seed, "name": name, "effects": effects})

        # Skyrim Intersection Logic
        shared_effects = set(ingredients[0]["effects"])
        for ing in ingredients[1:]:
            shared_effects.intersection_update(ing["effects"])

        embed = discord.Embed(title="🧪 Alchemy Workbench", color=discord.Color.dark_purple())
        ing_desc = "\n".join([f"• **{i['name']}**" for i in ingredients])
        embed.add_field(name=f"Ingredients Combined by {interaction.user.display_name}", value=ing_desc, inline=False)

        # Handle Failed Brew
        if not shared_effects:
            # Failing awards slightly more EXP than eating (e.g., 30 EXP) for effort
            exp_gained = 30
            await self.add_exp(interaction.guild, interaction.user, exp_gained)

            embed.color = discord.Color.red()
            embed.add_field(name="Result", value="💥 **Ruined Mixture!** These ingredients share no common properties, resulting in a useless fizzing sludge.", inline=False)
            embed.set_footer(text=f"+{exp_gained} EXP (Valuable learning experience through failure!)")
            await interaction.followup.send(embed=embed)
            return

        # Successful Brew - Calculate Rarity-Based EXP
        potion_effects = sorted(list(shared_effects))
        potion_name = f"Potion of {' & '.join(potion_effects)}"
        
        # Determine base EXP scaling based on what tiers are present in the shared effects
        rarity_bonus = 50
        all_effects_pool = self.effects_data
        for eff in shared_effects:
            if eff in all_effects_pool.get("legendary", []):
                rarity_bonus += 200
            elif eff in all_effects_pool.get("epic", []):
                rarity_bonus += 100
            elif eff in all_effects_pool.get("rare", []):
                rarity_bonus += 50
            else:
                rarity_bonus += 20

        embed.color = discord.Color.green()
        embed.add_field(name="Result", value=f"✨ **Successfully brewed {potion_name}!**", inline=False)

        # Check First Discovery & Track Unlocked Unique Potions for Player
        guild_data = await self.config.guild(interaction.guild).all()
        discovered_list = guild_data["discovered_potions"]
        players = guild_data["players"]
        user_id_str = str(interaction.user.id)

        if user_id_str not in players:
            players[user_id_str] = {"name": interaction.user.display_name, "exp": 0, "unlocked": []}

        is_first_ever_server_discovery = potion_name not in discovered_list
        user_unlocked = players[user_id_str]["unlocked"]
        
        # Only grant big EXP the *first time this specific user* makes this unique potion
        if potion_name not in user_unlocked:
            user_unlocked.append(potion_name)
            players[user_id_str]["unlocked"] = user_unlocked

        if is_first_ever_server_discovery:
            discovered_list.append(potion_name)
            await self.config.guild(interaction.guild).discovered_potions.set(discovered_list)
            
            # Massive EXP bonus for server-first discovery!
            rarity_bonus += 500
            embed.add_field(name="🏆 Milestone", value="**First Time Discovery in this Realm! (+500 Bonus EXP)**", inline=False)

            alert_chan_id = guild_data["alert_channel"]
            if alert_chan_id:
                channel = interaction.guild.get_channel(alert_chan_id)
                if channel:
                    alert_embed = discord.Embed(
                        title="🚨 New Potion Discovered!",
                        description=f"{interaction.user.mention} has discovered **{potion_name}** for the very first time in this realm!",
                        color=discord.Color.gold()
                    )
                    await channel.send(embed=alert_embed)

        # Commit final EXP
        await self.add_exp(interaction.guild, interaction.user, rarity_bonus)
        embed.set_footer(text=f"✨ Successfully brewed! +{rarity_bonus} EXP gained.")

        await interaction.followup.send(embed=embed)

    # --- Slash Command: Leaderboard (Ranked by Level) ---
    @app_commands.command(name="leaderboard", description="View the top alchemists in the realm ranked by their level and EXP!")
    async def leaderboard(self, interaction: discord.Interaction):
        guild_data = await self.config.guild(interaction.guild).all()
        players = guild_data.get("players", {})

        if not players:
            await interaction.response.send_message("🧪 No one has brewed any potions or eaten ingredients yet! Use `/brew` or `/eat`.", ephemeral=False)
            return

        # Pre-calculate levels for sorting
        processed_players = []
        for user_id, data in players.items():
            lvl, cur_exp, req_exp = self.get_level_and_progress(data["exp"])
            processed_players.append({
                "name": data["name"],
                "level": lvl,
                "exp": data["exp"],
                "cur_exp": cur_exp,
                "req_exp": req_exp
            })

        # Sort primarily by Level (descending), then by total EXP (descending)
        sorted_players = sorted(processed_players, key=lambda x: (x["level"], x["exp"]), reverse=True)

        embed = discord.Embed(
            title="🏆 Realm Alchemist Leaderboard",
            description="Ranked by Alchemist Level and Experience.",
            color=discord.Color.gold()
        )

        leaderboard_text = ""
        for rank, p in enumerate(sorted_players[:10], start=1):
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            icon = medals.get(rank, f"`{rank}.`")
            leaderboard_text += f"{icon} **{p['name']}** — Level **{p['level']}** (`{p['cur_exp']}/{p['req_exp']} EXP`)\n"

        embed.add_field(name="Top Alchemists", value=leaderboard_text, inline=False)
        embed.set_footer(text="Experiment with /brew, /eat, and discover rare effects to level up!")

        await interaction.response.send_message(embed=embed)
