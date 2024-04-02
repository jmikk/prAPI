import aiohttp
import xml.etree.ElementTree as ET
from redbot.core import commands
import discord
import asyncio
from datetime import datetime, timedelta


EXCLUDED_REGIONS = {"excluded_region1", "excluded_region2"}  # Update with your excluded regions

class Recruitomatic9006(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_channel = None
        self.embed_send_task = None
        self.last_interaction = discord.utils.utcnow()  # Track the last interaction

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
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        text = await response.text()    
                        return ET.fromstring(text)
                        #return text
    
                    else:
                        print(f"Failed to fetch data: {response.status}")
                        return response.status
        except Exception as e:
            await self.target_channel.send(e)

    async def parse_nations(self, xml_data):
        """Parses nation details from XML, filtering out excluded regions."""
        nations = []
        await self.target_channel.send("xml_data")

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
        
        self.last_interaction = datetime.utcnow()

        while True:
            if datetime.utcnow() - self.last_interaction > timedelta(minutes=10):
                await self.target_channel.send("No interactions for 10 minutes. Stopping the recruitment messages.")
                self.embed_send_task.cancel()
                break
            
            await self.target_channel.send("fetch_nation_data")
            xml_data = await self.fetch_nation_data()
            
            if xml_data:
                await self.target_channel.send("parse_nations")
                nations = self.parse_nations(xml_data)
                await self.target_channel.send("generate_telegram_urls")
                telegram_urls = self.generate_telegram_urls(nations)
              
                await self.target_channel.send("build emebed")
                embed = discord.Embed(title="Recruit Message", description="Recruitment Telegrams:", color=0x00ff00)
                view = discord.ui.View()
                
                await self.target_channel.send("add buttons")
                for url in telegram_urls:
                    view.add_item(discord.ui.Button(label="Recruitment Telegram", url=url, style=discord.ButtonStyle.url))

                view.add_item(discord.ui.Button(label="Done", style=discord.ButtonStyle.danger, custom_id="done_button"))
                view.add_item(discord.ui.Button(label="Reset Timer", style=discord.ButtonStyle.primary, custom_id="reset_timer_button"))

                await self.target_channel.send("Hello")

                
                if self.target_channel:
                    await self.target_channel.send("sending emebed")

                    await self.target_channel.send(embed=embed, view=view)

            else:
                await self.target_channel.send("Failed to fetch nation data.")

            await asyncio.sleep(interval_minutes * 60)  # Wait for the specified interval before repeating

    @discord.ui.button(custom_id="done_button", style=discord.ButtonStyle.danger, label="Done")
    async def done_button_callback(self, button, interaction):
        if self.embed_send_task:
            self.embed_send_task.cancel()
            await interaction.response.send_message("Recruitment messages stopped.", ephemeral=True)

    @discord.ui.button(custom_id="reset_timer_button", style=discord.ButtonStyle.primary, label="Reset Timer")
    async def reset_timer_button_callback(self, button, interaction):
        self.last_interaction = discord.utils.utcnow()
        await interaction.response.send_message("Timer reset. Waiting for the next interaction or timeout.", ephemeral=True)

    @commands.command()
    async def stoprecruitment(self, ctx):
        """Immediately stops the recruitment loop."""
        if self.embed_send_task and not self.embed_send_task.cancelled():
            self.embed_send_task.cancel()  # Cancel the running task
            self.embed_send_task = None  # Reset the task to None
            await ctx.send("Recruitment loop has been stopped.")
        else:
            await ctx.send("Recruitment loop is not currently running.")
