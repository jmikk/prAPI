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
            master_currency_name="Wellspring Coins",
            exchange_rates={},  # {"currency_name": {"config_id": int, "rate": float}}
        )
        self.config.register_user(master_balance=0)

            # Lootbox configuration
        self.config.register_global(
            season=3,
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
    async def season(self, ctx, *season: int):
        """Set the season to filter cards."""
        seasons = [season for season in seasons]
        await self.config.season.set(seasons)
        await ctx.send(f"Season(s) set to {seasons}")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def categories(self, ctx, *categories: str):
        """Set the categories to filter cards."""
        categories = [category for category in categories]
        await self.config.categories.set(categories)
        await ctx.send(f"Categories set to {', '.join(categories)}")
        
    @shop.command()
    async def buy_lootbox(self, ctx):
        await ctx.send("You bought a lootbox woot woot!")

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
