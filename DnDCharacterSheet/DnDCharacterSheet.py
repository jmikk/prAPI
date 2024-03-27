from redbot.core import commands, Config, data_manager
import random
import discord
import os
import asyncio
from collections import Counter  # Make sure to add this line

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

    # Command group for D&D related commands
    @commands.group(name="D&D")
    async def dnd(self, ctx):
        """D&D Commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Type `help D&D` for more information on D&D commands.")


    async def read_effects_tsv(self):
        effects = []
        # Construct the path to your effects.tsv file within the cog's data directory
        effects_filepath = os.path.join(data_manager.cog_data_path(self), 'effects.tsv')
        
        with open(effects_filepath, 'r') as file:
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

    @dnd.command(name="giveitem")
    @commands.has_role("Last Light (DM)")
    async def giveitem(self, ctx, member: discord.Member, item_name: str):
        """Gives a randomly effectuated item to a specified player"""

        # Read effects from TSV
        all_effects = await self.read_effects_tsv()

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

        await ctx.send(f"{member.display_name} has been given the item: {item_name} with {item_effects}!")

    
    async def paginate_inventory(self, ctx, inventory, member):
        """Sends paginated embeds of the inventory items."""
        items_per_page = 10
        pages = [inventory[i:i + items_per_page] for i in range(0, len(inventory), items_per_page)]

        def get_embed(page_index):
            embed = discord.Embed(title=f"{member.display_name}'s Inventory", color=discord.Color.blue())
            page = pages[page_index]
            for item in page:
                embed.add_field(name=item, value="\u200b", inline=False)
            embed.set_footer(text=f"Page {page_index + 1}/{len(pages)}")
            return embed

        current_page = 0
        message = await ctx.send(embed=get_embed(current_page))

        # Reaction controls
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

                if str(reaction.emoji) == "▶️" and current_page < len(pages) - 1:
                    current_page += 1
                    await message.edit(embed=get_embed(current_page))
                    await message.remove_reaction(reaction, user)
                elif str(reaction.emoji) == "◀️" and current_page > 0:
                    current_page -= 1
                    await message.edit(embed=get_embed(current_page))
                    await message.remove_reaction(reaction, user)
                else:
                    await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

    @dnd.command(name="viewinventory")
    async def viewinventory(self, ctx, member: discord.Member = None):
        """View the inventory of a specified user, or your own if no user is specified."""

        if not member:
            member = ctx.author

        user_inventory = await self.config.member(member).inventory()

        if user_inventory:
            inventory_list = list(user_inventory.keys())
            await self.paginate_inventory(ctx, inventory_list, member)
        else:
            await ctx.send(f"{member.display_name} has no items in their inventory.")

    @dnd.command(name="clearinventory")
    @commands.is_owner()
    async def clear_inventory(self, ctx, member: discord.Member):
        """Clear the entire inventory of a specified player"""
        await self.config.member(member).inventory.clear()
        await ctx.send(f"{member.display_name}'s inventory has been cleared.")

    @dnd.command(name="deleteitem")
    @commands.is_owner()
    async def delete_item(self, ctx, member: discord.Member, *, item_name: str):
        """Delete a specific item from a player's inventory"""
        user_inventory = await self.config.member(member).inventory()
        if item_name in user_inventory:
            del user_inventory[item_name]
            await self.config.member(member).inventory.set(user_inventory)
            await ctx.send(f"Item '{item_name}' has been removed from {member.display_name}'s inventory.")
        else:
            await ctx.send(f"{member.display_name} does not have an item named '{item_name}'.")

    @dnd.command(name="eatitem")
    async def eat_item(self, ctx, *, item_name: str):
        """Eat an item from your inventory, deleting it and showing its first effect."""
        user_inventory = await self.config.member(ctx.author).inventory()

        if item_name in user_inventory:
            item_effects = user_inventory[item_name]
            if item_effects:
                # Assuming item_effects is a list of effects and you want to show the first one
                first_effect = item_effects[0]
                await ctx.send(f"{ctx.author.display_name} eats the {item_name} and experiences: {first_effect['Name']}, {first_effect['Effect']}, for {first_effect['Duration']} (when used in a potion), Notes: {first_effect['Notes']} ")
            else:
                await ctx.send(f"The {item_name} seems to have no effects.")

            # Delete the item from the inventory after "eating" it
            del user_inventory[item_name]
            await self.config.member(ctx.author).inventory.set(user_inventory)
        else:
            await ctx.send(f"You don't have an item named '{item_name}' in your inventory.")




    @dnd.command(name="brew")
    async def brew(self, ctx, *item_names: str):
        """Brew a potion using items from your inventory, using the most shared effect."""
        user_inventory = await self.config.member(ctx.author).inventory()
    
        # Check if all specified items are in the user's inventory
        missing_items = [item for item in item_names if item not in user_inventory]
        if missing_items:
            await ctx.send(f"Brewing failed, missing: {', '.join(missing_items)}")
            return
    
        all_effect_names = []
        # Loop through each specified item, collect its effects' names, and remove it from the inventory
        for item_name in item_names:
            item_effects = user_inventory.get(item_name, [])
            for effect in item_effects:
                # Assuming each effect is a dictionary with a 'name' key
                effect_name = effect.get('Name', 'Unnamed Effect')
                all_effect_names.append(effect_name)
    
            # Remove the used item from the inventory
            #del user_inventory[item_name]
    
        # Save the updated inventory back to the config
        #await self.config.member(ctx.author).inventory.set(user_inventory)
    
        # Count the effects and find the most common one(s)
        effect_counts = Counter(all_effect_names)
        most_common_effects = effect_counts.most_common()
        highest_count = most_common_effects[0][1] if most_common_effects else 0
    
        # Get all effects that share the highest count
        final_effects = [effect for effect, count in most_common_effects if count == highest_count]
        if len(final_effects) > 3:
            final_effects = random.sample(final_effects, 3)
    
        if final_effects:
            # Create a potion with the most shared effect(s)
            potion_name = "Potion of " + " and ".join(final_effects)
            await ctx.send(f"Successfully brewed a potion with the following effects: {', '.join(final_effects)}")
        else:
            await ctx.send("Brewing failed. The ingredients share no common effects.")

        
        
    
    
