import discord
import aiohttp
import asyncio
import random
import time
from bs4 import BeautifulSoup
from redbot.core import commands
# Updated Import below:
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
            
            if self.remaining < 10:
                delay = max(0, 1.0 - (now - self.last_request))
                await asyncio.sleep(delay)
            
            self.last_request = time.time()

    def update(self, headers):
        rem = headers.get("X-Ratelimit-Remaining")
        if rem is not None:
            self.remaining = int(rem)
        
        # NS specific: they also use X-Retry-After sometimes, 
        # but Retry-After is the standard.
        ret = headers.get("Retry-After") or headers.get("X-Retry-After")
        if ret is not None:
            self.retry_after = int(ret)

class NSCards(commands.Cog):
    """NationStates Cards with Header-Aware Rate Limiting."""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        # Please ensure [YourNation] is replaced with your NS nation name
        self.headers = {"User-Agent": "RedBot Cog - NSCards v3.1 - Used by [YourNation]"}
        self.throttler = NSThrottler()

    def cog_unload(self):
        # Clean up the session when the cog is unloaded
        self.bot.loop.create_task(self.session.close())

    async def fetch(self, url):
        await self.throttler.throttle()
        async with self.session.get(url, headers=self.headers) as response:
            self.throttler.update(response.headers)
            
            if response.status == 429:
                wait = int(response.headers.get("Retry-After", 5))
                await asyncio.sleep(wait)
                return await self.fetch(url) 
                
            if response.status != 200:
                return None
                
            return BeautifulSoup(await response.text(), "xml")

    @commands.command()
    async def draw(self, ctx, nation: str = 9006):
        """Fetch 5 random cards from a nation's deck."""
        
        # 'trigger_typing' is now 'typing' and used as a context manager
        async with ctx.typing():
            # Request 1: Get the deck
            deck_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname={nation}"
            soup = await self.fetch(deck_url)
            
            if not soup or not soup.find("DECK"):
                return await ctx.send("Could not access deck. Check the nation name or API status.")

            cards = soup.find_all("CARD")
            if not cards:
                return await ctx.send("This nation's deck is empty.")

            sampled = random.sample(cards, min(len(cards), 5))
            pages = []

            for i, card in enumerate(sampled, 1):
                cid = card.find("CARDID").text
                season = card.find("SEASON").text
                
                # Requests 2-6: Individual card info
                info_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={cid};season={season}"
                card_soup = await self.fetch(info_url)
                
                if not card_soup: 
                    continue

                name = card_soup.find("NAME").text if card_soup.find("NAME") else "Unknown"
                rarity = card_soup.find("RARITY").text.capitalize() if card_soup.find("RARITY") else "Unknown"
                owners = len(card_soup.find_all("OWNER"))

                embed = discord.Embed(
                    title=f"{name} (S{season})", 
                    color=await ctx.embed_color(),
                    description=f"**Card ID:** {cid}"
                )
                embed.set_thumbnail(url=f"https://www.nationstates.net/images/cards/s{season}/{cid}.jpg")
                embed.add_field(name="Rarity", value=rarity, inline=True)
                embed.add_field(name="Owners", value=f"{owners} nations", inline=True)
                embed.set_footer(text=f"Limit Remaining: {self.throttler.remaining} | Card {i}/{len(sampled)}")
                pages.append(embed)

        if not pages:
            return await ctx.send("Failed to retrieve card data from the API.")

        await menus.menu(ctx, pages, menus.DEFAULT_CONTROLS)

async def setup(bot):
    # Added 'async' to setup which is preferred in newer Red versions
    await bot.add_cog(NSCards(bot))
