import json
import random
from pathlib import Path
import discord
from redbot.core import app_commands, commands, Config

class alchemy(commands.Cog):
    """Skyrim-style Alchemy game with file-based configuration, custom string names, and public alerts."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210, force_registration=True
        )
        
        default_guild = {
            "alert_channel": None,
            "discovered_potions": []
        }
        self.config.register_guild(**default_guild)
        
        # Load data files from cog directory
        self.path = Path(__file__).parent
        self.effects_data = self.load_json("effects.json")
        self.words_data = self.load_json("ingredient_words.json")

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
        
        # Use the exact user string (properly capitalized) as the ingredient name
        name = seed_text.strip().title()
        
        # Pick 1 effect from each tier using the file pools
        effects = [
            rng.choice(self.effects_data.get("common", ["Restore Health"])),
            rng.choice(self.effects_data.get("rare", ["Fortify Attack"])),
            rng.choice(self.effects_data.get("epic", ["Cure Disease"])),
            rng.choice(self.effects_data.get("legendary", ["Absorb Health"]))
        ]
        rng.shuffle(effects)
        
        return name, effects

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
        
        # Pick a random combo
        adj = random.choice(adjectives)
        noun = random.choice(nouns)
        generated_name = f"{adj} {noun}"
        
        # Evaluate its effects so the user can see what it does
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
        common_effect = effects[0]  # First effect is common

        embed = discord.Embed(
            title="🍽️ Experimental Tasting",
            description=f"{interaction.user.mention} takes a bold bite out of **{name}**...",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="👅 Effect Discovered!", 
            value=f"Their tongue tingles as they realize this ingredient possesses the **{common_effect}** property.", 
            inline=False
        )
        
        # Public response as requested
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
        await interaction.response.defer(thinking=False) # Public processing

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
        embed.add_field(name="Ingredients Combined by " + interaction.user.display_name, value=ing_desc, inline=False)

        if not shared_effects:
            embed.color = discord.Color.red()
            embed.add_field(name="Result", value="💥 **Ruined Mixture!** These ingredients share no common properties, resulting in a useless fizzing sludge.", inline=False)
            await interaction.followup.send(embed=embed)
            return

        potion_effects = sorted(list(shared_effects))
        potion_name = f"Potion of {' & '.join(potion_effects)}"
        
        embed.color = discord.Color.green()
        embed.add_field(name="Result", value=f"✨ **Successfully brewed {potion_name}!**", inline=False)

        # First Discovery Check
        guild_data = await self.config.guild(interaction.guild).all()
        discovered_list = guild_data["discovered_potions"]

        if potion_name not in discovered_list:
            discovered_list.append(potion_name)
            await self.config.guild(interaction.guild).discovered_potions.set(discovered_list)

            embed.add_field(name="🏆 Milestone", value="**First Time Discovery!**", inline=False)

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

        await interaction.followup.send(embed=embed)
