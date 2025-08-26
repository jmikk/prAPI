
# CrossServer Portal Chat Cog for Red-DiscordBot (v3)
# Features
# - Cross-server/channel "portal" chat relayed via webhooks, impersonating sender (nickname ~ server) + avatar
# - Restrict operation to admin-configured channels only
# - Global (portal-wide) ban list to stop specific users' messages from crossing
# - Mentions disabled across servers (@everyone/@here/user/role pings sanitized)
# - Optional reply workflow via a bot-side Reply button + Modal that posts back through the portal
# - Works even if you run two separate bots (each guild stores partner webhooks; no direct bot-to-bot socket needed)
#
# Setup Outline (per guild):
# 1) Create a webhook in the *destination* channel of each partner guild and copy its URL.
# 2) On each bot, run: [p]portal addchannel #portal
# 3) On each bot, run: [p]portal addpartner <partner_guild_id> <webhook_url>
#    (repeat for each partner destination you want to relay to)
# 4) (Optional) Enable/disable the reply controls: [p]portal togglereplies
# 5) Test by sending a message in an allowed channel; it should appear in partner channels.
#
# NOTE: Webhooks do not generate component interactions. So after sending the impersonated webhook message,
#       the bot also sends a small control message with a Reply button (owned by the bot) beneath it. Clicking
#       that button opens a Modal to type a reply. The reply is then sent *via webhook* impersonating the replier
#       back across the portal, prefixed with a reference to the original.

from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from redbot.core import commands as redcommands
from redbot.core import Config, checks

MENTION_RE = re.compile(r"<@!?\d+>|<@&\d+>|@everyone|@here")

__all__ = ["CrossPortal"]

class CrossPortal(commands.Cog):
    """Cross-server portal chat using webhooks, with admin controls and reply buttons."""

    default_guild = {
        "allowed_channels": [],              # list[int]
        "partners": {},                      # dict[str_guild_id] -> webhook_url
        "banned_users": [],                  # list[int]
        "enable_replies": True,              # show Reply controls beneath mirrored msgs
    }

    default_global = {
        "message_map": {}                    # mirrored_msg_id(str) -> {origin fields}
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xC0FFEE77B07)
        self.config.register_guild(**self.default_guild)
        self.config.register_global(**self.default_global)

    # -------------------- UTILITIES --------------------
    @staticmethod
    def _display_name(member: discord.Member) -> str:
        base = member.nick or member.name
        guild_name = member.guild.name
        # Keep within Discord limits (~80 for username); trim conservatively
        combo = f"{base} ~ {guild_name}"
        if len(combo) > 80:
            combo = combo[:77] + "…"
        return combo

    @staticmethod
    def _sanitize_content(text: str) -> str:
        # Remove/neutralize mentions to prevent cross-server pings
        def repl(m: re.Match) -> str:
            s = m.group(0)
            return s.replace("@", "@\u200b")  # break ping
        return MENTION_RE.sub(repl, text)

    @staticmethod
    def _allowed_mentions() -> discord.AllowedMentions:
        return discord.AllowedMentions(users=False, roles=False, everyone=False, replied_user=False)

    async def _send_via_webhook(
        self,
        webhook_url: str,
        content: str,
        username: str,
        avatar_url: Optional[str] = None,
        files: Optional[List[discord.File]] = None,
        embeds: Optional[List[discord.Embed]] = None,
        reference_hint: Optional[str] = None,
    ) -> Optional[discord.WebhookMessage]:
        try:
            wh = discord.Webhook.from_url(webhook_url, client=self.bot)
            # Prepend reference hint (for replies)
            if reference_hint:
                content = f"↪️ {reference_hint}\n{content}" if content else f"↪️ {reference_hint}"
            msg = await wh.send(
                content=content or None,
                username=username,
                avatar_url=avatar_url,
                wait=True,
                allowed_mentions=self._allowed_mentions(),
                files=files or None,
                embeds=embeds or None,
            )
            return msg
        except Exception:
            return None

    async def _post_reply_controls(self, channel: discord.TextChannel, origin_payload: dict):
        # Small bot-owned control message with a Reply button referencing the mirrored id
        view = ReplyController(self, origin_payload)
        try:
            await channel.send(
                content=f"Reply to **{origin_payload.get('origin_author_name','someone')}**'s message above:",
                view=view,
                allowed_mentions=self._allowed_mentions(),
            )
        except Exception:
            pass

    # -------------------- LISTENERS --------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots, DMs, system messages
        if message.guild is None or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if message.channel.id not in guild_conf["allowed_channels"]:
            return

        # Skip if banned
        if message.author.id in set(guild_conf["banned_users"]):
            return

        # Prepare impersonation fields
        username = self._display_name(message.author)
        avatar_url = message.author.display_avatar.url if message.author.display_avatar else None

        content = message.content or ""
        content = self._sanitize_content(content)

        # forward attachments as URLs (simple baseline); advanced: download & reupload files
        embeds: List[discord.Embed] = []
        attach_lines = []
        for a in message.attachments:
            # don't allow mentions in filenames
            safe_name = self._sanitize_content(a.filename)
            attach_lines.append(f"[Attachment: {safe_name}] {a.url}")
        if attach_lines:
            content = (content + "\n" if content else "") + "\n".join(attach_lines)

        # for each partner webhook, send mirrored message
        partners: Dict[str, str] = guild_conf["partners"]
        if not partners:
            return

        # Keep a record mapping mirrored IDs to origin for reply controls
        origin_hint = {
            "origin_guild_id": message.guild.id,
            "origin_channel_id": message.channel.id,
            "origin_message_id": message.id,
            "origin_author_id": message.author.id,
            "origin_author_name": username,
            "origin_excerpt": (message.content[:100] + "…") if message.content and len(message.content) > 100 else (message.content or ""),
        }

        for partner_gid, webhook_url in partners.items():
            mirrored = await self._send_via_webhook(
                webhook_url=webhook_url,
                content=content,
                username=username,
                avatar_url=avatar_url,
                embeds=embeds,
            )
            if not mirrored:
                continue

            # Save mapping for reply controls
            try:
                async with self.config.message_map() as mmap:
                    mmap[str(mirrored.id)] = origin_hint
            except Exception:
                pass

            # Add Reply controls if enabled
            if guild_conf.get("enable_replies", True) and isinstance(mirrored.channel, discord.TextChannel):
                await self._post_reply_controls(mirrored.channel, origin_hint)

    # -------------------- COMMANDS --------------------
    @redcommands.group(name="portal")
    @commands.guild_only()
    @checks.admin()
    async def portal_group(self, ctx: commands.Context):
        """Configure the cross-server portal."""
        pass

    @portal_group.command(name="addchannel")
    async def portal_addchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Allow portal relays in this channel."""
        async with self.config.guild(ctx.guild).allowed_channels() as chans:
            if channel.id not in chans:
                chans.append(channel.id)
        await ctx.send(f"✅ Added {channel.mention} to portal channels.")

    @portal_group.command(name="removechannel")
    async def portal_removechannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Disallow portal relays in this channel."""
        async with self.config.guild(ctx.guild).allowed_channels() as chans:
            if channel.id in chans:
                chans.remove(channel.id)
        await ctx.send(f"🗑️ Removed {channel.mention} from portal channels.")

    @portal_group.command(name="list")
    async def portal_list(self, ctx: commands.Context):
        """Show portal settings for this guild."""
        conf = await self.config.guild(ctx.guild).all()
        chans = ", ".join(f"<#${cid}>".replace("$","") for cid in conf["allowed_channels"]) or "(none)"
        partners = "\n".join(f"Guild {gid}: {url}" for gid, url in conf["partners"].items()) or "(none)"
        banned = ", ".join(f"<@{uid}>" for uid in conf["banned_users"]) or "(none)"
        await ctx.send(
            f"**Allowed Channels:** {chans}\n**Partners:**\n{partners}\n**Banned:** {banned}\n**Reply Controls:** {'on' if conf.get('enable_replies', True) else 'off'}"
        )

    @portal_group.command(name="addpartner")
    async def portal_addpartner(self, ctx: commands.Context, partner_guild_id: int, webhook_url: str):
        """Add/update a partner guild's destination webhook URL."""
        async with self.config.guild(ctx.guild).partners() as partners:
            partners[str(partner_guild_id)] = webhook_url
        await ctx.send(f"🤝 Partner {partner_guild_id} set.")

    @portal_group.command(name="removepartner")
    async def portal_removepartner(self, ctx: commands.Context, partner_guild_id: int):
        """Remove a partner guild."""
        async with self.config.guild(ctx.guild).partners() as partners:
            partners.pop(str(partner_guild_id), None)
        await ctx.send(f"🗑️ Partner {partner_guild_id} removed.")

    @portal_group.command(name="ban")
    async def portal_ban(self, ctx: commands.Context, user: discord.User):
        """Ban a user from the portal (their messages won't be relayed)."""
        async with self.config.guild(ctx.guild).banned_users() as banned:
            if user.id not in banned:
                banned.append(user.id)
        await ctx.send(f"🚫 Banned {user.mention} from portal relays.")

    @portal_group.command(name="unban")
    async def portal_unban(self, ctx: commands.Context, user: discord.User):
        """Unban a user from the portal."""
        async with self.config.guild(ctx.guild).banned_users() as banned:
            if user.id in banned:
                banned.remove(user.id)
        await ctx.send(f"✅ Unbanned {user.mention} for portal relays.")

    @portal_group.command(name="toggleReplies")
    async def portal_toggle_replies(self, ctx: commands.Context):
        """Toggle the small Reply controls under mirrored messages."""
        cur = await self.config.guild(ctx.guild).enable_replies()
        await self.config.guild(ctx.guild).enable_replies().set(not cur)
        await ctx.send(f"💬 Reply controls are now {'enabled' if not cur else 'disabled'}.")

    # -------------------- REPLY CONTROLLER --------------------
    async def launch_reply_modal(self, interaction: discord.Interaction, origin_payload: dict):
        modal = ReplyModal(self, origin_payload)
        await interaction.response.send_modal(modal)

    async def handle_reply_submit(self, interaction: discord.Interaction, origin_payload: dict, reply_text: str):
        # Find partner webhooks of *this* guild to fan-out the reply
        guild = interaction.guild
        if not guild:
            return
        conf = await self.config.guild(guild).all()
        partners: Dict[str, str] = conf["partners"]
        if not partners:
            await interaction.followup.send("No partners configured for this server.", ephemeral=True)
            return

        # Impersonate the replier
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        username = (self._display_name(member) if member else interaction.user.display_name)
        avatar_url = interaction.user.display_avatar.url if interaction.user else None

        # Sanitize reply
        reply_text = self._sanitize_content(reply_text)

        # Build reference hint to show what we're replying to
        ref_author = origin_payload.get("origin_author_name", "someone")
        excerpt = origin_payload.get("origin_excerpt", "")
        hint = f"Replying to {ref_author}: '{excerpt}'" if excerpt else f"Replying to {ref_author}"

        successes = 0
        for _gid, webhook_url in partners.items():
            msg = await self._send_via_webhook(
                webhook_url=webhook_url,
                content=reply_text,
                username=username,
                avatar_url=avatar_url,
                reference_hint=hint,
            )
            if msg:
                successes += 1

        if successes:
            await interaction.followup.send(f"Sent reply across the portal to {successes} destination(s).", ephemeral=True)
        else:
            await interaction.followup.send("Failed to send reply.", ephemeral=True)

# -------------------- UI COMPONENTS --------------------
class ReplyController(discord.ui.View):
    def __init__(self, cog: CrossPortal, origin_payload: dict, *, timeout: Optional[float] = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.origin_payload = origin_payload

        self.add_item(ReplyButton(cog, origin_payload))

class ReplyButton(discord.ui.Button):
    def __init__(self, cog: CrossPortal, origin_payload: dict):
        super().__init__(label="Reply", style=discord.ButtonStyle.primary, custom_id=f"portal_reply:{origin_payload.get('origin_message_id','0')}")
        self.cog = cog
        self.origin_payload = origin_payload

    async def callback(self, interaction: discord.Interaction):
        # Anyone can reply; adjust to checks if needed
        await self.cog.launch_reply_modal(interaction, self.origin_payload)

class ReplyModal(discord.ui.Modal, title="Portal Reply"):
    def __init__(self, cog: CrossPortal, origin_payload: dict):
        super().__init__()
        self.cog = cog
        self.origin_payload = origin_payload
        self.reply_input = discord.ui.TextInput(label="Your reply", style=discord.TextStyle.paragraph, max_length=1800, required=True)
        self.add_item(self.reply_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.cog.handle_reply_submit(interaction, self.origin_payload, str(self.reply_input.value))

# -------------------- SETUP --------------------
async def setup(bot):
    await bot.add_cog(CrossPortal(bot))
