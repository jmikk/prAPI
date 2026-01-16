from __future__ import annotations

import io
import re
from typing import List, Optional, Union

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red


def _sanitize_cell(value: Optional[str]) -> str:
    """
    Prepare text for TSV: collapse CRLF, keep tabs readable, avoid huge control chars.
    """
    if not value:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\t", "    ")
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value


ChannelLike = Union[discord.TextChannel, discord.Thread]


class log(commands.Cog):
    """
    Per-channel incremental logger.

    - Exports all messages since the last time /logchannel was run in that channel.
    - Splits output into multiple TSV files, each containing up to N messages (messages_per_file).
    - Stores a per-channel checkpoint (message ID) updated at the end of a successful run.
    """

    __author__ = "ChatGPT"
    __version__ = "1.2.0"

    HEADER = "message_id\tcreated_at_iso\tauthor_id\tauthor_tag\tauthor_display\tcontent\tattachments\tjump_url\n"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=873214556122, force_registration=True)

        default_channel = {
            "last_logged_message_id": None,   # int
            "messages_per_file": 1000,        # int
        }
        self.config.register_channel(**default_channel)

    def _format_row(self, m: discord.Message) -> str:
        created = m.created_at.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
        disc = getattr(m.author, "discriminator", "0")
        author_tag = f"{m.author.name}#{disc}" if disc != "0" else m.author.name
        author_display = getattr(m.author, "display_name", m.author.name)
        content = _sanitize_cell(m.content)

        attachment_urls = [a.url for a in (m.attachments or [])]
        attachments_joined = _sanitize_cell(" ".join(attachment_urls))

        return (
            f"{m.id}\t{created}\t{m.author.id}\t{_sanitize_cell(author_tag)}\t"
            f"{_sanitize_cell(author_display)}\n{content}\n{attachments_joined}\n{m.jump_url}\n"
        )

    async def _send_tsv_file(
        self,
        ctx: commands.Context,
        channel: ChannelLike,
        rows: List[str],
        part: int,
        first_id: int,
        last_id: int,
    ) -> None:
        out = io.StringIO()
        out.write(self.HEADER)
        out.writelines(rows)
        data = out.getvalue().encode("utf-8")
        out.close()

        filename = f"channel_log_{channel.id}_part{part}_{first_id}_to_{last_id}.tsv"
        file_obj = discord.File(fp=io.BytesIO(data), filename=filename)
        await ctx.send(
            content=f"Log export file {part}: `{len(rows)}` message(s) ({first_id} → {last_id}).",
            file=file_obj,
        )

    @commands.hybrid_command(name="logchannel")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def logchannel(self, ctx: commands.Context):
        """
        Dump messages in THIS channel since the last time this command was run here.
        Splits the export into multiple files based on messages_per_file.
        """
        channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("This command can only be used in text channels or threads.")
            return

        # Start-of-run checkpoint: exclude messages that arrive mid-run.
        checkpoint_id: Optional[int] = None
        try:
            checkpoint_id = getattr(channel, "last_message_id", None)
            if checkpoint_id is None:
                last_msgs = [m async for m in channel.history(limit=1)]
                checkpoint_id = last_msgs[0].id if last_msgs else None
        except Exception:
            checkpoint_id = None

        if checkpoint_id is None:
            await ctx.send("I couldn't determine the latest message in this channel. Try again.")
            return

        last_logged_id: Optional[int] = await self.config.channel(channel).last_logged_message_id()
        messages_per_file: int = await self.config.channel(channel).messages_per_file()

        if messages_per_file < 1 or messages_per_file > 10000:
            messages_per_file = 1000  # fail-safe

        use_after: Optional[discord.Object] = None
        if last_logged_id is not None:
            use_after = discord.Object(id=int(last_logged_id))

        status_msg = await ctx.send(
            f"Exporting messages… (after `{last_logged_id}` up to checkpoint `{checkpoint_id}`) "
            f"chunk size: `{messages_per_file}`/file"
        )

        exported_count = 0
        part = 1
        rows: List[str] = []
        first_id_in_part: Optional[int] = None
        last_id_in_part: Optional[int] = None

        try:
            async with ctx.typing():
                async for msg in channel.history(limit=None, after=use_after, oldest_first=True):
                    # Stop at checkpoint (exclude anything after the run started)
                    if msg.id > checkpoint_id:
                        break

                    # Exclude invoking message if this was invoked as a prefix command
                    if getattr(ctx, "message", None) and msg.id == ctx.message.id:
                        continue

                    # Accumulate
                    if first_id_in_part is None:
                        first_id_in_part = msg.id
                    last_id_in_part = msg.id

                    rows.append(self._format_row(msg))
                    exported_count += 1

                    # Flush file when we hit the per-file cap
                    if len(rows) >= messages_per_file:
                        await self._send_tsv_file(
                            ctx=ctx,
                            channel=channel,
                            rows=rows,
                            part=part,
                            first_id=int(first_id_in_part),
                            last_id=int(last_id_in_part),
                        )
                        part += 1
                        rows = []
                        first_id_in_part = None
                        last_id_in_part = None

                # Flush any remainder
                if rows:
                    await self._send_tsv_file(
                        ctx=ctx,
                        channel=channel,
                        rows=rows,
                        part=part,
                        first_id=int(first_id_in_part or 0),
                        last_id=int(last_id_in_part or 0),
                    )

        except discord.Forbidden:
            await status_msg.edit(content="I do not have permission to read message history in this channel.")
            return
        except discord.HTTPException as e:
            # Don’t advance checkpoint if uploads fail
            await status_msg.edit(content=f"Export failed while uploading a file: `{type(e).__name__}: {e}`")
            return
        except Exception as e:
            await status_msg.edit(content=f"Export failed: `{type(e).__name__}: {e}`")
            return

        if exported_count == 0:
            # Nothing new; still advance checkpoint so next run starts from here.
            await self.config.channel(channel).last_logged_message_id.set(int(checkpoint_id))
            await status_msg.edit(content="No new messages to export since the last run. Checkpoint updated.")
            return

        # Update checkpoint only after successful export
        await self.config.channel(channel).last_logged_message_id.set(int(checkpoint_id))
        await status_msg.edit(
            content=f"Done. Exported `{exported_count}` message(s) across `{part if rows else part}` file(s). "
                    f"Checkpoint updated to `{checkpoint_id}`."
        )

    @commands.hybrid_command(name="logchannelreset")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def logchannelreset(self, ctx: commands.Context):
        """
        Reset this channel's logging checkpoint (next run will export the entire channel history).
        """
        channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("This command can only be used in text channels or threads.")
            return

        await self.config.channel(channel).last_logged_message_id.set(None)
        await ctx.send("This channel's log checkpoint has been reset (next run exports full history).")

    @commands.hybrid_command(name="logchannellimit")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def logchannellimit(self, ctx: commands.Context, messages_per_file: int):
        """
        Set the per-channel messages-per-file limit for exports.
        Example: /logchannellimit 2000
        """
        channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("This command can only be used in text channels or threads.")
            return

        if messages_per_file < 1 or messages_per_file > 10000:
            await ctx.send("messages_per_file must be between 1 and 10000.")
            return

        await self.config.channel(channel).messages_per_file.set(int(messages_per_file))
        await ctx.send(f"Messages per exported file for this channel set to `{messages_per_file}`.")


async def setup(bot: Red):
    await bot.add_cog(log(bot))
