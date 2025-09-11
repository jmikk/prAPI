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
import io
import json
from datetime import datetime, timezone
from discord import ui, ButtonStyle, Interaction



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

class GobCookieView(ui.View):
    """Persistent view with a link to the card + a 'Give Gob a Cookie' button."""
    def __init__(self, cog: "CardsAuctionWatcher", card_url: Optional[str] = None):
        # timeout=None makes it persistent across restarts (since we register it in cog_load)
        super().__init__(timeout=None)
        self.cog = cog
        # If a specific card URL is provided, add a link button dynamically
        if card_url:
            self.add_item(ui.Button(label="Open card", style=ButtonStyle.link, url=card_url))

        # Add the cookie button (custom_id must be stable for persistent views)
        self.add_item(ui.Button(label="Give Gob a Cookie", style=ButtonStyle.primary, custom_id="caw_give_gob_cookie"))

    @ui.button(label="Give Gob a Cookie", style=ButtonStyle.primary, custom_id="caw_give_gob_cookie")  # noqa
    async def give_cookie(self, interaction: Interaction, button: ui.Button):
        # Increment global cookie count
        current = await self.cog.config.gob_cookies()
        await self.cog.config.gob_cookies.set(current + 1)
        try:
            await interaction.response.send_message("🍪 Thanks! Gob appreciates your cookie.", ephemeral=True)
        except Exception:
            # In DMs ephemeral isn't supported; fall back to normal followup
            if interaction.channel:
                await interaction.channel.send("🍪 Thanks! Gob appreciates your cookie.")


class CardsAuctionWatcher(commands.Cog):
    """Fetch NS auctions once per cycle, fan out placeholders to all webhooks, then enrich each card every 5s.
    Cleans up ended auctions and keeps ongoing ones updated across cycles.
    """

    __author__ = "you"
    __version__ = "1.4.0"

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
            "gob_cookies": 0,  
            "webhooks_enabled": False,   # <<< NEW
            "mapping_enabled": False,    # <<< NEW
        }
        self.config.register_global(**default_global)
        self.config.register_user(watchlist=[])  # List[str] of "cardid:season"
        # PER-GUILD config: just the webhook URLs
        self.config.register_guild(webhooks=[])

        # runtime
        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None

    async def cog_load(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        # persistent view for the cookie button
        self.bot.add_view(GobCookieView(self))
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
        webhooks_enabled = await self.config.webhooks_enabled()
        mapping_enabled = await self.config.mapping_enabled()
    
        # 1) Fetch auctions once
        auctions = await self._fetch_current_auctions(user_agent=ua)
    
        # 1.5) Always notify watchers (DMs) even if webhooks/mapping are off
        for a in auctions:
            # if you already added the notifier helper earlier:
            await self._notify_watchers_for(a["cardid"], a["season"], a.get("name"))
    
        # If webhooks are disabled, we stop here (watchlist-only mode)
        if not webhooks_enabled:
            return
    
        # From here on, webhooks are enabled. Decide mapping behavior.
        current_keys = {self._key(a["cardid"], a["season"]) for a in auctions}
        message_map: Dict[str, Dict[str, int]] = await self.config.message_map()
    
        now_unix = int(time.time())
        per_card_delay = max(1, delay)
    
        if mapping_enabled:
            # ---------- FULL mapping/edit/cleanup mode (your current behavior) ----------
            prior_keys = set(message_map.keys())
            ended_keys = prior_keys - current_keys
            if ended_keys:
                await self._cleanup_ended(ended_keys, message_map)
    
            # Post placeholders with ETA where missing
            for idx, a in enumerate(auctions):
                key = self._key(a["cardid"], a["season"])
                message_map.setdefault(key, {})
                eta_unix = now_unix + idx * per_card_delay
                for url in webhooks:
                    if url not in message_map[key]:
                        embed = self._build_initial_embed(a["cardid"], a["season"], a.get("name"), a.get("category"), eta_unix)
                        try:
                            msg = await self._send_webhook_message(url, embed)
                            message_map[key][url] = msg.id
                        except Exception:
                            log.exception("Failed sending placeholder to webhook: %s", url)
    
            await self.config.message_map.set(message_map)
    
            # ETA refresh
            for idx, a in enumerate(auctions):
                key = self._key(a["cardid"], a["season"])
                per_hooks = message_map.get(key, {})
                if not per_hooks:
                    continue
                eta_unix = now_unix + idx * per_card_delay
                eta_embed = self._build_initial_embed(a["cardid"], a["season"], a.get("name"), a.get("category"), eta_unix)
                for url, msg_id in list(per_hooks.items()):
                    try:
                        await self._edit_webhook_message(url, msg_id, eta_embed)
                    except discord.NotFound:
                        message_map[key].pop(url, None)
                    except Exception:
                        log.exception("ETA refresh edit failed (%s, %s)", url, msg_id)
            await self.config.message_map.set(message_map)
    
            # Detail loop with edits
            for a in auctions:
                cardid, season = a["cardid"], a["season"]
                key = self._key(cardid, season)
                per_hooks = (await self.config.message_map()).get(key, {})
                if not per_hooks:
                    # late placeholders with immediate-ish ETA
                    eta_unix = int(time.time())
                    embed = self._build_initial_embed(cardid, season, a.get("name"), a.get("category"), eta_unix)
                    per_hooks = {}
                    for url in webhooks:
                        try:
                            msg = await self._send_webhook_message(url, embed)
                            per_hooks[url] = msg.id
                        except Exception:
                            log.exception("Late placeholder send failed: %s", url)
                    message_map = await self.config.message_map()
                    message_map[key] = per_hooks
                    await self.config.message_map.set(message_map)
    
                try:
                    details = await self._fetch_card_details(cardid, season, user_agent=ua)
                    embed = self._build_detailed_embed(details)
                except Exception:
                    log.exception("Detail fetch failed for card %s S%s", cardid, season)
                    embed = self._build_initial_embed(cardid, season, a.get("name"), a.get("category"))
    
                stale_urls = []
                for url, msg_id in per_hooks.items():
                    try:
                        await self._edit_webhook_message(url, msg_id, embed)
                    except discord.NotFound:
                        stale_urls.append(url)
                    except Exception:
                        log.exception("Editing webhook message failed (%s, %s)", url, msg_id)
    
                if stale_urls:
                    message_map = await self.config.message_map()
                    for u in stale_urls:
                        message_map.get(key, {}).pop(u, None)
                    await self.config.message_map.set(message_map)
    
                await asyncio.sleep(per_card_delay)
    
        else:
            # ---------- LIGHTWEIGHT mode (no mapping): post fresh placeholders with ETA each cycle, then stop ----------
            # No cleanup, no editing, no state changes to message_map
            if not webhooks:
                return
            for idx, a in enumerate(auctions):
                eta_unix = now_unix + idx * per_card_delay
                embed = self._build_initial_embed(a["cardid"], a["season"], a.get("name"), a.get("category"), eta_unix)
                for url in webhooks:
                    try:
                        await self._send_webhook_message(url, embed)
                    except Exception:
                        log.exception("Send placeholder (no-mapping) failed: %s", url)
            # (intentionally no detail fetches or sleeps here)



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
    
        # ✅ Use the embed's timestamp for the ETA display in the footer area
        if eta_unix is not None:
            embed.timestamp = datetime.fromtimestamp(int(eta_unix), tz=timezone.utc)
            # Footer label (Discord shows the timestamp on the right)
            embed.set_footer(text="ETA for details • NationStates Cards • Auctions")
    
            # Optional (uncomment if you also want a relative ETA inside the body)
            embed.add_field(name="ETA", value=_discord_rel_ts(eta_unix), inline=True)
        else:
            embed.set_footer(text="NationStates Cards • Auctions")
        return embed


    def _build_detailed_embed(self, d: Dict) -> discord.Embed:
        title = f"Card {d['cardid']} (S{d['season']}) — {d['name']}"
        embed = discord.Embed(title=title)
        if d.get("flag"):
            flag_url = d["flag"]
            if flag_url.startswith("uploads/"):
                flag_url = f"https://www.nationstates.net/images/cards/s{d['season']}/" + flag_url
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
        webhooks_enabled = await self.config.webhooks_enabled()
        mapping_enabled = await self.config.mapping_enabled()

        await ctx.send(
            "**Cards Auction Watcher**\n"
            f"Global Enabled: `{enabled}`\n"
            f"Global Interval: `{interval}` minutes\n"
            f"Global Per-card delay: `{delay}` seconds\n"
            f"Global User-Agent: `{ua}`\n"
            f"Webhooks in this guild: `{len(hooks)}`"
            f"Webhooks Enabled: `{webhooks_enabled}`\n"
            f"Mapping Enabled: `{mapping_enabled}`\n"
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

    @caw_group.command(name="dump")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_dump(self, ctx: commands.Context):
        """
        Delete ALL known webhook messages and export a JSON dump.
        Keeps webhook lists and settings; clears only the message map.
        """
        await ctx.typing()
        # Pause the loop briefly by toggling enabled off then back on when done
        was_enabled = await self.config.enabled()
        if was_enabled:
            await self.config.enabled.set(False)
    
        try:
            data = await self._dump_and_optionally_delete(perform_delete=True)
            # Now that we've deleted everything, also clear the message map (extra safety)
            await self.config.message_map.set({})
            # Send file
            stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            fp = io.BytesIO(data)
            fp.seek(0)
            await ctx.send(
                content="Dump complete. All known webhook messages removed and state reset.",
                file=discord.File(fp, filename=f"caw_dump_{stamp}.json"),
            )
        finally:
            # restore enabled flag
            if was_enabled:
                await self.config.enabled.set(True)
                await self._ensure_task()
        
    @caw_group.command(name="dumpdry")
    @commands.has_guild_permissions(manage_guild=True)
    async def caw_dumpdry(self, ctx: commands.Context):
        """
        Export a JSON dump of all known webhook messages WITHOUT deleting anything.
        """
        await ctx.typing()
        data = await self._dump_and_optionally_delete(perform_delete=False)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        fp = io.BytesIO(data)
        fp.seek(0)
        await ctx.send(
            content="Dry dump complete. No messages were deleted.",
            file=discord.File(fp, filename=f"caw_dumpdry_{stamp}.json"),
        )
        
        @caw_group.command(name="webhooks")
        @commands.has_guild_permissions(manage_guild=True)
        async def caw_webhooks(self, ctx: commands.Context, state: str):
            """Turn webhook posting/editing on or off globally. Usage: [p]caw webhooks on|off"""
            state = state.lower()
            if state not in {"on", "off"}:
                return await ctx.send("Use `on` or `off`.")
            await self.config.webhooks_enabled.set(state == "on")
            await ctx.send(f"Webhooks are now **{'ENABLED' if state == 'on' else 'DISABLED'}**.")
        
        @caw_group.command(name="mapping")
        @commands.has_guild_permissions(manage_guild=True)
        async def caw_mapping(self, ctx: commands.Context, state: str):
            """Turn message mapping/edits/cleanup on or off globally. Usage: [p]caw mapping on|off"""
            state = state.lower()
            if state not in {"on", "off"}:
                return await ctx.send("Use `on` or `off`.")
            await self.config.mapping_enabled.set(state == "on")
            await ctx.send(f"Mapping is now **{'ENABLED' if state == 'on' else 'DISABLED'}**.")


    @caw_group.command(name="watch")
    async def caw_watch(self, ctx: commands.Context, cardid: int, season: int):
        """Add a card to *your* watchlist. You'll get a DM when it's seen in a cycle."""
        key = self._key(cardid, season)
        lst = await self.config.user(ctx.author).watchlist()
        if key in lst:
            return await ctx.send(f"You're already watching **{cardid} (S{season})**.")
        lst.append(key)
        await self.config.user(ctx.author).watchlist.set(lst)
    
        # update global index
        idx = await self.config.watch_index()
        idx.setdefault(key, [])
        if ctx.author.id not in idx[key]:
            idx[key].append(ctx.author.id)
        await self.config.watch_index.set(idx)
    
        await ctx.send(f"Added **{cardid} (S{season})** to your watchlist. I'll DM you when I see it.")
    
    @caw_group.command(name="unwatch")
    async def caw_unwatch(self, ctx: commands.Context, cardid: int, season: int):
        """Remove a card from your watchlist."""
        key = self._key(cardid, season)
        lst = await self.config.user(ctx.author).watchlist()
        if key not in lst:
            return await ctx.send(f"**{cardid} (S{season})** is not in your watchlist.")
        lst.remove(key)
        await self.config.user(ctx.author).watchlist.set(lst)
    
        # update global index
        idx = await self.config.watch_index()
        if key in idx and ctx.author.id in idx[key]:
            idx[key].remove(ctx.author.id)
            if not idx[key]:
                idx.pop(key, None)
        await self.config.watch_index.set(idx)
    
        await ctx.send(f"Removed **{cardid} (S{season})** from your watchlist.")
    
    @caw_group.command(name="mywatchlist")
    async def caw_mywatchlist(self, ctx: commands.Context):
        """Show your watchlist."""
        lst = await self.config.user(ctx.author).watchlist()
        if not lst:
            return await ctx.send("Your watchlist is empty. Add one with: `caw watch <cardid> <season>`")
        nicely = "\n".join(f"• {k.replace(':', ' (S')} )" for k in lst)
        await ctx.send(f"**Your watchlist:**\n{nicely}")
    
    @caw_group.command(name="cookies")
    async def caw_cookies(self, ctx: commands.Context):
        """Cookie dashboard 🥠"""
        total = await self.config.gob_cookies()
        await ctx.send(f"🍪 **Gob's cookie jar:** `{total}` cookies")
    


    # ----------------- Utils -----------------

    @staticmethod
    def _key(cardid: int, season: int) -> str:
        return f"{cardid}:{season}"

    async def _dump_and_optionally_delete(self, perform_delete: bool) -> bytes:
        """
        Build a JSON dump of all tracked webhook messages.
        If perform_delete=True, also delete each message and record the outcome.
        Returns a bytes buffer containing the JSON.
        """
        # Snapshot config data
        message_map = await self.config.message_map()
        # We also include non-sensitive config info for context
        enabled = await self.config.enabled()
        interval = await self.config.interval_minutes()
        delay = await self.config.detail_delay_sec()
        ua = await self.config.user_agent()
    
        # Gather guild webhooks
        all_guild_hooks = {}
        for g in self.bot.guilds:
            try:
                hooks = await self.config.guild(g).webhooks()
                all_guild_hooks[str(g.id)] = hooks
            except Exception:
                all_guild_hooks[str(g.id)] = []
    
        report = {
            "meta": {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "perform_delete": perform_delete,
                "global_enabled": enabled,
                "global_interval_minutes": interval,
                "global_detail_delay_sec": delay,
                "global_user_agent": ua,
            },
            "guild_webhooks": all_guild_hooks,
            "messages": [],
        }
    
        # Delete / collect
        for key, per_hooks in list(message_map.items()):
            for url, msg_id in list(per_hooks.items()):
                entry = {
                    "card_key": key,
                    "webhook_url": url,
                    "message_id": msg_id,
                    "action": "none",
                    "error": None,
                }
                if perform_delete:
                    try:
                        await self._delete_webhook_message(url, msg_id)
                        entry["action"] = "deleted"
                        # remove from map as we go to minimize retries if interrupted
                        per_hooks.pop(url, None)
                    except discord.NotFound:
                        entry["action"] = "not_found"
                        per_hooks.pop(url, None)
                    except Exception as e:
                        entry["action"] = "error"
                        entry["error"] = repr(e)
                else:
                    entry["action"] = "listed"
                report["messages"].append(entry)
    
            # if we deleted everything under this key, drop the key too
            if perform_delete and not per_hooks:
                message_map.pop(key, None)
    
        # persist map updates if we were deleting
        if perform_delete:
            await self.config.message_map.set(message_map)
    
        # Serialize to bytes
        buf = io.BytesIO()
        buf.write(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
        return buf.getvalue()
        def _card_url(self, cardid: int, season: int) -> str:
    return f"https://www.nationstates.net/page=deck/card={cardid}/season={season}"

    async def _notify_watchers_for(self, cardid: int, season: int, name: str):
        """DM everyone watching this (cardid, season)."""
        key = self._key(cardid, season)
        idx = await self.config.watch_index()
        user_ids = idx.get(key, [])
        if not user_ids:
            return
    
        url = self._card_url(cardid, season)
        view = GobCookieView(self, card_url=url)  # includes link + cookie button
    
        for uid in user_ids:
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            if not user:
                continue
            # Build a small embed DM
            embed = discord.Embed(
                title=f"Found on auction: Card {cardid} (S{season})",
                description=f"**{name or 'Unknown'}** is on the auction list this cycle.",
            )
            embed.url = url
            try:
                await user.send(embed=embed, view=view)
            except Exception:
                # can't DM this user (privacy settings); ignore
                pass





def setup(bot: Red):
    bot.add_cog(CardsAuctionWatcher(bot))
