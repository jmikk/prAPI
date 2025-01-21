import discord
from redbot.core import commands, Config
import aiohttp
import asyncio
import re
from datetime import datetime


class SSE(commands.Cog):
    """Listen to the NationStates founding API feed and notify about matches."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(target=None, listening=False)
        self.current_task = None
        self.current_channel = None

    @commands.group()
    async def nsfeed(self, ctx):
        """Commands for managing the NationStates API feed."""
        pass

    @nsfeed.command()
    async def settarget(self, ctx, *, target: str):
        """Set the target string to look for in the SSE feed."""
        target = target.lower().replace(" ", "_")
        await self.config.guild(ctx.guild).target.set(target)
        await ctx.send(f"Target set to: `{target}`")

    @nsfeed.command()
    async def start(self, ctx):
        """Start listening to the NationStates API feed."""
        listening = await self.config.guild(ctx.guild).listening()
        if listening:
            await ctx.send("Already listening to the feed.")
            return

        target = await self.config.guild(ctx.guild).target()
        if not target:
            await ctx.send("Please set a target first using `nsfeed settarget`.")
            return

        self.current_channel = ctx.channel
        await self.config.guild(ctx.guild).listening.set(True)
        await ctx.send("Started listening to the NationStates API feed.")
        self.current_task = asyncio.create_task(self.listen_to_feed(ctx.guild.id))

    @nsfeed.command()
    async def stop(self, ctx):
        """Stop listening to the NationStates API feed."""
        listening = await self.config.guild(ctx.guild).listening()
        if not listening:
            await ctx.send("Not currently listening to the feed.")
            return

        await self.config.guild(ctx.guild).listening.set(False)
        self.current_channel = None
        if self.current_task:
            self.current_task.cancel()
        await ctx.send("Stopped listening to the NationStates API feed.")

    async def listen_to_feed(self, guild_id):
        """Listen to the SSE feed and notify on matches."""
        url = "https://www.nationstates.net/api/member+admin"
        headers = {"User-Agent": "9006"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        buffer = ""
                        async for chunk in response.content.iter_any():
                            buffer += chunk.decode("utf-8")
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                line = line.strip()
                                if line.startswith("data:"):
                                    event_data = line[5:].strip()
                                    target = await self.config.guild_from_id(guild_id).target()

                                    if target in event_data:
                                        matches = re.findall(r"%%(.*?)%%", event_data)
                                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        match_message = (
                                            f"[{timestamp}] Found between %%: " + ", ".join(matches)
                                        )

                                        # Send message to the current channel
                                        if self.current_channel:
                                            await self.current_channel.send(match_message)
                                            await self.current_channel.send(
                                                f"Event data: {event_data}"
                                            )
        except asyncio.CancelledError:
            # Handle task cancellation gracefully
            pass
        except Exception as e:
            if self.current_channel:
                await self.current_channel.send(f"Error in listening to the feed: {e}")
                await self.config.guild(ctx.guild).listening.set(False)
                self.current_channel = None
                if self.current_task:
                    self.current_task.cancel()
                await ctx.send("Stopped listening to the NationStates API feed. Most times this is just means nothing happened for a bit, Start me again by doing ```nsfeed start```")

    async def cog_unload(self):
        """Ensure the task is stopped when the cog is unloaded."""
        if self.current_task:
            self.current_task.cancel()
