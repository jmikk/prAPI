import discord
import asyncio
import json
import re
import logging
from redbot.core import commands, Config
from aiohttp_sse_client import client as sse_client

log = logging.getLogger("red.nsevents")

class SSE(commands.Cog):
    """NationStates SSE Watcher with Region Filtering"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        default_global = {
            "channel_id": None,
            "user_agent": "Redbot Cog - Operator: Unknown",
            "rules": [], 
        }
        self.config.register_global(**default_global)
        self.task = None
        self.url = "https://www.nationstates.net/api/rmb+moves+founding+cte+vote+resolution+member"

    def cog_unload(self):
        if self.task:
            self.task.cancel()

    async def cog_load(self):
        self.task = asyncio.create_task(self.sse_listener())

    def clean_ns_text(self, text: str) -> str:
        """Hyperlinks nations/regions and cleans BBCode."""
        if not text: return ""
        # Nations/Regions to Markdown Links
        text = re.sub(r"@@(.[^@]+)@@", r"[\1](https://www.nationstates.net/nation=\1)", text)
        text = re.sub(r"%%(.[^%]+)%%", r"[\1](https://www.nationstates.net/region=\1)", text)
        
        # BBCode cleaning
        text = re.sub(r"\[b\](.*?)\[/b\]", r"**\1**", text, flags=re.I)
        text = re.sub(r"\[quote=.*?\](.*?)\[/quote\]", r"> \1", text, flags=re.S | re.I)
        
        # Clean underscores in display names only (not URLs)
        # This is a bit tricky, so we just replace underscores in the bracketed labels
        text = re.sub(r"\[(.*?)\]\(", lambda m: f"[{m.group(1).replace('_', ' ')}](", text)
        return text

    async def sse_listener(self):
        await self.bot.wait_until_ready()
        while True:
            ua = await self.config.user_agent()
            headers = {'User-Agent': ua}
            try:
                async with sse_client.EventSource(self.url, headers=headers, timeout=0) as event_source:
                    async for event in event_source:
                        if event.data:
                            try:
                                await self.process_event(json.loads(event.data))
                            except: continue
            except Exception as e:
                log.error(f"SSE Error: {e}")
                await asyncio.sleep(10)

    async def process_event(self, data: dict):
        chan_id = await self.config.channel_id()
        channel = self.bot.get_channel(chan_id)
        if not channel: return

        raw_str = data.get("str", "")
        buckets = data.get("buckets", [])
        rules = await self.config.rules()

        for rule in rules:
            # Check Regex first
            if not re.search(rule["regex"], raw_str, re.IGNORECASE):
                continue
            
            # Check Region Filter (if specified in rule)
            filter_region = rule.get("region")
            if filter_region:
                # Format check: "The North Pacific" -> "region:the_north_pacific"
                target_bucket = f"region:{filter_region.lower().replace(' ', '_')}"
                if target_bucket not in buckets:
                    continue

            # Build Embed
            t = rule["template"]
            clean_str = self.clean_ns_text(raw_str)
            rmb_msg = self.clean_ns_text(data.get("rmbMessage", ""))

            embed = discord.Embed(
                title=t.get("title", "NS Event").replace("{id}", data.get("id", "")),
                description=t.get("description", "{str}").replace("{str}", clean_str).replace("{message}", rmb_msg),
                color=t.get("color", 0x3498db)
            )
            if "footer" in t:
                embed.set_footer(text=t["footer"].replace("{time}", data.get("time", "")))
            
            await channel.send(embed=embed)
            break

    @commands.group()
    @commands.is_owner()
    async def nset(self, ctx):
        """Settings for NationStates SSE"""
        pass

    @nset.command()
    async def addrule(self, ctx, regex: str, region: str, *, template_json: str):
        """
        Add a rule with a region filter. Use 'None' for no region filter.
        Example: [p]nset addrule "founded" "The North Pacific" {"title": "New TNP Nation", "color": 3066993}
        """
        try:
            template = json.loads(template_json)
            region_val = None if region.lower() == "none" else region
            async with self.config.rules() as rules:
                rules.append({"regex": regex, "region": region_val, "template": template})
            await ctx.send(f"Rule added for region: {region_val or 'Any'}")
        except json.JSONDecodeError:
            await ctx.send("Invalid JSON template.")

    @nset.command()
    async def clear(self, ctx):
        """Clear all rules."""
        await self.config.rules.set([])
        await ctx.send("Rules cleared.")

    @nset.command()
    async def ua(self, ctx, *, ua: str):
        """Set User-Agent (include nation/email)."""
        await self.config.user_agent.set(ua)
        await ctx.send("User-Agent updated.")

    @nset.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Set output channel."""
        await self.config.channel_id.set(channel.id)
        await ctx.send(f"Target set to {channel.mention}")
