import discord
from discord.ext import commands
import aiohttp
import xml.etree.ElementTree as ET

class CardsAuction(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- CONFIG COMMAND ---
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setua(self, ctx, *, user_agent: str):
        """Set the User-Agent (UA) to use for NationStates API requests."""
        await self.bot.db.set_raw("cardsauction", "ua", value=user_agent)
        await ctx.send("✅ User-Agent has been set.")

    # --- FETCH & DISPLAY COMMAND ---
    @commands.command()
    async def auctions(self, ctx):
        """Fetch and display the current cards auctions."""

        ua = await self.bot.db.get_raw("cardsauction", "ua", default=None)
        if not ua:
            return await ctx.send("❌ User-Agent not set. Please set it with `setua`.")

        url = "https://www.nationstates.net/cgi-bin/api.cgi?q=cards+auctions"

        headers = {"User-Agent": ua}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return await ctx.send(f"❌ API request failed with status {response.status}")
                data = await response.text()

        # Parse XML
        root = ET.fromstring(data)
        auctions = []

        for auction in root.findall("AUCTIONS/AUCTION"):
            cardid = auction.find("CARDID").text
            name = auction.find("NAME").text
            category = auction.find("CATEGORY").text
            season = auction.find("SEASON").text
            auctions.append((cardid, name, category, season))

        if not auctions:
            return await ctx.send("❌ No auctions found.")

        # --- PAGINATED DISPLAY ---

        pages = []
        chunk_size = 10  # 10 auctions per page

        for i in range(0, len(auctions), chunk_size):
            chunk = auctions[i:i+chunk_size]
            embed = discord.Embed(
                title="Current Card Auctions",
                color=discord.Color.blurple()
            )
            for cardid, name, category, season in chunk:
                embed.add_field(
                    name=f"{name} (Season {season})",
                    value=f"Card ID: {cardid} | Category: {category}",
                    inline=False
                )
            embed.set_footer(text=f"Page {i // chunk_size + 1} of {len(auctions) // chunk_size + 1}")
            pages.append(embed)

        # Simple paginator
        current = 0
        message = await ctx.send(embed=pages[current])

        if len(pages) == 1:
            return

        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["◀️", "▶️"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

                if str(reaction.emoji) == "▶️" and current < len(pages) - 1:
                    current += 1
                    await message.edit(embed=pages[current])
                    await message.remove_reaction(reaction, user)
                elif str(reaction.emoji) == "◀️" and current > 0:
                    current -= 1
                    await message.edit(embed=pages[current])
                    await message.remove_reaction(reaction, user)
            except Exception:
                break
