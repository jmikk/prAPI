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
            "target_nations": ["neptunian_military_administration", "eswaria", "vulxo"],
            "cached_leaderboard": [],
            "last_updated": 0     # Tracks epoch time of the last successful refresh
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
        
        # Save cache and timestamp
        await self.config.set_raw("cached_leaderboard", value=sorted_scores)
        await self.config.set_raw("last_updated", value=int(time.time()))

    @commands.group()
    @commands.is_owner()
    async def marketmovers(self, ctx):
        """Market Movers competition management commands."""
        pass

    @marketmovers.command(name="leaderboard")
    async def mm_leaderboard(self, ctx):
        """Displays the fancy embed leaderboard for Market Movers."""
        cached_scores = await self.config.get_raw("cached_leaderboard")
        hard_stop = await self.config.hard_stop_time()
        last_updated = await self.config.get_raw("last_updated")
        
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
        
        time_display = f"Never updated" if last_updated == 0 else f"Updated <t:{last_updated}:R>"
        filter_display = "None (All time)" if hard_stop == 0 else f"< timestamp {hard_stop}>"
        embed.set_footer(text=f"{time_display} • Time Filter: {filter_display}")
        
        await ctx.send(embed=embed)

    @marketmovers.command(name="dump")
    async def mm_dump(self, ctx):
        """Dumps the final leaderboard text and deletes the cached data."""
        cached_scores = await self.config.get_raw("cached_leaderboard")
        
        if not cached_scores:
            await ctx.send("⚠️ The leaderboard cache is already empty.")
            return
            
        dump_lines = ["Rank | Nation | Unique Trades", "-" * 35]
        for idx, (nation, score) in enumerate(cached_scores, start=1):
            dump_lines.append(f"{idx:<4} | {nation:<20} | {score}")
            
        full_dump = "\n".join(dump_lines)
        
        if len(full_dump) > 1900:
            await ctx.send("The dump is too long to output safely in a single message.")
            return
            
        # Clear out (delete) the cached leaderboard and timestamp
        await self.config.set_raw("cached_leaderboard", value=[])
        await self.config.set_raw("last_updated", value=0)
        
        await ctx.send(f"🗑️ Leaderboard data exported and successfully **deleted** from cache:\n```text\n{full_dump}\n```")

    @marketmovers.command(name="score")
    async def mm_score(self, ctx, *, nation_name: str):
        """Looks up a specific nation's trade score and current rank."""
        cached_scores = await self.config.get_raw("cached_leaderboard")
        cleaned_target = nation_name.strip().lower()
        
        if not cached_scores:
            await ctx.send("Leaderboard cache is empty. Run `[p]marketmovers refresh` first.")
            return
            
        found_nation = None
        found_rank = None
        found_score = 0
        
        for idx, (nation, score) in enumerate(cached_scores, start=1):
            if nation.lower() == cleaned_target:
                found_nation = nation
                found_rank = idx
                found_score = score
                break
                
        if not found_nation:
            nations = await self.config.target_nations()
            if cleaned_target not in [n.lower() for n in nations]:
                await ctx.send(f"⚠️ `{nation_name}` is not currently on the competing nations roster.")
            else:
                await ctx.send(f"⚠️ `{nation_name}` is on the roster, but has `0` recorded trades in the current cache. Try running `[p]marketmovers refresh`.")
            return
            
        embed = discord.Embed(
            title=f"📊 Score Lookup: {found_nation}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Rank", value=f"#{found_rank}", inline=True)
        embed.add_field(name="Unique Trades", value=str(found_score), inline=True)
        
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

    @mm_nations.command(name="list")
    async def nations_list(self, ctx):
        """Lists all nations currently participating in the competition."""
        nations = await self.config.target_nations()
        
        if not nations:
            await ctx.send("There are currently no nations on the competition roster.")
            return
            
        embed = discord.Embed(
            title="📋 Participating Nations Roster",
            description="\n".join([f"• `{n}`" for n in sorted(nations)]),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Total competitors: {len(nations)}")
        await ctx.send(embed=embed)

    @mm_nations.command(name="add")
    async def nations_add(self, ctx, *, nation_name: str):
        """Add a nation to the competition lineup."""
        async with self.config.target_nations() as nations:
            cleaned = nation_name.strip().lower()
            if cleaned in nations:
                await ctx.send(f"⚠️ `{nation_name}` is already on the roster.")
                return
            nations.append(cleaned)
        await ctx.send(f"✅ Added `{nation_name}` to the Market Movers competition!")

    @mm_nations.command(name="remove")
    async def nations_remove(self, ctx, *, nation_name: str):
        """Remove a nation from the competition lineup."""
        async with self.config.target_nations() as nations:
            cleaned = nation_name.strip().lower()
            if cleaned not in nations:
                await ctx.send(f"⚠️ `{nation_name}` wasn't found in the competition roster.")
                return
            nations.remove(cleaned)
        await ctx.send(f"🗑️ Removed `{nation_name}` from the competition.")
