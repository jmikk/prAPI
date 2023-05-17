from redbot.core import commands
import asyncio
import sans


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
        await ctx.send("This is version 1.4")

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
