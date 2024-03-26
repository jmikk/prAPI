from redbot.core import commands, Config
import random
import discord

class DnDCharacterSheet(commands.Cog):
    """Gives items to players with random effects"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="9003s_guild_items", force_registration=True)

        default_guild = {
            "items": {},
            "stash": {}
        }

        default_member = {
            "inventory": {}
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

    async def read_effects_tsv(self, filepath):
        effects = []
        with open(filepath, 'r') as file:
            for line in file:
                parts = line.strip().split('\t')
                if len(parts) == 4:  # Ensure there are exactly 4 columns
                    effects.append({
                        "Name": parts[0],
                        "Effect": parts[1],
                        "Duration": parts[2],
                        "Notes": parts[3]
                    })
        return effects

    @commands.guild_only()
    @commands.command()
    @commands.has_role("@Last Light (DM)")
    async def giveitem(self, ctx, member: discord.Member, item_name: str):
        """Gives a randomly effectuated item to a specified player"""
        
        # Read effects from TSV
        effects_filepath = '/path/to/effects.tsv'  # Adjust the path to your effects.tsv file
        all_effects = await self.read_effects_tsv(effects_filepath)

        # Check if item already exists in guild config
        guild_items = await self.config.guild(ctx.guild).items.all()
        
        if item_name in guild_items:
            item_effects = guild_items[item_name]
        else:
            # Pick 4 unique random effects for the new item
            item_effects = random.sample(all_effects, 4)
            # Save the new item with its effects to the guild config
            await self.config.guild(ctx.guild).items.set_raw(item_name, value=item_effects)

        # Add the item to the specified user's inventory
        user_inventory = await self.config.member(member).inventory.all()
        user_inventory[item_name] = item_effects
        await self.config.member(member).inventory.set(user_inventory)

        await ctx.send(f"{member.display_name} has been given the item: {item_name} with unique effects!")
