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

def dynamic_cooldown(ctx):
    user_roles = [role.id for role in ctx.author.roles]

    # Default cooldown: 1 use per week (7 days)
    cooldown_period = 7 * 24 * 3600  # 7 days in seconds
    rate = 1

    # Adjust cooldown based on roles
    if 1098646004250726420 in user_roles:  # Role A
        rate = 2
    if 1098673767858843648 in user_roles:  # Role B
        rate = 3

    return Cooldown(rate=rate, per=cooldown_period)

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
                await handle_rate_limit(response)
                if response.status != 200:
                    await ctx.send(f"Failed to fetch card info. Status code: {response.status}")
                    return
                xml_content = await response.text()
                await ctx.send("Parsing card info...")
                card_info = await self.parse_card_info(ctx, xml_content)
                if card_info:
                    await ctx.send(embed=card_info)
                else:
                    await ctx.send("Failed to parse card info.")
                    await ctx.send(f"Raw XML content:\n```xml\n{xml_content}\n```")

    async def parse_card_info(self, ctx, xml_content):
        
        try:
            xml_list = xml_content.split("\n")
            xml_list = xml_list[:-1]
            for each in xml_list:
                await ctx.send(each)
                if each.startswith("<CARDID>"):
                    each = each.replace("</CARDID>","")
                    each = each.replace("<CARDID>","")
                    card_id = each
                if each.startswith("<CATEGORY>"):
                    each = each.replace("</CATEGORY>","")
                    each = each.replace("<CATEGORY>","")
                    category = each
                if each.startswith("<FLAG>"):
                    each = each.replace("</FLAG>","")
                    each = each.replace("<FLAG>","")
                    flag = each
                if each.startswith("<MARKET_VALUE>"):
                    each = each.replace("</MARKET_VALUE>","")
                    each = each.replace("<MARKET_VALUE>","")
                    market_value = each
                if each.startswith("<NAME>"):
                    each = each.replace("</NAME>","")
                    each = each.replace("<NAME>","")
                    name = each
                if each.startswith("<SEASON>"):
                    each = each.replace("</SEASON>","")
                    each = each.replace("<SEASON>","")
                    season = each
                if each.startswith("</CARD>"):
                    break


            # Create an embed with the card details
            embed = discord.Embed(title=f"Card Info: {name}", color=discord.Color.blue())
            embed.add_field(name="Card ID", value=card_id, inline=True)
            embed.add_field(name="Category", value=category, inline=True)
            embed.add_field(name="Market Value", value=market_value, inline=True)
            embed.add_field(name="Season", value=season, inline=True)
            embed.set_thumbnail(url=f"https://www.nationstates.net/{flag}")

            return embed
        except ET.ParseError as e:
            await ctx.send(f"Error parsing XML: {e}")
            return None

    @my_command.error
    async def my_command_error(self, ctx, error):
        if isinstance(error, CommandOnCooldown):
            retry_after = int(error.retry_after)
            timestamp = int(time.time() + retry_after)
            cooldown_message = f"You can use this command again <t:{timestamp}:R>."
            await ctx.send(cooldown_message)
        else:
            await ctx.send(error)

def setup(bot):
    bot.add_cog(sheets(bot))
