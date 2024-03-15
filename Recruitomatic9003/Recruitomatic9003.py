from redbot.core import commands, Config
import xml.etree.ElementTree as ET
from discord import Embed, ButtonStyle
from discord.ui import View, Button
import asyncio
import aiohttp
from datetime import datetime
from datetime import datetime, timedelta

class BatchButton(Button):
    def __init__(self, label: str, url: str):
        super().__init__(style=ButtonStyle.url, label=label, url=url)

class ApproveButton(Button):
    def __init__(self, label: str, custom_id: str, cog_instance, ctx, nations_count):
        super().__init__(style=ButtonStyle.success, label=label, custom_id=custom_id)
        self.cog_instance = cog_instance
        self.ctx = ctx
        self.nations_count = nations_count  # Number of processed nations

    async def callback(self, interaction):
        await interaction.response.defer()

        
        # Fetch current user settings
        user_settings = await self.cog_instance.config.user(self.ctx.author).all()
        # Calculate new token count
        new_token_count = user_settings.get('tokens', 0) + self.nations_count
        # Update user settings with new token count
        await self.cog_instance.config.user(self.ctx.author).tokens.set(new_token_count)
        # Continue with running the next cycle
        view = View()
        await self.cog_instance.run_cycle(self.ctx, user_settings, view)



class DoneButton(Button):
    def __init__(self, label: str, custom_id: str, cog_instance, ctx):
        super().__init__(style=ButtonStyle.danger, label=label, custom_id=custom_id)
        self.cog_instance = cog_instance
        self.ctx = ctx

    async def callback(self, interaction):
        # Stop the recruitment loop
        self.cog_instance.loop_running = False

        # Fetch the total tokens earned by the user
        user_settings = await self.cog_instance.config.user(self.ctx.author).all()
        total_tokens = user_settings.get('tokens', 0)
        # Create an embed with the total tokens information
        embed = Embed(title="Tokens Earned", description=f"You have a total of {total_tokens} tokens. Use [p]token_shop to access the token shop to spend them on cool things!", color=0x00ff00)
        # Respond with the embed
        await interaction.response.send_message(embed=embed)
        
        for item in self.view.children:
            item.disabled = True
        # Acknowledge the interaction and update the message with disabled buttons
        await interaction.response.edit_message(view=self.view)
        self.processed_nations.clear()

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
        self.processed_nations = set()  # Track already processed nations
        

    async def fetch_nation_details(self, user_agent):
        async with aiohttp.ClientSession() as session:
            headers = {'User-Agent': user_agent}
            url = "https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails"
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.text()

    async def run_cycle(self, ctx, user_settings, view):
        excluded_regions = user_settings['excluded_regions']
        user_agent = user_settings['user_agent']

        if not user_settings['template']:
            await ctx.send("Make sure to set a template first with [p]set_user_template %template-1234%")
            return 
        template = user_settings['template']

        data = await self.fetch_nation_details(user_agent)
        if data is None:
            embed = Embed(title="Error", description="Failed to fetch nation details.", color=0xff0000)
            await ctx.send(embed=embed)
            return False

        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            embed = Embed(title="Error", description=f"Error parsing XML: {e}", color=0xff0000)
            await ctx.send(embed=embed)
            return False

        nations = []
        for new_nation in root.findall('./NEWNATIONDETAILS/NEWNATION'):
            nation_name = new_nation.get('name')
            region = new_nation.find('REGION').text
            if region not in excluded_regions and nation_name not in self.processed_nations:
                nations.append(nation_name)
                self.processed_nations.add(nation_name)  # Add to the set of already processed nations

        view.clear_items()
        embed = Embed(title="Recruitment Cycle", color=0x00ff00)
        if not nations:
            embed.description = "No new nations found in this cycle."
        else:
            for i, group in enumerate([nations[i:i + 8] for i in range(0, len(nations), 8)]):
                nations_str = ",".join(group)
                url = f"https://www.nationstates.net/page=compose_telegram?tgto={nations_str}&message={template}"
                view.add_item(BatchButton(label=f"Batch {i+1}", url=url))
            embed.description = "Nations ready for recruitment:"
        nations_count = len(nations)
        view.add_item(ApproveButton("Approve", "approve", self, ctx, nations_count))
        view.add_item(DoneButton("All Done", "done", self, ctx))


        current_time = datetime.utcnow()
        # Subtract 5 hours
        new_time = current_time - timedelta(hours=5)
        
        # Convert the new time to a Unix timestamp
        new_unix_timestamp = int(new_time.timestamp())
        
        # Now you can format this for Discord
        fancy_timestamp = f"<t:{new_unix_timestamp}:R>"
   
        if embed.description == "No new nations found in this cycle.":
            await ctx.send(content=fancy_timestamp,embed=embed, view=view)
        else:
            await ctx.send(content=ctx.author.mention+" "+fancy_timestamp,embed=embed, view=view)

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
        while self.loop_running and cycles < 10 and (datetime.utcnow() - start_time).total_seconds() < 600:
            view = View()

            success = await self.run_cycle(ctx, user_settings, view)
            if not success:
                break

            await asyncio.sleep(timer)
            cycles += 1

        self.loop_running = False

    @commands.command()
    async def set_user_template(self, ctx, *, template: str):
        """Sets the user's recruitment message template."""
        # Ensure the template meets your requirements, e.g., starts and ends with %%
        if template.startswith("%") and template.endswith("%"):
            await self.config.user(ctx.author).template.set(template)
            await ctx.send("Your recruitment template has been updated.")
        else:
            await ctx.send("Error: The template must start and end with %.")

