import discord
from discord.ext import commands, tasks
import aiohttp
import xml.etree.ElementTree as ET
import json
import os
from datetime import datetime
from redbot.core import commands


class DailyNationTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q=nations"
        self.data_file = "nation_data.json"
        self.template_file = "template_data.json"
        self.channel_id = 1343661925694705775  # Change to your channel ID
        self.load_data()
        self.load_templates()
        self.daily_task.start()

    def cog_unload(self):
        self.daily_task.cancel()

    def load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, "r") as f:
                self.nation_data = json.load(f)
        else:
            self.nation_data = {}

    def save_data(self):
        with open(self.data_file, "w") as f:
            json.dump(self.nation_data, f, indent=4)

    def load_templates(self):
        if os.path.exists(self.template_file):
            with open(self.template_file, "r") as f:
                self.templates = json.load(f)
        else:
            self.templates = {}  # {"1": "%25TEMPLATE-XXXXX%25", "5": "%25TEMPLATE-XXXXX%25"}

    def save_templates(self):
        with open(self.template_file, "w") as f:
            json.dump(self.templates, f, indent=4)

    @tasks.loop(hours=24)
    async def daily_task(self):
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            await channel.send("Started daily loop")
        await self.bot.wait_until_ready()
        new_nations = await self.get_nations()
        today = datetime.utcnow().strftime("%Y-%m-%d")

        for nation in new_nations:
            if nation not in self.nation_data:
                self.nation_data[nation] = {"first_seen": today, "days": 1}
            else:
                self.nation_data[nation]["days"] += 1

        # Remove nations no longer in the region
        for nation in list(self.nation_data.keys()):
            if nation not in new_nations:
                del self.nation_data[nation]

        self.save_data()

        for day_str, template in self.templates.items():
            try:
                day_threshold = int(day_str)
                await self.send_tg_links(day_threshold, template)
            except ValueError:
                continue
        if channel:
            await channel.send("Ended daily loop")

    async def get_nations(self):
        headers = {"User-Agent": "9005"}  # Preset header
        async with aiohttp.ClientSession() as session:
            async with session.get(self.api_url, headers=headers) as resp:
                if resp.status != 200:
                    print("Failed to fetch data")
                    return []
                text = await resp.text()
                root = ET.fromstring(text)
                nations_str = root.find("NATIONS").text
                return nations_str.split(":")

    async def send_tg_links(self, threshold, template_id):
        nations_to_tg = [n for n, d in self.nation_data.items() if d["days"] == threshold]

        if not nations_to_tg:
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return

        nation_chunks = [nations_to_tg[i:i+8] for i in range(0, len(nations_to_tg), 8)]

        buttons = []
        for i, chunk in enumerate(nation_chunks[:20]):
            tg_link = f"https://www.nationstates.net/page=compose_telegram?tgto={','.join(chunk)}&message={template_id}&generated_by=TW_daily_TGs__by_9005____instance_run_by_9005"
            buttons.append(discord.ui.Button(label=f"TG Set {i+1}", url=tg_link, style=discord.ButtonStyle.link))

        view = discord.ui.View()
        for button in buttons:
            view.add_item(button)

        embed = discord.Embed(title="Daily TG Links", description=f"Nations in region for {threshold} days.", color=discord.Color.blue())
        embed.set_footer(text=f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

        await channel.send(embed=embed, view=view)

    @commands.command()
    async def settemplate(self, ctx, day: int, template_id: str):
        """Set the TG template ID for a specific day (format: %TEMPLATE-XXXXX%)."""
        if not (template_id.startswith("%TEMPLATE-") and template_id.endswith("%")):
            await ctx.send("Invalid template format. Please use the format: %TEMPLATE-XXXXX%")
            return
        encoded_template = template_id.replace("%", "%25")
        self.templates[str(day)] = encoded_template
        self.save_templates()
        await ctx.send(f"Template for day {day} set to {encoded_template}")

    @commands.command()
    async def removetemplate(self, ctx, day: int):
        """Remove the TG template for a specific day."""
        if str(day) in self.templates:
            del self.templates[str(day)]
            self.save_templates()
            await ctx.send(f"Template for day {day} removed.")
        else:
            await ctx.send(f"No template found for day {day}.")

    @commands.command()
    async def listtemplates(self, ctx):
        """List all TG templates set for each day."""
        if not self.templates:
            await ctx.send("No templates set.")
        else:
            msg = "\n".join([f"Day {day}: {template}" for day, template in sorted(self.templates.items(), key=lambda x: int(x[0]))])
            await ctx.send(f"Current TG templates:\n{msg}")

    @commands.command()
    async def resetnationdata(self, ctx):
        """Reset all nation data to start fresh."""
        self.nation_data = {}
        self.save_data()
        await ctx.send("All nation data has been reset to 0.")

async def setup(bot):
    await bot.add_cog(DailyNationTracker(bot))
