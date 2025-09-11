# cards_auction_watcher.py
import asyncio
import logging
from typing import Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET
import time
import aiohttp
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.cards_auction_watcher")

NS_BASE = "https://www.nationstates.net/cgi-bin/api.cgi"

def _discord_rel_ts(unix_seconds: int) -> str:
    return f"<t:{int(unix_seconds)}:R>"

def parse_int(s: Optional[str], default: int = 0) -> int:
    try:
        return int(s) if s is not None else default
    except Exception:
        return default

def parse_float(s: Optional[str], default: float = 0.0) -> float:
    try:
        return float(s) if s is not None else default
    except Exception:
        return default

class CardsAuctionWatcher(commands.Cog):
    """Fetch NS auctions once per cycle, fan out placeholders to all webhooks, then enrich each card every 5s.
    Cleans up ended auctions and keeps ongoing ones updated across cycles.
    """

    __author__ = "you"
    __version__ = "1.3.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="sdxfcgvhbjnk", force_registration=True)

        # GLOBAL config: single loop, single delay/interval/UA + persistent message map
        default_global = {
            "enabled": False,
            "interval_minutes": 30,
            "detail_delay_sec": 5,
            "user_agent": "",
            # key = "cardid:season" -> { webhook_url: message_id }
            "message_map": {},  # Dict[str, Dict[str, int]]
        }
        self.config.register_global(**default_global)

        # PER-GUILD config: just the webhook URLs
        self.config.register_guild(webhooks=[])

        # runtime
        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None

    async def cog_load(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        if await self.config.enabled():
            await self._ensure_task()

    async def cog_unload(self):
        if self._task and not self._task.done():
            self._task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    # ----------------- Task runner (global) -----------------

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

                # Gather ALL configured webhooks across all guilds
                all_webhooks: List[str] = []
                for g in self.bot.guilds:
                    try:
                        hooks = await self.config.guild(g).webhooks()
                        all_webhooks.extend([h for h in hooks if h])
                    except Exception:
                        continue
                all_webhooks = list(dict.fromkeys(all_webhooks))  # de-dup but keep order

                if not all_webhooks:
                    log.info("CardsAuctionWatcher: no webhooks configured anywhere; idling this cycle.")
                else:
                    await self._run_once(all_webhooks)

                # global interval
                minutes = await self.config.interval_minutes()
                await asyncio.sleep(max(1, minutes) * 60)

            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("CardsAuctionWatcher loop error")
                await asyncio.sleep(30)

    async def _run_once(self, webhooks: List[str]):
        ua = await self.config.user_agent()
        delay = await self.config.detail_delay_sec()

        # 1) Fetch auctions ONCE
        auctions = await self._fetch_current_auctions(user_agent=ua)
        current_keys = {self._key(a["cardid"], a["season"]) for a in auctions}

        # 2) Load prior message map and CLEAN UP ENDED auctions
        message_map: Dict[str, Dict[str, int]] = await self.config.message_map()
        prior_keys = set(message_map.keys())
        ended_keys = prior_keys - current_keys
        if ended_keys:
            await self._cleanup_ended(ended_keys, message_map)

        # 3) Post placeholders for NEW auctions and for NEW webhooks added since last cycle
        for a in auctions:
            key = self._key(a["cardid"], a["season"])
            message_map.setdefault(key, {})
            for url in webhooks:
                if url not in message_map[key]:
                    # New auction or newly added webhook; post placeholder
                    embed = self._build_initial_embed(a["cardid"], a["season"], a.get("name"), a.get("category"))
                    try:
                        msg = await self._send_webhook_message(url, embed)
                        message_map[key][url] = msg.id
                    except Exception:
                        log.exception("Failed sending placeholder to webhook: %s", url)

        # Persist any changes so far (after cleanup & placeholders)
        await self.config.message_map.set(message_map)

        # 3.5) **ETA refresh** on continuing auctions:
        # For auctions that already had messages, refresh the footer with the *new* cycle ETA
        for idx, a in enumerate(auctions):
            key = self._key(a["cardid"], a["season"])
            per_hooks = message_map.get(key, {})
            if not per_hooks:
                continue
            eta_unix = now_unix + idx * max(1, delay)
            # Build a lightweight initial embed with updated ETA
            eta_embed = self._build_initial_embed(a["cardid"], a["season"], a.get("name"), a.get("category"), eta_unix)
            for url, msg_id in list(per_hooks.items()):
                try:
                    await self._edit_webhook_message(url, msg_id, eta_embed)
                except discord.NotFound:
                    # message removed externally; clean mapping
                    message_map[key].pop(url, None)
                except Exception:
                    log.exception("ETA refresh edit failed (%s, %s)", url, msg_id)
        # Persist any mapping trims
        await self.config.message_map.set(message_map)

        # 4) Detail loop: one-by-one, every N seconds, get details and EDIT existing messages
        for a in auctions:
            cardid, season = a["cardid"], a["season"]
            key = self._key(cardid, season)

            # Double-check map still present
            per_hooks = (await self.config.message_map()).get(key, {})
            if not per_hooks:
                # if somehow missing (e.g., deleted while we ran), create placeholders now
                per_hooks = {}
                embed = self._build_initial_embed(cardid, season, a.get("name"), a.get("category"))
                for url in webhooks:
                    try:
                        msg = await self._send_webhook_message(url, embed)
                        per_hooks[url] = msg.id
                    except Exception:
                        log.exception("Late placeholder send failed: %s", url)
                message_map = await self.config.message_map()
                message_map[key] = per_hooks
                await self.config.message_map.set(message_map)

            # Fetch details & edit
            try:
                details = await self._fetch_card_details(cardid, season, user_agent=ua)
                embed = self._build_detailed_embed(details)
            except Exception:
                log.exception("Detail fetch failed for card %s S%s", cardid, season)
                embed = self._build_initial_embed(cardid, season, a.get("name"), a.get("category"))

            # Edit every stored message for this card
            stale_urls = []
            for url, msg_id in per_hooks.items():
                try:
                    await self._edit_webhook_message(url, msg_id, embed)
                except discord.NotFound:
                    # Message was deleted manually; mark stale
                    stale_urls.append(url)
                except Exception:
                    log.exception("Editing webhook message failed (%s, %s)", url, msg_id)

            # Remove stale entries from map
            if stale_urls:
                message_map = await self.config.message_map()
                for u in stale_urls:
                    message_map.get(key, {}).pop(u, None)
                await self.config.message_map.set(message_map)

            # wait N seconds between detail requests
            await asyncio.sleep(max(1, delay))

    # ----------------- Cleanup helpers -----------------

    async def _cleanup_ended(self, ended_keys: set, message_map: Dict[str, Dict[str, int]]):
        """Delete webhook messages for auctions that are no longer present."""
        for key in list(ended_keys):
            per_hooks = message_map.get(key, {})
            for url, msg_id in list(per_hooks.items()):
                try:
                    await self._delete_webhook_message(url, msg_id)
                except discord.NotFound:
                    pass  # already gone
                except Exception:
                    log.exception("Failed to delete ended auction message (%s, %s)", url, msg_id)
            # Remove from map
            message_map.pop(key, None)

    # ----------------- HTTP helpers + NS rate handling -----------------

    async def _fetch_with_rate_limit(self, url: str, headers: Dict[str, str]) -> str:
        assert self._session is not None
        async with self._session.get(url, headers=headers) as resp:
            text = await resp.text()
            # Apply your NS header strategy
            rl_remaining = resp.headers.get("Ratelimit-Remaining")
            rl_reset = resp.headers.get("Ratelimit-Reset")
            try:
                if rl_remaining is not None and rl_reset is not None:
                    remaining = int(rl_remaining)
                    remaining -= 10
                    reset_time = int(rl_reset)
                    wait_time = reset_time / remaining if remaining > 0 else reset_time
                    wait_time = max(0, min(wait_time, 5))  # small cap for sanity
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
            except Exception:
                pass
            return text

    async def _fetch_current_auctions(self, user_agent: str) -> List[Dict]:
        url = f"{NS_BASE}?q=cards+auctions"
        headers = {"User-Agent": user_agent}
        xml_text = await self._fetch_with_rate_limit(url, headers)
        try:
            root = ET.fromstring(xml_text)
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

    async def _fetch_card_details(self, cardid: int, season: int, user_agent: str) -> Dict:
        url = f"{NS_BASE}?q=card+info+markets;cardid={cardid};season={season}"
        headers = {"User-Agent": user_agent}
        xml_text = await self._fetch_with_rate_limit(url, headers)
        root = ET.fromstring(xml_text)

        name = (root.findtext("NAME") or "").strip()
        category = (root.findtext("CATEGORY") or "").strip()
        mv = parse_float((root.findtext("MARKET_VALUE") or "0").strip(), 0.0)
        region = (root.findtext("REGION") or "").strip()
        slogan = (root.findtext("SLOGAN") or "").strip()
        govtype = (root.findtext("TYPE") or "").strip() or (root.findtext("GOVT") or "").strip()
        flag = (root.findtext("FLAG") or "").strip()
        season_val = parse_int((root.findtext("SEASON") or "0").strip(), season)
        cid = parse_int((root.findtext("CARDID") or "0").strip(), cardid)

        bids, asks = [], []
        markets_node = root.find("MARKETS")
        if markets_node is not None:
            for m in markets_node.findall("MARKET"):
                ttype = (m.findtext("TYPE") or "").strip().lower()
                price = parse_float((m.findtext("PRICE") or "0").strip(), 0.0)
                nation = (m.findtext("NATION") or "").strip()
                ts = parse_int((m.findtext("TIMESTAMP") or "0").strip(), 0)
                if ttype == "bid":
                    bids.append((price, nation, ts))
                elif ttype == "ask":
                    asks.append((price, nation, ts))

        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        return {
            "cardid": cid,
            "season": season_val,
            "name": name,
            "category": category,
            "market_value": mv,
            "region": region,
            "slogan": slogan,
            "govtype": govtype,
            "flag": flag,
            "top_bids": bids[:5],
            "top_asks": asks[:5],
            "bid_count": len(bids),
            "ask_count": len(asks),
        }

    # ----------------- Embeds -----------------
    
    def _build_initial_embed(
        self,
        cardid: int,
        season: int,
        name: Optional[str],
        category: Optional[str],
        eta_unix: Optional[int] = None,
    ) -> discord.Embed:
        title = f"Auction: Card {cardid} (S{season})"
        desc = "Fetching market details… this message will update."
        embed = discord.Embed(title=title, description=desc)
        embed.add_field(name="Name", value=name or "Unknown", inline=True)
        embed.add_field(name="Category", value=category or "Unknown", inline=True)
    
        if eta_unix:
            embed.set_footer(text=f"ETA for details: {_discord_rel_ts(eta_unix)} • NationStates Cards • Auctions")
        else:
            embed.set_footer(text="NationStates Cards • Auctions")
        return embed

    def _build_detailed_embed(self, d: Dict) -> discord.Embed:
        title = f"Card {d['cardid']} (S{d['season']}) — {d['name']}"
        embed = discord.Embed(title=title)
        if d.get("flag"):
            flag_url = d["flag"]
            if flag_url.startswith("uploads/"):
                flag_url = f"https://www.nationstates.net/images/cards/s{d['season']}/uploads/" + flag_url
            embed.set_thumbnail(url=flag_url)

        embed.add_field(name="Category", value=d.get("category", "Unknown") or "Unknown", inline=True)
        embed.add_field(name="Market Value", value=f"{d.get('market_value', 0.0):,.2f}", inline=True)
        if d.get("region"):
            embed.add_field(name="Region", value=d["region"], inline=True)
        if d.get("govtype"):
            embed.add_field(name="Type", value=d["govtype"], inline=True)
        if d.get("slogan"):
            embed.add_field(name="Slogan", value=d["slogan"][:1024], inline=False)

        def fmt_book(side):
            if not side:
                return "_none_"
            return "\n".join(f"• **{p:,.2f}** by `{n}` (t={_discord_rel_ts(ts)})" for p, n, ts in side)

        embed.add_field(name="Top Bids (best first)", value=fmt_book(d.get("top_bids", [])), inline=False)
        embed.add_field(name="Top Asks (cheapest first)", value=fmt_book(d.get("top_asks", [])), inline=False)
        embed.set_footer(text=f"Bids: {d.get('bid_count', 0)} • Asks: {d.get('ask_count', 0)} • NationStates Cards")
        return embed

    # ----------------- Webhook helpers -----------------

    async def _send_webhook_message(self, url: str, embed: discord.Embed) -> discord.Message:
        assert self._session is not None
        webhook = discord.Webhook.from_url(url, session=self._session)
        return await webhook.send(embed=embed, wait=True)

    async def _edit_webhook_message(self, url: str, message_id: int, embed: discord.Embed):
        assert self._session is not None
        webhook = discord.Webhook.from_url(url, session=self._session)
        await webhook.edit_message(message_id, embed=embed)

    async def _delete_webhook_message(self, url: str, message_id: int):
        assert self._session is not None
        webhook = discord.Webhook.from_url(url, session=self._session)
        await webhook.delete_message(message_id)

    # ----------------- Commands -----------------

    @commands.guild_only()
    @commands.group(name="caw", invoke_without_command=True)
    async def caw_group(self, ctx: commands.Context):
        """Cards Auction Watcher (global cooldowns; per-guild webhooks; cleanup of ended auctions)."""
        enabled = await self.config.enabled()
        interval = await self.config.interval_minutes()
        delay = await self.config.detail_delay_sec()
        ua = await self.config.user_agent()
        hooks = await self.config.guild(ctx.guild).webhooks()
        await ctx.send(
            "**Cards Auction Watcher**\n"
            f"Global Enabled: `{enabled}`\n"
            f"Global Interval: `{interval}` minutes\n"
            f"Global Per-card delay: `{delay}` seconds\n"
            f"Global User-Agent: `{ua}`\n"
            f"Webhooks in this guild: `{len(hooks)}`"
        )

    @caw_group.command(name="start")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_start(self, ctx: commands.Context):
        await self.config.enabled.set(True)
        await self._ensure_task()
        await ctx.send("Started the **global** Cards Auction Watcher.")

    @caw_group.command(name="stop")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_stop(self, ctx: commands.Context):
        await self.config.enabled.set(False)
        await ctx.send("Stopped the **global** Cards Auction Watcher.")

    @caw_group.command(name="addwebhook")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_addwebhook(self, ctx: commands.Context, url: str):
        webhooks = await self.config.guild(ctx.guild).webhooks()
        webhooks.append(url)
        await self.config.guild(ctx.guild).webhooks.set(webhooks)
        await ctx.send("Webhook added for this guild.")

    @caw_group.command(name="listwebhooks")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_listwebhooks(self, ctx: commands.Context):
        webhooks = await self.config.guild(ctx.guild).webhooks()
        if not webhooks:
            await ctx.send("No webhooks configured in this guild.")
            return
        lines = [f"{i+1}. {u}" for i, u in enumerate(webhooks)]
        await ctx.send("Webhooks in this guild:\n" + "\n".join(lines))

    @caw_group.command(name="removewebhook")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_removewebhook(self, ctx: commands.Context, index: int):
        webhooks = await self.config.guild(ctx.guild).webhooks()
        if index < 1 or index > len(webhooks):
            await ctx.send("Invalid index.")
            return
        removed = webhooks.pop(index - 1)
        await self.config.guild(ctx.guild).webhooks.set(webhooks)
        await ctx.send(f"Removed webhook: {removed}")

    @caw_group.command(name="setinterval")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_setinterval(self, ctx: commands.Context, minutes: int):
        minutes = max(5, min(minutes, 240))
        await self.config.interval_minutes.set(minutes)
        await ctx.send(f"**Global** polling interval set to {minutes} minutes.")

    @caw_group.command(name="setdelay")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_setdelay(self, ctx: commands.Context, seconds: int):
        seconds = max(1, min(seconds, 60))
        await self.config.detail_delay_sec.set(seconds)
        await ctx.send(f"**Global** per-card detail delay set to {seconds} seconds.")

    @caw_group.command(name="setua")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_setua(self, ctx: commands.Context, *, user_agent: str):
        await self.config.user_agent.set(user_agent)
        await ctx.send(f"**Global** User-Agent set to `{user_agent}`.")

    @caw_group.command(name="clearmap")
    @commands.is_owner()
    async def caw_clearmap(self, ctx: commands.Context):
        """Clear the saved message map (useful if webhooks were wiped externally)."""
        await self.config.message_map.set({})
        await ctx.send("Cleared the saved auction message map.")

    # ----------------- Utils -----------------

    @staticmethod
    def _key(cardid: int, season: int) -> str:
        return f"{cardid}:{season}"

def setup(bot: Red):
    bot.add_cog(CardsAuctionWatcher(bot))
