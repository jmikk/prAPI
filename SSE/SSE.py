# elderscry.py
from __future__ import annotations

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

log = logging.getLogger("red.elderscry")

# ---------- Defaults ----------
DEFAULT_COMMON_FILTERS: Dict[str, str] = {
    # Feel free to trim/add; these mirror your original list
    "Issues Answered (Legislation)": r"\bnew legislation\b",
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

class Elderscry(commands.Cog):
    """NationStates SSE multiplexer: one stream, many filters/webhooks/mentions."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xE1D3_5CRY, force_registration=True)
        self.session: Optional[aiohttp.ClientSession] = None
        self.listener_task: Optional[asyncio.Task] = None
        self.last_event_at: Optional[datetime] = None

        default_guild = {
            "regions": [],                     # list of region slugs (lowercase, underscores). If empty, no listener.
            "default_webhook": "",             # fallback webhook (https://discord.com/api/webhooks/...)
            "user_agent": "",                  # NS UA string
            "enabled": False,                  # start/stop toggle
            "filters": [],                     # list of dicts: pattern, color (int), role_id (int|None), webhook (str|None), name (str|None)
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
            await self._broadcast_embeds([embed], event_text=data.get("str",""), prefer_filter_name="RMB Posts")

        except Exception:
            log.exception("RMB parse failed")

    async def _process_filtered_event(self, data: dict):
        event_str = data.get("str", "")
        html = data.get("htmlStr", "")

        # Flag
        flag_url = self._flag_from_html(html)

        # Build generic embed (we’ll adjust colour/role/webhook per-filter match)
        title, desc = self._smart_title_desc(event_str)
        title, desc = hyperlink_ns(title), hyperlink_ns(desc)

        # Scan filters in every guild; send to each matched destination
        tasks = []
        for guild in self.bot.guilds:
            if not await self.config.guild(guild).enabled():
                continue

            filters = await self.config.guild(guild).filters()
            default_webhook = await self.config.guild(guild).default_webhook()
            if not default_webhook and not any(f.get("webhook") for f in filters):
                # No place to send; skip this guild
                continue

            matched_any = False
            for f in filters:
                patt = f.get("pattern") or ""
                try:
                    if not patt or not re.search(patt, event_str, re.I):
                        continue
                except re.error:
                    # bad regex; skip
                    continue

                matched_any = True
                color = int(f.get("color") or 0x5865F2)
                role_id = f.get("role_id")
                webhook = f.get("webhook") or default_webhook

                if not webhook:
                    continue

                embed = discord.Embed(
                    title=title or "NationStates Event",
                    description=desc or event_str,
                    colour=discord.Colour(color),
                    timestamp=datetime.fromtimestamp(
                        data.get("time", int(datetime.now(timezone.utc).timestamp())),
                        tz=timezone.utc,
                    ),
                )
                if flag_url:
                    embed.set_thumbnail(url=flag_url)
                embed.set_footer(text=f"Event ID: {data.get('id','N/A')}")

                content = f"<@&{role_id}>" if role_id else None
                tasks.append(self._post_webhook(webhook, content, [embed]))

            # Optional “no filter matched” path? (Disabled by default)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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

    async def _broadcast_embeds(self, embeds: List[discord.Embed], event_text: str, prefer_filter_name: Optional[str] = None):
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
                target_filters = [f for f in filters if (f.get("name") == prefer_filter_name)]
            if not target_filters:
                # fallback: any filter whose regex matches
                for f in filters:
                    patt = f.get("pattern") or ""
                    try:
                        if patt and re.search(patt, event_text, re.I):
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
    async def es_filters_add(self, ctx: commands.Context, pattern: str, color: int, role_id: Optional[int] = None, webhook: Optional[str] = None, *, name: Optional[str] = None):
        """Add a filter. Example:
        [p]elderscry filters add "(?i)was founded in" 3447003 123456789012345678 https://... --name Foundings
        """
        entry = {"pattern": pattern, "color": int(color), "role_id": role_id, "webhook": webhook, "name": name}
        async with self.config.guild(ctx.guild).filters() as fs:
            fs.append(entry)
        await ctx.send("Filter added.")

    @es_filters.command(name="remove")
    async def es_filters_remove(self, ctx: commands.Context, index: int):
        async with self.config.guild(ctx.guild).filters() as fs:
            if 1 <= index <= len(fs):
                fs.pop(index - 1)
                await ctx.send("Filter removed.")
            else:
                await ctx.send("Invalid index.")

    @es_filters.command(name="addcommon")
    async def es_filters_addcommon(self, ctx: commands.Context, common_name: str, color: int, role_id: Optional[int] = None, webhook: Optional[str] = None):
        """Add a predefined common filter by name (see list)."""
        patt = DEFAULT_COMMON_FILTERS.get(common_name)
        if not patt:
            await ctx.send("Unknown common filter name. Use [p]elderscry common list")
            return
        entry = {"pattern": patt, "color": int(color), "role_id": role_id, "webhook": webhook, "name": common_name}
        async with self.config.guild(ctx.guild).filters() as fs:
            fs.append(entry)
        await ctx.send(f"Common filter '{common_name}' added.")

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

# ---- setup ----
async def setup(bot: Red):
    await bot.add_cog(Elderscry(bot))
