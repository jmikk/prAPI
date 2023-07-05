import discord
from redbot.core import commands
import aiohttp
import tempfile

class CardQ(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def search_cards(self, ctx, season: int, *, search_params):
        base_url = "https://api.nsupc.dev/cards/v1"
        query_params = f"season={season}&{search_params}"
        search_url = f"{base_url}?{query_params}"

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url) as response:
                data = await response.json()
                # Process the response data as needed
        
        # Generating the card list in the desired format
        card_list = []
        for card_id, card_name in data["nations"].items():
            card_link = f"www.nationstates.net/page=deck/card={card_id}/season={season}"
            card_list.append(f"{card_id},{card_name},{card_link}")
        
        # Creating a temporary file and writing the content to it
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            tmp_file.write("\n".join(card_list))
            tmp_file_path = tmp_file.name
        
        # Creating and sending the file
        file = discord.File(tmp_file_path, filename="card_list.csv")
        await ctx.send(file=file)

def setup(bot):
    bot.add_cog(CardSearch(bot))
