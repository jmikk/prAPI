import aiohttp
import random
import xml.etree.ElementTree as ET
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from discord import Embed
import time
import csv
import os
from datetime import datetime

tsv_file = "report.tsv"

class lootbox(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "season": 1,
            "categories": ["common","uncommon", "rare", "ultra-rare","epic"],
            "useragent": "",
            "nationName": "",
            "cooldown": 3600  # Default cooldown is 1 hour
        }
        default_user = {
            "password": "",
            "last_used": 0,
            "uses": 0
        }
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)

    @commands.group()
    async def cardset(self, ctx):
        """Group of commands to set season, categories, user-agent, nationName, and cooldown."""
        pass

    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def season(self, ctx, season: int):
        """Set the season to filter cards."""
        await self.config.season.set(season)
        await ctx.send(f"Season set to {season}")

    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def categories(self, ctx, *categories: str):
        """Set the categories to filter cards."""
        categories = [category.upper() for category in categories]
        await self.config.categories.set(categories)
        await ctx.send(f"Categories set to {', '.join(categories)}")

    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def useragent(self, ctx, *, useragent: str):
        """Set the User-Agent header for the requests."""
        await self.config.useragent.set(useragent)
        await ctx.send(f"User-Agent set to {useragent}")
    
    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def nationname(self, ctx, *, nationname: str):
        """Set the nationName for the loot box prizes."""
        await self.config.nationName.set(nationname)
        await ctx.send(f"Nation Name set to {nationname}")

    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def cooldown(self, ctx, cooldown: int):
        """Set the cooldown period for the loot box command in seconds."""
        await self.config.cooldown.set(cooldown)
        await ctx.send(f"Cooldown set to {cooldown} seconds")

    @commands.dm_only()
    @cardset.command()
    async def password(self, ctx, *, password: str):
        """Set the password for the loot box prizes in DM."""
        await self.config.user(ctx.author).password.set(password)
        await ctx.send(f"Password set to {password}")

    @commands.command()
    async def openlootbox(self, ctx, recipient: str):
        """Open a loot box and fetch a random card for the specified nation."""
        season = await self.config.season()
        nationname = await self.config.nationName()
        categories = await self.config.categories()
        useragent = await self.config.useragent()
        cooldown = await self.config.cooldown()

        now = ctx.message.created_at.timestamp()
        user_data = await self.config.user(ctx.author).all()
        last_used = user_data["last_used"]
        uses = user_data["uses"]

        if now - last_used < cooldown:
            # Check role limits
            max_uses = 1
            if ctx.guild:
                member = ctx.guild.get_member(ctx.author.id)
                if member:
                    if 1098646004250726420 in [role.id for role in member.roles]:
                        max_uses = 2
                    if 1098673767858843648 in [role.id for role in member.roles]:
                        max_uses = 3
            if uses >= max_uses:
                remaining_time = cooldown - (now - last_used)
                timestamp = int(time.time() + remaining_time)
                await ctx.send(f"Please wait until <t:{timestamp}:R> before opening another loot box.")
                return
        else:
            # Reset uses after cooldown
            uses = 0

        # Update user's last used time and uses
        await self.config.user(ctx.author).last_used.set(now)
        await self.config.user(ctx.author).uses.set(uses + 1)

        headers = {"User-Agent": useragent}
        password = await self.config.user(ctx.author).password()

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

                # Fetch card details
                async with session.get(
                    f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={random_card['id']};season={random_card['season']}"
                ) as card_info_response:
                    if card_info_response.status != 200:
                        await ctx.send("Failed to fetch card details from NationStates API.")
                        return

                    card_info_data = await card_info_response.text()
                    card_info = self.parse_card_info(card_info_data)

                    embed_color = self.get_embed_color(random_card['category'])
                    embed = Embed(title="Loot Box Opened!", description="You received a card!", color=embed_color)
                    embed.add_field(name="Card Name", value=card_info['name'], inline=True)
                    embed.add_field(name="Card ID", value=random_card['id'], inline=True)
                    embed.add_field(name="Season", value=random_card['season'], inline=True)
                    embed.add_field(name="Market Value", value=card_info['market_value'], inline=True)
                    await ctx.send(embed=embed)

                # Prepare the gift
                prepare_data = {
                    "nation": nationname,
                    "c": "giftcard",
                    "cardid": random_card['id'],
                    "season": random_card['season'],
                    "to": recipient,
                    "mode": "prepare"
                }
                prepare_headers = {
                    "User-Agent": useragent,
                    "X-Password": password
                }

                async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
                    if prepare_response.status != 200:
                        await ctx.send("Failed to prepare the gift.")
                        return

                    prepare_response_data = await prepare_response.text()
                    token = self.parse_token(prepare_response_data)
                    x_pin = prepare_response.headers.get("X-Pin")

                    if not token or not x_pin:
                        await ctx.send("Failed to retrieve the token or X-Pin for gift execution.")
                        return

                    # Execute the gift
                    execute_data = {
                        "nation": nationname,
                        "c": "giftcard",
                        "cardid": random_card['id'],
                        "season": random_card['season'],
                        "to": recipient,
                        "mode": "execute",
                        "token": token
                    }
                    execute_headers = {
                        "User-Agent": useragent,
                        "X-Pin": x_pin
                    }

                    async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
                        if execute_response.status == 200:
                            await self.add_to_tsv(recipient, random_card['id'], random_card['season'], card_info['market_value'])
                            await ctx.send(f"Successfully gifted the card to {recipient}!")
                        else:
                            await ctx.send("Failed to execute the gift.")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def resetrequests(self, ctx, user: commands.UserConverter):
        """Reset a user's requests, allowing them to open more loot boxes."""
        await self.config.user(user).last_used.set(0)
        await self.config.user(user).uses.set(0)
        await ctx.send(f"{user.display_name}'s requests have been reset.")

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

    def parse_card_info(self, xml_data):
        root = ET.fromstring(xml_data)
        return {
            "name": root.find("NAME").text,
            "market_value": root.find("MARKET_VALUE").text
        }

    def parse_token(self, xml_data):
        root = ET.fromstring(xml_data)
        token = root.find("SUCCESS")
        return token.text if token is not None else None

    def get_embed_color(self, category):
        colors = {
            "COMMON": 0x808080,       # Grey
            "UNCOMMON": 0x00FF00,     # Green
            "RARE": 0x0000FF,         # Blue
            "ULTRA-RARE": 0x800080,   # Purple
            "EPIC": 0xFFA500,         # Orange
            "LEGENDARY": 0xFFFF00     # Yellow
        }
        return colors.get(category.upper(), 0xFFFFFF)  # Default to white if not found

    async def add_to_tsv(self, destination, card_id, season, MV):
        # Append to the TSV file
        with open(tsv_file, 'a', newline='') as file:
            writer = csv.writer(file, delimiter='\t')
            writer.writerow([destination, card_id, season, datetime.now().strftime('%Y-%m-%d'), MV])

def setup(bot):
    bot.add_cog(Lootbox(bot))
