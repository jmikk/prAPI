# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from typing import Dict, Set, Iterable, List, Tuple
import re

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

def split_nations_blob(blob: str) -> List[str]:
    """
    Split a user-provided blob into nation tokens.
    Accepts commas, semicolons, pipes, newlines, and whitespace.
    """
    if not blob:
        return []
    # Split on commas/semicolons/pipes/newlines OR any whitespace
    parts = re.split(r"[,\n;|]+|\s{1,}", blob.strip())
    return [p for p in (x.strip() for x in parts) if p]


# ==========================
# Cog
# ==========================
class NationStatesLinker2(commands.Cog):
    """NationStates linker with multi-region access + visitor logic."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xA1C3BEEF, force_registration=True)

        self.config.register_user(linked_nations=[])

        self.config.register_global(user_agent=DEFAULT_UA)

        self.config.register_guild(
            access_role_id=None,
            visitor_role_id=None,
            verified_role_id=None,
            regions={},  # region_norm -> role_id
            update_hour=4,
            log_channel_id=None,
            target_nation=None,              # normalized nation name
            trade_last_timestamp=0,          # int unix timestamp
            trade_stats={},                  # seller -> {"legendary": int, "nonlegendary": int}
        )


        self.daily_sync.start()
        self.bot.add_view(self.VerifyView(self))

    def cog_unload(self):
        self.daily_sync.cancel()

    # ==========================
    # API Helpers
    # ==========================

    # ==========================
    # Trades Processing
    # ==========================
    async def fetch_recent_trades(
        self,
        session: aiohttp.ClientSession,
        limit: int = 1000,
        sincetime: int | None = None,
    ) -> str:
        """
        Fetch trades XML for all cards. Uses the documented format:
          ?q=cards+trades;limit=...;sincetime=...
        Returns raw XML text.
        """
        q = f"cards trades;limit={int(limit)}"
        if sincetime and sincetime > 0:
            q += f";sincetime={int(sincetime)}"

        # Important: NS expects the semicolon syntax as part of q
        params = {"q": q}

        async with session.get(API_URL, params=params) as resp:
            text = await resp.text()
            await self._respect_rate_limit(resp.headers)
            return text

    def parse_trades_xml(self, xml_text: str) -> List[dict]:
        """
        Parses the trades response into a list of dicts.
        Defensive: fields vary across API versions and shards; we treat missing tags gracefully.
        Expected tags commonly include:
          TRADE/CARDID, TRADE/SEASON, TRADE/BUYER, TRADE/SELLER, TRADE/PRICE, TRADE/TIMESTAMP
          and sometimes CATEGORY or RARITY.
        """
        trades: List[dict] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return trades

        # The trades entries are typically under <TRADES><TRADE>...</TRADE></TRADES>
        for t in root.findall(".//TRADE"):
            def get_text(tag: str) -> str:
                el = t.find(tag)
                return (el.text or "").strip() if el is not None else ""

            cardid = get_text("CARDID")
            season = get_text("SEASON")
            buyer = normalize(get_text("BUYER")) if get_text("BUYER") else ""
            seller = normalize(get_text("SELLER")) if get_text("SELLER") else ""
            price_raw = get_text("PRICE")
            timestamp_raw = get_text("TIMESTAMP")

            category = get_text("CATEGORY")
            rarity = get_text("RARITY")

            # Normalize timestamp/price
            try:
                ts = int(timestamp_raw) if timestamp_raw else 0
            except ValueError:
                ts = 0

            # price can be blank or numeric
            price_blank = (price_raw == "")

            price_val = 0
            if not price_blank:
                try:
                    price_val = int(price_raw)
                except ValueError:
                    price_val = 0

            trades.append(
                {
                    "cardid": cardid,
                    "season": season,
                    "buyer": buyer,
                    "seller": seller,
                    "price_blank": price_blank,
                    "price": price_val,
                    "timestamp": ts,
                    "category": category.strip().lower(),
                    "rarity": rarity.strip().lower(),
                }
            )

        return trades

    def trade_is_legendary(self, trade: dict) -> bool:
        """
        Determine legendary-ness as robustly as possible across possible tags.
        """
        # Some APIs/clients use rarity; some use category; sometimes numeric categories exist.
        if trade.get("rarity") == "legendary":
            return True
        if trade.get("category") == "legendary":
            return True
        return False

    async def build_linked_nations_for_guild(self, guild: discord.Guild) -> Set[str]:
        """
        Build a set of all linked nations for members of THIS guild.
        This is used to decide whether a seller is "in the linked nations list".
        """
        linked: Set[str] = set()
        for m in guild.members:
            if m.bot:
                continue
            try:
                ln = await self.config.user(m).linked_nations()
            except Exception:
                continue
            for n in ln or []:
                nn = normalize(n)
                if nn:
                    linked.add(nn)
        return linked

    async def process_trade_records_for_guild(self, guild: discord.Guild):
        """
        Process the cards trades feed:
          - find trades where buyer==target_nation and (PRICE blank or 0)
          - if seller not in linked nations, log it and update leaderboards
        """
        gconf = self.config.guild(guild)
        target = await gconf.target_nation()
        if not target:
            return  # not configured

        log_channel_id = await gconf.log_channel_id()
        log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
        if log_channel is None:
            return  # nowhere to log

        last_ts = await gconf.trade_last_timestamp()
        headers = {"User-Agent": await self.config.user_agent()}

        linked_nations = await self.build_linked_nations_for_guild(guild)

        async with aiohttp.ClientSession(headers=headers) as session:
            xml_text = await self.fetch_recent_trades(session, limit=1000, sincetime=last_ts)

        trades = self.parse_trades_xml(xml_text)
        if not trades:
            return

        # Track max timestamp to advance our cursor
        max_ts = last_ts

        alerts: List[str] = []

        async with gconf.trade_stats() as stats:
            for tr in trades:
                ts = tr.get("timestamp", 0)
                if ts and ts > max_ts:
                    max_ts = ts

                if tr.get("buyer") != target:
                    continue

                # PRICE blank or 0
                if not (tr.get("price_blank") or tr.get("price", 0) == 0):
                    continue

                seller = tr.get("seller") or ""
                if not seller:
                    continue

                # If seller is NOT linked, alert
                if seller not in linked_nations:
                    cardid = tr.get("cardid") or ""
                    season = tr.get("season") or ""
                    if not cardid or not season:
                        continue

                    url = f"https://www.nationstates.net/page=deck/card={cardid}/season={season}/trades_history=1"

                    price_display = "blank" if tr.get("price_blank") else str(tr.get("price", 0))
                    alerts.append(
                        f"- Unlinked seller **{display(seller)}** sold to **{display(target)}** at price **{price_display}**: {url}"
                    )

                    # Update leaderboards (per seller)
                    entry = stats.get(seller, {"legendary": 0, "nonlegendary": 0})
                    if self.trade_is_legendary(tr):
                        entry["legendary"] = int(entry.get("legendary", 0)) + 1
                    else:
                        entry["nonlegendary"] = int(entry.get("nonlegendary", 0)) + 1
                    stats[seller] = entry

        # Persist cursor forward (only if it advanced)
        if max_ts > last_ts:
            await gconf.trade_last_timestamp.set(max_ts)

        # Log alerts (chunk to avoid Discord limits)
        if alerts:
            header = f"**NS Trades Monitor** — Buyer: **{display(target)}** — Unlinked seller alerts:\n"
            chunk = header
            for line in alerts:
                if len(chunk) + len(line) + 1 > 1900:
                    await log_channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())
                    chunk = header + line + "\n"
                else:
                    chunk += line + "\n"
            if chunk.strip() != header.strip():
                await log_channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())

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
                    nn = normalize(n)
                    if nn:
                        nations.add(nn)
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
    # Region Data Builder
    # ==========================
    async def build_region_data_for_guild(self, guild: discord.Guild) -> Dict[str, Set[str]]:
        gconf = self.config.guild(guild)
        regions = await gconf.regions()
        if not regions:
            return {}

        headers = {"User-Agent": await self.config.user_agent()}
        region_data: Dict[str, Set[str]] = {}

        async with aiohttp.ClientSession(headers=headers) as session:
            for region_norm in regions.keys():
                region_data[region_norm] = await self.fetch_region_nations(session, region_norm)

        return region_data

    # ==========================
    # Role Sync Logic
    # ==========================
    async def sync_member(self, member: discord.Member, region_data: Dict[str, Set[str]]):
        guild = member.guild
        gconf = self.config.guild(guild)

        access = guild.get_role(await gconf.access_role_id())
        visitor = guild.get_role(await gconf.visitor_role_id())
        verified = guild.get_role(await gconf.verified_role_id())

        linked = {normalize(n) for n in await self.config.user(member).linked_nations() if n}

        # RULE: No mask/roles unless you link a nation
        if not linked:
            to_remove = []
            if access and access in member.roles:
                to_remove.append(access)
            if visitor and visitor in member.roles:
                to_remove.append(visitor)

            regions = await gconf.regions()
            for _, role_id in regions.items():
                role = guild.get_role(role_id)
                if role and role in member.roles:
                    to_remove.append(role)

            if verified and verified in member.roles:
                # Optional: keep verified only if you want "verified" to imply "has linked at least once".
                # If you want verified removed when no linked nations exist, keep this line.
                to_remove.append(verified)

            if to_remove:
                await member.remove_roles(*to_remove, reason="NS unlink/no-linked cleanup")
            return

        qualifies = set()
        for region, nations in region_data.items():
            if linked & nations:
                qualifies.add(region)

        to_add, to_remove = [], []

        # If they have linked nations, ensure verified role exists (successful verification is what adds linked nations)
        if verified and verified not in member.roles:
            to_add.append(verified)

        if qualifies:
            # In-region: Access + region role(s), no visitor
            if access and access not in member.roles:
                to_add.append(access)
            if visitor and visitor in member.roles:
                to_remove.append(visitor)
        else:
            # Not in-region: Visitor only, no access or region roles
            if visitor and visitor not in member.roles:
                to_add.append(visitor)
            if access and access in member.roles:
                to_remove.append(access)

        regions = await gconf.regions()
        for region, role_id in regions.items():
            role = guild.get_role(role_id)
            if not role:
                continue

            if qualifies:
                # Add only the region roles they qualify for
                if region in qualifies and role not in member.roles:
                    to_add.append(role)
                if region not in qualifies and role in member.roles:
                    to_remove.append(role)
            else:
                # If they qualify for none, remove all region roles
                if role in member.roles:
                    to_remove.append(role)

        if to_add:
            await member.add_roles(*to_add, reason="NS region sync")
        if to_remove:
            await member.remove_roles(*to_remove, reason="NS region sync")

    async def run_member_sync(self, member: discord.Member):
        """Fetch current region memberships and sync a single member immediately."""
        if not member.guild:
            return
        region_data = await self.build_region_data_for_guild(member.guild)
        await self.sync_member(member, region_data)

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

            region_data = await self.build_region_data_for_guild(guild)

            for m in guild.members:
                if not m.bot:
                    await self.sync_member(m, region_data)
            await self.process_trade_records_for_guild(guild)

    # ==========================
    # Commands
    # ==========================
    @commands.command()
    async def linknation(self, ctx: commands.Context):
        view = self.VerifyView(self)
        await ctx.send(
            f"Visit {VERIFY_URL} to get your code, then click below to verify.",
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )


    @commands.command(name="nsltradelb")
    async def nsltradelb(self, ctx: commands.Context):
        """
        Show two leaderboards:
          - Non-legendary count
          - Legendary count
        Counts are for flagged trades (buyer==target_nation and price blank/0 and seller not linked).
        """
        gconf = self.config.guild(ctx.guild)
        target = await gconf.target_nation()
        stats = await gconf.trade_stats()

        if not target:
            return await ctx.send("No target nation configured. Set it with `nslset targetnation <nation>`.")
        if not stats:
            return await ctx.send("No trade alerts have been recorded yet.")

        # Build sorted lists
        nonleg = sorted(((k, int(v.get("nonlegendary", 0))) for k, v in stats.items()), key=lambda x: x[1], reverse=True)
        leg = sorted(((k, int(v.get("legendary", 0))) for k, v in stats.items()), key=lambda x: x[1], reverse=True)

        # Trim to top N
        top_n = 15
        nonleg = [(k, c) for k, c in nonleg if c > 0][:top_n]
        leg = [(k, c) for k, c in leg if c > 0][:top_n]

        lines = [f"**NS Trades Monitor Leaderboards** — Buyer: **{display(target)}**", ""]

        lines.append("**Non-Legendary (Top 15):**")
        if nonleg:
            lines.extend([f"{i+1}. **{display(k)}** — {c}" for i, (k, c) in enumerate(nonleg)])
        else:
            lines.append("_No non-legendary counts recorded._")

        lines.append("")
        lines.append("**Legendary (Top 15):**")
        if leg:
            lines.extend([f"{i+1}. **{display(k)}** — {c}" for i, (k, c) in enumerate(leg)])
        else:
            lines.append("_No legendary counts recorded._")

        msg = "\n".join(lines)
        # Ensure size safety
        if len(msg) > 1900:
            msg = msg[:1900] + "\n…"
        await ctx.send(msg)



    @commands.command(name="mynations")
    async def mynations(self, ctx: commands.Context, *args: str):
        """
        Show linked nations in ~1900-char pages.

        Usage:
          - mynations
          - mynations 2
          - mynations @User
          - mynations @User 2
        """
        target: discord.Member = ctx.author if isinstance(ctx.author, discord.Member) else None
        page: int = 1

        # -------- Parse args --------
        # Accept patterns:
        #   [] -> self, page 1
        #   [page] -> self, page
        #   [member] -> member, page 1
        #   [member, page] -> member, page
        if len(args) == 1:
            token = args[0]
            if token.isdigit():
                page = int(token)
            else:
                try:
                    target = await commands.MemberConverter().convert(ctx, token)
                except commands.BadArgument:
                    return await ctx.send(
                        "I couldn't resolve that user. Use `mynations 2`, `mynations @User`, or `mynations @User 2`."
                    )
        elif len(args) >= 2:
            member_token = args[0]
            page_token = args[1]

            try:
                target = await commands.MemberConverter().convert(ctx, member_token)
            except commands.BadArgument:
                return await ctx.send(
                    "I couldn't resolve that user. Try `mynations @User 2` (ping them or use their ID)."
                )

            if page_token.isdigit():
                page = int(page_token)
            else:
                return await ctx.send("Page must be a number, e.g. `mynations @User 2`.")

        if not isinstance(target, discord.Member):
            return await ctx.send("This command must be used in a server.")

        if page < 1:
            page = 1

        # -------- Load linked nations for target --------
        linked = [normalize(n) for n in await self.config.user(target).linked_nations()]
        linked = sorted({n for n in linked if n})

        if not linked:
            if target.id == ctx.author.id:
                return await ctx.send("You do not have any linked nations yet.")
            return await ctx.send(f"{target.display_name} does not have any linked nations yet.")

        # -------- Build pages up to ~1900 chars --------
        header_base = "**Linked nations:**\n"
        chunks = []
        current = ""

        for n in linked:
            line = f"- **{display(n)}** — https://www.nationstates.net/nation={n}\n"

            # Extremely defensive: prevent a pathological single-line overflow
            if len(line) > 1800:
                line = line[:1800] + "…\n"

            if not current:
                current = header_base + line
            elif len(current) + len(line) > 1900:
                chunks.append(current)
                current = header_base + line
            else:
                current += line

        if current:
            chunks.append(current)

        total_pages = len(chunks)

        if page > total_pages:
            return await ctx.send(
                f"Page {page} is out of range. {target.display_name} has **{total_pages}** page(s). "
                f"Try `mynations {target.mention} {total_pages}`."
            )

        # -------- Add page indicator + whose list --------
        who = "Your" if target.id == ctx.author.id else f"{target.display_name}'s"
        msg = chunks[page - 1].replace(
            header_base,
            f"**{who} linked nations (page {page}/{total_pages}):**\n",
            1,
        )

        await ctx.send(msg)



    @commands.command()
    async def unlinknation(self, ctx: commands.Context, nation: str):
        n = normalize(nation)
        changed = False
        async with self.config.user(ctx.author).linked_nations() as ln:
            if n in ln:
                ln.remove(n)
                changed = True

        if changed:
            await ctx.send(f"Unlinked {display(n)}")
        else:
            await ctx.send(f"{display(n)} was not linked.")

        if isinstance(ctx.author, discord.Member):
            await self.run_member_sync(ctx.author)

    @commands.command(name="addnations")
    @commands.has_role("Board of Directors")
    async def addnations(self, ctx: commands.Context, *, nations: str):
        """
        Bulk-add nations to your linked list WITHOUT verification.
        Accepts comma/space/newline separated lists.
        """
        tokens = split_nations_blob(nations)
        if not tokens:
            return await ctx.send("No nations found in your input. Example: `addnations testlandia, my nation, another_nation`")

        # Normalize + validate length
        cleaned = []
        for t in tokens:
            nn = normalize(t)
            if not nn:
                continue
            if len(nn) > NATION_MAX_LEN:
                continue
            cleaned.append(nn)

        if not cleaned:
            return await ctx.send("No valid nations were found after cleaning/normalizing.")

        added = []
        already = []
        async with self.config.user(ctx.author).linked_nations() as ln:
            existing = set(normalize(x) for x in ln if x)
            for nn in cleaned:
                if nn in existing:
                    already.append(nn)
                    continue
                ln.append(nn)
                existing.add(nn)
                added.append(nn)

        # Feedback
        msg_parts = []
        if added:
            msg_parts.append(
                "**Added (no verification):**\n" +
                "\n".join(f"- {display(n)}" for n in added[:25]) +
                (f"\n…and {len(added) - 25} more." if len(added) > 25 else "")
            )
        if already:
            msg_parts.append(
                "**Already linked (skipped):**\n" +
                "\n".join(f"- {display(n)}" for n in already[:25]) +
                (f"\n…and {len(already) - 25} more." if len(already) > 25 else "")
            )

        await ctx.send("\n\n".join(msg_parts) if msg_parts else "Nothing changed.")

        # Sync roles immediately
        if isinstance(ctx.author, discord.Member):
            await self.run_member_sync(ctx.author)


    @commands.group()
    async def nslset(self, ctx):
        pass

    @nslset.command(name="logchannel")
    @commands.has_permissions(manage_guild=True)
    async def nslset_logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).log_channel_id.set(channel.id)
        await ctx.send(f"Log channel set to {channel.mention}")

    @nslset.command(name="targetnation")
    @commands.has_permissions(manage_guild=True)
    async def nslset_targetnation(self, ctx: commands.Context, *, nation: str):
        nn = normalize(nation)
        if not nn or len(nn) > NATION_MAX_LEN:
            return await ctx.send("Invalid nation name.")
        await self.config.guild(ctx.guild).target_nation.set(nn)
        await ctx.send(f"Target nation set to **{display(nn)}**")

    @nslset.command(name="test_loop")
    @commands.has_permissions(manage_guild=True)
    async def test_loop(self):
        self.daily_sync()

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
        await ctx.send("Running sync...")
        # Trigger one full pass (don’t call the task function directly)
        for guild in self.bot.guilds:
            regions = await self.config.guild(guild).regions()
            if not regions:
                continue
            region_data = await self.build_region_data_for_guild(guild)
            for m in guild.members:
                if not m.bot:
                    await self.sync_member(m, region_data)
                    await asyncio.sleep(0.1)
        await ctx.send("Done.")

    # ==========================
    # UI
    # ==========================
    class VerifyView(discord.ui.View):
        def __init__(self, cog: "NationStatesLinker2"):
            super().__init__(timeout=None)  # persistent
            self.cog = cog

        @discord.ui.button(
            label="Verify Nation",
            style=discord.ButtonStyle.primary,
            custom_id="nsl2_verify_nation",
        )
        async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                await interaction.response.send_modal(NationStatesLinker2.VerifyModal(self.cog))
            except Exception as e:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        f"Error opening modal: `{type(e).__name__}: {e}`",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        f"Error opening modal: `{type(e).__name__}: {e}`",
                        ephemeral=True,
                    )

    class VerifyModal(discord.ui.Modal):
        def __init__(self, cog: "NationStatesLinker2"):
            super().__init__(title="Verify Nation")
            self.cog = cog

            self.nation = discord.ui.TextInput(label="Nation", max_length=NATION_MAX_LEN)
            self.code = discord.ui.TextInput(label="Verify Code", max_length=128)
            self.add_item(self.nation)
            self.add_item(self.code)

        async def on_submit(self, interaction: discord.Interaction):
            ok = await self.cog.verify_with_ns(self.nation.value, self.code.value)
            if not ok:
                return await interaction.response.send_message("Verification failed.", ephemeral=True)

            nation_norm = normalize(self.nation.value)
            async with self.cog.config.user(interaction.user).linked_nations() as ln:
                if nation_norm not in ln:
                    ln.append(nation_norm)

            await interaction.response.send_message(
                f"Linked **[{display(nation_norm)}](https://www.nationstates.net/nation={nation_norm})**",
                ephemeral=True,
            )
            await self.cog.run_member_sync(interaction.user)


async def setup(bot):
    await bot.add_cog(NationStatesLinker2(bot))
