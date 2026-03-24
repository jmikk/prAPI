import discord
import asyncio
import aiohttp
import time
import math
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict
from redbot.core import commands, Config, checks

class NexusCards(commands.Cog):
    """Purchase cards from 9006 and The Phoenix of the Spring using Wellcoins."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        
        default_global = {
            "user_agent": "Red-Bot NexusCards Cog - Used by [YourNation]",
            "source_nations": {
                "9006": {"password": ""},
                "the_phoenix_of_the_spring": {"password": ""}
            },
            "giveaway_nation": "The_Well_Giveaways"
        }
        default_user = {
            "common_uses": [],
            "legendary_uses": []
        }
        
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)

    async def _smart_sleep(self, headers: Dict):
        """Updates remaining requests and sleeps if approaching limit (saves 10)."""
        remaining = int(headers.get("X-Ratelimit-Remaining", 50))
        if remaining < 10:
            sleep_time = int(headers.get("X-Ratelimit-Reset", 30))
            await asyncio.sleep(sleep_time)

    async def _ns_request(self, url: str, password: str = None, ctx= None):
        """Standardized NS API requester."""
        ua = await self.config.user_agent()
        headers = {"User-Agent": ua}
        if password:
            headers["X-Password"] = password

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                await self._smart_sleep(response.headers)
                text = await response.text()
                await ctx.send(text)
                return ET.fromstring(text)

    def _calculate_legendary_cost(self, mv: float, season: str) -> int:
        """Logic: Up to 50 MV = 10k. Every 25.00 after = +5k. Apply multipliers."""
        if mv <= 50.00:
            base_cost = 10000
        else:
            increments = math.ceil((mv - 50.00) / 25.00)
            base_cost = 10000 + (increments * 5000)
        
        multipliers = {"1": 4.0, "2": 3.0, "3": 2.0, "4": 1.0, "cte": 1.5}
        mult = multipliers.get(str(season).lower(), 1.0)
        return int(base_cost * mult)

    async def _check_weekly_limit(self, user: discord.Member, limit_type: str, max_uses: int):
        now = time.time()
        one_week = 604800
        async with self.config.user(user).all() as data:
            data[limit_type] = [t for t in data[limit_type] if now - t < one_week]
            return len(data[limit_type]) < max_uses

    # --- Commands ---

    @commands.command()
    async def pricecheck(self, ctx, card_id: int, season: str):
        """Check the Wellcoin price of a Legendary card before buying."""
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={card_id};season={season}"
        root = await self._ns_request(url,ctx = ctx)
        await ctx.send(root)
        
        if root.find(".//MARKET_VALUE") is None:
            return await ctx.send("Could not find that card or market data.")

        mv = float(root.find(".//MARKET_VALUE").text)
        name = root.find(".//NAME").text
        cost = self._calculate_legendary_cost(mv, season)

        embed = discord.Embed(title="Price Evaluation", color=discord.Color.blue())
        embed.add_field(name="Card", value=f"{name} (S{season} #{card_id})", inline=False)
        embed.add_field(name="Market Value", value=f"{mv}", inline=True)
        embed.add_field(name="Wellcoin Cost", value=f"**{cost:,} WC**", inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def getcard(self, ctx):
        """Purchase a random non-legendary card from 9006 (400 Wellcoins)."""
        nexus = self.bot.get_cog("NexusExchange")
        if not nexus: return await ctx.send("NexusExchange cog not found.")

        if not await self._check_weekly_limit(ctx.author, "common_uses", 15):
            return await ctx.send("You have reached your limit of 15 cards this week.")

        try:
            bal = await nexus.get_balance(ctx.author)
            if bal < 400: return await ctx.send(f"Insufficient funds. (Current: {bal})")
        except: return await ctx.send("Error checking balance.")

        # Fetch 9006 Deck
        url = "https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname=9006"
        root = await self._ns_request(url)
        cards = root.findall(".//CARD")
        eligible = [c for c in cards if c.find("CATEGORY").text.lower() != "legendary"]
        
        if not eligible: return await ctx.send("No eligible cards found in 9006.")

        import random
        target = random.choice(eligible)
        card_id = target.find("ID").text
        season = target.find("SEASON").text
        name = target.find("NAME").text if target.find("NAME") is not None else "Unknown Name"
        mv = target.find("MARKET_VALUE").text if target.find("MARKET_VALUE") is not None else "0.00"

        # Transfer Logic
        sources = await self.config.source_nations()
        passw = sources.get("9006", {}).get("password")
        gift_url = f"https://www.nationstates.net/cgi-bin/api.cgi?a=sendcard&cardid={card_id}&season={season}&to={ctx.author.display_name.replace(' ', '_')}"
        
        result = await self._ns_request(gift_url, password=passw)
        
        if result.find("SUCCESS") is not None:
            await nexus.take_wellcoins(ctx.author, 400)
            async with self.config.user(ctx.author).common_uses() as uses:
                uses.append(time.time())

            # Specific requested Embed format
            embed = discord.Embed(title="Loot Box Opened!", description="You received a card!", color=discord.Color.gold())
            embed.add_field(name="Card Name", value=name, inline=False)
            embed.add_field(name="Card ID", value=card_id, inline=True)
            embed.add_field(name="Season", value=season, inline=True)
            embed.add_field(name="Market Value", value=mv, inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Transfer failed. Ensure your Discord name matches your Nation name exactly.")

    @commands.command()
    async def buylegendary(self, ctx, card_id: int, season: str):
        """Purchase a specific Legendary artwork."""
        nexus = self.bot.get_cog("NexusExchange")
        if not nexus: return await ctx.send("NexusExchange cog not found.")

        if not await self._check_weekly_limit(ctx.author, "legendary_uses", 1):
            return await ctx.send("Limit: 1 Legendary per week.")

        sources_to_check = ["9006", "the_phoenix_of_the_spring"]
        source_creds = await self.config.source_nations()
        found_in = None
        card_data = None

        for nation in sources_to_check:
            url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={card_id};season={season}"
            root = await self._ns_request(url)
            owners = [o.text.lower() for o in root.findall(".//OWNER")]
            
            if nation in owners:
                giveaway_nation = await self.config.giveaway_nation()
                if giveaway_nation.lower() in owners:
                    return await ctx.send("This card is reserved for a giveaway.")
                
                found_in = nation
                card_data = root
                break
        
        if not found_in:
            return await ctx.send("Legendary not found in stockpiles.")

        mv = float(card_data.find(".//MARKET_VALUE").text)
        cost = self._calculate_legendary_cost(mv, season)
        
        bal = await nexus.get_balance(ctx.author)
        if bal < cost:
            return await ctx.send(f"This costs {cost} WC. You have {bal}.")

        passw = source_creds.get(found_in, {}).get("password")
        gift_url = f"https://www.nationstates.net/cgi-bin/api.cgi?a=sendcard&cardid={card_id}&season={season}&to={ctx.author.display_name.replace(' ', '_')}"
        
        result = await self._ns_request(gift_url, password=passw)
        
        if result.find("SUCCESS") is not None:
            await nexus.take_wellcoins(ctx.author, cost)
            async with self.config.user(ctx.author).legendary_uses() as uses:
                uses.append(time.time())
            await ctx.send(f"💎 Sent Season {season} #{card_id} to you for {cost} Wellcoins.")
        else:
            await ctx.send("❌ Transfer failed. Check Nation name or password.")

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def nexusset(self, ctx):
        """Admin Settings."""
        pass

    @nexusset.command()
    async def useragent(self, ctx, *, ua: str):
        await self.config.user_agent.set(ua)
        await ctx.send(f"UA set to: `{ua}`")

    @nexusset.command()
    async def source(self, ctx, nation: str, password: str):
        nation = nation.lower().replace(" ", "_")
        async with self.config.source_nations() as sources:
            sources[nation] = {"password": password}
        await ctx.send(f"Stored credentials for {nation}.")
