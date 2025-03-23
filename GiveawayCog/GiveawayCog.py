import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import random
from discord.ext import tasks


class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9006)
        self.config.register_guild(giveaway_channel=None)
        self.giveaway_tasks = {}

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setgiveawaychannel2(self, ctx, channel: discord.TextChannel):
        """Set the channel where giveaways will be posted."""
        await self.config.guild(ctx.guild).giveaway_channel.set(channel.id)
        await ctx.send(f"Giveaway channel set to {channel.mention}.")

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def startgiveaway2(self, ctx, length_in_days: int, card_link: str, role: discord.Role = None):
        """Start a giveaway with a card link, duration in days, and optional role restriction."""
        channel_id = await self.config.guild(ctx.guild).giveaway_channel()
        if not channel_id:
            return await ctx.send("Giveaway channel is not set. Use `setgiveawaychannel` first.")

        card_id, season = self.parse_card_link(card_link)
        if not card_id or not season:
            return await ctx.send("Invalid card link format.")

        card_data = await self.fetch_card_info(card_id, season)
        if not card_data:
            return await ctx.send("Failed to fetch card info from NationStates API.")

        end_time = datetime.utcnow() - timedelta(hours=5) + timedelta(minutes=length_in_days) 
        channel = ctx.guild.get_channel(channel_id)
        role_id = role.id if role else None
        view = GiveawayButtonView(role_id, card_data, card_link, role, end_time)
        message = await channel.send(embed=view.create_embed(), view=view)
        view.message = message

        self.giveaway_tasks[message.id] = self.bot.loop.create_task(self.end_giveaway(message, view, end_time))

    def parse_card_link(self, link):
        try:
            parts = link.split("card=")[1].split("/")
            card_id = parts[0]
            season = parts[1].replace("season=", "")
            return card_id, season
        except (IndexError, ValueError):
            return None, None

    async def fetch_card_info(self, card_id, season):
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={card_id};season={season}"
        headers = {"User-Agent": "9007"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                data = await response.text()
                root = ET.fromstring(data)
                return {
                    "cardid": root.findtext("CARDID"),
                    "name": root.findtext("NAME"),
                    "season": root.findtext("SEASON"),
                    "category": root.findtext("CATEGORY"),
                    "flag": root.findtext("FLAG"),
                    "market_value": root.findtext("MARKET_VALUE")
                }

    async def end_giveaway(self, message, view, end_time):
        await discord.utils.sleep_until(end_time)
        await view.disable_all_items()
        await message.edit(view=view)
        entrants = view.get_entrants()
        if entrants:
            winner = random.choice(entrants)
            await message.reply(f"Giveaway ended! Congratulations {winner.mention}, you won the card giveaway! Please let the Host know where you want your card sent!")
        else:
            await message.reply("Giveaway ended! No entrants.")

class GiveawayButtonView(discord.ui.View):
    def __init__(self, role_id, card_data, card_link, role, end_time):
        super().__init__(timeout=None)
        self.entrants = set()
        self.role_id = role_id
        self.card_data = card_data
        self.card_link = card_link
        self.role = role
        self.end_time = end_time
        self.message = None

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.role_id and self.role_id not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You do not have the required role to enter this giveaway.", ephemeral=True)
            return
        self.entrants.add(interaction.user)
        await interaction.response.send_message("You have entered the giveaway!", ephemeral=True)

        # Update the embed with the new entrant count
        if self.message:
            await self.message.edit(embed=self.create_embed(), view=self)

    def get_entrants(self):
        return list(self.entrants)

    async def disable_all_items(self):
        for item in self.children:
            item.disabled = True
        self.stop()

    def create_embed(self):
        embed = discord.Embed(
            title=f"Giveaway: {self.card_data['name']} ({self.card_data['category'].title()})",
            description=f"A {self.card_data['category'].title()} card is up for grabs!",
            url=self.card_link,
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=f"https://www.nationstates.net/images/flags/{self.card_data['flag']}")
        embed.add_field(name="Market Value", value=f"{self.card_data['market_value']}", inline=True)
        eligible_role = self.role.mention if self.role else "Everyone"
        embed.add_field(name="Eligible Role", value=eligible_role, inline=True)
        embed.add_field(name="Ends", value=f"<t:{int(self.end_time.timestamp())}:R>", inline=False)
        embed.add_field(name="Entrants", value=str(len(self.entrants)), inline=False)
        embed.set_footer(text="Click the button below to enter!")
        return embed
