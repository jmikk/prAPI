from __future__ import annotations
import asyncio
from typing import Dict, List, Optional

import aiohttp

import discord
from discord import AllowedMentions
from redbot.core import commands, Config, checks
from redbot.core.bot import Red


class PortalChat(commands.Cog):
    """
    Link messages from one channel to another (even across servers) using webhooks.

    • Create a link from a *source* channel to a *destination webhook*.
    • The cog stores the webhook in the destination.
    • Messages in the source are re-posted to the destination via the webhook
      with the original author's display name and avatar.

    Notes & Permissions:
    - Bot needs: Read Messages, Read Message History in the source channel.
    - In the destination channel: Manage Webhooks, Send Messages, Attach Files, Embed Links.
    - We ignore messages created by webhooks to prevent loops.
    - Mentions are sanitized (no pings) by default.
    """

    __author__ = "you"
    __version__ = "1.3.1"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xC0FFEE10, force_registration=True)
        self.config.register_global(links=[])
        self._lock = asyncio.Lock()
        # dedicated aiohttp session for webhooks
        self.session: aiohttp.ClientSession | None = aiohttp.ClientSession()

    async def _get_links(self) -> List[dict]:
        return await self.config.links()

    async def _set_links(self, links: List[dict]) -> None:
        await self.config.links.set(links)

    async def _find_links_from_source(self, source_id: int) -> List[dict]:
        return [l for l in await self._get_links() if l.get("source_channel_id") == source_id]

    async def _send_via_webhook(
        self,
        webhook_url: str,
        content: str | None,
        username: str,
        avatar_url: Optional[str],
        files: List[discord.File] | None = None,
        embeds: List[discord.Embed] | None = None,
    ) -> None:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        wh = discord.Webhook.from_url(webhook_url, session=self.session)
            await wh.send(
                content=content,
                username=username,
                avatar_url=avatar_url,
                files=files or None,
                embeds=embeds or None,
                allowed_mentions=AllowedMentions.none(),
                wait=False,
            )

    @commands.Cog.listener("on_message")
    async def relay_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            return
        if message.webhook_id is not None:
            return

        links = await self._find_links_from_source(message.channel.id)
        if not links:
            return

        content = message.content or None
        files: List[discord.File] = []
        try:
            for attachment in message.attachments:
                files.append(await attachment.to_file())
        except Exception as e:
            await message.channel.send(f"⚠️ Failed to fetch some attachments: {e}")

        embeds: List[discord.Embed] = []
        try:
            for e in message.embeds:
                embeds.append(e)
        except Exception as e:
            await message.channel.send(f"⚠️ Failed to process some embeds: {e}")

        avatar_url = str(message.author.display_avatar.url) if message.author.display_avatar else None
        username = message.author.display_name

        for link in links:
            webhook_url = link.get("webhook_url")
            if not webhook_url:
                await message.channel.send("❌ No webhook URL configured for this link.")
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
                await message.channel.send(f"✅ Message relayed to webhook {webhook_url[:60]}...")
            except Exception as e:
                await message.channel.send(f"❌ Failed to send message to webhook: {e}")

    @commands.group(name="portal")
    @checks.admin_or_permissions(manage_guild=True)
    async def portal(self, ctx: commands.Context):
        """Manage portal links (source -> destination webhook)."""
        pass

    @portal.command(name="add")
    async def portal_add(
        self,
        ctx: commands.Context,
        source: discord.TextChannel,
        webhook_url: str,
    ):
        """Link messages from **source** channel to a **destination webhook URL**.

        Example: `[p]portal add #from-here https://discord.com/api/webhooks/...`
        """
        async with self._lock:
            links = await self._get_links()
            if any(l for l in links if l["source_channel_id"] == source.id and l["webhook_url"] == webhook_url):
                return await ctx.send("That link already exists.")
            links.append(
                {
                    "source_channel_id": source.id,
                    "webhook_url": webhook_url,
                }
            )
            await self._set_links(links)

        await ctx.send(f"✅ Linked {source.mention} → {webhook_url}.")

    @portal.command(name="remove")
    async def portal_remove(
        self,
        ctx: commands.Context,
        source: discord.TextChannel,
        webhook_url: str,
    ):
        """Remove an existing portal link from **source** to **webhook URL**."""
        async with self._lock:
            links = await self._get_links()
            new_links = [l for l in links if not (l["source_channel_id"] == source.id and l["webhook_url"] == webhook_url)]
            if len(new_links) == len(links):
                return await ctx.send("No such link was found.")
            await self._set_links(new_links)
        await ctx.send(f"🗑️ Removed link {source.mention} → {webhook_url}.")

    @portal.command(name="list")
    async def portal_list(self, ctx: commands.Context):
        """List all active portal links."""
        links = await self._get_links()
        if not links:
            return await ctx.send("No links configured.")
        lines = []
        for l in links:
            s = self.bot.get_channel(l["source_channel_id"]) or f"<#{l['source_channel_id']}>"
            d = l["webhook_url"]
            lines.append(f"• {getattr(s, 'mention', s)} → {d}")
        await ctx.send("**Active portal links:**\n" + "\n".join(lines))

    @portal.command(name="clearbroken")
    async def portal_clearbroken(self, ctx: commands.Context):
        """Remove links whose source channels are no longer accessible."""
        async with self._lock:
            links = await self._get_links()
            kept = []
            removed = []
            for l in links:
                if self.bot.get_channel(l["source_channel_id"]) is None:
                    removed.append(l)
                else:
                    kept.append(l)
            await self._set_links(kept)
        await ctx.send(f"Removed {len(removed)} broken link(s). Kept {len(kept)}.")


async def setup(bot: Red) -> None:
    await bot.add_cog(PortalChat(bot))

async def teardown(bot: Red) -> None:
    cog = bot.get_cog("PortalChat")
    if cog and getattr(cog, "session", None):
        try:
            await cog.session.close()
        except Exception:
            pass

    
