# redbot cog: channel_logger.py
# Logs messages from a channel since the last time the command was run in THAT channel
# and dumps them into a text/TSV file posted back into the channel.

from __future__ import annotations

import io
import re
from typing import Optional, List

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red


def _sanitize_cell(value: str) -> str:
    """
    Prepare text for TSV: collapse CRLF, keep tabs readable, avoid huge control chars.
    """
    if value is None:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\t", "    ")
    # Optional: collapse multiple newlines a bit (comment out if you want raw newlines)
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value


class log(commands.Cog):
    """
    Per-channel incremental logger.

    Run the command in a channel to export messages since last run in that channel.
    The cog stores a per-channel checkpoint (message ID).
    """

    __author__ = "ChatGPT"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=873214556122, force_registration=True)

        default_channel = {
            "last_logged_message_id": None,  # int
        }
        self.config.register_channel(**default_channel)

    @commands.hybrid_command(name="logchannel")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def logchannel(
        self,
        ctx: commands.Context,
    ):
        """
        Dump messages in THIS channel since the last time this command was run here.


        """
        channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("This command can only be used in text channels or threads.")
            return

        # Determine the "checkpoint" (the latest message ID at the start of the run).
        # This prevents messages arriving mid-run from being inconsistently included.
        checkpoint_id = None
        try:
            # last_message_id is often available; if not, fetch history for last message
            checkpoint_id = getattr(channel, "last_message_id", None)
            if checkpoint_id is None:
                last_msgs = [m async for m in channel.history(limit=1)]
                checkpoint_id = last_msgs[0].id if last_msgs else None
        except Exception:
            checkpoint_id = None

        # Read previous checkpoint for THIS channel
        last_logged_id = await self.config.channel(channel).last_logged_message_id()

        # If there is no checkpoint to anchor, nothing to do
        if checkpoint_id is None:
            await ctx.send("I couldn't determine the latest message in this channel. Try again.")
            return

        # If the channel has never been logged, we will log "up to limit" most recent messages.
        # (Otherwise, logging *everything* could be excessive.)
        use_after = None
        if last_logged_id is not None:
            use_after = discord.Object(id=int(last_logged_id))

        status_msg = await ctx.send(
            f"Exporting messages… (since last run: `{last_logged_id}`"
        )

        # Collect messages
        exported: List[discord.Message] = []
        count = 0

        try:
            # Oldest-first makes it easier to stop cleanly at checkpoint_id.
            async for msg in channel.history(limit=None, after=use_after, oldest_first=True):
                # Stop at checkpoint
                if msg.id > checkpoint_id:
                    break

                # For prefix commands, exclude the invoking message itself (optional).
                # For hybrid/slash, ctx.message may be None.
                if getattr(ctx, "message", None) and msg.id == ctx.message.id:
                    continue

                exported.append(msg)
                count += 1
        except discord.Forbidden:
            await status_msg.edit(content="I do not have permission to read message history in this channel.")
            return
        except Exception as e:
            await status_msg.edit(content=f"Export failed due to an unexpected error: `{type(e).__name__}: {e}`")
            return

        if not exported:
            # Update checkpoint anyway so the next run starts from here
            await self.config.channel(channel).last_logged_message_id.set(int(checkpoint_id))
            await status_msg.edit(content="No new messages to export since the last run. Checkpoint updated.")
            return

        # Build TSV output
        # Columns: message_id, created_at_iso, author_id, author_tag, author_display, content, attachments, jump_url
        out = io.StringIO()
        out.write(
            "message_id\tcreated_at_iso\tauthor_id\tauthor_tag\tauthor_display\t"
        )

        for m in exported:
            created = m.created_at.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
            author_tag = f"{m.author.name}#{m.author.discriminator}" if m.author.discriminator != "0" else m.author.name
            author_display = m.author.display_name
            content = _sanitize_cell(m.content)

            attachment_urls = []
            if m.attachments:
                attachment_urls.extend([a.url for a in m.attachments])

            # You may also want to capture sticker/embeds; kept minimal here.
            attachments_joined = _sanitize_cell(" ".join(attachment_urls))

            line = (
                f"{m.id}\t{created}\t{m.author.id}\t{_sanitize_cell(author_tag)}\t"
                f"{_sanitize_cell(author_display)}\n{content}\n{attachments_joined}\n"
            )
            out.write(line)

        data = out.getvalue().encode("utf-8")
        out.close()

        # File naming
        first_id = exported[0].id
        last_id = exported[-1].id
        filename = f"channel_log_{channel.id}_{first_id}_to_{last_id}.tsv"

        # Post file to channel
        file_obj = discord.File(fp=io.BytesIO(data), filename=filename)

        await ctx.send(
            content=(
                f"Exported `{len(exported)}` message(s) from <#{channel.id}> "
                f"(after `{last_logged_id}` up to `{checkpoint_id}`)."
            ),
            file=file_obj,
        )

        # Update checkpoint to the start-of-run checkpoint_id
        await self.config.channel(channel).last_logged_message_id.set(int(checkpoint_id))

        await status_msg.edit(content=f"Done. Checkpoint updated to `{checkpoint_id}`.")

    @commands.hybrid_command(name="logchannelreset")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def logchannelreset(self, ctx: commands.Context):
        """
        Reset this channel's logging checkpoint (next run will export up to `limit` recent messages).
        """
        channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("This command can only be used in text channels or threads.")
            return

        await self.config.channel(channel).last_logged_message_id.set(None)
        await ctx.send("This channel's log checkpoint has been reset.")


async def setup(bot: Red):
    await bot.add_cog(log(bot))
