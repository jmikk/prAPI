from redbot.core import commands, Config
import asyncio
import xml.etree.ElementTree as ET
import requests
import random
from datetime import datetime, timedelta

class CardRequestCog(commands.Cog):
    """Cog for managing card requests and sending cards"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "claim_nations": [],
            "password": "",
            "user_agent": "RedbotCardRequestCog/1.0",
            "request_log_channel": None,
            "requests": {},
            "last_reset": None,
        }
        self.config.register_global(**default_global)
        self.password = ""

    @commands.command()
    @commands.is_owner()
    async def set_claim_password(self, ctx, *, password: str):
        """Sets the password shared by all nations from which cards can be claimed"""
        await self.config.password.set(password)
        self.password = password
        await ctx.send("Password set successfully.")

    @commands.command()
    @commands.is_owner()
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
    @commands.is_owner()
    async def set_user_agent(self, ctx, *, user_agent: str):
        """Sets the User-Agent header for API requests"""
        await self.config.user_agent.set(user_agent)
        await ctx.send(f"User-Agent set to {user_agent}.")

    @commands.command()
    @commands.is_owner()
    async def set_log_channel(self, ctx, channel_id: int):
        """Sets the log channel where card transactions will be logged"""
        await self.config.request_log_channel.set(channel_id)
        await ctx.send(f"Log channel set to {channel_id}.")

    @commands.command()
    async def request_card2(self, ctx, card_id: str, season: str, destiNATION: str, gifter: str):
        """Request a card from a nation"""
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
        claim_nation = gifter

        # Prepare the API request to gift the card
        data = {
            "nation": claim_nation,
            "cardid": card_id,
            "season": season,
            "to": giftie,
            "mode": "prepare",
            "c": "giftcard",
        }
        password = await self.config.password()
        user_agent = await self.config.user_agent()
        headers = {"User-Agent": user_agent}

        response = requests.post("https://www.nationstates.net/cgi-bin/api.cgi", params=data, auth=(claim_nation, password), headers=headers)
        root = ET.fromstring(response.content)
        gift_token = root.find("SUCCESS").text

        # Execute the card gift
        data.update(mode="execute", token=gift_token)
        response = requests.post("https://www.nationstates.net/cgi-bin/api.cgi", params=data, auth=(claim_nation, password), headers=headers)

        # Log the request
        requests[user_id] = {"month": current_month, "card_id": card_id, "nation": giftie}
        await self.config.requests.set(requests)

        log_channel_id = await self.config.request_log_channel()
        log_channel = self.bot.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(f"Card {card_id} (Season {season}) sent to {giftie} from {claim_nation}.")

        await ctx.send(f"Card {card_id} (Season {season}) has been sent to {giftie} from {claim_nation}.")

    @commands.command()
    @commands.is_owner()
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
