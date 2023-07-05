import discord
from redbot.core import commands
import aiohttp
import tempfile
import xml.etree.ElementTree as ET

class CardQ(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.cooldown(1, 60, commands.BucketType.user)
    @commands.command()
    async def search_cards(self, ctx, season: int, *search_params):
        await ctx.send("Searching for that, if you need help check out my documentation here https://api.nsupc.dev/cards/v1")
        base_url = "https://api.nsupc.dev/cards/v1"
        params = "&".join(search_params)
        query_params = f"season={season}&{params}"
        search_url = f"{base_url}?{query_params}"
        await ctx.send(search_url)

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url) as response:
                data = await response.json()
                status = data.get("status")
                if status == "success":
                    # Process the response data as needed
                    card_list = []
                    for card_id, card_name in data["nations"].items():
                        card_link = f"www.nationstates.net/page=deck/card={card_id}/season={season}"
                        card_list.append(f"{card_id},{card_name},{card_link}")

                    # Check if deck= parameter is provided
                    if "deck=" in params:
                        deck_name = params.split("deck=")[1].strip()
                        deck_data = await self.get_user_deck_data(deck_name)
                        filtered_card_list = self.filter_card_list(card_list, deck_data, include=True)
                        await self.send_card_list(ctx, filtered_card_list, deck_name)
                    elif "!deck=" in params:
                        deck_name = params.split("!deck=")[1].strip()
                        deck_data = await self.get_user_deck_data(deck_name)
                        filtered_card_list = self.filter_card_list(card_list, deck_data, include=False)
                        await self.send_card_list(ctx, filtered_card_list, deck_name)
                    else:
                        await self.send_card_list(ctx, card_list, None)

                else:
                    # Send the raw data to the user
                    await ctx.send(data)

    async def get_user_deck_data(self, deck_name):
        headers = {
            "User-Agent": "9006"
        }
        params = {
            "q": f"cards+deck;nationname={deck_name}"
        }
        api_url = "https://www.nationstates.net/cgi-bin/api.cgi"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params, headers=headers) as response:
                deck_data = await response.text()
                return deck_data

    def filter_card_list(self, card_list, deck_data, include=True):
        deck_ids = self.extract_card_ids_from_deck(deck_data)
        filtered_list = []
        for card in card_list:
            card_id = card.split(",")[0]
            if (card_id in deck_ids and include) or (card_id not in deck_ids and not include):
                filtered_list.append(card)
        return filtered_list

    async def send_card_list(self, ctx, card_list, deck_name):
        if len(card_list) > 0:
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
                tmp_file.write("\n".join(card_list))
                tmp_file_path = tmp_file.name

            file = discord.File(tmp_file_path, filename="card
