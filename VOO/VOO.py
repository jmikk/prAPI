# vigil_of_origins.py
from __future__ import annotations
import traceback, time
import asyncio
import json
import logging
import re
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Deque, List, Optional
import aiohttp
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import discord
from discord import ui
from urllib.parse import urlencode
from zoneinfo import ZoneInfo  # add at top of file
from datetime import timedelta

log = logging.getLogger("red.vigil_of_origins")

FOUNDING_SSE_URL = "https://www.nationstates.net/api/founding"
GENERATED_BY = "Vigil_of_origins___by_9005____instance_run_by_By_9005"
MAX_TG_BATCH = 8
REGION_RE = re.compile(r"region=([a-z0-9_]+)", re.I)


NATION_RE = re.compile(r"nation=([a-z0-9_]+)", re.I)

class VOOControlView(ui.View):
    """Persistent control view with three buttons."""
    def __init__(self, cog: "VigilOfOrigins"):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(label="Recruit", style=discord.ButtonStyle.primary, custom_id="voo:recruit")
    async def recruit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_recruit(interaction)

    @ui.button(label="Register", style=discord.ButtonStyle.secondary, custom_id="voo:register")
    async def register_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_register(interaction)

    @ui.button(label="Leaderboard", style=discord.ButtonStyle.success, custom_id="voo:leaderboard")
    async def leaderboard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_leaderboard(interaction)

class TemplateModal(ui.Modal, title="Register TG Template"):
    template = ui.TextInput(
        label="Your template (e.g. %TEMPLATE-35972625%)",
        style=discord.TextStyle.short,
        required=True,
        max_length=64,
        placeholder="%TEMPLATE-35972625%",
    )

    def __init__(self, cog: "VigilOfOrigins"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        t = str(self.template.value).strip()
        # Basic validation: must start and end with %
        if not (t.startswith("%") and t.endswith("%")):
            await interaction.response.send_message(
                "Please include the surrounding `%` signs, e.g. `%TEMPLATE-35972625%`.",
                ephemeral=True,
            )
            return
        if interaction.guild:
            member = interaction.guild.get_member(interaction.user.id)
            if member:
                await self.cog._ensure_recruiter_role(member)
        await self.cog.config.user(interaction.user).template.set(t)
        await interaction.response.send_message("Saved! You can now use **Recruit**.", ephemeral=True)

class VOO(commands.Cog):
    """Watches NationStates founding SSE and helps recruit."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x9005_0001, force_registration=True)
        self.session: Optional[aiohttp.ClientSession] = None
        self.listener_task: Optional[asyncio.Task] = None
        self.queue: Deque[str] = deque()
        self.last_event_at: Optional[datetime] = None
        self.weekly_task: Optional[asyncio.Task] = None
        self._err_last_notice_ts: dict[int, int] = {}  # guild_id -> unix ts

        default_guild = {
            "channel_id": None,
            "control_message_id": None,
            "user_agent": "9003",
            "queue_snapshot": [],
            "region_blacklist": [],   
            "active_recruiter_role_id": None,
            "weekly_pot": 0,                         # grows +pot_increment each Recruit action
            "pot_increment_per_batch": 10,           # default: +10 per set (per Recruit button press)
            "min_weekly_payout": 100,                # minimum each eligible user receives (not drawn from pot)
            "weekly_sent": {},                       # {user_id: int}, resets weekly
            "auto_weekly_enabled": True,             # run scheduled weekly payout
            "auto_weekly_dow": 6,                    # 0=Mon ... 6=Sun
            "auto_weekly_hour": 23,
            "auto_weekly_minute": 59,
            "auto_weekly_tz": "America/Chicago",
            # per-TG dynamic reward tiers based on current queue length BEFORE dequeue:
            # pay = reward where queue_len < lt; else fallthrough to default_over_reward
            "defcon_levels": [  # evaluated by queue < lt, in ascending lt
                {"lt": 200,  "name": "Trickle",   "emoji": "💧","reward":10},
                {"lt": 300,  "name": "Stream",    "emoji": "🌿","reward":9},
                {"lt": 400,  "name": "Torrent",   "emoji": "🌪️","reward":8},
                {"lt": 500,  "name": "Geyser",    "emoji": "🧨","reward":7},
                {"lt": 800,  "name": "Flood", "emoji": "🚨","reward":6},
                {"lt": 1000, "name": "Deluge",    "emoji": "🛑","reward":5},
            ],
            "default_over_reward": 4,
            "defcon_overflow_name": "Maelstrom",
            "defcon_overflow_emoji": "🌀",
        
            "panic_enabled": True,         # announce when level rises
            "panic_cooldown_minutes": 30,  # minimum minutes between panic alerts
            "last_defcon_index": -1,       # last announced index
            "last_panic_at_ts": 0,         # unix timestamp of last panic
            "recruiter_role_id": None,  # role to ping on alerts; given on Register
                }
        
        default_user = {
            "template": None,
            "sent_count": 0,  # nations counted
        }
        self.config.register_guild(**default_guild)
        self.config.register_user(**default_user)

        # Register persistent view on startup
        self.bot.add_view(VOOControlView(self))

    # ---------- Lifecycle ----------
    async def cog_load(self):
        # Restore queue from guilds that have snapshots
        for guild in self.bot.guilds:
            snap = await self.config.guild(guild).queue_snapshot()
            if snap:
                for n in snap:
                    if n not in self.queue:
                        self.queue.append(n)
        await self.start_listener()
        if self.weekly_task is None or self.weekly_task.done():
            self.weekly_task = asyncio.create_task(self._weekly_scheduler(), name="VOO_WeeklyPayout")


    async def cog_unload(self):
        await self.stop_listener()
        if self.session:
            await self.session.close()
        if self.weekly_task and not self.weekly_task.done():
            self.weekly_task.cancel()
            try:
                await self.weekly_task
            except asyncio.CancelledError:
                pass

    def _get_nexus(self):
    # NexusExchange must be loaded as a cog; exposes add_wellcoins(user, amount)
        return self.bot.get_cog("NexusExchange")

    async def _get_per_tg_reward(self, guild: discord.Guild, queue_len_before: int) -> int:
        tiers = await self.config.guild(guild).defcon_levels()
        tiers = sorted(tiers, key=lambda x: int(x.get("lt", 0)))
        for t in tiers:
            try:
                if queue_len_before < int(t["lt"]):
                    return int(t["reward"])
            except Exception:
                continue
        return int(await self.config.guild(guild).default_over_reward())
    
    async def _bump_weekly_pot(self, guild: discord.Guild, batches: int = 1):
        inc = int(await self.config.guild(guild).pot_increment_per_batch())
        current = int(await self.config.guild(guild).weekly_pot())
        await self.config.guild(guild).weekly_pot.set(current + (inc * max(1, batches)))
    
    async def _add_weekly_sent(self, user: discord.abc.User, guild: discord.Guild, count: int):
        uid = str(user.id)
        async with self.config.guild(guild).weekly_sent() as ws:
            ws[uid] = int(ws.get(uid, 0)) + int(count)
    
    async def _ensure_active_role(self, member: discord.Member):
        role_id = await self.config.guild(member.guild).active_recruiter_role_id()
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if role and role not in member.roles:
            try:
                await member.add_roles(role, reason="Recruiter sent at least 1 TG this week")
            except Exception:
                pass
    
    async def _clear_active_role_all(self, guild: discord.Guild):
        role_id = await self.config.guild(guild).active_recruiter_role_id()
        if not role_id:
            return
        role = guild.get_role(role_id)
        if not role:
            return
        try:
            for m in list(role.members):
                try:
                    await m.remove_roles(role, reason="Weekly reset")
                except Exception:
                    continue
        except Exception:
            pass

    def _norm_region(self, r: str) -> str:
        # "The East Pacific" -> "the_east_pacific"
        return re.sub(r"\s+", "_", r.strip().lower())


    # ---------- SSE Listener ----------
    async def start_listener(self):
        if self.listener_task and not self.listener_task.done():
            return
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None))
        self.listener_task = asyncio.create_task(self._run_listener(), name="VOO_SSE_Listener")
        await self._refresh_all_embeds()


    async def stop_listener(self):
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
        self.listener_task = None
        await self._refresh_all_embeds()


    async def _run_listener(self):
        """Long-running SSE reader with auto-reconnect and idle timeout (1h)."""
        idle_limit = timedelta(hours=1)
        backoff = 3
    
        while True:
            try:
                ua = await self._get_user_agent_global()
                headers = {"User-Agent": ua}
                log.info("Connecting to SSE: %s (UA=%s)", FOUNDING_SSE_URL, ua)
                async with self.session.get(FOUNDING_SSE_URL, headers=headers) as resp:
                    resp.raise_for_status()
                    self.last_event_at = datetime.now(timezone.utc)
                    backoff = 3  # ✅ reset backoff on successful connect
    
                    try:
                        async for raw_line in resp.content:
                            # reconnect if idle too long
                            if self.last_event_at and datetime.now(timezone.utc) - self.last_event_at > idle_limit:
                                log.warning("SSE idle > 1 hour; reconnecting.")
                                break
    
                            line = raw_line.decode("utf-8", errors="ignore").strip()
    
                            # count activity on blanks/heartbeats/fields
                            if line == "" or line.startswith(":") or line.startswith(("event:", "id:", "retry:")):
                                self.last_event_at = datetime.now(timezone.utc)
                                continue
    
                            if line.startswith("data:"):
                                payload = line[5:].strip()
                                self.last_event_at = datetime.now(timezone.utc)
                                await self._handle_sse_data(payload)
                                continue
    
                    except aiohttp.http_exceptions.TransferEncodingError:
                        # ✅ benign mid-chunk close; reconnect immediately, no notifier
                        log.debug("SSE stream TE error; fast reconnect.")
                        continue
                    except (aiohttp.ClientPayloadError, aiohttp.ClientOSError, ConnectionResetError) as e:
                        # ✅ common stream read errors; fast reconnect, no notifier
                        log.debug("SSE stream read error (%r); fast reconnect.", e)
                        continue
    
                # normal reconnect path (e.g., idle break)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
    
            except asyncio.CancelledError:
                log.info("SSE listener cancelled.")
                raise
            except Exception as e:
                # Real errors: log and notify (your notifier), then backoff
                log.exception("SSE listener error: %r", e)
                try:
                    await self._notify_listener_error("will attempt to reconnect shortly", e)
                except Exception:
                    pass
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)



    async def _handle_sse_data(self, data_line: str):
        """
        Parse one SSE 'data:' line, extract nation/region, and queue if allowed.
        Rules:
          - ignore nations whose names end with digits (e.g., 'testlandia123')
          - ignore nations from any blacklisted region (per-guild blacklists)
          - keep newest-first; no duplicates
        """
        try:
            obj = json.loads(data_line)
        except json.JSONDecodeError:
            log.debug("Non-JSON data: %s", data_line)
            return

        html = obj.get("htmlStr") or ""
        text = obj.get("str") or ""

        # Extract nation from html first:  <a href="nation=the_parya" ...>
        m_n_html = NATION_RE.search(html)
        # Fallback from text form: @@the_parya@@
        m_n_text = re.search(r"@@([a-z0-9_]+)@@", text, re.I)
        nation = (m_n_html.group(1) if m_n_html else (m_n_text.group(1) if m_n_text else None))

        # Extract region similarly:
        # from html: <a href="region=osiris" ...>
        m_r_html = REGION_RE.search(html) if 'REGION_RE' in globals() else None
        # from text: %%osiris%%
        m_r_text = re.search(r"%%([a-z0-9_]+)%%", text, re.I)
        region = (m_r_html.group(1) if m_r_html else (m_r_text.group(1) if m_r_text else None))

        if not nation:
            return

        nation = nation.lower()

        # Skip any nation whose name ends with digits
        if re.search(r"\d+$", nation):
            return

        # Regional blacklist check (global effect across guilds)
        if region:
            region_norm = region.lower()
            try:
                for guild in self.bot.guilds:
                    bl = await self.config.guild(guild).region_blacklist()
                    if region_norm in bl:
                        return
            except Exception:
                # If config read fails, fail open (don't queue) to be safe
                return

        # De-dup and queue (newest first)
        if nation in self.queue:
            return

        self.queue.appendleft(nation)
        for guild in self.bot.guilds:
            await self._maybe_panic_on_rise(guild, len(self.queue))
        # Persist and refresh UI
        await self._persist_queue_snapshot()
        await self._refresh_all_embeds()


    async def _persist_queue_snapshot(self):
        # Persist only up to, say, 300 to avoid bloating config
        snapshot = list(self.queue)[:300]
        # Store to all guilds that have the cog configured
        for guild in self.bot.guilds:
            await self.config.guild(guild).queue_snapshot.set(snapshot)

    async def _get_user_agent_global(self) -> str:
        # Use first configured guild UA; if none, default
        for guild in self.bot.guilds:
            ua = await self.config.guild(guild).user_agent()
            if ua:
                return ua
        return 



    async def post_or_update_control_message(self, guild: discord.Guild, channel: discord.TextChannel | discord.Thread):
        await self.config.guild(guild).channel_id.set(channel.id)
        await self._edit_control_message(guild)




    # ---------- Button Handlers ----------
    async def handle_register(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TemplateModal(self))

    async def handle_leaderboard(self, interaction: discord.Interaction):
        """Show top recruiters by total nations sent."""
        data: dict = await self.config.all_users()  # <-- await to get dict
        if not data:
            await interaction.response.send_message("No stats yet. Be the first to recruit!", ephemeral=True)
            return

        # Build (user_id:int, sent_count:int) list
        rows = []
        for uid_str, urec in data.items():
            try:
                uid = int(uid_str)
            except (TypeError, ValueError):
                continue
            sent = int(urec.get("sent_count", 0) or 0)
            if sent > 0:
                rows.append((uid, sent))

        if not rows:
            await interaction.response.send_message("No stats yet. Be the first to recruit!", ephemeral=True)
            return

        # Sort by sent_count desc, then by user id for stable order
        rows.sort(key=lambda x: (-x[1], x[0]))

        # Prepare top 10 lines
        lines = []
        for i, (uid, cnt) in enumerate(rows[:10], start=1):
            name = f"<@{uid}>"
            # If we have a guild context, try to get a nicer display name
            if interaction.guild:
                member = interaction.guild.get_member(uid)
                if member:
                    name = member.display_name
            lines.append(f"**{i}.** {name} — **{cnt}** nations")

        # Send ephemeral embed
        embed = discord.Embed(
            title="Recruitment Leaderboard",
            description="\n".join(lines),
            color=discord.Color.green(),
        )
        total_unique = len({u for u, _ in rows})
        total_sent = sum(cnt for _, cnt in rows)
        embed.set_footer(text=f"Tracked users: {total_unique} • Total nations recruited: {total_sent}")

        await interaction.response.send_message(embed=embed, ephemeral=True)


    async def handle_recruit(self, interaction: discord.Interaction):
        user_conf = self.config.user(interaction.user)
        template = await user_conf.template()
        if not template:
            await interaction.response.send_message(
                "You must **Register** your template first (e.g. `%TEMPLATE-35972625%`).",
                ephemeral=True,
            )
            return

       # Build list of up to 8 newest nations
        if not self.queue:
            await interaction.response.send_message("The queue is empty right now.", ephemeral=True)
            return
        
        qlen_before = len(self.queue)

        batch: List[str] = []
        while self.queue and len(batch) < MAX_TG_BATCH:
            batch.append(self.queue.popleft())

        await self._persist_queue_snapshot()
        await self._refresh_all_embeds()
        tgto = ",".join(batch)

        # IMPORTANT: do NOT pre-encode message or tgto.
        # Let the client encode once so % -> %25 and commas -> %2C (once).
        message_raw = template.strip()  # e.g. "%TEMPLATE-35972625%"

        # generated_by is safe as-is (only underscores), but encode if you ever add spaces.
        link = (
            "https://www.nationstates.net/page=compose_telegram"
            f"?tgto={tgto}"
            f"&message={message_raw}"
            f"&generated_by={GENERATED_BY}"
        )


        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        nexus = self._get_nexus()
        instant_coins = 0
        if nexus and member:
            reward_per_tg = await self._get_per_tg_reward(member.guild, qlen_before)
            instant_coins = reward_per_tg * len(batch)
            try:
                await nexus.add_wellcoins(member, float(instant_coins))
            except Exception:
                log.exception("Failed paying per-TG reward to %s", member)
        
        if member:
            await self._add_weekly_sent(member, member.guild, len(batch))
            await self._ensure_active_role(member)
            await self._bump_weekly_pot(member.guild, batches=1)



        # Count stats (per-nation)
        current = await user_conf.sent_count()
        await user_conf.sent_count.set(current + len(batch))

                # Build a link+reminder view
        class RecruitView(discord.ui.View):
            def __init__(self, cog: "VOO", link_url: str):
                super().__init__(timeout=1200)
                self.cog = cog
                # Link button on top row
                self.add_item(
                    discord.ui.Button(
                        label="Open Recruit Link",
                        url=link_url,
                        style=discord.ButtonStyle.link,
                        row=0
                    )
                )

            @discord.ui.button(label="Remind in 40s", style=discord.ButtonStyle.secondary, row=1, custom_id="voo:remind:40")
            async def remind_40(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self._schedule(interaction, 40)

            @discord.ui.button(label="Remind in 50s", style=discord.ButtonStyle.secondary, row=1, custom_id="voo:remind:50")
            async def remind_50(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self._schedule(interaction, 50)

            @discord.ui.button(label="Remind in 60s", style=discord.ButtonStyle.secondary, row=1, custom_id="voo:remind:60")
            async def remind_60(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self._schedule(interaction, 60)

            @discord.ui.button(label="Remind in 120s", style=discord.ButtonStyle.secondary, row=1, custom_id="voo:remind:120")
            async def remind_120(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self._schedule(interaction, 120)

            # inside RecruitView in handle_recruit
            async def _schedule(self, interaction: discord.Interaction, seconds: int):
                # 1) silently defer so Discord is satisfied (no message shown)
                try:
                    await interaction.response.defer(ephemeral=True)  # no ack text
                except discord.InteractionResponded:
                    pass  # already deferred/responded somehow
            
                # 2) schedule the reminder; it will send the ephemeral followup later
                await self.cog._schedule_reminder(interaction, max(1, int(seconds)))
        view = RecruitView(self, link)


        await interaction.response.send_message(
            content=(
                f"Here’s your recruitment link for **{len(batch)}** nation(s).\n"
                f"Instant reward: **{instant_coins}** Wellcoins\n\n"
                f"Targets: `{tgto}`"
            ),
            view=view,
            ephemeral=True,
        )


    # ---------- Commands ----------
    @commands.group(name="voo")
    @checks.admin_or_permissions(manage_guild=True)
    async def voo_group(self, ctx: commands.Context):
        """Vigil of Origins controls."""
        pass

    @voo_group.command(name="setchannel")
    async def set_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set the control channel and (re)post the button embed."""
        channel = channel or ctx.channel
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await self.post_or_update_control_message(ctx.guild, channel)
        await ctx.send(f"Control embed is set in {channel.mention}.")

    @voo_group.command(name="setuseragent")
    async def set_user_agent(self, ctx: commands.Context, user_agent: str):
        """Set the NationStates User-Agent header (e.g., 9003, 9005, etc.)."""
        await self.config.guild(ctx.guild).user_agent.set(user_agent.strip())
        await ctx.send(f"User-Agent set to `{user_agent.strip()}`. Restarting listener…")
        await self.stop_listener()
        await self.start_listener()

    @voo_group.command(name="start")
    async def start_cmd(self, ctx: commands.Context):
        """Start the SSE listener."""
        await self.start_listener()
        await self._refresh_all_embeds()
        await ctx.send("SSE listener started.")

    @voo_group.command(name="stop")
    async def stop_cmd(self, ctx: commands.Context):
        """Stop the SSE listener."""
        await self.stop_listener()
        await self._refresh_all_embeds()

        await ctx.send("SSE listener stopped.")

    @voo_group.command(name="queue")
    async def show_queue(self, ctx: commands.Context, peek: int = 10):
        """Show queue length and a peek at the upcoming nations."""
        qlen = len(self.queue)
        preview = list(self.queue)[:max(0, min(peek, 25))]
        msg = f"Queue length: **{qlen}**"
        if preview:
            msg += "\nNext up: " + ", ".join(preview)
        await ctx.send(msg)

    @voo_group.command(name="clearqueue")
    async def clear_queue(self, ctx: commands.Context):
        """Clear the entire queue."""
        self.queue.clear()
        await self._persist_queue_snapshot()
        await self._refresh_all_embeds()
        await ctx.send("Queue cleared.")

    @voo_group.command(name="resetstats")
    async def reset_stats(self, ctx: commands.Context):
        """Reset all users' sent counts."""
        async with self.config.all_users() as allu:
            for uid in list(allu.keys()):
                allu[uid]["sent_count"] = 0
        await ctx.send("Leaderboard stats reset.")

    async def _get_status_text(self) -> str:
        if self.listener_task and not self.listener_task.done():
            return "🟢 SSE: **ON**"
        return "🔴 SSE: **OFF**"


    async def _upsert_control_message(self, guild: discord.Guild):
        """Ensure the control embed is present, updated, and is the most recent message."""
        channel_id = await self.config.guild(guild).channel_id()
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        qlen = len(self.queue)
        status = await self._get_status_text()
        reward, lvl_name, lvl_emoji, idx, total = await self._current_reward_and_defcon(guild, qlen)
        embed = self._build_control_embed(qlen, status, reward, lvl_name, lvl_emoji, idx, total)

        view = VOOControlView(self)
        msg_id = await self.config.guild(guild).control_message_id()

        # If we have a message stored, try to fetch it
        message = None
        if msg_id:
            try:
                message = await channel.fetch_message(msg_id)
            except Exception:
                message = None

        # Determine if the stored message is the most recent message in the channel
        is_latest = False
        try:
            # channel.last_message_id is cheap; if None, fetch last message via history
            last_id = channel.last_message_id
            if last_id is None:
                async for m in channel.history(limit=1):
                    last_id = m.id
                    break
            if last_id and msg_id and last_id == msg_id:
                is_latest = True
        except Exception:
            pass

        if message and is_latest:
            # Just edit in place
            try:
                await message.edit(embed=embed, view=view)
                return
            except Exception:
                pass

        # If here: either no message, or it's not latest; delete old and post new at bottom
        if message:
            try:
                await message.delete()
            except Exception:
                pass

        new_msg = await channel.send(embed=embed, view=view)
        await self.config.guild(guild).control_message_id.set(new_msg.id)
  

    def _last_event_markdown(self) -> str:
        if not self.last_event_at:
            return "Last event: —"
        epoch = int(self.last_event_at.replace(tzinfo=timezone.utc).timestamp())
        return f"Last event: <t:{epoch}:R> (<t:{epoch}:F>)"

    async def _get_status_text(self) -> str:
        on = self.listener_task and not self.listener_task.done()
        status = "🟢 SSE: **ON**" if on else "🔴 SSE: **OFF**"
        return f"{status}\n{self._last_event_markdown()}"

    def _build_control_embed(self, qlen: int, status_text: str, reward: int, level_name: str, level_emoji: str, idx: int, total: int) -> discord.Embed:
        embed = discord.Embed(
            title="Vigil of Origins — Founding Monitor",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Status", value=status_text, inline=False)
        embed.add_field(name="Queue", value=f"**{qlen} nations**", inline=False)
        embed.add_field(name="Current Reward", value=f"**{reward}** Wellcoins per TG", inline=True)
    
        bar = self._level_bar(idx, total)
        embed.add_field(
            name="Wellspring Alert",
            value=f"{level_emoji} **{level_name}**  {bar}",
            inline=True,
        )
    
        embed.add_field(
            name="How to Recruit",
            value=(
                "• **Recruit**: Private TG link to the **newest** up to 8 queued nations (then removes them).\n"
                "• **Register**: Save your `%TEMPLATE-...%` once; your Recruit link will include it.\n"
                "• **Leaderboard**: See who has recruited the most nations."
            ),
            inline=False,
        )
        return embed


    async def _edit_control_message(self, guild: discord.Guild):
        """Edit the existing control embed in place (no bump). If missing, post once."""
        channel_id = await self.config.guild(guild).channel_id()
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        qlen = len(self.queue)
        status = await self._get_status_text()
        reward, lvl_name, lvl_emoji, idx, total = await self._current_reward_and_defcon(guild, qlen)
        embed = self._build_control_embed(qlen, status, reward, lvl_name, lvl_emoji, idx, total)
        
        view = VOOControlView(self)

        msg_id = await self.config.guild(guild).control_message_id()
        if msg_id:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed, view=view)
                return
            except Exception:
                pass  # fall through to post if missing/deleted

        new_msg = await channel.send(embed=embed, view=view)
        await self.config.guild(guild).control_message_id.set(new_msg.id)

    async def _refresh_all_embeds(self):
        """Refresh (edit in place) the control embed for every configured guild."""
        for guild in self.bot.guilds:
            try:
                await self._edit_control_message(guild)
            except Exception:
                pass


    @commands.command(name="bumpvoo")
    @checks.admin_or_permissions(manage_guild=True)
    async def bump_voo(self, ctx: commands.Context):
        """Delete and repost the control embed to push it to the bottom."""
        new_msg = await self._bump_control_message(ctx.guild)
        if new_msg:
            await ctx.send(f"✅ Control embed bumped to the bottom in {new_msg.channel.mention}.")
        else:
            await ctx.send("Failed to bump: no valid control channel set.")



    @voo_group.group(name="blacklist", invoke_without_command=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def voo_blacklist(self, ctx: commands.Context):
        """Manage the regional blacklist (queue ignores nations from these regions)."""
        bl = await self.config.guild(ctx.guild).region_blacklist()
        if not bl:
            await ctx.send("Regional blacklist is currently **empty**.")
        else:
            await ctx.send("Blacklisted regions:\n- " + "\n- ".join(sorted(bl)))

    @voo_blacklist.command(name="add")
    async def voo_blacklist_add(self, ctx: commands.Context, *, region: str):
        """Add a region to the blacklist (spaces ok)."""
        r = self._norm_region(region)
        async with self.config.guild(ctx.guild).region_blacklist() as bl:
            if r in bl:
                await ctx.send(f"`{r}` is already blacklisted.")
                return
            bl.append(r)
        await ctx.send(f"Added `{r}` to the regional blacklist.")

    @voo_blacklist.command(name="remove")
    async def voo_blacklist_remove(self, ctx: commands.Context, *, region: str):
        """Remove a region from the blacklist."""
        r = self._norm_region(region)
        async with self.config.guild(ctx.guild).region_blacklist() as bl:
            if r not in bl:
                await ctx.send(f"`{r}` was not on the blacklist.")
                return
            bl.remove(r)
        await ctx.send(f"Removed `{r}` from the regional blacklist.")

    @voo_blacklist.command(name="clear")
    async def voo_blacklist_clear(self, ctx: commands.Context):
        """Clear the regional blacklist."""
        await self.config.guild(ctx.guild).region_blacklist.set([])
        await ctx.send("Cleared the regional blacklist.")

    async def _weekly_scheduler(self):
        """Runs every ~60s and triggers weekly payout at configured time."""
        while True:
            try:
                for guild in self.bot.guilds:
                    gconf = self.config.guild(guild)
                    if not await gconf.auto_weekly_enabled():
                        continue
                    try:
                        tz = ZoneInfo(await gconf.auto_weekly_tz())
                    except Exception:
                        tz = ZoneInfo("America/Chicago")
                    now_local = datetime.now(tz)
                    dow = int(await gconf.auto_weekly_dow())
                    hh = int(await gconf.auto_weekly_hour())
                    mm = int(await gconf.auto_weekly_minute())
    
                    # Fire once within the target minute; use a small marker to avoid double-run
                    key = f"weekly_marker_{now_local.date().isoformat()}"
                    ran_today = await self.bot.db.guild(guild).get_raw(key, default=False)
                    if (now_local.weekday() == dow and now_local.hour == hh and now_local.minute == mm and not ran_today):
                        await self._run_weekly_payout(guild)
                        await self.bot.db.guild(guild).set_raw(key, value=True)
                    elif now_local.hour == 0 and now_local.minute < 5:
                        # clear marker near midnight local
                        await self.bot.db.guild(guild).set_raw(key, value=False)
                await asyncio.sleep(600)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Weekly scheduler error")
                await asyncio.sleep(600)

    async def _run_weekly_payout(self, guild: discord.Guild):
        """Distribute weekly pot, post leaderboard with % breakdown, then reset."""
        gconf = self.config.guild(guild)
        ws: dict = await gconf.weekly_sent()
        pot = int(await gconf.weekly_pot())
        min_payout = int(await gconf.min_weekly_payout())
        channel_id = await gconf.channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
    
        # Aggregate rows
        rows = []
        total_sent = 0
        for uid_str, cnt in (ws or {}).items():
            try:
                cnt = int(cnt)
                if cnt > 0:
                    uid = int(uid_str)
                    rows.append((uid, cnt))
                    total_sent += cnt
            except Exception:
                continue
    
        embed = discord.Embed(title="Weekly Recruitment Results", color=discord.Color.gold())
    
        if not rows or total_sent == 0:
            embed.description = "No recruiters this week."
            try:
                if channel:
                    await channel.send(embed=embed)
            except Exception:
                pass
            # Reset anyway
            await gconf.weekly_pot.set(0)
            await gconf.weekly_sent.set({})
            await self._clear_active_role_all(guild)
            return
    
        # Sort; build payouts
        rows.sort(key=lambda x: (-x[1], x[0]))
    
        # Compute pot shares (rounded); last user absorbs rounding drift
        payouts = []  # (uid, cnt, pct, share_from_pot, min_bonus)
        pot_paid_total = 0
        for idx, (uid, cnt) in enumerate(rows):
            pct = (cnt / total_sent) * 100.0
            share = round((cnt / total_sent) * pot)
            if idx == len(rows) - 1:
                share = pot - pot_paid_total
            pot_paid_total += max(0, share)
            payouts.append((uid, cnt, pct, max(0, share), max(0, min_payout)))
    
        # Pay with NexusExchange
        nexus = self._get_nexus()
        if nexus:
            for uid, cnt, pct, share, bonus in payouts:
                member = guild.get_member(uid)
                if not member:
                    continue
                # Share from pot
                if share > 0:
                    try:
                        await nexus.add_wellcoins(member, float(share))
                    except Exception:
                        log.exception("Pot share payout failed for %s", member)
                # Minimum (not from pot)
                if bonus > 0:
                    try:
                        await nexus.add_wellcoins(member, float(bonus))
                    except Exception:
                        log.exception("Minimum payout failed for %s", member)
    
        # Build nice per-user lines: Name — TGs • xx.xx% → share WC (+min WC)
        lines = []
        for i, (uid, cnt, pct, share, bonus) in enumerate(payouts, start=1):
            member = guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            pct_str = f"{pct:.2f}%"
            if bonus > 0:
                line = f"**{i}.** {name} — **{cnt}** TGs • {pct_str} → **{share}** WC + **{bonus}** WC"
            else:
                line = f"**{i}.** {name} — **{cnt}** TGs • {pct_str} → **{share}** WC"
            lines.append(line)
    
        # Compose embed
        embed.description = "\n".join(lines[:50])  # safety cap
        embed.add_field(name="Weekly Pot (distributed)", value=f"{pot} WC (paid {pot_paid_total} WC)", inline=True)
        embed.add_field(name="Salary", value=f"{min_payout} WC (not from pot)", inline=True)
        embed.set_footer(text=f"Total TGs: {total_sent} • Recruiters paid: {len(payouts)}")
    
        # Announce
        try:
            if channel:
                await channel.send(embed=embed)
        except Exception:
            pass
    
        # Cleanup
        await gconf.weekly_pot.set(0)
        await gconf.weekly_sent.set({})
        await self._clear_active_role_all(guild)


    @voo_group.command(name="setactiverole")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_active_role(self, ctx: commands.Context, role: discord.Role):
        """Set the 'Active Recruiter' role to assign weekly."""
        await self.config.guild(ctx.guild).active_recruiter_role_id.set(role.id)
        await ctx.send(f"Active Recruiter role set to {role.mention}")
    
    @voo_group.group(name="rewards", invoke_without_command=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def rewards_group(self, ctx: commands.Context):
        """Show per-TG reward tiers and defaults."""
        tiers = await self.config.guild(ctx.guild).defcon_levels()
        tiers = sorted(tiers, key=lambda x: int(x.get("lt", 0)))
        over = await self.config.guild(ctx.guild).default_over_reward()
        lines = [f"• queue < {t['lt']}: {t['reward']} WC" for t in tiers]
        lines.append(f"• otherwise: {over} WC")
        await ctx.send("Per-TG reward tiers:\n" + "\n".join(lines))
    
    @rewards_group.command(name="set")
    async def rewards_set(self, ctx: commands.Context, lt: int, reward: int):
        """Set or update a tier: pay `reward` WC per TG when queue < `lt`."""
        lt, reward = int(lt), int(reward)
        async with self.config.guild(ctx.guild).defcon_levels() as tiers:
            # upsert
            for t in tiers:
                if int(t.get("lt", -1)) == lt:
                    t["reward"] = reward
                    break
            else:
                tiers.append({"lt": lt, "reward": reward})
        await ctx.send(f"Tier updated: queue < {lt} → {reward} WC")
    
    @rewards_group.command(name="remove")
    async def rewards_remove(self, ctx: commands.Context, lt: int):
        """Remove a tier by 'lt' threshold."""
        lt = int(lt)
        async with self.config.guild(ctx.guild).defcon_levels() as tiers:
            new = [t for t in tiers if int(t.get("lt", -1)) != lt]
            tiers.clear()
            tiers.extend(new)
        await ctx.send(f"Removed tier with lt={lt}")
    
    @rewards_group.command(name="setdefault")
    async def rewards_setdefault(self, ctx: commands.Context, reward: int):
        """Set default per-TG reward when queue >= highest threshold."""
        await self.config.guild(ctx.guild).default_over_reward.set(int(reward))
        await ctx.send(f"Default over-threshold reward set to {reward} WC")
    
    @voo_group.command(name="setpotincrement")
    async def set_pot_increment(self, ctx: commands.Context, amount: int):
        """Set how much the weekly pot grows per Recruit action (default 10)."""
        await self.config.guild(ctx.guild).pot_increment_per_batch.set(int(amount))
        await ctx.send(f"Pot increment per set updated to {amount} WC")
    
    @voo_group.command(name="setminweekly")
    async def set_min_weekly(self, ctx: commands.Context, amount: int):
        """Set minimum weekly payout per eligible user (not drawn from pot)."""
        await self.config.guild(ctx.guild).min_weekly_payout.set(int(amount))
        await ctx.send(f"Minimum weekly payout set to {amount} WC")
    
    @voo_group.command(name="weeklypayout")
    async def weekly_payout_cmd(self, ctx: commands.Context):
        """Run weekly payout now (manual trigger)."""
        await self._run_weekly_payout(ctx.guild)
        await ctx.send("Weekly payout executed.")
    
    @voo_group.command(name="autosettlement")
    async def auto_settlement(self, ctx: commands.Context, enabled: bool, dow: int = 6, hour: int = 23, minute: int = 59, tz: str = "America/Chicago"):
        """
        Enable/disable automatic weekly payout and set schedule.
        dow: 0=Mon ... 6=Sun
        """
        await self.config.guild(ctx.guild).auto_weekly_enabled.set(bool(enabled))
        await self.config.guild(ctx.guild).auto_weekly_dow.set(int(dow))
        await self.config.guild(ctx.guild).auto_weekly_hour.set(int(hour))
        await self.config.guild(ctx.guild).auto_weekly_minute.set(int(minute))
        await self.config.guild(ctx.guild).auto_weekly_tz.set(str(tz))
        state = "enabled" if enabled else "disabled"
        await ctx.send(f"Auto weekly payout {state} — schedule set to DOW={dow} {hour:02d}:{minute:02d} {tz}")

    @voo_group.command(name="testpayout")
    @checks.admin_or_permissions(manage_guild=True)
    async def test_payout(self, ctx: commands.Context, minutes: int = 5, tz: str = "America/Chicago"):
        """
        Schedule the weekly payout to run X minutes from now (default 5).
        Also enables auto-settlement and clears the run marker for that date.
        Usage: [p]voo testpayout 5 America/Chicago
        """
        minutes = max(1, int(minutes))  # at least 1 minute
    
        # Compute target time in the requested timezone
        try:
            zone = ZoneInfo(tz)
        except Exception:
            await ctx.send(f"Unknown timezone `{tz}`. Using America/Chicago.")
            tz = "America/Chicago"
            zone = ZoneInfo(tz)
    
        now_local = datetime.now(zone)
        target = now_local + timedelta(minutes=minutes)
    
        # Configure auto settlement to the target minute
        await self.config.guild(ctx.guild).auto_weekly_enabled.set(True)
        await self.config.guild(ctx.guild).auto_weekly_tz.set(tz)
        await self.config.guild(ctx.guild).auto_weekly_dow.set(target.weekday())  # 0=Mon...6=Sun
        await self.config.guild(ctx.guild).auto_weekly_hour.set(target.hour)
        await self.config.guild(ctx.guild).auto_weekly_minute.set(target.minute)
    
        # Clear the "already ran" marker for the target date so it will fire
        # (This matches the marker logic used in _weekly_scheduler)
        key = f"weekly_marker_{target.date().isoformat()}"
        try:
            await self.bot.db.guild(ctx.guild).set_raw(key, value=False)
        except Exception:
            # If your bot.db isn't available, silently ignore; it will likely still trigger.
            pass
    
        # Confirm to user
        when_str = target.strftime("%Y-%m-%d %H:%M")
        await ctx.send(
            f"✅ Auto settlement scheduled **{minutes} min** from now at **{when_str} {tz}** "
            f"(DoW={target.weekday()}, {target.hour:02d}:{target.minute:02d}).\n"
            f"It will run once when the scheduler ticks that minute."
        )
    
    async def _schedule_reminder(self, interaction: discord.Interaction, seconds: int):
        """
        After `seconds`, send:
          1) an *ephemeral* reminder to the clicker, and
          2) a public ping in the control channel (auto-delete if configured).
        """
        user = interaction.user
        guild = interaction.guild
    
        # resolve target channel (prefer control channel; else system; else first sendable text channel)
        async def _resolve_channel() -> Optional[discord.TextChannel]:
            if not guild:
                return None
            try:
                channel_id = await self.config.guild(guild).channel_id()
                if channel_id:
                    ch = guild.get_channel(channel_id)
                    if ch and ch.permissions_for(guild.me).send_messages:
                        return ch
            except Exception:
                pass
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                return guild.system_channel
            for c in guild.text_channels:
                if c.permissions_for(guild.me).send_messages:
                    return c
            return None
    
        channel = await _resolve_channel()
        delete_after = 0
        try:
            delete_after = int(await self.config.guild(guild).reminder_public_delete_after())
        except Exception:
            delete_after = 5  # fallback
    
        async def _job():
            try:
                await asyncio.sleep(max(1, int(seconds)))
                # 2) public ping (optionally auto-delete)
                if channel:
                    try:
                        if delete_after and delete_after > 0:
                            await channel.send(
                                content=f"{user.mention} ⏰ Recruit reminder!",
                                delete_after=float(delete_after),
                            )
                        else:
                            await channel.send(content=f"{user.mention} ⏰ Recruit reminder!")
                    except Exception:
                        pass
            except Exception:
                log.exception("Failed to deliver reminder for %s", user)
    
        asyncio.create_task(
            _job(),
            name=f"VOO_Reminder_{guild.id if guild else 'dm'}_{user.id}_{seconds}",
        )

    async def _current_reward_and_defcon(self, guild: discord.Guild, qlen: int):
        """Return (reward_per_tg:int, level_name:str, emoji:str, idx:int, total_levels:int)."""
        # reward from your existing tier logic
        reward = await self._get_per_tg_reward(guild, qlen)
    
        levels = await self.config.guild(guild).defcon_levels()
        levels = sorted(levels, key=lambda x: int(x.get("lt", 0)))
        overflow_name  = await self.config.guild(guild).defcon_overflow_name()
        overflow_emoji = await self.config.guild(guild).defcon_overflow_emoji()
    
        idx = None
        for i, lv in enumerate(levels):
            try:
                if qlen < int(lv["lt"]):
                    idx = i
                    name  = lv.get("name", f"Level {i+1}")
                    emoji = lv.get("emoji", "✨")
                    break
            except Exception:
                continue
    
        if idx is None:
            # overflow
            idx = len(levels)
            name  = overflow_name or "Overflow"
            emoji = overflow_emoji or "🌀"
    
        return int(reward), str(name), str(emoji), int(idx), int(len(levels))
    
    async def _maybe_panic_on_rise(self, guild: discord.Guild, qlen: int):
        """If DEFCON index increased & cooldown passed, post a short alert that pings the Recruiter role."""
        reward, name, emoji, idx, total = await self._current_reward_and_defcon(guild, qlen)
    
        gconf = self.config.guild(guild)
        if not await gconf.panic_enabled():
            await gconf.last_defcon_index.set(idx)
            return
    
        last_idx = int(await gconf.last_defcon_index())
        now_ts = int(datetime.now(timezone.utc).timestamp())
        last_panic = int(await gconf.last_panic_at_ts())
        cooldown = max(0, int(await gconf.panic_cooldown_minutes())) * 60
    
        # resolve control channel
        channel = None
        try:
            ch_id = await gconf.channel_id()
            if ch_id:
                ch = guild.get_channel(ch_id)
                if isinstance(ch, (discord.TextChannel, discord.Thread)):
                    channel = ch
        except Exception:
            pass
    
        # resolve recruiter role mention (if configured)
        role_mention = ""
        try:
            rid = await gconf.recruiter_role_id()
            if rid:
                role = guild.get_role(int(rid))
                if role:
                    role_mention = role.mention + " "
        except Exception:
            pass
    
        if idx > last_idx and (now_ts - last_panic >= cooldown):
            if channel:
                try:
                    bar = self._level_bar(idx, total)
                    await channel.send(
                        content=(
                            f"{role_mention}{emoji} **Wellspring Alert risen to {name}** "
                            f"({idx+1}/{total+1})\n"
                            f"Queue: **{qlen}** • Current reward: **{reward} WC/TG**\n{bar}"
                        ),
                        allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
                    )
                    await gconf.last_panic_at_ts.set(now_ts)
                    # bump embed after alert
                    await self._bump_control_message(guild)
                except Exception:
                    log.exception("Failed to send panic alert")
        await gconf.last_defcon_index.set(idx)


    
    def _level_bar(self, idx: int, total: int, width: int = 10) -> str:
        """Simple bar like [██████░░░░] where idx grows from 0..total."""
        # map idx to filled proportion
        denom = max(1, total + 1)
        filled = max(0, min(width, round(((idx + 1) / denom) * width)))
        return "[" + "█" * filled + "░" * (width - filled) + "]"

    @voo_group.group(name="defcon", invoke_without_command=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def defcon_group(self, ctx: commands.Context):
        """Show DEFCON-style Wellspring levels."""
        levels = await self.config.guild(ctx.guild).defcon_levels()
        levels = sorted(levels, key=lambda x: int(x.get("lt", 0)))
        over_name  = await self.config.guild(ctx.guild).defcon_overflow_name()
        over_emoji = await self.config.guild(ctx.guild).defcon_overflow_emoji()
        lines = [f"• queue < {lv['lt']}: {lv.get('emoji','✨')} {lv.get('name','Level')}" for lv in levels]
        lines.append(f"• otherwise: {over_emoji} {over_name}")
        await ctx.send("**Wellspring Levels**\n" + "\n".join(lines))
    
    @defcon_group.command(name="set")
    async def defcon_set(self, ctx: commands.Context, lt: int, name: str, emoji: str = "✨"):
        """Add/update a level: when queue < lt, show (emoji name)."""
        lt = int(lt)
        async with self.config.guild(ctx.guild).defcon_levels() as levels:
            for lv in levels:
                if int(lv.get("lt", -1)) == lt:
                    lv["name"] = name
                    lv["emoji"] = emoji
                    break
            else:
                levels.append({"lt": lt, "name": name, "emoji": emoji})
        await ctx.send(f"Level set: queue < {lt} → {emoji} {name}")
    
    @defcon_group.command(name="remove")
    async def defcon_remove(self, ctx: commands.Context, lt: int):
        lt = int(lt)
        async with self.config.guild(ctx.guild).defcon_levels() as levels:
            new = [lv for lv in levels if int(lv.get("lt", -1)) != lt]
            levels.clear()
            levels.extend(new)
        await ctx.send(f"Removed level with lt={lt}")
    
    @defcon_group.command(name="setoverflow")
    async def defcon_overflow(self, ctx: commands.Context, name: str, emoji: str = "🌀"):
        await self.config.guild(ctx.guild).defcon_overflow_name.set(name)
        await self.config.guild(ctx.guild).defcon_overflow_emoji.set(emoji)
        await ctx.send(f"Overflow level set to {emoji} {name}")
    
    @voo_group.group(name="panic", invoke_without_command=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def panic_group(self, ctx: commands.Context):
        enabled = await self.config.guild(ctx.guild).panic_enabled()
        cd = await self.config.guild(ctx.guild).panic_cooldown_minutes()
        await ctx.send(f"Panic alerts: **{'ON' if enabled else 'OFF'}** • Cooldown: **{cd} min**")
    
    @panic_group.command(name="enable")
    async def panic_enable(self, ctx: commands.Context, enabled: bool):
        await self.config.guild(ctx.guild).panic_enabled.set(bool(enabled))
        await ctx.send(f"Panic alerts {'enabled' if enabled else 'disabled'}.")
    
    @panic_group.command(name="cooldown")
    async def panic_cooldown(self, ctx: commands.Context, minutes: int):
        await self.config.guild(ctx.guild).panic_cooldown_minutes.set(int(max(0, minutes)))
        await ctx.send(f"Panic cooldown set to {minutes} minutes.")
    
    @panic_group.command(name="reset")
    async def panic_reset(self, ctx: commands.Context):
        await self.config.guild(ctx.guild).last_defcon_index.set(-1)
        await self.config.guild(ctx.guild).last_panic_at_ts.set(0)
        await ctx.send("Panic state reset.")


    async def _bump_control_message(self, guild: discord.Guild) -> Optional[discord.Message]:
        """
        Delete and repost the control embed to push it to the bottom.
        Returns the new message or None.
        """
        channel_id = await self.config.guild(guild).channel_id()
        if not channel_id:
            return None
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return None
    
        # delete old
        msg_id = await self.config.guild(guild).control_message_id()
        if msg_id:
            try:
                old = await channel.fetch_message(msg_id)
                await old.delete()
            except Exception:
                pass
    
        qlen = len(self.queue)
        status = await self._get_status_text()
        reward, lvl_name, lvl_emoji, idx, total = await self._current_reward_and_defcon(guild, qlen)
        embed = self._build_control_embed(qlen, status, reward, lvl_name, lvl_emoji, idx, total)
        view = VOOControlView(self)
    
        new_msg = await channel.send(embed=embed, view=view)
        await self.config.guild(guild).control_message_id.set(new_msg.id)
        return new_msg

    async def _notify_listener_error(self, note: str, exc: Optional[BaseException] = None, cooldown_sec: int = 120):
        """
        Post a compact error notice in each configured control channel.
        Cooldown prevents spam (default 2 min per guild).
        """
        # Build a short error snippet
        snippet = ""
        if exc:
            try:
                tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                # keep it short (first ~12 lines or 800 chars)
                lines = tb.splitlines()
                snippet = "\n```py\n" + "\n".join(lines[:12])[:800] + "\n```"
            except Exception:
                # fallback to simple repr
                snippet = f"\n```\n{repr(exc)}\n```"
    
        now = int(time.time())
        for guild in self.bot.guilds:
            try:
                ch_id = await self.config.guild(guild).channel_id()
                if not ch_id:
                    continue
                channel = guild.get_channel(ch_id)
                if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                    continue
    
                # cooldown per guild
                last = self._err_last_notice_ts.get(guild.id, 0)
                if now - last < cooldown_sec:
                    continue
                self._err_last_notice_ts[guild.id] = now
    
                await channel.send(f"⚠️ **VOO listener error** — {note}{snippet}")
            except Exception:
                # don't let error reporting crash anything
                continue

    async def _ensure_recruiter_role(self, member: discord.Member):
        """Give the persistent 'Recruiter' role to anyone who registers."""
        role_id = await self.config.guild(member.guild).recruiter_role_id()
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if role and role not in member.roles:
            try:
                await member.add_roles(role, reason="Registered a recruitment template")
            except Exception:
                log.exception("Failed to add Recruiter role to %s", member)

    
    @voo_group.command(name="setrecruiterrole")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_recruiter_role(self, ctx: commands.Context, role: discord.Role):
        """Set the persistent 'Recruiter' role (pinged on alerts; granted on Register)."""
        await self.config.guild(ctx.guild).recruiter_role_id.set(role.id)
        await ctx.send(f"Recruiter role set to {role.mention}. I’ll grant it on Register and ping it for alerts.")
    
        
            
        
            
    


        






async def setup(bot: Red):
    await bot.add_cog(VOO(bot))
