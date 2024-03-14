from redbot.core import commands, Config
import xml.etree.ElementTree as ET
from discord import ButtonStyle
from discord.ui import View, Button
import asyncio
import aiohttp
from datetime import datetime

class ApproveButton(Button):
    def __init__(self, label: str, custom_id: str, cog_instance, ctx):
        super().__init__(style=ButtonStyle.success, label=label, custom_id=custom_id)
        self.cog_instance = cog_instance
        self.ctx = ctx

    async def callback(self, interaction):
        await interaction.response.defer()
        user_settings = await self.cog_instance.config.user(self.ctx.author).all()
        view = View()
        success = await self.cog_instance.run_cycle(self.ctx, user_settings, view)
        if success:
            await interaction.followup.send("New cycle started!", ephemeral=True)
        else:
            await interaction.followup.send("Failed to start a new cycle.", ephemeral=True)

class DoneButton(Button):
    def __init__(self, label: str, custom_id: str, cog_instance):
        super().__init__(style=ButtonStyle.danger, label=label, custom_id=custom_id)
        self.cog_instance = cog_instance

    async def callback(self, interaction):
        self.cog_instance.loop_running = False
        await interaction.response.send_message("Loop stopped, done for now.", ephemeral=True)

class Recruitomatic9003(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_user_settings = {
            "template": None,
            "excluded_regions": ["the_wellspring"],
            "user_agent": "YourUserAgentHere"
        }
        self.config.register_user(**default_user_settings)
        self.loop_running = False

    async def fetch_nation_details(self, user_agent):
        async with aiohttp.ClientSession() as session:
            headers = {'User-Agent': user_agent}
            async with session.get("https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails", headers=headers) as response:
                if response.status == 200:
                    return await response.text()

    async def run_cycle(self, ctx, user_settings, view):
        excluded_regions = user_settings['excluded_regions']
        user_agent = user_settings['user_agent']
        template = user_settings['template'] if user_settings['template'] else "%%TEMPLATE-XXXXXX%%"

        data = await self.fetch_nation_details(user_agent)
        if data is None:
            await ctx.send("Failed to fetch nation details.")
            return False

        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            await ctx.send(f"Error parsing XML: {e}")
            return False

        nations = []
        for new_nation in root.findall('./NEWNATIONDETAILS/NEWNATION'):
            region = new_nation.find('REGION').text
            if region not in excluded_regions:
                nations.append(new_nation.get('name'))

        grouped_nations = [nations[i:i + 8] for i in range(0, len(nations), 8)]
        if not grouped_nations:
            await ctx.send("No nations found or all nations are in excluded regions.")
            return True

        view.clear_items()
        for i, group in enumerate(grouped_nations, start=1):
            nations_str = ",".join(group)
            url = f"https://www.nationstates.net/page=compose_telegram?tgto={nations_str}&message={template}"
            view.add_item(Button(style=ButtonStyle.url, label=f"Batch {i}", url=url))

        view.add_item(ApproveButton("Approve", "approve", self, ctx))
        view.add_item(DoneButton("All Done", "done", self))

        await ctx.send("Click on the buttons below or wait for the next cycle:", view=view)
        return True

    @commands.command()
    async def recruit(self, ctx, timer: int):
        if self.loop_running:
            await ctx.send("A recruitment loop is already running.")
            return

        self.loop_running = True
        timer = max(40, timer * 60)
        cycles = 0
        start_time = datetime.utcnow()

        user_settings = await self.config.user(ctx.author).all()
        view = View()
        while self.loop_running and cycles < 10 and (datetime.utcnow() - start_time).total_seconds() < 600:
            success = await self.run_cycle(ctx, user_settings, view)
            if not success:
                break

            await asyncio.sleep(timer)
            cycles += 1

        self.loop_running = False

