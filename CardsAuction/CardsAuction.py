import discord
from discord.ext import commands
from discord.ui import View, Button
import aiohttp
import xml.etree.ElementTree as ET
import asyncio
from redbot.core import commands, Config

class CardsAuction(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = commands.Config.get_conf(self, identifier=1234567890)
        default_global = {"ua": None}
        self.config.register_global(**default_global)
        self.cooldown = commands.CooldownMapping.from_cooldown(1, 300, commands.BucketType.user)  # 5 minute cooldown

        self.valid_filters = ["legendary", "epic", "ultra-rare", "rare", "uncommon", "common"] + [f"s{i}" for i in range(1, 10)]

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def setua(self, ctx, *, user_agent: str):
        """Set the User-Agent (UA) to use for NationStates API requests."""
        await self.config.ua.set(user_agent)
        await ctx.reply("✅ User-Agent has been set.")

    @commands.hybrid_command()
    async def auctions(self, ctx, *filters: str):
        """Fetch and display the current cards auctions. Supports filters like legendary epic s2 s3 etc."""

        bucket = self.cooldown.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return await ctx.reply(f"⏳ You're on cooldown. Try again in {round(retry_after)} seconds.")

        ua = await self.config.ua()
        if not ua:
            return await ctx.reply("❌ User-Agent not set. Please set it with `setua`.")

        url = "https://www.nationstates.net/cgi-bin/api.cgi?q=cards+auctions"
        headers = {"User-Agent": ua}

        await ctx.defer()

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return await ctx.reply(f"❌ API request failed with status {response.status}")
                data = await response.text()

        root = ET.fromstring(data)
        auctions = []

        filter_categories = {"legendary": "legendary", "epic": "epic", "ultra-rare": "ultra-rare",
                            "rare": "rare", "uncommon": "uncommon", "common": "common"}

        filter_seasons = set()
        filter_types = set()

        for f in filters:
            if f.lower() in filter_categories:
                filter_types.add(filter_categories[f.lower()])
            elif f.lower().startswith("s") and f[1:].isdigit():
                filter_seasons.add(f[1:])

        for auction in root.findall("AUCTIONS/AUCTION"):
            cardid = auction.find("CARDID").text
            name = auction.find("NAME").text
            category = auction.find("CATEGORY").text
            season = auction.find("SEASON").text

            if (not filter_types or category.lower() in filter_types) and (not filter_seasons or season in filter_seasons):
                auctions.append((cardid, name, category, season))

        if not auctions:
            return await ctx.reply("❌ No auctions found with the given filters.")

        pages = []
        chunk_size = 10

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

        class AuctionView(View):
            def __init__(self, pages):
                super().__init__(timeout=60)
                self.pages = pages
                self.index = 0

            @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
            async def previous(self, interaction: discord.Interaction, button: Button):
                if self.index > 0:
                    self.index -= 1
                    await interaction.response.edit_message(embed=self.pages[self.index], view=self)

            @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
            async def next(self, interaction: discord.Interaction, button: Button):
                if self.index < len(self.pages) - 1:
                    self.index += 1
                    await interaction.response.edit_message(embed=self.pages[self.index], view=self)

        await ctx.reply(embed=pages[0], view=AuctionView(pages))

    @auctions.autocomplete("filters")
    async def auctions_autocomplete(self, interaction: discord.Interaction, current: str):
        suggestions = [f for f in self.valid_filters if f.startswith(current.lower())]
        return [discord.app_commands.Choice(name=f, value=f) for f in suggestions[:25]]

async def setup(bot):
    await bot.add_cog(CardsAuction(bot))
