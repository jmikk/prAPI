import aiohttp  # Ensure aiohttp is installed in your environment
import xml.etree.ElementTree as ET
from redbot.core import commands
import discord
import asyncio

EXCLUDED_REGIONS = {"excluded_region1", "excluded_region2"}  # Update with your excluded regions

class Recruitomatic9006(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_channel = None
        self.embed_send_task = None

    def cog_unload(self):
        if self.embed_send_task:
            self.embed_send_task.cancel()

    @commands.command(name="recruit2")
    async def recruit2(self, ctx, minutes: int):
        """Starts sending the recruit embed in the current channel every X minutes."""
        if self.embed_send_task:
            self.embed_send_task.cancel()

        self.target_channel = ctx.channel
        self.embed_send_task = asyncio.create_task(self.send_embed_periodically(minutes))

        await ctx.send(f"Will send recruit embed every {minutes} minutes in this channel.")

    async def fetch_nation_data(self):
        """Fetches new nation details from the NationStates API."""
        url = "https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails"
        headers = {"User-Agent": "Recruitomatic9006, written by 9003, nswa9002@gmail.com (discord: 9003) V 2"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    text = await response.text()
                    return ET.fromstring(text)
                else:
                    print(f"Failed to fetch data: {response.status}")
                    return None

    def parse_nations(self, xml_data):
        """Parses nation details from XML, filtering out excluded regions."""
        nations = []
        for newnation in xml_data.findall(".//NEWNATION"):
            region = newnation.find("REGION").text
            if region not in EXCLUDED_REGIONS:
                nations.append(newnation.get("name"))
        return nations

    def generate_telegram_urls(self, nations):
        """Generates URLs for sending telegrams to nations, in chunks of 8."""
        urls = []
        base_url = "https://www.nationstates.net/page=compose_telegram?tgto="
        template = "&message=%25TEMPLATE-29841116%25"

        for i in range(0, len(nations), 8):
            nation_chunk = nations[i:i+8]
            urls.append(base_url + ",".join(nation_chunk) + template)

        return urls

    async def send_embed_periodically(self, interval_minutes):
        """Sends an embed with recruitment telegram URLs periodically."""
        while True:
            xml_data = await self.fetch_nation_data()
            if xml_data:
                nations = self.parse_nations(xml_data)
                telegram_urls = self.generate_telegram_urls(nations)

                embed = discord.Embed(title="Recruit Message", description="Choose an option:", color=0x00ff00)
                for url in telegram_urls:
                    embed.add_field(name="Recruitment Telegram", value=f"[Send Telegram]({url})", inline=False)

                if self.target_channel:
                    await self.target_channel.send(embed=embed)
            else:
                await self.target_channel.send("Failed to fetch nation data.")

            await asyncio.sleep(interval_minutes * 60)  # Wait for the specified interval before repeating
