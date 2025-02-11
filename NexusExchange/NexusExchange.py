import discord
from redbot.core import commands, Config, checks
import aiohttp
import random
import xml.etree.ElementTree as ET
from discord import Embed
import time
import csv
import os
from datetime import datetime

class NexusExchange(commands.Cog):
    """A Master Currency Exchange Cog for The Wellspring"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=True)
        self.config.register_guild(
            master_currency_name="wellcoin",
            exchange_rates={},  # {"currency_name": {"config_id": int, "rate": float}}
        )
        self.config.register_user(master_balance=0)

            # Lootbox configuration
        self.config.register_global(
            season=[3,4],
            categories=["common", "uncommon", "rare", "ultra-rare", "epic"],
            useragent="",
            nationName="",
            password="",
        )


    @commands.group(name="shop")
    async def shop(self, ctx):
        """Master command for the shop."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(title="🛒 Shop Inventory", color=discord.Color.blue())
            
            embed.add_field(name="Loot box", value=f"💰 `10 Coins`\n📜", inline=False)

            await ctx.send(embed=embed)

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def set_nation(self, ctx, *, nationname: str):
        """Set the nation name for the loot box prizes."""
        await self.config.nationName.set(nationname)
        await ctx.send(f"Nation Name set to {nationname}")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def set_password(self, ctx, *, password: str):
        """Set the password for the loot box prizes."""
        await self.config.password.set(password)
        await ctx.send("Password has been set successfully.")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def useragent(self, ctx, *, useragent: str):
        """Set the User-Agent header for the requests."""
        await self.config.useragent.set(useragent)
        await ctx.send(f"User-Agent set to {useragent}")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def season(self, ctx, *seasons: str):
        """Set the season to filter cards."""
        seasons = [season for season in seasons]
        await self.config.season.set(seasons)
        await ctx.send(f"Season's set to {seasons}")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def categories(self, ctx, *categories: str):
        """Set the categories to filter cards."""
        categories = [category for category in categories]
        await self.config.categories.set(categories)
        await ctx.send(f"Categories set to {', '.join(categories)}")

    @shop.command()
    @commands.admin()
    @commands.cooldown(1, 60, commands.BucketType.default)  # 1 use per 60 seconds
    async def buy_lootbox(self, ctx, *recipient: str):
        """Open a loot box and fetch a random card for the specified nation."""
        await ctx.send("You bought a lootbox woot woot!")

        if len(recipient) < 1:
            await ctx.send("Make sure to put your nation in after openlootbox")
            return


        recipient =  "_".join(recipient)
        season = await self.config.season()
        nationname = await self.config.nationName()
        categories = ["common","uncommon", "rare", "ultra-rare","epic"]
        useragent = await self.config.useragent()

        headers = {"User-Agent": useragent}
        password = await self.config.password()

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
                    await ctx.send(data[:1000])
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
                        if prepare_response.status == 409 or 403:
                            await ctx.send(prepare_response.text)
                            await ctx.send("No loot boxes ready! Give me a minute or so to wrap one up for you.")
                            return       
                        await ctx.send(prepare_response.text)
                        await ctx.send("Failed to prepare the gift.")
                        return

                    prepare_response_data = await prepare_response.text()
                    token = self.parse_token(prepare_response_data)
                    x_pin = prepare_response.headers.get("X-Pin")

                    if not token or not x_pin:
                        await ctx.send(prepare_response_data)
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
                            await ctx.send(embed=embed)

                            await ctx.send(f"Successfully gifted the card to {recipient}!")
                        else:
                            await ctx.send("Failed to execute the gift.")

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def add_to_currency(self, ctx, user: discord.Member, currency_name: str, amount: int):
        """Add a certain amount of a mini-currency to a user's balance."""
        currency_name = currency_name.lower().replace(" ", "_")
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()

        if currency_name not in exchange_rates:
            await ctx.send("This currency does not exist.")
            return

        config_id = exchange_rates[currency_name]["config_id"]
        mini_currency_config = Config.get_conf(None, identifier=config_id, force_registration=True)
        
        # Retrieve user's current balance
        user_balance = await mini_currency_config.user(user).get_raw(currency_name, default=0)
        new_balance = user_balance + amount

        # Update balance
        await mini_currency_config.user(user).set_raw(currency_name, value=new_balance)

        await ctx.send(f"Added `{amount}` `{currency_name}` to {user.mention}. New balance: `{new_balance}`.")

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def add_currency(self, ctx, currency_name: str, config_id: int, rate: float):
        """Add a new mini-currency with its config ID and exchange rate."""
        currency_name = currency_name.lower().replace(" ","_")
        async with self.config.guild(ctx.guild).exchange_rates() as exchange_rates:
            exchange_rates[currency_name] = {"config_id": config_id, "rate": rate}
        await ctx.send(f"Added `{currency_name}` with exchange rate `{rate}` from config `{config_id}`.")

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def remove_currency(self, ctx, currency_name: str):
        """Remove a mini-currency from the exchange list."""
        currency_name = currency_name.lower().replace(" ","_")
        async with self.config.guild(ctx.guild).exchange_rates() as exchange_rates:
            if currency_name not in exchange_rates:
                await ctx.send("This currency does not exist.")
                return
            del exchange_rates[currency_name]
        await ctx.send(f"Removed `{currency_name}` from the exchange list.")

    @commands.guild_only()
    @commands.command()
    async def exchange(self, ctx, currency_name: str, amount: int):
        """Convert a mini-currency into Wellspring Coins."""
        currency_name = currency_name.lower().replace(" ","_")
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()
        
        if currency_name not in exchange_rates:
            await ctx.send("This currency is not available for exchange.")
            return

        config_id = exchange_rates[currency_name]["config_id"]
        rate = exchange_rates[currency_name]["rate"]
        mini_currency_config = Config.get_conf(None, identifier=config_id)
        user_balance = await mini_currency_config.user(ctx.author).get_raw(currency_name, default=0)

        if user_balance < amount:
            await ctx.send("You do not have enough of this currency.")
            return

        new_wellspring_coins = int(amount * rate)
        
        # Deduct from mini-currency
        await mini_currency_config.user(ctx.author).set_raw(currency_name, value=user_balance - amount)
        
        # Add to master currency
        master_balance = await self.config.user(ctx.author).master_balance()
        await self.config.user(ctx.author).master_balance.set(master_balance + new_wellspring_coins)
        
        await ctx.send(f"Exchanged `{amount}` `{currency_name}` for `{new_wellspring_coins}` Wellspring Coins!")

    @commands.guild_only()
    @commands.command()
    async def balance(self, ctx, currency_name: str = None):
        """Check your balance of Wellspring Coins or a specific mini-currency."""
        if currency_name is None:
            balance = await self.config.user(ctx.author).master_balance()
            await ctx.send(f"You have `{balance}` Wellspring Coins.")
        else:
            currency_name = currency_name.lower().replace(" ","_")
            exchange_rates = await self.config.guild(ctx.guild).exchange_rates()

            if currency_name not in exchange_rates:
                await ctx.send("This currency does not exist.")
                return

            config_id = exchange_rates[currency_name]["config_id"]
            mini_currency_config = Config.get_conf(None, identifier=config_id, force_registration=True)
            user_balance = await mini_currency_config.user(ctx.author).get_raw(currency_name, default=0)

            await ctx.send(f"You have `{user_balance}` `{currency_name}`.")

    @commands.guild_only()
    @commands.command()
    async def rates(self, ctx):
        """View current exchange rates."""
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()
        if not exchange_rates:
            await ctx.send("No currencies have been added yet.")
            return
        
        embed = discord.Embed(title="Exchange Rates", color=discord.Color.blue())
        for currency, data in exchange_rates.items():
            embed.add_field(name=currency, value=f"Rate: `{data['rate']}` (Config: `{data['config_id']}`)", inline=False)
        
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def set_rate(self, ctx, currency_name: str, rate: float):
        """Change the exchange rate for a mini-currency."""
        currency_name = currency_name.lower().replace(" ","_")
        async with self.config.guild(ctx.guild).exchange_rates() as exchange_rates:
            if currency_name not in exchange_rates:
                await ctx.send("That currency does not exist.")
                return
            exchange_rates[currency_name]["rate"] = rate
        await ctx.send(f"Updated `{currency_name}` exchange rate to `{rate}`.")

    @commands.guild_only()
    @commands.command()
    async def debug_currency(self, ctx, currency_name: str):
        """Dump everything related to a given currency's config."""
        currency_name = currency_name.lower().replace(" ", "_")
        
        # Check if the currency exists
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()
        if currency_name not in exchange_rates:
            await ctx.send(f"Currency `{currency_name}` does not exist.")
            return
    
        # Retrieve the correct config_id
        config_id = exchange_rates[currency_name]["config_id"]
        mini_currency_config = Config.get_conf(None, identifier=config_id, force_registration=True)
    
        # Retrieve all stored data in this Config space
        try:
            all_data = await mini_currency_config.all()
            all_user_data = await mini_currency_config.all_users()
            all_member_data = await mini_currency_config.all_members()
        except Exception as e:
            await ctx.send(f"Error retrieving data: {e}")
            return
    
        # Format the data for debugging
        embed = discord.Embed(title=f"Debugging `{currency_name}`", color=discord.Color.red())
        embed.add_field(name="Stored Config ID", value=f"`{config_id}`", inline=False)
        
        if all_data:
            embed.add_field(name="Global Config Data", value=f"```{str(all_data)[:1000]}```", inline=False)
        else:
            embed.add_field(name="Global Config Data", value="No data found.", inline=False)
    
        if all_user_data:
            embed.add_field(name="User-Level Data", value=f"```{str(all_user_data)[:1000]}```", inline=False)
        else:
            embed.add_field(name="User-Level Data", value="No user data found.", inline=False)
    
        if all_member_data:
            embed.add_field(name="Member-Level Data", value=f"```{str(all_member_data)[:1000]}```", inline=False)
        else:
            embed.add_field(name="Member-Level Data", value="No member data found.", inline=False)
    
        await ctx.send(embed=embed)


    def parse_cards(self, xml_data, season, categories):
        root = ET.fromstring(xml_data)
        cards = []
        for card in root.findall(".//CARD"):
            card_season = int(card.find("SEASON").text)
            card_category = card.find("CATEGORY").text
            if str(card_season) in str(season) and card_category in categories:
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
