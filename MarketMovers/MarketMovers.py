from collections import defaultdict
import time
import xml.etree.ElementTree as ET
import aiohttp
import discord
from redbot.core import Config, commands

class MarketMovers(commands.Cog):
    """Tracks NationStates card market activity for a competitive leaderboard."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        
        default_global = {
            "hard_stop_time": 0,  # 0 means all history, or a unix timestamp
            "target_nations": [],
            "cached_leaderboard": []
        }
        self.config.register_global(**default_global)

    async def update_leaderboard_cache(self):
        hard_stop = await self.config.hard_stop_time()
        nations = await self.config.target_nations()
        
        unique_participation_set = set()
        current_beforetime = int(time.time())
        base_url = "https://www.nationstates.net/cgi-bin/api.cgi?q=cards+trades"
        user_agent = "MarketMoversBot (Contact: your-email@example.com)"
        
        headers = {"User-Agent": user_agent}
        
        async with aiohttp.ClientSession() as session:
            page_count = 0
            while page_count < 25:  # Safety cap
                page_count += 1
                url = f"{base_url};limit=1000;beforetime={current_beforetime}"
                
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(15)
                        continue
                    if resp.status != 200:
                        break
                    
                    xml_data = await resp.text()
                
                try:
                    root = ET.fromstring(xml_data)
                except ET.ParseError:
                    break
                
                trades = root.findall(".//TRADE")
                if not trades:
                    break
                
                oldest_timestamp = None
                
                for trade in trades:
                    ts_el = trade.find("TIMESTAMP")
                    if ts_el is None or not ts_el.text:
                        continue
                    try:
                        timestamp = int(ts_el.text.strip())
                    except ValueError:
                        continue
                    
                    if oldest_timestamp is None or timestamp < oldest_timestamp:
                        oldest_timestamp = timestamp
                        
                    if hard_stop > 0 and timestamp < hard_stop:
                        continue
                        
                    price_el = trade.find("PRICE")
                    if price_el is None or not price_el.text or not price_el.text.strip():
                        continue
                    try:
                        if float(price_el.text.strip()) <= 0:
                            continue
                    except ValueError:
                        continue
                        
                    card_id = trade.find("CARDID")
                    season = trade.find("SEASON")
                    buyer = trade.find("BUYER")
                    seller = trade.find("SELLER")
                    
                    c_id = card_id.text.strip() if card_id is not None and card_id.text else "unknown"
                    s_id = season.text.strip() if season is not None and season.text else "1"
                    
                    if buyer is not None and buyer.text:
                        unique_participation_set.add((buyer.text.strip().lower(), c_id, s_id))
                    if seller is not None and seller.text:
                        unique_participation_set.add((seller.text.strip().lower(), c_id, s_id))
                    
                if not oldest_timestamp or oldest_timestamp >= current_beforetime:
                    break
                if hard_stop > 0 and oldest_timestamp <= hard_stop:
                    break
                current_beforetime = oldest_timestamp
                
        # Calculate scores
        tallies = defaultdict(int)
        for player, _, _ in unique_participation_set:
            tallies[player] += 1
            
        scores = {n: tallies[n.strip().lower()] for n in nations}
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Save cache
        await self.config.set_raw("cached_leaderboard", value=sorted_scores)

    @commands.group()
    async def marketmovers(self, ctx):
        """Market Movers competition management commands."""
        pass

    @marketmovers.command(name="leaderboard")
    async def mm_leaderboard(self, ctx):
        """Displays the fancy embed leaderboard for Market Movers."""
        cached_scores = await self.config.get_raw("cached_leaderboard")
        hard_stop = await self.config.hard_stop_time()
        
        if not cached_scores:
            await ctx.send("Leaderboard data is currently empty. Run `[p]marketmovers refresh` to generate it.")
            return
            
        embed = discord.Embed(
            title="🏆 Market Movers Leaderboard 🏆",
            description="Ranking nations by unique paid card trades (buys & sells).",
            color=discord.Color.gold()
        )
        
        leaderboard_text = ""
        medals = ["🥇", "🥈", "🥉"]
        
        for idx, (nation, score) in enumerate(cached_scores, start=1):
            icon = medals[idx - 1] if idx <= 3 else f"`{idx}.`"
            leaderboard_text += f"{icon} **{nation}** — `{score}` unique trades\n"
            
        embed.add_field(name="Standings", value=leaderboard_text or "No data available.", inline=False)
        embed.set_footer(text=f"Time Horizon Boundary Filter: {'None (All time)' if hard_stop == 0 else f'< timestamp {hard_stop}>'}")
        
        await ctx.send(embed=embed)

    @marketmovers.command(name="refresh")
    async def mm_refresh(self, ctx):
        """Manually triggers an immediate update of the market leaderboard cache."""
        async with ctx.typing():
            await self.update_leaderboard_cache()
        await ctx.send("✅ Market Movers leaderboard data has been successfully refreshed!")

    @marketmovers.command(name="timeframe")
    async def mm_timeframe(self, ctx, timestamp: int):
        """Set the hard stop unix timestamp boundary limit (0 to clear)."""
        await self.config.hard_stop_time.set(timestamp)
        await ctx.send(f"⚙️ Hard stop timestamp boundary successfully updated to: `{timestamp}`")

    @marketmovers.group(name="nations")
    async def mm_nations(self, ctx):
        """Manage competing nations on the leaderboard."""
        pass

    @mm_nations.command(name="add")
    async def nations_add(self, ctx, nation_name: str):
        """Add a nation to the competition lineup."""
        async with self.config.target_nations() as nations:
            cleaned = nation_name.strip().lower()
            if cleaned in nations:
                await ctx.send(f"⚠️ `{nation_name}` is already on the roster.")
                return
            nations.append(cleaned)
        await ctx.send(f"✅ Added `{nation_name}` to the Market Movers competition!")

    @mm_nations.command(name="remove")
    async def nations_remove(self, ctx, nation_name: str):
        """Remove a nation from the competition lineup."""
        async with self.config.target_nations() as nations:
            cleaned = nation_name.strip().lower()
            if cleaned not in nations:
                await ctx.send(f"⚠️ `{nation_name}` wasn't found in the competition roster.")
                return
            nations.remove(cleaned)
        await ctx.send(f"🗑️ Removed `{nation_name}` from the competition.")


def setup(bot):
    # Must be synchronous (no await)
    bot.add_cog(MarketMovers(bot))
