# redbot cog: channel_logger.py
# Exports "rendered-looking" Discord messages to plain .txt:
# - Uses msg.clean_content (resolves user/role/channel mentions to readable text)
# - Preserves Discord markdown as-is (bold, italics, code blocks, etc.)
# - Includes attachments as URLs
# - Supports: target channel (log a different channel than invocation), date range, chunking, off switch
#
# Commands:
#   /logchannel [target] [start] [end] [chunk_size] [safety_limit]
#   /logchanneloff
#
# Date formats (interpreted as UTC):
#   YYYY-MM-DD
#   YYYY-MM-DD HH:MM
#   YYYY-MM-DD HH:MM:SS
#   YYYY-MM-DDTHH:MM[:SS]

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional, Dict

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red


def _parse_date(date_str: str) -> datetime:
    s = date_str.strip().replace("T", " ")
    fmts = ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    raise ValueError("Invalid date format.")


class log(commands.Cog):
    __author__ = "ChatGPT"
    __version__ = "1.5.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=873214556122, force_registration=True)
        self.config.register_channel(is_exporting=False)

        # Cancel flags keyed by INVOCATION channel id (where you run /logchannel)
        self._cancel_flags: Dict[int, bool] = {}

    async def _format_message_block(self, msg: discord.Message) -> str:
        author_display = getattr(msg.author, "display_name", msg.author.name)
        author_id = msg.author.id

        created_utc = (
            msg.created_at.astimezone(timezone.utc)
            .replace(tzinfo=None)
            .isoformat(sep=" ", timespec="seconds")
        )

        header = f"{author_display} ({author_id}) | {created_utc} UTC\n"
        
        reply_info = ""
        ref = msg.reference
        
        if ref and ref.message_id:
            # 1. Try to get it from the internal cache first
            ref_obj = ref.cached_message
            
            # 2. If not in cache, try to fetch it from the API
            if not ref_obj:
                try:
                    # We use the channel the current message is in
                    ref_obj = await msg.channel.fetch_message(ref.message_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    ref_obj = None

            if ref_obj:
                ref_author = getattr(ref_obj.author, "display_name", "Unknown User")
                # Truncate preview to keep the text file readable
                preview = (ref_obj.clean_content[:50] + "...") if len(ref_obj.clean_content) > 50 else (ref_obj.clean_content or "[Embed/Image]")
                reply_info = f"-> Replying to {ref_author}: \"{preview}\"\n"
            else:
                reply_info = f"-> Replying to Message ID: {ref.message_id} (Message Deleted or Inaccessible)\n"

        content = msg.clean_content or ""
        block = header + reply_info + content + "\n"

        if msg.attachments:
            urls = " ".join(a.url for a in msg.attachments)
            block += f"[Attachments: {urls}]\n"

        if getattr(msg, "stickers", None) and msg.stickers:
            sticker_bits = " ".join(f"{s.name}({s.id})" for s in msg.stickers)
            block += f"[Stickers: {sticker_bits}]\n"

        block += f"[Jump: {msg.jump_url}]\n"
        block += "-" * 60 + "\n"
        return block

    async def _send_chunk(
        self,
        ctx: commands.Context,
        target_channel_id: int,
        chunk_index: int,
        chunk_count: int,
        txt_text: str,
    ) -> None:
        filename = f"channel_log_{target_channel_id}_chunk{chunk_index}.txt"
        data = txt_text.encode("utf-8", errors="replace")
        file_obj = discord.File(fp=io.BytesIO(data), filename=filename)

        await ctx.send(
            content=f"Uploaded chunk {chunk_index} ({chunk_count} messages) from <#{target_channel_id}>.",
            file=file_obj,
        )

    @commands.hybrid_command(name="logchannel")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def logchannel(
        self,
        ctx: commands.Context,
        target: Optional[discord.TextChannel] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        chunk_size: int = 1000,
        safety_limit: int = 20000,
    ):
        """
        Export messages from a TARGET channel (can differ from invocation channel),
        filtered by an optional UTC date range, uploading a text file every `chunk_size` messages.

        Output uses msg.clean_content to make mentions look like Discord.
        """
        invocation_channel = ctx.channel
        if not isinstance(invocation_channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("Run this in a text channel or thread.")
            return

        inv_id = invocation_channel.id

        if await self.config.channel(invocation_channel).is_exporting():
            await ctx.send("An export is already running here. Use `/logchanneloff` to stop it.")
            return

        # Determine target channel
        if target is None:
            if isinstance(invocation_channel, discord.Thread):
                await ctx.send("If you're invoking from a thread, you must supply a target channel.")
                return
            target_channel = invocation_channel
        else:
            target_channel = target

        # Parse date range (UTC)
        after_dt = None
        before_dt = None
        try:
            if start:
                after_dt = _parse_date(start).replace(tzinfo=timezone.utc)
            if end:
                before_dt = _parse_date(end).replace(tzinfo=timezone.utc)
        except ValueError:
            await ctx.send(
                "Invalid date format. Use `YYYY-MM-DD` or `YYYY-MM-DD HH:MM` (seconds optional)."
            )
            return

        if after_dt and before_dt and before_dt <= after_dt:
            await ctx.send("`end` must be after `start`.")
            return

        if chunk_size < 1:
            chunk_size = 1000
        if chunk_size > 5000:
            chunk_size = 5000

        # Start export
        await self.config.channel(invocation_channel).is_exporting.set(True)
        self._cancel_flags[inv_id] = False

        status_msg = await ctx.send(
            f"Starting export. Reading from <#{target_channel.id}> and uploading here.\n"
            f"Range (UTC): start=`{start or 'None'}` end=`{end or 'None'}`\n"
            f"Chunk size: `{chunk_size}` | Safety limit: `{safety_limit}`\n"
            f"Stop with `/logchanneloff`."
        )

        exported_total = 0
        chunk_index = 1
        chunk_count = 0
        buf = io.StringIO()

        try:
            async for msg in target_channel.history(
                limit=None,
                after=after_dt,
                before=before_dt,
                oldest_first=True,
            ):
                if self._cancel_flags.get(inv_id):
                    break

                # Skip the invocation message if applicable (prefix usage only)
                if target_channel.id == inv_id and getattr(ctx, "message", None) and msg.id == ctx.message.id:
                    continue

                buf.write(await self._format_message_block(msg))       
                chunk_count += 1
                exported_total += 1

                if chunk_count >= chunk_size:
                    await self._send_chunk(
                        ctx=ctx,
                        target_channel_id=target_channel.id,
                        chunk_index=chunk_index,
                        chunk_count=chunk_count,
                        txt_text=buf.getvalue(),
                    )
                    chunk_index += 1
                    chunk_count = 0
                    buf.close()
                    buf = io.StringIO()

                if safety_limit and exported_total >= safety_limit:
                    break

            cancelled = self._cancel_flags.get(inv_id, False)

            if chunk_count > 0:
                await self._send_chunk(
                    ctx=ctx,
                    target_channel_id=target_channel.id,
                    chunk_index=chunk_index,
                    chunk_count=chunk_count,
                    txt_text=buf.getvalue(),
                )

            if cancelled:
                await status_msg.edit(
                    content=f"Export stopped. Uploaded `{exported_total}` messages from <#{target_channel.id}>."
                )
            else:
                await status_msg.edit(
                    content=f"Export complete. Uploaded `{exported_total}` messages from <#{target_channel.id}>."
                )

        except discord.Forbidden:
            await status_msg.edit(content="I do not have permission to read message history in the target channel.")
        except Exception as e:
            await status_msg.edit(content=f"Export failed: `{type(e).__name__}: {e}`")
        finally:
            await self.config.channel(invocation_channel).is_exporting.set(False)
            self._cancel_flags.pop(inv_id, None)
            try:
                buf.close()
            except Exception:
                pass

    @commands.hybrid_command(name="logchanneloff")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def logchanneloff(self, ctx: commands.Context):
        """
        Stop an export started from THIS invocation channel.
        """
        invocation_channel = ctx.channel
        if not isinstance(invocation_channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("Run this in a text channel or thread.")
            return

        inv_id = invocation_channel.id
        if not await self.config.channel(invocation_channel).is_exporting():
            await ctx.send("No export is currently running from this channel.")
            return

        self._cancel_flags[inv_id] = True
        await ctx.send("Stopping export after the current batch…")


async def setup(bot: Red):
    await bot.add_cog(log(bot))
