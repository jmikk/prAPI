from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import discord
from redbot.core import commands, Config

import asyncio

import math
from discord import ui

ROLE_ID_QUEST_ADMIN = 1113108765315715092  # your admin role for managing quests


def has_quest_permission():
    async def predicate(ctx: commands.Context):
        return any(role.id == ROLE_ID_QUEST_ADMIN for role in getattr(ctx.author, "roles", []))
    return commands.check(predicate)


@dataclass
class Quest:
    quest_id: str
    title: str
    description: str
    game: str                    # e.g., "hunger_games", "casino", "farming"
    objective: str               # e.g., "wins", "kills", "slots_spins"
    target: int = 1              # how many needed to complete
    enabled: bool = True


class FantasyJobBoard(commands.Cog):
    """
    Guild quest system with:
    - Admin quest creation/removal
    - Per-user progress tracking
    - Auto announcement to a configured channel on completion
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=2468024)

        self.config.register_guild(
            announce_channel_id=None,
            quests={},  # {quest_id: quest_dict}
        )
        self.config.register_user(
            progress={},     # {quest_id: int}
            completed={},    # {quest_id: unix_ts}
        )

    # -----------------------------
    # Helpers
    # -----------------------------
    async def _get_announce_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        chan_id = await self.config.guild(guild).announce_channel_id()
        if not chan_id:
            return None
        chan = guild.get_channel(chan_id)
        if isinstance(chan, discord.TextChannel):
            return chan
        return None

    def _quest_from_dict(self, quest_id: str, data: Dict[str, Any]) -> Quest:
        return Quest(
            quest_id=quest_id,
            title=data.get("title", "Untitled Quest"),
            description=data.get("description", ""),
            game=data.get("game", "unknown"),
            objective=data.get("objective", "progress"),
            target=int(data.get("target", 1)),
            enabled=bool(data.get("enabled", True)),
        )

    def _quest_to_dict(self, q: Quest) -> Dict[str, Any]:
        return {
            "title": q.title,
            "description": q.description,
            "game": q.game,
            "objective": q.objective,
            "target": q.target,
            "enabled": q.enabled,
        }

    def _make_embed_for_quest(self, q: Quest) -> discord.Embed:
        emb = discord.Embed(
            title=f"Quest: {q.title}",
            description=q.description or "*No description provided.*",
            color=discord.Color.gold() if q.enabled else discord.Color.dark_grey(),
        )
        emb.add_field(name="Quest ID", value=q.quest_id, inline=True)
        emb.add_field(name="Game", value=q.game, inline=True)
        emb.add_field(name="Objective", value=f"{q.objective} (target: {q.target})", inline=False)
        emb.set_footer(text="Use /quest progress or the quest commands to track your progress.")
        return emb

    async def _backfill_quest_for_guild(self, guild: discord.Guild, quest_id: str) -> int:
        """
        Scan all guild members and award quest completion to anyone whose stored progress
        already meets/exceeds the target. Returns number of newly-awarded completions.
        """
        quests_raw = await self.config.guild(guild).quests()
        qdata = quests_raw.get(quest_id)
        if not qdata:
            return 0
    
        q = self._quest_from_dict(quest_id, qdata)
        if not q.enabled:
            return 0  # only backfill when enabled
    
        announce_channel = await self._get_announce_channel(guild)
        newly_awarded = 0
    
        # Ensure member cache is available; if you use member intents, this should work.
        for member in guild.members:
            if member.bot:
                continue
    
            user_conf = self.config.user(member)
            completed = await user_conf.completed()
            if quest_id in completed:
                continue
    
            progress = await user_conf.progress()
            cur = int(progress.get(quest_id, 0))
    
            if cur >= q.target:
                completed[quest_id] = int(time.time())
                await user_conf.completed.set(completed)
                newly_awarded += 1
    
                if announce_channel:
                    await announce_channel.send(
                        f"🏁 {member.mention} completed **{q.title}** "
                        f"(Game: `{q.game}`, Objective: `{q.objective}`)!"
                    )
    
                # Light throttle to avoid hammering Discord if many users complete at once
                await asyncio.sleep(0.2)
    
        return newly_awarded

    # -----------------------------
    # Public API for other cogs
    # -----------------------------
    async def record_progress(
        self,
        member: discord.Member,
        *,
        game: str,
        objective: str,
        amount: int = 1,
        debug = False
    ) -> None:
        """
        Call this from other cogs whenever a player does something relevant.
        If any enabled quests match (game + objective), progress is updated.
        When a quest reaches target, it is marked complete and announced (if configured).
        """
        if member.bot or not member.guild:
            return
        if amount <= 0:
            return

        guild = member.guild
        guild_conf = self.config.guild(guild)
        user_conf = self.config.user(member)

        quests_raw = await guild_conf.quests()
        if not quests_raw:
            return

        completed = await user_conf.completed()
        progress = await user_conf.progress()

        # Iterate quests and update matching ones
        newly_completed: list[Quest] = []

        for quest_id, qdata in quests_raw.items():
            q = self._quest_from_dict(quest_id, qdata)

            if q.game != game or q.objective != objective:
                continue
            if quest_id in completed:
                continue
            
            current = int(progress.get(quest_id, 0))
            current += amount
            progress[quest_id] = current
            
            # Only award completion if enabled
            if q.enabled and current >= q.target:
                completed[quest_id] = int(time.time())
                newly_completed.append(q)


        # Persist once
        await user_conf.progress.set(progress)
        await user_conf.completed.set(completed)
        if debug:
            channel = await self._get_announce_channel(guild)
            if channel:
                await channel.send(f"DEBUG: Counted 1 Game: {game}, obj: {objective}, amount: {amount}")
            
        # Announce completions
        if newly_completed:
            channel = await self._get_announce_channel(guild)
            if channel:
                for q in newly_completed:
                    await channel.send(
                        f"🏁 {member.mention} completed the **{q.title}** quest!"
                    )

    # -----------------------------
    # Commands
    # -----------------------------
    @commands.group(name="quest", invoke_without_command=True)
    async def quest_group(self, ctx: commands.Context):
        """Quest system commands."""
        await ctx.send_help(ctx.command)

    @quest_group.command(name="setchannel")
    @has_quest_permission()
    async def quest_set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where quest completions will be announced (admins only)."""
        await self.config.guild(ctx.guild).announce_channel_id.set(channel.id)
        await ctx.send(f"✅ Quest completion announcements will be sent in {channel.mention}.")

    @quest_group.command(name="add")
    @has_quest_permission()
    async def quest_add(
        self,
        ctx: commands.Context,
        quest_id: str,
        game: str,
        objective: str,
        target: int,
        *,
        title_and_description: str,
    ):
        """
        Add a quest (admins only).

        Usage:
          [p]quest add <quest_id> <game> <objective> <target> <title | description>

        Example:
          [p]quest add hg_win_10 hunger_games wins 10 Win 10 Matches | Win 10 Hunger Games matches.
        """
        if target < 1:
            return await ctx.send("❌ Target must be at least 1.")

        if "|" in title_and_description:
            title, desc = [x.strip() for x in title_and_description.split("|", 1)]
        else:
            title, desc = title_and_description.strip(), ""

        guild_conf = self.config.guild(ctx.guild)
        quests = await guild_conf.quests()

        if quest_id in quests:
            return await ctx.send("❌ A quest with that quest_id already exists. Use a different ID or remove it first.")

        q = Quest(
            quest_id=quest_id,
            title=title,
            description=desc,
            game=game,
            objective=objective,
            target=target,
            enabled=True,
        )
        quests[quest_id] = self._quest_to_dict(q)
        await guild_conf.quests.set(quests)

        await ctx.send("✅ Quest added.")
        await ctx.send(embed=self._make_embed_for_quest(q))

    @quest_group.command(name="remove")
    @has_quest_permission()
    async def quest_remove(self, ctx: commands.Context, quest_id: str):
        """Remove a quest by ID (admins only)."""
        guild_conf = self.config.guild(ctx.guild)
        quests = await guild_conf.quests()

        if quest_id not in quests:
            return await ctx.send("❌ No quest found with that ID.")

        removed = quests.pop(quest_id)
        await guild_conf.quests.set(quests)

        await ctx.send(f"🗑️ Removed quest `{quest_id}` ({removed.get('title', 'Untitled')}).")

    @quest_group.command(name="enable")
    @has_quest_permission()
    async def quest_enable(self, ctx: commands.Context, quest_id: str):
        """Enable a quest (admins only) and retro-award it to members who already qualify."""
        guild_conf = self.config.guild(ctx.guild)
        quests = await guild_conf.quests()
        if quest_id not in quests:
            return await ctx.send("❌ No quest found with that ID.")
    
        quests[quest_id]["enabled"] = True
        await guild_conf.quests.set(quests)
    
        # Backfill scan
        awarded = await self._backfill_quest_for_guild(ctx.guild, quest_id)
    
        await ctx.send(f"✅ Enabled quest `{quest_id}`. Retro-awarded to **{awarded}** member(s).")


    @quest_group.command(name="disable")
    @has_quest_permission()
    async def quest_disable(self, ctx: commands.Context, quest_id: str):
        """Disable a quest (admins only)."""
        guild_conf = self.config.guild(ctx.guild)
        quests = await guild_conf.quests()
        if quest_id not in quests:
            return await ctx.send("❌ No quest found with that ID.")
        quests[quest_id]["enabled"] = False
        await guild_conf.quests.set(quests)
        await ctx.send(f"✅ Disabled quest `{quest_id}`.")

    @quest_group.command(name="list")
    async def quest_list(self, ctx: commands.Context, game: Optional[str] = None):
        """List available quests (paginated). Optionally filter by game."""
        quests_raw = await self.config.guild(ctx.guild).quests()
        if not quests_raw:
            return await ctx.send("📭 There are currently no quests configured.")
    
        view = QuestListView(self, ctx.author.id, ctx.guild, quests_raw, game_filter=game, per_page=3)
        view._update_button_states()
        embed = await view.render_embed(ctx.author)
        await ctx.send(embed=embed, view=view)

    @quest_group.command(name="search")
    async def quest_search(self, ctx: commands.Context, *, query: str):
        """Search quests by ID/title/description/game/objective."""
        query = query.strip().lower()
        if not query:
            return await ctx.send("❌ Provide a search term.")
    
        quests_raw = await self.config.guild(ctx.guild).quests()
        if not quests_raw:
            return await ctx.send("📭 There are currently no quests configured.")
    
        hits: list[tuple[str, dict]] = []
        for quest_id, qdata in quests_raw.items():
            haystack = " ".join([
                quest_id,
                str(qdata.get("title", "")),
                str(qdata.get("description", "")),
                str(qdata.get("game", "")),
                str(qdata.get("objective", "")),
            ]).lower()
    
            if query in haystack:
                hits.append((quest_id, qdata))
    
        if not hits:
            return await ctx.send(f"🔎 No quests matched `{query}`.")
    
        # Show first 25 matches (keep it simple; can paginate later)
        hits = hits[:25]
    
        user_conf = self.config.user(ctx.author)
        progress = await user_conf.progress()
        completed = await user_conf.completed()
    
        e = discord.Embed(
            title="🔎 Quest Search Results",
            description=f"Query: `{query}` • Matches: **{len(hits)}** (showing up to 25)",
            color=discord.Color.gold(),
        )
    
        lines = []
        for quest_id, qdata in hits:
            q = self._quest_from_dict(quest_id, qdata)
    
            if quest_id in completed:
                status = "✅ Completed"
            elif not q.enabled:
                status = "⏸️ Disabled"
            else:
                cur = int(progress.get(quest_id, 0))
                status = f"🟦 {cur}/{q.target}" if cur > 0 else f"🟨 0/{q.target}"
    
            lines.append(
                f"• **{q.title}** `({q.quest_id})` — {status}\n"
                f"  `{q.game}` • `{q.objective}` • target **{q.target}**"
            )
    
        text = "\n".join(lines)
        if len(text) > 3500:
            text = text[:3490] + "…"
    
        e.add_field(name="Matches", value=text, inline=False)
        await ctx.send(embed=e)



    @quest_group.command(name="progress")
    async def quest_progress(self, ctx: commands.Context):
        """Show your quest progress and completed quests."""
        guild_quests = await self.config.guild(ctx.guild).quests()
        if not guild_quests:
            return await ctx.send("📭 There are currently no quests configured.")

        progress = await self.config.user(ctx.author).progress()
        completed = await self.config.user(ctx.author).completed()

        emb = discord.Embed(title=f"🧭 Quest Progress for {ctx.author.display_name}", color=discord.Color.blurple())

        # Active quests
        active_lines = []
        for quest_id, qdata in guild_quests.items():
            q = self._quest_from_dict(quest_id, qdata)
            if not q.enabled:
                continue
            if quest_id in completed:
                continue
            cur = int(progress.get(quest_id, 0))
            active_lines.append(f"• **{q.title}**: {cur}/{q.target}")

        # Completed quests
        completed_lines = []
        for quest_id, ts in completed.items():
            qdata = guild_quests.get(quest_id)
            if not qdata:
                # quest removed, still show something
                completed_lines.append(f"• `{quest_id}`: completed <t:{int(ts)}:R>")
                continue
            q = self._quest_from_dict(quest_id, qdata)
            completed_lines.append(f"• **{q.title}** (`{q.quest_id}`): completed <t:{int(ts)}:R>")

        emb.add_field(
            name="Active",
            value="\n".join(active_lines) if active_lines else "No active quests (or you have completed them all).",
            inline=False,
        )
        emb.add_field(
            name="Completed",
            value="\n".join(completed_lines) if completed_lines else "None yet.",
            inline=False,
        )

        await ctx.send(embed=emb)


class QuestListView(ui.View):
    def __init__(
        self,
        cog,
        author_id: int,
        guild: discord.Guild,
        quests_raw: dict,
        *,
        game_filter: str | None = None,
        per_page: int = 10,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id
        self.guild = guild
        self.quests_raw = quests_raw
        self.game_filter = game_filter  # None = all
        self.per_page = per_page
        self.page = 0

        # Build filter options from existing quests
        games = sorted({(q.get("game") or "unknown") for q in quests_raw.values()})
        options = [discord.SelectOption(label="All Games", value="__all__", default=(game_filter is None))]
        for g in games[:24]:  # Discord limit: 25 options
            options.append(discord.SelectOption(label=g, value=g, default=(g == game_filter)))

        self.add_item(QuestGameFilterSelect(self, options))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.author_id

    def _filtered_items(self) -> list[tuple[str, dict]]:
        items = list(self.quests_raw.items())

        # Filter by game if set
        if self.game_filter:
            items = [(qid, q) for (qid, q) in items if (q.get("game") or "unknown") == self.game_filter]

        # Stable sort: enabled first, then by game, then title
        def key_fn(item):
            qid, q = item
            enabled = bool(q.get("enabled", True))
            game = q.get("game") or "unknown"
            title = q.get("title") or qid
            return (0 if enabled else 1, game.lower(), title.lower())

        items.sort(key=key_fn)
        return items

    async def render_embed(self, viewer: discord.Member) -> discord.Embed:
        items = self._filtered_items()
        total = len(items)
        pages = max(1, math.ceil(total / self.per_page))
        self.page = max(0, min(self.page, pages - 1))

        start = self.page * self.per_page
        end = start + self.per_page
        page_items = items[start:end]

        # Load viewer progress/completions to show personal status
        user_conf = self.cog.config.user(viewer)
        progress = await user_conf.progress()
        completed = await user_conf.completed()

        title = "📜 Quest Board"
        subtitle = f"Showing: {self.game_filter if self.game_filter else 'All Games'} • Page {self.page + 1}/{pages}"

        e = discord.Embed(title=title, description=subtitle, color=discord.Color.gold())

        if not page_items:
            e.add_field(name="No quests found", value="Try selecting a different game filter.", inline=False)
            return e

        lines = []
        for quest_id, qdata in page_items:
            q = self.cog._quest_from_dict(quest_id, qdata)  # uses your helper

            is_completed = quest_id in completed
            is_enabled = q.enabled
            cur = int(progress.get(quest_id, 0))
            tgt = int(q.target)

            if is_completed:
                icon = "✅"
                status = "Completed"
            elif not is_enabled:
                icon = "⏸️"
                status = "Disabled"
            elif cur > 0:
                icon = "🟦"
                status = f"In Progress ({cur}/{tgt})"
            else:
                icon = "🟨"
                status = f"Not Started (0/{tgt})"

            # Keep each entry compact; long descriptions get messy fast
            short_desc = (q.description or "").strip()
            if len(short_desc) > 80:
                short_desc = short_desc[:77] + "..."

            lines.append(
                f"{icon} **{q.title}** `({q.quest_id})`\n"
                f"• Status: {status}"
                + (f"\n• {short_desc}" if short_desc else "")
            )

        e.add_field(name="Quests", value="\n\n".join(lines), inline=False)
        e.set_footer(text="Use the dropdown to filter. Use Prev/Next to browse.")
        return e

    def _update_button_states(self):
        items = self._filtered_items()
        total = len(items)
        pages = max(1, math.ceil(total / self.per_page))
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= pages - 1

    @ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page -= 1
        self._update_button_states()
        embed = await self.render_embed(interaction.user)  # type: ignore[arg-type]
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page += 1
        self._update_button_states()
        embed = await self.render_embed(interaction.user)  # type: ignore[arg-type]
        await interaction.response.edit_message(embed=embed, view=self)


class QuestGameFilterSelect(ui.Select):
    def __init__(self, parent_view: QuestListView, options: list[discord.SelectOption]):
        super().__init__(placeholder="Filter by game...", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        self.parent_view.game_filter = None if val == "__all__" else val
        self.parent_view.page = 0
        self.parent_view._update_button_states()
        embed = await self.parent_view.render_embed(interaction.user)  # type: ignore[arg-type]
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
