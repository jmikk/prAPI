import aiohttp
import random
import xml.etree.ElementTree as ET
from redbot.core import commands, Config
from redbot.core.bot import Red

class lootbox(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "season": 1,
            "categories": ["common", "rare", "ultra-rare"],
            "useragent": "",
            "nationName": ""
        }
        default_user = {
            "password": ""
        }
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)

    @commands.group()
    async def cardset(self, ctx):
        """Group of commands to set season, categories, user-agent, and nationName."""
        pass

    @cardset.command()
    async def season(self, ctx, season: int):
        """Set the season to filter cards."""
        await self.config.season.set(season)
        await ctx.send(f"Season set to {season}")

    @cardset.command()
    async def categories(self, ctx, *categories: str):
        """Set the categories to filter cards."""
        categories=categories.upper()
        await self.config.categories.set(categories)
        await ctx.send(f"Categories set to {', '.join(categories)}")

    @cardset.command()
    async def useragent(self, ctx, *, useragent: str):
        """Set the User-Agent header for the requests."""
        await self.config.useragent.set(useragent)
        await ctx.send(f"User-Agent set to {useragent}")
    
    @cardset.command()
    async def nationname(self, ctx, *, nationname: str):
        """Set the nationName for the loot box prizes."""
        await self.config.nationName.set(nationname)
        await ctx.send(f"Nation Name set to {nationname}")

    @commands.dm_only()
    @cardset.command()
    async def password(self, ctx, *, password: str):
        """Set the password for the loot box prizes in DM."""
        await self.config.user(ctx.author).password.set(password)
        await ctx.send(f"Password set to {password}")

    @commands.command()
    async def getcard(self, ctx):
        """Fetch a random card from the specified nation's deck based on season and category."""
        season = await self.config.season()
        if not season:
            await ctx.send("Please set a password with cardset season {season}.")
            return
        nationname = await self.config.nationName()
        if not nationname:
            await ctx.send("Please set a nationname with cardset nationname {nationname}.")
            return
        password = await self.config.user(ctx.author).password()
        if not password:
            await ctx.send("Please set a password with cardset password {password}.")
            return
        categories = await self.config.categories()
        if not categories:
            await ctx.send("Please set a password with cardset categories {categories}.")
            return
        useragent = await self.config.useragent()
        if not useragent:
            await ctx.send("Please set a password with cardset useragent {useragent}")
            return
        

        headers = {"User-Agent": useragent}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname={nationname}"
            ) as response:
                if response.status != 200:
                    await ctx.send("Failed to fetch data from NationStates API.")
                    return

                data = await response.text()
                cards = self.parse_cards(data, season, categories)

                if not cards:
                    await ctx.send(
                        f"No cards found for season {season} in categories {', '.join(categories)}"
                    )
                    return

                random_card = random.choice(cards)
                card_info = f"ID: {random_card['id']}, Season: {random_card['season']}, Category: {random_card['category']}"
                await ctx.send(card_info)

    def parse_cards(self, xml_data, season, categories):
        root = ET.fromstring(xml_data)
        cards = []
        for card in root.findall(".//CARD"):
            card_season = int(card.find("SEASON").text)
            card_category = card.find("CATEGORY").text
            if card_season == season and card_category in categories:
                card_id = card.find("CARDID").text
                cards.append(
                    {"id": card_id, "season": card_season, "category": card_category}
                )
        return cards


def setup(bot):
    bot.add_cog(Lootbox(bot))
