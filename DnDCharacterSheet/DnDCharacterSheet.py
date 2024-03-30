from redbot.core import commands, Config, data_manager
import random
import discord
import os
import asyncio
from collections import Counter 
from discord.ui import Button, View
from discord import ButtonStyle, Interaction
from discord import Embed
from discord import Color
from discord.utils import MISSING
from discord import ui
from discord.ui import Modal, TextInput

class CharacterSheetModal(Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_item(TextInput(label="Character Name", placeholder="Enter your character's name..."))
        self.add_item(TextInput(label="Class and Level", placeholder="Enter your character's class and level..."))
        self.add_item(TextInput(label="Race", placeholder="Enter your character's race..."))
        # Add more fields as needed for your D&D character sheet

    async def callback(self, interaction: discord.Interaction):
        # This method is called when the modal is submitted
        # Process and save the character sheet details here
        character_name = self.children[0].value
        class_and_level = self.children[1].value
        race = self.children[2].value
        # Process additional fields as needed

        await interaction.response.send_message(f"Character Sheet Created:\nName: {character_name}\nClass & Level: {class_and_level}\nRace: {race}", ephemeral=True)

class CharacterSheetView(View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Take from Stash Button
        self.sheet_button = Button(label="New Character", style=discord.ButtonStyle.green)
        self.sheet_button.callback = self.create_character_sheet_button
        self.add_item(self.sheet_button)

    @discord.ui.button(label="Create Character Sheet", style=discord.ButtonStyle.green, custom_id="create_character_sheet")
    async def create_character_sheet_button(self, button: Button, interaction: discord.Interaction):
        try:
            #modal = CharacterSheetModal(title="D&D Character Sheet")
            #await interaction.response.send_modal(modal)
            await interaction.response.send(f"I work")

        except Exception as e:
            await interaction.response.send(f"An error occurred: {str(e)}")




class GuildStashView(ui.View):
    def __init__(self, cog, ctx, guild_stash):
        super().__init__()
        self.cog = cog
        self.ctx = ctx
        self.potions = list(guild_stash.items())
        self.current_index = 0
        self.update_embed()
        
        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.grey)
        self.previous_button.callback = self.previous_potion
        self.add_item(self.previous_button)

        # Next Button
        self.next_button = Button(label="Next", style=discord.ButtonStyle.grey)
        self.next_button.callback = self.next_potion
        self.add_item(self.next_button)

        # Take from Stash Button
        self.take_button = Button(label="Take from Stash", style=discord.ButtonStyle.green)
        self.take_button.callback = self.take_from_stash
        self.add_item(self.take_button)

    def update_embed(self):
        if self.potions:
            potion_name, potion_details = self.potions[self.current_index]
            self.embed = Embed(title=f"{potion_name} (Quantity: {potion_details['quantity']})", color=Color.gold())
    
            # Iterate over each effect in the potion's details and add it as a field
            for effect in potion_details['effects']:
                self.embed.add_field(name=effect['name'], value=effect['text'], inline=False)
    
            self.embed.set_footer(text=f"Potion {self.current_index + 1} of {len(self.potions)}")
        else:
            self.embed = Embed(title="No potions available", description="You currently have no potions in your stash.", color=Color.red())


    async def previous_potion(self, interaction):
        if interaction.user != self.ctx.author:
            # Respond with a message that only the command issuer can use this button
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return
        # Decrement the index and update the embe
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.potions) - 1  # Loop back to the last potion
        self.update_embed()

        # Respond to the interaction by updating the message with the new embed
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def next_potion(self, interaction):
        if interaction.user != self.ctx.author:
            # Respond with a message that only the command issuer can use this button
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return
        # Increment the index and update the embed
        self.current_index = (self.current_index + 1) % len(self.potions)  # Loop back to the first potion
        self.update_embed()

        # Respond to the interaction by updating the message with the new embed
        await interaction.response.edit_message(embed=self.embed, view=self)


    async def take_from_stash(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            # Respond with a message that only the command issuer can use this button
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return
        potion_name, potion_details = self.potions[self.current_index]

        # Remove one potion from the guild stash
        potion_details['quantity'] -= 1
        if potion_details['quantity'] <= 0:
            self.potions.pop(self.current_index)
            if self.current_index > 0:
                self.current_index -= 1

        # Update the guild's stash in the config
        await self.cog.config.guild(self.ctx.guild).stash.set({potion_name: potion_details for potion_name, potion_details in self.potions if potion_details['quantity'] > 0})

        # Add the potion to the user's stash
        user_potions = await self.cog.config.member(interaction.user).potions()
        if potion_name in user_potions:
            user_potions[potion_name]['quantity'] += 1
        else:
            user_potions[potion_name] = {'quantity': 1, 'effects': potion_details['effects']}

        # Update the user's potions in the config
        await self.cog.config.member(interaction.user).potions.set(user_potions)

        # Update the embed to reflect changes
        self.update_embed()

        # Confirm the action to the user
        await interaction.response.edit_message(embed=self.embed, view=self)
        await interaction.followup.send(f"{interaction.user.mention} took one {potion_name} from the guild stash.")




class PotionView(View):
    def __init__(self, cog, ctx, member, potions,guild_potions, message=None):
        super().__init__()
        self.ctx = ctx
        self.member = member
        self.potions = potions
        self.guild_potions = potions
        self.current_index = 0
        self.cog = cog
        self.message = message  # The original message reference
        self.embed = MISSING  # Initialize the embed to MISSING
        self.update_embed()  # Update the embed with the first potion's details

        # Previous Button
        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.grey)
        self.previous_button.callback = self.previous_potion
        self.add_item(self.previous_button)

        # Next Button
        self.next_button = Button(label="Next", style=discord.ButtonStyle.grey)
        self.next_button.callback = self.next_potion
        self.add_item(self.next_button)

        self.give_to_guild_button = Button(label="Give to Guild", style=discord.ButtonStyle.blurple)
        self.give_to_guild_button.callback = self.give_to_guild
        self.add_item(self.give_to_guild_button)

    async def log(self, message: str):
        await self.ctx.send(message)

    async def previous_potion(self, interaction):
        if interaction.user != self.ctx.author:
            # Respond with a message that only the command issuer can use this button
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return
        # Decrement the index and update the embe
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.potions) - 1  # Loop back to the last potion
        self.update_embed()

        # Respond to the interaction by updating the message with the new embed
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def next_potion(self, interaction):
        if interaction.user != self.ctx.author:
            # Respond with a message that only the command issuer can use this button
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return
        # Increment the index and update the embed
        self.current_index = (self.current_index + 1) % len(self.potions)  # Loop back to the first potion
        self.update_embed()

        # Respond to the interaction by updating the message with the new embed
        await interaction.response.edit_message(embed=self.embed, view=self)

    
    def update_embed(self):
        if self.potions:
            potion_name, potion_details = self.potions[self.current_index]
            self.embed = Embed(title=f"{potion_name} (Quantity: {potion_details['quantity']})", color=Color.blue())
    
            # Iterate over each effect in the potion's details and add it as a field
            for effect in potion_details['effects']:
                self.embed.add_field(name=effect['name'], value=effect['text'], inline=False)
    
            self.embed.set_footer(text=f"Potion {self.current_index + 1} of {len(self.potions)}")
        else:
            self.embed = Embed(title="No potions available", description="You currently have no potions in your stash.", color=Color.red())


    async def give_to_guild(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            # Respond with a message that only the command issuer can use this button
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return
        await interaction.response.defer()  # Defer the response to have more time for processing.

        try:
            potion_name, potion_details = self.potions[self.current_index]
    
            # Decrease potion quantity in the user's stash.
            potion_details['quantity'] -= 1
    
            # Fetch the current guild stash.
            guild_stash = await self.cog.config.guild(interaction.guild).stash()
    
            # Add or update the potion in the guild's stash.
            if potion_name in guild_stash:
                guild_stash[potion_name]['quantity'] += 1
            else:
                guild_stash[potion_name] = {'quantity': 1, 'effects': potion_details['effects']}
    
            # Update the guild's stash in the config.
            await self.cog.config.guild(interaction.guild).stash.set(guild_stash)
    
            # If the potion's quantity has dropped to 0, remove it from the user's potions.
            if potion_details['quantity'] <= 0:
                self.potions.pop(self.current_index)
                if self.current_index > 0:  # Adjust the index if necessary.
                    self.current_index -= 1
    
            # Update the user's potions in the config.
            await self.cog.config.member(interaction.user).potions.set({potion_name: potion_details for potion_name, potion_details in self.potions if potion_details['quantity'] > 0})
    
            # Update the embed to reflect changes.
            self.update_embed()
    
            # Confirm the action to the user.
            await interaction.followup.send(f"{self.member.mention} gave one {potion_name} to the guild's stash.")
    
            # Edit the original message with the updated embed and view.
            await interaction.edit_original_response(embed=self.embed, view=self)
    
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")
    
    @discord.ui.button(label="Drink", style=ButtonStyle.green)
    async def drink(self, interaction: Interaction, button: Button):
        if interaction.user != self.ctx.author:
            # Respond with a message that only the command issuer can use this button
            await interaction.response.send_message("You cannot use this button.", ephemeral=True)
            return
        try:
            potion_name, potion_details = self.potions[self.current_index]
            potion_quantity = potion_details['quantity']
            potion_effects = potion_details['effects']
                #await interaction.response.send_message(f"{potion_name}\n{potion_details['effects']}\n {potion_effects}\n{potion_quantity}", view=self)
    
            potion_effects = "\n".join([f"{effect['name']}: {effect['text']}" for effect in potion_details['effects']])
    
            potion_details['quantity'] -= 1
        
            if potion_details['quantity'] <= 0:
                self.potions.pop(self.current_index)
                self.current_index = max(self.current_index - 1, 0)
                #await interaction.response.send_message(f"{potion_effects}")
            await self.cog.config.member(self.member).potions.set({potion_name: potion_details for potion_name, potion_details in self.potions})
    
            self.update_embed()
    
                
            await interaction.response.edit_message(embed=self.embed, view=self)
            await interaction.followup.send(f"{self.member.mention} drank {potion_name}!\nEffects:\n{potion_effects}")
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")




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
            "inventory": {},
            "potions":{}
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
    async def giveitem(self, ctx, member: discord.Member, *item_names: str):
        """Gives randomly effectuated items to a specified player"""
    
        # Read effects from TSV
        all_effects = await self.read_effects_tsv()
    
        # Check if item already exists in guild config
        guild_items = await self.config.guild(ctx.guild).items.all()
    
        for item_name in item_names:
            item_name = item_name.lower()  # Convert item name to lowercase
    
            if item_name in guild_items:
                item_effects = guild_items[item_name]
            else:
                # Pick 4 unique random effects for the new item
                item_effects = random.sample(all_effects, 4)
                # Save the new item with its effects to the guild config
                await self.config.guild(ctx.guild).items.set_raw(item_name, value=item_effects)
    
            # Add the item to the specified user's inventory
            user_inventory = await self.config.member(member).inventory.all()
    
            if item_name in user_inventory:
                # Item exists, increment the quantity
                user_inventory[item_name]['quantity'] += 1
            else:
                # New item, add with a quantity of 1 and its effects
                user_inventory[item_name] = {'quantity': 1, 'effects': item_effects}
    
            await self.config.member(member).inventory.set(user_inventory)
    
        await ctx.send(f"{member.display_name} has been given the items: {', '.join(item_names)}!")




    
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
            # Construct a list of strings with each item's name and quantity
            inventory_list = [f"{item_name} (x{details['quantity']})" for item_name, details in user_inventory.items()]
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


    @dnd.command(name="clearpotions")
    @commands.is_owner()
    async def clear_potions(self, ctx, member: discord.Member):
        """Clear the entire inventory of a specified player"""
        await self.config.member(member).potions.clear()
        await ctx.send(f"{member.display_name}'s potions has been cleared.")

    @dnd.command(name="deletepotion")
    @commands.is_owner()
    async def delete_potions(self, ctx, member: discord.Member, *, item_name: str):
        """Delete a specific item from a player's inventory"""
        user_inventory = await self.config.member(member).potions()
        if item_name in user_inventory:
            del user_inventory[item_name]
            await self.config.member(member).potions.set(user_inventory)
            await ctx.send(f"Item '{item_name}' has been removed from {member.display_name}'s potions.")
        else:
            await ctx.send(f"{member.display_name} does not have an item named '{item_name}'.")
            
    @dnd.command(name="eatitem")
    async def eat_item(self, ctx, *, item_name: str):
        """Eat an item from your inventory, decrementing its quantity and showing its first effect."""
        user_inventory = await self.config.member(ctx.author).inventory()
    
        if item_name in user_inventory:
            item_details = user_inventory[item_name]
            item_effects = item_details.get('effects', [])
            
            if item_effects:
                # Assuming item_effects is a list of effects and you want to show the first one
                first_effect = item_effects[0]
                await ctx.send(f"{ctx.author.display_name} eats the {item_name} and experiences: {first_effect.get('Name', 'Unnamed Effect')}, {first_effect.get('Effect', 'No description available')}, for {first_effect.get('Duration', 'Unknown duration')} (when used in a potion), Notes: {first_effect.get('Notes', 'N/A')}")
            else:
                await ctx.send(f"The {item_name} seems to have no effects.")
    
            # Decrement the item's quantity
            item_details['quantity'] -= 1
    
            # If the quantity is now 0, remove the item from the inventory
            if item_details['quantity'] <= 0:
                del user_inventory[item_name]
            
            # Update the user's inventory in the config
            await self.config.member(ctx.author).inventory.set(user_inventory)
    
        else:
            await ctx.send(f"You don't have an item named '{item_name}' in your inventory.")


    @dnd.command(name="brew")
    async def brew(self, ctx, *item_names: str):
        """Brew a potion using items from your inventory, using up to three of the most shared effects, and add or update it in your potions with effect text and adjusted quantity."""

        # Convert all items in the list to lowercase
        item_names = [item.lower() for item in item_names]
        
        if len(item_names) < 1:
            await ctx.send("Can't make a potion with only one ingredent!")
            return
        
        user_data = await self.config.member(ctx.author).all()
    
        # Ensure the potions key exists in user_data
        if 'potions' not in user_data:
            user_data['potions'] = {}
    
        # Check for missing or insufficient items
        inventory = user_data.get('inventory', {})
        missing_or_insufficient_items = [
            item for item in item_names
            if item not in inventory or inventory[item]['quantity'] < 1
        ]
    
        if missing_or_insufficient_items:
            await ctx.send(f"Brewing failed, missing: {', '.join(missing_or_insufficient_items)}")
            return
    
        all_effects = []  # Store tuples of (effect_name, effect_text)
        for item_name in item_names:
            item_details = inventory.get(item_name, {})
            item_effects = item_details.get('effects', [])
            for effect in item_effects:
                effect_name = effect.get('Name', 'Unnamed Effect')
                effect_text = effect.get('Effect', 'No description available')
                all_effects.append((effect_name, effect_text))
    
            # Decrement the used ingredient's quantity
            inventory[item_name]['quantity'] -= 1
            # Remove the ingredient from the inventory if the quantity is now 0
            if inventory[item_name]['quantity'] == 0:
                del inventory[item_name]
    
        # Update the user's inventory after using items
        user_data['inventory'] = inventory
    
        # Process effects to find the most common ones for the new potion
        effect_counts = Counter([effect_name for effect_name, _ in all_effects])
        most_common_effects = effect_counts.most_common()
        highest_count = most_common_effects[0][1] if most_common_effects else 0
        
    
        # Get tuples of all effects that share the highest count
        final_effects = [effect for effect in all_effects if effect_counts[effect[0]] == highest_count]
    
        # Limit to the top 3 most common effects
        if len(final_effects) > 3:
            final_effects = random.sample(final_effects, 3)
        if highest_count < 2:
            final_effects = None
    
        if final_effects:
            potion_effects_data = [{'name': name, 'text': text} for name, text in final_effects]
            potion_name = "Potion of " + " and ".join(name for name, _ in final_effects)
    
            # Update potion quantity or add a new potion
            if potion_name in user_data['potions']:
                user_data['potions'][potion_name]['quantity'] += 1
            else:
                user_data['potions'][potion_name] = {
                    'effects': potion_effects_data,
                    'quantity': 1
                }
    
            await ctx.send(f"Successfully brewed {potion_name} with effects: {', '.join(name for name, _ in final_effects)}")
        else:
            await ctx.send("Brewing failed. The ingredients share no common effects.")
    
        # Save the updated user data
        await self.config.member(ctx.author).set(user_data)



    @dnd.command(name="clearstash")
    @commands.guild_only()  # Ensure this command is only usable within a guild
    @commands.has_permissions(administrator=True)  # Restrict to users with the Administrator permission
    async def clear_stash(self, ctx):
        # Set the guild's stash to an empty dictionary, effectively clearing it
        await self.config.guild(ctx.guild).stash.set({})
        
        # Send a confirmation message
        await ctx.send("The guild stash has been cleared.")


    @dnd.command(name="viewpotions")
    async def view_potions(self, ctx):
        
        member = ctx.author
        guild = ctx.guild
    
        member_potions = await self.config.member(member).potions()
        guild_potions = await self.config.guild(guild).stash()
    
        if not member_potions:
            await ctx.send(f"{member.display_name}'s potion stash is empty.")
            return
    
        potions_list = list(member_potions.items())
    
        # Check if there are potions in the list
        if potions_list:
            potion_name, potion_details = potions_list[0]  # Get the first potion's details
            initial_embed = Embed(title=f"{potion_name} (Quantity: {potion_details['quantity']})", color=Color.blue())
    
            # Add each effect as a separate field in the embed
            for effect in potion_details['effects']:
                initial_embed.add_field(name=effect['name'], value=effect['text'], inline=False)
    
            initial_embed.set_footer(text=f"Potion 1 of {len(potions_list)}")
        else:
            # No potions available
            initial_embed = Embed(title="No potions available", description="You currently have no potions in your stash.", color=Color.red())
        
        # Send the initial message
        message = await ctx.send(embed=initial_embed)
    
        # Instantiate PotionView with the message reference
        view = PotionView(self, ctx, member, potions_list, guild_potions, message=message)
        await message.edit(embed=initial_embed, view=view)  # Make sure the view is attached to the message


    @dnd.command(name="viewguildstash")
    async def view_guild_stash(self, ctx):
        guild_stash = await self.config.guild(ctx.guild).stash()  # Fetch the guild stash
    
        # Initialize and send the GuildStashView
        view = GuildStashView(self, ctx, guild_stash)
        message = await ctx.send(embed=view.embed, view=view)

    @dnd.command(name="clearallinventories")
    @commands.has_permissions(administrator=True)  # Ensure only administrators can run this
    async def clear_all_inventories(self, ctx):
        # Confirm before proceeding
        async with ctx.typing():
            for member in ctx.guild.members:
                # Skip bots
                if member.bot:
                    continue
    
                # Clear each member's inventory
                await self.config.member(member).inventory.clear()
    
            await ctx.send("All member inventories have been cleared.")

    @dnd.command()
    async def create_character(self, ctx: commands.Context):
        """Sends a button to the user to create a new D&D character sheet."""
        view = CharacterSheetView()
        await ctx.send("Click the button below to create your D&D character sheet:", view=view)







