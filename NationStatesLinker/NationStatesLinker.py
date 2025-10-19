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

import asyncio
from typing import List, Optional

import aiohttp
import xml.etree.ElementTree as ET
import discord
from redbot.core import commands, Config

# Constants
VERIFY_URL = "https://www.nationstates.net/page=verify"
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
            region_name=None,  # e.g., "vibonia"
        )

    # --------------- Utility ---------------
    @staticmethod
    def normalize_nation(n: str) -> str:
        return n.strip().lower().replace(" ", "_")

    @staticmethod
    def display_nation(n: str) -> str:
        return n.replace("_", " ").title()

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

    async def fetch_region_members(self, region: str) -> tuple[set[str], set[str]]:
        """Fetch region member lists (residents and WA residents) from NS API.
        Returns (residents_set, wa_residents_set) of normalized nation names.
        - Residents are from <NATIONS> which are often colon-separated.
        - WA residents are from <UNNATIONS> which are often comma-separated.
        We handle both ':' and ',' and whitespace as separators defensively.
        """
        region_norm = region.strip().lower().replace(" ", "_")
        params = {"region": region_norm, "q": "nations+wanations"}
        ua = await self.config.user_agent()
        headers = {"User-Agent": ua}
        timeout = aiohttp.ClientTimeout(total=20)
        residents: set[str] = set()
        wa_residents: set[str] = set()
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(API_VERIFY_URL, params=params) as resp:
                xml_text = await resp.text()
                await self._respect_rate_limit(resp.headers)
        try:
            root = ET.fromstring(xml_text)
            nations_text = ""
            un_text = ""
            n_el = root.find("NATIONS")
            if n_el is not None and n_el.text:
                nations_text = n_el.text.strip()
            # UNNATIONS (some dumps use UNNATIONS, others UNNATIONS alias as UNNATIONS)
            un_el = root.find("UNNATIONS")
            if un_el is not None and un_el.text:
                un_text = un_el.text.strip()
            # Parse residents
            if nations_text:
                raw_parts = nations_text.replace("
", " ").replace(",", ":").split(":")
", " ").replace(",", ":").split(":")
                for part in raw_parts:
                    p = part.strip()
                    if not p:
                        continue
                    residents.add(self.normalize_nation(p))
            # Parse WA residents
            if un_text:
                # UNNATIONS frequently comma-separated
                raw_parts = un_text.replace("
", " ").replace(":", ",").split(",")
", " ").replace(":", ",").split(",")
                for part in raw_parts:
                    p = part.strip()
                    if not p:
                        continue
                    wa_residents.add(self.normalize_nation(p))
        except ET.ParseError:
            # If parsing fails, return empty sets
            pass
        return residents, wa_residents

    # Utility helpers for role assignment
    async def get_role(self, guild: discord.Guild, role_id: Optional[int]) -> Optional[discord.Role]:
        if not role_id:
            return None
        return guild.get_role(role_id)

    async def apply_roles(self, guild: discord.Guild, member: discord.Member, *, residents: Optional[set[str]] = None, wa_residents: Optional[set[str]] = None) -> bool:
        """Apply Visitor/Resident/WA Resident roles based on NS API membership.
        Stacking rules:
        - Give Resident if any linked nation is in region NATIONS.
        - Give WA Resident if any linked nation is in region UNNATIONS.
        - Remove Visitor if either Resident or WA Resident is assigned.
        Returns True if any roles were added/removed, else False.
        """
        if member.bot:
            return False
        gconf = self.config.guild(guild)
        visitor_id = await gconf.visitor_role()
        resident_id = await gconf.resident_role()
        wa_resident_id = await gconf.wa_resident_role()
        region = await gconf.region_name()

        visitor_role = await self.get_role(guild, visitor_id)
        resident_role = await self.get_role(guild, resident_id)
        wa_resident_role = await self.get_role(guild, wa_resident_id)

        nations = await self.config.user(member).linked_nations()
        nations_set = {self.normalize_nation(n) for n in nations}

        is_resident = False
        is_wa_resident = False
        if region:
            if residents is None or wa_residents is None:
                residents, wa_residents = await self.fetch_region_members(region)
            is_resident = any(n in residents for n in nations_set)
            is_wa_resident = any(n in wa_residents for n in nations_set)
        else:
            is_resident = bool(nations)
            is_wa_resident = False

        to_add = []
        to_remove = []

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
        except (discord.Forbidden, discord.HTTPException):
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
            nation_list = "
".join(
                f"[{self.display_nation(n)}](https://www.nationstates.net/nation={n})" for n in nations
            )
            await ctx.send(f"🌍 {user.display_name}'s linked NationStates nation(s):
{nation_list}")
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
                f"ℹ️ Region not set. Linked nations for {member.display_name}: {pretty}
"
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
        await ctx.send("
".join(lines))

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

    @commands.command(name="nslaudit")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def nslaudit(self, ctx: commands.Context):
        """Audit everyone in this server and update Visitor/Resident/WA roles.
        Uses NS API against the configured region.
        """
        guild = ctx.guild
        region = await self.config.guild(guild).region_name()
        if not region:
            return await ctx.send("❌ No region configured. Set one with `[p]nslset region <region>`.")
        await ctx.send("🔎 Fetching region membership from NationStates...")
        residents, wa_residents = await self.fetch_region_members(region)
        members = [m for m in guild.members if not m.bot]
        await ctx.send(f"🔁 Auditing {len(members)} members for region `{region}`...")
        updated = 0
        failed = 0
        for idx, member in enumerate(members, start=1):
            try:
                changed = await self.apply_roles(guild, member, residents=residents, wa_residents=wa_residents)
                if changed:
                    updated += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.2)
        await ctx.send(f"✅ Audit complete. Updated: {updated} | Failed: {failed}.")

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
        await ctx.send(f"✅ Region set to `{region_norm}`. Use `[p]nslaudit` to sync roles.")}`")

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


async def setup(bot: commands.Bot):
    await bot.add_cog(NationStatesLinker(bot))
