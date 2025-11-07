# waarchiver.py
# Redbot cog: World Assembly Archiver -> creates a Forum post per proposal
# Requires discord.py 2.x (bundled with Red) for ForumChannel.create_thread

from __future__ import annotations

import asyncio
import html
import re
from textwrap import wrap
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from redbot.core import commands, Config

BASE = "https://www.nationstates.net"
API = f"{BASE}/cgi-bin/api.cgi"

# Discord limits
DISCORD_MAX_FIELD = 1024
DISCORD_MAX_FIELDS_PER_EMBED = 25
DISCORD_MAX_DESC = 4096
DISCORD_MAX_EMBEDS_PER_MESSAGE = 10

COLOR_GREEN = 0x2ECC71
COLOR_RED = 0xE74C3C


def bbcode_to_discord(text: str) -> str:
    """Convert basic BBCode to Discord markdown."""
    if not text:
        return ""
    s = text

    # [url=...]...[/url]
    s = re.sub(r"\[url=(.+?)\](.*?)\[/url\]", r"[\2](\1)", s, flags=re.I | re.S)

    # styles
    s = re.sub(r"\[b\](.*?)\[/b\]", r"**\1**", s, flags=re.I | re.S)
    s = re.sub(r"\[i\](.*?)\[/i\]", r"*\1*", s, flags=re.I | re.S)   # ← added s
    s = re.sub(r"\[u\](.*?)\[/u\]", r"__\1__", s, flags=re.I | re.S) # ← added s
    s = re.sub(r"\[s\](.*?)\[/s\]", r"~~\1~~", s, flags=re.I | re.S) # ← added s

    # [quote] -> blockquote
    def _quote_repl(m):
        body = m.group(1).strip()
        return "\n".join("> " + line for line in body.splitlines())
    s = re.sub(r"\[quote\](.*?)\[/quote\]", _quote_repl, s, flags=re.I | re.S)

    # lists
    s = re.sub(r"\[list(?:=[^\]]+)?\]", "", s, flags=re.I)  # [list], [list=1], [list=a]
    s = re.sub(r"\[/list\]", "", s, flags=re.I)
    s = re.sub(r"(?m)^\s*\[\*\]\s*", "- ", s)

    # remove any leftover bbcode-ish tags
    s = re.sub(r"\[(?:/?[a-zA-Z][^\]]*)\]", "", s)
    return s



def split_text(text: str, limit: int) -> List[str]:
    """Split text to <= limit, preferring paragraph and word boundaries."""
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    for para in re.split(r"(\n{2,})", text):
        if not para:
            continue
        if len(para) > limit:
            parts.extend(wrap(para, width=limit, break_long_words=True, break_on_hyphens=False))
        else:
            parts.append(para)
    merged: List[str] = []
    cur = ""
    for p in parts:
        if not cur:
            cur = p
        elif len(cur) + len(p) <= limit:
            cur += p
        else:
            merged.append(cur)
            cur = p
    if cur:
        merged.append(cur)
    out: List[str] = []
    for m in merged:
        if len(m) <= limit:
            out.append(m)
        else:
            out.extend(wrap(m, width=limit, break_long_words=True, break_on_hyphens=False))
    return out


def clean_text(s: Optional[str]) -> str:
    if s is None:
        return ""
    return html.unescape(s).strip()


def nation_to_slug(nation: str) -> str:
    # NationStates uses underscores for spaces; leave ASCII safe
    from urllib.parse import quote

    underscored = nation.replace(" ", "_")
    return quote(underscored, safe="_")


class WAArchiver(commands.Cog):
    """Archive World Assembly resolutions as **Forum posts**."""

    __author__ = "you + ChatGPT"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xA11A011A, force_registration=True)
        default_guild = {
            "forum_wa1_channel_id": None,  # General Assembly forum channel id
            "forum_wa2_channel_id": None,  # Security Council forum channel id
            "ns_user_agent": "WellspringTools/1.0 (contact: you@example.com)",
            "discord_post_delay": 0.7,
            "continue_on_missing": True,
            # Optional memory of last posted RESID per council
            "last_posted_resid_wa1": 0,
            "last_posted_resid_wa2": 0,
        }
        self.config.register_guild(**default_guild)
        self._http: Optional[aiohttp.ClientSession] = None

    # ------------- aiohttp session -------------
    async def cog_load(self):
        if self._http is None:
            headers = {"User-Agent": "WellspringTools/1.0 (contact: you@example.com)"}
            self._http = aiohttp.ClientSession(headers=headers)

    async def cog_unload(self):
        if self._http and not self._http.closed:
            await self._http.close()

    # ------------- NS HTTP -------------
    async def ns_get(self, guild: discord.Guild, params: Dict[str, str]) -> str:
        """GET NationStates API with polite rate limiting."""
        if self._http is None or self._http.closed:
            await self.cog_load()

        ua = await self.config.guild(guild).ns_user_agent()
        # Update UA per guild before request
        self._http.headers.update({"User-Agent": ua})

        async with self._http.get(API, params=params, timeout=30) as resp:
            # Rate limiting guidance
            try:
                remaining = resp.headers.get("Ratelimit-Remaining")
                reset_time = resp.headers.get("Ratelimit-Reset")
                if remaining is not None and reset_time is not None:
                    remaining_int = int(remaining) - 10
                    reset_int = int(reset_time)
                    wait_time = (reset_int / remaining_int) if remaining_int > 0 else reset_int
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(0.5)
            except Exception:
                await asyncio.sleep(0.5)

            resp.raise_for_status()
            return await resp.text()

    # ------------- NS parsing -------------
    async def get_last_resolution_id(self, guild: discord.Guild, council: int) -> int:
        assert council in (1, 2)
        xml_text = await self.ns_get(guild, {"wa": str(council), "q": "lastresolution"})
        m = re.search(r"/page=WA_past_resolution/id=(\d+)/council=\d+", xml_text)
        if not m:
            raise RuntimeError(f"Could not parse lastresolution ID for council {council}")
        return int(m.group(1))

    async def get_resolution_xml_el(self, guild: discord.Guild, council: int, resid: int):
        import xml.etree.ElementTree as ET

        try:
            xml_text = await self.ns_get(guild, {"wa": str(council), "q": "resolution", "id": str(resid)})
        except aiohttp.ClientResponseError:
            return None
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None
        return root.find("./RESOLUTION")

    # ------------- Embed building -------------
    def build_embeds_from_resolution(self, council: int, res_el) -> List[discord.Embed]:
        # Collect tags
        tagmap: Dict[str, str] = {}
        resid = None
        name = None
        desc = None
        repealed_by = None

        for child in list(res_el):
            tag = child.tag.upper()
            val_raw = clean_text(child.text)
            val_md = bbcode_to_discord(val_raw)
            tagmap[tag] = val_md
            if tag == "RESID":
                resid = val_md
            elif tag == "NAME":
                name = val_md
            elif tag == "DESC":
                desc = val_md
            elif tag == "REPEALED_BY":
                repealed_by = val_md

        if not resid:
            resid = tagmap.get("COUNCILID", "unknown")

        title = name or f"Resolution {resid}"
        url = f"{BASE}/page=WA_past_resolution/id={resid}/council={council}"
        color = COLOR_RED if repealed_by else COLOR_GREEN

        prepared_fields: List[Tuple[str, str]] = []
        for tag, val in tagmap.items():
            if tag == "DESC":
                continue
            if tag == "PROPOSED_BY" and val:
                link = f"https://www.nationstates.net/nation={nation_to_slug(val)}"
                val = f"[{val}]({link})"
            prepared_fields.append((tag, val if val else "—"))

        # Split big fields into chunks
        exploded_fields: List[Tuple[str, str]] = []
        for tag, val in prepared_fields:
            chunks = split_text(val, DISCORD_MAX_FIELD)
            if len(chunks) == 1:
                exploded_fields.append((tag, chunks[0]))
            else:
                for i, ch in enumerate(chunks, 1):
                    exploded_fields.append((f"{tag} (part {i}/{len(chunks)})", ch))

        # Description split across embeds if needed
        desc_chunks = split_text(desc or "", DISCORD_MAX_DESC) if desc else []

        embeds: List[discord.Embed] = []
        fields_idx = 0
        desc_idx = 0
        embed_count = 0

        while fields_idx < len(exploded_fields) or desc_idx < len(desc_chunks) or embed_count == 0:
            embed_count += 1
            embed = discord.Embed(color=color)
            if embed_count == 1:
                embed.title = title[:256]
                embed.url = url

            if desc_idx < len(desc_chunks):
                embed.description = desc_chunks[desc_idx]
                desc_idx += 1

            while fields_idx < len(exploded_fields) and len(embed.fields) < DISCORD_MAX_FIELDS_PER_EMBED:
                tag, val = exploded_fields[fields_idx]
                embed.add_field(name=tag[:256], value=val[:DISCORD_MAX_FIELD], inline=False)
                fields_idx += 1

            if embed_count > 1 and not embed.title:
                embed.title = f"{title} (cont. {embed_count-1})"[:256]
                embed.url = url

            embeds.append(embed)

        return embeds

    # ------------- Posting helpers -------------
    async def _get_forum(self, guild: discord.Guild, council: int) -> discord.ForumChannel:
        chan_id = await (self.config.guild(guild).forum_wa1_channel_id() if council == 1 else self.config.guild(guild).forum_wa2_channel_id())
        if not chan_id:
            raise RuntimeError(f"Forum channel for council {council} is not configured. Use `[p]waarchive set forum {council} #forum`.")
        channel = guild.get_channel(chan_id)
        if channel is None:
            channel = await self.bot.fetch_channel(chan_id)
        if not isinstance(channel, discord.ForumChannel):
            raise RuntimeError("Configured channel is not a Forum channel.")
        return channel

    async def post_resolution_as_forum_thread(self, guild: discord.Guild, council: int, res_el) -> Optional[int]:
        """Create a forum thread for a single resolution and post embeds."""
        forum = await self._get_forum(guild, council)
        embeds = self.build_embeds_from_resolution(council, res_el)
        if not embeds:
            return None

        # First message becomes the forum post content
        title = embeds[0].title or "WA Resolution"
        # Create the thread with first embed
        created = await forum.create_thread(name=title, content=f"World Assembly Council {council}", embed=embeds[0])
        thread: discord.Thread = created.thread

        # Post any remaining embeds in batches of 10
        for i in range(1, len(embeds), DISCORD_MAX_EMBEDS_PER_MESSAGE):
            batch = embeds[i : i + DISCORD_MAX_EMBEDS_PER_MESSAGE]
            await thread.send(embeds=batch)
            await asyncio.sleep(0.4)  # gentle pacing

        return thread.id

    # ------------- Commands -------------
    @commands.group(name="waarchive", invoke_without_command=True)
    @commands.guild_only()
    async def waarchive(self, ctx: commands.Context):
        """Archive WA resolutions as Forum posts. Use subcommands."""
        guild = ctx.guild
        wa1 = await self.config.guild(guild).forum_wa1_channel_id()
        wa2 = await self.config.guild(guild).forum_wa2_channel_id()
        ua = await self.config.guild(guild).ns_user_agent()
        await ctx.send(
            f"Configured:\n"
            f"- WA1 Forum: {f'<#{wa1}>' if wa1 else 'Not set'}\n"
            f"- WA2 Forum: {f'<#{wa2}>' if wa2 else 'Not set'}\n"
            f"- User-Agent: `{ua}`\n"
            f"Subcommands: set forum, set ua, backfill, post, since"
        )

    @waarchive.group(name="set")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def wa_set(self, ctx: commands.Context):
        """Settings for WA archiver."""
        pass

    @wa_set.command(name="forum")
    async def wa_set_forum(self, ctx: commands.Context, council: int, channel: discord.ForumChannel):
        """Set the Forum channel for a council (1 or 2)."""
        if council not in (1, 2):
            return await ctx.send("Council must be 1 (GA) or 2 (SC).")
        if council == 1:
            await self.config.guild(ctx.guild).forum_wa1_channel_id.set(channel.id)
        else:
            await self.config.guild(ctx.guild).forum_wa2_channel_id.set(channel.id)
        await ctx.send(f"Set Forum for council {council} to {channel.mention}")

    @wa_set.command(name="ua")
    async def wa_set_ua(self, ctx: commands.Context, *, user_agent: str):
        """Set the NationStates API User-Agent (please make it descriptive)."""
        await self.config.guild(ctx.guild).ns_user_agent.set(user_agent.strip())
        await ctx.send("User-Agent updated.")

    @commands.command(name="wa_backfill")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def wa_backfill(self, ctx: commands.Context, council: int, count: int = 10):
        """
        Create Forum posts for the latest `count` resolutions in a council, going backward.
        Example: [p]wa_backfill 2 5
        """
        if council not in (1, 2):
            return await ctx.send("Council must be 1 (GA) or 2 (SC).")
        try:
            latest = await self.get_last_resolution_id(ctx.guild, council)
        except Exception as e:
            return await ctx.send(f"Failed to get lastresolution for council {council}: {e}")

        await ctx.send(f"Council {council}: latest RESID is **{latest}**. Backfilling {count}…")
        posted = 0
        resid = latest
        cont = await self.config.guild(ctx.guild).continue_on_missing()
        delay = await self.config.guild(ctx.guild).discord_post_delay()

        while posted < count and resid > 0:
            el = await self.get_resolution_xml_el(ctx.guild, council, resid)
            if el is None:
                if cont:
                    resid -= 1
                    continue
                else:
                    break
            try:
                await self.post_resolution_as_forum_thread(ctx.guild, council, el)
                posted += 1
            except Exception as e:
                await ctx.send(f"Error posting RESID {resid}: {e}")
            resid -= 1
            await asyncio.sleep(delay)

        await ctx.send(f"Council {council}: backfill complete. Posted {posted} thread(s).")

    @commands.command(name="wa_post")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def wa_post(self, ctx: commands.Context, council: int, resid: int):
        """Post a specific RESID as a Forum thread. Example: [p]wa_post 1 22"""
        if council not in (1, 2):
            return await ctx.send("Council must be 1 (GA) or 2 (SC).")
        el = await self.get_resolution_xml_el(ctx.guild, council, resid)
        if el is None:
            return await ctx.send("That RESID was not found.")
        try:
            thread_id = await self.post_resolution_as_forum_thread(ctx.guild, council, el)
        except Exception as e:
            return await ctx.send(f"Failed to create thread: {e}")
        await ctx.send(f"Posted council {council} RESID {resid} → thread ID `{thread_id}`")

    @commands.command(name="wa_since")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def wa_since(self, ctx: commands.Context, council: int, start_resid: int, count: int = 10):
        """
        Walk backward starting at `start_resid` for `count` threads.
        Example: [p]wa_since 2 900 20
        """
        if council not in (1, 2):
            return await ctx.send("Council must be 1 (GA) or 2 (SC).")
        await ctx.send(f"Council {council}: posting from RESID {start_resid} backward {count}…")

        posted = 0
        resid = start_resid
        cont = await self.config.guild(ctx.guild).continue_on_missing()
        delay = await self.config.guild(ctx.guild).discord_post_delay()

        while posted < count and resid > 0:
            el = await self.get_resolution_xml_el(ctx.guild, council, resid)
            if el is None:
                if cont:
                    resid -= 1
                    continue
                else:
                    break
            try:
                await self.post_resolution_as_forum_thread(ctx.guild, council, el)
                posted += 1
            except Exception as e:
                await ctx.send(f"Error posting RESID {resid}: {e}")
            resid -= 1
            await asyncio.sleep(delay)

        await ctx.send(f"Council {council}: posted {posted} thread(s).")

async def setup(bot):
    await bot.add_cog(WAArchiver(bot))
