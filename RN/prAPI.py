from redbot.core import commands
import asyncio
import sans
import codecs


def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False
    return commands.permissions_check(predicate)


class prAPI(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.auth = sans.NSAuth()
        self.RegionalNation = ""
        self.client = sans.AsyncClient()
        self.password = ""

    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

 #   async def cog_command_error(self, ctx, error):
 #       await ctx.send(" ".join(error.args))

    async def api_request(self, data) -> sans.Response:
        response = await self.client.get(sans.World(**data), auth=self.auth)
        response.raise_for_status()
        return response

    @commands.command()
    @commands.is_owner()
    async def RN_agent(self, ctx, *,agent):
        sans.set_agent(agent, _force=True)
        await ctx.send("Agent set.")

    @commands.command()
    @is_owner_overridable()
    async def RN_version(self, ctx):
        await ctx.send("This is version 1.5")

    @commands.command()
    @is_owner_overridable()
    async def dispatch_list(self, ctx):
        await self.reauth()
        data = {
            "nation": self.RegionalNation,
             "q" : "dispatchlist"
        }
        r = await self.api_request(data=data)
        r.xml.findall("DISPATCH")
       # output=""
       # for each in dispatchs:
       #    output = f"{output} ID: {each.get('id')} Title: {each.find('TITLE').text} Views: {each.find('VIEWS').text} Score: {find('SCORE').text}\n"
       #The above code I want to work but does not
        await ctx.send(r.text)

    @commands.command()
    @is_owner_overridable()
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
    @is_owner_overridable()
    async def edit_dispatch(self, ctx, id:str, title: str, category:str, subcategory:str):
        await self.reauth()
        output = await ctx.message.attachments[0].read()
        output = codecs.decode(output, 'utf-8-sig')
        data = {
            "nation": self.RegionalNation,
            "c": "dispatch",
            "dispatch": "edit",
            "text": output,
            "mode": "prepare",
            "category": category,
            "subcategory": subcategory,
            "title": title,
            "dispatchid":id
        }
        r = await self.api_request(data=data)
        dispatchToken = r.xml.find("SUCCESS").text
        data.update(mode="execute", token=dispatchToken)
        r = await self.api_request(data=data)
        rtext = r.xml.find("SUCCESS").text
        await ctx.send(rtext)
        
    @commands.command()
    @is_owner_overridable()
    async def new_dispatch(self, ctx,title: str, category:str, subcategory:str):
        await self.reauth()
        output = await ctx.message.attachments[0].read()
        output = codecs.decode(output, 'utf-8-sig')
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
        rtext = r.xml.find("SUCCESS").text
        await ctx.send(rtext)
        
    @commands.command()
    @is_owner_overridable()
    async def delete_dispatch(self, ctx,ID):
        await self.reauth()
        data = {
            "nation": self.RegionalNation,
            "c": "dispatch",
            "dispatch": "remove",
            "mode": "prepare",
            "dispatchid":ID
        }
        r = await self.api_request(data=data)
        dispatchToken = r.xml.find("SUCCESS").text
        data.update(mode="execute", token=dispatchToken)
        r = await self.api_request(data=data)
        rtext = r.xml.find("SUCCESS").text
        await ctx.send(rtext)

    @commands.command()
    @is_owner_overridable()
    async def rmb_post(self, ctx, Region, *, msg):
        await self.reauth(ctx=ctx)
        str = ''
        for item in msg:
            str = str + item
            
        data = {
            "nation": self.RegionalNation,
            "region": Region,
            "c": "rmbpost",
            "text": str,
            "mode": "prepare",
        }
        r = await self.api_request(data=data)
        rmbToken = r.xml.find("SUCCESS").text
        data.update(mode="execute", token=rmbToken)
        r = await self.api_request(data=data)
        await ctx.send(f"Posted on  {Region} RMB")

    @commands.command()
    @is_owner_overridable()
    async def gift_card(self, ctx, giftie, cardid, season):
        await self.reauth()
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
    @commands.is_owner()
    async def set_regional_nation(self, ctx, *, nation):
        nation = "_".join(nation.lower().split())
        self.RegionalNation = nation
        await ctx.send(f"Set regional nation to {self.RegionalNation}")

    @commands.command()
    @commands.is_owner()
    async def set_regional_nation_password(self, ctx, *, password2):
        self.password=password2
        self.auth = sans.NSAuth(password=self.password)
        await ctx.send(f"Set regional nation password for {self.RegionalNation}.")
   
    async def reauth(self,ctx):
        self.auth = sans.NSAuth(password=self.password)
        await ctx.send("Reauthed")

    @commands.command()
    @commands.is_owner()
    async def clear_regional_nation(self, ctx):
        await ctx.send("Voiding any saved data on the regional Nation")
        self.auth = sans.NSAuth()
        self.RegionalNation = ""
