import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import random
from discord.ext import tasks


class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9006)
        self.config.register_guild(giveaway_channel=None, log_channel=None)
        self.config.register_global(winner_map={}, nationname=None, password=None)
        self.giveaway_tasks = {}
        self.session = aiohttp.ClientSession()

    async def log_error(self, ctx, error):
        log_channel_id = await self.config.guild(ctx.guild).log_channel()
        log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None
        if log_channel:
            await log_channel.send(f"Error occurred: {error}")
        await ctx.send("An error occurred. Please reach out to <@207526562331885568> for help.")

    @commands.command()
    async def claimcard(self, ctx, *, destination: str):
        """Claim all unclaimed cards and specify where to send them."""
        try:
            winner_map = await self.config.winner_map.all()
            user_claims = {uid: info for uid, info in winner_map.items() if int(uid) == ctx.author.id}

            if not user_claims:
                return await ctx.send("You have no unclaimed giveaways.")

            useragent = "9007"
            password = await self.config.password()
            nationname = await self.config.nationname()

            if not password or not nationname:
                return await ctx.send("Nation name or password is not set. Use `setnation` and `setpassword` commands.")

            # Prepare log channel
            log_channel_id = await self.config.guild(ctx.guild).log_channel()
            log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None

            x_pin = None

            for uid, claim_info in user_claims.items():
                card_id = claim_info["cardid"]
                season = claim_info["season"]

                if log_channel:
                    await log_channel.send(f"{ctx.author.mention} claimed card ID {card_id} (Season {season}) to be sent to {destination}.")

                prepare_data = {
                    "nation": nationname,
                    "c": "giftcard",
                    "cardid": card_id,
                    "season": season,
                    "to": destination,
                    "mode": "prepare"
                }
                prepare_headers = {
                    "User-Agent": useragent,
                    "X-Password": password
                }

                async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
                    prepare_text = await prepare_response.text()
                    if prepare_response.status != 200:
                        return await ctx.send("Failed to prepare the gift.")

                    token = self.parse_token(prepare_text)
                    if not x_pin:
                        x_pin = prepare_response.headers.get("X-Pin")

                    if not token or not x_pin:
                        return await ctx.send("Failed to retrieve the token or X-Pin for gift execution.")

                execute_data = {
                    "nation": nationname,
                    "c": "giftcard",
                    "cardid": card_id,
                    "season": season,
                    "to": destination,
                    "mode": "execute",
                    "token": token
                }
                execute_headers = {
                    "User-Agent": useragent,
                    "X-Pin": x_pin
                }

                async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
                    if execute_response.status != 200:
                        return await ctx.send("Failed to execute the gift.")

                await self.config.winner_map.clear_raw(str(ctx.author.id))

            await ctx.send("Successfully claimed and gifted all cards!")

        except Exception as e:
            await self.log_error(ctx, str(e))

    def parse_token(self, text):
        try:
            root = ET.fromstring(text)
            return root.findtext("TOKEN")
        except ET.ParseError:
            return None

# The rest of the cog remains unchanged
# ...
