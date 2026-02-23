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
    """NationStates Card Poker - Pulling from 9005."""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.headers = {"User-Agent": "RedBot Cog - CardPoker v7.0 - Used by [YourNation]"}
        self.throttler = NSThrottler()
        
        # Color & Emoji mapping for Rarity/Category
        self.rarity_data = {
            "common": {"c": 0x929292, "e": "⚪"},
            "uncommon": {"c": 0x47b547, "e": "🟢"},
            "rare": {"c": 0x3d76b8, "e": "🔵"},
            "ultra-rare": {"c": 0x8a2be2, "e": "🟣"},
            "epic": {"c": 0xff8c00, "e": "🟠"},
            "legendary": {"c": 0xffd700, "e": "🟡"}
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
    async def draw(self, ctx):
        """Draw 5 cards from 9005 and display as a poker hand."""
        async with ctx.typing():
            # Locked to nation 9005
            deck_url = "https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname=9005"
            root = await self.fetch_xml(deck_url)
            
            if root is None:
                return await ctx.send("Could not access the NationStates API.")

            cards_elements = root.findall(".//CARD")
            if not cards_elements:
                return await ctx.send("Deck 9005 is empty or unavailable.")

            sampled = random.sample(cards_elements, min(len(cards_elements), 5))
            card_pages = []
            overview_lines = []

            for i, card_data in enumerate(sampled, 1):
                cid = card_data.find("CARDID").text
                season = card_data.find("SEASON").text
                
                info_url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={cid};season={season}"
                card_root = await self.fetch_xml(info_url)
                
                if card_root is None: continue

                name = card_root.find(".//NAME").text or "Unknown"
                cat = (card_root.find(".//CATEGORY").text or "common").lower()
                mv = card_root.find(".//MARKET_VALUE").text or "0.00"
                flag_path = card_root.find(".//FLAG").text or ""
                owners = len(card_root.findall(".//OWNER"))

                data = self.rarity_data.get(cat, self.rarity_data["common"])
                card_link = f"https://www.nationstates.net/page=deck/card={cid}/season={season}"
                
                # Add to Summary Page
                overview_lines.append(f"{i}. {data['e']} **[{name}]({card_link})** ({cat.capitalize()})")

                # Individual Detail Page
                embed = discord.Embed(title=f"{name} (S{season})", url=card_link, color=data['c'])
                embed.set_thumbnail(url=f"https://www.nationstates.net/images/cards/s{season}/{flag_path}")
                embed.set_image(url=f"https://www.nationstates.net/images/cards/s{season}/{cid}.jpg")
                embed.add_field(name="Category", value=f"{data['e']} {cat.capitalize()}", inline=True)
                embed.add_field(name="MV", value=f"🪙 {mv}", inline=True)
                embed.add_field(name="Owners", value=f"👥 {owners}", inline=True)
                embed.set_footer(text=f"Card {i}/5 | Limit: {self.throttler.remaining}")
                card_pages.append(embed)

            if not card_pages:
                return await ctx.send("Failed to retrieve card data.")

            # Create the First (Overview) Page
            overview_embed = discord.Embed(
                title="🎴 Your Poker Hand - Nation 9005",
                description="\n".join(overview_lines),
                color=0x2f3136
            )
            overview_embed.set_footer(text="Legend: ⚪C 🟢U 🔵R 🟣UR 🟠E 🟡L")
            
            # Combine Overview with Detail Pages
            final_pages = [overview_embed] + card_pages

        await menus.menu(ctx, final_pages, menus.DEFAULT_CONTROLS)

async def setup(bot):
    await bot.add_cog(NSCards(bot))
