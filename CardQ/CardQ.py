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

                    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
                        tmp_file.write("\n".join(card_list))
                        tmp_file_path = tmp_file.name

                    file = discord.File(tmp_file_path, filename="card_list.csv")

                    # Check if deck= parameter is provided
                    if "deck=" in params:
                        deck_name = params.split("deck=")[1].strip()
                        deck_data = await self.get_user_deck_data(deck_name)
                        deck_ids = self.extract_card_ids_from_deck(deck_data)

                        # Filter the card list based on the user's deck
                        filtered_card_list = [card for card in card_list if card.split(",")[0] in deck_ids]

                        with tempfile.NamedTemporaryFile(mode="w", delete=False) as filtered_tmp_file:
                            filtered_tmp_file.write("\n".join(filtered_card_list))
                            filtered_tmp_file_path = filtered_tmp_file.name

                        filtered_file = discord.File(filtered_tmp_file_path, filename="filtered_card_list.csv")
                        await ctx.send(f"Card IDs in {deck_name}'s deck: {', '.join(deck_ids)}", file=filtered_file)

                    elif "!deck=" in params:
                        deck_name = params.split("!deck=")[1].strip()
                        deck_data = await self.get_user_deck_data(deck_name)
                        deck_ids = self.extract_card_ids_from_deck(deck_data)

                        # Filter the card list based on the user's deck
                        filtered_card_list = [card for card in card_list if card.split(",")[0] not in deck_ids]

                        with tempfile.NamedTemporaryFile(mode="w", delete=False) as filtered_tmp_file:
                            filtered_tmp_file.write("\n".join(filtered_card_list))
                            filtered_tmp_file_path = filtered_tmp_file.name

                        filtered_file = discord.File(filtered_tmp_file_path, filename="filtered_card_list.csv")
                        await ctx.send(f"Card IDs not in {deck_name}'s deck: {', '.join(deck_ids)}", file=filtered_file)

                    else:
                        await ctx.send(f"{ctx.author.mention} Enjoy! I dug it from the salt mine just for you!", file=file)

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
    
        def extract_card_ids_from_deck(self, deck_data):
            deck_ids = []
            if deck_data:
                root = ET.fromstring(deck_data)
                cards = root.findall("./DECK/CARD")
                for card in cards:
                    card_id = card.find("CARDID").text
                    deck_ids.append(card_id)
            return deck_ids
