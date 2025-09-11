import asyncio
import logging
from typing import Dict, List, Tuple, Set, Optional

import aiohttp
import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import xml.etree.ElementTree as ET

log = logging.getLogger("red.wellspring.auctionwatch")

DEFAULT_GUILD = {
    "cookies": 0,               # total "Gob" cookies given
    "user_agent": "9003",       # NationStates UA header (override with [p]setnsua)
    "log_channel_id": 0,        # Channel to send errors/success summaries
}

DEFAULT_USER = {
    # list of tuples [[cardid, season], ...]
    "watchlist": []
}


class GobCookieView(discord.ui.View):
    def __init__(self, cog: "AuctionWatch", *, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.cog = cog

    @discord.ui.button(label="Give Gob a cookie", style=discord.ButtonStyle.primary)
    async def give_cookie(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
        try:
            guild = interaction.guild
            if guild is None:
                mutuals = [g for g in self.cog.bot.guilds if g.get_member(interaction.user.id)]
                guild = mutuals[0] if mutuals else None

            if guild is None:
                await interaction.response.send_message(
                    "I couldn't figure out which server to credit this cookie to, but Gob appreciates it anyway!",
                    ephemeral=True
                )
                return

            current = await self.cog.config.guild(guild).cookies()
            await self.cog.config.guild(guild).cookies.set(current + 1)
            await interaction.response.send_message("🍪 Gob says thanks! (+1 cookie)")

            # Success log
            try:
                await self.cog._log_for_user(
                    interaction.user,
                    f"✅ **AuctionWatch**: Recorded a cookie from <@{interaction.user.id}>. Total now: **{current + 1}**."
                )
            except Exception:
                pass

        except Exception:
            log.exception("Failed to record cookie")
            if not interaction.response.is_done():
                await interaction.response.send_message("Sorry, I couldn't record that cookie right now.", ephemeral=True)
            # Error log
            try:
                user = interaction.user
                await self.cog._log_for_user(user, f"❗ **AuctionWatch**: Failed to record cookie from <@{user.id}>.")
            except Exception:
                pass
        return


class AuctionWatch(commands.Cog):
    """
    Watches NationStates Card Auctions and DMs users when their watched cards appear.
    Includes a Gob cookie button, cookie leaderboard, start/stop commands,
    and logs errors/successes to a configured channel.

    • Add a watch:   [p]watchlist add <cardid> <season>
    • Remove a watch:[p]watchlist remove <cardid> <season>
    • List watches:  [p]watchlist list
    • Show cookies:  [p]gobcookies
    • Set UA header (owner/admin): [p]setnsua <text>
    • Set log channel: [p]awsetlog [#channel]
    • Show log channel: [p]awlogstatus
    • Manually check:  [p]checkauctions
    • Start/Stop loop: [p]startauctions / [p]stopauctions
    """

    __author__ = "your_name_here"
    __version__ = "1.1.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890123456, force_registration=True)
        self.config.register_guild(**DEFAULT_GUILD)
        self.config.register_user(**DEFAULT_USER)

        # Cache of (cardid, season) pairs recently notified to reduce duplicate pings
        self._recent_notified: Dict[Tuple[int, int, int], float] = {}
        # Start background task
        self.poll_auctions.start()

    def cog_unload(self):
        self.poll_auctions.cancel()

    # ===== Commands =====

    @commands.group(name="watchlist")
    async def watchlist(self, ctx: commands.Context):
        """Manage your card watch list."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @watchlist.command(name="add")
    async def watchlist_add(self, ctx: commands.Context, cardid: int, season: int):
        """Add a card to your watch list by Card ID and Season."""
        wl: List[List[int]] = await self.config.user(ctx.author).watchlist()
        pair = [int(cardid), int(season)]
        if pair in wl:
            return await ctx.send(f"That card (ID {cardid}, S{season}) is already on your watch list.")
        wl.append(pair)
        await self.config.user(ctx.author).watchlist.set(wl)
        await ctx.tick()
        await ctx.send(f"Added card **ID {cardid}** (Season **{season}**) to your watch list.")

    @watchlist.command(name="remove")
    async def watchlist_remove(self, ctx: commands.Context, cardid: int, season: int):
        """Remove a card from your watch list."""
        wl: List[List[int]] = await self.config.user(ctx.author).watchlist()
        pair = [int(cardid), int(season)]
        if pair not in wl:
            return await ctx.send(f"I didn't find card (ID {cardid}, S{season}) on your watch list.")
        wl.remove(pair)
        await self.config.user(ctx.author).watchlist.set(wl)
        await ctx.tick()
        await ctx.send(f"Removed card **ID {cardid}** (Season **{season}**) from your watch list.")

    @watchlist.command(name="list")
    async def watchlist_list(self, ctx: commands.Context):
        """Show your current watch list."""
        wl: List[List[int]] = await self.config.user(ctx.author).watchlist()
        if not wl:
            return await ctx.send("Your watch list is empty. Add one with `[p]watchlist add <cardid> <season>`.")
        lines = [f"• ID **{cid}**, Season **{s}** — <https://www.nationstates.net/page=deck/card={cid}/season={s}>" for cid, s in wl]
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Watch List", description="\n".join(lines))
        await ctx.send(embed=embed)

    @commands.command(name="gobcookies")
    async def gobcookies(self, ctx: commands.Context):
        """Show how many cookies Gob has received."""
        count = await self.config.guild(ctx.guild).cookies() if ctx.guild else 0
        embed = discord.Embed(
            title="Gob's Cookie Jar",
            description=f"🍪 **{count}** cookies collected so far!",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @checks.admin()
    @commands.command(name="setnsua")
    async def setnsua(self, ctx: commands.Context, *, user_agent: str):
        """Set the NationStates API User-Agent header used by this server."""
        await self.config.guild(ctx.guild).user_agent.set(user_agent)
        await ctx.tick()
        await ctx.send(f"User-Agent set to: `{discord.utils.escape_markdown(user_agent)}`")

    @checks.mod_or_permissions(manage_guild=True)
    @commands.command(name="checkauctions")
    async def check_auctions_now(self, ctx: commands.Context):
        """Manually check auctions now (mod-only)."""
        await ctx.send("Checking auctions now…")
        processed, matches, dm_attempts, dm_successes = await self._poll_once()
        summary = (
            f"Done. Processed **{processed}** auctions. "
            f"Matches: **{matches}**. "
            f"DMs: **{dm_successes}/{dm_attempts}** sent."
        )
        await ctx.send(summary)
        await self._broadcast_log(f"🧪 **AuctionWatch** manual run: {summary}")

    # ===== Background Task =====

    @tasks.loop(minutes=30.0)
    async def poll_auctions(self):
        try:
            processed, matches, dm_attempts, dm_successes = await self._poll_once()
            # Success summary only when there are matches to avoid spam
            if matches > 0:
                await self._broadcast_log(
                    f"✅ **AuctionWatch** background run: Processed **{processed}** auctions; "
                    f"Matches: **{matches}**; DMs: **{dm_successes}/{dm_attempts}** sent."
                )
        except Exception:
            log.exception("Error in poll_auctions loop")
            await self._broadcast_log("❗ **AuctionWatch**: An unexpected error occurred in the polling loop. Check logs.")

    @poll_auctions.before_loop
    async def before_poll(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(5)

    async def _poll_once(self) -> Tuple[int, int, int, int]:
        """
        Fetch the auctions XML, parse it, and DM watchers.

        Returns:
            processed_auctions, match_count, dm_attempts, dm_successes
        """
        # Build a set of all watched (cardid, season) for quick membership checks
        all_watchers: Dict[Tuple[int, int], List[int]] = {}
        for user_id, data in (await self.config.all_users()).items():
            for cid, season in data.get("watchlist", []):
                key = (int(cid), int(season))
                all_watchers.setdefault(key, []).append(int(user_id))

        if not all_watchers:
            return 0, 0, 0, 0

        # Fetch auctions
        url = "https://www.nationstates.net/cgi-bin/api.cgi?q=cards+auctions"

        # Use one UA; prefer any guild-configured UA (take from the first guild) or fallback default
        guilds = self.bot.guilds
        user_agent = DEFAULT_GUILD["user_agent"]
        if guilds:
            ua = await self.config.guild(guilds[0]).user_agent()
            if ua:
                user_agent = ua

        headers = {"User-Agent": user_agent}

        text = None
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    log.warning("Auctions fetch failed: HTTP %s", resp.status)
                    await self._broadcast_log(f"⚠️ **AuctionWatch**: Auctions fetch failed with HTTP `{resp.status}`.")
                    return 0, 0, 0, 0
                text = await resp.text()

                # Rate limiting handling from user's policy
                try:
                    if "Ratelimit-Remaining" in resp.headers:
                        remaining = int(resp.headers["Ratelimit-Remaining"]) - 10
                        reset_time = int(resp.headers.get("Ratelimit-Reset", "1"))
                        wait_time = (reset_time / remaining) if remaining > 0 else reset_time
                        await asyncio.sleep(max(0.0, wait_time))
                except Exception:
                    pass

        if not text:
            await self._broadcast_log("⚠️ **AuctionWatch**: Auctions response was empty.")
            return 0, 0, 0, 0

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            log.exception("Failed to parse auctions XML")
            await self._broadcast_log("❌ **AuctionWatch**: Failed to parse auctions XML.")
            return 0, 0, 0, 0

        auctions = root.findall(".//AUCTION")
        now = asyncio.get_event_loop().time()
        processed = 0
        matches = 0
        dm_attempts = 0
        dm_successes = 0
        
        for a in auctions:
            try:
                cardid = int((a.findtext("CARDID") or "0").strip())
                season = int((a.findtext("SEASON") or "0").strip())
                cardname = (a.findtext("NAME") or "Unknown Card").strip()
            except Exception:
                continue
        
            processed += 1
            watchers = all_watchers.get((cardid, season), [])
            if not watchers:
                continue
        
            # We count a “match” once per auctioned card that has any watchers.
            matches += 1
        
            card_url = f"https://www.nationstates.net/page=deck/card={cardid}/season={season}"
            embed = discord.Embed(
                title=f"Watched Card Found: {cardname} Season {season}",
                description=f"I spotted a watched card in the auctions feed!\n\n**Card Link:** {card_url}",
                color=discord.Color.blurple(),
            )
            view = GobCookieView(self)
        
            for uid in watchers:
                # Per-user, per-card dedupe (3 hours)
                k = (uid, cardid, season)
                last = self._recent_notified.get(k)
                if last and (now - last) < (3 * 60 * 60):
                    # Skip this user; they were notified about this card recently
                    continue
        
                user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                if not user:
                    # Still record the timestamp so we don't hammer the API on missing users
                    self._recent_notified[k] = now
                    continue
        
                try:
                    dm_attempts += 1
                    await user.send(embed=embed, view=view)
                    dm_successes += 1
                    await self._log_for_user(user, f"📨 **AuctionWatch**: DM sent to <@{uid}> for card **{cardid} (S{season})**.")
                except discord.Forbidden:
                    msg = f"📵 **AuctionWatch**: Could not DM <@{uid}> for card **{cardid} (S{season})** (DMs disabled?)."
                    log.info(msg)
                    await self._log_for_user(user, msg)
                except Exception as e:
                    log.exception("Error DMing user %s", uid)
                    await self._log_for_user(user, f"❗ **AuctionWatch**: Error DMing <@{uid}> for card **{cardid} (S{season})**: `{e!r}`")
                finally:
                    # Mark as notified (even on failure) to avoid retry spam for 3 hours
                    self._recent_notified[k] = now
        
        # Clean old entries from recent cache (older than 6 hours)
        cutoff = now - (6 * 60 * 60)
        for k, t in list(self._recent_notified.items()):
            if t < cutoff:
                self._recent_notified.pop(k, None)
        
        return processed, matches, dm_attempts, dm_successes


    @checks.admin()
    @commands.command(name="startauctions")
    async def start_auctions(self, ctx: commands.Context):
        """Start the auction polling task (admin only)."""
        if self.poll_auctions.is_running():
            await ctx.send("⏳ Auction polling is already running.")
        else:
            self.poll_auctions.start()
            await ctx.send("✅ Auction polling has been started.")
            await self._broadcast_log("▶️ **AuctionWatch**: Background polling **started**.")

    @checks.admin()
    @commands.command(name="stopauctions")
    async def stop_auctions(self, ctx: commands.Context):
        """Stop the auction polling task (admin only)."""
        if self.poll_auctions.is_running():
            self.poll_auctions.cancel()
            await ctx.send("🛑 Auction polling has been stopped.")
            await self._broadcast_log("⏹️ **AuctionWatch**: Background polling **stopped**.")
        else:
            await ctx.send("⚠️ Auction polling is not currently running.")

    # ---------- Logging helpers ----------
    def _get_log_channel_for_guild(self, guild: Optional[discord.Guild]) -> Optional[discord.TextChannel]:
        if not guild:
            return None
        # Synchronous placeholder (kept for API symmetry); always use async accessor below.
        return None

    async def _aget_log_channel_for_guild(self, guild: Optional[discord.Guild]) -> Optional[discord.TextChannel]:
        if not guild:
            return None
        chan_id = await self.config.guild(guild).log_channel_id()
        if not chan_id:
            return None
        ch = guild.get_channel(chan_id)
        if isinstance(ch, discord.TextChannel):
            return ch
        return None

    async def _broadcast_log(self, message: str):
        """Send a message to every guild's configured log channel (dedupes by channel)."""
        seen: Set[int] = set()
        for g in self.bot.guilds:
            chan = await self._aget_log_channel_for_guild(g)
            if chan and chan.id not in seen:
                seen.add(chan.id)
                try:
                    await chan.send(message)
                except Exception:
                    log.exception("Failed to send log message to #%s in %s", chan, g)

    async def _log_for_user(self, user: discord.abc.User, message: str):
        """Find a guild the user shares that has a log channel configured; send there."""
        for g in self.bot.guilds:
            if g.get_member(user.id):
                chan = await self._aget_log_channel_for_guild(g)
                if chan:
                    try:
                        await chan.send(message)
                    except Exception:
                        log.exception("Failed to send user-scoped log to %s in %s", chan, g)
                    return
        # Fallback: broadcast once if we couldn't find a mutual with a log channel
        await self._broadcast_log(message)

    @checks.admin()
    @commands.command(name="awsetlog")
    async def aw_set_log(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set the channel for AuctionWatch logs (errors/success summaries). Defaults to current channel."""
        channel = channel or ctx.channel
        await self.config.guild(ctx.guild).log_channel_id.set(channel.id)
        await ctx.tick()
        await ctx.send(f"✅ Log channel set to {channel.mention}")

    @checks.admin()
    @commands.command(name="awlogstatus")
    async def aw_log_status(self, ctx: commands.Context):
        """Show the current AuctionWatch log channel for this server."""
        chan_id = await self.config.guild(ctx.guild).log_channel_id()
        if chan_id:
            ch = ctx.guild.get_channel(chan_id)
            if isinstance(ch, discord.TextChannel):
                return await ctx.send(f"📝 Current log channel: {ch.mention}")
        await ctx.send("ℹ️ No log channel set. Use `[p]awsetlog` here or with a channel mention.")
    # ---------- /helpers ----------


async def setup(bot: Red):
    await bot.add_cog(AuctionWatch(bot))
