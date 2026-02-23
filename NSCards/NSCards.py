import discord
import aiohttp
import asyncio
import random
import time
import xml.etree.ElementTree as ET
from redbot.core import commands
from redbot.core.utils import menus

class NSThrottler:
    def __init__(self):
        self.remaining = 50
        self.retry_after = 0
        self.last_request = 0
        self.lock = asyncio.Lock()

    async def throttle(self):
        async with self.lock:
            now = time.time()
            if self.retry_after > 0:
                await asyncio.sleep(self.retry_after)
                self.retry_after = 0
            if self.remaining < 5:
                delay = max(0, 1.0 - (now - self.last_request))
                await asyncio.sleep(delay)
            self.last_request = time.time()

    def update(self, headers):
        rem = headers.get("X-Ratelimit-Remaining")
        if rem: self.remaining = int(rem)
        ret = headers.get("Retry-After") or headers.get("X-Retry-After")
        if ret: self.retry_after = int(ret)

class NSCards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.headers = {"User-Agent": "RedBot Cog - NSCards v4.0 - Used by [YourNation]"}
        self.throttler = NSThrottler()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def fetch_xml(self, url):
        await self.throttler.throttle()
        async with self.session.get(url, headers=self.headers) as response:
            self.throttler.update(response.headers)
            if response.status == 429:
                await asyncio.sleep(int(response.headers.get("Retry-After", 5)))
                return await self.fetch_xml(url)
            if response.status != 200:
                return None
            text = await response.text()
            return ET.fromstring(text)

    @commands.command()
    async def draw(self, ctx, nation: str):
        """Fetch 5 random cards using native XML parsing."""
        async with ctx.typing():
            deck_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname={nation}"
            root = await self.fetch_xml(deck_url)
            
            if root is None:
                return await ctx.send("Could not access API.")

            # Find all CARD elements
            cards = root.findall(".//CARD")
            if not cards:
                return await ctx.send("Deck is empty or nation doesn't exist.")

            sampled = random.sample(cards, min(len(cards), 5))
            pages = []

            for i, card in enumerate(sampled, 1):
                cid = card.find("CARDID").text
                season = card.find("SEASON").text
                
                info_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={cid};season={season}"
                card_root = await self.fetch_xml(info_url)
                
                if card_root is None: continue

                # Extraction using ElementTree
                name = card_root.find(".//NAME").text if card_root.find(".//NAME") is not None else "Unknown"
                rarity = card_root.find(".//RARITY").text.capitalize() if card_root.find(".//RARITY") is not None else "Unknown"
                owners = len(card_root.findall(".//OWNER"))

                embed = discord.Embed(title=f"{name} (S{season})", color=await ctx.embed_color())
                embed.set_thumbnail(url=f"https://www.nationstates.net/images/cards/s{season}/{cid}.jpg")
                embed.add_field(name="Rarity", value=rarity, inline=True)
                embed.add_field(name="Owners", value=str(owners), inline=True)
                embed.set_footer(text=f"Limit: {self.throttler.remaining} | {i}/{len(sampled)}")
                pages.append(embed)

        if not pages:
            return await ctx.send("No card data found.")
        await menus.menu(ctx, pages, menus.DEFAULT_CONTROLS)

async def setup(bot):
    await bot.add_cog(NSCards(bot))
