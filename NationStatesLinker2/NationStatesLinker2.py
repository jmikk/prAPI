# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, time as dtime
from typing import Dict, List, Optional, Set

import aiohttp
import discord
import xml.etree.ElementTree as ET
from redbot.core import commands, Config
from discord.ext import tasks  
# ==========================
# Constants
# ==========================
API_URL = "https://www.nationstates.net/cgi-bin/api.cgi"
VERIFY_URL = "https://www.nationstates.net/page=verify_login"
DEFAULT_UA = "RedbotNSLinker/3.0 (contact: 9003)"
NATION_MAX_LEN = 40


# ==========================
# Helpers
# ==========================
def normalize(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def display(value: str) -> str:
    return value.replace("_", " ").title()


# ==========================
# Cog
# ==========================
class NationStatesLinker2(commands.Cog):
    """NationStates linker with multi-region access + visitor logic."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xA1C3BEEF, force_registration=True)

        self.config.register_user(
            linked_nations=[]
        )

        self.config.register_global(
            user_agent=DEFAULT_UA
        )

        self.config.register_guild(
            access_role_id=None,
            visitor_role_id=None,
            verified_role_id=None,
            regions={},  # region_norm -> mask_role_id
            update_hour=4,
            log_channel_id=None,
        )

        self.daily_sync.start()
        self.bot.add_view(self.VerifyView(self))

    def cog_unload(self):
        self.daily_sync.cancel()

    # ==========================
    # API Helpers
    # ==========================
    async def _respect_rate_limit(self, headers):
        try:
            r = int(headers.get("Ratelimit-Remaining", 1)) - 10
            reset = int(headers.get("Ratelimit-Reset", 0))
            r = max(1, r)
            await asyncio.sleep(reset / r if r else reset)
        except Exception:
            pass

    async def fetch_region_nations(self, session: aiohttp.ClientSession, region: str) -> Set[str]:
        params = {"region": region, "q": "nations"}
        async with session.get(API_URL, params=params) as resp:
            text = await resp.text()
            await self._respect_rate_limit(resp.headers)

        nations = set()
        try:
            root = ET.fromstring(text)
            el = root.find("NATIONS")
            if el is not None and el.text:
                for n in el.text.replace(",", ":").split(":"):
                    nations.add(normalize(n))
        except ET.ParseError:
            pass
        return nations

    async def verify_with_ns(self, nation: str, checksum: str) -> bool:
        params = {"a": "verify", "nation": normalize(nation), "checksum": checksum}
        headers = {"User-Agent": await self.config.user_agent()}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(API_URL, params=params) as resp:
                await self._respect_rate_limit(resp.headers)
                return (await resp.text()).strip() == "1"

    # ==========================
    # Role Sync Logic
    # ==========================
    async def sync_member(self, member: discord.Member, region_data: Dict[str, Set[str]]):
        guild = member.guild
        gconf = self.config.guild(guild)

        access = guild.get_role(await gconf.access_role_id())
        visitor = guild.get_role(await gconf.visitor_role_id())
        verified = guild.get_role(await gconf.verified_role_id())

        linked = {normalize(n) for n in await self.config.user(member).linked_nations()}
        qualifies = set()

        for region, nations in region_data.items():
            if linked & nations:
                qualifies.add(region)

        to_add, to_remove = [], []

        if linked and verified and verified not in member.roles:
            to_add.append(verified)

        if qualifies:
            if access and access not in member.roles:
                to_add.append(access)
            if visitor and visitor in member.roles:
                to_remove.append(visitor)
        else:
            if visitor and visitor not in member.roles:
                to_add.append(visitor)
            if access and access in member.roles:
                to_remove.append(access)

        regions = await gconf.regions()
        for region, role_id in regions.items():
            role = guild.get_role(role_id)
            if not role:
                continue
            if region in qualifies and role not in member.roles:
                to_add.append(role)
            if region not in qualifies and role in member.roles:
                to_remove.append(role)

        if to_add:
            await member.add_roles(*to_add, reason="NS region sync")
        if to_remove:
            await member.remove_roles(*to_remove, reason="NS region sync")

    # ==========================
    # Daily Sync
    # ==========================
    @tasks.loop(hours=24)
    async def daily_sync(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            regions = await self.config.guild(guild).regions()
            if not regions:
                continue

            headers = {"User-Agent": await self.config.user_agent()}
            async with aiohttp.ClientSession(headers=headers) as session:
                region_data = {}
                for r in regions:
                    region_data[r] = await self.fetch_region_nations(session, r)

            for m in guild.members:
                if not m.bot:
                    await self.sync_member(m, region_data)
                    await asyncio.sleep(0.1)

    # ==========================
    # Commands
    # ==========================
    @commands.command()
    async def linknation(self, ctx: commands.Context):
        view = self.VerifyView(self)
        await ctx.send(
            f"Visit {VERIFY_URL} to get your code, then click below.",
            view=view
        )

    @commands.command()
    async def unlinknation(self, ctx: commands.Context, nation: str):
        n = normalize(nation)
        async with self.config.user(ctx.author).linked_nations() as ln:
            if n in ln:
                ln.remove(n)
                await ctx.send(f"Unlinked {display(n)}")
        await self.daily_sync()

    @commands.group()
    async def nslset(self, ctx):
        pass

    @nslset.command()
    async def accessrole(self, ctx, role: discord.Role):
        await self.config.guild(ctx.guild).access_role_id.set(role.id)
        await ctx.send("Access role set.")

    @nslset.command()
    async def visitorrole(self, ctx, role: discord.Role):
        await self.config.guild(ctx.guild).visitor_role_id.set(role.id)
        await ctx.send("Visitor role set.")

    @nslset.command()
    async def verifiedrole(self, ctx, role: discord.Role):
        await self.config.guild(ctx.guild).verified_role_id.set(role.id)
        await ctx.send("Verified role set.")

    @nslset.command()
    async def region(self, ctx, region: str, role: discord.Role):
        async with self.config.guild(ctx.guild).regions() as r:
            r[normalize(region)] = role.id
        await ctx.send("Region added.")

    @commands.command()
    async def nslupdate(self, ctx):
        await ctx.send("Running sync…")
        await self.daily_sync()
        await ctx.send("Done.")

class VerifyView(discord.ui.View):
    def __init__(self, cog: "NationStatesLinker2"):
        super().__init__(timeout=None)  # ✅ persistent
        self.cog = cog

    @discord.ui.button(
        label="Verify Nation",
        style=discord.ButtonStyle.primary,
        custom_id="nsl2_verify_nation",  # ✅ required for persistence
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(NationStatesLinker2.VerifyModal(self.cog))
        except Exception as e:
            # Always respond so Discord doesn't show "Interaction failed"
            if interaction.response.is_done():
                await interaction.followup.send(f"⚠️ Error opening modal: `{type(e).__name__}: {e}`", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ Error opening modal: `{type(e).__name__}: {e}`", ephemeral=True)



async def setup(bot):
    await bot.add_cog(NationStatesLinker(bot))
