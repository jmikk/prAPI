import discord
import aiohttp
import asyncio
import random
import time
import xml.etree.ElementTree as ET
from redbot.core import commands

class CardPaginator(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=60)
        self.pages = pages
        self.current_page = 0

    async def update_page(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.pages)
        await self.update_page(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.pages)
        await self.update_page(interaction)

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
    """NationStates Card Poker with Buttons."""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.headers = {"User-Agent": "RedBot Cog - CardPokerButtons v8.0 - Used by [YourNation]"}
        self.throttler = NSThrottler()
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
            return ET.fromstring(await response.text())

    @commands.command()
    async def draw(self, ctx):
        """Draw a poker hand from 9005 using Buttons."""
        async with ctx.typing():
            deck_url = "https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname=9005"
            root = await self.fetch_xml(deck_url)
            
            if root is None or not root.findall(".//CARD"):
                return await ctx.send("Could not access deck 9005.")

            sampled = random.sample(root.findall(".//CARD"), 5)
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
                link = f"https://www.nationstates.net/page=deck/card={cid}/season={season}"
                
                overview_lines.append(f"{i}. {data['e']} **[{name}]({link})** ({cat.capitalize()})")

                embed = discord.Embed(title=f"{name} (S{season})", url=link, color=data['c'])
                embed.set_thumbnail(url=f"https://www.nationstates.net/images/cards/s{season}/{flag_path}")
                embed.set_image(url=f"https://www.nationstates.net/images/cards/s{season}/{cid}.jpg")
                embed.add_field(name="Category", value=f"{data['e']} {cat.capitalize()}", inline=True)
                embed.add_field(name="MV", value=f"🪙 {mv}", inline=True)
                embed.add_field(name="Owners", value=f"👥 {owners}", inline=True)
                embed.set_footer(text=f"Card {i}/5 | Limit: {self.throttler.remaining}")
                card_pages.append(embed)

            overview_embed = discord.Embed(
                title="🎴 Your Poker Hand - Nation 9005",
                description="\n".join(overview_lines),
                color=0x2f3136
            )
            overview_embed.set_footer(text="Legend: ⚪C 🟢U 🔵R 🟣UR 🟠E 🟡L")
            
            final_pages = [overview_embed] + card_pages
            view = CardPaginator(final_pages)
            await ctx.send(embed=final_pages[0], view=view)

async def setup(bot):
    await bot.add_cog(NSCards(bot))
