import aiohttp
import xml.etree.ElementTree as ET
from redbot.core import commands
from redbot.core.commands import BucketType, Cooldown, CommandOnCooldown
import discord
import time
import asyncio
import csv
import os
from datetime import datetime


tsv_file = "report.tsv"
nation_password = None  # Global variable to store the nation password

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
    async def my_command(self, ctx, card_id: int, destination: str):
        user_agent = "9003"
        headers = {"User-Agent": user_agent}
        global nation_password
        if not nation_password:
            await ctx.send("Please set the nation password using the `set_password` command.")
            return

        await ctx.send("Fetching card info...")
        # Fetch card info from the NationStates API
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={card_id};season=3"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"User-Agent": user_agent}) as response:
                await handle_rate_limit(response)
                if response.status != 200:
                    await ctx.send(f"Failed to fetch card info. Status code: {response.status}")
                    return
                xml_content = await response.text()
                await ctx.send("Parsing card info...")
                card_info = await self.parse_card_info(ctx, xml_content)
                if card_info:
                    await ctx.send(embed=card_info)
                    await self.add_to_tsv(destination, card_id, 3)

                    # Gifting the card
                    nation = "testlandia"  # Assuming the nation is "testlandia", adjust as necessary
                    season = 1
                    headers["X-Password"] = nation_password
                    prepare_data = {
                        "nation": nation,
                        "c": "giftcard",
                        "cardid": card_id,
                        "season": season,
                        "to": destination,
                        "mode": "prepare"
                    }

                    async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", headers=headers, data=prepare_data) as response:
                        await handle_rate_limit(response)
                        if response.status != 200:
                            await ctx.send(f"Failed to prepare gift. Status code: {response.status} {await response.text()}")
                            return

                        response_text = await response.text()
                        # Extract token from the response
                        token_start = response_text.find("<SUCCESS>") + len("<SUCCESS>")
                        token_end = response_text.find("</SUCCESS>")
                        token = response_text[token_start:token_end].strip()

                        # Extract pin from headers
                        x_pin = response.headers.get("X-Pin")
                        if not token or not x_pin:
                            await ctx.send("Failed to retrieve token or pin.")
                            return

                        # Execute the gift
                        headers["X-Pin"] = x_pin
                        del headers["X-Password"]  # Remove X-Password for security
                        execute_data = {
                            "nation": nation,
                            "c": "giftcard",
                            "cardid": card_id,
                            "season": season,
                            "to": destination,
                            "mode": "execute",
                            "token": token
                        }

                        async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", headers=headers, data=execute_data) as response:
                            await handle_rate_limit(response)
                            if response.status != 200:
                                await ctx.send(f"Failed to execute gift. Status code: {response.status}")
                                return

                            await ctx.send(f"Successfully gifted card {card_id} to {destination}!")
                else:
                    await ctx.send("Failed to parse card info.")
                    await ctx.send(f"Raw XML content:\n```xml\n{xml_content}\n```")

    async def parse_card_info(self, ctx, xml_content):
        try:
            xml_list = xml_content.split("\n")
            xml_list = xml_list[:-1]
            card_data = {}
            for each in xml_list:
                if each.startswith("<CARDID>"):
                    card_data['card_id'] = each.replace("</CARDID>", "").replace("<CARDID>", "")
                if each.startswith("<CATEGORY>"):
                    card_data['category'] = each.replace("</CATEGORY>", "").replace("<CATEGORY>", "")
                if each.startswith("<FLAG>"):
                    card_data['flag'] = each.replace("</FLAG>", "").replace("<FLAG>", "")
                if each.startswith("<MARKET_VALUE>"):
                    card_data['market_value'] = each.replace("</MARKET_VALUE>", "").replace("<MARKET_VALUE>", "")
                if each.startswith("<NAME>"):
                    card_data['name'] = each.replace("</NAME>", "").replace("<NAME>", "")
                if each.startswith("<SEASON>"):
                    card_data['season'] = each.replace("</SEASON>", "").replace("<SEASON>", "")
                if each.startswith("</CARD>"):
                    break

            # Create an embed with the card details
            embed = discord.Embed(title=f"{card_data['name']}", color=discord.Color.blue())
            embed.add_field(name="Card ID", value=card_data['card_id'], inline=True)
            embed.add_field(name="Category", value=card_data['category'], inline=True)
            embed.add_field(name="Market Value", value=card_data['market_value'], inline=True)
            embed.add_field(name="Season", value=card_data['season'], inline=True)
            embed.set_thumbnail(url=f"https://www.nationstates.net/images/cards/s3/{card_data['flag']}")

            return embed
        except ET.ParseError as e:
            await ctx.send(f"Error parsing XML: {e}")
            return None

    async def add_to_tsv(self, destination, card_id, season):
        # Append to the TSV file
        with open(tsv_file, 'a', newline='') as file:
            writer = csv.writer(file, delimiter='\t')
            writer.writerow([destination, card_id, season, datetime.now().strftime('%Y-%m-%d')])

    @commands.command()
    async def view_report(self, ctx):
        # Read and send the contents of the TSV file
        if not os.path.exists(tsv_file) or os.path.getsize(tsv_file) == 0:
            await ctx.send("The report file is empty.")
            return

        with open(tsv_file, 'r') as file:
            content = file.read()
            await ctx.send(f"```\n{content}\n```")

    @commands.command()
    async def clear_report(self, ctx):
        # Clear the contents of the TSV file
        open(tsv_file, 'w').close()
        await ctx.send("The report file has been cleared.")

    @commands.command()
    async def set_password(self, ctx, password: str):
        global nation_password
        nation_password = password
        await ctx.send("Nation password has been set.")

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
