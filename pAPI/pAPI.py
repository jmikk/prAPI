from redbot.core import commands
import asyncio
import sans
from discord.ext import commands


class pAPI(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.auth = sans.NSAuth()
        self.RegionalNation = ""
        self.client = sans.AsyncClient()

    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    async def cog_command_error(self, ctx, error):
        await ctx.send(" ".join(error.args))

    async def api_request(self, data) -> sans.Response:
        response = await self.client.post(sans.World(**data), auth=self.auth)
        response.raise_for_status()
        return response

    @commands.command()
    async def pAPI_agent(self, ctx, *, agent):
        sans.set_agent(agent, _force=True)
        await ctx.send("Agent set.")

    @commands.command()
    async def pAPI_version(self, ctx):
        await ctx.send("This is version 1.5")

    @commands.command()
    async def dispatch_list_types(self, ctx):
        await ctx.send(
            """
1 -> factbook
    100 - Overview
    101 - History
    102 - Geography
    103 -> culture 
    104 - poltics
    105- Legeslation 
    106 -> Relgion
    107 -> Military
    108 -> Economy
    109 -> International
    110 -> Triva
    111 -> Miscellaneous

3 -> Bulletin
    305 -> Policy
    315 -> News
    325 -> Opinion
    385 -> Campaign

5-> account
    505 -> Milatary
    515 -> trade
    525 -> sport
    535 -> Drama
    545 -> Diplomacy
    555 -> Science
    565 -> Culture
    595 -> Other

8-> Meta
    835 -> Gameplay
    845 -> Reference
"""
        )

    @commands.command()
    async def new_dispatch(self, ctx, file: discord.File, title, category, subcategory):
        with open(File, "r") as f:
            output = f.read()
        data = {
            "nation": self.RegionalNation,
            "c": "dispatch",
            "dispatch": "add",
            "text": output,
            "mode": "prepare",
            "category": category,
            "subcategory": subcategory,
            "title": title,
        }
        r = await self.api_request(data=data)
        dispatchToken = r.xml.find("SUCCESS").text
        data.update(mode="execute", token=dispatchToken)
        r = await self.api_request(data=data)
        await ctx.send(f"Posted Dispatch URL when 9003 grabs it for ya")

    @commands.command()
    async def rmb_post(self, ctx, Region, *, msg):
        output = msg
        data = {
            "nation": self.RegionalNation,
            "region": Region,
            "c": "rmbpost",
            "text": output,
            "mode": "prepare",
        }
        r = await self.api_request(data=data)
        rmbToken = r.xml.find("SUCCESS").text
        data.update(mode="execute", token=rmbToken)
        r = await self.api_request(data=data)
        await ctx.send(f"Posted on  {Region} RMB")

    @commands.command()
    async def gift_card(self, ctx, giftie, cardid, season):
        await ctx.send(
            f"Attempting to gift {cardid} to {giftie} from {self.RegionalNation}"
        )
        data = {
            "nation": self.RegionalNation,
            "cardid": cardid,
            "season": season,
            "to": giftie,
            "mode": "prepare",
            "c": "giftcard",
        }
        r = await self.api_request(data)
        giftToken = r.xml.find("SUCCESS").text
        # await ctx.send(r.headers)
        data.update(mode="execute", token=giftToken)
        await self.api_request(data=data)
        # await ctx.send(z2.content)
        await ctx.send(f"Gifted {cardid}, season {season} to {giftie}")

    @commands.command()
    async def set_regional_nation(self, ctx, *, nation):
        nation = "_".join(nation.lower().split())
        self.RegionalNation = nation
        await ctx.send(f"Set regional nation to {self.RegionalNation}")

    @commands.command()
    async def set_regional_nation_password(self, ctx, *, password2):
        self.auth = sans.NSAuth(password=password2)
        await ctx.send(f"Set regional nation password for {self.RegionalNation}.")

    @commands.command()
    async def clear_regional_nation(self, ctx):
        await ctx.send("Voiding any saved data on the regional Nation")
        self.auth = sans.NSAuth()
        self.RegionalNation = ""
