from redbot.core import commands, Config
import asyncio
import xml.etree.ElementTree as ET
import requests
import random
from datetime import datetime, timedelta
import sans

def is_admin():
    async def predicate(ctx):
        # Check if the user has a role named "Admin"
        return any(role.name == "Admin" for role in ctx.author.roles)
    return commands.check(predicate)


class CardRequestCog(commands.Cog):
    """Cog for managing card requests and sending cards"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.password = ""
        self.client = sans.AsyncClient()

        default_global = {
            "claim_nations": [],
            "user_agent": "RedbotCardRequestCog/1.0 written by 9003 for Luc-Oliver",
            "request_log_channel": None,
            "requests": {},
            "last_reset": None,
        }
        self.auth = sans.NSAuth()

        self.config.register_global(**default_global)
        self.password = ""

    async def api_request(self, data) -> sans.Response:
        response = await self.client.get(sans.World(**data), auth=self.auth)
        response.raise_for_status()
        return response

    @commands.command()
    @is_admin()
    async def remove_claim_nation(self, ctx, *, nation: str):
        """Removes a nation from which cards can be claimed"""
        claim_nations = await self.config.claim_nations()
        nation = "_".join(nation.lower().split())
        if nation in claim_nations:
            claim_nations.remove(nation)
            await self.config.claim_nations.set(claim_nations)
            await ctx.send(f"Nation {nation} removed from the claim list.")
        else:
            await ctx.send(f"Nation {nation} is not in the claim list.")

    @commands.command()
    @is_admin()
    async def set_claim_nation_password(self, ctx, *, password2):
        self.password=password2
        self.auth = sans.NSAuth(password=self.password)
        await ctx.send(f"Set regional nation password.")

    @commands.command()
    @is_admin()
    async def add_claim_nation(self, ctx, *, nation: str):
        """Adds a nation from which cards can be claimed"""
        claim_nations = await self.config.claim_nations()
        nation = "_".join(nation.lower().split())
        if nation not in claim_nations:
            claim_nations.append(nation)
            await self.config.claim_nations.set(claim_nations)
            await ctx.send(f"Nation {nation} added to the claim list.")
        else:
            await ctx.send(f"Nation {nation} is already in the claim list.")

    @commands.command()
    @is_admin()
    async def CRC_agent(self, ctx, *,agent):
        sans.set_agent(agent, _force=True)
        await ctx.send("Agent set.")
        self.UA=agent

    @commands.command()
    @is_admin()
    async def set_log_channel(self, ctx, channel_id: int):
        """Sets the log channel where card transactions will be logged"""
        await self.config.request_log_channel.set(channel_id)
        await ctx.send(f"Log channel set to {channel_id}.")

    @commands.command()
    async def request_card2(self, ctx, card_id: str, season: str, destiNATION: str, gifter: str):
        """Request a card from a nation"""

        self.auth = sans.NSAuth(password=self.password)


        
        user_id = str(ctx.author.id)
        current_month = datetime.utcnow().month
        requests = await self.config.requests()

        if user_id in requests:
            last_request_month = requests[user_id]["month"]
            if last_request_month == current_month:
                await ctx.send("You have already made a request this month.")
                return

        claim_nations = await self.config.claim_nations()
        if not claim_nations:
            await ctx.send("No nations available for claiming cards.")
            return

        if gifter not in claim_nations:
            await ctx.send("No Nation not found: Error in the Gifter name please double check it")
            return

        giftie = destiNATION.lower().replace(" ", "_")

        await ctx.send(
            f"Attempting to gift {card_id} to {giftie} from {gifter}"
        )
        data = {
            "nation": gifter,
            "cardid": card_id,
            "season": season,
            "to": giftie,
            "mode": "prepare",
            "c": "giftcard",
        }
        r = await self.api_request(data)
        giftToken = r.xml.find("SUCCESS").text
        # await ctx.send(r.headers)
        data.update(mode="execute", token=giftToken)
        await self.api_request(data=data)
        # await ctx.send(z2.content)
        # Log the request
        requests[user_id] = {"month": current_month, "card_id": card_id, "nation": giftie}
        await self.config.requests.set(requests)

        log_channel_id = await self.config.request_log_channel()
        log_channel = self.bot.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(f"Card {card_id} (Season {season}) sent to {giftie} from {gifter}.")

        await ctx.send(f"Card {card_id} (Season {season}) has been sent to {giftie} from {gifter}.")

    @commands.command()
    @is_admin()
    async def reset_requests(self, ctx):
        """Manually resets all requests"""
        await self.config.requests.set({})
        await ctx.send("All requests have been reset.")

    async def cog_check(self, ctx):
        """Check if the requests should be reset based on the date"""
        last_reset = await self.config.last_reset()
        current_date = datetime.utcnow().date()

        if not last_reset or datetime.strptime(last_reset, "%Y-%m-%d").date() < current_date.replace(day=1):
            await self.config.requests.set({})
            await self.config.last_reset.set(current_date.strftime("%Y-%m-%d"))
            return True
        return True

