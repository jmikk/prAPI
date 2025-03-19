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


class prAPI(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "useragent": "",
            "nationName": "",
            "password": "",
        }

        self.config.register_global(**default_global)
        
    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def RN_useragent(self, ctx, *, useragent: str):
        """Set the User-Agent header for the requests."""
        await self.config.useragent.set(useragent)
        await ctx.send(f"User-Agent set to {useragent}")
    
    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def RN_nationname(self, ctx, *, nationname: str):
        """Set the nationName for the loot box prizes."""
        nationname = nationname.replace(" ","_").lower()
        await self.config.nationName.set(nationname)
        await ctx.send(f"Nation Name set to {nationname}")

    @commands.dm_only()
    @commands.command()
    async def RN_password(self, ctx, *, password: str):
        """Set the password for the loot box prizes in DM."""
        await self.config.password.set(password)
        await ctx.send(f"Password set to {password}")

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.default)  # 1 use per 60 seconds
    async def gift_card(self, ctx, giftie, ID, Season):
        """Open a loot box and fetch a random card for the specified nation."""
        recipient =  "_".join(giftie)
        useragent = await self.config.useragent()
        headers = {"User-Agent": useragent}
        password = await self.config.password()
        nationname = await self.config.nationName()
        # Prepare the gift
        prepare_data = {
                    "nation": nationname,
                    "c": "giftcard",
                    "cardid": ID,
                    "season": Season,
                    "to": giftie,
                    "mode": "prepare"
                }
        prepare_headers = {
                    "User-Agent": useragent,
                    "X-Password": password
                }

        async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
            if prepare_response.status != 200:
                        
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
                        "cardid": ID,
                        "season": Season,
                        "to": giftie,
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
