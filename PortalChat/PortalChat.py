from __future__ import annotations
import asyncio
from typing import Dict, List, Optional

import discord
from discord import AllowedMentions
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import aiohttp
from discord.ext import tasks
from datetime import datetime, timedelta


class PortalChat(commands.Cog):
    """
    Link messages from one channel to another (even across servers) using webhooks.
    Also syncs reactions (add/remove) between source and destination messages.
    """

    __author__ = "you"
    __version__ = "1.5.0"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xC0FFEE10, force_registration=True)
        # mapping: original_msg_id -> {"c": dest_channel_id, "m": dest_msg_id, "ts": unix_timestamp}
        self.config.register_global(links=[], mapping={}, max_age_days=7, max_map=5000)
        self._lock = asyncio.Lock()
        self.session: aiohttp.ClientSession | None = aiohttp.ClientSession()
        # start periodic cleanup
        try:
            self._purge_old_mappings.start()
        except RuntimeError:
            pass

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
    ) -> Optional[discord.Message]:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        wh = discord.Webhook.from_url(webhook_url, session=self.session)
        return await wh.send(
            content=content,
            username=username,
            avatar_url=avatar_url,
            files=files or [],
            embeds=embeds or [],
            allowed_mentions=AllowedMentions.none(),
            wait=True,  # wait True so we get a Message back
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
        except Exception:
            pass

        embeds: List[discord.Embed] = []
        try:
            for e in message.embeds:
                embeds.append(e)
        except Exception:
            pass

        if not content and not files and not embeds:
            return

        # Format webhook username as Nickname (Server), trimmed to Discord limit (32)
        avatar_url = str(message.author.display_avatar.url) if message.author.display_avatar else None
        username = f"{message.author.display_name} ({message.guild.name})"
        if len(username) > 32:
            username = username[:32]

        for link in links:
            webhook_url = link.get("webhook_url")
            if not webhook_url:
                continue
            try:
                relayed_msg = await self._send_via_webhook(
                    webhook_url=webhook_url,
                    content=content,
                    username=username,
                    avatar_url=avatar_url,
                    files=files.copy() if files else None,
                    embeds=embeds.copy() if embeds else None,
                )
                if relayed_msg:
                    async with self._lock:
                        mapping = await self.config.mapping()
                        mapping[str(message.id)] = {
                            "c": relayed_msg.channel.id,
                            "m": relayed_msg.id,
                            "ts": int(datetime.utcnow().timestamp()),
                        }
                        # size-based prune using config cap
                        max_map = await self.config.max_map()
                        if len(mapping) > max_map:
                            items = sorted(mapping.items(), key=lambda kv: kv[1].get("ts", 0))
                            drop = max(1, len(items) // 5)  # drop oldest ~20%
                            for k, _ in items[:drop]:
                                mapping.pop(k, None)
                        await self.config.mapping.set(mapping)
            except Exception as e:
                owner = (await self.bot.application_info()).owner
                try:
                    await owner.send(f"❌ Failed to send message to webhook in {message.channel.mention}: {type(e).__name__}: {e}")
                except Exception:
                    pass

    @commands.Cog.listener("on_raw_reaction_add")
    async def relay_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignore the bot itself
        if payload.user_id == self.bot.user.id:
            return
        mapping = await self.config.mapping()
        key = str(payload.message_id)
        val = mapping.get(key)
        if not val:
            return
        if isinstance(val, dict):
            dest_channel_id, dest_msg_id = val["c"], val["m"]
        else:
            # backward compatibility with old tuple format
            dest_channel_id, dest_msg_id = val
        channel = self.bot.get_channel(dest_channel_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(dest_msg_id)
            await msg.add_reaction(payload.emoji)
        except Exception:
            pass

    @commands.Cog.listener("on_raw_reaction_remove")
    async def relay_reaction_remove(self, payload: discord.RawReactionActionEvent):
        mapping = await self.config.mapping()
        key = str(payload.message_id)
        val = mapping.get(key)
        if not val:
            return
        if isinstance(val, dict):
            dest_channel_id, dest_msg_id = val["c"], val["m"]
        else:
            dest_channel_id, dest_msg_id = val
        channel = self.bot.get_channel(dest_channel_id)
        if not channel:
            return
        try:
            # Only remove the mirrored reaction if the source no longer has that emoji
            try:
                source_channel = self.bot.get_channel(payload.channel_id)
                if source_channel:
                    source_msg = await source_channel.fetch_message(payload.message_id)
                    if any(str(r.emoji) == str(payload.emoji) for r in source_msg.reactions):
                        return  # still present in source; keep mirrored reaction
            except Exception:
                pass

            msg = await channel.fetch_message(dest_msg_id)
            await msg.remove_reaction(payload.emoji, self.bot.user)
        except Exception:
            pass

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
        async with self._lock:
            links = await self._get_links()
            if any(l for l in links if l["source_channel_id"] == source.id and l["webhook_url"] == webhook_url):
                return await ctx.send("That link already exists.")
            links.append({"source_channel_id": source.id, "webhook_url": webhook_url})
            await self._set_links(links)
        await ctx.send(f"✅ Linked {source.mention} → {webhook_url}.")

    @portal.command(name="remove")
    async def portal_remove(
        self,
        ctx: commands.Context,
        source: discord.TextChannel,
        webhook_url: str,
    ):
        async with self._lock:
            links = await self._get_links()
            new_links = [l for l in links if not (l["source_channel_id"] == source.id and l["webhook_url"] == webhook_url)]
            if len(new_links) == len(links):
                return await ctx.send("No such link was found.")
            await self._set_links(new_links)
        await ctx.send(f"🗑️ Removed link {source.mention} → {webhook_url}.")

    @portal.command(name="list")
    async def portal_list(self, ctx: commands.Context):
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

    # -------------
    # Housekeeping
    # -------------
    @tasks.loop(minutes=30)
    async def _purge_old_mappings(self):
        try:
            mapping = await self.config.mapping()
            if not mapping:
                return
            max_age_days = await self.config.max_age_days()
            cutoff = int((datetime.utcnow() - timedelta(days=max_age_days)).timestamp())
            # keep dict entries newer than cutoff; drop old tuple entries (no ts)
            new_map = {}
            for k, v in mapping.items():
                if isinstance(v, dict):
                    if v.get("ts", 0) >= cutoff:
                        new_map[k] = v
                # tuples are treated as stale and dropped to reclaim memory
            await self.config.mapping.set(new_map)
        except Exception:
            pass

    @_purge_old_mappings.before_loop
    async def _before_purge(self):
        await self.bot.wait_until_ready()

    def cog_unload(self):
        if hasattr(self, "_purge_old_mappings") and self._purge_old_mappings.is_running():
            self._purge_old_mappings.cancel()
        if self.session and not self.session.closed:
            try:
                asyncio.create_task(self.session.close())
            except Exception:
                pass


async def setup(bot: Red) -> None:
    await bot.add_cog(PortalChat(bot))

async def teardown(bot: Red) -> None:
    cog = bot.get_cog("PortalChat")
    if cog and getattr(cog, "session", None):
        try:
            await cog.session.close()
        except Exception:
            pass
