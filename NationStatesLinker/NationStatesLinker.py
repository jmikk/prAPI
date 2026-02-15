# -*- coding: utf-8 -*-
"""
NationStates Linker (All-in-One Cog)
-----------------------------------
A Redbot v3 cog that lets users link their NationStates nation to their Discord
account via the official NationStates verify code flow.

Features
- /linknation (prefix command: linknation): Sends a button that opens a modal to
  collect the Nation name and the verify checksum code.
- /mynation (prefix command: mynation): Shows your linked nation(s) as clickable links.
- /unlinknation (prefix command: unlinknation <nation>): Removes a linked nation.
- Owner-only command: [p]nslset ua <string> to set the User-Agent header.

Notes
- Uses the NationStates verify API endpoint: a=verify with nation & checksum.
- Respects NS API rate limiting by reading headers and sleeping accordingly.
- Normalizes nation names to lowercase with underscores before storage.

Tested with discord.py 2.x and Red v3.
"""

from __future__ import annotations
from typing import Optional
import asyncio
from typing import List, Optional

import aiohttp
import xml.etree.ElementTree as ET
import discord
from redbot.core import commands, Config
import os
import tarfile
import io
from redbot.core import checks, data_manager

# Constants
VERIFY_URL = "https://www.nationstates.net/page=verify_login"
API_VERIFY_URL = "https://www.nationstates.net/cgi-bin/api.cgi"
DEFAULT_UA = "RedbotNSLinker/1.0 (contact: 9003)"  # You can change this or via command
NATION_MAX_LEN = 40


class NationStatesLinker(commands.Cog):
    """Link your NationStates nation to your Discord account with a verify button & modal."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xA1C3BEEF, force_registration=True)
        self.config.register_user(linked_nations=[])
        self.config.register_global(user_agent=DEFAULT_UA)
        # Guild-level settings for assignable roles and target region
        self.config.register_guild(
            visitor_role=None,
            resident_role=None,
            wa_resident_role=None,
            verified_role=None,
            region_name=None,  # e.g., "vibonia"
            log_channel_id = None,
            welcome_channel_id=None,      # NEW
            welcome_message=None,         # NEW
            welcome_enabled=False,        # NEW
        )

    # --------------- Utility ---------------
    @staticmethod
    def normalize_nation(n: str) -> str:
        return n.strip().lower().replace(" ", "_")

    @staticmethod
    def display_nation(n: str) -> str:
        return n.replace("_", " ").title()

    def _render_welcome(self, guild: discord.Guild, member: discord.Member, template: str) -> str:
      """Render {user}, {server}, {region} macros."""
      if not template:
          return ""
      # Pull region or show a friendly placeholder
      # (we do a light sync get since this is not async-safe here; call sites await in advance)
      region = None
      try:
          # best-effort; call sites should pass in a pre-fetched region if needed
          region = None
      except Exception:
          pass
      # We'll just fill region at call site (below) to avoid sync config access here.
      return template  # will be replaced at call site
  

    async def _respect_rate_limit(self, headers: aiohttp.typedefs.LooseHeaders) -> None:
        """Respect NationStates API rate limits if headers are present.
        Mirrors the user's preferred strategy (slightly defensive).
        """
        try:
            remaining = headers.get("Ratelimit-Remaining")
            reset_time = headers.get("Ratelimit-Reset")
            if remaining is not None and reset_time is not None:
                remaining = int(remaining)
                # safety margin like user's snippet
                remaining = max(1, remaining - 10)
                reset_time = int(reset_time)
                wait_time = (reset_time / remaining) if remaining > 0 else reset_time
                await asyncio.sleep(max(0.0, wait_time))
        except Exception:
            # If headers are absent or malformed, just proceed.
            pass

    async def verify_with_ns(self, nation: str, checksum: str) -> bool:
        """Call the NS verify endpoint. Returns True if verified, else False.
        API semantics: returns '1' for success, '0' for failure.
        """
        nation = self.normalize_nation(nation)
        params = {"a": "verify", "nation": nation, "checksum": checksum.strip()}
        ua = await self.config.user_agent()
        headers = {"User-Agent": ua}

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(API_VERIFY_URL, params=params) as resp:
                text = (await resp.text()).strip()
                await self._respect_rate_limit(resp.headers)
                return text == "1"
  
    def _safe_debug_send(self, ctx_or_chan, msg: str):
      if not ctx_or_chan:
          return
      try:
          # avoid accidental pings
          return ctx_or_chan.send(msg, allowed_mentions=discord.AllowedMentions.none())
      except Exception:
          pass


    async def fetch_region_members(
      self,
      region: str,
      *,
      ctx: Optional[commands.Context] = None,
      verbose: bool = False,
  ) -> tuple[set[str], set[str]]:
      """Fetch region member lists (residents and WA residents) from NS API.
      Returns (residents_set, wa_residents_set) of normalized nation names.
      """
      region_norm = region.strip().lower().replace(" ", "_")
      params = {"region": region_norm, "q": "nations+wanations"}
      ua = await self.config.user_agent()
      headers = {"User-Agent": ua}
      timeout = aiohttp.ClientTimeout(total=20)
      residents: set[str] = set()
      wa_residents: set[str] = set()
  
      if verbose:
          await self._safe_debug_send(ctx, f"🌐 GET /api.cgi params={params} UA=`{ua}`")
  
      async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
          async with session.get(API_VERIFY_URL, params=params) as resp:
              status = resp.status
              rlh = resp.headers.get("Ratelimit-Remaining")
              rlr = resp.headers.get("Ratelimit-Reset")
              ctype = resp.headers.get("Content-Type")
              xml_text = await resp.text()
              await self._respect_rate_limit(resp.headers)
  
      if verbose:
          await self._safe_debug_send(
              ctx,
              f"📥 Status: {status} | Content-Type: {ctype} | Len: {len(xml_text)} | "
              f"Rate: remaining={rlh} reset={rlr}"
          )
          # show a short preview (avoid flooding)
          preview = (xml_text[:500] + "…") if len(xml_text) > 500 else xml_text
          await self._safe_debug_send(ctx, f"🧾 XML preview:\n```xml\n{preview}\n```")
  
      try:
          root = ET.fromstring(xml_text)
          # --- residents from <NATIONS>
          nations_text = ""
          n_el = root.find("NATIONS")
          if n_el is not None and n_el.text:
              nations_text = n_el.text.strip()
  
          # --- WA residents from <WANATIONS> (correct shard name)
          wa_text = ""
          wa_el = root.find("WANATIONS")
          if wa_el is None:
              # legacy fallback if NS ever shipped alias (rare)
              wa_el = root.find("UNNATIONS")
          if wa_el is not None and wa_el.text:
              wa_text = wa_el.text.strip()
  
          if verbose:
              await self._safe_debug_send(
                  ctx,
                  f"🔎 Found tags -> NATIONS: {bool(nations_text)} | WANATIONS/UNNATIONS: {bool(wa_text)}"
              )
  
          # Parse residents (NATIONS is typically colon-separated, sometimes commas)
          if nations_text:
              raw_parts = nations_text.replace(",", ":").split(":")
              for part in raw_parts:
                  p = part.strip()
                  if p:
                      residents.add(self.normalize_nation(p))
  
          # Parse WA residents (WANATIONS often comma-separated)
          if wa_text:
              raw_parts = wa_text.replace(",", ":").split(":")
              for part in raw_parts:
                  p = part.strip()
                  if p:
                      wa_residents.add(self.normalize_nation(p))
  
          if verbose:
              # Show counts and a few samples
              res_samp = ", ".join(sorted(list(residents))[:10])
              wa_samp = ", ".join(sorted(list(wa_residents))[:10])
              await self._safe_debug_send(ctx, f"📊 Residents count: {len(residents)}; sample: {res_samp or '—'}")
              await self._safe_debug_send(ctx, f"📊 WA Residents count: {len(wa_residents)}; sample: {wa_samp or '—'}")
  
      except ET.ParseError as e:
          if verbose:
              await self._safe_debug_send(ctx, f"❌ XML ParseError: `{e}`")
          # return empty sets on error
          return set(), set()
  
      return residents, wa_residents


    # Utility helpers for role assignment
    async def get_role(self, guild: discord.Guild, role_id: Optional[int]) -> Optional[discord.Role]:
        if not role_id:
            return None
        return guild.get_role(role_id)

    async def apply_roles(
        self,
        guild: discord.Guild,
        member: discord.Member,
        *,
        residents: Optional[set[str]] = None,
        wa_residents: Optional[set[str]] = None,
        ctx: Optional[commands.Context] = None,  # NEW
    ) -> bool:
        if member.bot:
            return False
        gconf = self.config.guild(guild)
        visitor_id = await gconf.visitor_role()
        resident_id = await gconf.resident_role()
        wa_resident_id = await gconf.wa_resident_role()
        verified_role = await self.get_role(guild, gconf.verified_role)  
        region = await gconf.region_name()
        log_channel_id = await gconf.log_channel_id()  # <- we'll use this for fallback
    
        visitor_role = await self.get_role(guild, visitor_id)
        resident_role = await self.get_role(guild, resident_id)
        wa_resident_role = await self.get_role(guild, wa_resident_id)
    
        nations = await self.config.user(member).linked_nations()
        nations_set = {self.normalize_nation(n) for n in nations}
        has_any_linked = bool(nations_set)  # NEW**

        if verified_role:
            if True and verified_role not in member.roles:
                to_add.append(verified_role)

        is_resident = False
        is_wa_resident = False
        if region:
            if residents is None or wa_residents is None:
                residents, wa_residents = await self.fetch_region_members(region)
            is_resident = any(n in residents for n in nations_set)
            is_wa_resident = any(n in wa_residents for n in nations_set)
        else:
            # Default to Visitor if no region configured
            is_resident = False
            is_wa_resident = False
    
        to_add, to_remove = [], []
      
        if is_resident and resident_role and resident_role not in member.roles:
            to_add.append(resident_role)
        if is_wa_resident and wa_resident_role and wa_resident_role not in member.roles:
            to_add.append(wa_resident_role)
        if (is_resident or is_wa_resident) and visitor_role and visitor_role in member.roles:
            to_remove.append(visitor_role)
    
        if not is_resident and not is_wa_resident:
            if visitor_role and visitor_role not in member.roles:
                to_add.append(visitor_role)
            if resident_role and resident_role in member.roles:
                to_remove.append(resident_role)
            if wa_resident_role and wa_resident_role in member.roles:
                to_remove.append(wa_resident_role)
    
        changed = False
        try:
            if to_add:
                await member.add_roles(*to_add, reason="NS role sync")
                changed = True
            if to_remove:
                await member.remove_roles(*to_remove, reason="NS role sync")
                changed = True
        except (discord.Forbidden, discord.HTTPException) as e:
            # Prefer the invoking context if present
            if ctx:
                await ctx.send(
                    f"⚠️ Failed to change roles for **{member.display_name}**: "
                    f"`{type(e).__name__}: {e}`\n"
                    f"Tips: Bot needs **Manage Roles**, and its role must be **above** the target roles.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                # Fallback to configured log channel if available
                if log_channel_id:
                    chan = guild.get_channel(log_channel_id)
                    if chan:
                        try:
                            await chan.send(
                                f"⚠️ Failed to change roles for **{member}**: "
                                f"`{type(e).__name__}: {e}` (guild: {guild.name})",
                                allowed_mentions=discord.AllowedMentions.none(),
                            )
                        except Exception:
                            pass
        return changed

    # --------------- Commands ---------------
    @commands.command()
    async def linknation(self, ctx: commands.Context, *nation_name: str):
        """Send a message with a Verify button and the NS verify link."""
        shown_nation = "_".join(nation_name).replace("<", "").replace(">", "") if nation_name else "Nation_name"
        if len(shown_nation) > NATION_MAX_LEN:
            return await ctx.send("❌ Nation name too long. Please enter a valid NationStates nation name.")

        txt = (
            f"To verify your NationStates nation, visit **{VERIFY_URL}** and copy the code shown there.\n\n"
            f"Then click **Verify Nation** below to enter your nation (e.g., `{shown_nation}`) and paste the code."
        )
        view = self.VerifyButton(self)
        await ctx.send(content=txt, view=view)

    @commands.command()
    async def mynation(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Check which NationStates nation is linked to a Discord user."""
        user = user or ctx.author
        nations: List[str] = await self.config.user(user).linked_nations()
        if nations:
            nation_list = "".join(f"[{self.display_nation(n)}](https://www.nationstates.net/nation={n})" for n in nations)
            await ctx.send(f"🌍 {user.display_name}'s linked NationStates nation(s):{nation_list}")
        else:
            await ctx.send(f"❌ {user.display_name} has not linked a NationStates nation yet.")

    @commands.command(name="nslstatus")
    @commands.guild_only()
    async def nslstatus(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Show a user's NS Resident / WA Resident status and which linked nations qualify them."""
        member = user or ctx.author
        region = await self.config.guild(ctx.guild).region_name()
        nations: List[str] = await self.config.user(member).linked_nations()
        if not nations:
            return await ctx.send(f"❌ {member.display_name} has no linked nations.")
        if not region:
            pretty = ", ".join(self.display_nation(n) for n in nations)
            return await ctx.send(
                f"ℹ️ Region not set. Linked nations for {member.display_name}: {pretty}"
                f"Set one with `[p]nslset region <region>` and run `[p]nslaudit`."
            )
        # Fetch region membership once
        residents, wa_residents = await self.fetch_region_members(region)
        in_res = [n for n in nations if self.normalize_nation(n) in residents]
        in_wa = [n for n in nations if self.normalize_nation(n) in wa_residents]
        is_res = bool(in_res)
        is_wa = bool(in_wa)
        # Build a human-friendly report
        lines = [f"📍 Region: `{region}`", f"👤 User: {member.mention}"]
        lines.append("🔗 Linked nations: " + ", ".join(self.display_nation(n) for n in nations))
        if is_res:
            lines.append("🏠 Resident via: " + ", ".join(self.display_nation(n) for n in in_res))
        else:
            lines.append("🏠 Resident: no (none of the linked nations are in NATIONS)")
        if is_wa:
            lines.append("🟦 WA Resident via: " + ", ".join(self.display_nation(n) for n in in_wa))
        else:
            lines.append("🟦 WA Resident: no (none of the linked nations are in UNNATIONS)")
        # Summarize role expectation
        if is_res and is_wa:
            lines.append("✅ Expected roles: Resident + WA Resident")
        elif is_res:
            lines.append("✅ Expected role: Resident")
        elif is_wa:
            lines.append("✅ Expected role: WA Resident (no Resident if nation not in NATIONS)")
        else:
            lines.append("✅ Expected role: Visitor")
        await ctx.send("".join(lines))

    @commands.command()
    async def unlinknation(self, ctx: commands.Context, *, nation_name: str):
        """Unlink a specific NationStates nation from your Discord account."""
        nation_name = self.normalize_nation(nation_name)
        async with self.config.user(ctx.author).linked_nations() as nations:
            if nation_name in nations:
                nations.remove(nation_name)
                await ctx.send(f"✅ Successfully unlinked the NationStates nation: **{self.display_nation(nation_name)}**")
                # Re-apply roles after unlink
                if ctx.guild:
                    await self.apply_roles(ctx.guild, ctx.author)
            else:
                await ctx.send(f"❌ You do not have **{self.display_nation(nation_name)}** linked to your account.")

    @commands.command(name="nslauditmember")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def nslauditmember(self, ctx: commands.Context, member: discord.Member):
        """Audit a single member and update their Visitor/Resident/WA roles.
        Uses NS API against the configured region.
        """
        allowed_none = discord.AllowedMentions.none()
        guild = ctx.guild
    
        # ---- preflight checks
        gconf = self.config.guild(guild)
        region = await gconf.region_name()
        visitor_id = await gconf.visitor_role()
        resident_id = await gconf.resident_role()
        wa_resident_id = await gconf.wa_resident_role()
    
        # bot perms & hierarchy checks
        me = guild.me
        if not me.guild_permissions.manage_roles:
            return await ctx.send("❌ I’m missing the **Manage Roles** permission.", allowed_mentions=allowed_none)
    
        missing = []
        def _get(role_id):
            return guild.get_role(role_id) if role_id else None
    
        visitor_role = _get(visitor_id)
        resident_role = _get(resident_id)
        wa_resident_role = _get(wa_resident_id)
    
        if not visitor_role: missing.append("Visitor")
        if not resident_role: missing.append("Resident")
        if not wa_resident_role: missing.append("WA Resident")
    
        if missing:
            return await ctx.send(
                f"⚠️ Missing configured roles: {', '.join(missing)}. "
                f"Set them with `[p]nslroles visitor|resident|wa_resident <role>`.",
                allowed_mentions=allowed_none
            )
    
        too_high = []
        for r, name in [(visitor_role, "Visitor"), (resident_role, "Resident"), (wa_resident_role, "WA Resident")]:
            if r and r >= me.top_role:
                too_high.append(name)
        if too_high:
            return await ctx.send(
                f"❌ My highest role must be **above**: {', '.join(too_high)}.",
                allowed_mentions=allowed_none
            )
    
        if not region:
            return await ctx.send("❌ No region configured. Set one with `[p]nslset region <region>`.", allowed_mentions=allowed_none)
    
        await ctx.send(f"🔎 Fetching region membership for `{region}`…", allowed_mentions=allowed_none)
    
        # ---- fetch region data with error surfacing
        try:
            residents, wa_residents = await self.fetch_region_members(region)
        except Exception as e:
            return await ctx.send(
                f"❌ Failed to fetch region data for `{region}`: `{type(e).__name__}: {e}`",
                allowed_mentions=allowed_none
            )
    
        await ctx.send(f"🔁 Auditing **{member.display_name}** for region `{region}`…", allowed_mentions=allowed_none)
    
        try:
            changed = await self.apply_roles(
                guild,
                member,
                residents=residents,
                wa_residents=wa_residents,
                ctx=ctx,
            )
            if changed:
                await ctx.send(f"✅ Roles updated for **{member.display_name}**.", allowed_mentions=allowed_none)
            else:
                await ctx.send(f"ℹ️ No changes needed for **{member.display_name}**.", allowed_mentions=allowed_none)
        except Exception as e:
            await ctx.send(
                f"⚠️ Failed to audit **{member.display_name}**: `{type(e).__name__}: {e}`",
                allowed_mentions=allowed_none
            )

   
    @commands.command(name="nslaudit")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def nslaudit(self, ctx: commands.Context):
        """Audit everyone in this server and update Visitor/Resident/WA roles.
        Uses NS API against the configured region.
        """
        allowed_none = discord.AllowedMentions.none()
        guild = ctx.guild
    
        # ---- preflight checks
        gconf = self.config.guild(guild)
        region = await gconf.region_name()
        visitor_id = await gconf.visitor_role()
        resident_id = await gconf.resident_role()
        wa_resident_id = await gconf.wa_resident_role()
    
        # bot perms & hierarchy checks
        me = guild.me
        if not me.guild_permissions.manage_roles:
            return await ctx.send("❌ I’m missing the **Manage Roles** permission.", allowed_mentions=allowed_none)
    
        missing = []
        def _get(role_id):
            return guild.get_role(role_id) if role_id else None
    
        visitor_role = _get(visitor_id)
        resident_role = _get(resident_id)
        wa_resident_role = _get(wa_resident_id)
    
        if not visitor_role: missing.append("Visitor")
        if not resident_role: missing.append("Resident")
        if not wa_resident_role: missing.append("WA Resident")
    
        if missing:
            await ctx.send(
                f"⚠️ Missing configured roles: {', '.join(missing)}. "
                f"Set them with `[p]nslroles visitor|resident|wa_resident <role>`.",
                allowed_mentions=allowed_none
            )
    
        # check role position (hierarchy)
        too_high = []
        for r, name in [(visitor_role, "Visitor"), (resident_role, "Resident"), (wa_resident_role, "WA Resident")]:
            if r and r >= me.top_role:
                too_high.append(name)
        if too_high:
            return await ctx.send(
                f"❌ My highest role must be **above**: {', '.join(too_high)}.",
                allowed_mentions=allowed_none
            )
    
        if not region:
            return await ctx.send("❌ No region configured. Set one with `[p]nslset region <region>`.", allowed_mentions=allowed_none)
    
        await ctx.send("🔎 Fetching region membership from NationStates…", allowed_mentions=allowed_none)
    
        # ---- fetch region data with error surfacing
        try:
            residents, wa_residents = await self.fetch_region_members(region)
        except Exception as e:
            return await ctx.send(
                f"❌ Failed to fetch region data for `{region}`: `{type(e).__name__}: {e}`",
                allowed_mentions=allowed_none
            )
    
        members = [m for m in guild.members if not m.bot]
        await ctx.send(f"🔁 Auditing {len(members)} members for region `{region}`…", allowed_mentions=allowed_none)
    
        updated = 0
        failed = 0
        failed_lines = []
    
        # ---- audit loop with per-member error reporting
        for idx, member in enumerate(members, start=1):
            try:
                changed = await self.apply_roles(
                    guild,
                    member,
                    residents=residents,
                    wa_residents=wa_residents,
                    ctx=ctx,  # <-- lets apply_roles send detailed errors here
                )
                if changed:
                    updated += 1
            except Exception as e:
                failed += 1
                # collect + also surface immediately
                msg = f"⚠️ `{idx}/{len(members)}` failed for **{member.display_name}**: `{type(e).__name__}: {e}`"
                failed_lines.append(msg)
                await ctx.send(msg, allowed_mentions=allowed_none)
    
            # tiny pause to be gentle with rate limits
            await asyncio.sleep(0.2)
    
        # ---- final summary (and compact error recap if any)
        summary = f"✅ Audit complete. Updated: {updated} | Failed: {failed}."
        await ctx.send(summary, allowed_mentions=allowed_none)
    
        if failed_lines:
            # avoid flooding: send a compact block (discord 2000 char limit)
            header = "🧾 Error recap (first 20):"
            recap = "\n".join(failed_lines[:20])
            block = f"{header}\n{recap}"
            if len(block) > 1900:
                block = block[:1900] + "…"
            await ctx.send(block, allowed_mentions=allowed_none)


    # --------------- Role Settings ---------------
    @commands.group(name="nslroles")
    @commands.has_permissions(manage_roles=True)
    async def nslroles(self, ctx: commands.Context):
        """Set roles for NationStates verification tiers."""
        pass

    @nslroles.command(name="visitor")
    async def nslroles_visitor(self, ctx: commands.Context, role: discord.Role):
        """Set the Visitor role for unverified users."""
        await self.config.guild(ctx.guild).visitor_role.set(role.id)
        await ctx.send(f"✅ Visitor role set to {role.mention}")
      
    @nslroles.command(name="verified")
    async def nslroles_verified(self, ctx: commands.Context, role: discord.Role):
        """Set the verified role for unverified users."""
        await self.config.guild(ctx.guild).verified_role.set(role.id)
        await ctx.send(f"✅ Verified role set to {role.mention}")

    @nslroles.command(name="resident")
    async def nslroles_resident(self, ctx: commands.Context, role: discord.Role):
        """Set the Resident role for verified users."""
        await self.config.guild(ctx.guild).resident_role.set(role.id)
        await ctx.send(f"✅ Resident role set to {role.mention}")

    @nslroles.command(name="wa_resident")
    async def nslroles_wa_resident(self, ctx: commands.Context, role: discord.Role):
        """Set the WA Resident role for WA verified users."""
        await self.config.guild(ctx.guild).wa_resident_role.set(role.id)
        await ctx.send(f"✅ WA Resident role set to {role.mention}")

    # --------------- Owner-only settings ---------------
    @commands.group(name="nslset")
    @commands.is_owner()
    async def nslset(self, ctx: commands.Context):
        """NationStates Linker settings (owner only)."""
        pass

    @nslset.command(name="ua")
    async def nslset_ua(self, ctx: commands.Context, *, user_agent: str):
        """Set the User-Agent header used for NS API requests."""
        await self.config.user_agent.set(user_agent)
        await ctx.send(f"✅ User-Agent updated to: `{discord.utils.escape_markdown(user_agent)}`")

    @nslset.command(name="showua")
    async def nslset_showua(self, ctx: commands.Context):
        """Show the current User-Agent header."""
        ua = await self.config.user_agent()
        await ctx.send(f"📎 Current User-Agent: `{discord.utils.escape_markdown(ua)}`")

    @nslset.command(name="logchannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def nslset_logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set a log channel for role change messages."""
        await self.config.guild(ctx.guild).log_channel_id.set(channel.id)
        await ctx.send(f"✅ Log channel set to {channel.mention}")

    @nslset.command(name="region")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def nslset_region(self, ctx: commands.Context, *, region: str):
        """Set the target region used to determine Resident/WA Resident.
        Example: `[p]nslset region vibonia`
        """
        region_norm = self.normalize_nation(region)
        await self.config.guild(ctx.guild).region_name.set(region_norm)
        await ctx.send(f"✅ Region set to `{region_norm}`. Use `[p]nslaudit` to sync roles.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
          guild = member.guild
          gconf = self.config.guild(guild)
          enabled = await gconf.welcome_enabled()
          if not enabled:
              return
      
          channel_id = await gconf.welcome_channel_id()
          message = await gconf.welcome_message()
          if not channel_id or not message:
              return  # nothing configured
      
          channel = guild.get_channel(channel_id)
          if not channel or not isinstance(channel, discord.TextChannel):
              return
      
          region = await gconf.region_name() or "your region"
          # Render macros
          text = (
              message
              .replace("{user}", member.mention)
              .replace("{server}", guild.name)
              .replace("{region}", region)
          )
      
          # Only allow the user mention we inserted; no roles/everyone
          allowed = discord.AllowedMentions(users=True, roles=False, everyone=False)
          try:
              await channel.send(text, allowed_mentions=allowed)
          except discord.Forbidden:
              # silently ignore if we can't send there
              pass
          except discord.HTTPException:
              pass

    @nslset.command(name="welcome")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def nslset_welcome_toggle(self, ctx: commands.Context, state: str):
        """Enable or disable the welcome message. Usage: [p]nslset welcome on|off"""
        state_l = state.lower()
        if state_l not in {"on", "off"}:
            return await ctx.send("Usage: `[p]nslset welcome on|off`")
        enabled = state_l == "on"
        await self.config.guild(ctx.guild).welcome_enabled.set(enabled)
        await ctx.send(f"✅ Welcome messages {'enabled' if enabled else 'disabled'}.")
    
    @nslset.command(name="welcomechannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def nslset_welcome_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where welcome messages are sent."""
        await self.config.guild(ctx.guild).welcome_channel_id.set(channel.id)
        await ctx.send(f"✅ Welcome channel set to {channel.mention}")
    
    @nslset.command(name="welcomemsg")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def nslset_welcome_msg(self, ctx: commands.Context, *, message: str):
        """Set the welcome message. Macros: {user}, {server}, {region}."""
        await self.config.guild(ctx.guild).welcome_message.set(message)
        await ctx.send("✅ Welcome message updated.\n"
                       "Macros available: `{user}`, `{server}`, `{region}`")

    @nslset.command(name="welcomepreview")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def nslset_welcome_preview(self, ctx: commands.Context):
        """Preview the current welcome message using you as the new member."""
        gconf = self.config.guild(ctx.guild)
        channel_id = await gconf.welcome_channel_id()
        message = await gconf.welcome_message()
        if not message:
            return await ctx.send("❌ No welcome message set. Use `[p]nslset welcomemsg <text>`.")
        region = await gconf.region_name() or "your region"
    
        # Render preview as if the author joined
        rendered = (
            message
            .replace("{user}", ctx.author.mention)
            .replace("{server}", ctx.guild.name)
            .replace("{region}", region)
        )
    
        # Send preview here (don’t ping roles/everyone)
        await ctx.send(f"**Preview:**\n{rendered}", allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
    

    # --------------- UI: Button & Modal ---------------
    class VerifyButton(discord.ui.View):
        def __init__(self, cog: "NationStatesLinker", timeout: Optional[float] = 600):
            super().__init__(timeout=timeout)
            self.cog = cog

        @discord.ui.button(label="Verify Nation", style=discord.ButtonStyle.primary)
        async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
            await interaction.response.send_modal(NationStatesLinker.VerifyNationModal(self.cog))

    class VerifyNationModal(discord.ui.Modal, title="Verify your NationStates Nation"):
        def __init__(self, cog: "NationStatesLinker"):
            super().__init__()
            self.cog = cog

            self.nation_input = discord.ui.TextInput(
                label="Nation name (e.g., the_wellspring)",
                placeholder="Your NationStates nation",
                required=True,
                max_length=NATION_MAX_LEN,
            )
            self.code_input = discord.ui.TextInput(
                label="Verify code (checksum)",
                placeholder="Paste the code from the Verify page",
                required=True,
                min_length=6,
                max_length=128,
            )

            self.add_item(self.nation_input)
            self.add_item(self.code_input)

        async def on_submit(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
            nation_raw = str(self.nation_input.value)
            code_raw = str(self.code_input.value)

            # Basic validation
            if len(nation_raw.strip()) == 0:
                return await interaction.response.send_message("❌ Please provide a nation name.", ephemeral=True)
            if len(nation_raw) > NATION_MAX_LEN:
                return await interaction.response.send_message("❌ Nation name too long.", ephemeral=True)

            # Call the verify endpoint
            try:
                ok = await self.cog.verify_with_ns(nation_raw, code_raw)
            except Exception as e:
                return await interaction.response.send_message(
                    f"⚠️ Network error during verification: `{type(e).__name__}: {e}`", ephemeral=True
                )

            if not ok:
                return await interaction.response.send_message(
                    "❌ Verification failed. Double-check your nation name and code from the verify page.",
                    ephemeral=True,
                )

            # Store the normalized nation if success
            nation_norm = self.cog.normalize_nation(nation_raw)
            async with self.cog.config.user(interaction.user).linked_nations() as nations:
                if nation_norm in nations:
                    return await interaction.response.send_message(
                        f"ℹ️ **{self.cog.display_nation(nation_norm)}** is already linked to your account.",
                        ephemeral=True,
                    )
                nations.append(nation_norm)

            # Confirm success
            url = f"https://www.nationstates.net/nation={nation_norm}"
            await interaction.response.send_message(
                f"✅ Successfully verified and linked **[{self.cog.display_nation(nation_norm)}]({url})**!",
                ephemeral=True,
            )

            # Try to apply roles upon successful verification
            if interaction.guild and isinstance(interaction.user, discord.Member):
                await self.cog.apply_roles(interaction.guild, interaction.user)

    @commands.command(name="nslprobe")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def nslprobe(self, ctx: commands.Context, *, region: Optional[str] = None):
        """Debug the NS API read for a region (prints parsing details)."""
        region = region or await self.config.guild(ctx.guild).region_name()
        if not region:
            return await ctx.send("❌ No region configured or provided.", allowed_mentions=discord.AllowedMentions.none())
        await ctx.send(f"🔬 Probing region `{region}`…", allowed_mentions=discord.AllowedMentions.none())
        await self.fetch_region_members(region, ctx=ctx, verbose=True)
    
    @commands.command(name="nsladminlink")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def nsladminlink(self, ctx: commands.Context, member: discord.Member, nation: str, *, flag: Optional[str] = None):
        """Admin command to link a nation to a user. Use --force to skip verify."""
        nation_norm = self.normalize_nation(nation)
    
        if flag != "--force":
            return await ctx.send(
                "⚠️ To prevent abuse, verification requires the NS checksum.\n"
                "If you're sure, use:\n"
                f"`{ctx.clean_prefix}nsladminlink {member.id} {nation} --force` to override."
            )
    
        async with self.config.user(member).linked_nations() as nations:
            if nation_norm in nations:
                return await ctx.send(f"ℹ️ {self.display_nation(nation_norm)} is already linked to {member.display_name}.")
            nations.append(nation_norm)
    
        await ctx.send(f"✅ Force-linked **{self.display_nation(nation_norm)}** to **{member.display_name}**.")
    
        if ctx.guild:
            await self.apply_roles(ctx.guild, member, ctx=ctx)
    
        log_channel_id = await self.config.guild(ctx.guild).log_channel_id()
        if log_channel_id:
            log_channel = ctx.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"🛡️ Admin {ctx.author} force-linked {nation_norm} to {member}.")

    @commands.command(name="nslgrantverified")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def nslgrantverified(self, ctx: commands.Context):
        """
        Give the configured Verified role to every non-bot member who has at least one linked nation.
        (Does not remove the role from anyone.)
        """
        gconf = self.config.guild(ctx.guild)
        verified_id = await gconf.verified_role()
        if not verified_id:
            return await ctx.send("❌ No Verified role configured. Set it with `[p]nslroles verified <role>`.")
        verified_role = ctx.guild.get_role(verified_id)
        if not verified_role:
            return await ctx.send("❌ The configured Verified role no longer exists. Please set it again.")

        me = ctx.guild.me
        if not me.guild_permissions.manage_roles:
            return await ctx.send("❌ I’m missing the **Manage Roles** permission.")

        if verified_role >= me.top_role:
            return await ctx.send("❌ My highest role must be **above** the Verified role to assign it.")

        members = [m for m in ctx.guild.members if not m.bot]
        await ctx.send(f"🔎 Scanning {len(members)} members for linked nations…")

        updated = 0
        checked = 0
        for m in members:
            try:
                nations = await self.config.user(m).linked_nations()
                if nations and verified_role not in m.roles:
                    await m.add_roles(verified_role, reason="NS verified grant (has linked nation)")
                    updated += 1
            except (discord.Forbidden, discord.HTTPException):
                # Skip silently but continue
                pass
            checked += 1

        await ctx.send(f"✅ Done. Checked: {checked} | Newly given Verified: {updated}.")

    @commands.group()
    @checks.is_owner()
    async def migrate(self, ctx):
        """Instance migration tools."""
        pass

    @migrate.command(name="pack")
    async def pack_instance(self, ctx):
        """Zips the entire instance and uploads it to the channel."""
        # FIX: Changed instance_dir() to data_path()
        instance_path = data_manager.data_path()
        instance_name = data_manager.instance_name()
        archive_name = f"{instance_name}_backup.tar.gz"

        await ctx.send("📦 Packing instance data... this may take a moment.")

        # Filter to skip the bulky/error-prone RepoManager cache and logs
        def migration_filter(tarinfo):
            if "RepoManager/repos" in tarinfo.name or "logs" in tarinfo.name or ".git" in tarinfo.name:
                return None
            return tarinfo

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # We add the instance_path directly
            tar.add(instance_path, arcname=instance_name, filter=migration_filter)
        
        buf.seek(0)
        file_to_send = discord.File(buf, filename=archive_name)
        
        await ctx.send(f"✅ Pack complete for `{instance_name}`. Uploading...", file=file_to_send)

    @migrate.command(name="unpack")
    async def unpack_instance(self, ctx):
        """Downloads an attached .tar.gz and extracts it."""
        if not ctx.message.attachments:
            return await ctx.send("❌ Please attach the `.tar.gz` file.")

        attachment = ctx.message.attachments[0]
        # FIX: Ensure we extract to the directory ABOVE the data folder
        # because the tar contains the instance name folder
        target_dir = os.path.dirname(data_manager.data_path())

        await ctx.send(f"📥 Downloading and extracting to `{target_dir}`...")

        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                data = await resp.read()

        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tar.extractall(path=target_dir)

        await ctx.send("✅ Data unpacked! Restart the bot to see your old data.")
    





async def setup(bot: commands.Bot):
    await bot.add_cog(NationStatesLinker(bot))
