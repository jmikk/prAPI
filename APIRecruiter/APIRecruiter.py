import discord
from redbot.core import commands, Config
from discord.ext import tasks  
import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import time
import re
import datetime
import traceback

class APIRecruiter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=345678765)
        self.config.register_global(
            blacklist_regions=[],
            sent_nations=[],
            client_key="",
            tgid="",
            secret_key="",
            last_sent_time=0,
            last_report_count=0,
            total_tgs_sent=0,
            user_agent="APIRecruiterBot/1.0"
        )
        self.recruitment_loop.start()
        self.daily_report.start()

    def cog_unload(self):
        self.recruitment_loop.cancel()
        self.daily_report.cancel()

    async def get_log_channel(self):
        return self.bot.get_channel(1098673276064120842)

    @commands.command()
    @commands.is_owner()
    async def settginfo(self, ctx, client_key: str, tgid: str, secret_key: str):
        await self.config.client_key.set(client_key)
        await self.config.tgid.set(tgid)
        await self.config.secret_key.set(secret_key)
        channel = await self.get_log_channel()
        if channel:
            await channel.send("Telegram info set successfully.")

    @commands.command()
    @commands.is_owner()
    async def setuseragent(self, ctx, *, user_agent: str):
        await self.config.user_agent.set(user_agent)
        channel = await self.get_log_channel()
        if channel:
            await channel.send(f"User-Agent set to: {user_agent}")

    @commands.command()
    async def addregionblacklist(self, ctx, *, region: str):
        region = region.lower().replace(" ", "_")
        blacklist = await self.config.blacklist_regions()
        channel = await self.get_log_channel()
        if region not in blacklist:
            blacklist.append(region)
            await self.config.blacklist_regions.set(blacklist)
            if channel:
                await channel.send(f"Region '{region}' added to blacklist.")
        else:
            if channel:
                await channel.send(f"Region '{region}' is already blacklisted.")

    @commands.command()
    async def showblacklist(self, ctx):
        blacklist = await self.config.blacklist_regions()
        channel = await self.get_log_channel()
        if channel:
            await channel.send("Blacklisted Regions: " + ", ".join(blacklist))

    async def fetch_new_nations(self):
        user_agent = await self.config.user_agent()
        headers = {"User-Agent": user_agent}
        url = "https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails"
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
                root = ET.fromstring(text)
                nations = []
                for nation in root.find("NEWNATIONDETAILS"):
                    name = nation.attrib["name"]
                    region = nation.find("REGION").text
                    nations.append((name, region))
                return nations

    async def send_telegram(self, nation_name, attempt=1):
        #debug output 
        channel = await self.get_log_channel()
        if channel:
            await channel.send(f"Here Sending TG")
        #end debug output
        if attempt > 5:
            channel = await self.get_log_channel()
            if channel:
                await channel.send(f"Failed to send TG to {nation_name} after 5 attempts. Skipping.")
            return False

        client_key = await self.config.client_key()
        tgid = await self.config.tgid()
        secret_key = await self.config.secret_key()
        user_agent = await self.config.user_agent()
        url = (f"https://www.nationstates.net/cgi-bin/api.cgi?a=sendTG"
               f"&client={client_key}&tgid={tgid}&key={secret_key}&to={nation_name}")
        headers = {"User-Agent": user_agent}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    await self.config.last_sent_time.set(int(time.time()))
                    sent = await self.config.sent_nations()
                    sent.append(nation_name)
                    await self.config.sent_nations.set(sent)
                    total_sent = await self.config.total_tgs_sent()
                    await self.config.total_tgs_sent.set(total_sent + 1)
                    channel = await self.get_log_channel()
                    if channel:
                        await channel.send(f"Sent TG to {nation_name}")
                    return True
                elif resp.status == 429:
                    channel = await self.get_log_channel()
                    if channel:
                        await channel.send(f"To soon!")
                    retry_after = int(resp.headers.get('X-Retry-After', 180))
                    await asyncio.sleep(retry_after)
                    return await self.send_telegram(nation_name, attempt + 1)
                channel = await self.get_log_channel()
                if channel:
                    await channel.send(f"{resp.text()[:1900]}")
                return False

    @tasks.loop(seconds=60)
    async def recruitment_loop(self):
        try:
            #debug output 
            channel = await self.get_log_channel()
            if channel:
                await channel.send(f"Here!")
            #end debug output
            blacklist = await self.config.blacklist_regions()
            sent_nations = await self.config.sent_nations()
            last_sent_time = await self.config.last_sent_time()
            now = int(time.time())
    
            if now - last_sent_time < 180:
                return  # Wait for recruitment rate limit
    
            nations = await self.fetch_new_nations()
            for name, region in nations:
                if name in sent_nations:
                    continue
                if re.search(r"\d+$", name):
                    continue  # Skip nations ending in numbers
                if region.lower() in blacklist:
                    continue
                success = await self.send_telegram(name)
                if success:
                    print(f"Sent TG to {name}")
                break
        except Exception as e:
            tb = traceback.format_exc()
            channel = await self.get_log_channel()
            if channel:
                await channel.send(f"Error {tb}[:1900]")
            


    @recruitment_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def daily_report(self):
        await self.send_report()

    @daily_report.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def manualreport(self, ctx):
        await self.send_report()

    async def send_report(self):
        sent_nations = await self.config.sent_nations()
        last_report_count = await self.config.last_report_count()
        total_sent = await self.config.total_tgs_sent()
        sent_since_last = total_sent - last_report_count

        report_content = "\n".join(sent_nations)
        filename = f"tg_sent_{datetime.datetime.utcnow().strftime('%Y-%m-%d')}.txt"

        file = discord.File(fp=discord.File(fp=report_content.encode(), filename=filename), filename=filename)
        channel = await self.get_log_channel()
        if channel:
            await channel.send(
                content=(f"Recruitment Report:\nTotal TGs Sent: {total_sent}\n"
                         f"TGs Sent Since Last Report: {sent_since_last}"),
                file=file
            )
        await self.config.last_report_count.set(total_sent)
        await self.config.sent_nations.set([])

    @commands.command()
    async def resetrecruitlist(self, ctx):
        await self.config.sent_nations.set([])
        await self.config.last_report_count.set(0)
        await self.config.total_tgs_sent.set(0)
        channel = await self.get_log_channel()
        if channel:
            await channel.send("Recruitment list and report count reset.")

    @commands.command()
    async def getrecruitlist(self, ctx):
        total_sent = await self.config.total_tgs_sent()
        channel = await self.get_log_channel()
        if channel:
            await channel.send(f"Total TGs sent: {total_sent}")

    @commands.command()
    @commands.is_owner()
    async def forcestartloops(self, ctx):
        if not self.recruitment_loop.is_running():
            try:
                self.recruitment_loop.start()
                await ctx.send("Recruitment loop started.")
            except RuntimeError as e:
                await ctx.send(f"Failed to start recruitment loop: {e}")
        else:
            await ctx.send("Recruitment loop is already running.")
    
        if not self.daily_report.is_running():
            self.daily_report.start()
            await ctx.send("Daily report loop started.")
        else:
            await ctx.send("Daily report loop is already running.")

