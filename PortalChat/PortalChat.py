from __future__ import annotations
import asyncio
from typing import Dict, List, Optional, Tuple

import discord
from discord import AllowedMentions
from redbot.core import commands, Config, checks
from redbot.core.bot import Red


class PortalChat(commands.Cog):
    """
    Link messages from one channel to another (even across servers) using webhooks.

    • Create a link from a *source* channel to a *destination* channel.
    • The cog creates (or uses) a webhook in the destination channel.
    • Messages in the source are re-posted to the destination via the webhook
      with the original author's display name and avatar.

    Notes & Permissions:
    - Bot needs: Read Messages, Read Message History in the source channel.
    - In the destination channel: Manage Webhooks, Send Messages, Attach Files, Embed Links.
    - We ignore messages created by webhooks to prevent loops.
    - Mentions are sanitized (no pings) by default.
    """

    __author__ = "you"
    __version__ = "1.0.0"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xC0FFEE10, force_registration=True)
        # A list of link objects stored globally, since links can span guilds
        # link schema: {
        #   "source_channel_id": int,
        #   "dest_channel_id": int,
        #   "webhook_id": Optional[int],
        #   "webhook_url": Optional[str]
        # }
        self.config.register_global(links=[])
        self._lock = asyncio.Lock()

    # -----------------------------
    # Utilities
    # -----------------------------

    async def _get_links(self) -> List[dict]:
        return await self.config.links()

    async def _set_links(self, links: List[dict]) -> None:
        await self.config.links.set(links)

    async def _find_link(self, source_id: int, dest_id: int) -> Optional[dict]:
        links = await self._get_links()
        for l in links:
            if l.get("source_channel_id") == source_id and l.get("dest_channel_id") == dest_id:
                return l
        return None

    async def _find_links_from_source(self, source_id: int) -> List[dict]:
        return [l for l in await self._get_links() if l.get("source_channel_id") == source_id]

    async def _ensure_webhook(self, dest_channel: discord.TextChannel) -> Tuple[int, str]:
        """Create a webhook in the destination channel if needed. Returns (id, url)."""
        # Try to reuse an existing webhook owned by this bot if present.
        try:
            hooks = await dest_channel.webhooks()
        except discord.Forbidden:
            raise commands.UserFeedbackCheckFailure(
                "I can't access webhooks in the destination channel. I need 'Manage Webhooks'."
            )
        for wh in hooks:
            if wh.user and wh.user.id == self.bot.user.id:
                return wh.id, wh.url
        # Create new webhook
        try:
            wh = await dest_channel.create_webhook(name="PortalChat", reason="Channel link relay")
            return wh.id, wh.url
        except discord.Forbidden:
            raise commands.UserFeedbackCheckFailure(
                "I wasn't able to create a webhook. Do I have 'Manage Webhooks' in the destination?"
            )

    async def _send_via_webhook(
        self,
        webhook_url: str,
        content: str | None,
        username: str,
        avatar_url: Optional[str],
        files: List[discord.File] | None = None,
        embeds: List[discord.Embed] | None = None,
    ) -> None:
        # Use Red's shared aiohttp session
        async with self.bot.http_session as session:
            wh = discord.Webhook.from_url(webhook_url, session=session)
            await wh.send(
                content=content,
                username=username,
                avatar_url=avatar_url,
                files=files or None,
                embeds=embeds or None,
                allowed_mentions=AllowedMentions.none(),
                wait=False,
            )

    # -----------------------------
    # Listener
    # -----------------------------

    @commands.Cog.listener("on_message")
    async def relay_message(self, message: discord.Message):
        # Basic filters
        if message.author.bot:
            # Webhooks are bot-like; we'll further exclude webhook messages explicitly below.
            pass
        # Don't relay DMs or system messages
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            return
        if message.webhook_id is not None:
            # Never relay webhook messages (prevents echo loops)
            return

        links = await self._find_links_from_source(message.channel.id)
        if not links:
            return

        # Build content and gather files/embeds
        content = message.content or None
        files: List[discord.File] = []
        try:
            for attachment in message.attachments:
                files.append(await attachment.to_file())
        except Exception:
            # If any file fails, still try to send others
            pass

        # Use only safe-to-forward embeds (discord.Embed instances already are)
        embeds: List[discord.Embed] = []
        try:
            for e in message.embeds:
                # Only forward rich/message embeds; skip unknown types if desired
                embeds.append(e)
        except Exception:
            pass

        avatar_url = str(message.author.display_avatar.url) if message.author.display_avatar else None
        username = message.author.display_name

        # Relay to each destination
        for link in links:
            webhook_url = link.get("webhook_url")
            dest_id = link.get("dest_channel_id")

            # Validate destination still exists
            dest_channel = self.bot.get_channel(dest_id)
            if dest_channel is None:
                # Skip silently; admin can clean stale links
                continue

            try:
                await self._send_via_webhook(
                    webhook_url=webhook_url,
                    content=content,
                    username=username,
                    avatar_url=avatar_url,
                    files=files.copy() if files else None,
                    embeds=embeds.copy() if embeds else None,
                )
            except discord.HTTPException:
                # If webhook is invalid (deleted/unauthorized), try to recreate once
                try:
                    wh_id, wh_url = await self._ensure_webhook(dest_channel)
                except commands.UserFeedbackCheckFailure:
                    continue
                # Update stored webhook and retry
                async with self._lock:
                    all_links = await self._get_links()
                    for l in all_links:
                        if l.get("source_channel_id") == link["source_channel_id"] and l.get("dest_channel_id") == dest_id:
                            l["webhook_id"] = wh_id
                            l["webhook_url"] = wh_url
                    await self._set_links(all_links)
                try:
                    await self._send_via_webhook(
                        webhook_url=wh_url,
                        content=content,
                        username=username,
                        avatar_url=avatar_url,
                        files=files.copy() if files else None,
                        embeds=embeds.copy() if embeds else None,
                    )
                except Exception:
                    # Give up for this destination
                    continue

    # -----------------------------
    # Commands
    # -----------------------------

    @commands.group(name="linkch")
    @checks.admin_or_permissions(manage_guild=True)
    async def linkch(self, ctx: commands.Context):
        """Manage channel links (source -> destination)."""
        pass

    @linkch.command(name="add")
    async def linkch_add(
        self,
        ctx: commands.Context,
        source: discord.TextChannel,
        destination: discord.TextChannel,
    ):
        """Link messages from **source** channel to **destination** channel.

        Example: `[p]linkch add #from-here #to-there`
        You can reference channels in other servers by ID.
        """
        # Basic sanity checks
        if source.id == destination.id:
            return await ctx.send("Source and destination cannot be the same channel.")

        # Ensure webhook exists/usable in destination
        try:
            wh_id, wh_url = await self._ensure_webhook(destination)
        except commands.UserFeedbackCheckFailure as e:
            return await ctx.send(str(e))

        async with self._lock:
            links = await self._get_links()
            if any(l for l in links if l["source_channel_id"] == source.id and l["dest_channel_id"] == destination.id):
                return await ctx.send("That link already exists.")
            links.append(
                {
                    "source_channel_id": source.id,
                    "dest_channel_id": destination.id,
                    "webhook_id": wh_id,
                    "webhook_url": wh_url,
                }
            )
            await self._set_links(links)

        await ctx.send(
            f"✅ Linked {source.mention} → {destination.mention}. Messages in the source will mirror to the destination."
        )

    @linkch.command(name="remove")
    async def linkch_remove(
        self,
        ctx: commands.Context,
        source: discord.TextChannel,
        destination: discord.TextChannel,
    ):
        """Remove an existing link from **source** to **destination**."""
        async with self._lock:
            links = await self._get_links()
            new_links = [l for l in links if not (l["source_channel_id"] == source.id and l["dest_channel_id"] == destination.id)]
            if len(new_links) == len(links):
                return await ctx.send("No such link was found.")
            await self._set_links(new_links)
        await ctx.send(f"🗑️ Removed link {source.mention} → {destination.mention}.")

    @linkch.command(name="list")
    async def linkch_list(self, ctx: commands.Context):
        """List all active links."""
        links = await self._get_links()
        if not links:
            return await ctx.send("No links configured.")
        lines = []
        for l in links:
            s = self.bot.get_channel(l["source_channel_id"]) or f"<#{l['source_channel_id']}>"
            d = self.bot.get_channel(l["dest_channel_id"]) or f"<#{l['dest_channel_id']}>"
            lines.append(f"• {getattr(s, 'mention', s)} → {getattr(d, 'mention', d)}")
        await ctx.send("**Active links:**\n" + "\n".join(lines))

    @linkch.command(name="clearbroken")
    async def linkch_clearbroken(self, ctx: commands.Context):
        """Remove links whose destination channels are no longer accessible."""
        async with self._lock:
            links = await self._get_links()
            kept = []
            removed = []
            for l in links:
                if self.bot.get_channel(l["dest_channel_id"]) is None:
                    removed.append(l)
                else:
                    kept.append(l)
            await self._set_links(kept)
        await ctx.send(f"Removed {len(removed)} broken link(s). Kept {len(kept)}.")


async def setup(bot: Red) -> None:
    await bot.add_cog(PortalChat(bot))
