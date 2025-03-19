from redbot.core import commands
import asyncio
import sans
import codecs
import os
import xml.etree.ElementTree as ET
import requests
import random
import html
import discord


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
        self.QOTDList=[]
        self.UA=""
        self.QOTDTime=40

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
    async def set_QOTD_time(self, ctx,time):
        self.QOTDTime=int(time)
        await ctx.send(f"time set to {self.QOTDTime}")
        
    @commands.command()
    @commands.is_owner()
    async def add_region_QOTD(self, ctx,*,region):
        region = region.lower()
        self.QOTDList.append(region)
        self.QOTDList = list(set(self.QOTDList))
        
        await ctx.send("The current QOTDList:")
        await ctx.send(self.QOTDList)

    @commands.command()
    @is_owner_overridable()
    async def QOTD(self, ctx,*,msg):
        msg = msg + "[spoiler=Click here for info on how to subscribe to QOTD] This Question of the day is brought to you by [region]The Wellspring[/region].  If you would like to sign up for questions of the day from me please send a Telegram to myself or [nation]9005[/nation].  We will get back to you as quickly as we can to set things up.[/spoiler]"  
        await self.reauth()
        await ctx.send(f"This will take approximately {int(self.QOTDTime) * len(self.QOTDList)} secounds") 
        for Region in self.QOTDList:
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
            output = "oopsie doodle"
            if "region=the_wellspring" in r.text:
                output = r.text.replace('<NATION id="the_phoenix_of_the_spring">\n<SUCCESS>Your message has been lodged! &lt;a href="',"")
                output = output.replace('"&gt;&lt;span class="smalltext"&gt;View your post.&lt;/span&gt;&lt;/a&gt;</SUCCESS>\n</NATION>',"")

        QOTD_id = 1115271309404942439
        channel_id = 1099398125061406770  # The target channel ID
        target_channel = self.bot.get_channel(channel_id)
    
        if target_channel:
            await target_channel.send("https://www.nationstates.net"+ output + f"<@&{QOTD_id}>")
        else:
            await ctx.send("https://www.nationstates.net"+ output + f"<@&{QOTD_id}>")
            
            
            
            #await ctx.send(r.text)
            await ctx.send(f"Posted on  {Region} RMB")
            await asyncio.sleep(self.QOTDTime)

    @commands.command()
    @commands.is_owner()
    async def remove_region_QOTD(self, ctx,*,region):
        region = region.lower()
        self.QOTDList.remove(region)
        await ctx.send("The current QOTDList:")
        await ctx.send(self.QOTDList)

    @commands.command()
    @commands.is_owner()
    async def list_region_QOTD(self, ctx,):
        await ctx.send("The current QOTDList:")
        await ctx.send(self.QOTDList)  
        
    
    @commands.command()
    @commands.is_owner()
    async def RN_agent(self, ctx, *,agent):
        sans.set_agent(agent, _force=True)
        await ctx.send("Agent set.")
        self.UA=agent

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
        await self.reauth()
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
        await ctx.send(r.text)
        rmbToken = r.xml.find("SUCCESS").text
        data.update(mode="execute", token=rmbToken)
        r = await self.api_request(data=data)
        await ctx.send(f"Posted on  {Region} RMB")

    @commands.command()
    async def card_scan(self,ctx,season="3",puppet="9006"):
        data ={'q':'cards+deck',"nationname":puppet}
        r = await self.api_request(data)
        root = ET.fromstring(r.text)
        # Find all CARDID elements and extract their values
        card_ids = []
        for card in root.findall(".//CARD"):
            card_season = card.find("SEASON").text
            card_category = card.find("CATEGORY").text
            
            if card_season == season and card_category != "legendary":
                card_id = card.find("CARDID").text
                card_ids.append(card_id)        
        output=[]
        for each in card_ids:
            output.append(f"https://www.nationstates.net/page=deck/card={each}/season={season}")
        if len(output) > 10:
            outbutt="\n".join(output[0:10])
            await ctx.send(outbutt)
        else:
            outbutt="\n".join(output)
            await ctx.send(outbutt)
            
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
   
    async def reauth(self):
        self.auth = sans.NSAuth(password=self.password)

    @commands.command()
    @commands.is_owner()
    async def clear_regional_nation(self, ctx):
        await ctx.send("Voiding any saved data on the regional Nation")
        self.auth = sans.NSAuth()
        self.RegionalNation = ""

    @commands.command()
    async def endo_lotto(self,ctx,name):
        # Fetch the XML data
        url = "https://www.nationstates.net/cgi-bin/api.cgi?nation=9006&q=endorsements"
        headers = {"User-Agent": "9005"}
        response = requests.get(url, headers=headers)
        
        # Parse the XML
        root = ET.fromstring(response.content)
        
        # Find the endorsements element
        endorsements_element = root.find('ENDORSEMENTS')
        
        # Split the text content of the endorsements element into a list of names
        endorsements_list = endorsements_element.text.split(',')
        
        # Randomly select one of the names
        random_endorsement = random.choice(endorsements_list)
        await ctx.send(f"Here you go {random_endorsement}")

    @commands.command(name="sendfile")
    @commands.admin_or_permissions(administrator=True)
    async def send_file(self, ctx, filename: str):
        """
        Sends a file located in the bot's directory.

        Admin Only.

        Usage: [p]sendfile filename.extension
        Example: [p]sendfile example.txt
        """
        filepath = os.path.join(os.getcwd(), filename)

        if not os.path.isfile(filepath):
            await ctx.send(f"❌ File `{filename}` not found.")
            return

        try:
            await ctx.send("📤 Sending file...", file=discord.File(fp=filepath))
        except Exception as e:
            await ctx.send(f"❌ Failed to send file: `{str(e)}`")


