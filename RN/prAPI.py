import aiohttp
import random
import xml.etree.ElementTree as ET
from redbot.core import commands, Config, checks, tasks
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
        self.qotd_loop.start() # Start the background loop


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
        self.qotd_loop.cancel() # Stop the loop if the cog is unloaded

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

    # --- THE BACKGROUND LOOP ---
    @tasks.loop(hours=24)
    async def qotd_loop(self):
        # Retrieve the queue from your config (assuming a list of strings)
        queue = await self.config.qotd_queue()
        
        if not queue:
            # Optional: Log to your log channel that the queue is empty
            return

        # Pop the first question
        next_q = queue.pop(0)
        await self.config.qotd_queue.set(queue)

        # Call your posting logic (extracted to a helper method)
        await self.post_to_nationstates(next_q)

    @qotd_loop.before_loop
    async def before_qotd_loop(self):
        await self.bot.wait_until_ready()

    @commands.group(invoke_without_command=True)
    @has_specific_role()
    async def qotd(self, ctx):
        """Shows the current QOTD queue status."""
        queue = await self.config.qotd_queue()
        await ctx.send(f"📋 There are currently **{len(queue)}** questions in the queue.")

    @qotd.command(name="add")
    @has_specific_role()
    async def qotd_add(self, ctx, *, message: str):
        """Add a new question to the end of the queue."""
        async with self.config.qotd_queue() as queue:
            queue.append(message)
            count = len(queue)
        
        await ctx.send(f"✅ Added! That is question **#{count}** in the queue.")

    @qotd.command(name="list")
    @has_specific_role()
    async def qotd_list(self, ctx):
        """List all upcoming questions."""
        queue = await self.config.qotd_queue()
        if not queue:
            return await ctx.send("The queue is empty.")
        
        formatted_list = "\n".join([f"{i+1}. {q[:50]}..." for i, q in enumerate(queue)])
        await ctx.send(f"**Upcoming Queue:**\n{formatted_list}")

    async def post_to_nationstates(self, message: str):
        region = "the_wellspring"
        useragent = await self.config.useragent()
        password = await self.config.password()
        nationname = await self.config.nationName()

        if not all([useragent, password, nationname]):
            return # Log error

        # --- Your Prepare Logic ---
        prepare_data = {"nation": nationname, "c": "rmbpost", "region": region, "text": message, "mode": "prepare"}
        prepare_headers = {"User-Agent": useragent, "X-Password": password}

        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
            if prepare_response.status != 200:
                return 

            prepare_text = await prepare_response.text()
            token = self.parse_token(prepare_text)
            x_pin = prepare_response.headers.get("X-Pin")

            if not token or not x_pin:
                return

        # --- Your Execute Logic ---
        execute_data = {"nation": nationname, "c": "rmbpost", "region": region, "text": message, "mode": "execute", "token": token}
        execute_headers = {"User-Agent": useragent, "X-Pin": x_pin}

        async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
            if execute_response.status == 200:
                execute_text = await execute_response.text()
                # ... (Insert your re.search and XML logic here to get full_url) ...
                
                # Log to Discord
                log_channel = self.bot.get_channel(1405569526329774200)
                if log_channel:
                    allowed_mentions = discord.AllowedMentions(roles=True)
                    await log_channel.send(f"{full_url} <@&1115271309404942439>", allowed_mentions=allowed_mentions)



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
    async def postdispatch(self, ctx, category: int, subcategory:int,*, title: str):
        """
        Upload a text file containing the dispatch content, and post it to NationStates.
        Usage: $postdispatch "Your Title" (then upload the file with the command)
        """
        required_role_id = 1113108765315715092
        if not any(role.id == required_role_id for role in ctx.author.roles):
            await ctx.send("❌ You do not have permission to use this command.")
            return    

        replacements = {
                "’": "'",
                "‘": "'",
                "“": '"',
                "”": '"',
                "—": "-",  # em dash
                "–": "-",  # en dash
                "…": "...",
            }
        for bad, good in replacements.items():
            title = title.replace(bad, good)
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
            replacements = {
                "’": "'",
                "‘": "'",
                "“": '"',
                "”": '"',
                "—": "-",  # em dash
                "–": "-",  # en dash
                "…": "...",
            }
            for bad, good in replacements.items():
                text = text.replace(bad, good)
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
                if resp.status != 200 or "SUCCESS" not in prepare_text:
                    await ctx.send(f"❌ Prepare failed:\n{box(prepare_text[:1900])}")
                    return
                xpin = resp.headers.get("X-Pin")
                match = re.search(r"<SUCCESS>(.*?)</SUCCESS>", prepare_text)
                if not match:
                    await ctx.send(f"❌ Could not find token in response:\n{box(prepare_text[:1900])}")
                    return
                token = match.group(1)

            # Step 2: Execute
            headers_execute = {
                "User-Agent": useragent,
                "X-Pin": xpin
            }

            payload["mode"] = "execute"
            payload["token"] = token

            async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", headers=headers_execute, data=payload) as resp:
                execute_text = await resp.text()
                if resp.status != 200:
                    await ctx.send(f"❌ Execute failed:\n{box(execute_text[:1900])}")
                else:
                    
                    # Extract the href content inside the SUCCESS tag
                    match = re.search(r'&lt;a href="([^"]+)"&gt;', execute_text)
                    if match:
                        relative_url = match.group(1)
                        full_url = f"https://www.nationstates.net{relative_url}"
                        await ctx.send(full_url)
    
