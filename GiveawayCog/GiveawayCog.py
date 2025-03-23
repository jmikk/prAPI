import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import random

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

    async def end_giveaway(self, message, view, end_time):
        await discord.utils.sleep_until(end_time)
        await view.disable_all_items()
        await message.edit(view=view)
        entrants = view.get_entrants()
        if entrants:
            winner = random.choice(entrants)
            await self.config.winner_map.set_raw(
                str(winner.id),
                value={
                    "message_id": message.id,
                    "cardid": view.card_data["cardid"],
                    "season": view.card_data["season"],
                    "timestamp": int(datetime.utcnow().timestamp())
                }
            )
            await message.reply(f"Giveaway ended! Congratulations {winner.mention}, you won the card giveaway! Use `!claimcard <destination>` to tell Gob where to send your card.")
        else:
            await message.reply("Giveaway ended! No entrants.")

    @commands.admin_or_permissions(administrator=True)
    @commands.command()
    async def viewclaims(self, ctx):
        """Admin command to view all unclaimed cards."""
        try:
            winner_map = await self.config.winner_map.all()

            if not winner_map:
                return await ctx.send("There are no unclaimed giveaways.")

            grouped_claims = {}
            for uid, info in winner_map.items():
                user_id = int(uid)
                grouped_claims.setdefault(user_id, []).append(info)

            messages = []
            for user_id, claims in grouped_claims.items():
                user = ctx.guild.get_member(user_id)
                user_name = user.display_name if user else f"User ID {user_id}"
                claims_text = "\n".join([
                    f"Card ID {claim['cardid']} (Season {claim['season']}) - Won on <t:{int(claim.get('timestamp', 0))}:F>"
                    for claim in claims
                ])
                messages.append(f"**{user_name}**\n{claims_text}")

            for chunk in [messages[i:i+5] for i in range(0, len(messages), 5)]:
                await ctx.send("\n\n".join(chunk))

        except Exception as e:
            await self.log_error(ctx, str(e))

    def parse_token(self, text):
        try:
            root = ET.fromstring(text)
            return root.findtext("TOKEN")
        except ET.ParseError:
            return None
