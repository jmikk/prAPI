from redbot.core import commands, Config
import requests
import xml.etree.ElementTree as ET

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
    async def recruit(self, ctx):
        user_settings = await self.config.user(ctx.author).all()
        excluded_regions = user_settings['excluded_regions']
        user_agent = user_settings['user_agent']
        
        headers = {'User-Agent': user_agent}
        response = requests.get("https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails", headers=headers)
        data = ET.fromstring(response.content)
        
        nations = []
        for new_nation in data.find('NEWNATIONDETAILS').findall('NEWNATION'):
            region = new_nation.find('REGION').text
            if region not in excluded_regions:
                nations.append(new_nation.get('name'))
        
        grouped_nations = [nations[i:i + 8] for i in range(0, len(nations), 8)]
        for group in grouped_nations:
            await ctx.send(', '.join(group))
