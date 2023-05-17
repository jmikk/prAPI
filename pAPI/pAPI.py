from redbot.core import commands
import requests
import time

class pAPI(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.password=""
        self.RegionalNation=""
        
    @commands.command(pass_context=True)
    async def pAPI_version(self,ctx):
        await ctx.send("This is version 1.4")
        
    def api_request(self,data, header,_limit=0):
        if _limit > 50:
            return
        url = "https://www.nationstates.net/cgi-bin/api.cgi"
        response = requests.post(url, data=data, headers=header)
        head = response.headers
        if waiting_time := head.get("Retry-After"):
            time.sleep(int(waiting_time)+1)
            self.api_request(data,header,_limit+1)
        try:
            requests_left = int(head["X-RateLimit-Remaining"])
        except KeyError:
            requests_left = int(head["RateLimit-Remaining"])
        try:
            seconds_until_reset = int(head["X-RateLimit-Reset"])
        except KeyError:
            seconds_until_reset = int(head["RateLimit-Reset"])
        time.sleep(seconds_until_reset / requests_left)
        return response

    @commands.command(pass_context=True)
    async def log(self,ctx):
        await ctx.send(ctx.me)
    
    
    @commands.command(pass_context=True)
    async def rmb_post(self, ctx, User_Agent, Region, *msg):
        output = ""
        for each in msg:
            output=output+each+" "
        data={"nation":self.RegionalNation,"region":Region,"c":"rmbpost","text":output,"mode":"prepare"}
        r = self.api_request(data=data,header={"User-Agent":User_Agent,'X-Password':self.password})
        rmbToken = r.text.replace(f'<NATION id="{self.RegionalNation}">\n<SUCCESS>',"")
        rmbToken = rmbToken.replace('</SUCCESS>\n</NATION>',"")
        rmbToken = rmbToken.strip()
        data = {"nation":self.RegionalNation,"region":Region,"c":"rmbpost","text":output,"mode":"execute","token":rmbToken}
        headerz = {'User-Agent': User_Agent, 'X-pin': r.headers["x-pin"]}
        r = self.api_request(data=data,header=headerz)
        if str(r.status_code) == "200":
            await ctx.send(f"Posted on  {Region} RMB")
        else:
            await ctx.send(r.text)
        
        
    @commands.command(pass_context=True)
    async def gift_card(self, ctx, User_Agent, giftie, cardid, season):
        await ctx.send(f"Attempting to gift {cardid} to {giftie} from {self.RegionalNation}")
        headers = {"User-Agent": User_Agent, 'X-Password':self.password}
        data = {'nation': self.RegionalNation, 'cardid': cardid, 'season': season, 'to': giftie, 'mode': "prepare", 'c': 'giftcard'}
        r = self.api_request(data, headers)
        giftToken = r.text.replace(f'<NATION id="{self.RegionalNation}">\n<SUCCESS>',"")
        giftToken = giftToken.replace('</SUCCESS>\n</NATION>',"")
        giftToken= giftToken.strip()
        #await ctx.send(r.headers)
        headerz = {'User-Agent': User_Agent, 'X-pin': r.headers["x-pin"]}
        data = {'nation': self.RegionalNation, 'cardid': cardid, 'season': season, 'token': giftToken, 'to': giftie, 'mode': "execute", 'c': 'giftcard'}
        z2 = self.api_request(data=data, header=headerz)
        #await ctx.send(z2.content)
        if str(z2.status_code) == "200":
            await ctx.send(f"Gifted {cardid}, season {season} to {giftie}")
        else:
            await ctx.send(z2.text)

    @commands.command(pass_context=True)
    async def set_regional_nation(self,ctx,*nation):
        nation=str(nation).replace("(","").replace(")","").replace(",","").replace("'","").replace(" ","_")
        nation = nation.lower()
        self.RegionalNation=nation
        await ctx.send(f"Set regional nation to {self.RegionalNation}")

    @commands.command(pass_context=True)
    async def set_regional_nation_password(self,ctx,password2):
        self.password = password2
        await ctx.send(f"Set regional nation password for {self.RegionalNation}.")

    @commands.command(pass_context=True)
    async def clear_regional_nation(self,ctx):
        await ctx.send("Voiding any saved data on the regional Nation")
        self.password=""
        self.RegionalNation=""
