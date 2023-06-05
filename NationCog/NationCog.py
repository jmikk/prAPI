from redbot.core import commands
import asyncio
import discord
import requests
import gspread
import xml.etree.ElementTree as ET


class NationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTPWrErSHEy9kZVwcT7NK_gVJsBdytg2yNnKgXgFbs_Cxe2VFj2wUbBCgsER6Uik5ewWaJMj2UrlIFz/pub?gid=0&single=true&output=csv"
        self.api_url = "https://www.nationstates.net/cgi-bin/api.cgi?region=The_wellspring&q=nations"
        self.user_agent = "9003"
        self.target_channel_id = None  # Store the target channel ID here

    @commands.command()
    async def set_channel(self, ctx, channel: discord.TextChannel):
        self.target_channel_id = channel.id
        await ctx.send(f"Target channel set to {channel.mention}")

    @commands.command()
    async def check_nations(self, ctx):
        await ctx.send("Starting")
        await ctx.send("Load data from the Google Sheets CSV")
        data = self.load_spreadsheet_data()
        if data is None:
            await ctx.send("Failed to load spreadsheet data.")
            return

        await ctx.send("Fetch the nations from the NationStates API")
        api_nations = self.fetch_api_nations()
        if api_nations is None:
            await ctx.send("Failed to fetch nations from the API.")
            return

        await ctx.send("Compare the nations and send messages for missing ones")
        missing_nations = self.compare_nations(data, api_nations)
        if not missing_nations:
            await ctx.send("No missing nations found.")
            return

        for nation in missing_nations:
            discord_name = nation["Discord"]
            wellspring_name = nation["wellspring_name"]
            message = f"Nation not found in API: Discord Name: {discord_name}, Wellspring Name: {wellspring_name}"
            target_channel = self.bot.get_channel(self.target_channel_id)
            await target_channel.send(message)

    def load_spreadsheet_data(self):
        try:
            response = requests.get(self.sheet_url)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return None

    def fetch_api_nations(self):
        try:
            response = requests.get(
                self.api_url, headers={"User-Agent": self.user_agent}
            )
            response.raise_for_status()
            xml_data = ET.fromstring(response.text)
            nation_elements = xml_data.findall(".//NATIONS")
            return [nation.text for nation in nation_elements[0]]
        except (requests.RequestException, ET.ParseError):
            return None

    def compare_nations(self, data, api_nations):
        # Parse the spreadsheet data and extract the nations
        lines = data.split("\n")
        header = lines[0].split("\t")
        nations = []
        for line in lines[1:]:
            if line.strip() != "":
                values = line.split("\t")
                nation = dict(zip(header, values))
                nations.append(nation)

        # Compare the nations and find missing ones
        missing_nations = []
        for nation in nations:
            discord_name = nation.get("Discord")
            wellspring_name = nation.get("The Wellspring Nation")
            if discord_name and wellspring_name and wellspring_name not in api_nations:
                missing_nations.append({
                    "discord_name": discord_name,
                    "wellspring_name": wellspring_name
                })

        return missing_nations

