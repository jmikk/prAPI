from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import discord
from redbot.core import commands, Config


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
            if not q.enabled:
                continue
            if q.game != game or q.objective != objective:
                continue
            if quest_id in completed:
                continue  # already completed

            current = int(progress.get(quest_id, 0))
            current += amount
            progress[quest_id] = current

            if current >= q.target:
                completed[quest_id] = int(time.time())
                newly_completed.append(q)

        # Persist once
        await user_conf.progress.set(progress)
        await user_conf.completed.set(completed)

        # Announce completions
        if newly_completed:
            channel = await self._get_announce_channel(guild)
            if channel:
                for q in newly_completed:
                    await channel.send(
                        f"🏁 {member.mention} completed **{q.title}** "
                        f"(Game: `{q.game}`, Objective: `{q.objective}`)!"
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
        """Enable a quest (admins only)."""
        guild_conf = self.config.guild(ctx.guild)
        quests = await guild_conf.quests()
        if quest_id not in quests:
            return await ctx.send("❌ No quest found with that ID.")
        quests[quest_id]["enabled"] = True
        await guild_conf.quests.set(quests)
        await ctx.send(f"✅ Enabled quest `{quest_id}`.")

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
        """List available quests (optionally filter by game)."""
        quests_raw = await self.config.guild(ctx.guild).quests()
        if not quests_raw:
            return await ctx.send("📭 There are currently no quests configured.")

        # Build a compact list embed
        emb = discord.Embed(title="📜 Quest Board", color=discord.Color.gold())
        count = 0
        for quest_id, qdata in quests_raw.items():
            q = self._quest_from_dict(quest_id, qdata)
            if game and q.game != game:
                continue
            status = "Enabled" if q.enabled else "Disabled"
            emb.add_field(
                name=f"{q.title} ({status})",
                value=f"ID: `{q.quest_id}`\nGame: `{q.game}`\nObjective: `{q.objective}` Target: `{q.target}`",
                inline=False,
            )
            count += 1

        if count == 0:
            return await ctx.send("📭 No quests matched that filter.")

        await ctx.send(embed=emb)

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
            active_lines.append(f"• **{q.title}** (`{q.quest_id}`): {cur}/{q.target}")

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
