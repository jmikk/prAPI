import discord
from discord.ext import tasks
from redbot.core import commands, Config
from aiohttp import ClientSession, ClientError
import json
from datetime import datetime

class RegionMonitor(commands.Cog):
    """Monitor regions for updates and delegate changes via SSE."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=098342)
        default_global = {"region_mapping": {}, "sse_url": "https://www.nationstates.net/api/member+admin"}
        self.config.register_global(**default_global)
        self.sse_task = None

    @commands.group()
    async def regionmonitor(self, ctx):
        """Manage the Region Monitor settings."""
        pass

    @regionmonitor.command()
    async def loadfile(self, ctx, file: discord.Attachment):
        """Upload a file mapping Radio Silence, trigger, and target regions."""
        content = await file.read()
        try:
            mappings = {}
            for line in content.decode("utf-8").splitlines():
                parts = line.split(",")
                if len(parts) == 3:
                    rs, trigger, target = parts
                    mappings[rs.strip()] = {"trigger": trigger.strip(), "target": target.strip()}
            await self.config.region_mapping.set(mappings)
            await ctx.send("Region mappings loaded successfully.")
        except Exception as e:
            await ctx.send(f"Error processing the file: {e}")

    @regionmonitor.command()
    async def start(self, ctx):
        """Start monitoring the SSE feed."""
        if self.sse_task is not None:
            return await ctx.send("Monitoring is already running.")
        self.sse_task = self.bot.loop.create_task(self.listen_to_sse())
        await ctx.send("Monitoring started.")

    @regionmonitor.command()
    async def stop(self, ctx):
        """Stop monitoring the SSE feed."""
        if self.sse_task is None:
            return await ctx.send("Monitoring is not running.")
        self.sse_task.cancel()
        self.sse_task = None
        await ctx.send("Monitoring stopped.")

    async def listen_to_sse(self):
        url = await self.config.sse_url()
        if not url:
            print("SSE URL not set.")
            return
        mappings = await self.config.region_mapping()

        while True:
            try:
                async with ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            print(f"Failed to connect to SSE feed: {response.status}")
                            await self.retry_on_failure()
                            continue
                        async for line in response.content:
                            if line:
                                try:
                                    event = json.loads(line.decode("utf-8"))
                                    await self.process_event(event, mappings)
                                except json.JSONDecodeError:
                                    continue
            except ClientError as e:
                print(f"Connection error: {e}")
                await self.retry_on_failure()
            except TimeoutError:
                print("Connection timed out.")
                await self.retry_on_failure()
            except Exception as e:
                print(f"Unexpected error: {e}")
                await self.retry_on_failure()

    async def retry_on_failure(self):
        """Handles retries after a connection error."""
        print("Retrying connection in 5 seconds...")
        await discord.utils.sleep_until(datetime.now().timestamp() + 5)

    async def process_event(self, event, mappings):
        # Extract event data
        event_str = event.get("str", "")
        event_time = event.get("time", None)
        event_timestamp = f"<t:{event_time}:F>" if event_time else "Unknown time"

        # Process region updates
        for rs, regions in mappings.items():
            trigger = regions["trigger"]
            target = regions["target"]

            if f"%%{trigger}%% updated" in event_str:
                message = (
                    f"Region Trigger: `{trigger}` was updated at {event_timestamp}.\n"
                    f"Radio Silence Region: `{rs}`"
                )
                await self.send_notification(message)

            # Process delegate change events
            if f"became WA Delegate of %%{target}%%" in event_str:
                delegate = event_str.split("@@")[1].split("@@")[0]
                message = (
                    f"**New Delegate Alert!**\n"
                    f"`{delegate}` became the WA Delegate of `{target}` at {event_timestamp}."
                )
                await self.send_notification(message)

    async def send_notification(self, message):
        """Send the notification to a specific Discord channel."""
        # Replace with your target channel ID
        channel_id = 811288101557239888  # Replace this with your Discord channel ID
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(message)
