import aiohttp
import random
import xml.etree.ElementTree as ET
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import discord
import time
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
        self.session = aiohttp.ClientSession()

    def has_specific_role():
        async def predicate(ctx):
            role_id = 1113108765315715092
            return any(role.id == role_id for role in ctx.author.roles)
        return commands.check(predicate)


    def cog_unload(self):
        asyncio.create_task(self.session.close())

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
        nationname = nationname.replace(" ", "_").lower()
        await self.config.nationName.set(nationname)
        await ctx.send(f"Nation Name set to {nationname}")

    @commands.dm_only()
    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def RN_password(self, ctx, *, password: str):
        """Set the password for the loot box prizes in DM."""
        await self.config.password.set(password)
        await ctx.send("Password set.")

    def parse_token(self, xml_data: str) -> str:
        """Extracts the token from XML response."""
        try:
            root = ET.fromstring(xml_data)
            token = root.find("SUCCESS").text
            return token
        except ET.ParseError:
            return None

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.default)
    @has_specific_role()# 1 use per 60 seconds
    async def gift_card(self, ctx, giftie: str, ID: str, Season: str):
        """Gift a card to a specified nation."""
        recipient = "_".join(giftie.split()).lower()
        useragent = await self.config.useragent()
        password = await self.config.password()
        nationname = await self.config.nationName()

        if not all([useragent, password, nationname]):
            await ctx.send("Please ensure User-Agent, Nation Name, and Password are all set.")
            return

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

        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
            prepare_text = await prepare_response.text()
            if prepare_response.status != 200:
                await ctx.send("Failed to prepare the gift.")
                await ctx.send(prepare_text)
                return

            token = self.parse_token(prepare_text)
            x_pin = prepare_response.headers.get("X-Pin")

            if not token or not x_pin:
                await ctx.send("Failed to retrieve the token or X-Pin for gift execution.")
                await ctx.send(prepare_text)
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

        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
            execute_text = await execute_response.text()
            if execute_response.status == 200:
                await ctx.send(f"Successfully gifted card ID {ID} (Season {Season}) to {recipient}!")
            else:
                await ctx.send("Failed to execute the gift.")
                await ctx.send(execute_text)

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.default)
    @has_specific_role()
    async def rmb_post(self, ctx, region: str, *, message: str):
        """Admin Only: Post a message to a region's RMB."""
        region = region.replace(" ", "_").lower()
        useragent = await self.config.useragent()
        password = await self.config.password()
        nationname = await self.config.nationName()
    
        if not all([useragent, password, nationname]):
            await ctx.send("Please ensure User-Agent, Nation Name, and Password are all set.")
            return
    
        prepare_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": message,
            "mode": "prepare"
        }
        prepare_headers = {
            "User-Agent": useragent,
            "X-Password": password
        }
    
        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
            prepare_text = await prepare_response.text()
            if prepare_response.status != 200:
                await ctx.send("Failed to prepare RMB post.")
                await ctx.send(prepare_text)
                return
    
            token = self.parse_token(prepare_text)
            x_pin = prepare_response.headers.get("X-Pin")
    
            if not token or not x_pin:
                await ctx.send("Failed to retrieve the token or X-Pin for RMB post execution.")
                await ctx.send(prepare_text)
                return
    
        execute_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": message,
            "mode": "execute",
            "token": token
        }
        execute_headers = {
            "User-Agent": useragent,
            "X-Pin": x_pin
        }
    
        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
            execute_text = await execute_response.text()
            if execute_response.status == 200:
                await ctx.send(f"Successfully posted to the RMB of {region}!")
            else:
                await ctx.send("Failed to execute RMB post.")
                await ctx.send(execute_text)

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.default)
    @has_specific_role()
    async def QOTD(self, ctx, *, message: str):
        """Admin Only: Post a message to a region's RMB."""
        region = "the_wellspring"
        useragent = await self.config.useragent()
        password = await self.config.password()
        nationname = await self.config.nationName()
    
        if not all([useragent, password, nationname]):
            await ctx.send("Please ensure User-Agent, Nation Name, and Password are all set.")
            return
    
        prepare_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": message,
            "mode": "prepare"
        }
        prepare_headers = {
            "User-Agent": useragent,
            "X-Password": password
        }
    
        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
            prepare_text = await prepare_response.text()
            if prepare_response.status != 200:
                await ctx.send("Failed to prepare RMB post.")
                await ctx.send(prepare_text)
                return
    
            token = self.parse_token(prepare_text)
            x_pin = prepare_response.headers.get("X-Pin")
    
            if not token or not x_pin:
                await ctx.send("Failed to retrieve the token or X-Pin for RMB post execution.")
                await ctx.send(prepare_text)
                return
    
        execute_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": message,
            "mode": "execute",
            "token": token
        }
        execute_headers = {
            "User-Agent": useragent,
            "X-Pin": x_pin
        }
    
        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
            execute_text = await execute_response.text()
            if execute_response.status == 200:
                await ctx.send(f"Successfully posted to the RMB of {region}!")
            else:
                await ctx.send("Failed to execute RMB post.")
                await ctx.send(execute_text)
