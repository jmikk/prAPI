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
            #await channel.send("Started daily loop")
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
            await channel.send("Daily loop done!")

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

    @commands.has_role(1113108765315715092)
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
    
    @commands.has_role(1113108765315715092)
    @commands.command()
    async def removetemplate(self, ctx, day: int):
        """Remove the TG template for a specific day."""
        if str(day) in self.templates:
            del self.templates[str(day)]
            self.save_templates()
            await ctx.send(f"Template for day {day} removed.")
        else:
            await ctx.send(f"No template found for day {day}.")

    @commands.has_role(1113108765315715092)
    @commands.command()
    async def listtemplates(self, ctx):
        """List all TG templates set for each day."""
        if not self.templates:
            await ctx.send("No templates set.")
        else:
            msg = "\n".join([f"Day {day}: {template}" for day, template in sorted(self.templates.items(), key=lambda x: int(x[0]))])
            await ctx.send(f"Current TG templates:\n{msg}")

    @commands.has_role(1113108765315715092)
    @commands.command()
    async def resetnationdata(self, ctx):
        """Reset all nation data to start fresh."""
        self.nation_data = {}
        self.save_data()
        await ctx.send("All nation data has been reset to 0.")


    @commands.has_role(1113108765315715092)
    @commands.command()
    async def sendonetg(self, ctx, day: int, template_id: str, *, mode: str = 'exact'):
        """Send a one-off TG link to nations that are exactly or at least X days in the region.
        Usage: !sendonetg <day> <TEMPLATE-XXXXX> [exact/atleast]
        """
        if not (template_id.startswith("%TEMPLATE-") and template_id.endswith("%")):
            await ctx.send("Invalid template format. Please use: %TEMPLATE-XXXXX%")
            return
    
        encoded_template = template_id.replace("%", "%25")
        if mode.lower() == 'atleast':
            nations_to_tg = [n for n, d in self.nation_data.items() if d["days"] >= day]
        else:
            nations_to_tg = [n for n, d in self.nation_data.items() if d["days"] == day]
    
        if not nations_to_tg:
            await ctx.send("No nations match the criteria.")
            return
    
        nation_chunks = [nations_to_tg[i:i+8] for i in range(0, len(nations_to_tg), 8)]
        buttons = []
        for i, chunk in enumerate(nation_chunks[:20]):
            tg_link = f"https://www.nationstates.net/page=compose_telegram?tgto={','.join(chunk)}&message={encoded_template}&generated_by=TW_daily_TGs__by_9005____instance_run_by_9005"
            buttons.append(discord.ui.Button(label=f"One-Off TG {i+1}", url=tg_link, style=discord.ButtonStyle.link))
    
        view = discord.ui.View()
        for button in buttons:
            view.add_item(button)
    
        embed = discord.Embed(title="One-Off TG Links",
                              description=f"Nations {'at least' if mode.lower() == 'atleast' else 'exactly'} {day} days in region.",
                              color=discord.Color.green())
        embed.set_footer(text=f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
        await ctx.send(embed=embed, view=view)

    @commands.has_role(1113108765315715092)
    @commands.command()
    async def importcensusdays(self, ctx):
        """Import days from census rank scale 80. Uses rank score as days (rounded down)."""
        await ctx.send("Starting import of census data...")
        headers = {"User-Agent": "9005"}
        start = 1
        total_imported = 0

        async with aiohttp.ClientSession() as session:
            while True:
                url = f"https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q=censusranks;scale=80&start={start}"
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        await ctx.send(f"Failed to fetch census data at start={start}.")
                        break
                    text = await resp.text()
                    root = ET.fromstring(text)
                    nations = root.findall(".//NATION")

                    if not nations:
                        break

                    for nation in nations:
                        name = nation.find("NAME").text
                        score = float(nation.find("SCORE").text)
                        self.nation_data[name] = {"first_seen": "imported", "days": int(score)}
                        total_imported += 1

                    start += len(nations)

                    remaining = int(resp.headers.get("X-Ratelimit-Remaining", 100))
                    reset_time = int(resp.headers.get("X-Ratelimit-Reset", 10))
                    if remaining < 20:
                        await ctx.send(f"Sleeping for {reset_time} seconds due to rate limiting...")
                        await asyncio.sleep(reset_time)

        self.save_data()
        await ctx.send(f"Import complete. Total nations updated: {total_imported}.")


    @commands.command()
    async def viewnationdata(self, ctx):
        """View all nation data with pagination."""
        sorted_data = sorted(self.nation_data.items(), key=lambda x: (-x[1]['days'], x[0]))
        pages = [sorted_data[i:i+10] for i in range(0, len(sorted_data), 10)]

        if not pages:
            await ctx.send("No nation data available.")
            return

        class Paginator(discord.ui.View):
            def __init__(self, data_pages):
                super().__init__(timeout=60)
                self.data_pages = data_pages
                self.page = 0

            async def update_embed(self, interaction):
                embed = discord.Embed(title=f"Nation Data (Page {self.page + 1}/{len(self.data_pages)})", color=discord.Color.gold())
                for name, info in self.data_pages[self.page]:
                    link = f"https://www.nationstates.net/nation={name}"
                    embed.add_field(name=f"[{name}]({link})", value=f"Days: {info['days']}", inline=False)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
            async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.page = (self.page - 1) % len(self.data_pages)
                await self.update_embed(interaction)

            @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
            async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.page = (self.page + 1) % len(self.data_pages)
                await self.update_embed(interaction)

        view = Paginator(pages)
        embed = discord.Embed(title="Nation Data (Page 1/{})".format(len(pages)), color=discord.Color.gold())
        for name, info in pages[0]:
            link = f"https://www.nationstates.net/nation={name}"
            embed.add_field(name=f"[{name}]({link})", value=f"Days: {info['days']}", inline=False)

        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(DailyNationTracker(bot))
