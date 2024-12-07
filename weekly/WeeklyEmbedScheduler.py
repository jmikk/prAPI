from redbot.core import commands, Config
from datetime import datetime, timedelta
import discord
import asyncio

class WeeklyEmbedScheduler(commands.Cog):
    """A cog to schedule weekly embeds."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {"schedules": []}
        self.config.register_guild(**default_guild)
        self.task = self.bot.loop.create_task(self.check_schedules())

    def cog_unload(self):
        self.task.cancel()

    async def check_schedules(self):
        await self.bot.wait_until_ready()
        while True:
            now = datetime.utcnow()
            guilds = await self.config.all_guilds()
            for guild_id, data in guilds.items():
                for schedule in data["schedules"]:
                    send_time = datetime.strptime(schedule["time"], "%Y-%m-%d %H:%M:%S")
                    if now >= send_time:
                        guild = self.bot.get_guild(guild_id)
                        channel = guild.get_channel(schedule["channel_id"])
                        if channel:
                            embed = discord.Embed(
                                title=schedule["title"],
                                description=schedule["description"],
                                color=discord.Color.blue(),
                            )
                            for field in schedule["fields"]:
                                embed.add_field(name=field["name"], value=field["value"], inline=field["inline"])
                            await channel.send(embed=embed)
                        # Update the schedule to the next week
                        schedule["time"] = (send_time + timedelta(weeks=1)).strftime("%Y-%m-%d %H:%M:%S")
                await self.config.guild(guild_id).schedules.set(data["schedules"])
            await asyncio.sleep(60)  # Check every minute

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.group()
    async def scheduleembed(self, ctx):
        """Manage weekly scheduled embeds."""
        pass

    @scheduleembed.command()
    async def add(self, ctx, channel: discord.TextChannel, day: str, time: str, title: str, description: str):
        """
        Add a new scheduled embed.
        
        Parameters:
        - channel: The channel where the embed will be sent.
        - day: The day of the week (e.g., Monday, Tuesday).
        - time: The time in 24-hour format (e.g., 14:30 for 2:30 PM UTC).
        - title: The title of the embed.
        - description: The description of the embed.
        """
        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        if day.lower() not in day_map:
            await ctx.send("Invalid day. Please provide a valid day of the week.")
            return

        now = datetime.utcnow()
        target_day = day_map[day.lower()]
        target_time = datetime.strptime(time, "%H:%M").time()
        delta_days = (target_day - now.weekday() + 7) % 7
        target_datetime = datetime.combine(now + timedelta(days=delta_days), target_time)

        schedule = {
            "channel_id": channel.id,
            "time": target_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "title": title,
            "description": description,
            "fields": [],
        }
        async with self.config.guild(ctx.guild).schedules() as schedules:
            schedules.append(schedule)

        await ctx.send(f"Scheduled an embed for {day} at {time} UTC in {channel.mention}.")

    @scheduleembed.command()
    async def list(self, ctx):
        """List all scheduled embeds."""
        schedules = await self.config.guild(ctx.guild).schedules()
        if not schedules:
            await ctx.send("No scheduled embeds.")
            return

        embed = discord.Embed(title="Scheduled Embeds", color=discord.Color.green())
        for idx, schedule in enumerate(schedules, 1):
            embed.add_field(
                name=f"{idx}. {schedule['title']}",
                value=f"Channel: <#{schedule['channel_id']}>\nTime: {schedule['time']}\nDescription: {schedule['description']}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @scheduleembed.command()
    async def delete(self, ctx, index: int):
        """Delete a scheduled embed by its index."""
        async with self.config.guild(ctx.guild).schedules() as schedules:
            if 0 < index <= len(schedules):
                removed = schedules.pop(index - 1)
                await ctx.send(f"Deleted scheduled embed: {removed['title']}")
            else:
                await ctx.send("Invalid index.")

    @scheduleembed.command()
    async def edit(self, ctx, index: int, title: str = None, description: str = None):
        """Edit a scheduled embed by its index."""
        async with self.config.guild(ctx.guild).schedules() as schedules:
            if 0 < index <= len(schedules):
                schedule = schedules[index - 1]
                if title:
                    schedule["title"] = title
                if description:
                    schedule["description"] = description
                await ctx.send(f"Updated scheduled embed: {schedule['title']}")
            else:
                await ctx.send("Invalid index.")
