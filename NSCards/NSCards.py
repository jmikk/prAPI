import discord
import aiohttp
import asyncio
import random
import time
from bs4 import BeautifulSoup
from redbot.core import commands
from redbot.core.utils.chat_menus import menu, DEFAULT_CONTROLS

class NSThrottler:
    def __init__(self):
        self.remaining = 50
        self.retry_after = 0
        self.last_request = 0
        self.lock = asyncio.Lock()

    async def throttle(self):
        async with self.lock:
            now = time.time()
            
            # If we were hit with a 429 previously, respect the retry-after
            if self.retry_after > 0:
                await asyncio.sleep(self.retry_after)
                self.retry_after = 0
            
            # Proactive Throttling: 
            # If we have < 5 requests left, force a 1-second pause between calls
            # to let the rolling 30-second window "breathe".
            if self.remaining < 5:
                delay = max(0, 1.0 - (now - self.last_request))
                await asyncio.sleep(delay)
            
            self.last_request = time.time()

    def update(self, headers):
        # NS returns 'X-Ratelimit-Remaining'
        rem = headers.get("X-Ratelimit-Remaining")
        if rem is not None:
            self.remaining = int(rem)
            
        # NS returns 'Retry-After' in seconds
        ret = headers.get("Retry-After")
        if ret is not None:
            self.retry_after = int(ret)

class NSCards(commands.Cog):
    """NationStates Cards with Header-Aware Rate Limiting."""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        # Change 'YourNation' to your actual nation name to follow NS script rules!
        self.headers = {"User-Agent": "RedBot Cog - Version 3.0 - Used by [YourNation]"}
        self.throttler = NSThrottler()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def fetch(self, url):
        await self.throttler.throttle()
        
        async with self.session.get(url, headers=self.headers) as response:
            self.throttler.update(response.headers)
            
            if response.status == 429:
                wait = int(response.headers.get("Retry-After", 5))
                await asyncio.sleep(wait)
                return await self.fetch(url) # Retry once
                
            if response.status != 200:
                return None
                
            return BeautifulSoup(await response.text(), "xml")

    @commands.command()
    async def draw(self, ctx, nation: str):
        """Fetch 5 random cards from a nation's deck."""
        await ctx.trigger_typing()
        
        # Request 1: Get the deck
        deck_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname={nation}"
        soup = await self.fetch(deck_url)
        
        if not soup or not soup.find("DECK"):
            return await ctx.send("Could not access deck. Check the nation name.")

        cards = soup.find_all("CARD")
        if not cards:
            return await ctx.send("Deck is empty.")

        sampled = random.sample(cards, min(len(cards), 5))
        pages = []

        for i, card in enumerate(sampled, 1):
            cid = card.find("CARDID").text
            season = card.find("SEASON").text
            
            # Request 2-6: Individual card info
            info_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={cid};season={season}"
            card_soup = await self.fetch(info_url)
            
            if not card_soup: continue

            name = card_soup.find("NAME").text
            rarity = card_soup.find("RARITY").text.capitalize()
            owners = len(card_soup.find_all("OWNER"))

            embed = discord.Embed(title=f"{name} (S{season})", color=await ctx.embed_color())
            embed.set_thumbnail(url=f"https://www.nationstates.net/images/cards/s{season}/{cid}.jpg")
            embed.add_field(name="Rarity", value=rarity, inline=True)
            embed.add_field(name="Owners", value=str(owners), inline=True)
            embed.set_footer(text=f"Limit Remaining: {self.throttler.remaining} | {i}/5")
            pages.append(embed)

        await menu(ctx, pages, DEFAULT_CONTROLS)

def setup(bot):
    bot.add_cog(NSCards(bot))
