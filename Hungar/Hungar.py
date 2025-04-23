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
from discord import app_commands
import math
import json


class MapButton(Button):
    def __init__(self, cog):
        super().__init__(label="View Map", style=discord.ButtonStyle.primary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        try:
            guild = interaction.guild
            zones = await self.cog.config.guild(guild).zones2()

            if not zones:
                await interaction.response.send_message(
                    "There are no active zones to display right now.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🗺️ Arena Map - Active Zones",
                description="Here are the zones currently in play:",
                color=discord.Color.green()
            )

            for zone in zones:
                if not isinstance(zone, dict):
                    continue  # or log it
                name = zone.get("name", "Unknown Zone")
                desc = zone.get("description", "No description provided.")
                embed.add_field(name=name, value=desc, inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"⚠️ An error occurred while loading the map.\n```{e}```",
                ephemeral=True
            )


class EqualizerButton(Button):
    """Button for the Gamemaster to balance the game by bringing all tributes up to the same total stat value."""
    
    def __init__(self, cog, guild, channel):
        super().__init__(label="Equalizer", style=discord.ButtonStyle.primary)
        self.cog = cog
        self.guild = guild
        self.channel = channel

    async def callback(self, interaction: Interaction):
        """Triggers the Equalizer event to balance all tributes' total stats."""
        try:
            config = await self.cog.config.guild(self.guild).all()
            players = config["players"]

            if not players:
                await interaction.response.send_message("No tributes to equalize!", ephemeral=True)
                return

            # Get only alive players
            alive_players = {p_id: p for p_id, p in players.items() if p["alive"]}
            if not alive_players:
                await interaction.response.send_message("No alive tributes to equalize!", ephemeral=True)
                return

            # Calculate total stats for each player
            total_stats = {p_id: sum(p["stats"].values()) for p_id, p in alive_players.items()}
            max_stats = max(total_stats.values())  # The highest total stat value
            stat_choices = ["Def", "Str", "Con", "Wis", "HP"]

            # Track boost distribution per player
            boost_distribution = {p_id: 0 for p_id in alive_players.keys()}

            # **Iterate through players, adding stats until they match the max total stats**
            for p_id, tribute in alive_players.items():
                current_total = total_stats[p_id]
                missing_stats = max_stats - current_total  # Amount needed to match the strongest player
                
                while missing_stats > 0:
                    boost_stat = random.choice(stat_choices)  # Randomly select a stat
                    boost_amount = min(missing_stats, random.randint(1, 5))  # Ensure we don't over-boost

                    # Apply the boost
                    tribute["stats"][boost_stat] += boost_amount
                    boost_distribution[p_id] += boost_amount
                    missing_stats -= boost_amount  # Decrease the remaining needed amount

            # Save the updated stats
            await self.cog.config.guild(self.guild).players.set(players)

            # Announce the event
            boost_messages = [
                f"**{players[p_id]['name']}** gained **+{amount}** total stats!"
                for p_id, amount in boost_distribution.items()
            ]
            boost_summary = "\n".join(boost_messages)

            await self.channel.send(
                "⚖️ **The Equalizer Strikes!** ⚖️\n"
                "A mysterious force seeks balance... All tributes now stand as equals yet still differnt!\n\n"
                f"{boost_summary}\n\nMay the best tribute survive! 🏹🔥"
            )

            await interaction.response.send_message("Equalizer activated successfully!", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)




class CheckGoldButton(Button):
    """Button to display the user's current Wellcoins"""

    def __init__(self, cog):
        super().__init__(label="Check Wellcoins", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        try:
            user_id = interaction.user
            gold = await self.cog.config_gold.user(user_id).master_balance()
            await interaction.response.send_message(f"You have {gold} Wellcoins.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

        

class AllTributesView(View):
    def __init__(self, cog, pages, per_page=5):
        super().__init__(timeout=120)
        self.cog = cog
        self.pages = pages
        self.page = 0
        self.per_page = per_page
        self.total_pages = len(pages)

        self.prev_button = Button(label="⬅️ Back", style=discord.ButtonStyle.secondary, disabled=True)
        self.next_button = Button(label="Next ➡️", style=discord.ButtonStyle.secondary, disabled=(self.total_pages <= 1))

        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    def get_embed(self):
        embed = discord.Embed(
            title="🏹 Hunger Games Tributes 🏹",
            description=f"Page {self.page + 1} of {self.total_pages}\nHere are the current tributes and their stats:",
            color=discord.Color.gold()
        )

        for field in self.pages[self.page]:
            embed.add_field(name=field["name"], value=field["value"], inline=False)

        return embed

    async def update_message(self, interaction: Interaction):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def next_page(self, interaction: Interaction):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_message(interaction)

    async def prev_page(self, interaction: Interaction):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)


class ViewAllTributesButton(Button):
    """Button to display all tribute stats with pagination."""
    def __init__(self, cog, guild):
        super().__init__(label="View All Tributes", style=discord.ButtonStyle.secondary)
        self.cog = cog
        self.guild = guild

    async def callback(self, interaction: Interaction):
        try:
            config = await self.cog.config.guild(self.guild).all()
            players = config["players"]

            if not players:
                await interaction.response.send_message("❌ No tributes are currently in the game.", ephemeral=True)
                return

            sorted_players = sorted(players.items(), key=lambda p: p[1]["district"])
            tribute_fields = []

            for player_id, player in sorted_players:
                # Resolve display name
                if player_id.isdigit():
                    member = self.guild.get_member(int(player_id))
                    display_name = member.nick or member.name if member else player["name"]
                else:
                    display_name = player["name"]

                status = "🟢 **Alive**" if player["alive"] else "🔴 **Eliminated**"

                tribute_fields.append({
                    "name": f"District {player['district']}: {display_name}",
                    "value": (
                        f"{status}\n"
                        f"**🛡️ Def:** {player['stats']['Def']}\n"
                        f"**⚔️ Str:** {player['stats']['Str']}\n"
                        f"**💪 Con:** {player['stats']['Con']}\n"
                        f"**🧠 Wis:** {player['stats']['Wis']}\n"
                        f"**❤️ HP:** {player['stats']['HP']}"
                    )
                })

            # Paginate into pages of 5 tributes each
            per_page = 5
            pages = [tribute_fields[i:i + per_page] for i in range(0, len(tribute_fields), per_page)]

            view = AllTributesView(self.cog, pages, per_page)
            await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error: `{type(e).__name__}: {e}`", ephemeral=True)


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

        self.add_item(EqualizerButton(cog, guild, public_channel))

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
        super().__init__(label="Sponsor a Random Tribute (10 Wellcoins)", style=discord.ButtonStyle.success)
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
        boost_amount = random.randint(1, 5)  # Normal random boost amount

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
    """Button that tells players to use the slash command instead of sponsoring directly."""
    def __init__(self,cog):
        super().__init__(label="Sponsor a Tribute", style=discord.ButtonStyle.success)

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message(
            "Use the `/sponsor` slash command to choose a tribute and send a gift. The price increases each day!",
            ephemeral=True
        )






class BidRankingView(View):
    def __init__(self, cog, pages, per_page=5):
        super().__init__(timeout=120)
        self.cog = cog
        self.pages = pages
        self.per_page = per_page
        self.page = 0
        self.total_pages = len(pages)

        self.prev_button = Button(label="⬅️ Back", style=discord.ButtonStyle.secondary, disabled=True)
        self.next_button = Button(label="Next ➡️", style=discord.ButtonStyle.secondary, disabled=(self.total_pages <= 1))

        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    def get_embed(self):
        embed = discord.Embed(
            title="🏅 Tribute Betting Rankings 🏅",
            description=f"Page {self.page + 1} of {self.total_pages}",
            color=discord.Color.gold()
        )

        for field in self.pages[self.page]:
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=False
            )

        return embed

    async def update_message(self, interaction: Interaction):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def next_page(self, interaction: Interaction):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_message(interaction)

    async def prev_page(self, interaction: Interaction):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)


class ViewBidsButton(Button):
    def __init__(self, cog):
        super().__init__(label="View Bids", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        try:
            guild = interaction.guild
            players = await self.cog.config.guild(guild).players()
            all_users = await self.cog.config.all_users()

            bid_totals = {}
            bet_details = {}

            for player_id, player_data in players.items():
                if not player_data.get("alive"):
                    continue

                tribute_bets = player_data.get("bets", {})
                total_bets = 0
                details = []

                for user_id, user_data in all_users.items():
                    bets = user_data.get("bets", {})
                    if player_id in bets:
                        bet_amount = bets[player_id]["amount"]
                        total_bets += bet_amount
                        member = guild.get_member(int(user_id))
                        display_name = member.nick or member.name if member else f"User {user_id}"
                        details.append(f"{display_name}: {bet_amount} Wellcoins")

                ai_bets = tribute_bets.get("AI", [])
                for ai_bet in ai_bets:
                    total_bets += ai_bet["amount"]
                    details.append(f"{ai_bet['name']}: {ai_bet['amount']} Wellcoins")

                if total_bets > 0:
                    bid_totals[player_id] = total_bets
                    bet_details[player_id] = details

            sorted_tributes = sorted(bid_totals.items(), key=lambda item: item[1], reverse=True)

            # Paginate into chunks
            fields_per_page = 5
            all_fields = []
            for rank, (tribute_id, total_bet) in enumerate(sorted_tributes, start=1):
                tribute = players.get(tribute_id)
                if not tribute or not tribute.get("alive"):
                    continue
                district = tribute.get("district", "?")
                tribute_name = (
                    guild.get_member(int(tribute_id)).display_name
                    if tribute_id.isdigit() and guild.get_member(int(tribute_id))
                    else tribute.get("name", f"Unknown [{tribute_id}]")
                )
                details_text = "\n".join(bet_details[tribute_id]) or "No individual breakdown."

                all_fields.append({
                    "name": f"#{rank} {tribute_name} (District {district})",
                    "value": f"Total Bets: {total_bet} Wellcoins\n{details_text}"
                })

            if not all_fields:
                await interaction.response.send_message("❌ No bets have been placed yet.", ephemeral=True)
                return

            # Chunk into pages
            pages = [all_fields[i:i + fields_per_page] for i in range(0, len(all_fields), fields_per_page)]

            view = BidRankingView(self.cog, pages)
            await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error: `{type(e).__name__}: {e}`", ephemeral=True)






class BettingButton(Button):
    def __init__(self, cog):
        super().__init__(label="Place a Bet", style=discord.ButtonStyle.danger)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message("To place a bid do ``/placebid`` Remember you can only bid day 0 and 1")


class TributeRankingView(View):
    def __init__(self, cog, tribute_scores, per_page=10):
        super().__init__(timeout=120)
        self.cog = cog
        self.tribute_scores = tribute_scores
        self.per_page = per_page
        self.page = 0
        self.total_pages = math.ceil(len(tribute_scores) / per_page)

        # Buttons
        self.prev_button = Button(label="⬅️ Back", style=discord.ButtonStyle.secondary, disabled=True)
        self.next_button = Button(label="Next ➡️", style=discord.ButtonStyle.secondary, disabled=self.total_pages <= 1)

        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    def get_embed(self):
        start = self.page * self.per_page
        end = start + self.per_page
        embed = discord.Embed(
            title="Tribute Rankings",
            description=f"Page {self.page + 1} of {self.total_pages}",
            color=discord.Color.gold()
        )

        for rank, tribute in enumerate(self.tribute_scores[start:end], start=start + 1):
            embed.add_field(
                name=f"District {tribute['district']}",
                value=f"#{rank} {tribute['name']}\nScore: {tribute['score']}",
                inline=False
            )

        return embed

    async def update_message(self, interaction: Interaction):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def next_page(self, interaction: Interaction):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_message(interaction)

    async def prev_page(self, interaction: Interaction):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)

class ViewTributesButton(Button):
    def __init__(self, cog):
        super().__init__(label="View Tributes", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: Interaction):
        try:
            guild = interaction.guild
            if guild is None:
                raise ValueError("This command must be used in a server.")

            players = await self.cog.config.guild(guild).players()
            if not players:
                raise ValueError("No players found in the game.")

            # Calculate tribute scores
            tribute_scores = []
            for player_id, player in players.items():
                if player.get("alive"):
                    stats = player.get("stats", {})
                    if not stats:
                        raise ValueError(f"No stats found for player: {player['name']}")

                    score = (
                        stats.get("Def", 0)
                        + stats.get("Str", 0)
                        + stats.get("Con", 0)
                        + stats.get("Wis", 0)
                        + (stats.get("HP", 0) // 5)
                    )
                    tribute_scores.append({
                        "name": player.get("name", f"Unknown [{player_id}]"),
                        "district": player.get("district", "?"),
                        "score": score
                    })

            if not tribute_scores:
                raise ValueError("No alive tributes to show.")

            tribute_scores.sort(key=lambda x: x["score"], reverse=True)

            view = TributeRankingView(self.cog, tribute_scores)
            await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"⚠️ Something went wrong: `{type(e).__name__}: {e}`",
                ephemeral=True
            )


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
        if not feast_active:
            self.add_item(SponsorButton(cog))


        # Only add the Betting Button on Day 0 and Day 1
        if current_day in [0, 1]:
            self.add_item(BettingButton(cog))
        
        self.add_item(MapButton(cog))  # 👈 add this line
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

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        guild = interaction.guild
        players = await self.cog.config.guild(guild).players()

        if user_id not in players or not players[user_id]["alive"]:
            await interaction.response.send_message("You are not in the game or are no longer alive.", ephemeral=True)
            return

        # Load current active zones
        zones = await self.cog.config.guild(guild).zones2()
        if not zones:
            await interaction.response.send_message("⚠️ Zones have not been initialized yet.", ephemeral=True)
            return

        # Show dropdown view
        view = View()
        if not self.action == "Feast":
            view.add_item(ZoneSelect(self.cog, user_id, self.action, zones))
            await interaction.response.send_message(f"Choose a zone to **{self.action}** in:", view=view, ephemeral=True)
        else:
            await interaction.response.send_message(f"You have picked to attend the feast.", ephemeral=True)




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

class ZoneSelect(Select):
    def __init__(self, cog, user_id, action, zones):
        self.cog = cog
        self.user_id = user_id
        self.action = action
        options = [discord.SelectOption(label=z["name"], description=z.get("description", ""), value=z["name"]) for z in zones]

        super().__init__(placeholder="Choose a zone...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_zone = self.values[0]
        players = await self.cog.config.guild(interaction.guild).players()

        players[self.user_id]["action"] = self.action
        players[self.user_id]["zone"] = selected_zone
        await self.cog.config.guild(interaction.guild).players.set(players)

        await interaction.response.send_message(
            f"You have chosen to **{self.action}** in **{selected_zone}**.", ephemeral=True
        )


class Hungar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=1234567890)
        self.config_gold = Config.get_conf(None, identifier=345678654456, force_registration=False)
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
            zones2=[],       # currently active zones
            zone_pool2=[],   # full zone list
             
            
        )
        self.config.register_user(
            gold=0,
            bets={},
            kill_count=0,
            zone=""
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

    @app_commands.command(name="placebet", description="Place a bet on a tribute.")
    @app_commands.describe(
        tribute="Choose a living tribute",
        amount="Amount of Wellcoins to bet (number or 'all')"
    )
    async def place_bet(self, interaction: Interaction, tribute: str, amount: str):
        guild = interaction.guild
        user = interaction.user

        current_day = await self.config.guild(guild).day_counter()
        if current_day not in (0, 1):
            await interaction.response.send_message("❌ You can only place bets on Day 0 or Day 1.", ephemeral=True)
            return

        players = await self.config.guild(guild).players()

        tribute_data = players.get(tribute)
        if not tribute_data or not tribute_data.get("alive"):
            await interaction.response.send_message("❌ That tribute isn't alive or doesn't exist.", ephemeral=True)
            return

        user_gold = await self.config_gold.user(user).master_balance()

        if amount.lower() == "all":
            bet_amount = user_gold
        elif amount.isdigit():
            bet_amount = int(amount)
        else:
            await interaction.response.send_message("❌ Invalid amount. Please enter a number or 'all'.", ephemeral=True)
            return

        if bet_amount <= 0 or bet_amount > user_gold:
            await interaction.response.send_message(
                f"❌ You don't have enough Wellcoins. Your balance: {user_gold}", ephemeral=True
            )
            return

        # Deduct and record the bet
        await self.config_gold.user(user).master_balance.set(user_gold - bet_amount)
        user_bets = await self.config.user(user).bets()

        if tribute in user_bets:
            user_bets[tribute]["amount"] += bet_amount
        else:
            user_bets[tribute] = {"amount": bet_amount, "daily_earnings": 0}

        await self.config.user(user).bets.set(user_bets)
        await interaction.response.send_message(
            f"💰 {user.mention} bet **{bet_amount} Wellcoins** on **{tribute_data['name']}**!")

    @place_bet.autocomplete("tribute")
    async def tribute_autocomplete(self, interaction: Interaction, current: str):
        guild = interaction.guild
        players = await self.config.guild(guild).players()
        options = []
    
        for pid, pdata in players.items():
            if not pdata.get("alive"):
                continue
    
            # Resolve display name
            member = guild.get_member(int(pid)) if pid.isdigit() else None
            display_name = member.display_name if member else pdata.get("name", f"Unknown [{pid}]")
    
            # Get district (default to 99 for unknown to push them last)
            try:
                district = int(pdata.get("district", 99))
            except (ValueError, TypeError):
                district = 99
    
            label = f"[D{district}] {display_name}"
    
            if current.lower() in label.lower():
                options.append({
                    "district": district,
                    "choice": app_commands.Choice(name=label, value=pid)
                })
    
        # Sort by district number
        sorted_options = sorted(options, key=lambda x: x["district"])
    
        # Return only the Choice objects (limit 25)
        return [opt["choice"] for opt in sorted_options[:25]]



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


        # 🎖️ **Assign a Role to the User**
        role_name = "Tribute"  # Change this to match your role name
        role = get(guild.roles, name=role_name)  # Fetch the role
    
        if role:
            await ctx.author.add_roles(role)
        
        # Award 100 gold to the player in user config
        user_gold = await self.config_gold.user(ctx.author).master_balance()
        user_gold += 10
        await self.config_gold.user(ctx.author).master_balance.set(user_gold)
    

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

        base_path = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_path, "zone.json")
        with open(file_path) as f:
            all_zones = json.load(f)


        selected_zones = random.sample(all_zones, k=min(6, len(all_zones)))  # Start with 6 zones
        await self.config.guild(ctx.guild).zones2.set(selected_zones)
    
        # store total zone pool for shrinking
        await self.config.guild(ctx.guild).zone_pool2.set(all_zones)
        WLboard = await self.config.guild(ctx.guild).WLboard()
        # If each game has one winner:
        games_ran = sum(data.get("wins", 0) for data in WLboard.values())
        await ctx.send(f"Welcome to the: **{games_ran}** weekly game of The Wellspring")
        await ctx.send("🌍 The arena has been divided into zones. Let the Hunger Games begin!")

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
        
        # Add AI bettors
        ai_bettors = {}
        npc_names = await self.load_npc_names()
        for tribute_id, tribute in players.items():
            if not tribute["alive"]:
                continue
        
            ai_name = random.choice(npc_names)
            bet_amount = random.randint(5, 50)  # Random bet between 50 and 500 gold
        
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
    
        MAX_DISCORD_MESSAGE_LENGTH = 2000
        
        participant_announcement = "\n".join(participant_list)
        message_prefix = "The Hunger Games have begun with the following participants (sorted by District):\n"
        
        # Split safely by lines if too long
        messages = []
        current_message = message_prefix
        
        for line in participant_list:
            # +1 for newline
            if len(current_message) + len(line) + 1 > MAX_DISCORD_MESSAGE_LENGTH:
                messages.append(current_message)
                current_message = line + "\n"
            else:
                current_message += line + "\n"
        
        # Add the last message chunk
        if current_message.strip():
            messages.append(current_message)
        
        # Send each part
        for msg in messages:
            await ctx.send(msg)


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
        
        file = "Hunger_Games.txt"
        async with aiofiles.open(file, mode="a") as f:
            await f.write(f"Day {current_day}\n")

        # Reset all player actions to None
        for player_id, player_data in players.items():
            if player_data["alive"]:  # Only reset actions for alive players
                player_data["action"] = None
                player_data["zone"] = None  


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

        MAX_DISCORD_MESSAGE_LENGTH = 2000
        
        # Base message
        base_message = (
            f"Day {config['day_counter']} begins in the Hunger Games! {alive_count} participants remain.\n"
            f"{feast_message}\n"
            f"Alive participants:"
        )
        
        # Start building message chunks
        messages = [base_message]
        current_chunk = ""
        
        for mention in alive_mentions:
            if len(messages[-1]) + len(current_chunk) + len(mention) + 2 > MAX_DISCORD_MESSAGE_LENGTH:
                # Finalize the current chunk and start a new message
                messages[-1] += f" {current_chunk.strip(', ')}"
                current_chunk = mention + ", "
                messages.append("")
            else:
                current_chunk += mention + ", "
        
        # Add the last chunk to the last message
        if current_chunk:
            messages[-1] += f" {current_chunk.strip(', ')}"
        
        # Send each message
        for msg in messages:
            await ctx.send(msg.strip())

        # Calculate the next day start time
        day_start = datetime.utcnow()
        alive_count = len(alive_players)
        day_duration = min(max(int(alive_count) * 20 + 20,60),300)
        day_counter = config.get("day_counter", 0)
        if day_counter > 0 and day_counter % 10 == 0:
            day_duration = int(day_duration * 1.5)  # Feast days are longer
    
        next_day_start = day_start + timedelta(seconds=day_duration) - timedelta(hours=5)
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
        winner_id = ""
        winner = ""
        winner_bonus = 0
        guild = ctx.guild
        config = await self.config.guild(guild).all()
        players = config["players"]
        leaderboard = config.get("elimination_leaderboard", [])
        all_users = await self.config.all_users()
        alive_players = [player for player in players.values() if player["alive"]]
        WLboard = config.get("WLboard", {})
    
        role = get(guild.roles, name="Tribute")
        if role:
            for member in guild.members:
                if role in member.roles:
                    await member.remove_roles(role)
    
        # Lock GameMaster Dashboard
        dashboard_channel_id = config.get("dashboard_channel_id")
        dashboard_message_id = config.get("dashboard_message_id")
        if dashboard_channel_id and dashboard_message_id:
            dashboard_channel = guild.get_channel(dashboard_channel_id)
            if dashboard_channel:
                try:
                    message = await dashboard_channel.fetch_message(dashboard_message_id)
                    if message:
                        disabled_view = GameMasterView(self, guild, None)
                        for item in disabled_view.children:
                            item.disabled = True
                        await message.edit(content="🔒 **Game Over!** The GameMaster dashboard is now locked.", view=disabled_view)
                except discord.NotFound:
                    print("Dashboard message not found, skipping lockout.")
    
        # Declare winner
        if alive_players:
            winner = alive_players[0]
            winner_id = next((pid for pid, pdata in players.items() if pdata == winner), None)
            if not winner.get("is_npc", False):
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
            leaderboard.sort(key=lambda x: x["day"], reverse=True)
            elim_embed = discord.Embed(
                title="🏅 Elimination Leaderboard 🏅",
                description="Here are the players eliminated so far:",
                color=discord.Color.red(),
            )
            for entry in leaderboard[:25]:
                elim_embed.add_field(
                    name=f"Day {entry['day']}",
                    value=f"{entry['name']}",
                    inline=False
                )
            await ctx.send(embed=elim_embed)
    
            # Kill leaderboard
            sorted_players = sorted(players.values(), key=lambda p: len(p["kill_list"]), reverse=True)[:25]
            kill_embed = discord.Embed(
                title="🏆 Kill Leaderboard 🏆",
                description="Here are the top killers:",
                color=discord.Color.gold(),
            )
            sorted_players = sorted_players[:25]
            for i, player in enumerate(sorted_players, start=1):
                kills = len(player["kill_list"])
                kill_text = "kill" if kills == 1 else "kills"
                kill_embed.add_field(
                    name="",
                    value=f"**{i}.** {player['name']}: {kills} {kill_text}\nKilled: {', '.join(player['kill_list'])}",
                    inline=False
                )
            await ctx.send(embed=kill_embed)
    
            # Calculate total pot
            total_pot = 0
            for user_data in all_users.values():
                bets = user_data.get("bets", {})
                total_pot += sum(bet["amount"] for bet in bets.values())
    
            for tribute_data in players.values():
                npc_bets = tribute_data.get("bets", {}).get("AI", [])
                for ai_bet in npc_bets:
                    total_pot += ai_bet["amount"]
    
            winner_bonus = int(total_pot * 0.5)
    
        # Distribute winnings to users
        for user_id, user_data in all_users.items():
            bets = user_data.get("bets", {})
            user_balance = await self.config_gold.user_from_id(user_id).master_balance()
            for tribute_id, bet_data in bets.items():
                if tribute_id == winner_id:
                    user_balance += bet_data["amount"] * 2
            await self.config_gold.user_from_id(user_id).master_balance.set(user_balance)
            await self.config.user_from_id(user_id).bets.set({})
    
        # Give bonus to winner
        if winner_bonus > 0 and not winner.get("is_npc", False):
            winner_balance = await self.config_gold.user_from_id(int(winner_id)).master_balance()
            winner_balance += winner_bonus
            await self.config_gold.user_from_id(int(winner_id)).master_balance.set(winner_balance)
            await ctx.send(f"💰 {winner['name']} receives **{winner_bonus} Wellcoins** from the bets placed on them!")
    
        # Update kill counts
        for player_id, player_data in players.items():
            if not player_data.get("is_npc") and player_data["kill_list"]:
                user_id = int(player_id)
                total_kills = len(player_data["kill_list"])
                current_kill_count = await self.config.user_from_id(user_id).kill_count()
                await self.config.user_from_id(user_id).kill_count.set(current_kill_count + total_kills)
    
        # Reset game state
        await self.config.guild(guild).clear()
        await self.config.guild(guild).set({
            "districts": {},
            "players": {},
            "game_active": False,
            "day_duration": 120,
            "day_start": None,
            "day_counter": 0,
            "WLboard": WLboard,
        })
    
        for user_id in all_users:
            await self.config.user_from_id(user_id).bets.set({})
    
        await self.config.guild(guild).players.set({})
        await self.config.guild(guild).game_active.set(False)
        await self.config.guild(guild).elimination_leaderboard.set([])
    
        # Log result
        file = "Hunger_Games.txt"
        async with aiofiles.open(file, mode="a") as f:
            if winner:
                await f.write(f"💰 {winner['name']} receives **{winner_bonus} Wellcoins** from the bets placed on them!\n")
    
        async with aiofiles.open(file, mode='r') as f:
            file_content = await f.read()
    
        member_dict = {str(member.id): (member.nick or member.name) for member in guild.members}
        for user_id, nickname in member_dict.items():
            mention = f"<@{user_id}>"
            if mention in file_content:
                file_content = file_content.replace(mention, nickname)
    
        async with aiofiles.open(file, mode='w') as f:
            await f.write(file_content)
            await f.write("\n")

    
        await ctx.send(file=discord.File(file))
        if os.path.exists(file):
            os.remove(file)

        

    async def process_day(self, ctx):
        guild = ctx.guild
        config = await self.config.guild(guild).all()
        players = config["players"]
        zones = config.get("zones2", [])
        zone_pool = config.get("zone_pool2", [])
    
        valid_zone_names = [z["name"] for z in zones]
        
        for player_id, data in players.items():
            current_zone = data.get("zone")
            current_zone_name = current_zone.get("name") if isinstance(current_zone, dict) else current_zone
        
            if not current_zone_name or current_zone_name not in valid_zone_names:
                data["zone"] = random.choice(zones)
                

    
        # Group players by zone
        zone_groups = {}
        for player_id, data in players.items():
            if not data["alive"]:
                continue
            zone = data["zone"]
            
            if isinstance(zone, dict):
                zone = zone.get("name", "Cornucopia")
            zone_groups.setdefault(zone, []).append(player_id)
    
        # Day counter logic
        day_counter = config.get("day_counter", 0) + 1
        await self.config.guild(guild).day_counter.set(day_counter)
        
        event_outcomes = []

        if day_counter > 20:
            # Stat decay: reduce highest stat by growing % each day after Day 20
            decay_percent = min(0.05 * (day_counter - 20), 0.5)  # Max 50% decay
            decay_percent_display = int(decay_percent * 100)
        
            for pid, pdata in players.items():
                if not pdata["alive"]:
                    continue
        
                stats = pdata["stats"]
                highest_stat = max(["Str", "Con", "Wis", "Def","HP"], key=lambda s: stats[s])
                decay_amount = int(stats[highest_stat] * decay_percent)
        
                stats[highest_stat] -= decay_amount
                if stats[highest_stat] < 1:
                    stats[highest_stat] = 1  # Prevent stat from going to 0 or negative
        
                zone_name = pdata["zone"]["name"] if isinstance(pdata["zone"], dict) else pdata["zone"]
                event_outcomes.append(
                    f"{pdata['name']}'s {highest_stat} is reduced by {decay_amount} due to the arena's harshness."
                )
    
        eliminations = []
        hunters, looters, resters, feast_participants = [], [], [], []
        hunted = set()
    
        # Shrink zones after Day 15
        if day_counter % 3 == 2 and len(zones) > 1:
            zone_to_remove = random.choice(zones)
            zones.remove(zone_to_remove)
            event_outcomes.append(f"⚠️ The zone **{zone_to_remove['name']}** has collapsed and is no longer safe!")
            await self.shrink_zones(ctx,zone_to_remove)
    
            for pid, data in players.items():
                if not data.get("alive"):
                    continue
                if data["zone"] == zone_to_remove:
                    new_zone = random.choice(zones)
                    data["zone"] = new_zone
                    event_outcomes.append(f"{data['name']} was forced to flee to **{new_zone['name']}**!")
                    
    
        # Assign actions
        for player_id, player_data in players.items():
            if not player_data["alive"]:
                continue
    
            if player_data.get("action") is None:
                if config.get("feast_active"):
                    player_data["action"] = random.choices(
                        ["Feast", "Hunt", "Rest", "Loot"],
                        weights=[60, 20, 10, 10], k=1
                    )[0]
                else:
                    player_data["action"] = random.choices(
                        ["Hunt", "Rest", "Loot"],
                        weights=[
                            player_data["stats"]["Str"],
                            player_data["stats"]["Con"] + len(player_data["items"]) * 3,
                            player_data["stats"]["Wis"]
                        ],
                        k=1
                    )[0]
    
            action = player_data["action"]
            if action == "Hunt":
                hunters.append(player_id)
            elif action == "Rest":
                resters.append(player_id)
                used_item = None
                if player_data["items"]:
                    # Pop and apply the first item
                    stat, boost = player_data["items"].pop(0)
                    player_data["stats"][stat] += boost
                    effect = f"{player_data['name']} used an item to get the following boost **+{boost} {stat}**!"
                    zone_name = player_data["zone"]["name"] if isinstance(player_data["zone"], dict) else player_data.get("zone", "Unknown Zone")
                    event_outcomes.append(f"{effect} ({zone_name})")
            
                else:
                    # No item used, apply default healing or rest message
                    if player_data["stats"]["HP"] < player_data["stats"]["Con"] * 2:
                        heal = random.randint(1, int(player_data["stats"]["Con"]))
                        player_data["stats"]["HP"] += heal
                        effect = await self.load_file("rest_heal.txt", name1=player_data["name"], dmg=heal)
                    else:
                        effect = await self.load_file("rest.txt", name1=player_data["name"])
                    
                    zone_name = player_data["zone"]["name"] if isinstance(player_data["zone"], dict) else player_data.get("zone", "Unknown Zone")
                    event_outcomes.append(f"{effect} ({zone_name})")

            elif action == "Loot":
                looters.append(player_id)
                if random.random() < 0.75:
                    stat = random.choice(["Def", "Str", "Con", "Wis"])
                    boost = random.randint(1, 10)
                    player_data["items"].append((stat, boost))
                    effect = await self.load_file(
                        f"loot_good_{stat}.txt",
                        name1=player_data['name'],
                        dmg=boost
                    )
                    zone_name = player_data["zone"]["name"] if isinstance(player_data["zone"], dict) else player_data.get("zone", "Unknown Zone")
                    event_outcomes.append(f"{effect} ({zone_name})")
                else:
                    threshold = 1 / (1 + player_data["stats"]["Wis"] / 10)
                    if random.random() < threshold:
                        damage = random.randint(1, 3)
                        player_data["stats"]["HP"] -= damage
                        effect = await self.load_file(
                            "loot_real_bad.txt",
                            name1=player_data['name'],
                            dmg=damage
                        )
                        zone_name = player_data["zone"]["name"] if isinstance(player_data["zone"], dict) else player_data.get("zone", "Unknown Zone")
                        event_outcomes.append(f"{effect} ({zone_name})")
                        if player_data["stats"]["HP"] <= 0:
                            player_data["alive"] = False
                            player_data["zone"] = {"name": "Cornucopia"}
                            event_outcomes.append(f"{player_data['name']} has been eliminated by their own foolishness! (Cornucopia)")
                    else:
                        effect = await self.load_file("loot_bad.txt", name1=player_data['name'])
                        zone_name = player_data["zone"]["name"] if isinstance(player_data["zone"], dict) else player_data.get("zone", "Unknown Zone")
                        event_outcomes.append(f"{effect} ({zone_name})")

            elif action == "Feast":
                feast_participants.append(player_id)
                players[player_id]["zone"] = {"name": "Cornucopia"}

        feasters = [pid for pid, p in players.items() if p.get("action") == "Feast" and p.get("alive")]
    
        if feasters:
    
            feast_log = ["🍖 The Feast begins at the Cornucopia..."]
        
            if len(feasters) == 1:
                solo = players[feasters[0]]
                for each in range(3):
                    stat = random.choice(["Str", "Con", "Def", "Wis"])
                    boost = random.randint(10, 15)
                    solo["stats"][stat] += boost
                    effect = f"🥇 {solo['name']} arrived alone and gained **+{boost} {stat}** from the untouched Cornucopia."
                event_outcomes.append(f"{effect} (Cornucopia)")
            else:
        
                alive_set = set(feasters)
            
                for round_num in range(3):
                    feast_log.append(f"\n💥 **Round {round_num} of the Feast Bloodbath!**")
                    targets = list(alive_set)
                    random.shuffle(targets)
            
                    for attacker_id in alive_set.copy():
                        if not players[attacker_id]["alive"]:
                            continue
            
                        valid_targets = [t for t in targets if t != attacker_id and players[t]["alive"]]
                        if not valid_targets:
                            continue
                        target_id = random.choice(valid_targets)
            
                        attacker = players[attacker_id]
                        target = players[target_id]
            
                        atk_score = (
                            attacker["stats"]["Str"] * 1.2 +
                            attacker["stats"]["Wis"] * 0.5 +
                            random.randint(1, 10)
                        )
                        def_score = (
                            target["stats"]["Def"] * 1.1 +
                            target["stats"]["Con"] * 0.5 +
                            random.randint(1, 10)
                        )
                        
                        if atk_score > def_score:
                            damage = max(1, int((atk_score - def_score) + random.randint(1, 20)))
                            target["stats"]["HP"] -= damage
                            effect = f"⚔️ {attacker['name']} slashed {target['name']} for **{damage} HP**!"
                            if target["stats"]["HP"] <= 0:
                                target["alive"] = False
                                attacker["kill_list"].append(target["name"])
                                effect += f" 💀 {target['name']} died!"
                                alive_set.discard(target_id)
                            event_outcomes.append(f"{effect} (Cornucopia)")
                        else:
                            effect = f"🛡️ {target['name']} deflected an attack from {attacker['name']}."
                            event_outcomes.append(f"{effect} (Cornucopia)")
            
                    # Traps!
                    for pid in list(alive_set):
                        if not players[pid]["alive"]:
                            continue
            
                        if random.random() < 0.25:
                            trap_damage = random.randint(5, 10)
                            players[pid]["stats"]["HP"] -= trap_damage
            
                            if players[pid]["stats"]["HP"] <= 0:
                                players[pid]["alive"] = False
                                effect = f"💀 {players[pid]['name']} triggered a deadly trap and died!"
                                alive_set.discard(pid)
                            else:
                                effect = f"⚠️ {players[pid]['name']} was injured by a trap and lost **{trap_damage} HP**!"
            
                            event_outcomes.append(f"{effect} (Cornucopia)")
        
            # Reward survivors
            if alive_set:
                for pid in alive_set:
                    player = players[pid]
                    for each in range(3):
                        stat = random.choice(["Str", "Con", "Def", "Wis", "HP"])
                        boost = random.randint(6, 12)
                        player["stats"][stat] += boost
                        effect = f"🌟 {player['name']} survived the Feast and gained **+{boost} {stat}**!"
                        event_outcomes.append(f"{effect} (Cornucopia)")

                
    
        # Zone-based hunting resolution
        for zone, zone_players in zone_groups.items():
            zone_hunters = [pid for pid in hunters if pid in zone_players]
            zone_targets = [pid for pid in zone_players if players[pid]["alive"] and pid not in hunters]
    
            random.shuffle(zone_hunters)
    
            for hunter_id in zone_hunters:
                if hunter_id in hunted:
                    continue
    
                hunter = players[hunter_id]
                potential_targets = [pid for pid in zone_players if pid != hunter_id and pid not in hunted and players[pid]["alive"]]
    
                if not potential_targets:
                    zone_name = hunter["zone"]["name"] if isinstance(hunter["zone"], dict) else hunter.get("zone", "Unknown Zone")
                    event_outcomes.append(f"{hunter['name']} hunted in **{zone}**, but found no one to challenge. ({zone_name})")
                    continue
    
                target_id = random.choice(potential_targets)
                target = players[target_id]
    
                hunter_str = hunter["stats"]["Str"] + hunter["stats"]["Wis"] + max(random.randint(1, 10), random.randint(1, 10))
                target_def = target["stats"]["Def"] + target["stats"]["Con"] + random.randint(1, 10)
                damage = hunter_str - target_def
    
                if damage > 0:
                    target["stats"]["HP"] -= damage
                    effect = await self.load_file(
                        "feast_attack.txt",
                        name1=hunter['name'],
                        name2=target['name'],
                        dmg=damage
                    )
                    zone_name = player_data["zone"]["name"] if isinstance(player_data["zone"], dict) else player_data.get("zone", "Unknown Zone")
                    event_outcomes.append(f"{effect} ({zone_name})")
    
                    if target["stats"]["HP"] <= 0:
                        target["alive"] = False
                        hunter["kill_list"].append(target["name"])
                        eliminations.append(target)
                        target["zone"] = {"name": "Cornucopia"}
                        zone_name = player_data["zone"]["name"] if isinstance(player_data["zone"], dict) else player_data.get("zone", "Unknown Zone")
                        event_outcomes.append(f"{target['name']} has been eliminated by {hunter['name']}! ({zone_name})")
                else:
                    backlash = abs(damage)
                    hunter["stats"]["HP"] -= backlash
                    effect = await self.load_file(
                        "tie_attack.txt",
                        name1=hunter['name'],
                        name2=target['name'],
                        dmg=0,
                        dmg2=backlash
                    )
                    zone_name = hunter["zone"]["name"] if isinstance(hunter["zone"], dict) else hunter.get("zone", "Unknown Zone")
                    event_outcomes.append(f"{effect} ({zone_name})")
                    
                    if hunter["stats"]["HP"] <= 0:
                        hunter["alive"] = False
                        target["kill_list"].append(hunter["name"])
                        eliminations.append(hunter)
                        hunter["zone"] = {"name": "Cornucopia"}
                        zone_name = hunter["zone"]["name"] if isinstance(hunter["zone"], dict) else hunter.get("zone", "Unknown Zone")
                        event_outcomes.append(f"{hunter['name']} has been eliminated by {target['name']} ({zone_name})!")
    
                hunted.add(hunter_id)
                hunted.add(target_id)
    
        # Save zone & player data
        await self.config.guild(guild).players.set(players)
        await self.config.guild(guild).zones2.set(zones)
    
        # Track eliminations
        for player_id, player_data in players.items():
            if player_data["alive"] is False and "eliminated_on" not in player_data:
                player_data["eliminated_on"] = day_counter
                eliminations.append(player_data)
    
        await self.config.guild(guild).players.set(players)

        # Day report
        if event_outcomes:
            zone_sorted_events = {}
        
            for line in event_outcomes:
                zone_name = "Announcements"  # fallback zone if none is tagged
                if line.endswith(")"):
                    parts = line.rsplit("(", 1)
                    line = parts[0].strip()
                    zone_name = parts[1].strip(")")
                zone_sorted_events.setdefault(zone_name, []).append(line)

            file = "Hunger_Games.txt"
            # Sort so Announcements is always last
            async with aiofiles.open(file, mode="a") as f:                    
                for zone_name in sorted(zone_sorted_events.keys(), key=lambda z: (z == "Announcements", z)):
                    await ctx.send(f"# __**Zone Report: {zone_name}**__")
                    await f.write(f"Zone Report: {zone_name}\n")

            
                    for event in zone_sorted_events[zone_name]:
                        if zone_name == "Distortion Field":
                            event_words = event.split()
                            random.shuffle(event_words)
                            event = ' '.join(event_words)
            
                        await ctx.send(event)
                        await f.write(event)

        else:
            await ctx.send("The day passed quietly.")

    
        # Save leaderboard
        if eliminations:
            leaderboard = config.get("elimination_leaderboard", [])
            for eliminated_player in eliminations:
                leaderboard.append({
                    "name": eliminated_player["name"],
                    "day": eliminated_player["eliminated_on"]
                })
            await self.config.guild(guild).elimination_leaderboard.set(leaderboard)
            
        # Process daily bet earnings
        players = await self.config.guild(guild).players()
        all_users = await self.config.all_users()
            
        for user_id, user_data in all_users.items():
            bets = user_data.get("bets", {})
            user_gold = await self.config_gold.user_from_id(user_id).master_balance()
    
            day_counter = config.get("day_counter", 0)
    
            for tribute_id, bet_data in bets.items():
                if tribute_id in players and players[tribute_id]["alive"]:
                        
                    daily_return = max(int(bet_data["amount"] * min(0.01 * day_counter/4, 0.20)),1)  
                    bet_data["daily_earnings"] += daily_return
                    user_gold += daily_return
            
            await self.config_gold.user_from_id(user_id).master_balance.set(user_gold)
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
    async def check_wellcoins(self, ctx):
        """Check your current wellcoins."""
        user_gold = await self.config_gold.user(ctx.author).master_balance()
        await ctx.send(f"{ctx.author.mention}, you currently have {user_gold} Wellcoins.")

    @hunger.command()
    async def leaderboard(self, ctx):
        """Display leaderboards for total kills and Wellcoins."""
        all_users = await self.config.all_users()
        guild_config = await self.config.guild(ctx.guild).all()
        
        # Gather and sort kill counts
        kill_leaderboard = sorted(
            all_users.items(),
            key=lambda x: x[1].get("kill_count", 0),
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

        
        await ctx.send(embed=embed)

        WLboard = guild_config.get("WLboard", [])
    
    @hunger.command()
    @commands.admin()
    async def reset_leaderboard(self, ctx):
        """Reset all user kill counts and Wellcoins."""
        all_users = await self.config.all_users()
        for user_id in all_users:
            await self.config.user_from_id(int(user_id)).kill_count.set(0)
            #await self.config.user_from_id(int(user_id)).gold.set(0)
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
                "You'll be assigned to a random district and given stats like Strength, Defense, Wisdom, Constitution, and HP. Your family is also sent 100 Wellcoins pre-bereavement gift."
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
                "Check your kills `!hunger leaderboard`. Compete for top spots in kills on the leaderboards!"
            ),
            inline=False
        )
        embed.add_field(
            name="7. Sponsoring",
            value=(
                "If you just fall in love with one of the tributes you can spend Wellcoins to help them out, use the sponsor button on any day to send a gift into the arena."
            ),
            inline=False
        )
        embed.set_footer(text="Good luck, and may the odds be ever in your favor!")
        
        await ctx.send(embed=embed)
    
    @hunger.command(name="view_signups")
    async def view_signups(self, ctx):
        """View the current list of players signed up for the Hunger Games."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()

        if not players:
            await ctx.send("No players have signed up for the Hunger Games yet.")
            return

        # Sort players by district number
        sorted_players = sorted(players.items(), key=lambda x: x[1].get("district", 0))
        total_players = len(sorted_players)
        total_pages = math.ceil(total_players / 10)

        async def create_embed(page):
            embed = discord.Embed(
                title="Current Hunger Games Signups",
                description=f"Page {page + 1}/{total_pages} - Showing up to 10 players",
                color=discord.Color.blue()
            )
            for player_id, player_data in sorted_players[page * 10:(page + 1) * 10]:
                name = player_data.get("name", "Unknown")
                district = player_data.get("district", "?")
                status = "Alive" if player_data.get("alive", False) else "Eliminated"
                embed.add_field(
                    name=f"{name} (District {district})",
                    value=f"Status: {status}",
                    inline=False
                )
            embed.set_footer(text=f"Total Players: {total_players}")
            return embed

        class Paginator(View):
            def __init__(self):
                super().__init__()
                self.page = 0

            @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
            async def previous(self, interaction: discord.Interaction, button: Button):
                if self.page > 0:
                    self.page -= 1
                    embed = await create_embed(self.page)
                    await interaction.response.edit_message(embed=embed, view=self)
                else:
                    await interaction.response.defer()

            @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
            async def next(self, interaction: discord.Interaction, button: Button):
                if self.page < total_pages - 1:
                    self.page += 1
                    embed = await create_embed(self.page)
                    await interaction.response.edit_message(embed=embed, view=self)
                else:
                    await interaction.response.defer()

        embed = await create_embed(0)
        await ctx.send(embed=embed, view=Paginator())


    
    @hunger.command()
    @is_gamemaster()
    async def clear_signups(self, ctx):
        """Clear all signups and reset the player list (Admin only)."""
        guild = ctx.guild
        await self.config.guild(guild).players.clear()
        await ctx.send("All signups have been cleared. The player list has been reset.")

    @hunger.command()
    async def chknum(self, ctx):
        WLboard = await self.config.guild(ctx.guild).WLboard()
        # If each game has one winner:
        games_ran = sum(data.get("wins", 0) for data in WLboard.values())
        await ctx.send(f"🧮 Estimated number of Hunger Games run before tracking: **{games_ran}**")

    
    @app_commands.command(name="sponsor", description="Sponsor a tribute with a random stat boost.")
    @app_commands.describe(tribute="Select a tribute to sponsor")
    async def sponsor(self, interaction: Interaction, tribute: str):
        try:
            guild = interaction.guild
            user = interaction.user
            config = await self.config.guild(guild).all()
            players = config["players"]
            day = config["day_counter"]
    
            # Cost increases as days go on
            # Cost increases with tribute power instead of days
            stats = players[tribute]["stats"]
            score = (
                stats["Def"]
                + stats["Str"]
                + stats["Con"]
                + stats["Wis"]
                + (stats["HP"] / 5)
            )
            cost = round(10 + (day * 5) + score/2)

            user_gold = await self.config_gold.user(user).master_balance()
    
            if tribute not in players or not players[tribute]["alive"]:
                await interaction.response.send_message("❌ That tribute doesn't exist or is no longer alive.", ephemeral=True)
                return
    
            if user_gold < cost:
                await interaction.response.send_message(f"❌ You need at least {cost} Wellcoins to sponsor someone. Your balance: {user_gold}", ephemeral=True)
                return
    
            # Deduct cost
            await self.config_gold.user(user).master_balance.set(user_gold - cost)
    
            # Apply random stat boost
            tribute_data = players[tribute]
            stat = random.choice(["Def", "Str", "Con", "Wis", "HP"])
            boost = random.randint(1, 10)
            tribute_data["stats"][stat] += boost
    
            await self.config.guild(guild).players.set(players)
    
            await interaction.response.send_message(
                f"🎁 **{user.display_name}** sponsored **{tribute_data['name']}** with **+{boost} {stat}** for **{cost} Wellcoins!**",
                ephemeral=False
            )
    
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error in `/sponsor`: `{type(e).__name__}: {e}`", ephemeral=True)
            raise e  # Re-raise so it still shows in the bot's console/logs


    @sponsor.autocomplete("tribute")
    async def sponsor_autocomplete(self, interaction: Interaction, current: str):
        guild = interaction.guild
        players = await self.config.guild(guild).players()
        day = await self.config.guild(guild).day_counter()
    
        options = []
    
        for pid, pdata in players.items():
            if not pdata.get("alive"):
                continue
    
            member = guild.get_member(int(pid)) if pid.isdigit() else None
            display_name = member.display_name if member else pdata["name"]
    
            # Moved inside the loop — calculate individual tribute's score and cost
            stats = pdata["stats"]
            score = (
                stats["Def"] + stats["Str"] + stats["Con"] + stats["Wis"] + (stats["HP"] / 5)
            )
            cost = round(10 + (day * 5) + score/2)
    
            label = f"{display_name} (Cost: {cost}💰)"
    
            if current.lower() in display_name.lower():
                options.append(app_commands.Choice(name=label[:100], value=pid))  # Discord max = 100 chars
    
        return options[:25]

    
    async def shrink_zones(self, guild2, zone_to_pop=None):
        zones = await self.config.guild(guild2.guild).zones2()
    
        if len(zones) <= 1:
            return zones  # Nothing to shrink if only one or fewer zones
    
        if zone_to_pop and zone_to_pop in zones:
            zones.remove(zone_to_pop)
        else:
            zones.pop(random.randint(0, len(zones) - 1))
    
        await self.config.guild(guild2.guild).zones2.set(zones)
        return zones







    

    




    

