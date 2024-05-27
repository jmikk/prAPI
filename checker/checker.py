import discord
from discord.ext import commands
import requests
import gzip
import xmltodict
import json
import os

APPROVED_NATIONS_FILE = "approved_nations.json"

class checker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_approved_nations()

    def load_approved_nations(self):
        if os.path.exists(APPROVED_NATIONS_FILE):
            with open(APPROVED_NATIONS_FILE, "r") as f:
                self.approved_nations = json.load(f)
        else:
            self.approved_nations = {}

    def save_approved_nations(self):
        with open(APPROVED_NATIONS_FILE, "w") as f:
            json.dump(self.approved_nations, f, indent=4)

    @commands.command()
    async def safety_check(self, ctx, region: str):
        await ctx.send("Starting safety check...")

        # Download and unzip the XML file with user agent header
        url = "https://www.nationstates.net/pages/nations.xml.gz"
        headers = {"User-Agent": "9006"}
        response = requests.get(url, headers=headers)
        xml_content = gzip.decompress(response.content)

        # Parse the XML
        data = xmltodict.parse(xml_content)

        # Find nations in the specified region
        nations_in_region = []
        for nation in data['NATIONS']['NATION']:
            if nation['REGION'].lower() == region.lower():
                nations_in_region.append(nation)

        # Check if any nations were found
        if not nations_in_region:
            await ctx.send(f"No nations found in region {region}.")
            return

        # Filter out approved nations if unchanged
        new_nations = []
        for nation in nations_in_region:
            nation_id = nation['NAME']
            if nation_id in self.approved_nations:
                if self.approved_nations[nation_id] == nation:
                    continue
            new_nations.append(nation)

        if not new_nations:
            await ctx.send(f"All nations in region {region} are already approved and unchanged.")
            return

        view = NationPaginator(ctx, new_nations, self)
        await ctx.send(embed=view.create_embed(new_nations[0]), view=view)

class NationPaginator(discord.ui.View):
    def __init__(self, ctx, nations, cog):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.nations = nations
        self.cog = cog
        self.index = 0

    def create_embed(self, nation):
        embed = discord.Embed(title=nation['FULLNAME'], description=nation['MOTTO'])
        embed.add_field(name="Type", value=nation['TYPE'])
        embed.add_field(name="UN Status", value=nation['UNSTATUS'])
        embed.add_field(name="Region", value=nation['REGION'])
        embed.add_field(name="Animal", value=nation['ANIMAL'])
        embed.add_field(name="Currency", value=nation['CURRENCY'])
        embed.add_field(name="Demonym", value=nation['DEMONYM'])
        embed.add_field(name="Demonym2", value=nation['DEMONYM2'])
        embed.add_field(name="Demonym2 Plural", value=nation['DEMONYM2PLURAL'])
        embed.add_field(name="Influence", value=nation['INFLUENCE'])
        embed.add_field(name="Leader", value=nation['LEADER'])
        embed.add_field(name="Capital", value=nation['CAPITAL'])
        embed.add_field(name="Religion", value=nation['RELIGION'])
        embed.add_field(name="Factbooks", value=nation['FACTBOOKS'])
        embed.add_field(name="Dispatches", value=nation['DISPATCHES'])
        embed.set_thumbnail(url=nation['FLAG'])
        embed.set_footer(text=f"Nation {self.index + 1} of {len(self.nations)}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.index > 0:
            self.index -= 1
            await interaction.response.edit_message(embed=self.create_embed(self.nations[self.index]), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.index < len(self.nations) - 1:
            self.index += 1
            await interaction.response.edit_message(embed=self.create_embed(self.nations[self.index]), view=self)

    @discord.ui.button(label="Report", style=discord.ButtonStyle.danger)
    async def report(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(f"Reported nation: {self.nations[self.index]['NAME']}", ephemeral=True)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, button: discord.ui.Button, interaction: discord.Interaction):
        nation_id = self.nations[self.index]['NAME']
        self.cog.approved_nations[nation_id] = self.nations[self.index]
        self.cog.save_approved_nations()
        await interaction.response.send_message(f"Approved nation: {self.nations[self.index]['NAME']}", ephemeral=True)
        # Move to the next nation or end if this is the last one
        if self.index < len(self.nations) - 1:
            self.index += 1
            await interaction.edit_original_response(embed=self.create_embed(self.nations[self.index]), view=self)
        else:
            await interaction.edit_original_response(content="No more nations to review.", embed=None, view=None)

def setup(bot):
    bot.add_cog(SafetyCheck(bot))
