# vigil_of_origins.py
from __future__ import annotations

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
from urllib.parse import urlencode, quote

log = logging.getLogger("red.vigil_of_origins")

FOUNDING_SSE_URL = "https://www.nationstates.net/api/founding"
GENERATED_BY = "Vigil_of_origins___by_9005____instance_run_by_By_9005"
MAX_TG_BATCH = 8

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

        default_guild = {
            "channel_id": None,
            "control_message_id": None,
            "user_agent": "9003",  # default UA per your preference
            "queue_snapshot": [],  # persisted queue for restarts
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
        # Optionally auto-start; comment out if you prefer manual start
        # await self.start_listener()

    async def cog_unload(self):
        await self.stop_listener()
        if self.session:
            await self.session.close()

    # ---------- SSE Listener ----------
    async def start_listener(self):
        if self.listener_task and not self.listener_task.done():
            return
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None))
        self.listener_task = asyncio.create_task(self._run_listener(), name="VOO_SSE_Listener")

    async def stop_listener(self):
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
        self.listener_task = None

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

                    async for raw_line in resp.content:
                        # Idle watchdog
                        if self.last_event_at and datetime.now(timezone.utc) - self.last_event_at > idle_limit:
                            log.warning("SSE idle > 1 hour; reconnecting.")
                            break

                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            await self._handle_sse_data(payload)
                            self.last_event_at = datetime.now(timezone.utc)
                        # Ignore other SSE fields (event:, id:, etc.)

                # Reconnect loop
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)  # cap backoff

            except asyncio.CancelledError:
                log.info("SSE listener cancelled.")
                raise
            except Exception as e:
                log.exception("SSE listener error: %r", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _handle_sse_data(self, data_line: str):
        """Parse a single SSE data line -> JSON -> extract nation -> push to queue."""
        try:
            obj = json.loads(data_line)
        except json.JSONDecodeError:
            log.debug("Non-JSON data: %s", data_line)
            return

        html = obj.get("htmlStr") or ""
        match = NATION_RE.search(html)
        if not match:
            # Fallback: try from "str" like @@the_parya@@
            s = obj.get("str") or ""
            m2 = re.search(r"@@([a-z0-9_]+)@@", s, re.I)
            nation = m2.group(1) if m2 else None
        else:
            nation = match.group(1)

        if not nation:
            return

        nation = nation.lower()
        # De-dup in-memory and keep newest-first for recruit batches
        if nation in self.queue:
            return
        self.queue.appendleft(nation)
        await self._persist_queue_snapshot()
        await self._maybe_bump_embed_footer()

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
        return "9003"

    # ---------- UI / Embed ----------
    async def _maybe_bump_embed_footer(self):
        # Update the footer showing queue length (lightweight best-effort)
        for guild in self.bot.guilds:
            channel_id = await self.config.guild(guild).channel_id()
            msg_id = await self.config.guild(guild).control_message_id()
            if not (channel_id and msg_id):
                continue
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                continue
            try:
                msg = await channel.fetch_message(msg_id)
                if not msg.embeds:
                    continue
                embed = msg.embeds[0]
                embed = discord.Embed.from_dict(embed.to_dict())  # clone
                qlen = len(self.queue)
                embed.set_footer(text=f"Queue: {qlen} nations")
                await msg.edit(embed=embed, view=VOOControlView(self))
            except Exception:
                pass

    async def post_or_update_control_message(self, guild: discord.Guild, channel: discord.TextChannel | discord.Thread):
        qlen = len(self.queue)
        embed = discord.Embed(
            title="Vigil of Origins — Founding Monitor",
            description=(
                "Watching the NationStates founding stream.\n"
                "Use the buttons below to **Recruit**, **Register** your template, or view the **Leaderboard**."
            ),
            color=discord.Color.blue(),
        )
        embed.add_field(name="What it does", value=(
            "• **Recruit**: Get a private TG link to the **newest** up to 8 queued nations (then removes them from the queue).\n"
            "• **Register**: Save your `%TEMPLATE-...%` once so your Recruit link includes it.\n"
            "• **Leaderboard**: See who has recruited the most nations."
        ), inline=False)
        embed.set_footer(text=f"Queue: {qlen} nations")

        msg_id = await self.config.guild(guild).control_message_id()
        view = VOOControlView(self)

        if msg_id:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed, view=view)
                return
            except Exception:
                pass

        msg = await channel.send(embed=embed, view=view)
        await self.config.guild(guild).control_message_id.set(msg.id)

    # ---------- Button Handlers ----------
    async def handle_register(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TemplateModal(self))

    async def handle_leaderboard(self, interaction: discord.Interaction):
        # Top 10 by sent_count
        all_users = []
        async for uid, data in self.config.all_users().items():
            all_users.append((int(uid), data.get("sent_count", 0)))
        all_users.sort(key=lambda x: x[1], reverse=True)
        lines = []
        for i, (uid, cnt) in enumerate(all_users[:10], start=1):
            member = interaction.guild.get_member(uid) if interaction.guild else None
            name = member.display_name if member else f"User {uid}"
            lines.append(f"**{i}.** {name} — **{cnt}** nations")
        if not lines:
            lines = ["No stats yet. Be the first to recruit!"]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

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

        batch: List[str] = []
        while self.queue and len(batch) < MAX_TG_BATCH:
            batch.append(self.queue.popleft())

        await self._persist_queue_snapshot()
        await self._maybe_bump_embed_footer()

        tgto = ",".join(batch)

        # URL-encode the template correctly so % -> %25
        # Using urllib.parse.quote will yield %25TEMPLATE-...%25 for %TEMPLATE-...%
        message_param = quote(template, safe="")  # encode everything incl. % symbols

        params = {
            "tgto": tgto,
            "message": message_param,
            "generated_by": GENERATED_BY,
        }
        link = f"https://www.nationstates.net/page=compose_telegram?{urlencode(params)}"

        # Count stats (per-nation)
        current = await user_conf.sent_count()
        await user_conf.sent_count.set(current + len(batch))

        await interaction.response.send_message(
            content=(
                f"Here’s your recruitment link for **{len(batch)}** nation(s):\n{link}\n\n"
                f"Targets: `{tgto}`"
            ),
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
        await ctx.send("SSE listener started.")

    @voo_group.command(name="stop")
    async def stop_cmd(self, ctx: commands.Context):
        """Stop the SSE listener."""
        await self.stop_listener()
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
        await self._maybe_bump_embed_footer()
        await ctx.send("Queue cleared.")

    @voo_group.command(name="resetstats")
    async def reset_stats(self, ctx: commands.Context):
        """Reset all users' sent counts."""
        async with self.config.all_users() as allu:
            for uid in list(allu.keys()):
                allu[uid]["sent_count"] = 0
        await ctx.send("Leaderboard stats reset.")

async def setup(bot: Red):
    await bot.add_cog(VOO(bot))
