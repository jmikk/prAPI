import discord
from discord.ext import tasks
from redbot.core import commands, Config
from aiohttp import ClientSession, ClientError
import json
from datetime import datetime


class SSE(commands.Cog):
    """Monitor regions for updates and delegate changes via SSE."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1098342)
        default_global = {"region_mapping": {}, "sse_url": "https://www.nationstates.net/api/member+admin"}
        self.config.register_global(**default_global)
        self.sse_task = None
        self.show_feed = False
        self.next_event_ctx = None  # Store context for showing the next event

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
                    mappings[rs.strip().lower().replace(" ", "_")] = {
                        "trigger": trigger.strip().lower().replace(" ", "_"),
                        "target": target.strip().lower().replace(" ", "_")
                    }
            await self.config.region_mapping.set(mappings)
            await ctx.send("Region mappings loaded successfully.")
        except Exception as e:
            error_message = f"Error processing the file: {e}"
            await ctx.send(error_message)
            await self.send_error_notification(error_message)

    @regionmonitor.command()
    async def start(self, ctx):
        """Start monitoring the SSE feed."""
        if self.sse_task is not None:
            return await ctx.send("Monitoring is already running.")
        self.sse_task = self.bot.loop.create_task(self.listen_to_sse())
        await ctx.send("Monitoring started.")

    @regionmonitor.command()
    async def showfeed(self, ctx):
        """Show the next SSE event the bot receives."""
        if self.sse_task is None:
            return await ctx.send("Monitoring is not running.")
        self.show_feed = True
        self.next_event_ctx = ctx  # Save the context to reply later
        await ctx.send("I'll show the next SSE event that the bot sees.")

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
            error_message = "SSE URL not set."
            print(error_message)
            await self.send_error_notification(error_message)
            return

        mappings = await self.config.region_mapping()

        while True:
            try:
                async with ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            error_message = f"Failed to connect to SSE feed: {response.status}"
                            print(error_message)
                            await self.send_error_notification(error_message)
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
                error_message = f"Connection error: {e}"
                print(error_message)
                await self.send_error_notification(error_message)
                await self.retry_on_failure()
            except TimeoutError:
                error_message = "Connection timed out."
                print(error_message)
                await self.send_error_notification(error_message)
                await self.retry_on_failure()
            except Exception as e:
                error_message = f"Unexpected error: {e}"
                print(error_message)
                await self.send_error_notification(error_message)
                await self.retry_on_failure()

    async def retry_on_failure(self):
        """Handles retries after a connection error."""
        print("Retrying connection in 5 seconds...")
        await discord.utils.sleep_until(datetime.now().timestamp() + 5)

    async def process_event(self, event, mappings):
        """Process incoming SSE events."""
        # Check if the next event should be shown
        if self.show_feed and self.next_event_ctx:
            await self.next_event_ctx.send(f"**Next SSE Event:** {event}")
            self.show_feed = False  # Reset the flag
            self.next_event_ctx = None

        # Continue with normal event processing
        event_str = event.get("str", "")
        event_time = event.get("time", None)
        event_timestamp = f"<t:{event_time}:F>" if event_time else "Unknown time"

        for rs, regions in mappings.items():
            trigger = regions["trigger"]
            target = regions["target"]

            if f"%%{trigger}%% updated" in event_str:
                message = (
                    f"Region Trigger: `{trigger}` was updated at {event_timestamp}.\n"
                    f"Radio Silence Region: `{rs}`"
                )
                await self.send_notification(message)

            if f"became WA Delegate of %%{target}%%" in event_str:
                delegate = event_str.split("@@")[1].split("@@")[0]
                message = (
                    f"**New Delegate Alert!**\n"
                    f"`{delegate}` became the WA Delegate of `{target}` at {event_timestamp}."
                )
                await self.send_notification(message)

    async def send_notification(self, message):
        """Send the notification to a specific Discord channel."""
        channel_id = 811288101557239888  # Replace this with your Discord channel ID
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(message)

    async def send_error_notification(self, error_message):
        """Send error notifications to the specified Discord channel."""
        channel_id = 811288101557239888  # Replace this with your Discord channel ID
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(f"⚠️ **Error:** {error_message}")
