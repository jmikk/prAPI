import discord
from redbot.core import commands
import aiohttp
import tempfile

class CardQ(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.cooldown(1, 60, commands.BucketType.user)
    @commands.command()
    async def search_cards(self, ctx, season: int, *search_params):
        await ctx.send("Searching for that, if you need help check out my documation here https://api.nsupc.dev/cards/v1")
        base_url = "https://api.nsupc.dev/cards/v1"
        params="&".join(search_params)
        await ctx.send(params)
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
                    await ctx.send( f"{ctx.author.mention} Enjoy I dug it from the salt mine just for you!",file=file)
                else:
                    # Send the raw data to the user
                    await ctx.send(data)
                    

