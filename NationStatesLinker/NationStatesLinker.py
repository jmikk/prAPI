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
import discord
from redbot.core import commands, Config

# Constants
VERIFY_URL = "https://www.nationstates.net/page=verify"
API_VERIFY_URL = "https://www.nationstates.net/cgi-bin/api.cgi"
DEFAULT_UA = ""  # You can change this or via command
NATION_MAX_LEN = 40


class NationStatesLinker(commands.Cog):
    """Link your NationStates nation to your Discord account with a verify button & modal."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="765435676", force_registration=True)
        self.config.register_user(linked_nations=[])
        self.config.register_global(user_agent=DEFAULT_UA)

    # --------------- Utility ---------------
    @staticmethod
    def normalize_nation(n: str) -> str:
        return n.strip().lower().replace(" ", "_")

    @staticmethod
    def display_nation(n: str) -> str:
        return n.replace("_", " ").title()

    async def _respect_rate_limit(self, headers: aiohttp.typedefs.LooseHeaders) -> None:
        """Respect NationStates API rate limits if headers are present.
        """
        try:
            remaining = headers.get("Ratelimit-Remaining")
            reset_time = headers.get("Ratelimit-Reset")
            if remaining is not None and reset_time is not None:
                remaining = int(remaining)
                remaining = max(1, remaining - 10)
                reset_time = int(reset_time)
                wait_time = (reset_time / remaining) if remaining > 0 else reset_time
                await asyncio.sleep(max(0.0, wait_time))
        except Exception:
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
            nation_list = "\n".join(
                f"[{self.display_nation(n)}](https://www.nationstates.net/nation={n})" for n in nations
            )
            await ctx.send(f"🌍 {user.display_name}'s linked NationStates nation(s):\n{nation_list}")
        else:
            await ctx.send(f"❌ {user.display_name} has not linked a NationStates nation yet.")

    @commands.command()
    async def unlinknation(self, ctx: commands.Context, *, nation_name: str):
        """Unlink a specific NationStates nation from your Discord account."""
        nation_name = self.normalize_nation(nation_name)
        async with self.config.user(ctx.author).linked_nations() as nations:
            if nation_name in nations:
                nations.remove(nation_name)
                await ctx.send(f"✅ Successfully unlinked the NationStates nation: **{self.display_nation(nation_name)}**")
            else:
                await ctx.send(f"❌ You do not have **{self.display_nation(nation_name)}** linked to your account.")

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


async def setup(bot: commands.Bot):
    await bot.add_cog(NationStatesLinker(bot))
