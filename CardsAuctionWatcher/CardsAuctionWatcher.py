import asyncio
import logging
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import time
import aiohttp
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from datetime import datetime, timezone

log = logging.getLogger("red.cards_auction_pinger")

NS_BASE = "https://www.nationstates.net/cgi-bin/api.cgi"

def parse_int(s: Optional[str], default: int = 0) -> int:
    try:
        return int(s) if s is not None else default
    except Exception:
        return default

class CardsAuctionWatcher(commands.Cog):
    """
    Minimal watcher: fetch auctions once per cycle.
    If a watched card (cardid:season) is present, DM watchers with a single embed.
    Rate-limit per (user, card) to once every cooldown window (default 3 hours).
    """

    __author__ = "you"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="sdxfcgvhbjnk", force_registration=True)

        default_global = {
            "enabled": False,
            "interval_minutes": 15,
            "cooldown_seconds": 3 * 60 * 60,  # 3 hours
            "user_agent": "9003",  # set your UA; change if you prefer
            # key = "cardid:season" -> [user_id, ...]
            "watch_index": {},  # Dict[str, List[int]]
        }
        self.config.register_global(**default_global)
        self.config.register_user(
            watchlist=[],            # List[str] of "cardid:season"
            last_notified={},        # Dict[str, int] (unix ts) per key
        )

        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None

    # -------- lifecycle --------

    async def cog_load(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        if await self.config.enabled():
            await self._ensure_task()

    async def cog_unload(self):
        if self._task and not self._task.done():
            self._task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _ensure_task(self):
        if self._task and not self._task.done():
            return
        self._task = self.bot.loop.create_task(self._runner())

    async def _runner(self):
        while True:
            try:
                if not await self.config.enabled():
                    await asyncio.sleep(30)
                    continue

                await self._run_once()
                minutes = await self.config.interval_minutes()
                await asyncio.sleep(max(1, minutes) * 60)

            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("CardsAuctionPinger loop error")
                await asyncio.sleep(30)

    # -------- core logic --------

    async def _run_once(self):
        ua = await self.config.user_agent()
        auctions = await self._fetch_current_auctions(user_agent=ua)
        if not auctions:
            return

        # Build a map from watch key -> (name, category) present this cycle
        present: Dict[str, Dict[str, str]] = {}
        for a in auctions:
            key = self._key(a["cardid"], a["season"])
            present[key] = {"name": a.get("name") or "Unknown", "category": a.get("category") or "Unknown"}

        # Get index: key -> [user_ids]
        watch_index = await self.config.watch_index()
        if not watch_index:
            return

        # For each present key, ping the watchers with per-user cooldown
        cooldown = await self.config.cooldown_seconds()
        now = int(time.time())

        for key, meta in present.items():
            user_ids: List[int] = watch_index.get(key, [])
            if not user_ids:
                continue

            for uid in list(user_ids):
                try:
                    user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                except Exception:
                    user = None
                if not user:
                    continue

                # Check per-user cooldown for this key
                last_map = await self.config.user(user).last_notified()
                last_ts = int(last_map.get(key, 0))
                if now - last_ts < cooldown:
                    continue  # still on cooldown for this (user, card)

                # DM embed
                cardid, season = key.split(":")
                await self._send_dm(user, int(cardid), int(season), meta["name"], meta["category"])

                # Update cooldown timestamp
                last_map[key] = now
                await self.config.user(user).last_notified.set(last_map)

    async def _fetch_current_auctions(self, user_agent: str) -> List[Dict]:
        url = f"{NS_BASE}?q=cards+auctions"
        headers = {"User-Agent": user_agent}
        text = await self._fetch_with_rate_limit(url, headers)
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            log.exception("Auctions XML parse error")
            return []

        auctions: List[Dict] = []
        node = root.find("AUCTIONS")
        if node is None:
            return auctions

        for a in node.findall("AUCTION"):
            cardid = parse_int((a.findtext("CARDID") or "").strip(), 0)
            category = (a.findtext("CATEGORY") or "").strip() or "unknown"
            name = (a.findtext("NAME") or "").strip() or "Unknown"
            season = parse_int((a.findtext("SEASON") or "").strip(), 0)
            if cardid and season:
                auctions.append({"cardid": cardid, "season": season, "name": name, "category": category})
        return auctions

    async def _fetch_with_rate_limit(self, url: str, headers: Dict[str, str]) -> str:
        # NationStates rate limit strategy as requested
        assert self._session is not None
        async with self._session.get(url, headers=headers) as resp:
            text = await resp.text()
            rl_remaining = resp.headers.get("Ratelimit-Remaining")
            rl_reset = resp.headers.get("Ratelimit-Reset")
            try:
                if rl_remaining is not None and rl_reset is not None:
                    remaining = int(rl_remaining)
                    remaining -= 10
                    reset_time = int(rl_reset)
                    wait_time = reset_time / remaining if remaining > 0 else reset_time
                    wait_time = max(0, min(wait_time, 5))
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
            except Exception:
                pass
            return text

    # -------- DM helper --------

    async def _send_dm(self, user: discord.User, cardid: int, season: int, name: str, category: str):
        embed = discord.Embed(
            title=f"Auction: Card {cardid} (S{season}) — {name}",
            description="This card is currently on the auction list.",
            timestamp=datetime.now(tz=timezone.utc),
        )
        embed.add_field(name="Category", value=category, inline=True)
        embed.url = self._card_url(cardid, season)
        try:
            await user.send(embed=embed)
        except Exception:
            # Can't DM this user (privacy settings, etc.)
            pass

    # -------- commands --------

    @commands.group(name="cap", invoke_without_command=True)
    async def cap_group(self, ctx: commands.Context):
        """Cards Auction Pinger (minimal)."""
        enabled = await self.config.enabled()
        interval = await self.config.interval_minutes()
        cooldown = await self.config.cooldown_seconds()
        ua = await self.config.user_agent()
        await ctx.send(
            "**Cards Auction Pinger**\n"
            f"Enabled: `{enabled}`\n"
            f"Interval: `{interval}` minutes\n"
            f"Cooldown: `{cooldown//3600}h`\n"
            f"User-Agent: `{ua}`"
        )

    @cap_group.command(name="start")
    @commands.is_owner()
    async def cap_start(self, ctx: commands.Context):
        await self.config.enabled.set(True)
        await self._ensure_task()
        await ctx.send("Started the minimal auction pinger.")

    @cap_group.command(name="stop")
    @commands.is_owner()
    async def cap_stop(self, ctx: commands.Context):
        await self.config.enabled.set(False)
        await ctx.send("Stopped the minimal auction pinger.")

    @cap_group.command(name="setua")
    @commands.is_owner()
    async def cap_setua(self, ctx: commands.Context, *, user_agent: str):
        await self.config.user_agent.set(user_agent)
        await ctx.send(f"User-Agent set to `{user_agent}`.")

    @cap_group.command(name="setinterval")
    @commands.is_owner()
    async def cap_setinterval(self, ctx: commands.Context, minutes: int):
        minutes = max(5, min(minutes, 240))
        await self.config.interval_minutes.set(minutes)
        await ctx.send(f"Polling interval set to {minutes} minutes.")

    @cap_group.command(name="setcooldown")
    @commands.is_owner()
    async def cap_setcooldown(self, ctx: commands.Context, hours: int):
        hours = max(1, min(hours, 24))
        await self.config.cooldown_seconds.set(hours * 3600)
        await ctx.send(f"Per-user per-card cooldown set to {hours} hours.")

    # watch management (per-user) + global index
    @cap_group.command(name="watch")
    async def cap_watch(self, ctx: commands.Context, cardid: int, season: int):
        key = self._key(cardid, season)
        wl = await self.config.user(ctx.author).watchlist()
        if key in wl:
            return await ctx.send("You're already watching that card.")
        wl.append(key)
        await self.config.user(ctx.author).watchlist.set(wl)

        idx = await self.config.watch_index()
        idx.setdefault(key, [])
        if ctx.author.id not in idx[key]:
            idx[key].append(ctx.author.id)
            await self.config.watch_index.set(idx)

        await ctx.send(f"Watching card `{cardid}` (S{season}).")

    @cap_group.command(name="unwatch")
    async def cap_unwatch(self, ctx: commands.Context, cardid: int, season: int):
        key = self._key(cardid, season)
        wl = await self.config.user(ctx.author).watchlist()
        if key in wl:
            wl.remove(key)
            await self.config.user(ctx.author).watchlist.set(wl)

        idx = await self.config.watch_index()
        if key in idx and ctx.author.id in idx[key]:
            idx[key].remove(ctx.author.id)
            if not idx[key]:
                idx.pop(key, None)
            await self.config.watch_index.set(idx)

        await ctx.send(f"Stopped watching card `{cardid}` (S{season}).")

    @cap_group.command(name="list")
    async def cap_list(self, ctx: commands.Context):
        wl = await self.config.user(ctx.author).watchlist()
        if not wl:
            return await ctx.send("You aren't watching any cards.")
        lines = "\n".join(f"- `{k}`" for k in wl)
        await ctx.send(f"You're watching:\n{lines}")

    # -------- utils --------

    @staticmethod
    def _key(cardid: int, season: int) -> str:
        return f"{cardid}:{season}"

    def _card_url(self, cardid: int, season: int) -> str:
        return f"https://www.nationstates.net/page=deck/card={cardid}/season={season}"
