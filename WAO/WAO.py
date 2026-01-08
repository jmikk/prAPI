import asyncio
import datetime
import logging
from typing import Dict, Any, Optional, Tuple

import discord
from aiohttp import ClientSession
from redbot.core import commands, Config, checks
from discord.ext import tasks
import xml.etree.ElementTree as ET
import html
import re

log = logging.getLogger("red.wa_proposal_watcher")

WA_BASE_URL = "https://www.nationstates.net/cgi-bin/api.cgi"


class WAO(commands.Cog):
    """
    Watches the NationStates WA proposal queues for both chambers,
    creates a forum thread for each proposal, and locks the thread
    when the proposal disappears from the queue.

    Extras:
    - UA is configurable via command and REQUIRED (no default).
    - Each proposal gets a detailed forum thread with NS link.
    - Optional webhooks fire on new proposals with custom messages & role pings.
    - Each proposal ID will only ever create ONE thread per guild; we track
      active/inactive state instead of deleting the record.
    - In proposal threads, messages starting with For/Against/Abstain become
      votes with emoji + live tallies (counts and percentages).
    - Optional voter role: if set, only that role can vote; otherwise anyone can.
    - Dump command to lock/delete all tracked threads and clear memory.
    - IFV system:
        * 2nd post in each thread reserved for an IFV.
        * `waobserver ifv <thread_id> <text>` updates that reserved post.
        * `setifvroles` defines which roles can write IFVs.
    """

    __author__ = "9005"
    __version__ = "1.6.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210001, force_registration=True
        )

        # Global config: NS User-Agent (required)
        self.config.register_global(ns_user_agent=None)

        self.config.register_guild(
            ga_forum_channel=None,
            sc_forum_channel=None,
            proposals={"1": {}, "2": {}},
            webhooks={},
            votes={},
            voter_role_id=None,
            ifv_role_ids=[],
            current_resolution_ids={"1": None, "2": None},
            resolution_messages={"1": "", "2": ""},
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

    async def _update_starter_embed_link_for_vote(
        self,
        guild: discord.Guild,
        entry: Dict[str, Any],
        council: int,
    ):
        """When a proposal reaches vote, update its starter embed links to GA/SC page."""
        thread_id = entry.get("thread_id")
        starter_message_id = entry.get("starter_message_id")
    
        if not thread_id or not starter_message_id:
            return
    
        thread = guild.get_thread(thread_id) or guild.get_channel(thread_id)
        if not isinstance(thread, discord.Thread):
            return
    
        try:
            starter_msg = await thread.fetch_message(starter_message_id)
        except discord.NotFound:
            return
        except Exception as e:
            log.debug("Failed to fetch starter message %s in thread %s: %s", starter_message_id, thread_id, e)
            return
    
        if not starter_msg.embeds:
            return
    
        vote_url = "https://www.nationstates.net/page=ga" if council == 1 else "https://www.nationstates.net/page=sc"
    
        base = starter_msg.embeds[0]
        embed = base.copy()
    
        # Update the clickable title link
        embed.url = vote_url
    
        # Update the "NationStates Link" field if present
        existing_fields = list(embed.fields)
        embed.clear_fields()
    
        for f in existing_fields:
            if f.name == "NationStates Link":
                embed.add_field(
                    name=f.name,
                    value=f"[View chamber page on NationStates]({vote_url})",
                    inline=f.inline,
                )
            else:
                embed.add_field(name=f.name, value=f.value, inline=f.inline)
    
        try:
            await starter_msg.edit(embed=embed)
        except Exception as e:
            log.debug("Failed to edit starter embed in thread %s: %s", thread_id, e)


    async def _check_resolution_for_council(
        self,
        guild: discord.Guild,
        council: int,
        ua: str,
    ):
        """
        Check current resolution for the given council (1 = GA, 2 = SC).

        If the resolution's ID matches a known proposal:
          - Pin that proposal's thread.
          - Optionally send a 'goes to vote' message (once per resolution).
        When the resolution changes or disappears:
          - Unpin the previous thread (if known).
        """
        guild_conf = self.config.guild(guild)
        data = await guild_conf.all()

        # Make sure our new keys exist
        current_resolution_ids = data.get("current_resolution_ids") or {"1": None, "2": None}
        resolution_messages = data.get("resolution_messages") or {"1": "", "2": ""}
        proposals_by_council: Dict[str, Dict[str, Any]] = data["proposals"].get(str(council), {})

        old_id = current_resolution_ids.get(str(council))
        res = await self._fetch_resolution(council, ua)
        new_id = res["id"] if res else None

        # If nothing changed, do nothing
        if new_id == old_id:
            return

        chamber_name = "General Assembly" if council == 1 else "Security Council"

        # 1) Unpin old resolution thread, if any
        if old_id and old_id in proposals_by_council:
            old_entry = proposals_by_council[old_id]
            thread_id = old_entry.get("thread_id")
            if thread_id:
                thread = guild.get_thread(thread_id) or guild.get_channel(thread_id)
                if isinstance(thread, discord.Thread):
                    try:
                        await thread.edit(pinned=False)
                    except Exception as e:
                        log.debug(
                            "Failed to unpin old resolution thread %s in guild %s: %s",
                            thread_id,
                            guild.id,
                            e,
                        )
            # You could also flip a flag on the entry if you want
            old_entry["at_vote"] = False

        # 2) If there is a new resolution, pin its thread and send message
        if new_id:
            # Determine the correct forum channel for this council
            forum_id = data.get("ga_forum_channel") if council == 1 else data.get("sc_forum_channel")
            forum = guild.get_channel(forum_id) if forum_id else None
            if not isinstance(forum, discord.ForumChannel):
                log.warning(
                    "Guild %s: cannot pin/create resolution thread for council %s because forum channel is not valid.",
                    guild.id, council
                )
            else:
                entry = proposals_by_council.get(new_id)

                # Try to resolve an existing thread from stored entry
                thread: Optional[discord.Thread] = None
                if entry:
                    thread_id = entry.get("thread_id")
                    if thread_id:
                        maybe_thread = guild.get_thread(thread_id) or guild.get_channel(thread_id)
                        if isinstance(maybe_thread, discord.Thread):
                            thread = maybe_thread

                # If no thread exists (not tracked or deleted), create it now
                if thread is None:
                    thread, starter_message_id, ifv_message_id = await self._create_thread_for_resolution(
                        forum=forum,
                        council=council,
                        res=res,  # res is the resolution dict you already fetched
                    )

                    proposals_by_council[new_id] = {
                        "thread_id": thread.id,
                        "starter_message_id": starter_message_id,
                        "ifv_message_id": ifv_message_id,
                        "name": res.get("name") if res else new_id,
                        "category": res.get("category") if res else "Unknown Category",
                        "proposed_by": res.get("proposed_by") if res else "Unknown",
                        "created": 0,
                        "active": True,
                        "at_vote": True,
                    }
                    entry = proposals_by_council[new_id]

                # Pin the thread
                try:
                    await thread.edit(pinned=True)
                except Exception as e:
                    log.debug(
                        "Failed to pin resolution thread %s in guild %s: %s",
                        thread.id,
                        guild.id,
                        e,
                    )

                # Mark state + update embed link
                entry["at_vote"] = True
                entry["active"] = True
                await self._update_starter_embed_link_for_vote(guild=guild, entry=entry, council=council)

                # Optional "goes to vote" message
                template = resolution_messages.get(str(council), "") or ""
                if template:
                    proposal_url = f"https://www.nationstates.net/page=UN_view_proposal/id={new_id}"
                    thread_url = f"https://discord.com/channels/{guild.id}/{thread.id}"
                    name = entry.get("name") or new_id
                    category = entry.get("category") or "Unknown Category"
                    proposed_by = entry.get("proposed_by") or "Unknown"

                    try:
                        content = template.format(
                            chamber=chamber_name,
                            name=name,
                            category=category,
                            proposed_by=proposed_by,
                            link=proposal_url,
                            thread=thread_url,
                        )
                        await thread.send(content)
                    except Exception as e:
                        log.debug("Failed to send resolution message in thread %s: %s", thread.id, e)


        # 3) Persist current resolution ID + proposals updates
        current_resolution_ids[str(council)] = new_id
        data["current_resolution_ids"] = current_resolution_ids
        data["proposals"][str(council)] = proposals_by_council

        await guild_conf.current_resolution_ids.set(current_resolution_ids)
        await guild_conf.proposals.set(data["proposals"])


    async def _fetch_resolution(
        self, council: int, user_agent: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch CURRENT resolution for a WA council from the NationStates API.

        Returns:
            dict with keys: id, name, category, proposed_by
            or None if no active resolution / parse failure.
        """
        if self.session is None or self.session.closed:
            self.session = ClientSession()

        params = {"wa": str(council), "q": "resolution"}
        headers = {"User-Agent": user_agent}

        async with self.session.get(
            WA_BASE_URL, params=params, headers=headers
        ) as resp:
            text = await resp.text()
            await self._handle_rate_limit(resp)

            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                log.exception("Failed to parse WA resolution XML for council %s", council)
                return None

        res_elem = root.find("RESOLUTION")
        if res_elem is None:
            return None

        pid = (res_elem.findtext("ID") or "").strip()
        if not pid:
            return None

        name = (res_elem.findtext("NAME") or "").strip()
        category = (res_elem.findtext("CATEGORY") or "").strip()
        proposed_by = (res_elem.findtext("PROPOSED_BY") or "").strip()
        desc = res_elem.findtext("DESC") or ""

        return {
            "id": pid,
            "name": name,
            "category": category,
            "proposed_by": proposed_by,
            "desc": desc,
        }


    # -------------- CONFIG COMMANDS --------------

    @commands.group(name="waobserver")
    @checks.admin_or_permissions(manage_guild=True)
    async def waobserver_group(self, ctx: commands.Context):
        """Configure and manage the WA proposal watcher."""
        pass

        # --- WEBHOOKS ---

    @waobserver_group.command(name="addwebhook")
    async def add_webhook(
        self,
        ctx: commands.Context,
        name: str,
        url: str,
        role: int,
        *,
        template: str,
    ):
        """
        Add a webhook that fires when a NEW proposal is found.

        Arguments:
        - name: Short identifier for this webhook config (no spaces recommended).
        - url: Webhook URL.
        - role: Role ID to ping when sending the message (use the ID of the role
                in the server where the webhook lives).
        - template: Custom message. Supports placeholders:

          {role}        -> role mention (<@&id>)
          {chamber}     -> 'General Assembly' or 'Security Council'
          {name}        -> proposal name
          {category}    -> proposal category
          {proposed_by} -> proposer nation
          {link}        -> NationStates proposal link
          {thread}      -> Discord thread URL
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
                "role_id": int(role),
                "template": template,
            }

        await ctx.send(
            f"Webhook `{name}` added. It will ping role ID `{role}` on new proposals."
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
            template = data.get("template", "")
            if len(template) > 80:
                template = template[:77] + "..."
            lines.append(
                f"- `{name}` → role ID: `{role_id}` | template: `{template}`"
            )

        await ctx.send("\n".join(lines))


    

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

    # --- VOTER ROLE ---

    @waobserver_group.command(name="setvoterrole")
    async def set_voter_role(self, ctx: commands.Context, role: discord.Role):
        """
        Set a voter role for WA proposal threads.

        If set, only members with this role may cast votes in proposal threads.
        If no voter role is set, anyone can vote.
        """
        await self.config.guild(ctx.guild).voter_role_id.set(role.id)
        await ctx.send(
            f"Voter role set to {role.mention}. Only members with this role may vote."
        )

    @waobserver_group.command(name="clearvoterrole")
    async def clear_voter_role(self, ctx: commands.Context):
        """Clear the voter role so that anyone can vote in proposal threads."""
        await self.config.guild(ctx.guild).voter_role_id.clear()
        await ctx.send(
            "Voter role cleared. Anyone can now vote in proposal threads."
        )

    # --- IFV ROLES ---

    @waobserver_group.command(name="setifvroles")
    async def set_ifv_roles(
        self, ctx: commands.Context, *roles: discord.Role
    ):
        """
        Set which roles are allowed to write IFVs.

        If at least one IFV role is set:
          - Only those roles (or admins/managers) may use [p]waobserver ifv.
        If none are set:
          - Only admins/managers may use [p]waobserver ifv.

        Example:
        [p]waobserver setifvroles @WA-Staff @Delegate
        """
        ids = [r.id for r in roles]
        await self.config.guild(ctx.guild).ifv_role_ids.set(ids)
        if ids:
            mentions = ", ".join(r.mention for r in roles)
            await ctx.send(
                f"IFV roles set to: {mentions}. Only these roles (plus admins) can write IFVs."
            )
        else:
            await ctx.send(
                "IFV roles set to empty. Only admins/managers may write IFVs."
            )

    @waobserver_group.command(name="clearifvroles")
    async def clear_ifv_roles(self, ctx: commands.Context):
        """Clear IFV roles. Only admins/managers may write IFVs."""
        await self.config.guild(ctx.guild).ifv_role_ids.set([])
        await ctx.send(
            "IFV roles cleared. Only admins/managers may write IFVs."
        )

    # --- IFV COMMAND ---

    @waobserver_group.command(name="ifv")
    async def set_ifv(
        self, ctx: commands.Context, thread_id: int, *, text: str
    ):
        """
        Set the IFV (In-Forum Vote) text for a proposal thread.

        Usage:
            [p]waobserver ifv <thread_id> <text>

        The IFV will be placed (or updated) in the reserved second post
        of that proposal thread.
        """
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        # Permission check: IFV roles OR admin/manage_guild
        conf = self.config.guild(guild)
        ifv_role_ids = await conf.ifv_role_ids()
        allowed = False

        if any(
            r.id in ifv_role_ids for r in ctx.author.roles
        ) and ifv_role_ids:
            allowed = True
        elif ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild:
            allowed = True

        if not allowed:
            if ifv_role_ids:
                await ctx.send(
                    "You do not have a role that is allowed to write IFVs."
                )
            else:
                await ctx.send(
                    "Only administrators or members with Manage Server may write IFVs."
                )
            return

        # Fetch thread
        thread = guild.get_thread(thread_id) or guild.get_channel(thread_id)
        if not isinstance(thread, discord.Thread):
            await ctx.send("That ID is not a valid thread.")
            return

        # Is it a tracked proposal thread?
        proposals = await conf.proposals()
        target_entry = None
        for council_data in proposals.values():
            for entry in council_data.values():
                if entry.get("thread_id") == thread_id:
                    target_entry = entry
                    break
            if target_entry:
                break

        if not target_entry:
            await ctx.send("That thread is not tracked as a WA proposal thread.")
            return

        ifv_message_id = target_entry.get("ifv_message_id")
        msg: Optional[discord.Message] = None

        if ifv_message_id:
            try:
                msg = await thread.fetch_message(ifv_message_id)
            except discord.NotFound:
                msg = None

        if msg is None:
            # Create a new IFV message if somehow missing
            msg = await thread.send("IFV will be posted here.")
            target_entry["ifv_message_id"] = msg.id
            await conf.proposals.set(proposals)

        await msg.edit(content=text)
        await ctx.send(f"IFV updated for thread {thread.mention}.")

    @waobserver_group.command(name="setresmsg")
    async def set_resolution_message(
        self, ctx: commands.Context, chamber: str, *, template: str
    ):
        """
        Set the message posted in a proposal thread when it goes to vote.

        chamber: ga, sc, 1, 2, or both
        template placeholders:
          {chamber}     -> 'General Assembly' or 'Security Council'
          {name}        -> proposal name
          {category}    -> category
          {proposed_by} -> proposer
          {link}        -> NationStates proposal link
          {thread}      -> Discord thread URL
        """
        chamber = chamber.lower()
        if chamber in ("ga", "1"):
            keys = ["1"]
        elif chamber in ("sc", "2"):
            keys = ["2"]
        elif chamber == "both":
            keys = ["1", "2"]
        else:
            await ctx.send("Chamber must be one of: ga, sc, 1, 2, both.")
            return

        async with self.config.guild(ctx.guild).resolution_messages() as res_msgs:
            for k in keys:
                res_msgs[k] = template

        nice = ", ".join(
            "General Assembly" if k == "1" else "Security Council" for k in keys
        )
        await ctx.send(f"Resolution message set for: {nice}.")

    @waobserver_group.command(name="clearresmsg")
    async def clear_resolution_message(
        self, ctx: commands.Context, chamber: str
    ):
        """
        Clear the 'goes to vote' message template.

        chamber: ga, sc, 1, 2, or both
        """
        chamber = chamber.lower()
        if chamber in ("ga", "1"):
            keys = ["1"]
        elif chamber in ("sc", "2"):
            keys = ["2"]
        elif chamber == "both":
            keys = ["1", "2"]
        else:
            await ctx.send("Chamber must be one of: ga, sc, 1, 2, both.")
            return

        async with self.config.guild(ctx.guild).resolution_messages() as res_msgs:
            for k in keys:
                res_msgs[k] = ""

        nice = ", ".join(
            "General Assembly" if k == "1" else "Security Council" for k in keys
        )
        await ctx.send(f"Resolution message cleared for: {nice}.")


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

        voter_role_id = data.get("voter_role_id")
        voter_role = ctx.guild.get_role(voter_role_id) if voter_role_id else None
        if voter_role:
            voter_role_str = f"{voter_role.mention}"
        elif voter_role_id:
            voter_role_str = f"`{voter_role_id}` (not found)"
        else:
            voter_role_str = "None (anyone can vote)"

        ifv_ids = data.get("ifv_role_ids", [])
        ifv_roles = [
            ctx.guild.get_role(rid) for rid in ifv_ids if ctx.guild.get_role(rid)
        ]
        if ifv_roles:
            ifv_str = ", ".join(r.mention for r in ifv_roles)
        elif ifv_ids:
            ifv_str = ", ".join(f"`{rid}`" for rid in ifv_ids)
        else:
            ifv_str = "None (only admins/managers)"

        msg = [
            f"**WA Proposal Watcher Status for {ctx.guild.name}**",
            f"User-Agent: {ua_display}",
            f"GA (WA=1) forum: {ga.mention if ga else 'Not set'}",
            f"SC (WA=2) forum: {sc.mention if sc else 'Not set'}",
            f"Voter role: {voter_role_str}",
            f"IFV roles: {ifv_str}",
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

    # --- DUMP / RESET ---

    @waobserver_group.command(name="dump")
    async def dump_data(self, ctx: commands.Context, lock: bool = True):
        """
        Dump all WAO tracking data for this server.

        If lock is True (default):
          - Lock + archive all threads tracked by this cog.
          - Clear stored proposals and votes.
        If lock is False:
          - Delete all threads tracked by this cog.
          - Clear stored proposals and votes.

        GA/SC forum channel settings and webhooks are NOT touched.
        """
        guild = ctx.guild
        data = await self.config.guild(guild).all()
        proposals = data.get("proposals", {"1": {}, "2": {}})

        action_word = "Locking and archiving" if lock else "Deleting"
        await ctx.send(
            f"{action_word} all tracked proposal threads and clearing WAO memory for this server..."
        )

        for council_key, council_data in proposals.items():
            for pid, entry in list(council_data.items()):
                thread_id = entry.get("thread_id")
                if not thread_id:
                    continue

                thread = guild.get_thread(thread_id) or guild.get_channel(thread_id)
                if not isinstance(thread, discord.Thread):
                    continue

                try:
                    if lock:
                        await thread.edit(locked=True, archived=True)
                    else:
                        await thread.delete(reason="WAO dump command")
                except Exception as e:
                    log.exception(
                        "Failed to %s thread %s for proposal %s in guild %s: %s",
                        "lock/archive" if lock else "delete",
                        thread_id,
                        pid,
                        guild.id,
                        e,
                    )

        # Clear memory: proposals + votes; keep forum/webhook settings
        await self.config.guild(guild).proposals.set({"1": {}, "2": {}})
        await self.config.guild(guild).votes.clear()

        await ctx.send("Done. WAO tracking data has been reset for this server.")

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
            log.warning("WAO: ns_user_agent is not set. Skipping checks.")
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
                    await self._check_resolution_for_council(guild, council=1, ua=ua)
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
                    await self._check_resolution_for_council(guild, council=2, ua=ua)
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

        text = html.unescape(raw)
        text = self._ns_bbcode_to_discord(text)

        limit = 4096
        notice = "\n\n*(Description truncated; see proposal gameside for full text.)*"

        if len(text) > limit:
            cutoff = limit - len(notice)
            if cutoff < 0:
                cutoff = 0
            text = text[:cutoff] + notice

        return text

    # -------------- CORE LOGIC: PROPOSALS --------------

    async def _check_for_council(
        self,
        guild: discord.Guild,
        forum: discord.ForumChannel,
        council: int,
        ua: str,
    ):
        """
        Check proposals for a given council (1 = GA, 2 = SC) and sync threads.

        - New proposals (never seen before) -> create new thread + fire webhooks.
        - Proposals no longer present (were active) -> lock + archive thread and
          mark as inactive, but keep the record so we never create a second thread
          for the same proposal ID.
        """
        proposals = await self._fetch_proposals(council, ua)
        current_ids = set(proposals.keys())

        guild_conf = self.config.guild(guild)
        all_data = await guild_conf.all()
        stored_by_council: Dict[str, Dict[str, Any]] = all_data["proposals"].get(
            str(council), {}
        )

        stored_ids_all = set(stored_by_council.keys())
        active_ids = {
            pid
            for pid, entry in stored_by_council.items()
            if entry.get("active", True)
        }

        new_ids = current_ids - stored_ids_all
        gone_ids = active_ids - current_ids
        current_resolution = await self._fetch_resolution(council, ua)
        current_resolution_id = current_resolution["id"] if current_resolution else None


        # Handle new proposals
        for pid in new_ids:
            info = proposals[pid]
            try:
                thread, starter_message_id, ifv_message_id = await self._create_thread_for_proposal(
                    forum=forum, council=council, proposal_id=pid, info=info
                )
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
                "starter_message_id": starter_message_id,
                "ifv_message_id": ifv_message_id,
                "name": info.get("name"),
                "category": info.get("category"),
                "created": info.get("created"),
                "active": True,
                "proposed_by": info.get("proposed_by"),
            }

        # Handle disappeared proposals -> lock threads & mark inactive
        for pid in gone_ids:
            if current_resolution_id and pid == current_resolution_id:
                entry = stored_by_council.get(pid)
                if entry:
                    entry["active"] = True        # still considered active
                    entry["at_vote"] = True       # optional: keep state consistent
                continue
                
            entry = stored_by_council.get(pid)
            if not entry:
                continue
            thread_id= entry.get("thread_id")
            if not thread_id:
                entry["active"] = False
                continue

            thread = guild.get_thread(thread_id)
            if thread is None:
                entry["active"] = False
                continue

            try:
                if not thread.locked or not thread.archived:
                    await thread.send(
                        "This proposal is no longer in the WA queue. Locking this thread."
                    )
                    await thread.edit(locked=True)
                    await thread.edit(archived=True)
            except Exception as e:
                log.exception(
                    "Failed to lock/archive thread %s for proposal %s: %s",
                    thread_id,
                    pid,
                    e,
                )

            entry["active"] = False

        all_data["proposals"][str(council)] = stored_by_council
        await guild_conf.proposals.set(all_data["proposals"])

    async def _create_thread_for_resolution(
        self,
        forum: discord.ForumChannel,
        council: int,
        res: Dict[str, Any],
    ) -> Tuple[discord.Thread, Optional[int], Optional[int]]:
        """
        Create a new forum thread for an at-vote resolution when we do not already
        have a proposal thread tracked (e.g., bot started mid-vote or record lost).
        """
        chamber_name = "General Assembly" if council == 1 else "Security Council"

        proposal_id = (res.get("id") or "").strip()
        name = (res.get("name") or proposal_id or "Unknown Resolution").strip()
        category = (res.get("category") or "Unknown Category").strip()
        proposed_by = (res.get("proposed_by") or "Unknown").strip()

        raw_desc = res.get("desc") or ""
        desc = self._process_description(raw_desc) if raw_desc else "No description provided."

        proposal_url = f"https://www.nationstates.net/page=UN_view_proposal/id={proposal_id}"
        vote_url = "https://www.nationstates.net/page=ga" if council == 1 else "https://www.nationstates.net/page=sc"

        if proposed_by != "Unknown":
            pb_slug = self._ns_slug(proposed_by)
            proposed_by_value = f"[{proposed_by}](https://www.nationstates.net/nation={pb_slug})"
        else:
            proposed_by_value = proposed_by

        embed = discord.Embed(
            title=name,
            url=vote_url,  # at vote: link title to chamber page
            description=desc,
        )
        embed.add_field(name="Chamber", value=chamber_name, inline=True)
        embed.add_field(name="Category", value=category, inline=True)
        embed.add_field(name="Proposed by", value=proposed_by_value, inline=True)
        embed.add_field(name="Proposal ID", value=f"`{proposal_id}`", inline=False)
        embed.add_field(
            name="NationStates Link",
            value=f"[View chamber page on NationStates]({vote_url})",
            inline=False,
        )
        embed.add_field(
            name="Proposal Link",
            value=f"[View proposal on NationStates]({proposal_url})",
            inline=False,
        )

        title = f"[{chamber_name}] {name}"

        # Optional: apply GA/SC tag if present
        applied_tags = []
        try:
            desired_names = (("ga", "general assembly") if council == 1 else ("sc", "security council"))
            for tag in forum.available_tags:
                if tag.name.lower() in desired_names:
                    applied_tags.append(tag)
                    break
        except Exception as e:
            log.debug("Failed to pick forum tag for council %s: %s", council, e)

        created = await forum.create_thread(
            name=title,
            embed=embed,
            applied_tags=applied_tags or None,
        )

        thread: discord.Thread
        starter_message_id: Optional[int] = None
        ifv_message_id: Optional[int] = None

        if hasattr(created, "thread") and hasattr(created, "message"):
            thread = created.thread
            starter_msg = created.message
            if isinstance(starter_msg, discord.Message):
                starter_message_id = starter_msg.id
        elif isinstance(created, discord.Thread):
            thread = created
        else:
            thread = created  # type: ignore

        # Reserve IFV post
        try:
            command_example = f"waobserver ifv {thread.id}"
            ifv_placeholder = await thread.send(
                f"*This post is reserved for the IFV.*\n\n"
                f"Use this command to set it:\n`{command_example}`"
            )
            ifv_message_id = ifv_placeholder.id
        except Exception as e:
            log.exception("Failed to reserve IFV post in thread %s: %s", thread.id, e)

        return thread, starter_message_id, ifv_message_id


    async def _create_thread_for_proposal(
        self,
        forum: discord.ForumChannel,
        council: int,
        proposal_id: str,
        info: Dict[str, Any],
    ) -> Tuple[discord.Thread, Optional[int], Optional[int]]:
        """Create a new forum thread for a proposal with rich info and NS link, plus reserve IFV post."""

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

        try:
            created_dt = datetime.datetime.utcfromtimestamp(created_ts)
            created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            created_str = f"{created_ts} (raw)"

        approvals_list = [a for a in approvals.split(":") if a]
        approvals_count = len(approvals_list)
        if approvals_count < 20:
            return

        if proposed_by != "Unknown":
            pb_slug = self._ns_slug(proposed_by)
            proposed_by_value = (
                f"[{proposed_by}](https://www.nationstates.net/nation={pb_slug})"
            )
        else:
            proposed_by_value = proposed_by

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

        option_str = option if option else "N/A"
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

        # ---------- NEW: pick a tag based on chamber ----------
        applied_tags = []
        try:
            desired_names = (
                ("ga", "general assembly") if council == 1
                else ("sc", "security council")
            )

            for tag in forum.available_tags:
                if tag.name.lower() in desired_names:
                    applied_tags.append(tag)
                    break  # we only need one
        except Exception as e:
            log.debug("Failed to pick forum tag for council %s: %s", council, e)
        # ------------------------------------------------------

        created = await forum.create_thread(
            name=title,
            embed=embed,
            applied_tags=applied_tags or None,
        )

        thread: discord.Thread
        starter_message_id: Optional[int] = None
        ifv_message_id: Optional[int] = None

        # ThreadWithMessage-like: has .thread and .message
        if hasattr(created, "thread") and hasattr(created, "message"):
            thread = created.thread
            starter_msg = created.message
            if isinstance(starter_msg, discord.Message):
                starter_message_id = starter_msg.id
        elif isinstance(created, discord.Thread):
            thread = created
        else:
            thread = created  # type: ignore

        # Reserve second post for IFV
        try:
            command_example = f"waobserver ifv {thread.id}"

            ifv_placeholder = await thread.send(
                f"*This post is reserved for the IFV.*\n\n"
                f"Use this command to set it:\n`{command_example}`"
            )
            ifv_message_id = ifv_placeholder.id

        except Exception as e:
            log.exception("Failed to reserve IFV post in thread %s: %s", thread.id, e)

        return thread, starter_message_id, ifv_message_id



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
        thread_url = f"https://discord.com/channels/{guild.id}/{thread.id}"

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
        """Fetch proposals for a WA council from NationStates API."""
        if self.session is None or self.session.closed:
            self.session = ClientSession()

        params = {"wa": str(council), "q": "proposals"}
        headers = {"User-Agent": user_agent}

        async with self.session.get(
            WA_BASE_URL, params=params, headers=headers
        ) as resp:
            text = await resp.text()
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
            pid = (prop.findtext("ID") or "").strip()
            if not pid:
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

            coauthors = [
                (c.text or "").strip() for c in prop.findall("COAUTHOR")
            ]
            coauthors = [c for c in coauthors if c]

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
        """Handle NationStates API rate limiting based on response headers."""
        headers = resp.headers
        try:
            remaining_raw = headers.get("Ratelimit-Remaining")
            reset_raw = headers.get("Ratelimit-Reset")
            if remaining_raw is None or reset_raw is None:
                return

            remaining = int(remaining_raw)
            reset_time = int(reset_raw)

            remaining -= 10
            if remaining > 0:
                wait_time = reset_time / remaining
            else:
                wait_time = reset_time

            if 0 < wait_time < 60:
                await asyncio.sleep(wait_time)
        except Exception:
            return

    # -------------- VOTING IN THREADS --------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Watch proposal threads for vote messages.

        Any message that starts with "For", "Against", or "Abstain"
        (case-insensitive) will:
        - Record/update that user's vote for this thread.
        - React with a specific emoji.
        - Edit the message to include the current tally for this thread.
        - Update the original embed with overall thread tallies.
        """
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.Thread):
            return

        guild = message.guild
        if guild is None:
            return

        proposals = await self.config.guild(guild).proposals()
        thread_id = message.channel.id
        is_tracked = False

        for council_data in proposals.values():
            for entry in council_data.values():
                if entry.get("thread_id") == thread_id:
                    is_tracked = True
                    break
            if is_tracked:
                break

        if not is_tracked:
            return

        voter_role_id = await self.config.guild(guild).voter_role_id()
        if voter_role_id:
            if not any(r.id == voter_role_id for r in message.author.roles):
                return

        text = message.content.strip()
        if not text:
            return

        m = re.match(r"^(for|against|abstain)\b", text, flags=re.IGNORECASE)
        if not m:
            return

        choice_raw = m.group(1).lower()
        if choice_raw == "for":
            choice = "for"
            emoji = "🟢"
        elif choice_raw == "against":
            choice = "against"
            emoji = "🔴"
        else:
            choice = "abstain"
            emoji = "⚪"

        votes_conf = self.config.guild(guild).votes
        async with votes_conf() as all_votes:
            tkey = str(thread_id)
            user_key = str(message.author.id)
            thread_votes = all_votes.get(tkey, {})
            thread_votes[user_key] = choice
            all_votes[tkey] = thread_votes

            total = len(thread_votes)
            for_count = sum(1 for v in thread_votes.values() if v == "for")
            against_count = sum(1 for v in thread_votes.values() if v == "against")
            abstain_count = sum(1 for v in thread_votes.values() if v == "abstain")

        def pct(count: int) -> float:
            return round(count * 100.0 / total, 1) if total > 0 else 0.0

        for_pct = pct(for_count)
        against_pct = pct(against_count)
        abstain_pct = pct(abstain_count)

        try:
            await message.add_reaction(emoji)
        except Exception as e:
            log.debug("Failed to add reaction to vote message: %s", e)

        # Update the starter embed with overall thread votes
        try:
            guild_conf = self.config.guild(guild)
            proposals = await guild_conf.proposals()
            starter_message_id = None

            for council_data in proposals.values():
                for entry in council_data.values():
                    if entry.get("thread_id") == thread_id:
                        starter_message_id = entry.get("starter_message_id")
                        break
                if starter_message_id:
                    break

            starter_msg: Optional[discord.Message] = None

            if starter_message_id:
                try:
                    starter_msg = await message.channel.fetch_message(starter_message_id)
                except discord.NotFound:
                    starter_msg = None

            # Fallback: find first message in thread and store it
            if starter_msg is None:
                try:
                    async for msg in message.channel.history(limit=1, oldest_first=True):
                        starter_msg = msg
                        starter_message_id = msg.id
                        break
                except Exception:
                    starter_msg = None

                if starter_msg and starter_message_id:
                    for council_key, council_data in proposals.items():
                        for pid, entry in council_data.items():
                            if entry.get("thread_id") == thread_id:
                                entry["starter_message_id"] = starter_message_id
                    await guild_conf.proposals.set(proposals)

            if starter_msg and starter_msg.embeds:
                base_embed = starter_msg.embeds[0]
                embed = base_embed.copy()

                existing_fields = list(embed.fields)
                embed.clear_fields()
                for f in existing_fields:
                    if f.name != "Thread Votes":
                        embed.add_field(name=f.name, value=f.value, inline=f.inline)

                votes_value = (
                    f"For {for_count} ({for_pct}%)\n"
                    f"Against {against_count} ({against_pct}%)\n"
                    f"Abstain {abstain_count} ({abstain_pct}%)"
                )
                embed.add_field(name="Thread Votes", value=votes_value, inline=False)

                await starter_msg.edit(embed=embed)
        except Exception as e:
            log.debug("Failed to update starter embed votes: %s", e)

        # Edit the vote message with its own tally line
        base_content = message.content
        marker = "\nVote tally:"
        if "Vote tally:" in base_content:
            base_content = base_content.split(marker)[0].rstrip()

        tally_line = (
            f"\n\nVote tally: "
            f"For {for_count} ({for_pct}%), "
            f"Against {against_count} ({against_pct}%), "
            f"Abstain {abstain_count} ({abstain_pct}%)"
        )
        new_content = base_content + tally_line

        if len(new_content) > 2000:
            max_base = 2000 - len(tally_line) - 3
            base_trim = base_content[:max_base] + "..."
            new_content = base_trim + tally_line

        try:
            await message.edit(content=new_content)
        except Exception as e:
            log.debug("Failed to edit vote message for tally: %s", e)


async def setup(bot):
    await bot.add_cog(WAO(bot))
