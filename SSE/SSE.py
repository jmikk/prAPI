# elderscry.py
from __future__ import annotations
import xml.etree.ElementTree as ET
import asyncio
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import xml.etree.ElementTree as ET


NATION_LINK_RE = re.compile(r'href="nation=([a-z0-9_]+)"', re.I)
NATION_TEXT_RE = re.compile(r"@@([a-z0-9_]+)@@", re.I)


log = logging.getLogger("red.elderscry")

# ---------- Defaults ----------
DEFAULT_COMMON_FILTERS: Dict[str, str] = {
    # Feel free to trim/add; these mirror your original list
    "Issues": r"\bnew legislation\b",
    "RMB Posts": r"\bregional message board\b",
    "Embassy Activity": r"\bembassy\b",
    "Ejections": r"\bejected\b",
    "Ceased to Exist": r"\bceased? to exist\b",
    "Delegate Votes/Resolutions": r"\bresolution\b",
    "Moves": r"\brelocated from\b",
    "Influence": r"\binfluence in\b",
    "Changed Flags": r"\baltered (?:its|their) national flag\b",
    "Region Update": r"\b@@ updated\.\b",
    "Foundings": r"\bwas founded in\b",
    "Reclassified": r"\bwas reclassified from\b",
    "National Fields": r"\bchanged its national\b",
    "Agreed to Embassy": r"\bagreed to construct embassies between\b",
    "Closing Embassy": r"\bordered the closure of embassies between\b",
    "Proposed Embassy": r"\bproposed constructing embassies between\b",
    "Cancelled closure of Embassies": r"\bcancelled the closure of embassies between\b",
    "Rejected Embassy": r"\brejected a request from\b",
    "Aborted construction of embassies": r"\baborted construction of embassies between\b",
    "Embassy closed": r"\bEmbassy cancelled between\b",
    "Embassy established": r"\bEmbassy established between\b",
    "Banjects": r"\bwas ejected and banned from\b",
    "Baning": r"\bbanned .*? from the region\b",
    "Unbanning": r"\bremoved .*? from the regional ban list\b",
    "RO Rename": r"\brenamed the office held\b",
    "RO power change": r"\bgranted (.+?) authority to .*? as .*?\b",
    "World Factbook Update": r"\bupdated the World Factbook entry\b",
    "Changed Regional Banner": r"\bchanged the regional banner\b",
    "Resigned from Office": r"\bresigned as .*? of\b",
    "Renamed Office": r'\brenamed the .*? from ".*?" to .*? in\b',
    "Changed Regional Flag": r"\baltered the regional flag\b",
    "Appointed to Office": r"\bappointed .*? as .*? with authority over .*? in\b",
    "Region Passworded": r"\bpassword-protected\b",
    "Tag Added": r'\badded the tag ".*?" to\b',
    "Tag removed": r'\bremoved the tag ".*?" to\b',
    "Revoked Powers": r"\bremoved .*? authority from .*? in\b",
    "Welcome Telegram Created": r"\bcomposed a new Welcome Telegram\b",
    "Region Founded": r"\bfounded the region\b",
    "Governor's Office Named": r"\bnamed the Governor\'s office\b",
    "Dismissed from Office": r"\bdismissed .*? as .*? of\b",
    "Map Created": r"\bcreated a map\b",
    "Map Version Created": r"\bcreated a map version\b",
    "Map Updated": r"\bupdated a map to a map version\b",
    "Map Endorsed": r"\bendorsed a map\b",
    "Map Endorsement Removed": r"\bremoved its endorsement from a map\b",
    "Poll Created": r"\bcreated a new poll in\b",
    "WA Vote Cast": r"\bvoted (for|against) the World Assembly Resolution\b",
    "Census Rank Achieved": r"\bwas ranked in the Top \d+% of the world for\b",
    "WA Proposal Approved": r"\bapproved the World Assembly proposal\b",
    "Endorsement Given": r"\bendorsed @@.*?@@",
    "WA Applied": r"\bapplied to join the World Assembly\b",
    "WA Admitted": r"\bwas admitted to the World Assembly\b",
    "WA Resigned": r"\bresigned from the World Assembly\b",
    "Delegate Changed": r"\bbecame WA Delegate of\b",
    "Delegate Seized": r"\bseized the position of .*? WA Delegate from\b",
    "Delegate Lost": r"\blost WA Delegate status in\b",
    "Endorsement Withdrawn": r"\bwithdrew (?:its|their|his|her) endorsement from\b",
    "Refoundings": r"\bwas refounded in\b",
    "Custom Banner Created": r"\bcreated a custom banner\b",
    "Region Password Removed": r"\bremoved regional password protection from\b",
    "Region Updated": r"\b@@ updated\.\b",
}

MINIFLAG_RE = re.compile(r'<img src="([^"]+?)" class="miniflag"', re.I)
RMB_LINK_RE = re.compile(r'<a href="/region=([^"/]+)/page=display_region_rmb\?postid=(\d+)', re.I)
REGION_RE = re.compile(r'href="region=([a-z0-9_]+)"', re.I)
REGION_TEXT_RE = re.compile(r"%%([a-z0-9_]+)%%", re.I)

def _extract_nation_from_event(html: str, text: str) -> Optional[str]:
    m = NATION_LINK_RE.search(html or "")
    if m:
        return m.group(1).lower()
    m2 = NATION_TEXT_RE.search(text or "")
    if m2:
        return m2.group(1).lower()
    return None

def _primary_region_from_event(html: str, text: str) -> Optional[str]:
    # Prefer destination on "relocated from ... to ..." (text)
    m_txt = re.search(r"relocated\s+from\s+%%[a-z0-9_]+%%\s+to\s+%%([a-z0-9_]+)%%", text or "", re.I)
    if m_txt:
        return m_txt.group(1).lower()

    # Prefer destination on "relocated ... to ..." (html)
    m_html = re.search(r"\bto\s*<a\s+href=\"region=([a-z0-9_]+)\"", html or "", re.I)
    if m_html:
        return m_html.group(1).lower()

    # Otherwise pick the last region reference if any
    regions_html = re.findall(r'href="region=([a-z0-9_]+)"', html or "", re.I)
    if regions_html:
        return regions_html[-1].lower()

    regions_txt = re.findall(r"%%([a-z0-9_]+)%%", text or "", re.I)
    if regions_txt:
        return regions_txt[-1].lower()

    return None


def _regions_from_event(html: str, text: str) -> set[str]:
    """Return all region slugs referenced in the event (origin + destination if present)."""
    regions: set[str] = set()

    # HTML links
    for r in re.findall(r'href="region=([a-z0-9_]+)"', html or "", re.I):
        regions.add(r.lower())

    # Text tokens
    for r in re.findall(r"%%([a-z0-9_]+)%%", text or "", re.I):
        regions.add(r.lower())

    return regions


def _extract_region_from_event(html: str, text: str) -> Optional[str]:
    m = REGION_RE.search(html or "")
    if m:
        return m.group(1).lower()
    m2 = REGION_TEXT_RE.search(text or "")
    if m2:
        return m2.group(1).lower()
    return None


def ns_norm(s: str) -> str:
    return re.sub(r"\s+", "_", s.strip().lower())

def hyperlink_ns(text: str) -> str:
    # @@Nation@@
    text = re.sub(
        r"@@(.*?)@@",
        lambda m: f"[{m.group(1)}](https://www.nationstates.net/nation={ns_norm(m.group(1))})",
        text,
    )
    # %%Region%%
    text = re.sub(
        r"%%(.*?)%%",
        lambda m: f"[{m.group(1)}](https://www.nationstates.net/region={ns_norm(m.group(1))})",
        text,
    )
    return text

def _parse_regions_csv(csv_str: str) -> List[str]:
    regions = [ns_norm(r) for r in (csv_str or "").split(",") if r.strip()]
    return list(dict.fromkeys(regions))  # dedup, keep order

class SSE(commands.Cog):
    """NationStates SSE multiplexer: one stream, many filters/webhooks/mentions."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543456787654, force_registration=True)
        self.session: Optional[aiohttp.ClientSession] = None
        self.listener_task: Optional[asyncio.Task] = None
        self.last_event_at: Optional[datetime] = None
        self._region_nations_cache: Dict[str, Tuple[set[str], float]] = {}
        self._cache_ttl_seconds: int = 9000  

        default_guild = {
            "regions": [],                     # list of region slugs (lowercase, underscores). If empty, no listener.
            "default_webhook": "",             # fallback webhook (https://discord.com/api/webhooks/...)
            "user_agent": "",                  # NS UA string
            "enabled": False,                  # start/stop toggle
            "filters": [],
            "route_unmatched_to_default": True,# list of dicts: pattern, color (int), role_id (int|None), webhook (str|None), name (str|None)
        }
        self.config.register_guild(**default_guild)

    # ------------- Lifecycle -------------
    async def cog_load(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None))
        # Autostart for guilds that have enabled
        if any(await self._guild_enabled_any()):
            self.listener_task = asyncio.create_task(self._run_listener(), name="Elderscry_SSE")

    async def cog_unload(self):
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
        if self.session:
            await self.session.close()

    async def _fetch_region_nations(self, region_slug: str) -> set[str]:
        """Fetch nations in a region via q=nations and return a set of normalized nation slugs."""
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?region={region_slug}&q=nations"
        headers = {"User-Agent": await self._pick_any_user_agent()}
        try:
            async with self.session.get(url, headers=headers) as resp:
                txt = await resp.text()
        except Exception:
            log.exception("Failed fetching region nations for %s", region_slug)
            return set()

        try:
            root = ET.fromstring(txt)
            # API returns colon-separated list inside <NATIONS>...</NATIONS>
            # (Your example had a typo </NATION>; the real tag is NATIONS)
            payload = root.findtext(".//NATIONS") or ""
            items = [ns_norm(x) for x in payload.split(":") if x]
            return set(items)
        except Exception:
            log.exception("Failed parsing region nations for %s", region_slug)
            return set()

    def _cache_valid(self, region_slug: str) -> bool:
        if region_slug not in self._region_nations_cache:
            return False
        _, ts = self._region_nations_cache[region_slug]
        return (datetime.now(timezone.utc).timestamp() - ts) < self._cache_ttl_seconds
    
    async def _ensure_region_cache(self, region_slug: str, force: bool = False) -> set[str]:
        if not force and self._cache_valid(region_slug):
            return self._region_nations_cache[region_slug][0]
        data = await self._fetch_region_nations(region_slug)
        self._region_nations_cache[region_slug] = (data, datetime.now(timezone.utc).timestamp())
        return data
    
    async def _region_for_nation_via_caches(self, nation_slug: str) -> Optional[str]:
        """
        Try to infer a region by checking caches for every enabled guild’s watched regions.
        1) Check valid caches first.
        2) If not found, refresh each region once and re-check.
        """
        # Union of watched regions across enabled guilds
        regions: List[str] = []
        for g in self.bot.guilds:
            if not await self.config.guild(g).enabled():
                continue
            regions.extend((await self.config.guild(g).regions()) or [])
        regions = list(dict.fromkeys(regions))  # dedup, keep order
        if not regions:
            return None
    
        # Pass 1: warm/valid caches
        for r in regions:
            data = await self._ensure_region_cache(r, force=False)
            if nation_slug in data:
                return r
    
        # Pass 2: force refresh and re-check
        for r in regions:
            data = await self._ensure_region_cache(r, force=True)
            if nation_slug in data:
                return r
    
        return None


    async def _guild_enabled_any(self) -> List[bool]:
        flags = []
        for g in self.bot.guilds:
            flags.append(await self.config.guild(g).enabled())
        return flags

    # ------------- SSE Core -------------
    async def _sse_url_and_headers(self) -> Tuple[Optional[str], Dict[str, str]]:
        # Build combined regions across all guilds that are enabled
        regions: List[str] = []
        uas: List[str] = []
        for g in self.bot.guilds:
            if not await self.config.guild(g).enabled():
                continue
            rs = [ns_norm(r) for r in (await self.config.guild(g).regions()) or []]
            if rs:
                regions.extend(rs)
            ua = await self.config.guild(g).user_agent()
            if ua:
                uas.append(ua)

        # Dedup regions
        regions = sorted(set(r for r in regions if r))
        if not regions:
            return None, {}

        # Build UA: pick first configured UA or safe default
        ua = uas[0] if uas else "Elderscry/1.0 (contact: your-discord#0000)"

        url = "https://www.nationstates.net/api/" + "+".join(f"region:{r}" for r in regions)
        headers = {"User-Agent": ua}
        return url, headers

    async def _run_listener(self):
        backoff = 3
        idle_limit = timedelta(hours=1)

        while True:
            try:
                url, headers = await self._sse_url_and_headers()
                if not url:
                    # Sleep until any guild enables with at least one region
                    await asyncio.sleep(10)
                    continue

                log.info("Elderscry connecting: %s", url)
                async with self.session.get(url, headers=headers) as resp:
                    resp.raise_for_status()
                    self.last_event_at = datetime.now(timezone.utc)

                    async for raw_line in resp.content:
                        # Idle watchdog
                        if self.last_event_at and datetime.now(timezone.utc) - self.last_event_at > idle_limit:
                            log.warning("Elderscry SSE idle > 1h -> reconnect")
                            break

                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if line == "":
                            self.last_event_at = datetime.now(timezone.utc)
                            continue
                        if line.startswith(":"):
                            self.last_event_at = datetime.now(timezone.utc)
                            continue

                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            self.last_event_at = datetime.now(timezone.utc)
                            await self._handle_event(payload)
                            continue

                        if line.startswith(("event:", "id:", "retry:")):
                            self.last_event_at = datetime.now(timezone.utc)
                            continue

                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Elderscry SSE error")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ------------- Event Handling -------------
    async def _handle_event(self, data_line: str):
        try:
            data = json.loads(data_line)
        except json.JSONDecodeError:
            return

        html = data.get("htmlStr") or ""
        text = data.get("str") or ""

        # RMB?
        m_rmb = RMB_LINK_RE.search(html)
        if m_rmb:
            region = m_rmb.group(1)
            post_id = m_rmb.group(2)
            await self._process_rmb(region, post_id, data)
            return

        # Normal filter-based event
        await self._process_filtered_event(data)

    async def _process_rmb(self, region_slug: str, post_id: str, data: dict):
        # Fetch message XML
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?region={region_slug}&q=messages&fromid={post_id}"
        headers = {"User-Agent": await self._pick_any_user_agent()}

        try:
            async with self.session.get(url, headers=headers) as resp:
                xml_text = await resp.text()
        except Exception:
            log.exception("RMB fetch failed")
            return

        try:
            root = ET.fromstring(xml_text)
            post_elem = root.find(".//POST")
            if post_elem is None:
                return

            message_text = (post_elem.findtext("MESSAGE") or "")
            nation = (post_elem.findtext("NATION") or "Unknown")
            # Simple BBCode -> Markdown
            message_text = (message_text.replace("[i]", "*").replace("[/i]", "*")
                                       .replace("[b]", "**").replace("[/b]", "**"))

            quotes = re.findall(r"\[quote=(.*?);(\d+)](.*?)\[/quote]", message_text, re.DOTALL)
            clean_text = re.sub(r"\[quote=(.*?);(\d+)](.*?)\[/quote]", "", message_text, flags=re.DOTALL).strip()

            # Flag
            flag_url = self._flag_from_html(data.get("htmlStr") or "")

            # Build embed
            embed = discord.Embed(
                title="New RMB Post",
                url=f"https://www.nationstates.net/region={region_slug}/page=display_region_rmb?postid={post_id}#p{post_id}",
                colour=discord.Colour(0x3498DB),
                timestamp=datetime.fromtimestamp(data.get("time", int(datetime.now(timezone.utc).timestamp())), tz=timezone.utc)
            )
            if flag_url:
                embed.set_thumbnail(url=flag_url)

            # Quotes
            for author, _, quote in quotes[:5]:
                if quote.strip():
                    embed.add_field(name=f"Quoted from {author}", value=quote.strip()[:1024], inline=False)

            # Body
            if clean_text:
                embed.add_field(name="Message", value=clean_text[:1024], inline=False)

            embed.set_footer(text=f"Posted by {nation} — https://www.nationstates.net/nation={ns_norm(nation)}")

            # Route to all guilds that are watching this region and have RMB Posts filter enabled (or a general catch-all)
            await self._broadcast_embeds(
                [embed],
                event_text=data.get("str", ""),
                prefer_filter_name="RMB Posts",
                region=region_slug.lower(),
            )
        except Exception:
            log.exception("RMB parse failed")
    s
    



    # ------------- Utils -------------
    
    def _flag_from_html(self, html: str) -> Optional[str]:
        m = MINIFLAG_RE.search(html)
        if not m:
            return None
        # normalize .svg and t2.png to .png
        rel = m.group(1).replace(".svg", ".png").replace("t2.png", ".png")
        return f"https://www.nationstates.net{rel}"

    def _smart_title_desc(self, event_str: str) -> Tuple[str, str]:
        # Keep your original “smart” fallback; otherwise just use raw
        m = re.match(r"(.*) in @@(\w+)@@, (.+)", event_str)
        if m:
            title = f"{m.group(1)} in {m.group(2).capitalize().replace('_',' ')}"
            desc = m.group(3).capitalize()
        else:
            title = "NationStates Event"
            desc = event_str
        return title, desc

    async def _post_webhook(self, webhook: str, content: Optional[str], embeds: List[discord.Embed]):
        if not webhook:
            return
        try:
            async with self.session.post(webhook, json={
                "content": content or "",
                "embeds": [e.to_dict() for e in embeds]
            }) as resp:
                if resp.status not in (200, 204):
                    txt = await resp.text()
                    log.warning("Webhook post %s -> %s %s", webhook[-32:], resp.status, txt[:200])
        except Exception:
            log.exception("Webhook post failed")

    async def _pick_any_user_agent(self) -> str:
        for g in self.bot.guilds:
            ua = await self.config.guild(g).user_agent()
            if ua:
                return ua
        return "Elderscry/1.0 (contact: your-discord#0000)"

    async def _broadcast_embeds(self, embeds: List[discord.Embed], event_text: str, prefer_filter_name: Optional[str] = None,region: Optional[str] = None):
        """
        Send embeds to every guild that is enabled, to each matching filter.
        If prefer_filter_name is provided, we first try filters whose `name` equals it;
        fallback to any filters whose regex matches the event_text.
        """
        tasks = []
        for guild in self.bot.guilds:
            if not await self.config.guild(guild).enabled():
                continue
            filters = await self.config.guild(guild).filters()
            default_webhook = await self.config.guild(guild).default_webhook()
            if not default_webhook and not any(f.get("webhook") for f in filters):
                continue

            # Try preferred named filter first
            target_filters = []
            if prefer_filter_name:
                for f in filters:
                    if f.get("name") != prefer_filter_name:
                        continue
                    # Region scoping: if filter has regions, require the event's region to be in them.
                    regs = [r.strip().lower() for r in (f.get("regions") or []) if r]
                    if regs:
                        if region and region.lower() in regs:
                            target_filters.append(f)
                        # if the filter is region-scoped but we don't know the region, skip it
                    else:
                        # no region restriction on this filter
                        target_filters.append(f)
                         
            if not target_filters:
                # fallback: any filter whose regex matches
                for f in filters:
                    patt = f.get("pattern") or ""
                    try:
                        if patt and re.search(patt, event_text, re.I):
                            # apply the same region scoping on regex-matched filters
                            regs = [r.strip().lower() for r in (f.get("regions") or []) if r]
                            if regs:
                                if region and region.lower() in regs:
                                    target_filters.append(f)
                            else:
                                target_filters.append(f)

                    
                    except re.error:
                        continue

            for f in target_filters or []:
                color = int(f.get("color") or 0x3498DB)
                role_id = f.get("role_id")
                webhook = f.get("webhook") or default_webhook
                if not webhook:
                    continue

                # copy embeds to adjust colour if needed
                adj = []
                for e in embeds:
                    e2 = discord.Embed.from_dict(e.to_dict())
                    e2.colour = discord.Colour(color)
                    adj.append(e2)

                content = f"<@&{role_id}>" if role_id else None
                tasks.append(self._post_webhook(webhook, content, adj))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------- Commands -------------
    @commands.group(name="elderscry")
    @checks.admin_or_permissions(manage_guild=True)
    async def es_group(self, ctx: commands.Context):
        """Elderscry controls."""
        pass

    @es_group.command(name="enable")
    async def es_enable(self, ctx: commands.Context, enabled: bool):
        await self.config.guild(ctx.guild).enabled.set(bool(enabled))
        await ctx.send(f"Elderscry is now **{'ON' if enabled else 'OFF'}**.")
        # Start/stop global task as needed
        if enabled:
            if not (self.listener_task and not self.listener_task.done()):
                self.listener_task = asyncio.create_task(self._run_listener(), name="Elderscry_SSE")
        else:
            # If all guilds disabled, stop the task
            if self.listener_task and not any(await self._guild_enabled_any()):
                self.listener_task.cancel()

    @es_group.command(name="setua")
    async def es_setua(self, ctx: commands.Context, *, user_agent: str):
        await self.config.guild(ctx.guild).user_agent.set(user_agent.strip())
        await ctx.send("User-Agent updated.")

    @es_group.group(name="region", invoke_without_command=True)
    async def es_region(self, ctx: commands.Context):
        regions = await self.config.guild(ctx.guild).regions()
        await ctx.send("Regions: " + (", ".join(regions) if regions else "_none_"))

    @es_region.command(name="add")
    async def es_region_add(self, ctx: commands.Context, *, region: str):
        r = ns_norm(region)
        async with self.config.guild(ctx.guild).regions() as rs:
            if r not in rs:
                rs.append(r)
        await ctx.send(f"Added region `{r}`.")

    @es_region.command(name="remove")
    async def es_region_remove(self, ctx: commands.Context, *, region: str):
        r = ns_norm(region)
        async with self.config.guild(ctx.guild).regions() as rs:
            if r in rs:
                rs.remove(r)
        await ctx.send(f"Removed region `{r}`.")

    @es_region.command(name="clear")
    async def es_region_clear(self, ctx: commands.Context):
        await self.config.guild(ctx.guild).regions.set([])
        await ctx.send("Cleared regions.")

    @es_group.command(name="setwebhook")
    async def es_setwebhook(self, ctx: commands.Context, webhook: str):
        await self.config.guild(ctx.guild).default_webhook.set(webhook.strip())
        await ctx.send("Default webhook set.")

    @es_group.group(name="filters", invoke_without_command=True)
    async def es_filters(self, ctx: commands.Context):
        filters = await self.config.guild(ctx.guild).filters()
        if not filters:
            await ctx.send("No filters set.")
            return
        lines = []
        for i, f in enumerate(filters, start=1):
            nm = f.get("name") or ""
            patt = f.get("pattern") or ""
            col = f.get("color")
            role = f.get("role_id")
            wh  = f.get("webhook")
            lines.append(f"**{i}.** {nm or '(unnamed)'} | /{patt}/ | color {col} | role {role} | webhook {'set' if wh else 'default'}")
        await ctx.send("\n".join(lines[:50]))
    
    @es_filters.command(name="add")
    async def es_filters_add(
        self,
        ctx: commands.Context,
        pattern: str,
        color: int,
        regions_csv: str,
        role_id: Optional[int] = None,
        webhook: Optional[str] = None,
        *,
        name: Optional[str] = None,
    ):
        """
        Add a filter (regions are REQUIRED).
    
        Usage:
          [p]elderscry filters add "<regex>" <color> "<regions_csv>" [role_id] [webhook] [-- trailing name]
    
        Examples:
          [p]elderscry filters add "(?i)was founded in" 3447003 "Osiris, The East Pacific" 123456789012345678 https://discord.com/api/webhooks/... -- Foundings
          [p]elderscry filters add "(?i)embassy" 15105570 "10000 Islands" -- Embassies
        """
        regions = _parse_regions_csv(regions_csv)
        if not regions:
            await ctx.send("❌ You must provide at least one region (comma-separated).")
            return
    
        # Optional: warn if region not in configured watch list (does not block creation)
        configured = set(await self.config.guild(ctx.guild).regions())
        unknown = [r for r in regions if r not in configured]
        if unknown:
            await ctx.send(
                "⚠️ The following regions are not in your current watch list: "
                + ", ".join(f"`{r}`" for r in unknown)
                + "\nThey will still be saved, but won’t match until you add them with "
                  "`[p]elderscry region add ...` or enable them in your config."
            )
    
        entry = {
            "pattern": pattern,
            "color": int(color),
            "role_id": role_id,
            "webhook": webhook,
            "name": name,
            "regions": regions,
        }
        async with self.config.guild(ctx.guild).filters() as fs:
            fs.append(entry)
    
        await ctx.send(
            f"✅ Filter added for regions: {', '.join(regions)}"
            + (f" • name: **{name}**" if name else "")
        )



    @es_filters.command(name="remove")
    async def es_filters_remove(self, ctx: commands.Context, index: int):
        async with self.config.guild(ctx.guild).filters() as fs:
            if 1 <= index <= len(fs):
                fs.pop(index - 1)
                await ctx.send("Filter removed.")
            else:
                await ctx.send("Invalid index.")

    @es_filters.command(name="addcommon")
    async def es_filters_addcommon(
        self,
        ctx: commands.Context,
        common_name: str,
        color: int,
        regions_csv: str,
        role_id: Optional[int] = None,
        webhook: Optional[str] = None,
    ):
        """
        Add a predefined common filter by name (regions are REQUIRED).
    
        Usage:
          [p]elderscry filters addcommon <CommonName> <color> "<regions_csv>" [role_id] [webhook]
    
        Example:
          [p]elderscry filters addcommon Foundings 3447003 "Osiris, The East Pacific"
        """
        patt = DEFAULT_COMMON_FILTERS.get(common_name)
        if not patt:
            await ctx.send("❌ Unknown common filter name. Use `[p]elderscry common` to see options.")
            return
    
        regions = _parse_regions_csv(regions_csv)
        if not regions:
            await ctx.send("❌ You must provide at least one region (comma-separated).")
            return
    
        # Optional: warn if region not in configured watch list (does not block creation)
        configured = set(await self.config.guild(ctx.guild).regions())
        unknown = [r for r in regions if r not in configured]
        if unknown:
            await ctx.send(
                "⚠️ The following regions are not in your current watch list: "
                + ", ".join(f"`{r}`" for r in unknown)
                + "\nThey will still be saved, but won’t match until you add them with "
                  "`[p]elderscry region add ...` or enable them in your config."
            )
    
        entry = {
            "pattern": patt,
            "color": int(color),
            "role_id": role_id,
            "webhook": webhook,
            "name": common_name,
            "regions": regions,
        }
        async with self.config.guild(ctx.guild).filters() as fs:
            fs.append(entry)
    
        await ctx.send(
            f"✅ Common filter **{common_name}** added for regions: {', '.join(regions)}"
        )


    @es_group.group(name="common", invoke_without_command=True)
    async def es_common(self, ctx: commands.Context):
        names = ", ".join(DEFAULT_COMMON_FILTERS.keys())
        await ctx.send(f"Common filters available:\n{names}")

    @es_group.command(name="status")
    async def es_status(self, ctx: commands.Context):
        regions = await self.config.guild(ctx.guild).regions()
        wh = await self.config.guild(ctx.guild).default_webhook()
        ua = await self.config.guild(ctx.guild).user_agent()
        enabled = await self.config.guild(ctx.guild).enabled()
        last = self.last_event_at
        last_str = f"<t:{int(last.timestamp())}:R>" if last else "—"
        await ctx.send(
            f"**Elderscry**: {'ON' if enabled else 'OFF'}\n"
            f"Regions: {', '.join(regions) if regions else '_none_'}\n"
            f"Default Webhook: {'set' if wh else 'not set'}\n"
            f"User-Agent: `{ua or '—'}`\n"
            f"Last activity: {last_str}"
        )

    @es_group.command(name="test")
    async def es_test(self, ctx: commands.Context, *, text: str):
        """Quick test: runs filters on arbitrary text and sends to matching webhooks."""
        fake_data = {
            "str": text,
            "htmlStr": "",
            "time": int(datetime.now(timezone.utc).timestamp()),
            "id": "test-" + datetime.now(timezone.utc).isoformat()
        }
        await self._process_filtered_event(fake_data)
        await ctx.send("Test dispatched to matching filters.")

    @es_filters.command(name="setregions")
    async def es_filters_setregions(self, ctx: commands.Context, index: int, *, regions_csv: str):
        """
        Set a filter's region scope with a comma-separated list of region slugs/names.
        Example: [p]elderscry filters setregions 2 Osiris, The East Pacific
        """
        async with self.config.guild(ctx.guild).filters() as fs:
            if not (1 <= index <= len(fs)):
                await ctx.send("Invalid filter index.")
                return
            regions = [ns_norm(r) for r in regions_csv.split(",") if r.strip()]
            fs[index - 1]["regions"] = regions
        await ctx.send(f"Filter {index} regions set to: {', '.join(regions) if regions else 'ALL'}")
    
    @es_group.command(name="fallback")
    async def es_fallback(self, ctx: commands.Context, enabled: bool):
        """Enable/disable routing unmatched events to the default webhook."""
        await self.config.guild(ctx.guild).route_unmatched_to_default.set(bool(enabled))
        await ctx.send(f"Unmatched → default webhook is now **{'ON' if enabled else 'OFF'}**.")

    @es_filters.command(name="list")
    async def es_filters_list(self, ctx: commands.Context):
        filters = await self.config.guild(ctx.guild).filters()
        if not filters:
            await ctx.send("No filters set.")
            return
        lines = []
        for i, f in enumerate(filters, start=1):
            nm = f.get("name") or "(unnamed)"
            patt = f.get("pattern") or ""
            col = f.get("color")
            role = f.get("role_id")
            wh  = f.get("webhook")
            regs = ", ".join(f.get("regions") or []) or "ALL"
            lines.append(
                f"**{i}.** {nm} | /{patt}/ | color {col} | role {role} | webhook {'custom' if wh else 'default'} | regions: {regs}"
            )
        await ctx.send("\n".join(lines[:50]))



# ---- setup ----
async def setup(bot: Red):
    await bot.add_cog(Elderscry(bot))
