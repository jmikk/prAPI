from redbot.core import commands, Config
import requests
import xml.etree.ElementTree as ET
from discord import ButtonStyle
from discord.ui import View
from discord.ui import Button
import asyncio



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
        self.config = Config.get_conf(self, identifier="Recruitomatic9003")
        default_user_settings = {
            "template": None,
            "excluded_regions": ["the_wellspring"],
            "user_agent": None
        }
        self.config.register_user(**default_user_settings)
        self.loop_running = False  # Add this to track if a loop is already running

    @commands.command()
    async def set_template(self, ctx, *, template: str):
        if template.startswith("%%") and template.endswith("%%"):
            await self.config.user(ctx.author).template.set(template)
            await ctx.send("Template set successfully.")
        else:
            await ctx.send("Template must start and end with '%%'.")

    @commands.command()
    async def set_excluded_regions(self, ctx, *, regions: str):
        regions_list = regions.split(", ")
        await self.config.user(ctx.author).excluded_regions.set(regions_list)
        await ctx.send("Excluded regions set successfully.")

    @commands.command()
    async def set_user_agent(self, ctx, *, user_agent: str):
        await self.config.user(ctx.author).user_agent.set(user_agent)
        await ctx.send("User-Agent set successfully.")

    @commands.command()
    async def slow_recruit(self, ctx):
        user_settings = await self.config.user(ctx.author).all()
        excluded_regions = user_settings['excluded_regions']
        user_agent = user_settings['user_agent']
        if not user_settings['template']:
            ctx.await("Go set a template with [p]template first")
            return
        template = user_settings['template'] 

        headers = {'User-Agent': user_agent}
        response = requests.get("https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails", headers=headers)
        data = ET.fromstring(response.content)

        nations = []
        for new_nation in data.find('NEWNATIONDETAILS').findall('NEWNATION'):
            region = new_nation.find('REGION').text
            if region not in excluded_regions:
                nations.append(new_nation.get('name'))

        grouped_nations = [nations[i:i + 8] for i in range(0, len(nations), 8)]
        if not grouped_nations:
            await ctx.send("No nations found or all nations are in excluded regions.")
            return

    @commands.command()
    async def recruit(self, ctx, timer:int):

        if self.loop_running:
            await ctx.send("A recruitment loop is already running.")
            return

        self.loop_running = True
        timer = max(40, timer * 60)  # Ensure timer is at least 40 seconds, and convert minutes to seconds

        cycles = 0
        start_time = ctx.message.created_at
        
        user_settings = await self.config.user(ctx.author).all()
        excluded_regions = user_settings['excluded_regions']
        user_agent = user_settings['user_agent']
        if not user_settings['template']:
            ctx.await("Go set a template with [p]template first")
            return
        template = user_settings['template'] 

        headers = {'User-Agent': user_agent}
        while self.loop_running and cycles < 10 and (datetime.utcnow() - start_time).total_seconds() < 600:
            response = requests.get("https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails", headers=headers)
            data = ET.fromstring(response.content)
    
            nations = []
            for new_nation in data.find('NEWNATIONDETAILS').findall('NEWNATION'):
                region = new_nation.find('REGION').text
                if region not in excluded_regions:
                    nations.append(new_nation.get('name'))
    
            grouped_nations = [nations[i:i + 8] for i in range(0, len(nations), 8)]
            if not grouped_nations:
                await ctx.send("No nations found or all nations are in excluded regions.")
                return
    
           
            for i, group in enumerate(grouped_nations, start=1):
                nations_str = ",".join(group)
                url = f"https://www.nationstates.net/page=compose_telegram?tgto={nations_str}&message={template}"
                view.add_item(Button(style=ButtonStyle.url, label=f"Batch {i}", url=url))

            view.add_item(ApproveButton("Approve", "approve", self, ctx))
            view.add_item(DoneButton("All Done", "done", self))

            await ctx.send("Click on the buttons below or wait for the next cycle:", view=view)

            await asyncio.sleep(timer)  # Wait for the specified timer duration before the next cycle
            cycles += 1
            await ctx.send("Click on the buttons below to send telegrams to the nations:", view=view)


        self.loop_running = False  # Reset loop status after it ends
            

