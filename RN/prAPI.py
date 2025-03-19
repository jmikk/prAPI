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
            "last_wa_nations": [],
            "last_all_nations": [],
        }
        self.config.register_global(**default_global)
        self.session = aiohttp.ClientSession()


    def split_message(msg: str, max_len=1900):
        return [msg[i:i+max_len] for i in range(0, len(msg), max_len)]

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
                for part in split_message(current_wa_nations):
                    await ctx.send(part)
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
        """Post the QOTD with nation shoutouts to the RMB of The Wellspring."""
        region = "the_wellspring"
        useragent = await self.config.useragent()
        password = await self.config.password()
        nationname = await self.config.nationName()
    
        if not all([useragent, password, nationname]):
            await ctx.send("Please ensure User-Agent, Nation Name, and Password are all set.")
            return
    
        # Fetch current nation lists
        current_wa_nations = await self.fetch_nations_list("wanations")
        current_all_nations = await self.fetch_nations_list("nations")
    
        if not current_wa_nations or not current_all_nations:
            
            
            await ctx.send(current_wa_nations[:1900])
            await ctx.send(current_all_nations[:1900])

            return
    
        last_wa_nations = await self.config.last_wa_nations()
        last_all_nations = await self.config.last_all_nations()
    
        new_wa_nations = [n for n in current_wa_nations if n not in last_wa_nations]
        new_all_nations = [n for n in current_all_nations if n not in last_all_nations]
    
        featured_wa_nation = random.choice(current_wa_nations) if current_wa_nations else None
    
        sections = [message]
    
        if featured_wa_nation:
            sections.append(f"\n[spoiler=🌟 Featured WA Nation of the Day 🌟]\n[nation2]{featured_wa_nation}[/nation]\n[/spoiler]")
    
        if new_wa_nations:
            wa_nation_lines = "\n".join(f"- [nation2]{n}[/nation]" for n in new_wa_nations)
            sections.append(f"\n[spoiler=📣 Welcome our new WA Nations! 📣]\n{wa_nation_lines}\n[/spoiler]")
    
        if new_all_nations:
            all_nation_lines = "\n".join(f"- [nation2]{n}[/nation]" for n in new_all_nations)
            sections.append(f"\n[spoiler=🎉 Welcome our new Nations! 🎉]\n{all_nation_lines}\n[/spoiler]")
    
        sections.append(
            "\n[spoiler=Click here for info on how to subscribe to QOTD]"
            " This Question of the Day is brought to you by [region]The Wellspring[/region]. "
            "To receive daily QOTDs, telegram me or [nation2]9005[/nation]![/spoiler]"
        )
    
        full_message = "\n".join(sections)
    
        # Prepare post
        prepare_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": full_message,
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
                await ctx.split_and_send(prepare_text)
                return
    
            token = self.parse_token(prepare_text)
            x_pin = prepare_response.headers.get("X-Pin")
    
            if not token or not x_pin:
                await ctx.send("Failed to retrieve token or X-Pin.")
                await ctx.send(prepare_text)
                return
    
        execute_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": full_message,
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
                # Parse the URL of the posted message from the response
                try:
                    root = ET.fromstring(execute_text)
                    success_text = root.find("SUCCESS").text
                    post_url_part = success_text.split('"')[0]  # Extract URL path
                    full_url = f"https://www.nationstates.net{post_url_part}"
                except Exception:
                    full_url = "URL parse failed."
    
                # Save nations for next QOTD
                await self.config.last_wa_nations.set(current_wa_nations)
                await self.config.last_all_nations.set(current_all_nations)
    
                # Send link + ping to the designated channel
                log_channel_id = 1099398125061406770
                ping_role_id = 1115271309404942439
                log_channel = self.bot.get_channel(log_channel_id)
    
                if log_channel:
                    await log_channel.send(f"{full_url} <@&{ping_role_id}>")
                else:
                    await ctx.send("Post succeeded, but I couldn't find the log channel.")
    
                await ctx.send(f"✅ QOTD successfully posted to RMB of {region}!")
            else:
                await ctx.send("Failed to execute RMB post.")
                await ctx.send(execute_text)



    async def fetch_nations_list(self, query: str):
        headers = {"User-Agent": await self.config.useragent()}
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q={query}"
    
        async with self.session.get(url, headers=headers) as response:
            text = await response.text()  # Always await
    
            if response.status != 200:
                # Return the raw text so the caller can handle/display it
                return text
    
            try:
                root = ET.fromstring(text)
                region_element = root.find("REGION")
                if region_element is None:
                    return text  # Return raw response if REGION is missing
    
                nations_text = region_element.find(query.upper()).text
                return nations_text.split(":") if nations_text else []
            except ET.ParseError:
                return text  # Return raw response if XML parse fails

                

