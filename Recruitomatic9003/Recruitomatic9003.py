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
        # Logic to approve, perhaps update some status or data
        await interaction.response.send_message("Approved!", ephemeral=True)
        # Here you could also trigger the next cycle manually if needed

class DoneButton(Button):
    def __init__(self, label: str, custom_id: str, cog_instance):
        super().__init__(style=ButtonStyle.danger, label=label, custom_id=custom_id)
        self.cog_instance = cog_instance

    async def callback(self, interaction):
        self.cog_instance.loop_running = False  # Signal to stop the loop
        await interaction.response.send_message("Loop stopped, done for now.", ephemeral=True)

class Recruitomatic9003(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)  # Changed identifier to a number
        default_user_settings = {
            "template": None,
            "excluded_regions": ["the_wellspring"],
            "user_agent": "YourUserAgentHere"  # Ensure you have a default or prompt the user to set this
        }
        self.config.register_user(**default_user_settings)
        self.loop_running = False

    async def fetch_nation_details(self, user_agent):
        async with aiohttp.ClientSession() as session:
            headers = {'User-Agent': user_agent}
            async with session.get("https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails", headers=headers) as response:
                if response.status == 200:
                    return await response.text()

    @commands.command()
    async def recruit(self, ctx, timer: int):
        if self.loop_running:
            await ctx.send("A recruitment loop is already running.")
            return

        self.loop_running = True
        timer = max(40, timer * 60)  # Ensure timer is at least 40 seconds, and convert minutes to seconds

        cycles = 0
        start_time = datetime.utcnow()

        user_settings = await self.config.user(ctx.author).all()
        excluded_regions = user_settings['excluded_regions']
        user_agent = user_settings['user_agent']
        template = user_settings['template'] if user_settings['template'] else "%%TEMPLATE-XXXXXX%%"

        while self.loop_running and cycles < 10 and (datetime.utcnow() - start_time).total_seconds() < 600:
            data = await self.fetch_nation_details(user_agent)
            if data is None:
                await ctx.send("Failed to fetch nation details.")
                break

            try:
                root = ET.fromstring(data)
            except ET.ParseError as e:
                await ctx.send(f"Error parsing XML: {e}")
                break

            nations = []
            for new_nation in root.findall('./NEWNATIONDETAILS/NEWNATION'):
                region = new_nation.find('REGION').text
                if region not in excluded_regions:
                    nations.append(new_nation.get('name'))

            grouped_nations = [nations[i:i + 8] for i in range(0, len(nations), 8)]
            if not grouped_nations:
                await ctx.send("No nations found or all nations are in excluded regions.")
                continue  # Use continue to proceed to the next cycle instead of breaking the loop

            view = View()  # Define the view here
            for i, group in enumerate(grouped_nations, start=1):
                nations_str = ",".join(group)
                url = f"https://www.nationstates.net/page=compose_telegram?tgto={nations_str}&message={template}"
                view.add_item(Button(style=ButtonStyle.url, label=f"Batch {i}", url=url))

            view.add_item(ApproveButton("Approve", "approve", self, ctx))
            view.add_item(DoneButton("All Done", "done", self))

            await ctx.send("Click on the buttons below or wait for the next cycle:", view=view)

            await asyncio.sleep(timer)  # Wait for the specified timer duration before the next cycle
            cycles += 1

        self.loop_running = False  # Reset loop status after it ends
