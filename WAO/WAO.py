import asyncio
import datetime
import logging
from typing import Dict, Any, Optional

import discord
from aiohttp import ClientSession
from redbot.core import commands, Config, checks
from discord.ext import tasks
import xml.etree.ElementTree as ET
import html
import re

log = logging.getLogger("red.wa_proposal_watcher")

WA_BASE_URL = "https://www.nationstates.net/cgi-bin/api.cgi"


class WAProposalWatcher(commands.Cog):
    """
    Watches the NationStates WA proposal queues for both chambers,
    creates a forum thread for each proposal, and locks the thread
    when the proposal disappears from the queue.

    - UA is configurable via command and REQUIRED (no default).
    - Each proposal gets a detailed forum thread with NS link.
    - Optional webhooks fire on new proposals with custom messages & role pings.
    """

    __author__ = "Jeremy + ChatGPT"
    __version__ = "1.2.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210001, force_registration=True
        )

        # Global config: NS User-Agent (required)
        self.config.register_global(ns_user_agent=None)

        # Per-guild config:
        # ga_forum_channel: forum channel ID for GA (wa=1)
        # sc_forum_channel: forum channel ID for SC (wa=2)
        # proposals: {
        #   "1": {proposal_id: {"thread_id": int, "name": str, "category": str}},
        #   "2": {...}
        # }
        # webhooks: {
        #   "name": {"url": str, "role_id": int, "template": str}
        # }
        self.config.register_guild(
            ga_forum_channel=None,
            sc_forum_channel=None,
            proposals={"1": {}, "2": {}},
            webhooks={},
        )

        self.session: Optional[ClientSession] = None
        self.check_proposals_loop.start()

    async def cog_load(self) -> None:
        if self.session is None:
            self.session = ClientSession()

    def cog_unload(self) -> None:
        self.check_proposals_loop.cancel()
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())

    # -------------- CONFIG COMMANDS --------------

    @commands.group(name="waobserver")
    @checks.admin_or_permissions(manage_guild=True)
    async def waobserver_group(self, ctx: commands.Context):
        """Configure and manage the WA proposal watcher."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # --- UA CONFIG ---

    @waobserver_group.command(name="setua")
    async def set_ua(self, ctx: commands.Context, *, user_agent: str):
        """
        Set the NationStates User-Agent string.

        This is REQUIRED before the cog will query the API.
        Example:
        [p]waobserver setua MyNation - WAWatcherBot (Discord: MyUser#1234)
        """
        user_agent = user_agent.strip()
        if not user_agent:
            await ctx.send("User-Agent cannot be empty.")
            return

        await self.config.ns_user_agent.set(user_agent)
        await ctx.send(f"User-Agent set to:\n`{user_agent}`")

    # --- FORUM CHANNELS ---

    @waobserver_group.command(name="setga")
    async def set_ga_forum(
        self, ctx: commands.Context, channel: discord.ForumChannel
    ):
        """Set the forum channel to use for General Assembly (WA=1) proposals."""
        await self.config.guild(ctx.guild).ga_forum_channel.set(channel.id)
        await ctx.send(
            f"General Assembly proposals will now post in forum: {channel.mention}"
        )

    @waobserver_group.command(name="setsc")
    async def set_sc_forum(
        self, ctx: commands.Context, channel: discord.ForumChannel
    ):
        """Set the forum channel to use for Security Council (WA=2) proposals."""
        await self.config.guild(ctx.guild).sc_forum_channel.set(channel.id)
        await ctx.send(
            f"Security Council proposals will now post in forum: {channel.mention}"
        )

    # --- WEBHOOKS ---

    @waobserver_group.command(name="addwebhook")
    async def add_webhook(
        self,
        ctx: commands.Context,
        name: str,
        url: str,
        role: discord.Role,
        *,
        template: str,
    ):
        """
        Add a webhook that fires when a NEW proposal is found.

        Arguments:
        - name: Short identifier for this webhook config (no spaces recommended).
        - url: Webhook URL.
        - role: Role to ping when sending the message.
        - template: Custom message. Supports placeholders:

          {role}        -> role mention
          {chamber}     -> 'General Assembly' or 'Security Council'
          {name}        -> proposal name
          {category}    -> proposal category
          {proposed_by} -> proposer nation
          {link}        -> NationStates proposal link
          {thread}      -> Discord thread link

        Example:
        [p]waobserver addwebhook alerts https://... @WA-Pings \
          {role} New {chamber} proposal: **{name}** by {proposed_by} - {link}
        """
        name = name.strip()
        if not name:
            await ctx.send("Webhook name cannot be empty.")
            return

        template = template.strip()
        if not template:
            await ctx.send("Template cannot be empty.")
            return

        async with self.config.guild(ctx.guild).webhooks() as hooks:
            hooks[name] = {
                "url": url,
                "role_id": role.id,
                "template": template,
            }

        await ctx.send(
            f"Webhook `{name}` added. It will ping {role.mention} on new proposals."
        )

    @waobserver_group.command(name="delwebhook")
    async def delete_webhook(self, ctx: commands.Context, name: str):
        """Delete a configured webhook by name."""
        name = name.strip()
        async with self.config.guild(ctx.guild).webhooks() as hooks:
            if name not in hooks:
                await ctx.send(f"No webhook named `{name}` is configured.")
                return
            hooks.pop(name)

        await ctx.send(f"Webhook `{name}` removed.")

    @waobserver_group.command(name="listwebhooks")
    async def list_webhooks(self, ctx: commands.Context):
        """List configured webhooks for this server."""
        hooks = await self.config.guild(ctx.guild).webhooks()
        if not hooks:
            await ctx.send("No webhooks are configured for this server.")
            return

        lines = ["**Configured WA webhooks:**"]
        for name, data in hooks.items():
            role_id = data.get("role_id")
            role = ctx.guild.get_role(role_id) if role_id else None
            role_str = role.mention if role else f"`{role_id}`"
            template = data.get("template", "")
            if len(template) > 80:
                template = template[:77] + "..."
            lines.append(f"- `{name}` → role: {role_str} | template: `{template}`")

        await ctx.send("\n".join(lines))

    # --- STATUS & FORCE CHECK ---

    @waobserver_group.command(name="status")
    async def status(self, ctx: commands.Context):
        """Show the current WA observer status for this server."""
        data = await self.config.guild(ctx.guild).all()
        ga_id = data.get("ga_forum_channel")
        sc_id = data.get("sc_forum_channel")
        ga = ctx.guild.get_channel(ga_id) if ga_id else None
        sc = ctx.guild.get_channel(sc_id) if sc_id else None

        ua = await self.config.ns_user_agent()
        ua_display = ua if ua else "*Not set (required!)*"

        msg = [
            f"**WA Proposal Watcher Status for {ctx.guild.name}**",
            f"User-Agent: {ua_display}",
            f"GA (WA=1) forum: {ga.mention if ga else 'Not set'}",
            f"SC (WA=2) forum: {sc.mention if sc else 'Not set'}",
        ]
        await ctx.send("\n".join(msg))

    @waobserver_group.command(name="forcecheck")
    async def force_check(self, ctx: commands.Context):
        """Force an immediate check of WA proposals."""
        ua = await self.config.ns_user_agent()
        if not ua:
            await ctx.send(
                "User-Agent is not set yet. Please set it first:\n"
                "`[p]waobserver setua <your NS user-agent>`"
            )
            return

        await ctx.send("Checking WA proposals now...")
        await self._run_full_check()
        await ctx.send("Done checking proposals.")

    # -------------- BACKGROUND LOOP --------------

    @tasks.loop(hours=1)
    async def check_proposals_loop(self):
        """Background loop that runs every hour."""
        try:
            await self._run_full_check()
        except Exception as e:
            log.exception("Error in check_proposals_loop: %s", e)

    @check_proposals_loop.before_loop
    async def before_check_proposals(self):
        await self.bot.wait_until_red_ready()

    async def _run_full_check(self):
        """Check proposals for all guilds that have channels configured."""
        ua = await self.config.ns_user_agent()
        if not ua:
            # UA not set; do nothing.
            log.warning(
                "WAProposalWatcher: ns_user_agent is not set. Skipping checks."
            )
            return

        all_guilds = await self.config.all_guilds()

        for guild_id, data in all_guilds.items():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue

            ga_forum_id = data.get("ga_forum_channel")
            sc_forum_id = data.get("sc_forum_channel")

            if ga_forum_id:
                channel = guild.get_channel(ga_forum_id)
                if isinstance(channel, discord.ForumChannel):
                    await self._check_for_council(guild, channel, council=1, ua=ua)
                else:
                    log.warning(
                        "Guild %s GA forum channel ID %s is not a forum.",
                        guild_id,
                        ga_forum_id,
                    )

            if sc_forum_id:
                channel = guild.get_channel(sc_forum_id)
                if isinstance(channel, discord.ForumChannel):
                    await self._check_for_council(guild, channel, council=2, ua=ua)
                else:
                    log.warning(
                        "Guild %s SC forum channel ID %s is not a forum.",
                        guild_id,
                        sc_forum_id,
                    )

    # -------------- HELPERS: NS TEXT PROCESSING --------------

    def _ns_slug(self, name: str) -> str:
        """Convert a nation/region name to a NS URL slug."""
        return name.strip().replace(" ", "_")

    def _ns_bbcode_to_discord(self, text: str) -> str:
        """Convert common NationStates BBCode to Discord markdown."""
        # Basic formatting tags
        text = re.sub(r"\[b\](.*?)\[/b\]", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"\[i\](.*?)\[/i\]", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"\[u\](.*?)\[/u\]", r"__\1__", text, flags=re.IGNORECASE | re.DOTALL)

        # [nation]Name[/nation]
        def repl_nation_simple(m):
            name = (m.group(1) or "").strip()
            if not name:
                return ""
            slug = self._ns_slug(name)
            return f"[{name}](https://www.nationstates.net/nation={slug})"

        text = re.sub(
            r"\[nation\](.*?)\[/nation\]", repl_nation_simple,
            text, flags=re.IGNORECASE | re.DOTALL
        )

        # [nation=slug]Label[/nation]
        def repl_nation_param(m):
            slug = (m.group(1) or "").strip()
            label = (m.group(2) or "").strip() or slug
            return f"[{label}](https://www.nationstates.net/nation={self._ns_slug(slug)})"

        text = re.sub(
            r"\[nation=(.*?)\](.*?)\[/nation\]", repl_nation_param,
            text, flags=re.IGNORECASE | re.DOTALL
        )

        # [region]Name[/region]
        def repl_region_simple(m):
            name = (m.group(1) or "").strip()
            if not name:
                return ""
            slug = self._ns_slug(name)
            return f"[{name}](https://www.nationstates.net/region={slug})"

        text = re.sub(
            r"\[region\](.*?)\[/region\]", repl_region_simple,
            text, flags=re.IGNORECASE | re.DOTALL
        )

        # [region=slug]Label[/region]
        def repl_region_param(m):
            slug = (m.group(1) or "").strip()
            label = (m.group(2) or "").strip() or slug
            return f"[{label}](https://www.nationstates.net/region={self._ns_slug(slug)})"

        text = re.sub(
            r"\[region=(.*?)\](.*?)\[/region\]", repl_region_param,
            text, flags=re.IGNORECASE | re.DOTALL
        )

        # [url=link]text[/url]
        text = re.sub(
            r"\[url=(.*?)\](.*?)\[/url\]", r"[\2](\1)",
            text, flags=re.IGNORECASE | re.DOTALL
        )
        # [url]link[/url]
        text = re.sub(
            r"\[url\](.*?)\[/url\]", r"<\1>",
            text, flags=re.IGNORECASE | re.DOTALL
        )

        # Lists: [list], [*], [/list]
        text = re.sub(r"\[list\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[/list\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[\*\]", "• ", text)

        # [quote]...[/quote]
        def repl_quote(m):
            inner = (m.group(1) or "").strip()
            if not inner:
                return ""
            lines = inner.splitlines()
            lines = ["> " + ln for ln in lines]
            return "\n".join(lines)

        text = re.sub(
            r"\[quote\](.*?)\[/quote\]", repl_quote,
            text, flags=re.IGNORECASE | re.DOTALL
        )

        return text

    def _process_description(self, raw: str) -> str:
        """
        Decode HTML entities, convert NS BBCode to Discord markdown,
        and truncate safely for embed description.
        """
        if not raw:
            return "No description provided."

        # Decode HTML entities like &#147; etc.
        text = html.unescape(raw)

        # Convert NS BBCode to Discord formatting
        text = self._ns_bbcode_to_discord(text)

        # Embed description limit is 4096 chars.
        limit = 4096
        notice = "\n\n*(Description truncated; see proposal gameside for full text.)*"

        if len(text) > limit:
            cutoff = limit - len(notice)
            if cutoff < 0:
                cutoff = 0
            text = text[:cutoff] + notice

        return text

    # -------------- CORE LOGIC --------------

    async def _check_for_council(
        self,
        guild: discord.Guild,
        forum: discord.ForumChannel,
        council: int,
        ua: str,
    ):
        """
        Check proposals for a given council (1 = GA, 2 = SC) and sync threads.

        - New proposals -> create new thread + fire webhooks.
        - Proposals no longer present -> lock + archive thread.
        """
        proposals = await self._fetch_proposals(council, ua)
        current_ids = set(proposals.keys())

        guild_conf = self.config.guild(guild)
        all_data = await guild_conf.all()
        stored_by_council: Dict[str, Dict[str, Any]] = all_data["proposals"].get(
            str(council), {}
        )
        stored_ids = set(stored_by_council.keys())

        new_ids = current_ids - stored_ids
        gone_ids = stored_ids - current_ids

        # Handle new proposals
        for pid in new_ids:
            info = proposals[pid]
            try:
                thread = await self._create_thread_for_proposal(
                    forum=forum, council=council, proposal_id=pid, info=info
                )
                # Fire webhooks for this new proposal
                await self._notify_webhooks_for_new_proposal(
                    guild=guild,
                    thread=thread,
                    council=council,
                    proposal_id=pid,
                    info=info,
                )
            except Exception as e:
                log.exception(
                    "Failed to create thread or send webhooks for proposal %s in guild %s: %s",
                    pid,
                    guild.id,
                    e,
                )
                continue

            stored_by_council[pid] = {
                "thread_id": thread.id,
                "name": info.get("name"),
                "category": info.get("category"),
                "created": info.get("created"),
            }

        # Handle disappeared proposals -> lock threads
        for pid in gone_ids:
            entry = stored_by_council.get(pid)
            if not entry:
                continue
            thread_id = entry.get("thread_id")
            if not thread_id:
                continue

            thread = guild.get_thread(thread_id)
            if thread is None:
                # maybe deleted manually
                continue

            try:
                if not thread.locked or not thread.archived:
                    await thread.edit(locked=True, archived=True)
                    await thread.send(
                        "This proposal is no longer in the WA queue. Locking this thread."
                    )
            except Exception as e:
                log.exception(
                    "Failed to lock/archive thread %s for proposal %s: %s",
                    thread_id,
                    pid,
                    e,
                )

            # Remove from stored proposals
            stored_by_council.pop(pid, None)

        # Save updated mapping
        all_data["proposals"][str(council)] = stored_by_council
        await guild_conf.proposals.set(all_data["proposals"])

    async def _create_thread_for_proposal(
        self,
        forum: discord.ForumChannel,
        council: int,
        proposal_id: str,
        info: Dict[str, Any],
    ) -> discord.Thread:
        """Create a new forum thread for a proposal with rich info and NS link."""
        chamber_name = "General Assembly" if council == 1 else "Security Council"
        category = info.get("category") or "Unknown Category"
        name = info.get("name") or proposal_id
        raw_desc = info.get("desc") or "No description provided."
        desc = self._process_description(raw_desc)

        proposed_by = info.get("proposed_by") or "Unknown"
        created_ts = info.get("created") or 0
        coauthors = info.get("coauthors") or []
        option = info.get("option") or ""
        approvals = info.get("approvals_raw") or ""

        # Format timestamps and other fields
        try:
            created_dt = datetime.datetime.utcfromtimestamp(created_ts)
            created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            created_str = f"{created_ts} (raw)"

        approvals_list = [a for a in approvals.split(":") if a]
        approvals_count = len(approvals_list)

        # Proposed by: link to nation if we can
        if proposed_by != "Unknown":
            pb_slug = self._ns_slug(proposed_by)
            proposed_by_value = (
                f"[{proposed_by}](https://www.nationstates.net/nation={pb_slug})"
            )
        else:
            proposed_by_value = proposed_by

        # Coauthors: each linked to their nation page
        if coauthors:
            coauthor_links = []
            for c in coauthors:
                c = c.strip()
                if not c:
                    continue
                slug = self._ns_slug(c)
                coauthor_links.append(
                    f"[{c}](https://www.nationstates.net/nation={slug})"
                )
            coauthor_str = ", ".join(coauthor_links) if coauthor_links else "None"
        else:
            coauthor_str = "None"

        # Option / Target, try to make it useful
        option_str = option if option else "N/A"
        # e.g. N:nation or R:region
        if option.upper().startswith("N:"):
            target = option[2:]
            slug = self._ns_slug(target)
            option_str = (
                f"Nation: [{target}](https://www.nationstates.net/nation={slug})"
            )
        elif option.upper().startswith("R:"):
            target = option[2:]
            slug = self._ns_slug(target)
            option_str = (
                f"Region: [{target}](https://www.nationstates.net/region={slug})"
            )

        proposal_url = f"https://www.nationstates.net/page=UN_view_proposal/id={proposal_id}"

        # Prepare embed
        embed = discord.Embed(
            title=name,
            url=proposal_url,
            description=desc,
        )
        embed.add_field(name="Chamber", value=chamber_name, inline=True)
        embed.add_field(name="Category", value=category, inline=True)
        embed.add_field(name="Proposed by", value=proposed_by_value, inline=True)
        embed.add_field(name="Co-authors", value=coauthor_str, inline=False)
        embed.add_field(name="Option / Target", value=option_str, inline=False)
        embed.add_field(name="Created", value=created_str, inline=True)
        embed.add_field(
            name="Approvals",
            value=f"{approvals_count} approvals",
            inline=True,
        )
        embed.add_field(
            name="Proposal ID",
            value=f"`{proposal_id}`",
            inline=False,
        )
        embed.add_field(
            name="NationStates Link",
            value=f"[View proposal on NationStates]({proposal_url})",
            inline=False,
        )

        title = f"[{chamber_name}] {name}"

        thread = await forum.create_thread(
            name=title,
            embed=embed,
        )
        return thread

    # -------------- WEBHOOK NOTIFICATIONS --------------

    async def _notify_webhooks_for_new_proposal(
        self,
        guild: discord.Guild,
        thread: discord.Thread,
        council: int,
        proposal_id: str,
        info: Dict[str, Any],
    ):
        """Send webhook notifications for a newly discovered proposal."""
        hooks = await self.config.guild(guild).webhooks()
        if not hooks:
            return

        chamber_name = "General Assembly" if council == 1 else "Security Council"
        name = info.get("name") or proposal_id
        category = info.get("category") or "Unknown Category"
        proposed_by = info.get("proposed_by") or "Unknown"
        proposal_url = f"https://www.nationstates.net/page=UN_view_proposal/id={proposal_id}"
        thread_url = thread.jump_url

        if self.session is None or self.session.closed:
            self.session = ClientSession()

        for hook_name, data in hooks.items():
            url = data.get("url")
            role_id = data.get("role_id")
            template = data.get("template") or (
                "{role} New {chamber} proposal: {name} ({category}) by "
                "{proposed_by} - {link}"
            )

            if not url:
                continue

            role_mention = f"<@&{role_id}>" if role_id else ""

            try:
                content = template.format(
                    role=role_mention,
                    chamber=chamber_name,
                    name=name,
                    category=category,
                    proposed_by=proposed_by,
                    link=proposal_url,
                    thread=thread_url,
                )
            except Exception as e:
                log.exception(
                    "Error formatting webhook template '%s' in guild %s: %s",
                    hook_name,
                    guild.id,
                    e,
                )
                continue

            try:
                webhook = discord.Webhook.from_url(url, session=self.session)
                await webhook.send(
                    content,
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )
            except Exception as e:
                log.exception(
                    "Failed to send webhook '%s' in guild %s: %s",
                    hook_name,
                    guild.id,
                    e,
                )

    # -------------- API FETCHING & PARSING --------------

    async def _fetch_proposals(
        self, council: int, user_agent: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch proposals for a WA council from NationStates API.

        Returns:
            dict mapping proposal_id -> info dict
        """
        if self.session is None or self.session.closed:
            self.session = ClientSession()

        params = {
            "wa": str(council),
            "q": "proposals",
        }
        headers = {"User-Agent": user_agent}

        async with self.session.get(
            WA_BASE_URL, params=params, headers=headers
        ) as resp:
            text = await resp.text()

            # Handle rate limiting according to your strategy
            await self._handle_rate_limit(resp)

            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                log.exception("Failed to parse WA XML for council %s", council)
                return {}

        proposals_elem = root.find("PROPOSALS")
        if proposals_elem is None:
            return {}

        proposals: Dict[str, Dict[str, Any]] = {}
        for prop in proposals_elem.findall("PROPOSAL"):
            # Prefer <ID> field to be safe
            pid = (prop.findtext("ID") or "").strip()
            if not pid:
                # fallback to attribute id
                pid = prop.get("id", "").strip()
            if not pid:
                continue

            category = (prop.findtext("CATEGORY") or "").strip()
            created_raw = (prop.findtext("CREATED") or "0").strip()
            try:
                created = int(created_raw)
            except ValueError:
                created = 0

            desc = prop.findtext("DESC") or ""
            name = (prop.findtext("NAME") or "").strip()
            proposed_by = (prop.findtext("PROPOSED_BY") or "").strip()
            approvals_raw = (prop.findtext("APPROVALS") or "").strip()

            # Co-authors (could be multiple COAUTHOR tags)
            coauthors = [
                (c.text or "").strip() for c in prop.findall("COAUTHOR")
            ]
            coauthors = [c for c in coauthors if c]

            # Option / Target (e.g., N:some_nation)
            option = (prop.findtext("OPTION") or "").strip()

            info = {
                "id": pid,
                "category": category,
                "created": created,
                "desc": desc,
                "name": name,
                "proposed_by": proposed_by,
                "approvals_raw": approvals_raw,
                "coauthors": coauthors,
                "option": option,
            }
            proposals[pid] = info

        return proposals

    async def _handle_rate_limit(self, resp):
        """
        Handle NationStates API rate limiting based on response headers.

        Pattern based on your existing approach:
        remaining = int(Ratelimit-Remaining) - 10
        wait_time = reset_time / remaining if remaining > 0 else reset_time
        """
        headers = resp.headers
        try:
            remaining_raw = headers.get("Ratelimit-Remaining")
            reset_raw = headers.get("Ratelimit-Reset")

            if remaining_raw is None or reset_raw is None:
                return

            remaining = int(remaining_raw)
            reset_time = int(reset_raw)

            # match your snippet's behavior
            remaining -= 10
            if remaining > 0:
                wait_time = reset_time / remaining
            else:
                wait_time = reset_time

            # don't sleep for huge nonsense values
            if 0 < wait_time < 60:
                await asyncio.sleep(wait_time)
        except Exception:
            # if anything is weird, just ignore; our load is tiny anyway
            return


async def setup(bot):
    await bot.add_cog(WAProposalWatcher(bot))
