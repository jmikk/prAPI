import aiohttp
import random
import xml.etree.ElementTree as ET
from redbot.core import commands, Config


class NationStatesCards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "season": 1,
            "categories": ["common", "rare", "ultra-rare"],
            "useragent": "9006",
        }
        self.config.register_global(**default_global)

    @commands.group()
    async def cardset(self, ctx):
        """Group of commands to set season, categories, and user-agent."""
        pass

    @cardset.command()
    async def season(self, ctx, season: int):
        """Set the season to filter cards."""
        await self.config.season.set(season)
        await ctx.send(f"Season set to {season}")

    @cardset.command()
    async def categories(self, ctx, *categories: str):
        """Set the categories to filter cards."""
        await self.config.categories.set(categories)
        await ctx.send(f"Categories set to {', '.join(categories)}")

    @cardset.command()
    async def useragent(self, ctx, *, useragent: str):
        """Set the User-Agent header for the requests."""
        await self.config.useragent.set(useragent)
        await ctx.send(f"User-Agent set to {useragent}")

    @commands.command()
    async def getcard(self, ctx, nationname: str):
        """Fetch a random card from the specified nation's deck based on season and category."""
        season = await self.config.season()
        categories = await self.config.categories()
        useragent = await self.config.useragent()

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
    bot.add_cog(NationStatesCards(bot))