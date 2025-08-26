# portalchat.py
from __future__ import annotations
import re
from typing import Dict, List, Optional

import discord
from redbot.core import commands, checks, Config  # <-- use Red's commands.Cog

MENTION_RE = re.compile(r"<@!?\d+>|<@&\d+>|@everyone|@here")

__all__ = ["PortalChat"]

class PortalChat(commands.Cog):  # <-- inherits from redbot.core.commands.Cog
    """Cross-server portal chat using webhooks, with admin controls and reply buttons."""

    default_guild = {
        "allowed_channels": [],
        "partners": {},          # {str_guild_id: webhook_url}
        "banned_users": [],
        "enable_replies": True,
    }
    default_global = {"message_map": {}}

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xC0FFEE77B07)
        self.config.register_guild(**self.default_guild)
        self.config.register_global(**self.default_global)

    @staticmethod
    def _display_name(member: discord.Member) -> str:
        base = member.nick or member.name
        guild_name = member.guild.name
        combo = f"{base} ~ {guild_name}"
        return combo if len(combo) <= 80 else combo[:77] + "…"

    @staticmethod
    def _sanitize_content(text: str) -> str:
        def repl(m: re.Match) -> str:
            return m.group(0).replace("@", "@\u200b")
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
            if reference_hint:
                content = f"↪️ {reference_hint}\n{content}" if content else f"↪️ {reference_hint}"
            return await wh.send(
                content=content or None,
                username=username,
                avatar_url=avatar_url,
                wait=True,
                allowed_mentions=self._allowed_mentions(),
                files=files or None,
                embeds=embeds or None,
            )
        except Exception:
            return None

    async def _post_reply_controls(self, channel: discord.TextChannel, origin_payload: dict):
        view = ReplyController(self, origin_payload)
        try:
            await channel.send(
                content=f"Reply to **{origin_payload.get('origin_author_name','someone')}**'s message above:",
                view=view,
                allowed_mentions=self._allowed_mentions(),
            )
        except Exception:
            pass

    # -------- Listeners --------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if message.channel.id not in guild_conf["allowed_channels"]:
            return
        if message.author.id in set(guild_conf["banned_users"]):
            return

        username = self._display_name(message.author)
        avatar_url = message.author.display_avatar.url if message.author.display_avatar else None

        content = self._sanitize_content(message.content or "")

        attach_lines = []
        for a in message.attachments:
            safe_name = self._sanitize_content(a.filename)
            attach_lines.append(f"[Attachment: {safe_name}] {a.url}")
        if attach_lines:
            content = (content + "\n" if content else "") + "\n".join(attach_lines)

        partners: Dict[str, str] = guild_conf["partners"]
        if not partners:
            return

        origin_hint = {
            "origin_guild_id": message.guild.id,
            "origin_channel_id": message.channel.id,
            "origin_message_id": message.id,
            "origin_author_id": message.author.id,
            "origin_author_name": username,
            "origin_excerpt": (message.content[:100] + "…") if message.content and len(message.content) > 100 else (message.content or ""),
        }

        for _, webhook_url in partners.items():
            mirrored = await self._send_via_webhook(
                webhook_url=webhook_url,
                content=content,
                username=username,
                avatar_url=avatar_url,
                embeds=None,
            )
            if not mirrored:
                continue

            try:
                async with self.config.message_map() as mmap:
                    mmap[str(mirrored.id)] = origin_hint
            except Exception:
                pass

            if guild_conf.get("enable_replies", True) and isinstance(mirrored.channel, discord.TextChannel):
                await self._post_reply_controls(mirrored.channel, origin_hint)

    # -------- Admin commands --------
    @commands.group(name="portal")
    @commands.guild_only()
    @checks.admin()
    async def portal_group(self, ctx: commands.Context):
        """Configure the cross-server portal."""
        pass

    @portal_group.command(name="addchannel")
    async def portal_addchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with self.config.guild(ctx.guild).allowed_channels() as chans:
            if channel.id not in chans:
                chans.append(channel.id)
        await ctx.send(f"✅ Added {channel.mention} to portal channels.")

    @portal_group.command(name="removechannel")
    async def portal_removechannel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with self.config.guild(ctx.guild).allowed_channels() as chans:
            if channel.id in chans:
                chans.remove(channel.id)
        await ctx.send(f"🗑️ Removed {channel.mention} from portal channels.")

    @portal_group.command(name="list")
    async def portal_list(self, ctx: commands.Context):
        conf = await self.config.guild(ctx.guild).all()
        chans = ", ".join(f"<#{cid}>" for cid in conf["allowed_channels"]) or "(none)"
        partners = "\n".join(f"Guild {gid}: {url}" for gid, url in conf["partners"].items()) or "(none)"
        banned = ", ".join(f"<@{uid}>" for uid in conf["banned_users"]) or "(none)"
        await ctx.send(
            f"**Allowed Channels:** {chans}\n"
            f"**Partners:**\n{partners}\n"
            f"**Banned:** {banned}\n"
            f"**Reply Controls:** {'on' if conf.get('enable_replies', True) else 'off'}"
        )

    @portal_group.command(name="addpartner")
    async def portal_addpartner(self, ctx: commands.Context, partner_guild_id: int, webhook_url: str):
        async with self.config.guild(ctx.guild).partners() as partners:
            partners[str(partner_guild_id)] = webhook_url
        await ctx.send(f"🤝 Partner {partner_guild_id} set.")

    @portal_group.command(name="removepartner")
    async def portal_removepartner(self, ctx: commands.Context, partner_guild_id: int):
        async with self.config.guild(ctx.guild).partners() as partners:
            partners.pop(str(partner_guild_id), None)
        await ctx.send(f"🗑️ Partner {partner_guild_id} removed.")

    @portal_group.command(name="ban")
    async def portal_ban(self, ctx: commands.Context, user: discord.User):
        async with self.config.guild(ctx.guild).banned_users() as banned:
            if user.id not in banned:
                banned.append(user.id)
        await ctx.send(f"🚫 Banned {user.mention} from portal relays.")

    @portal_group.command(name="unban")
    async def portal_unban(self, ctx: commands.Context, user: discord.User):
        async with self.config.guild(ctx.guild).banned_users() as banned:
            if user.id in banned:
                banned.remove(user.id)
        await ctx.send(f"✅ Unbanned {user.mention} for portal relays.")

    @portal_group.command(name="togglereplies")
    async def portal_toggle_replies(self, ctx: commands.Context):
        cur = await self.config.guild(ctx.guild).enable_replies()
        await self.config.guild(ctx.guild).enable_replies().set(not cur)
        await ctx.send(f"💬 Reply controls are now {'enabled' if not cur else 'disabled'}.")


# ---- UI Components ----
class ReplyController(discord.ui.View):
    def __init__(self, cog: PortalChat, origin_payload: dict, *, timeout: Optional[float] = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.origin_payload = origin_payload
        self.add_item(ReplyButton(cog, origin_payload))

class ReplyButton(discord.ui.Button):
    def __init__(self, cog: PortalChat, origin_payload: dict):
        super().__init__(label="Reply", style=discord.ButtonStyle.primary, custom_id=f"portal_reply:{origin_payload.get('origin_message_id','0')}")
        self.cog = cog
        self.origin_payload = origin_payload

    async def callback(self, interaction: discord.Interaction):
        await self.cog.launch_reply_modal(interaction, self.origin_payload)

class ReplyModal(discord.ui.Modal, title="Portal Reply"):
    def __init__(self, cog: PortalChat, origin_payload: dict):
        super().__init__()
        self.cog = cog
        self.origin_payload = origin_payload
        self.reply_input = discord.ui.TextInput(label="Your reply", style=discord.TextStyle.paragraph, max_length=1800, required=True)
        self.add_item(self.reply_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.cog.handle_reply_submit(interaction, self.origin_payload, str(self.reply_input.value))

# Methods the view calls:
async def setup(bot):  # kept for single-file testing, but package-style setup is below in __init__.py
    await bot.add_cog(PortalChat(bot))
