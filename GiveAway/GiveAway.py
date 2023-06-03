import discord
import asyncio
import random
from redbot.core import commands
from datetime import datetime, timedelta

class GiveAway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_channel_id = 865778321546543117
        self.current_giveaway = None

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def startgiveaway(self, ctx, duration: int, prize: str, *roles: discord.Role):
        if self.current_giveaway is not None:
            await ctx.send("A giveaway is already running.")
            return

        self.current_giveaway = {
            "end_time": datetime.utcnow() + timedelta(seconds=duration),
            "prize": prize,
            "roles": roles,
            "participants": []
        }

        end_timestamp = datetime.utcnow() + timedelta(seconds=duration)
        formatted_duration = discord.utils.format_dt(end_timestamp, "R")  # Fancy timestamp
        footer_text = f"Ends at {formatted_duration} UTC."

        embed = discord.Embed(title="Giveaway", description=f"React with 🎉 to enter the giveaway!\nPrize: {prize}", footer=footer_text)

        channel = self.bot.get_channel(self.giveaway_channel_id)
        message = await channel.send(embed=embed)
        await message.add_reaction("🎉")

        await asyncio.sleep(duration)
        self.current_giveaway = None

        new_message = await channel.fetch_message(message.id)
        reaction = discord.utils.get(new_message.reactions, emoji="🎉")
        participants = []
        async for user in reaction.users():
            participant = await channel.guild.fetch_member(user.id)
            if any(role in participant.roles for role in roles):
                participants.append(participant)

        if participants:
            winner = random.choice(participants)
            await channel.send(f"Congratulations to {winner.mention} for winning the giveaway!")
        else:
            await channel.send("No eligible participants. The giveaway has ended.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if self.current_giveaway is not None:
            channel_id = payload.channel_id
            message_id = payload.message_id
            user_id = payload.user_id

            if channel_id == self.giveaway_channel_id and message_id == self.current_giveaway["message_id"]:
                guild = self.bot.get_guild(payload.guild_id)
                member = guild.get_member(user_id)

                if any(role in member.roles for role in self.current_giveaway["roles"]):
                    self.current_giveaway["participants"].append(member)
