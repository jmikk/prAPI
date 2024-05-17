import aiohttp
import xml.etree.ElementTree as ET
from redbot.core import commands
from redbot.core.commands import BucketType, Cooldown, CommandOnCooldown
import discord
import time
import asyncio

user_agent = "9003"
headers = {"User-Agent": user_agent}

async def handle_rate_limit(response):
    remaining = int(response.headers.get("Ratelimit-Remaining", 10))
    reset_time = int(response.headers.get("Ratelimit-Reset", 30))

    if remaining < 20:  # Threshold for remaining requests
        wait_time = reset_time / max(remaining, 1)
        print(f"Rate limit nearly reached. Sleeping for {wait_time} seconds...")
        await asyncio.sleep(wait_time)

class sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.dynamic_cooldown(dynamic_cooldown, type=BucketType.user)
    @commands.command()
    async def my_command(self, ctx, card_id: int):
        await ctx.send("Fetching card info...")
        # Fetch card info from the NationStates API
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={card_id};season=3"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                # Debug statement to print response text
                # await ctx.send(await response.text())
                if response.status != 200:
                    await ctx.send(f"Failed to fetch card info. Status code: {response.status}")
                    return
                xml_content = await response.text()
                await ctx.send("Parsing card info...")
                card_info = self.parse_card_info(xml_content)
                if card_info:
                    await ctx.send(embed=card_info)
                else:
                    await ctx.send("Failed to parse card info.")

    def parse_card_info(self, xml_content):
        try:
            root = ET.fromstring(xml_content)
            card = root.find('CARD')
            if card is None:
                return None

            # Extract card details
            card_id = card.find('CARDID').text
            category = card.find('CATEGORY').text
            flag = card.find('FLAG').text
            market_value = card.find('MARKET_VALUE').text
            name = card.find('NAME').text
            season = card.find('SEASON').text

            # Create an embed with the card details
            embed = discord.Embed(title=f"Card Info: {name}", color=discord.Color.blue())
            embed.add_field(name="Card ID", value=card_id, inline=True)
            embed.add_field(name="Category", value=category, inline=True)
            embed.add_field(name="Market Value", value=market_value, inline=True)
            embed.add_field(name="Season", value=season, inline=True)
            embed.set_thumbnail(url=f"https://www.nationstates.net/{flag}")

            return embed
        except ET.ParseError as e:
            print(f"Error parsing XML: {e}")
            return None

    @my_command.error
    async def my_command_error(self, ctx, error):
        if isinstance(error, CommandOnCooldown):
            retry_after = int(error.retry_after)
            timestamp = int(time.time() + retry_after)
            cooldown_message = f"You can use this command again <t:{timestamp}:R>."
            await ctx.send(cooldown_message)
        else:
            raise error

def setup(bot):
    bot.add_cog(sheets(bot))
