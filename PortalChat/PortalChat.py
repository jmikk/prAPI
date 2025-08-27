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
    Link messages cross-server via webhooks and sync reactions **both ways**.
    - Messages: Source channel → destination webhook (can be cross-server).
    - Reactions: Add/remove mirrored in both directions.
    - Loop safety: ignores reactions from any bot users; keeps a timestamped map; prunes regularly.
    """

    __author__ = "you"
    __version__ = "1.7.1"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xC0FFEE10, force_registration=True)
        # mapping: message_id -> {"c": counterpart_channel_id, "m": counterpart_message_id, "ts": unix_timestamp}
        self.config.register_global(links=[], mapping={}, max_age_days=7, max_map=5000)
        self._lock = asyncio.Lock()
        self.session: aiohttp.ClientSession | None = aiohttp.ClientSession()
        # Edit debug + dry-run (so you can test publicly without editing live webhook messages)
        self.edit_debug: bool = False
        self.edit_dry_run: bool = False
        # start periodic cleanup
        try:
            self._purge_old_mappings.start()
        except RuntimeError:
            pass

    async def _delete_counterpart_message(
        self,
        src_channel_id: int,
        dest_channel_id: int,
        dest_message_id: int,
        wh_url: Optional[str]
    ) -> None:
        """
        Try to delete the counterpart message, preferring webhook deletion when we have (or can rehydrate) the webhook.
        Falls back to standard deletion if the bot has permissions in the destination channel.
        """
        # Rehydrate webhook if missing
        if not wh_url:
            try:
                wh_url = await self._resolve_webhook_for_pair(src_channel_id, dest_channel_id)
            except Exception:
                wh_url = None

        # Try webhook deletion first (works only if the message was created by THIS webhook)
        if wh_url:
            try:
                if self.session is None or self.session.closed:
                    self.session = aiohttp.ClientSession()
                wh = discord.Webhook.from_url(wh_url, session=self.session)

                # If the message lives in a thread, pass thread_id for reliability
                dest_channel = self.bot.get_channel(dest_channel_id)
                thread_id = None
                if isinstance(dest_channel, (discord.Thread,)):
                    thread_id = dest_channel.id

                # discord.py supports thread_id kwarg for webhook message ops
                if thread_id:
                    await wh.delete_message(dest_message_id, thread_id=thread_id)
                else:
                    await wh.delete_message(dest_message_id)
                return
            except discord.NotFound:
                # Already gone; consider this a success
                return
            except Exception as e:
                if getattr(self, "edit_debug", False):
                    try:
                        owner = (await self.bot.application_info()).owner
                        await owner.send(f"🧹 Webhook delete failed for {dest_message_id}: {type(e).__name__}: {e}")
                    except Exception:
                        pass
                # fall back to standard deletion

        # Fallback: use bot perms to delete
        dest_channel = self.bot.get_channel(dest_channel_id)
        if not isinstance(dest_channel, discord.TextChannel) and not isinstance(dest_channel, discord.Thread):
            return
        try:
            msg = await dest_channel.fetch_message(dest_message_id)
        except Exception:
            return
        try:
            await msg.delete()
        except Exception as e:
            if getattr(self, "edit_debug", False):
                try:
                    owner = (await self.bot.application_info()).owner
                    await owner.send(f"🧹 Fallback delete failed for {dest_message_id}: {type(e).__name__}: {e}")
                except Exception:
                    pass

    # -----------------------------
    # Helpers
    # -----------------------------
    async def _get_links(self) -> List[dict]:
        return await self.config.links()

    async def _save_bidirectional_mapping(self, a_msg: discord.Message, b_msg: discord.Message, webhook_url: str):
        """
        Save a <-> mapping for message IDs, including the webhook URL used to create the
        destination message so we can later edit/delete via the webhook API.
        """
        now_ts = int(datetime.utcnow().timestamp())
        async with self._lock:
            mapping = await self.config.mapping()
            mapping[str(a_msg.id)] = {"c": b_msg.channel.id, "m": b_msg.id, "w": webhook_url, "ts": now_ts}
            mapping[str(b_msg.id)] = {"c": a_msg.channel.id, "m": a_msg.id, "w": webhook_url, "ts": now_ts}
            # size-based prune using config cap
            max_map = await self.config.max_map()
            if len(mapping) > max_map:
                items = sorted(mapping.items(), key=lambda kv: kv[1].get("ts", 0) if isinstance(kv[1], dict) else 0)
                drop = max(1, len(items) // 5)  # drop oldest ~20%
                for k, _ in items[:drop]:
                    mapping.pop(k, None)
            await self.config.mapping.set(mapping)

    async def _resolve_webhook_for_pair(self, src_channel_id: int, dest_channel_id: int) -> Optional[str]:
        """
        Try to find the correct webhook URL for (source channel -> destination channel)
        by checking known links for the source and fetching their webhook to compare channel_id.
        """
        try:
            links = await self._get_links()
            candidates = [l.get("webhook_url") for l in links
                          if l.get("source_channel_id") == src_channel_id and l.get("webhook_url")]
            if not candidates:
                return None
    
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()
    
            for url in candidates:
                try:
                    wh = discord.Webhook.from_url(url, session=self.session)
                    # Fetch full webhook to get its channel_id
                    full = await wh.fetch()
                    if getattr(full, "channel_id", None) == dest_channel_id:
                        return url
                except Exception:
                    continue
        except Exception:
            pass
        return None

    @commands.Cog.listener("on_raw_message_delete")
    async def mirror_delete(self, payload: discord.RawMessageDeleteEvent):
        """
        When a message is deleted in either linked channel, delete its counterpart.
        Uses the mapping to find the other side. Removes both mapping entries first
        to avoid ping-pong.
        """
        # Ignore system/Guildless cases are fine; we only rely on IDs here.
        try:
            async with self._lock:
                mapping = await self.config.mapping()
                val = mapping.pop(str(payload.message_id), None)

                # Nothing to mirror
                if not val:
                    await self.config.mapping.set(mapping)
                    return

                # Prepare to also drop the counterpart's reverse entry
                try:
                    counterpart_key = str(val["m"] if isinstance(val, dict) else val[1])
                    mapping.pop(counterpart_key, None)
                except Exception:
                    pass

                await self.config.mapping.set(mapping)

            # With mapping removed, we can safely delete the counterpart (no loops)
            dest_channel_id = val["c"] if isinstance(val, dict) else val[0]
            dest_message_id = val["m"] if isinstance(val, dict) else val[1]
            wh_url = val.get("w") if isinstance(val, dict) else None

            await self._delete_counterpart_message(
                src_channel_id=payload.channel_id,
                dest_channel_id=dest_channel_id,
                dest_message_id=dest_message_id,
                wh_url=wh_url,
            )

        except Exception:
            # Silent fail to avoid noisy logs; your edit_debug flag only covers edits.
            pass



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
            wait=True,
        )

    def _is_bot_user(self, guild_id: Optional[int], user_id: int) -> bool:
        if user_id == self.bot.user.id:
            return True
        if guild_id:
            guild = self.bot.get_guild(guild_id)
            if guild:
                member = guild.get_member(user_id)
                if member:
                    return bool(member.bot)
        # Fallback: unknown user; treat as non-bot
        return False

    # -----------------------------
    # Message relay
    # -----------------------------
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
        
            for attachment in message.attachments:
                if attachment.filename.lower().endswith(".gif"):
                    embeds.append(discord.Embed().set_image(url=attachment.url))
                else:
                    files.append(await attachment.to_file())
        except Exception:
            pass

        if not content and not files and not embeds:
            return

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
                    await self._save_bidirectional_mapping(message, relayed_msg, webhook_url)
            except Exception as e:
                owner = (await self.bot.application_info()).owner
                try:
                    await owner.send(f"❌ Failed to send message to webhook in {message.channel.mention}: {type(e).__name__}: {e}")
                except Exception:
                    pass

    # -----------------------------
    # Edit mirroring (source -> destination webhook)
    # -----------------------------
    @commands.Cog.listener("on_message_edit")
    async def mirror_edit(self, before: discord.Message, after: discord.Message):
        # Filters
        reason_skip = None
        if after.author.bot:
            reason_skip = "author is a bot"
        elif after.webhook_id is not None:
            reason_skip = "message is a webhook"
        elif not after.guild:
            reason_skip = "DM message"

        owner = (await self.bot.application_info()).owner if getattr(self, "edit_debug", False) else None
        if reason_skip:
            if owner and self.edit_debug:
                try:
                    await owner.send(f"📝 EDIT skip: {reason_skip} in #{after.channel} | msg {after.id}")
                except Exception:
                    pass
            return

        mapping = await self.config.mapping()
        val = mapping.get(str(after.id))
        if not val:
            if owner and self.edit_debug:
                try:
                    await owner.send(f"📝 EDIT: no mapping for source msg {after.id} in #{after.channel}")
                except Exception:
                    pass
            return

        wh_url = val.get("w") if isinstance(val, dict) else None
        if not wh_url:
            # Try to re-hydrate the webhook URL from links based on destination channel
            dest_channel_id = val["c"] if isinstance(val, dict) else val[0]
            wh_url = await self._resolve_webhook_for_pair(after.channel.id, dest_channel_id)
        
            if wh_url:
                # Save back into mapping for future edits
                try:
                    async with self._lock:
                        mapping = await self.config.mapping()
                        entry = mapping.get(str(after.id), {})
                        if isinstance(entry, dict):
                            entry["w"] = wh_url
                            entry["ts"] = int(datetime.utcnow().timestamp())
                            mapping[str(after.id)] = entry
                            await self.config.mapping.set(mapping)
                    if owner and self.edit_debug:
                        try:
                            await owner.send(f"📝 EDIT: rehydrated webhook URL for source msg {after.id}")
                        except Exception:
                            pass
                except Exception:
                    pass
            else:
                if owner and self.edit_debug:
                    try:
                        await owner.send(
                            f"📝 EDIT: mapping found but no webhook URL for source msg {after.id} "
                            f"and could not resolve from links."
                        )
                    except Exception:
                        pass
                return


        new_content = after.content or None
        new_embeds: List[discord.Embed] = []
        try:
            for e in after.embeds:
                new_embeds.append(e)
        except Exception:
            pass

        if owner and self.edit_debug:
            try:
                preview = (new_content[:120] + "…") if (new_content and len(new_content) > 123) else (new_content or "<no content>")
                await owner.send("".join([
                        "🧪 EDIT DEBUG (dry-run=" + str(self.edit_dry_run) + ")",
                        f"source: #{after.channel} / msg {after.id}",
                        f"dest:   msg {val['m']}",
                        f"embeds: {len(new_embeds)}",
                        f"content preview: {preview}",
                        f"webhook: {wh_url[:60]}...",
                    ])
                )
            except Exception:
                pass

        if getattr(self, "edit_dry_run", False):
            # Do not actually edit the webhook while testing publicly
            return

        # Perform actual webhook edit
        try:
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()
            wh = discord.Webhook.from_url(wh_url, session=self.session)
            await wh.edit_message(val["m"], content=new_content, embeds=new_embeds or [])
        except Exception as e:
            if owner and self.edit_debug:
                try:
                    await owner.send(f"❌ EDIT: failed to edit dest msg {val['m']} for source {after.id}: {type(e).__name__}: {e}")
                except Exception:
                    pass

    # -----------------------------
    # Reaction mirroring (bi-directional)
    # -----------------------------
    @commands.Cog.listener("on_raw_reaction_add")
    async def relay_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignore any bot reactions to avoid loops across multiple bots
        if self._is_bot_user(payload.guild_id, payload.user_id):
            return
        mapping = await self.config.mapping()
        val = mapping.get(str(payload.message_id))
        if not val:
            return
        dest_channel = self.bot.get_channel(val["c"]) if isinstance(val, dict) else self.bot.get_channel(val[0])
        dest_msg_id = val["m"] if isinstance(val, dict) else val[1]
        if not dest_channel:
            return
        try:
            msg = await dest_channel.fetch_message(dest_msg_id)
            # Add reaction if it's not already present with at least one count
            # (Discord dedups add_reaction calls, but this is cheap)
            await msg.add_reaction(payload.emoji)
        except Exception:
            pass

    @commands.Cog.listener("on_raw_reaction_remove")
    async def relay_reaction_remove(self, payload: discord.RawReactionActionEvent):
        # Ignore bot-originated removals (rare, but keep symmetry)
        if self._is_bot_user(payload.guild_id, payload.user_id):
            return
        mapping = await self.config.mapping()
        val = mapping.get(str(payload.message_id))
        if not val:
            return
        dest_channel = self.bot.get_channel(val["c"]) if isinstance(val, dict) else self.bot.get_channel(val[0])
        dest_msg_id = val["m"] if isinstance(val, dict) else val[1]
        if not dest_channel:
            return
        try:
            # Only remove the mirrored reaction if the source no longer has that emoji at all
            try:
                if payload.guild_id and payload.channel_id:
                    src_channel = self.bot.get_channel(payload.channel_id)
                    if src_channel:
                        src_msg = await src_channel.fetch_message(payload.message_id)
                        if any(str(r.emoji) == str(payload.emoji) for r in src_msg.reactions):
                            return  # still present in source; keep mirrored reaction
            except Exception:
                pass

            msg = await dest_channel.fetch_message(dest_msg_id)
            await msg.remove_reaction(payload.emoji, self.bot.user)
        except Exception:
            pass

    # -----------------------------
    # Admin commands
    # -----------------------------
    @commands.group(name="portal")
    @checks.admin_or_permissions(manage_guild=True)
    async def portal(self, ctx: commands.Context):
        """Manage portal links (source -> destination webhook)."""
        pass

    @portal.command(name="add")
    async def portal_add(self, ctx: commands.Context, source: discord.TextChannel, webhook_url: str):
        async with self._lock:
            links = await self._get_links()
            if any(l for l in links if l["source_channel_id"] == source.id and l["webhook_url"] == webhook_url):
                return await ctx.send("That link already exists.")
            links.append({"source_channel_id": source.id, "webhook_url": webhook_url})
            await self._set_links(links)
        await ctx.send(f"✅ Linked {source.mention} → {webhook_url}.")

    @portal.command(name="remove")
    async def portal_remove(self, ctx: commands.Context, source: discord.TextChannel, webhook_url: str):
        async with self._lock:
            links = await self._get_links()
            new_links = [l for l in links if not (l["source_channel_id"] == source.id and l["webhook_url"] == webhook_url)]
            if len(new_links) == len(links):
                return await ctx.send("No such link was found.")
            await self._set_links(new_links)
        await ctx.send(f"🗑️ Removed link {source.mention} → {webhook_url}.")

    @portal.command(name="list")
    async def portal_list(self, ctx: commands.Context):
        """Send the configured portal links to the bot owner via DM."""
        links = await self._get_links()
        if not links:
            return await ctx.send("No links configured.")

        lines = []
        for l in links:
            s = self.bot.get_channel(l["source_channel_id"]) or f"<#{l['source_channel_id']}>"
            d = l["webhook_url"]
            lines.append(f"• {getattr(s, 'mention', s)} → {d}")

        owner = (await self.bot.application_info()).owner
        msg = "**Active portal links:**\n" + "\n".join(lines)

        try:
            await owner.send(msg)
            await ctx.send("📬 Sent the portal list to the bot owner.")
        except discord.Forbidden:
            await ctx.send("❌ Could not DM the bot owner. Do they have DMs disabled?")


    @portal.command(name="editdebug")
    async def portal_editdebug(self, ctx: commands.Context, mode: bool):
        """Enable/disable owner DM debug logs for edit mirroring (default: on)."""
        self.edit_debug = mode
        await ctx.send(f"Edit debug {'enabled' if mode else 'disabled'}.")

    @portal.command(name="editdryrun")
    async def portal_editdryrun(self, ctx: commands.Context, mode: bool):
        """Toggle dry-run for edit mirroring (no webhook edits when on)."""
        self.edit_dry_run = mode
        await ctx.send(f"Edit dry-run {'enabled' if mode else 'disabled'}.")

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

    # -----------------------------
    # Housekeeping
    # -----------------------------
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
                # tuples are treated as stale and dropped
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
