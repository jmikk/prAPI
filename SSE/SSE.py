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
        self.config.register_guild(targets={})  # Store targets as a dictionary
        self.config.register_guild(listening=False)
        self.current_task = None
        self.current_channel = None

    @commands.group()
    async def nsfeed(self, ctx):
        """Commands for managing the NationStates API feed."""
        pass

    @nsfeed.command()
    async def settarget(self, ctx, *, target_data: str):
        """Set targets and messages from input or a file.

        Input format:
        - List: `target1, message1; target2, message2`
        - File: Upload a file with `target,message` pairs, one per line.
        """
        if ctx.message.attachments:
            # Handle file input
            attachment = ctx.message.attachments[0]
            content = (await attachment.read()).decode("utf-8")
            lines = content.splitlines()
            target_dict = {}

            for line in lines:
                if "," in line:
                    target, message = line.split(",", 1)
                    target = target.lower().strip().replace(" ", "_")
                    target_dict[f"%{target}%"] = message.strip()

            await self.config.guild(ctx.guild).targets.set(target_dict)
            await ctx.send(f"Targets set from file with {len(target_dict)} entries.")
        else:
            # Handle manual input
            pairs = target_data.split(";")
            target_dict = {}

            for pair in pairs:
                if "," in pair:
                    target, message = pair.split(",", 1)
                    target = target.lower().strip().replace(" ", "_")
                    target_dict[f"%{target}%"] = message.strip()

            await self.config.guild(ctx.guild).targets.set(target_dict)
            await ctx.send(f"Targets set with {len(target_dict)} entries.")

    @nsfeed.command()
    async def start(self, ctx):
        """Start listening to the NationStates API feed."""
        listening = await self.config.guild(ctx.guild).listening()
        if listening:
            await ctx.send("Already listening to the feed.")
            return

        targets = await self.config.guild(ctx.guild).targets()
        if not targets:
            await ctx.send("Please set targets first using `nsfeed settarget`.")
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

        while await self.config.guild_from_id(guild_id).listening():
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
                                        targets = await self.config.guild_from_id(guild_id).targets()

                                        for target, message in targets.items():
                                            if target in event_data:
                                                timestamp = datetime.now().strftime("<t:%s:F>") % int(datetime.now().timestamp())
                                                if self.current_channel:
                                                    await self.current_channel.send(f"{timestamp} {message}")
                                                    await self.current_channel.send(f"Event data: {event_data}")
                        else:
                            if self.current_channel:
                                await self.current_channel.send(
                                    f"Error: Received status code {response.status}. {response.text}"
                                )
            except asyncio.CancelledError:
                # Handle task cancellation gracefully
                break
            except Exception as e:
                if self.current_channel and e:
                    if not "Response payload is not completed" in e:
                        await self.current_channel.send(
                                f"Error in listening to the feed: {e}. Retrying now. {datetime.now()}"
                            )
                        

    async def cog_unload(self):
        """Ensure the task is stopped when the cog is unloaded."""
        if self.current_task:
            self.current_task.cancel()
