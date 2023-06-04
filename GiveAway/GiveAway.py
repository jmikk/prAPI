import discord
import asyncio
import random
from redbot.core import commands
from datetime import datetime, timedelta

class GiveAway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaways = {}
        self.giveaway_channel_id = None  # Initialize giveaway channel ID as None

    def generate_giveaway_id(self):
        while True:
            giveaway_id = random.randint(1000, 9999)
            if giveaway_id not in self.giveaways:
                return giveaway_id

    def format_duration(self, duration):
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours} hours, {minutes} minutes"
        elif minutes > 0:
            return f"{minutes} minutes, {seconds} seconds"
        else:
            return f"{seconds} seconds"

    def format_timestamp(self, timestamp):
        return f"<t:{timestamp-18000}:R>"

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def startgiveaway(self, ctx, duration: int, prize: str, *roles: discord.Role):
        giveaway_id = self.generate_giveaway_id()

        if giveaway_id in self.giveaways:
            await ctx.send("A giveaway is already running with the same ID. Please try again.")
            return

        end_time = datetime.utcnow() + timedelta(seconds=duration)
        formatted_duration = self.format_duration(duration)

        giveaway_data = {
            "end_time": end_time,
            "prize": prize,
            "roles": roles,
            "participants": []
        }

        self.giveaways[giveaway_id] = giveaway_data

        end_timestamp = int(end_time.timestamp())
        message = (
            f"🎉 **Giveaway** 🎉\n\n"
            f"React with 🎉 to enter the giveaway!\n"
            f"Prize: {prize}\n"
            f"ID: {giveaway_id}\n"
            f"Ends in {self.format_timestamp(end_timestamp)}."
            f"Host: {ctx.author.mention}"
        )

        channel = self.bot.get_channel(self.giveaway_channel_id)
        sent_message = await channel.send(message)
        await sent_message.add_reaction("🎉")

        await asyncio.sleep(duration)
        del self.giveaways[giveaway_id]

        new_message = await channel.fetch_message(sent_message.id)
        reaction = discord.utils.get(new_message.reactions, emoji="🎉")
        participants = []
        async for user in reaction.users():
            participant = await channel.guild.fetch_member(user.id)
            if any(role in participant.roles for role in roles):
                participants.append(participant)

        if participants:
            winner = random.choice(participants)
            await channel.send(f"Congratulations to {winner.mention} for winning the giveaway ({giveaway_id}).  You won {prize}! Please let the Host:{ctx.author.mention} know where you want the prize!")
        else:
            await channel.send(f"No eligible participants. The giveaway ({giveaway_id}) has ended.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setgiveawaychannel(self, ctx, channel: discord.TextChannel):
        self.giveaway_channel_id = channel.id
        await ctx.send(f"Giveaway channel set to {channel.mention}")

            
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        for giveaway_id, giveaway_data in self.giveaways.items():
            channel_id = payload.channel_id
            message_id = payload.message_id
            user_id = payload.user_id

            if (
                channel_id == payload.channel_id
                and message_id == giveaway_data["message_id"]
            ):
                guild = self.bot.get_guild(payload.guild_id)
                member = guild.get_member(user_id)

                if any(role in member.roles for role in giveaway_data["roles"]):
                    giveaway_data["participants"].append(member)
