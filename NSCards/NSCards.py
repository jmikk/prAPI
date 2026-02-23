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
    """NationStates Cards with Season-specific Flags and Category Colors."""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.headers = {"User-Agent": "RedBot Cog - NSCards v6.0 - Used by [YourNation]"}
        self.throttler = NSThrottler()
        
        # Color mapping based on card category
        self.rarity_colors = {
            "common": 0x929292,      # Grey
            "uncommon": 0x47b547,    # Green
            "rare": 0x3d76b8,        # Blue
            "ultra-rare": 0x8a2be2,  # Purple
            "epic": 0xff8c00,        # Orange
            "legendary": 0xffd700    # Gold
        }

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
        """Fetch 5 random cards with season-accurate flags and MV."""
        async with ctx.typing():
            deck_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname={nation}"
            root = await self.fetch_xml(deck_url)
            
            if root is None:
                return await ctx.send("Could not access API.")

            cards = root.findall(".//CARD")
            if not cards:
                return await ctx.send("Deck is empty or nation doesn't exist.")

            sampled = random.sample(cards, min(len(cards), 5))
            pages = []

            for i, card_data in enumerate(sampled, 1):
                # Season and ID from the first request
                cid = card_data.find("CARDID").text
                season = card_data.find("SEASON").text
                
                # Detailed info from the second request
                info_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={cid};season={season}"
                card_root = await self.fetch_xml(info_url)
                
                if card_root is None: continue

                # Extraction from card_info
                name = card_root.find(".//NAME").text if card_root.find(".//NAME") is not None else "Unknown"
                category = card_root.find(".//CATEGORY").text if card_root.find(".//CATEGORY") is not None else "common"
                mv = card_root.find(".//MARKET_VALUE").text if card_root.find(".//MARKET_VALUE") is not None else "0.00"
                flag_path = card_root.find(".//FLAG").text if card_root.find(".//FLAG") is not None else ""
                owners_count = len(card_root.findall(".//OWNER"))

                # Constructing the dynamic Flag URL
                # Format: https://www.nationstates.net/images/cards/s[SEASON]/[FLAG_PATH]
                full_flag_url = f"https://www.nationstates.net/images/cards/s{season}/{flag_path}"
                
                # Card link for the title
                card_link = f"https://www.nationstates.net/page=deck/card={cid}/season={season}"
                
                # Embed Setup
                embed_color = self.rarity_colors.get(category.lower(), 0x929292)
                
                embed = discord.Embed(
                    title=f"{name} (S{season})",
                    url=card_link,
                    color=embed_color
                )
                embed.set_thumbnail(url=full_flag_url)
                embed.set_image(url=f"https://www.nationstates.net/images/cards/s{season}/{cid}.jpg")
                
                embed.add_field(name="Category", value=category.capitalize(), inline=True)
                embed.add_field(name="MV", value=f"🪙 {mv}", inline=True)
                embed.add_field(name="Owner Count", value=f"👥 {owners_count}", inline=True)
                
                embed.set_footer(text=f"Limit: {self.throttler.remaining} | {i}/{len(sampled)}")
                pages.append(embed)

        if not pages:
            return await ctx.send("Failed to retrieve card data.")
        await menus.menu(ctx, pages, menus.DEFAULT_CONTROLS)

async def setup(bot):
    await bot.add_cog(NSCards(bot))
