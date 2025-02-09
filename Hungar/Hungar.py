from redbot.core import commands, Config
import random
import asyncio
from datetime import datetime, timedelta
import os
import discord
from discord.ext.commands import CheckFailure
from discord.ui import View, Button, Modal, Select, TextInput
from discord import Interaction, TextStyle, SelectOption
import aiofiles
import traceback
from discord.utils import get

class CheckGoldButton(Button):
    """Button to display the user's current gold"""

    def __init__(self, cog):
        super().__init__(label="Check gold", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        try:
            user_id = interaction.user
            gold = await self.cog.config.user(user_id).gold()
            await interaction.response.send_message(f"You have {gold} gold.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

        

class ViewAllTributesButton(Button):
    """Button to display all tribute stats in one embed."""
    def __init__(self, cog, guild):
        super().__init__(label="View All Tributes", style=discord.ButtonStyle.secondary)
        self.cog = cog
        self.guild = guild

    async def callback(self, interaction: Interaction):
        """Shows all tributes' stats in a formatted embed."""
        config = await self.cog.config.guild(self.guild).all()
        players = config["players"]

        if not players:
            await interaction.response.send_message("No tributes are currently in the game.", ephemeral=True)
            return

        # Sort players by district
        sorted_players = sorted(players.values(), key=lambda p: p["district"])

        embed = discord.Embed(
            title="🏹 **Hunger Games Tributes** 🏹",
            description="Here are the current tributes and their stats:",
            color=discord.Color.gold()
        )

        for player in sorted_players:
            status = "🟢 **Alive**" if player["alive"] else "🔴 **Eliminated**"
            embed.add_field(
                name=f"District {player['district']}: {player['name']}",
                value=(
                    f"{status}\n"
                    f"**🛡️ Def:** {player['stats']['Def']}\n"
                    f"**⚔️ Str:** {player['stats']['Str']}\n"
                    f"**💪 Con:** {player['stats']['Con']}\n"
                    f"**🧠 Wis:** {player['stats']['Wis']}\n"
                    f"**❤️ HP:** {player['stats']['HP']}"
            ))

        await interaction.response.send_message(embed=embed, ephemeral=True)



class GameMasterView(View):
    """View for GameMasters to trigger events."""
    def __init__(self, cog, guild, public_channel):
        super().__init__(timeout=None)  # Persistent until game ends
        self.cog = cog
        self.guild = guild
        self.public_channel = public_channel  # Store public channel for messages

        # Add buttons for global events
        self.add_item(GameMasterEventButton(cog, guild, "Fog Descends",public_channel))
        self.add_item(GameMasterEventButton(cog, guild, "Arena Shrinks",public_channel))
        self.add_item(GameMasterEventButton(cog, guild, "Heatwave Strikes",public_channel))
        
        # Add buttons for targeted sponsorships
        self.add_item(SponsorRandomTributeButton(cog, guild , public_channel))
        self.add_item(MandatoryCombatButton(cog, guild,public_channel))
        self.add_item(MutantBeastAttackButton(cog, guild,public_channel))
        
        self.add_item(ViewAllTributesButton(cog, guild))

        self.add_item(GMHelpButton())

        self.add_item(ForceNextDayButton(cog, guild, public_channel))

class ForceNextDayButton(Button):
    """Forces the game to progress to the next day."""
    def __init__(self, cog, guild, public_channel):
        super().__init__(label="Force Next Day", style=discord.ButtonStyle.danger)
        self.cog = cog
        self.guild = guild
        self.public_channel = public_channel

    async def callback(self, interaction: Interaction):
        """Triggers the next day by calling the `nextday` command."""
        await self.cog.nextday(interaction)
        await interaction.response.send_message("⏩ **Next day has been forced!**", ephemeral=True)

class GMHelpButton(Button):
    """Displays a help message explaining how GameMasters can use their tools."""
    def __init__(self):
        super().__init__(label="How to GM", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: Interaction):
        """Sends an embed explaining how GameMasters can use the dashboard."""
        embed = discord.Embed(
            title="🕹️ **How to be a GameMaster** 🕹️",
            description=(
                "**As a GameMaster, you have powerful tools at your disposal. Here’s how to use them effectively:**\n\n"
                "- 🎭 **Trigger Events**: Use the buttons to launch **arena-wide effects** like fog or heatwaves.\n"
                "- 🎁 **Sponsor Tributes**: Provide a random tribute with a stat boost to shake things up!\n"
                "- ⚔️ **Mandatory Combat**: Force all tributes to **fight tomorrow**.\n"
                "- 🐺 **Mutant Beast Attack**: Send a dangerous **mutant beast** after a random tribute.\n"
                "- 🏹 **View Tributes**: Get an overview of all tributes’ stats.\n"
                "- 🔄 **Force Next Day**: Instantly **progress the game** to the next day (use wisely!).\n\n"
                "**GameMasters should balance fun and fairness! Keep the game engaging but not impossible.**"
            ),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)



class GameMasterEventButton(Button):
    """Button for triggering global events."""
    def __init__(self, cog, guild, event_name , public_channel):
        super().__init__(label=event_name, style=discord.ButtonStyle.primary)
        self.cog = cog
        self.guild = guild
        self.event_name = event_name
        self.public_channel = public_channel

    async def callback(self, interaction: Interaction):
        config = await self.cog.config.guild(self.guild).all()
        players = config["players"]

        event_message = ""
        
        if self.event_name == "Fog Descends":
            for player in players.values():
                if player["alive"]:
                    player["stats"]["Wis"] -= 2  # Decrease wisdom
                    if player["stats"]["Wis"] < 1:
                        player["stats"]["Wis"] = 1
            event_message = "🌫️ A thick fog descends over the arena, reducing all tributes' **Wisdom by 2**!"
        
        elif self.event_name == "Arena Shrinks":
            for player in players.values():
                if player["alive"]:
                    player["stats"]["HP"] -= 3  # Reduce HP
                    if player["stats"]["HP"] < 1:
                        player["stats"]["HP"] = 1
            event_message = "🏟️ The arena shrinks! All tributes lose **5 HP** as space gets tighter!"
        
        elif self.event_name == "Heatwave Strikes":
            for player in players.values():
                if player["alive"]:
                    player["stats"]["Con"] -= 2
                    if player["stats"]["Con"] < 1:
                        player["stats"]["Con"] = 1# Reduce Constitution
            event_message = "🔥 A brutal heatwave hits the arena! All tributes lose **2 Constitution** due to exhaustion!"

        # Save updated player stats
        await self.cog.config.guild(self.guild).players.set(players)

        # Announce event
        await self.public_channel.send(event_message)
        await interaction.response.defer()


class SponsorRandomTributeButton(Button):
    """Button to sponsor a random tribute with an item."""
    def __init__(self, cog, guild,public_channel):
        super().__init__(label="Sponsor a Random Tribute", style=discord.ButtonStyle.success)
        self.cog = cog
        self.guild = guild
        self.public_channel = public_channel  # Store public channel

    async def callback(self, interaction: Interaction):
        config = await self.cog.config.guild(self.guild).all()
        players = config["players"]
        alive_players = [p for p in players.values() if p["alive"]]

        if not alive_players:
            await interaction.response.send_message("No tributes are alive to sponsor!", ephemeral=True)
            return
        
        # Select a random tribute
        tribute = random.choice(alive_players)
        stat = random.choice(["Def", "Str", "Con", "Wis"])
        boost = random.randint(1, 5)
        tribute["stats"][stat] += boost
        
        await self.cog.config.guild(self.guild).players.set(players)
        await self.public_channel.send(f"🎁 **Someone** sponsored **{tribute['name']}** with a **+{boost} boost to {stat}**!")
        await interaction.response.defer()

class MandatoryCombatButton(Button):
    """Forces all tributes into combat next turn."""
    def __init__(self, cog, guild,public_channel):
        super().__init__(label="Mandatory Combat", style=discord.ButtonStyle.danger)
        self.cog = cog
        self.guild = guild
        self.public_channel = public_channel  # Store public channel

    async def callback(self, interaction: Interaction):
        config = await self.cog.config.guild(self.guild).all()
        players = config["players"]

        # Force all alive tributes to select "Hunt" for the next turn
        for player in players.values():
            if player["alive"]:
                player["action"] = "Hunt"

        await self.cog.config.guild(self.guild).players.set(players)

        await self.public_channel.send("⚔️ **Mandatory Combat!** All tributes have been set to hunt tomorrow!")
        await interaction.response.defer()


class MutantBeastAttackButton(Button):
    """Triggers a random mutant beast attack affecting tributes."""
    def __init__(self, cog, guild,public_channel):
        super().__init__(label="Mutant Beast Attack", style=discord.ButtonStyle.danger)
        self.cog = cog
        self.guild = guild
        self.public_channel = public_channel  # Store public channel

    async def callback(self, interaction: Interaction):
        config = await self.cog.config.guild(self.guild).all()
        players = config["players"]
        alive_players = [p for p in players.values() if p["alive"]]

        if not alive_players:
            await interaction.response.send_message("No tributes are alive to attack!", ephemeral=True)
            return

        # Select a random tribute to be attacked
        tries = 0
        victim = None
        
        while tries < len(alive_players):
            potential_victim = random.choice(alive_players)
            max_damage = min(potential_victim["stats"]["HP"] - 1, 15)

            if max_damage >= 2:
                victim = potential_victim
                damage = random.randint(1, max_damage)
                victim["stats"]["HP"] -= damage
                break  # Stop searching once a valid target is found

            tries += 1

        # If no valid tribute was found, exit gracefully
        if not victim:
            await interaction.response.send_message("No valid tributes had enough HP for a beast attack.", ephemeral=True)
            return
    
        await self.cog.config.guild(self.guild).players.set(players)
    
        await self.public_channel.send(f"🐺 A **mutant beast** ambushes **{victim['name']}**, dealing **{damage} damage**!")
        await interaction.response.defer()    


class ViewItemsButton(Button):
    def __init__(self, cog):
        super().__init__(label="View Items", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        guild = interaction.guild
        players = await self.cog.config.guild(guild).players()

        # Check if the user is in the game
        if user_id not in players:
            await interaction.response.send_message(
                "You are not part of the Hunger Games.", ephemeral=True
            )
            return

        # Fetch player data
        player = players[user_id]
        items = player.get("items", [])

        # Prepare embed to display items
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Items",
            color=discord.Color.gold()
        )

        if not items:
            embed.description = "You have no items."
        else:
            for idx, (stat, boost) in enumerate(items, start=1):
                embed.add_field(
                    name=f"Boost: +{boost} to **{stat}**",
                    value="",
                    inline=False
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class HungerGamesAI:
    def __init__(self, cog):
        self.cog = cog
        self.last_sponsorship = {}

import random
from datetime import datetime, timedelta
import asyncio

class HungerGamesAI:
    def __init__(self, cog):
        self.cog = cog
        self.last_sponsorship = {}

    async def ai_sponsor(self, guild, channel):
        """
        AI sponsors tributes at random times, favoring underdogs.
        1% chance to shower all tributes with gifts (+1000 to +2000 to all stats).
        """
        players = await self.cog.config.guild(guild).players()
        if not players:
            return  # No players to sponsor

        # 🎁 **1% chance for a massive sponsorship shower**
        if random.random() < .01:  # 1% chance
            # Decide a **fair** boost amount for all tributes
            universal_boost = random.randint(1000, 2000)

            # Apply to all alive tributes
            for player in players.values():
                if player["alive"]:
                    for stat in ["Def", "Str", "Wis", "HP"]:
                        player["stats"][stat] += universal_boost  # Apply boost

            await self.cog.config.guild(guild).players.set(players)

            # 🎉 Announce the sponsorship shower
            await channel.send(
                f"🌟 **A mysterious benefactor showers all tributes with gifts!** 🌟\n"
                f"Each tribute gains **+{universal_boost} to all stats!** 🎁"
            )
            self.last_sponsorship[guild.id] = datetime.utcnow()
            return  # Skip normal sponsorship

        # **Normal AI Sponsorship (Favoring Underdogs)**
        npc_names = await self.cog.load_npc_names()
        npc_name = random.choice(npc_names)

        # Select a tribute with weighting for underdogs
        alive_players = [p for p in players.values() if p["alive"]]
        if not alive_players:
            return  # No alive players to sponsor

        total_stats = {p["name"]: sum(p["stats"].values()) for p in alive_players}
        min_stats = min(total_stats.values())
        max_stats = max(total_stats.values())
        stat_range = max(1, max_stats - min_stats)

        # Weighting: lower stats get a higher chance
        weights = [
            1.5 - ((total_stats[p["name"]] - min_stats) / stat_range)
            for p in alive_players
        ]

        selected_tribute = random.choices(alive_players, weights=weights, k=1)[0]
        tribute_id = next(k for k, v in players.items() if v == selected_tribute)

        # Random stat to boost
        stat_to_boost = random.choice(["Def", "Str", "Con", "Wis", "HP"])
        boost_amount = random.randint(1, 10)  # Normal random boost amount

        # Apply sponsorship
        selected_tribute["stats"][stat_to_boost] += boost_amount
        await self.cog.config.guild(guild).players.set(players)

        # Broadcast sponsorship in the given channel
        await asyncio.sleep(5)
        if channel:
            await channel.send(
                f"🎁 **Someone** sponsored **{selected_tribute['name']}** with a "
                f"+{boost_amount} boost to {stat_to_boost}!"
            )

        # Track sponsorship timing to avoid spamming
        self.last_sponsorship[guild.id] = datetime.utcnow()

    async def should_sponsor(self, guild):
        """
        Determine if AI should sponsor today.
        """
        now = datetime.utcnow()
        last_time = self.last_sponsorship.get(guild.id, now - timedelta(days=1))
        # AI sponsor timer
        return (now - last_time).total_seconds() > random.randint(500, 1000)


        

class SponsorButton(Button):
    def __init__(self, cog):
        super().__init__(label="Sponsor a Tribute", style=discord.ButtonStyle.danger)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        try:
            guild = interaction.guild
            players = await self.cog.config.guild(guild).players()
            
            user_id = str(interaction.user.id)  # Get the sponsor's user ID
           
            # Create options for tributes using nicknames or usernames
            tribute_options = []
            for player_id, player in players.items():
                if player["alive"] and player_id != user_id:
                    if player_id.isdigit():  # Check if it's a real user
                        member = guild.get_member(int(player_id))
                        if member:
                            display_name = member.nick or member.name  # Use nickname or fallback to username
                            tribute_options.append(SelectOption(label=display_name, value=player_id))
                        else:
                            # Fallback to the stored name if the member is not found
                            tribute_options.append(SelectOption(label=player["name"], value=player_id))
                    else:
                        # For NPCs, use their stored names
                        tribute_options.append(SelectOption(label=player["name"], value=player_id))

            if not tribute_options:
                await interaction.response.send_message("There are no living tributes to sponsor.", ephemeral=True)
                return

            # Send the sponsor view
            day_count = await self.cog.config.guild(guild).day_counter()
            view = SponsorView(self.cog, tribute_options, guild, interaction.user,day_count)
            await interaction.response.send_message("Sponsor a tribute using the options below:", view=view, ephemeral=True)
        except Exception as e:
            error_message = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            await interaction.response.send_message(f"An error occurred: {error_message}", ephemeral=True)

class SponsorView(View):
    def __init__(self, cog, tribute_options, guild, user,day_count):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.tribute_options = tribute_options
        self.selected_tribute = None
        self.selected_stat = None
        self.selected_boost = None

        # Tribute selection dropdown
        self.tribute_select = Select(
            placeholder="Select a tribute...",
            options=tribute_options,
            custom_id="tribute_select"
        )
        self.tribute_select.callback = self.on_tribute_select
        self.add_item(self.tribute_select)

        # Stat selection dropdown
        self.stat_options = [
            SelectOption(label="Defense", value="Def"),
            SelectOption(label="Strength", value="Str"),
            SelectOption(label="Constitution", value="Con"),
            SelectOption(label="Wisdom", value="Wis"),
            SelectOption(label="HP", value="HP"),
        ]
        self.stat_select = Select(
            placeholder="Select a stat to boost...",
            options=self.stat_options,
            custom_id="stat_select"
        )
        self.stat_select.callback = self.on_stat_select
        self.add_item(self.stat_select)
        
        # Boost amount selection dropdown
        self.boost_options = [
            SelectOption(label=f"+{i} Boost ({20 * i + (day_count) * 10}) Gold)", value=str(i)) for i in range(1, 11)
        ]
        self.boost_select = Select(
            placeholder="Select the boost amount...",
            options=self.boost_options,
            custom_id="boost_select"
        )
        self.boost_select.callback = self.on_boost_select
        self.add_item(self.boost_select)

        # Confirm button
        self.confirm_button = Button(label="Confirm Sponsorship", style=discord.ButtonStyle.green, disabled=True)
        self.confirm_button.callback = self.confirm_sponsorship
        self.add_item(self.confirm_button)


    def get_tribute_options(self):
        """Get the tribute options with the selected value marked."""
        return [
            SelectOption(label=option.label, value=option.value, default=(option.value == self.selected_tribute))
            for option in self.tribute_options
        ]

    async def on_tribute_select(self, interaction: Interaction):
        try:
            self.selected_tribute = self.tribute_select.values[0]
            await self.update_confirm_button(interaction)
            await interaction.response.defer()  # Prevents interaction expiration

        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred in tribute selection: {e}", ephemeral=True
            )

    def get_stat_options(self):
        return [
            SelectOption(label=option.label, value=option.value, default=(option.value == self.selected_stat))
            for option in self.stat_options
        ]
    
    def get_boost_options(self):
        return [
            SelectOption(label=option.label, value=option.value, default=(option.value == str(self.selected_boost)))
            for option in self.boost_options
        ]

    async def on_stat_select(self, interaction: Interaction):
        self.selected_stat = self.stat_select.values[0]
        await self.update_confirm_button(interaction)
        await interaction.response.defer()  # Prevents interaction expiration
    
    async def on_boost_select(self, interaction: Interaction):
        self.selected_boost = int(self.boost_select.values[0])
        await self.update_confirm_button(interaction)
        await interaction.response.defer()  # Prevents interaction expiration


    async def update_confirm_button(self, interaction):
        """Ensure the confirm button enables when all fields are set and retains selections."""
        # Enable the confirm button if all three selections are made
        all_selected = self.selected_tribute and self.selected_stat and self.selected_boost
        self.confirm_button.disabled = not all_selected
    
        # Re-create dropdowns with current selections retained
        self.tribute_select.options = [
            SelectOption(label=option.label, value=option.value, default=(option.value == self.selected_tribute))
            for option in self.tribute_options
        ]
        self.stat_select.options = [
            SelectOption(label=option.label, value=option.value, default=(option.value == self.selected_stat))
            for option in self.stat_options
        ]
        self.boost_select.options = [
            SelectOption(label=option.label, value=option.value, default=(option.value == str(self.selected_boost)))
            for option in self.boost_options
        ]
    
        # Refresh the message with updated selections
        await interaction.response.edit_message(view=self)
    



class ViewBidsButton(Button):
    def __init__(self, cog):
        super().__init__(label="View Bids", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        try:
            guild = interaction.guild
            players = await self.cog.config.guild(guild).players()
            all_users = await self.cog.config.all_users()

            # Calculate total bets on each tribute
            bid_totals = {}
            bet_details = {}  # Store detailed bet info for each tribute

            for player_id, player_data in players.items():
                if not player_data["alive"]:
                    continue

                tribute_bets = player_data.get("bets", {})
                total_bets = 0
                details = []

                # Include user bets
                for user_id, user_data in all_users.items():
                    bets = user_data.get("bets", {})
                    if player_id in bets:
                        bet_amount = bets[player_id]["amount"]
                        total_bets += bet_amount
                        member = guild.get_member(int(user_id))
                        if member:
                            details.append(f"{member.nick}: {bet_amount} gold")

                # Include AI bets
                ai_bets = tribute_bets.get("AI", [])
                for ai_bet in ai_bets:
                    total_bets += ai_bet["amount"]
                    details.append(f"{ai_bet['name']}: {ai_bet['amount']} gold")

                if total_bets > 0:
                    bid_totals[player_id] = total_bets
                    bet_details[player_id] = details

            # Sort tributes by total bets
            sorted_tributes = sorted(
                bid_totals.items(),
                key=lambda item: item[1],
                reverse=True
            )

            # Create embed
            embed = discord.Embed(
                title="🏅 Tribute Betting Rankings 🏅",
                description="Ranking of living tributes based on total bets placed.",
                color=discord.Color.gold()
            )

            for rank, (tribute_id, total_bet) in enumerate(sorted_tributes, start=1):
                tribute = players.get(tribute_id)
                if not tribute["alive"]:
                    continue  # Skip dead tributes
                district = tribute["district"]

                # Determine display name (nickname or stored name for NPCs)
                if tribute_id.isdigit():  # Real user
                    member = guild.get_member(int(tribute_id))
                    tribute_name = member.display_name if member else tribute["name"]
                else:  # NPC
                    tribute_name = tribute["name"]

                # Format detailed bets
                details_text = "\n".join(bet_details[tribute_id])

                embed.add_field(
                    name=f"#{rank} {tribute_name} (District {district})",
                    value=f"Total Bets: {total_bet} gold\n{details_text}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)





class BettingButton(Button):
    def __init__(self, cog):
        super().__init__(label="Place a Bet", style=discord.ButtonStyle.danger)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        try:
            guild = interaction.guild
            players = await self.cog.config.guild(guild).players()

            # Create options for tributes using nicknames or usernames
            tribute_options = []
            for player_id, player in players.items():
                if player["alive"]:
                    if player_id.isdigit():  # Check if it's a real user
                        member = guild.get_member(int(player_id))
                        if member:
                            display_name = member.nick or member.name  # Use nickname or fallback to username
                            tribute_options.append(SelectOption(label=display_name, value=player_id))
                        else:
                            # Fallback to the stored name if the member is not found
                            tribute_options.append(SelectOption(label=player["name"], value=player_id))
                    else:
                        # For NPCs, use their stored names
                        tribute_options.append(SelectOption(label=player["name"], value=player_id))

            if not tribute_options:
                await interaction.response.send_message("There are no tributes to bet on.", ephemeral=True)
                return

            # Send a view with dropdowns for selecting tribute and bet amount
            view = BettingView(self.cog, tribute_options, guild)
            await interaction.response.send_message("Place your bet using the options below:", view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred: {e}", ephemeral=True
            )

class BettingView(View):
    def __init__(self, cog, tribute_options, guild):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild = guild
        self.tribute_options = tribute_options  # Store tribute options
        self.selected_tribute = None
        self.selected_amount = None

        # Tribute selection dropdown
        self.tribute_select = Select(
            placeholder="Select a tribute...",
            options=self.get_tribute_options(),
            custom_id="tribute_select"
        )
        self.tribute_select.callback = self.on_tribute_select
        self.add_item(self.tribute_select)

        # Bet amount selection dropdown
        self.amount_options = [
            SelectOption(label="10 Gold", value="10"),
            SelectOption(label="50 Gold", value="50"),
            SelectOption(label="100 Gold", value="100"),
            SelectOption(label="1000 Gold", value="1000"),
            SelectOption(label="All Gold", value="all")
        ]
        self.amount_select = Select(
            placeholder="Select bet amount...",
            options=self.get_amount_options(),
            custom_id="amount_select"
        )
        self.amount_select.callback = self.on_amount_select
        self.add_item(self.amount_select)

        # Confirm button
        self.confirm_button = Button(label="Confirm Bet", style=discord.ButtonStyle.green, disabled=True)
        self.confirm_button.callback = self.confirm_bet
        self.add_item(self.confirm_button)

    def get_tribute_options(self):
        """Get the tribute options with the selected value marked."""
        return [
            SelectOption(label=option.label, value=option.value, default=(option.value == self.selected_tribute))
            for option in self.tribute_options
        ]

    def get_amount_options(self):
        """Get the amount options with the selected value marked."""
        return [
            SelectOption(label=option.label, value=option.value, default=(option.value == self.selected_amount))
            for option in self.amount_options
        ]

    async def on_tribute_select(self, interaction: Interaction):
        try:
            self.selected_tribute = self.tribute_select.values[0]  # Store the selected tribute
            self.tribute_select.options = self.get_tribute_options()  # Update options to retain selection

            # Enable confirm button if both selections are made
            if self.selected_amount:
                self.confirm_button.disabled = False

            await interaction.response.edit_message(view=self)
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred in tribute selection: {e}", ephemeral=True
            )

    async def on_amount_select(self, interaction: Interaction):
        try:
            self.selected_amount = self.amount_select.values[0]  # Store the selected amount
            self.amount_select.options = self.get_amount_options()  # Update options to retain selection

            # Enable confirm button if both selections are made
            if self.selected_tribute:
                self.confirm_button.disabled = False

            await interaction.response.edit_message(view=self)
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred in amount selection: {e}", ephemeral=True
            )

    async def confirm_bet(self, interaction: Interaction):
        try:
            guild = interaction.guild
            user_gold = await self.cog.config.user(interaction.user).gold()

            # Determine the bet amount
            if self.selected_amount == "all":
                bet_amount = user_gold
            else:
                bet_amount = int(self.selected_amount)

            if bet_amount > user_gold:
                await interaction.response.send_message(
                    f"You don't have enough gold to place this bet. You have {user_gold} gold.",
                    ephemeral=True
                )
                return

            # Deduct gold and save the bet
            await self.cog.config.user(interaction.user).gold.set(user_gold - bet_amount)
            user_bets = await self.cog.config.user(interaction.user).bets()

            if self.selected_tribute in user_bets:
                await interaction.response.send_message(
                    "You have already placed a bet on this tribute.", ephemeral=True
                )
                return

            user_bets[self.selected_tribute] = {
                "amount": bet_amount,
                "daily_earnings": 0
            }
            await self.cog.config.user(interaction.user).bets.set(user_bets)

            players = await self.cog.config.guild(guild).players()
            tribute_name = players[self.selected_tribute]["name"]

            await interaction.response.send_message(
                f"You placed a bet of {bet_amount} gold on {tribute_name}. Good luck!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

class ViewTributesButton(Button):
    def __init__(self, cog):
        super().__init__(label="View Tributes", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        guild = interaction.guild
        players = await self.cog.config.guild(guild).players()

        # Calculate scores for each tribute
        tribute_scores = []
        for player_id, player in players.items():
            if player["alive"]:
                score = (
                    player["stats"]["Def"]
                    + player["stats"]["Str"]
                    + player["stats"]["Con"]
                    + player["stats"]["Wis"]
                    + (player["stats"]["HP"] // 5)  # Normalize HP by dividing by 5
                )
                tribute_scores.append({
                    "name": player["name"],
                    "district": player["district"],
                    "score": score
                })

        # Sort tributes by score in descending order
        tribute_scores.sort(key=lambda x: x["score"], reverse=True)

        # Create an embed with the rankings
        embed = discord.Embed(
            title="Tribute Rankings",
            description="Ranked tributes by their calculated scores.",
            color=discord.Color.gold()
        )
        for rank, tribute in enumerate(tribute_scores, start=1):
            embed.add_field(
                name=f"District {tribute['district']}",
                value=f"#{rank} {tribute['name']}\n Score: {tribute['score']}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)



class ViewStatsButton(Button):
    """Button to display the user's tribute stats in a detailed, formatted embed."""
    def __init__(self, cog):
        super().__init__(label="View Stats", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        """Shows the player's stats in a clean and formatted embed."""
        user_id = str(interaction.user.id)
        guild = interaction.guild
        players = await self.cog.config.guild(guild).players()

        # Check if the user is a tribute
        if user_id not in players:
            await interaction.response.send_message(
                "You are not part of the Hunger Games.", ephemeral=True
            )
            return

        player = players[user_id]
        status = "🟢 **Alive**" if player["alive"] else "🔴 **Eliminated**"

        # 🎨 Create a styled embed
        embed = discord.Embed(
            title="🏹 **Your Tribute Stats** 🏹",
            description=f"{status}",
            color=discord.Color.gold()
        )
        embed.add_field(name="🏛 **District**", value=f"{player['district']}", inline=False)
        embed.add_field(name="🛡️ **Defense**", value=f"{player['stats']['Def']}", inline=True)
        embed.add_field(name="⚔️ **Strength**", value=f"{player['stats']['Str']}", inline=True)
        embed.add_field(name="💪 **Constitution**", value=f"{player['stats']['Con']}", inline=True)
        embed.add_field(name="🧠 **Wisdom**", value=f"{player['stats']['Wis']}", inline=True)
        embed.add_field(name="❤️ **HP**", value=f"{player['stats']['HP']}", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)




class ActionSelectionView(View):
    def __init__(self, cog, feast_active, current_day):
        super().__init__(timeout=None)  # No timeout for the buttons
        self.cog = cog

        # Add action buttons
        self.add_item(ActionButton(cog, "Hunt"))
        self.add_item(ActionButton(cog, "Rest"))
        self.add_item(ActionButton(cog, "Loot"))
        
        if feast_active:
            self.add_item(ActionButton(cog, "Feast"))
        


        self.add_item(SponsorButton(cog))


        # Only add the Betting Button on Day 0 and Day 1
        if current_day in [0, 1]:
            self.add_item(BettingButton(cog))
        
        self.add_item(ViewItemsButton(cog))  # Add the new View Items button
        self.add_item(ViewStatsButton(cog))
        self.add_item(ViewTributesButton(cog))
        self.add_item(ViewBidsButton(cog))  # Add the new button here
        self.add_item(CheckGoldButton(cog))  # Add the new button here
 

class ActionButton(Button):
    def __init__(self, cog, action):
        super().__init__(label=action, style=discord.ButtonStyle.primary)
        self.cog = cog
        self.action = action

    async def callback(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        guild = interaction.guild
        players = await self.cog.config.guild(guild).players()

        # Check if the user is in the game and alive
        if user_id not in players or not players[user_id]["alive"]:
            await interaction.response.send_message(
                "You are not part of the game or are no longer alive.", ephemeral=True
            )
            return

        # Update the user's action
        players[user_id]["action"] = self.action
        await self.cog.config.guild(guild).players.set(players)
        
        await interaction.response.send_message(
            f"You have selected to **{self.action}** for today.", ephemeral=True
        )


#todo list

def is_gamemaster():
    """Check if the user has the GameMaster role."""
    async def predicate(ctx):
        gamemaster_role = discord.utils.get(ctx.guild.roles, name="GameMaster")
        if not gamemaster_role:
            raise CheckFailure("The 'GameMaster' role does not exist in this server.")
        if gamemaster_role not in ctx.author.roles:
            raise CheckFailure("You do not have the 'GameMaster' role.")
        return True
    return commands.check(predicate)

class Hungar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            districts={},
            players={},
            game_active=False,
            day_duration=120,  # Default: 1 hour in seconds
            day_start=None,
            day_counter=0, 
            random_events=True,  # Enable or disable random events
            feast_active=False, 
            WLboard={},  
             
            
        )
        self.config.register_user(
            gold=0,
            bets={},
            kill_count=0,  # Track total kills
        )
        self.ai_manager = HungerGamesAI(self)


    async def report_error(self, channel, error):
        """Send error details to a designated channel."""
        error_message = f"An error occurred:\n```{error}```"
        if isinstance(channel, discord.TextChannel):
            await channel.send(error_message)
        else:
            print(error_message)  #

    
    async def load_file(self,fileName,name1="Name1 Filler",name2="Name2 Filler",dmg="DMG Filler",dmg2="DMG2 Filler", item_name="Item name filler"):
        """Load file names from the fileName.txt file."""
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_path, fileName)
            with open(file_path, "r") as f:
                line =  [line.strip() for line in f.readlines() if line.strip()]
                line = random.choice(line)
                line = line.replace("{name1}",str(name1)).replace("{name2}",str(name2)).replace("{dmg}",str(dmg)).replace("{item}",str(item_name)).replace("{dmg2}",str(dmg2))
                return line
        except FileNotFoundError:
            return f"ERROR {fileName} not found"  # Fallback if file is missing

    
    async def load_npc_names(self):
        """Load NPC names from the NPC_names.txt file."""
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_path, "NPC_names.txt")
            with open(file_path, "r") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except FileNotFoundError:
            return [f"NPC {i+1}" for i in range(100)]  # Fallback if file is missing

    @commands.guild_only()
    @commands.group()
    async def hunger(self, ctx):
        """Commands for managing the Hunger Games."""
        pass

    @hunger.command()
    async def signup(self, ctx):
        """Sign up for the Hunger Games."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        config = await self.config.guild(guild).all()
        
        if config["game_active"]:
            await ctx.send("The Hunger Games are already active! Please wait for the next one")
            return
            
        if str(ctx.author.id) in players:
            await ctx.send("You are already signed up!")
            return

        if len(players) > 25:
            await ctx.send("Sorry this game is full try again next time!")
            return

        # 🎖️ **Assign a Role to the User**
        role_name = "Tribute"  # Change this to match your role name
        role = get(guild.roles, name=role_name)  # Fetch the role
    
        if role:
            await ctx.author.add_roles(role)
        
        # Award 100 gold to the player in user config
        user_gold = await self.config.user(ctx.author).gold()
        user_gold += 100
        await self.config.user(ctx.author).gold.set(user_gold)
    

        # Assign random district and stats
        district = random.randint(1, 12)  # Assume 12 districts
        stats = {
            "Def": random.randint(1, 10),
            "Str": random.randint(1, 10),
            "Con": random.randint(1, 10),
            "Wis": random.randint(1, 10),
            "HP": random.randint(15, 25)
        }
        if district == 1:
            stats["Def"] = stats["Def"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 2:
            stats["Def"] = stats["Def"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"]
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 3:
            stats["Def"] = stats["Def"]
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 4:
            stats["Def"] = stats["Def"] + 1
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 10
        elif district == 5:
            stats["Def"] = stats["Def"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 6:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 5
        elif district == 7:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 8:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 9:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 5
        elif district == 10:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] 
        elif district == 11:
            stats["Def"] = stats["Def"]
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 12:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"]
            
        

        players[str(ctx.author.id)] = {
            "name": ctx.author.display_name,
            "district": district,
            "stats": stats,
            "alive": True,
            "action": None,
            "items": [],
            "kill_list": [],  
        }

        await self.config.guild(guild).players.set(players)
        await ctx.send(f"{ctx.author.mention} has joined the Hunger Games from District {district}!")

    @hunger.command()
    @is_gamemaster()
    async def setdistrict(self, ctx, member: commands.MemberConverter, district: int):
        """Set a player's district manually (Admin only)."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        if str(member.id) not in players:
            await ctx.send(f"{member.display_name} is not signed up.")
            return

        players[str(member.id)]["district"] = district
        await self.config.guild(guild).players.set(players)
        await ctx.send(f"{member.display_name}'s district has been set to {district}.")

    @hunger.command()
    @is_gamemaster()
    async def startgame(self, ctx, npcs: int = 0, dashboard_channel: discord.TextChannel = None):
        """Start the Hunger Games (Admin only). Optionally, add NPCs."""
        file_name = "Hunger_Games.txt"
        async with aiofiles.open(file_name, mode='w') as file:
            pass
        
        guild = ctx.guild
        config = await self.config.guild(guild).all()
        
        if config["game_active"]:
            await ctx.send("The Hunger Games are already active!")
            return
        
        players = config["players"]
       
        # Load and shuffle NPC names
        npc_names = await self.load_npc_names()
        random.shuffle(npc_names)

        # Track used NPC names and add NPCs
        used_names = set(player["name"] for player in players.values() if player.get("is_npc"))
        available_names = [name for name in npc_names if name not in used_names]

        if len(available_names) < npcs:
            await ctx.send("Not enough unique NPC names available for the requested number of NPCs.")
            return

        for i in range(npcs):
            npc_id = f"npc_{i+1}"
            players[npc_id] = {
                "kill_list" : [] ,
                "name": available_names.pop(0),  # Get and remove the first available name
                "district": random.randint(1, 12),
                "stats": {
                    "Def": random.randint(1, 10),
                    "Str": random.randint(1, 10),
                    "Con": random.randint(1, 10),
                    "Wis": random.randint(1, 10),
                    "HP": random.randint(15, 25)
                },
                "alive": True,
                "action": None,
                "is_npc": True,
                "items": []
            }

        for player_id, player_data in players.items():
            if player_data.get("is_npc", False):
                # Bold NPC names
                player_data["name"] = f"**{player_data['name']}**"
            else:
                # Mention real players
                member = guild.get_member(int(player_id))
                if member:
                    player_data["name"] = member.mention  # Replace name with mention
                else:
                    player_data["name"] = player_data["name"]  # Fallback to original name

        if len(players) > 25: 
            await ctx.send("Sorry only 25 people can play (this includes NPCs)")
            return
        
        # Add AI bettors
        ai_bettors = {}
        npc_names = await self.load_npc_names()
        for tribute_id, tribute in players.items():
            if not tribute["alive"]:
                continue
        
            ai_name = random.choice(npc_names)
            bet_amount = random.randint(50, 500)  # Random bet between 50 and 500 gold
        
            # Save the bet to the AI bettors dictionary for announcements
            ai_bettors[ai_name] = {
                "tribute_id": tribute_id,
                "amount": bet_amount
            }
        
            # Store the AI bet in the tribute's bet data (same structure as user bets)
            tribute_bets = tribute.get("bets", {})  # Ensure "bets" key exists for tribute
            if "AI" not in tribute_bets:
                tribute_bets["AI"] = []
            tribute_bets["AI"].append({
                "name": ai_name,
                "amount": bet_amount
            })
            tribute["bets"] = tribute_bets  # Save back to players
        
        # Apply AI bets
        for ai_name, bet_data in ai_bettors.items():
            tribute_id = bet_data["tribute_id"]
            amount = bet_data["amount"]
        
            if tribute_id not in players or not players[tribute_id]["alive"]:
                continue  # Skip invalid tributes
                    
            await self.config.guild(guild).players.set(players)
            await self.config.guild(guild).game_active.set(True)
            await self.config.guild(guild).day_start.set(datetime.utcnow().isoformat())
            await self.config.guild(guild).day_counter.set(0)
    
            # Announce all participants with mentions for real players, sorted by district
            sorted_players = sorted(players.values(), key=lambda p: p["district"])
            participant_list = []
            for player in sorted_players:
                if player.get("is_npc"):
                    participant_list.append(f"{player['name']} from District {player['district']}")
                else:
                    member = guild.get_member(int(next((k for k, v in players.items() if v == player), None)))
                    if member:
                        participant_list.append(f"{member.mention} from District {player['district']}")
    
        participant_announcement = "\n".join(participant_list)
        await ctx.send(f"The Hunger Games have begun with the following participants (sorted by District):\n{participant_announcement}")

        # 📌 Send GameMaster Dashboard **if a private channel is provided**
        if dashboard_channel:
            dashboard_message = await dashboard_channel.send(
                "🕹️ **GameMaster Dashboard**: Use these buttons to trigger special events!",
                view=GameMasterView(self, ctx.guild, ctx.channel)
            )
            await self.config.guild(guild).set_raw("dashboard_message_id", value=dashboard_message.id)
            await self.config.guild(guild).set_raw("dashboard_channel_id", value=dashboard_channel.id)

            
        asyncio.create_task(self.run_game(ctx))

    async def run_game(self, ctx):
        """Handle the real-time simulation of the game."""
        try:
            guild = ctx.guild
            await self.announce_new_day(ctx, guild)
            while True:
                config = await self.config.guild(guild).all()
                if not config["game_active"]:
                    break

                if await self.ai_manager.should_sponsor(guild):
                    await self.ai_manager.ai_sponsor(guild, ctx.channel)
    
                day_start = datetime.fromisoformat(config["day_start"])
                day_duration = timedelta(seconds=config["day_duration"])
                if datetime.utcnow() - day_start >= day_duration:
                    await self.process_day(ctx)
                    if await self.isOneLeft(guild):
                        await self.endGame(ctx)
                        break
                    
                    config = await self.config.guild(guild).all()
                    players = await self.config.guild(guild).players()
                    alive_players = [player for player in players.values() if player["alive"]]
                    day_length = len(alive_players) * 20 + 20 #day speed settings
                    if config["day_counter"] % 10 == 0:
                        day_length = day_length * 1.5
                    await self.config.guild(guild).day_duration.set(day_length)
                    await self.announce_new_day(ctx, guild)
                    await self.config.guild(guild).day_start.set(datetime.utcnow().isoformat())
    
                await asyncio.sleep(10)  # Check every 10 seconds
        except Exception as e:
            await ctx.send(e)
            await ctx.send(traceback.format_exc())
            

    async def announce_new_day(self, ctx, guild):
        """Announce the start of a new day and ping alive players."""
        await ctx.send("https://i.imgur.com/gtCA6wO.png")
        config = await self.config.guild(guild).all()
        players = config["players"]
        current_day = config.get("day_counter", -1)

        # Reset all player actions to None
        for player_id, player_data in players.items():
            if player_data["alive"]:  # Only reset actions for alive players
                player_data["action"] = None

        await self.config.guild(guild).players.set(players)

        # Handle Feast Activation
        #await ctx.send(day_counter)
        if config["day_counter"] % 10 == 0:
            # Feast is active on Day 1 and every 10th day
            await self.config.guild(guild).feast_active.set(True)
            config = await self.config.guild(guild).all()

        else:
            # Ensure Feast is not active on other days
            await self.config.guild(guild).feast_active.set(False)
            config = await self.config.guild(guild).all()


        # Get alive players count
        alive_players = [player for player in players.values() if player["alive"]]
        alive_count = len(alive_players)

        feast_active = config.get("feast_active", False)
        feast_message = "A Feast has been announced! Attend by choosing `Feast` as your action today." if feast_active else ""

        alive_mentions = []
        for player_id, player_data in players.items():
            if player_data["alive"]:
                if player_data.get("is_npc"):
                    # NPC names are appended as text
                    alive_mentions.append(f"{player_data['name']}")
                else:
                    # Real players are pinged using mentions
                    member = guild.get_member(int(player_id))
                    if member:
                        alive_mentions.append(member.mention)

        # Send the announcement with all alive participant
        # Send the announcement
        await ctx.send(
            f"Day {config['day_counter']} begins in the Hunger Games! {alive_count} participants remain.\n"
            f"{feast_message}\n"
            f"Alive participants: {', '.join(alive_mentions)}"
        )
        # Calculate the next day start time
        day_start = datetime.utcnow()
        alive_count = len(alive_players)
        day_duration = max(int(alive_count) * 20 + 20,60)  
        day_counter = config.get("day_counter", 0)
        if day_counter > 0 and day_counter % 10 == 0:
            day_duration = int(day_duration * 1.5)  # Feast days are longer
    
        next_day_start = day_start + timedelta(seconds=day_duration) - timedelta(hours=6)
        next_day_start_timestamp = int(next_day_start.timestamp())  # Convert to Unix timestamp

                # Save the updated day start time and duration
        await self.config.guild(guild).day_start.set(day_start.isoformat())
        await self.config.guild(guild).day_duration.set(day_duration)

        await ctx.send(f"Pick your action for the day, the sun will set in about <t:{next_day_start_timestamp}:R>",view=ActionSelectionView(self, feast_active,current_day))

    async def isOneLeft(self, guild):
        """Check if only one player is alive."""
        players = await self.config.guild(guild).players()
        alive_players = [player for player in players.values() if player["alive"]]
        return len(alive_players) <= 1

    async def endGame(self, ctx):
        """End the game and announce the winner."""
        guild = ctx.guild
        config = await self.config.guild(guild).all()
        players = config["players"]
        leaderboard = config.get("elimination_leaderboard", [])
        all_users = await self.config.all_users()  # Fetch all users
    
        alive_players = [player for player in players.values() if player["alive"]]
        WLboard = config.get("WLboard",{})

        role = get(guild.roles, name="Tribute")
    
        if role:
            for member in guild.members:
                if role in member.roles:
                    await member.remove_roles(role)    


        # 🛑 **Disable GameMaster Dashboard if it exists**
        dashboard_channel_id = config.get("dashboard_channel_id")
        dashboard_message_id = config.get("dashboard_message_id")
    
        if dashboard_channel_id and dashboard_message_id:
            dashboard_channel = guild.get_channel(dashboard_channel_id)
            if dashboard_channel:
                try:
                    message = await dashboard_channel.fetch_message(dashboard_message_id)
                    if message:
                        # Create a **disabled version** of the GameMaster dashboard
                        disabled_view = GameMasterView(self, guild, None)
                        for item in disabled_view.children:
                            item.disabled = True  # Disable all buttons
                        
                        await message.edit(content="🔒 **Game Over!** The GameMaster dashboard is now locked.", view=disabled_view)
                except discord.NotFound:
                    print("Dashboard message not found, skipping lockout.")

        if alive_players:
            winner = alive_players[0]
            winner_id = next((pid for pid, pdata in players.items() if pdata == winner), None)
            if not alive_players[0].get("is_npc", False):
                WLboard = config.get("WLboard",{})
                winner_data = WLboard.get(winner_id, {
                "name": winner["name"],
                "wins": 0,
                })
                winner_data["wins"] += 1
                WLboard[winner_id] = winner_data
                await self.config.guild(guild).WLboard.set(WLboard)
            await ctx.send(f"The game is over! The winner is {winner['name']} from District {winner['district']}!")
        else:
            await ctx.send("The game is over! No one survived.")

    
        # Send elimination leaderboard
        if leaderboard:
            leaderboard.sort(key=lambda x: x["day"])  # Sort by elimination day
            
            # Create the elimination leaderboard embed
            elim_embed = discord.Embed(
                title="🏅 Elimination Leaderboard 🏅",
                description="Here are the players eliminated so far:",
                color=discord.Color.red(),
            )
            for entry in leaderboard:
                elim_embed.add_field(
                    name=f"Day {entry['day']}",
                    value=f"{entry['name']}",
                    inline=False
                )
            await ctx.send(embed=elim_embed)
    
            # Fetch player data and sort by kill count
            guild_data = await self.config.guild(ctx.guild).all()
            players = guild_data["players"]
            sorted_players = sorted(players.values(), key=lambda p: len(p["kill_list"]), reverse=True)
            
            # Create the kill leaderboard embed
            kill_embed = discord.Embed(
                title="🏆 Kill Leaderboard 🏆",
                description="Here are the top killers:",
                color=discord.Color.gold(),
            )
            for i, player in enumerate(sorted_players, start=1):
                kills = len(player["kill_list"])
                if kills == 1:
                    kill_embed.add_field(
                        name="",
                        value=f"**{i}.** {player['name']}: {kills} kill\nKilled: {', '.join(player['kill_list'])}",
                        inline=False)
                else:
                    kill_embed.add_field(
                        name="",
                        value=f"**{i}.** {player['name']}: {kills} kills\nKilled: {', '.join(player['kill_list'])}",
                        inline=False)
            await ctx.send(embed=kill_embed)
    
        # **Calculate total bets placed on the winner**
        total_bet_on_winner = 0
        for user_id, user_data in all_users.items():
            bets = user_data.get("bets", {})
            if winner_id in bets:
                total_bet_on_winner += bets[winner_id]["amount"]

        # **Include AI bets**
        winner_bets = players.get(winner_id, {}).get("bets", {})
        ai_bets = winner_bets.get("AI", [])

        for ai_bet in ai_bets:
            total_bet_on_winner += ai_bet["amount"]

                # Distribute winnings
        for user_id, user_data in all_users.items():
            bets = user_data.get("bets", {})
            user_gold = user_data.get("gold", 0)
    
            for tribute_id, bet_data in bets.items():
                if tribute_id == winner_id:
                    # Pay double the bet amount + daily earnings for the winner
                    user_gold += bet_data["amount"] * 2
                    # Clear bets after game ends
            await self.config.user_from_id(user_id).gold.set(user_gold)
            await self.config.user_from_id(user_id).bets.set({})

                # **Award 50% of total bets to the winner**
        winner_bonus = int(total_bet_on_winner * 0.5)  # 50% of total bets
        if winner_bonus > 0 and not winner.get("is_npc", False):  # Only give to real players
            winner_gold = await self.config.user_from_id(int(winner_id)).gold()
            winner_gold = winner_bonus + winner_gold
            await self.config.user_from_id(int(winner_id)).gold.set(winner_gold)
            await ctx.send(f"💰 {winner['name']} receives **{winner_bonus} gold** from the bets placed on them!")



            # Update total kill counts for each player
        for player_id, player_data in players.items():
            if not player_data.get("is_npc") and player_data["kill_list"]:
                user_id = int(player_id)
                total_kills = len(player_data["kill_list"])
                current_kill_count = await self.config.user_from_id(user_id).kill_count()
                await self.config.user_from_id(user_id).kill_count.set(current_kill_count + total_kills)

        await self.config.guild(guild).clear()
        await self.config.guild(guild).set({
            "districts": {},
            "players": {},
            "game_active": False,
            "day_duration": 120,
            "day_start": None,
            "day_counter": 0,
            "WLboard": WLboard,  # Preserve leaderboard data
        })
        
        all_users = await self.config.all_users()
        for user_id, user_data in all_users.items():
            await self.config.user_from_id(user_id).bets.set({})

    
        # Reset players
        await self.config.guild(guild).players.set({})
        await self.config.guild(guild).game_active.set(False)
        await self.config.guild(guild).elimination_leaderboard.set([])  # Reset leaderboard
        file = f"Hunger_Games.txt"
        async with aiofiles.open(file, mode="a") as file:  # "a" for append mode
            await file.write(f"💰 {winner['name']} receives **{winner_bonus} gold** from the bets placed on them!\n")  

        file_name = "Hunger_Games.txt"
        async with aiofiles.open(file_name, mode='r') as file:
            file_content = await file.read()
    
        member_dict = {str(member.id): (member.nick or member.name) for member in guild.members}
        
        for user_id, nickname in member_dict.items():
            mention = f"<@{user_id}>"
            if mention in file_content:
                file_content = file_content.replace(mention, nickname)
    
        async with aiofiles.open(file_name, mode='w') as file:
            await file.write(file_content)
        
        await ctx.send(file=discord.File("Hunger_Games.txt"))


        if os.path.exists("Hunger_Games.txt"):
            os.remove("Hunger_Games.txt")
        

    async def process_day(self, ctx):
        """Process daily events and actions."""
        guild = ctx.guild
        config = await self.config.guild(guild).all()  # Add this line to fetch config
        players = config["players"]
        event_outcomes = []
        hunted = set()
        hunters = []
        looters = []
        resters = []
        feast_participants = []  # Separate list for Feast participants
        eliminations = []
                
        day_counter = config.get("day_counter", 0) + 1
        await self.config.guild(guild).day_counter.set(day_counter)

        if day_counter > 15:
            reduction = (day_counter - 15) // 3   
            
            event_outcomes.append("A mysterious mist has descended upon the arena, sapping the abilites of all participants!")

            for player_id, player_data in players.items():
                if not player_data["alive"]:
                    continue
    
                # Choose a random stat to reduce
                stats = ["Def", "Str", "Con", "Wis"]
                stat_to_reduce = max(stats, key=lambda stat: player_data["stats"][stat])
                player_data["stats"][stat_to_reduce] -= reduction

                # Check if the player dies
                if player_data["stats"][stat_to_reduce] <= 0:
                    player_data["alive"] = False
                    event_outcomes.append(f"{player_data['name']} succumbed to the mist and perished.")
                    player_data["items"] = []  # Drop all items



        # Categorize players by action
        for player_id, player_data in players.items():
            if not player_data["alive"]:
                continue
            
            if config["feast_active"] and player_data.get("action") is None:
                player_data["action"] = random.choices(
                        ["Feast", "Hunt", "Rest", "Loot"], weights=[60, 20, 10, 10], k=1
                    )[0]
            elif player_data.get("action") is None: 
                player_data["action"] = random.choices(
                        ["Hunt", "Rest", "Loot"], weights=[player_data["stats"]["Str"], player_data["stats"]["Con"]+len(player_data["items"])*3, player_data["stats"]["Wis"]], k=1
                    )[0]

            if player_data.get("is_npc"):
                if config["feast_active"]:
                    # 80% chance NPC attends the Feast, adjust weights as needed
                    player_data["action"] = random.choices(
                        ["Feast", "Hunt", "Rest", "Loot"], weights=[60, 20, 10, 10], k=1
                    )[0]
                else:
                    player_data["action"] = random.choices(["Hunt", "Rest", "Loot"], weights=[player_data["stats"]["Str"], player_data["stats"]["Con"]+len(player_data["items"])*3, player_data["stats"]["Wis"]], k=1)[0]
            
            action = player_data["action"]

            if action == "Hunt":
                hunters.append(player_id)
                #event_outcomes.append(f"{player_data['name']} went hunting!")
            elif action == "Rest":
                resters.append(player_id)

                if player_data["stats"]["HP"] < player_data["stats"]["Con"]:
                    damage = random.randint(1, int(player_data["stats"]["Con"] / 2))
                    player_data["stats"]["HP"] += damage
                    event_outcomes.append(f"{player_data['name']} nursed their wounds and healed for {damage} points of damage.")
                
                if not player_data["items"]:  # No items to use, take damage instead
                    damage = random.randint(1, 5)
                    player_data["stats"]["HP"] -= damage
                    event_outcomes.append(f"{player_data['name']} has hunger pangs and takes {damage} points of damage.")
                
                    if player_data["stats"]["HP"] <= 0:
                        player_data["alive"] = False
                        event_outcomes.append(f"{player_data['name']} starved to death.")
                    continue
                else:
                    item = player_data["items"].pop()
                    stat, boost = item
                    player_data["stats"][stat] += boost
                    event_outcomes.append(f"{player_data['name']} rested and used a {stat} boost item (+{boost}).")
                    
            elif action == "Loot":
                looters.append(player_id)
                if random.random() < 0.75:  # 75% chance to find an item
                    stat = random.choice(["Def", "Str", "Con", "Wis"])
                    if stat == "HP":
                        boost = random.randint(5,10)
                    else:
                        boost = random.randint(1, 3)
                    player_data["items"].append((stat, boost))

                    
                    effect = await self.load_file(
                        f"loot_good_{stat}.txt",
                        name1=player_data['name'],
                        dmg=boost,
                        )

                    event_outcomes.append(effect)
                else:
                    threshold = 1 / (1 + player_data["stats"]["Wis"] / 10)  # Scale slows the decrease
                    if random.random() < threshold:
                        damage = random.randint(1,5)
                        player_data["stats"]["HP"]=player_data["stats"]["HP"] - damage

                        effect = await self.load_file(
                            f"loot_real_bad.txt",
                            name1=player_data['name'],
                            dmg=damage,
                            )
                        event_outcomes.append(effect)
                        
                        if player_data["stats"]["HP"] <= 0:
                            player_data["alive"] = False
                            event_outcomes.append(f"{player_data['name']} has been eliminated by themselves?!")
                            player_data["kill_list"].append(player_data['name'])
                            player_data["items"] = []
                    else:
                        effect = await self.load_file("loot_bad.txt",name1=player_data['name'])
                        event_outcomes.append(effect)
            elif action == "Feast":
                feast_participants.append(player_id)

        # Shuffle hunters for randomness
        random.shuffle(hunters)

        # Create priority target lists
        targeted_hunters = hunters[:]
        targeted_looters = looters[:]
        targeted_resters = resters[:]

        # Resolve hunting events
        for hunter_id in hunters:
            if hunter_id in hunted:
                continue

            # Find a target in priority order, excluding the hunter themselves
            target_id = None
            for target_list in [targeted_hunters, targeted_looters, targeted_resters]:
                while target_list:
                    potential_target = target_list.pop(0)
                    if potential_target != hunter_id and potential_target not in hunted:
                        target_id = potential_target
                        break
                if target_id:
                    break

            if not target_id:
                continue

            hunter = players[hunter_id]
            target = players[target_id]

            target_defense = target["stats"]["Def"] + random.randint(1+int((target["stats"]["Con"]/4)), 10+int(target["stats"]["Con"]))
            hunter_str = hunter["stats"]["Str"] + random.randint(1+int(target["stats"]["Wis"]/4), 10+int(hunter["stats"]["Wis"]))
            damage = abs(hunter_str - target_defense)

            if damage < 2:
                damage1 = damage + random.randint(1,3)
                target["stats"]["HP"] -= damage1
                damage2 = damage + random.randint(1,3)
                hunter["stats"]["HP"] -= damage2

                effect = await self.load_file(
                    "tie_attack.txt",
                    name1=hunter['name'],
                    name2=target['name'],
                    dmg=damage1,
                    dmg2=damage2
                    )
                
                event_outcomes.append(effect)
                if target["stats"]["HP"] <= 0:
                    target["alive"] = False
                    event_outcomes.append(f"{target['name']} has been eliminated by {hunter['name']}!")
                    hunter["kill_list"].append(target['name'])
                    if target["items"]:
                        hunter["items"].extend(target["items"])
                        event_outcomes.append(
                            f"{hunter['name']} looted {len(target['items'])} item(s) from {target['name']}."
                        )
                        target["items"] = [] 
                        
                if hunter["stats"]["HP"] <= 0:
                    hunter["alive"] = False
                    event_outcomes.append(f"{hunter['name']} has been eliminated by {target['name']}!")
                    target["kill_list"].append(hunter['name'])
                    if hunter["items"]:
                        target["items"].extend(hunter["items"])
                        event_outcomes.append(
                            f"{target['name']} looted {len(hunter['items'])} item(s) from {hunter['name']}."
                        )
                        hunter["items"] = []
            else:
                if hunter_str > target_defense:
                    target["stats"]["HP"] -= damage
                    
                    effect = await self.load_file(
                        "feast_attack.txt",
                        name1=hunter['name'],
                        name2=target['name'],
                        dmg=damage,
                        )
                    
                    event_outcomes.append(effect)
                    if target["stats"]["HP"] <= 0:
                        target["alive"] = False
                        event_outcomes.append(f"{target['name']} has been eliminated by {hunter['name']}!")
                        hunter["kill_list"].append(target['name'])
                        if target["items"]:
                            hunter["items"].extend(target["items"])
                            event_outcomes.append(
                                f"{hunter['name']} looted {len(target['items'])} item(s) from {target['name']}."
                            )
                            target["items"] = [] 
                else:
                    hunter["stats"]["HP"] -= damage

                    effect = await self.load_file(
                        "feast_attack.txt",
                        name1=target['name'],
                        name2=hunter['name'],
                        dmg=damage,
                        )
                    
                    event_outcomes.append(effect)
                    if hunter["stats"]["HP"] <= 0:
                        hunter["alive"] = False
                        event_outcomes.append(f"{hunter['name']} has been eliminated by {target['name']}!")
                        target["kill_list"].append(hunter['name'])
                        if hunter["items"]:
                            target["items"].extend(hunter["items"])
                            event_outcomes.append(
                                f"{target['name']} looted {len(hunter['items'])} item(s) from {hunter['name']}."
                            )
                            hunter["items"] = []

            # Mark both the hunter and target as involved in an event
            hunted.add(target_id)
            hunted.add(hunter_id)


            # Resolve Feast after other actions
        if config["feast_active"] and feast_participants:
            if len(feast_participants) == 1:
                # Single participant gains +5 to all stats
                participant = players[feast_participants[0]]
                for stat in ["Def", "Str", "Con", "Wis", "HP"]:
                    participant["stats"][stat] += 5
                event_outcomes.append(f"{participant['name']} attended the Feast alone and gained +5 to all stats!")
            else:
                # Multiple participants battle it out
                dead_players = []
                for _ in range(3):  # 3 battle rounds
                    if len(feast_participants) <= 1:
                        break
                    for participant_id in feast_participants[:]:
                        if participant_id in dead_players:
                            continue
                        valid_targets = [p for p in feast_participants if p != participant_id and p not in dead_players]
                        if not valid_targets:
                            break
                        target_id = random.choice(valid_targets)
                        participant = players[participant_id]
                        target = players[target_id]
                        participant_str = participant["stats"]["Str"] + random.randint(1, 10)
                        target_str = target["stats"]["Def"] + random.randint(1, 10)
    
                        if participant_str > target_str:
                            damage = participant_str - target_str
                            target["stats"]["HP"] -= damage
                          
                            effect = await self.load_file(
                                "feast_attack.txt",
                                name1=participant['name'],
                                name2=target['name'],
                                dmg=damage
                            )
                            
                            event_outcomes.append(effect)
                            if target["stats"]["HP"] <= 0:
                                target["alive"] = False
                                dead_players.append(target_id)
                                feast_participants.remove(target_id)
                                participant["items"].extend(target["items"])
                                target["items"] = []
                                event_outcomes.append(f"{target['name']} was eliminated by {participant['name']}!")
                                participant["kill_list"].append(target['name'])
                        else:
                            damage = target_str - participant_str
                            participant["stats"]["HP"] -= damage
                            effect = await self.load_file(
                                "feast_attack.txt",
                                name1=target['name'],
                                name2=participant['name'],
                                dmg=damage
                            )
                            event_outcomes.append(effect)
                            if participant["stats"]["HP"] <= 0:
                                participant["alive"] = False
                                dead_players.append(participant_id)
                                feast_participants.remove(participant_id)
                                target["items"].extend(participant["items"])
                                participant["items"] = []
                                event_outcomes.append(f"{participant['name']} was eliminated by {target['name']}!")
                                target["kill_list"].append(participant['name'])
    
                # Remaining participants split items and stats
                if feast_participants:
                    all_dropped_items = []
                    for dead_id in dead_players:
                        all_dropped_items.extend(players[dead_id]["items"])
                        players[dead_id]["items"] = []
    
                    # Distribute items
                    if all_dropped_items:
                        random.shuffle(all_dropped_items)
                        for item in all_dropped_items:
                            chosen_participant_id = random.choice(feast_participants)
                            players[chosen_participant_id]["items"].append(item)
                        event_outcomes.append("Feast participants split the items dropped by the eliminated players.")
                        
    
                    # Distribute +5 stat bonuses randomly
                    stat_bonus = 5
                    stats_to_distribute = ["Def", "Str", "Con", "Wis", "HP"]
                    for _ in range(stat_bonus):
                        for stat in stats_to_distribute:
                            if feast_participants:
                                chosen_participant_id = random.choice(feast_participants)
                                players[chosen_participant_id]["stats"][stat] += 1
                    event_outcomes.append("Surviving Feast participants split the remaining items among themselves! Taking time to apply the boosts.")


        # Save the updated players' state
        await self.config.guild(guild).players.set(players)

        day_counter = config.get("day_counter", 0)
        
        # Elimination announcement and tracking
        for player_id, player_data in players.items():
            if player_data["alive"] is False and "eliminated_on" not in player_data:
                player_data["eliminated_on"] = day_counter  # Track day of elimination
                eliminations.append(player_data)

        await self.config.guild(guild).players.set(players)

        # Announce the day's events
        if event_outcomes:
            eliminated = [event for event in event_outcomes if "was eliminated by" in event]
            others = [event for event in event_outcomes if "was eliminated by" not in event]

            # Combine the lists with 'others' first and 'eliminated' last
            if eliminated:
                others.append("A cannon sounds signaling another set of dead tributes \n\n")
                event_outcomes = others + eliminated
        #Prepare the events log file
            file_name = f"Hunger_Games.txt"
            async with aiofiles.open(file_name, mode='a') as file:
                # Pings users and bolds NPCs
                for each in event_outcomes:
                    await file.write(each + '\n')
                    await ctx.send(each)
            #await ctx.send("\n".join(event_outcomes))
        else:
           await ctx.send("The day passed quietly, with no significant events.")

    
        # Save elimination leaderboard
        if eliminations:
            leaderboard = config.get("elimination_leaderboard", [])
            for eliminated_player in eliminations:
                leaderboard.append(
                    {"name": eliminated_player["name"], "day": eliminated_player["eliminated_on"]}
                )
            await self.config.guild(guild).elimination_leaderboard.set(leaderboard)
        
        # Process daily bet earnings
        players = await self.config.guild(guild).players()
        all_users = await self.config.all_users()
        
        for user_id, user_data in all_users.items():
            bets = user_data.get("bets", {})
            user_gold = user_data.get("gold", 0)

            day_counter = config.get("day_counter", 0)

            for tribute_id, bet_data in bets.items():
                if tribute_id in players and players[tribute_id]["alive"]:
                    
                    daily_return = max(int(bet_data["amount"] * min(0.01 * day_counter, 0.20)),1)  
                    bet_data["daily_earnings"] += daily_return
                    user_gold += daily_return
        
            await self.config.user_from_id(user_id).gold.set(user_gold)
            await self.config.user_from_id(user_id).bets.set(bets)

    @hunger.command()
    @is_gamemaster()
    async def nextday(self, ctx):
        """Set the real-time length of a day in seconds (Admin only)."""
        guild = ctx.guild
        await self.config.guild(guild).day_duration.set(0)
        await ctx.send(f"The next day will start next cycle.")

    @hunger.command()
    @is_gamemaster()
    async def stopgame(self, ctx):
        """Stop the Hunger Games early (Admin only). Reset everything."""
        await self.endGame(ctx)
        await ctx.send("The Hunger Games have been stopped early by the admin. All settings and players have been reset.")

    @hunger.command()
    async def viewstats(self, ctx):
        """View your own stats in a detailed, formatted embed."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        
        user_id = str(ctx.author.id)
        if user_id not in players:
            await ctx.send("You are not part of the Hunger Games.", ephemeral=True)
            return
        
        player = players[user_id]
        status = "🟢 **Alive**" if player["alive"] else "🔴 **Eliminated**"
    
        # 🎨 Create a styled embed
        embed = discord.Embed(
            title="🏹 **Your Tribute Stats** 🏹",
            description=f"{status}",
            color=discord.Color.gold()
        )
        embed.add_field(name="🏛 **District**", value=f"{player['district']}", inline=False)
        embed.add_field(name="🛡️ **Defense**", value=f"{player['stats']['Def']}", inline=True)
        embed.add_field(name="⚔️ **Strength**", value=f"{player['stats']['Str']}", inline=True)
        embed.add_field(name="💪 **Constitution**", value=f"{player['stats']['Con']}", inline=True)
        embed.add_field(name="🧠 **Wisdom**", value=f"{player['stats']['Wis']}", inline=True)
        embed.add_field(name="❤️ **HP**", value=f"{player['stats']['HP']}", inline=True)
    
        await ctx.send(embed=embed, ephemeral=True)


    @hunger.command()
    async def place_bet(self, ctx, amount: int, *, tribute: str):
        """Place a bet on a tribute."""

        if not ("<" in tribute):
            tribute = f"**{tribute}**"

        tribute = tribute.strip()  # Clean up any extra spaces        
        
        if amount <= 0:
            await ctx.send("Bet amount must be greater than zero.")
            return
    
        user_gold = await self.config.user(ctx.author).gold()
        if amount > user_gold:
            await ctx.send("You don't have enough gold to place that bet. You can always play in the games to earn money.")
            return
    
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        tribute = tribute.lower()

        config = await self.config.guild(guild).all()
        
        day_counter = config.get("day_counter", 0)

        # Restrict betting to days 1 and 2
        if day_counter > 1:
            await ctx.send("Betting is only allowed on Day 0 and Day 1.")
            return
    
        # Validate tribute
        tribute_id = next((pid for pid, pdata in players.items() if pdata["name"].lower() == tribute), None)
        if not tribute_id:
            await ctx.send("Tribute not found. Please check the name and try again.")
            return
    
        # Save the bet
        user_bets = await self.config.user(ctx.author).bets()
        if tribute_id in user_bets:
            await ctx.send("You have already placed a bet on this tribute.")
            return
    
        user_bets[tribute_id] = {
            "amount": amount,
            "daily_earnings": 0
        }
        await self.config.user(ctx.author).bets.set(user_bets)
    
        # Deduct gold
        await self.config.user(ctx.author).gold.set(user_gold - amount)
    
        tribute_name = players[tribute_id]["name"]
        await ctx.send(f"{ctx.author.mention} has placed a bet of {amount} gold on {tribute_name}. Good luck!")
    
    @hunger.command()
    async def check_gold(self, ctx):
        """Check your current gold."""
        user_gold = await self.config.user(ctx.author).gold()
        await ctx.send(f"{ctx.author.mention}, you currently have {user_gold} gold.")

    @hunger.command()
    async def leaderboard(self, ctx):
        """Display leaderboards for total kills and gold."""
        all_users = await self.config.all_users()
        guild_config = await self.config.guild(ctx.guild).all()
        
        # Gather and sort kill counts
        kill_leaderboard = sorted(
            all_users.items(),
            key=lambda x: x[1].get("kill_count", 0),
            reverse=True
        )
        
        # Gather and sort gold counts
        gold_leaderboard = sorted(
            all_users.items(),
            key=lambda x: x[1].get("gold", 0),
            reverse=True
        )
        
        # Gather and sort winner leaderboard
        WLboard = guild_config.get("WLboard", {})
        sorted_winners = sorted(
            WLboard.values(),
            key=lambda x: x["wins"],
            reverse=True,
        )    

        embed = discord.Embed(title="🏆 Hunger Games Leaderboard 🏆", color=discord.Color.gold())
        # Add top players by kills
        if kill_leaderboard:
            kills_text = "\n".join(
                f"**{ctx.guild.get_member(int(user_id)).mention}**: {data['kill_count']} kills"
                for user_id, data in kill_leaderboard[:5]
                if ctx.guild.get_member(int(user_id))  # Ensure the user exists in the guild
            )
            embed.add_field(name="Top Killers", value=kills_text or "No data", inline=False)

         # Add most wins
        if sorted_winners:
            medals = ["🥇", "🥈", "🥉"]
            winner_text = "\n".join(
                f"{medals[idx]} **{winner['name']}**: {winner['wins']} wins"
                for idx, winner in enumerate(sorted_winners[:3])
            )
            embed.add_field(name="Top Winners", value=winner_text or "No data", inline=False)
    
        # Add top players by gold
        if gold_leaderboard:
            gold_text = "\n".join(
                f"**{ctx.guild.get_member(int(user_id)).mention}**: {data['gold']} gold"
                for user_id, data in gold_leaderboard[:5]
                if ctx.guild.get_member(int(user_id))  # Ensure the user exists in the guild
            )
            embed.add_field(name="Top Richest Players", value=gold_text or "No data", inline=False)
    
        await ctx.send(embed=embed)

        WLboard = guild_config.get("WLboard", [])
    
    @hunger.command()
    @commands.admin()
    async def reset_leaderboard(self, ctx):
        """Reset all user kill counts and gold."""
        all_users = await self.config.all_users()
        for user_id in all_users:
            await self.config.user_from_id(int(user_id)).kill_count.set(0)
            await self.config.user_from_id(int(user_id)).gold.set(0)
        await ctx.send("Leaderboards have been reset.")


    @hunger.command()
    async def how_to_play(self, ctx):
        """Learn how to play the Hunger Games bot."""
        embed = discord.Embed(
            title="How to Play the Hunger Games Bot",
            description="Welcome to the Hunger Games! Here's a quick guide to get you started.",
            color=discord.Color.green()
        )
        embed.add_field(
            name="1. Sign Up",
            value=(
                "Use the `!hunger signup` command to join the game. "
                "You'll be assigned to a random district and given stats like Strength, Defense, Wisdom, Constitution, and HP. Your family is also sent 100 gold pre-bereavement gift."
            ),
            inline=False
        )
        embed.add_field(
            name="2. Actions",
            value=(
                "Each day, choose an action:\n"
                "- **Hunt**: Attack other tributes and try to eliminate them.\n"
                "- **Rest**: Recover and use items to restore stats.\n"
                "- **Loot**: Search for valuable items to boost your stats."
            ),
            inline=False
        )
        embed.add_field(
            name="3. Betting (Days 0 & 1 Only)",
            value=(
                "Place bets on your favorite tributes using the action buttons. "
                "Earn 20% of your bet back each day the tribute survives, and double your bet if they win!"
            ),
            inline=False
        )
        embed.add_field(
            name="4. Survive!",
            value=(
                "Your goal is to be the last tribute standing. Survive random events, fights, and the challenges of the arena."
            ),
            inline=False
        )
        embed.add_field(
            name="5. Feasts",
            value=(
                "Every 10 days, and the first day a Feast is held. Choose the `Feast` action to participate and gain powerful boosts, "
                "but beware—others may attack you during the Feast!"
            ),
            inline=False
        )
        embed.add_field(
            name="6. Leaderboards",
            value=(
                "Check your kills and gold with `!hunger leaderboard`. Compete for top spots in kills and gold on the leaderboards!"
            ),
            inline=False
        )
        embed.add_field(
            name="7. Sponsoring",
            value=(
                "If you just fall in love with one of the tributes you can spend gold to help them out, use the sponsor button on any day to send them an item."
            ),
            inline=False
        )
        embed.set_footer(text="Good luck, and may the odds be ever in your favor!")
        
        await ctx.send(embed=embed)
    
    @hunger.command()
    async def view_signups(self, ctx):
        """View the current list of players signed up for the Hunger Games."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
    
        if not players:
            await ctx.send("No players have signed up for the Hunger Games yet.")
            return
    
        # Create an embed to display the player information
        embed = discord.Embed(
            title="Current Hunger Games Signups",
            description="Here is the list of players currently signed up:",
            color=discord.Color.blue(),
        )
    
        for player_id, player_data in players.items():
            player_name = player_data["name"]
            district = player_data["district"]
            status = "Alive" if player_data["alive"] else "Eliminated"
            embed.add_field(
                name=f"District {district}: {player_name}",
                value=f"Status: **{status}**",
                inline=False,
            )
    
        await ctx.send(embed=embed)
    
    @hunger.command()
    @is_gamemaster()
    async def clear_signups(self, ctx):
        """Clear all signups and reset the player list (Admin only)."""
        guild = ctx.guild
        await self.config.guild(guild).players.clear()
        await ctx.send("All signups have been cleared. The player list has been reset.")

    

    




    

