import aiohttp
import random
import xml.etree.ElementTree as ET
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import discord
import time
import os
from datetime import datetime
from discord import AllowedMentions
from redbot.core.utils.chat_formatting import box
import re

class prAPI(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "useragent": "",
            "nationName": "",
            "password": "",
            "last_wa_nations": [],
            "last_all_nations": [],
        }
        self.config.register_global(**default_global)
        self.session = aiohttp.ClientSession()


    async def split_and_send(self, ctx_or_channel, message: str, max_len: int = 1900):
        parts = [message[i:i + max_len] for i in range(0, len(message), max_len)]
        for part in parts:
            await ctx_or_channel.send(part)

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
                await ctx.send(prepare_response.status)
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
                await ctx.send(await execute_response.text())
                await ctx.send(f"Successfully posted to the RMB of {region}!")
            else:
                await ctx.send("Failed to execute RMB post.")
                await ctx.send(execute_text)

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.default)
    @has_specific_role()
    async def QOTD(self, ctx, *, message: str):
        """Post the Question of the Day to The Wellspring with shout-outs."""
        region = "the_wellspring"
        useragent = await self.config.useragent()
        password = await self.config.password()
        nationname = await self.config.nationName()
    
        if not all([useragent, password, nationname]):
            await ctx.send("Please ensure User-Agent, Nation Name, and Password are all set.")
            return
    
        # Prepare and post
        prepare_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": message,
            "mode": "prepare"
        }
        prepare_headers = {"User-Agent": useragent, "X-Password": password}
    
        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
            prepare_text = await prepare_response.text()
            if prepare_response.status != 200:
                await ctx.send(f"Failed to prepare RMB post. Status: {prepare_response.status}")
                await self.split_and_send(ctx, prepare_text)
                return
    
            token = self.parse_token(prepare_text)
            x_pin = prepare_response.headers.get("X-Pin")
    
            if not token or not x_pin:
                await ctx.send("Failed to retrieve token or X-Pin for RMB post execution.")
                await self.split_and_send(ctx, prepare_text)
                return
    
        execute_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": message,
            "mode": "execute",
            "token": token
        }
        execute_headers = {"User-Agent": useragent, "X-Pin": x_pin}
    
        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
            execute_text = await execute_response.text()
            if execute_response.status == 200:
                try:
                    root = ET.fromstring(execute_text)
                    success_text = root.find("SUCCESS").text
                
                    # Extract URL from the href in the SUCCESS text
                    import re
                    match = re.search(r'href="([^"]+)"', execute_text)
                    if match:
                        post_url_part = match.group(1)
                        full_url = f"https://www.nationstates.net{post_url_part}"
                    else:
                        full_url = "URL parse failed."
                except Exception:
                    full_url = "URL parse failed."

    
                log_channel_id = 1099398125061406770
                ping_role_id = 1115271309404942439
                log_channel = self.bot.get_channel(log_channel_id)
    
                if log_channel:
                    allowed_mentions = AllowedMentions(
                    everyone=False,  # Disables @everyone and @here mentions
                    users=True,      # Enables user mentions
                    roles=True       # Enables role mentions
                )
                    await log_channel.send(f"{full_url} <@&{ping_role_id}>",allowed_mentions=allowed_mentions)
                else:
                    await ctx.send("Post succeeded, but I couldn't find the log channel.")
    
                await ctx.send(f"✅ QOTD successfully posted to RMB of {region}!")
            else:
                await ctx.send("Failed to execute RMB post.")
                await self.split_and_send(ctx, execute_text)






    async def fetch_nations_list(self, query: str):
        headers = {"User-Agent": await self.config.useragent()}
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q={query}"

        async with self.session.get(url, headers=headers) as response:
            text = await response.text()

            if response.status != 200:
                return text
            try:
                root = ET.fromstring(text)
                region_element = root.find("REGION")
                if region_element is None:
                    return text

                tag_name = "UNNATIONS" if query == "wanations" else "NATIONS"
                nations_text = region_element.find(tag_name).text
                if not nations_text:
                    return []

                delimiter = "," if query == "wanations" else ":"
                return nations_text.split(delimiter)
            except ET.ParseError:
                return text

    @commands.command()
    async def postdispatch(self, ctx, category: int, subcategory:int, title: str):
        """
        Upload a text file containing the dispatch content, and post it to NationStates.
        Usage: $postdispatch "Your Title" (then upload the file with the command)
        """
        if not ctx.message.attachments:
            await ctx.send("❌ Please attach a `.txt` file with the dispatch content.")
            return

        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith(".txt"):
            await ctx.send("❌ Only `.txt` files are supported.")
            return

        try:
            content = await attachment.read()
            text = content.decode("utf-8")
        except Exception as e:
            await ctx.send(f"❌ Failed to read file: `{e}`")
            return

        settings = await self.config.all()
        nation = settings["nationName"]
        useragent = settings["useragent"]
        password = settings["password"]

        headers_prepare = {
            "User-Agent": useragent,
            "X-Password": password
        }

        payload = {
            "nation": nation,
            "c": "dispatch",
            "dispatch": "add",
            "title": title,
            "text": text,
            "category": category,     
            "subcategory": subcategory, 
            "mode": "prepare"
        }

        async with aiohttp.ClientSession() as session:
            # Step 1: Prepare
            async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", headers=headers_prepare, data=payload) as resp:
                prepare_text = await resp.text()
                if resp.status != 200 or "token" not in prepare_text:
                    await ctx.send(f"❌ Prepare failed:\n{box(prepare_text[:1900])}")
                    return

                match = re.search(r"<SUCCESS>(.*?)</SUCCESS>", prepare_text)
                if not match:
                    await ctx.send(f"❌ Could not find token in response:\n{box(prepare_text[:1900])}")
                    return
                token = match.group(1)

            # Step 2: Execute
            headers_execute = {
                "User-Agent": useragent,
                "X-Pin": password
            }

            payload["mode"] = "execute"
            payload["token"] = token

            async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", headers=headers_execute, data=payload) as resp:
                execute_text = await resp.text()
                if resp.status != 200:
                    await ctx.send(f"❌ Execute failed:\n{box(execute_text[:1900])}")
                else:
                    await ctx.send("✅ Dispatch successfully posted!")
    
