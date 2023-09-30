from redbot.core import commands
import asyncio
import time
import random
from datetime import datetime
import discord

def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False

    return commands.permissions_check(predicate)


class HOTW(commands.Cog):
    HOTWname="test"
    timestamp = datetime.now()  # Initialize timestamp as a datetime object
    # Define a dictionary to store user data
    user_data = {}

    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    # great once your done messing with the bot.
    #   async def cog_command_error(self, ctx, error):
    #       await ctx.send(" ".join(error.args))

    @commands.command()
    async def leaderboard(self, ctx):
        # Sort the user_data by total time and longest streak
        sorted_users_by_time = sorted(HOTW.user_data.values(), key=lambda x: x["total_time"], reverse=True)
        sorted_users_by_streak = sorted(HOTW.user_data.values(), key=lambda x: x["longest_streak"], reverse=True)
    
        # Create leaderboard messages
        time_leaderboard = "Top 3 Holders by Total Time:\n"
        streak_leaderboard = "Top 3 Holders by Longest Streak:\n"
    
        for i, user_data_time in enumerate(sorted_users_by_time[:3]):
            time_leaderboard += f"{i+1}. {user_data_time['name']} - {user_data_time['total_time']} seconds\n"
    
        for i, user_data_streak in enumerate(sorted_users_by_streak[:3]):
            streak_leaderboard += f"{i+1}. {user_data_streak['name']} - {user_data_streak['longest_streak']} seconds\n"
    
        # Send leaderboard messages
        await ctx.send(time_leaderboard)
        await ctx.send(streak_leaderboard)
    


    @commands.command()
    @commands.is_owner()
    async def HOTW(self, ctx):
        ways_to_take_water = [
    "Bob grabs Fancy Water from Joe.",
    "Bob snatches Fancy Water from Joe.",
    "Bob acquires Fancy Water from Joe.",
    "Bob appropriates Fancy Water from Joe.",
    "Bob seizes Fancy Water from Joe.",
    "Bob confiscates Fancy Water from Joe.",
    "Bob swipes Fancy Water from Joe.",
    "Bob procures Fancy Water from Joe.",
    "Bob lifts Fancy Water from Joe.",
    "Bob helps himself to Fancy Water from Joe.",
    "Bob secures Fancy Water from Joe.",
    "Bob obtains Fancy Water from Joe.",
    "Bob takes possession of Fancy Water from Joe.",
    "Bob claims Fancy Water from Joe.",
    "Bob wrests Fancy Water from Joe.",
    "Bob commandeers Fancy Water from Joe.",
    "Bob removes Fancy Water from Joe.",
    "Bob snags Fancy Water from Joe.",
    "Bob appropriates the Fancy Water from Joe.",
    "Bob makes off with Fancy Water from Joe.",
    "Bob filches Fancy Water from Joe.",
    "Bob gains control of Fancy Water from Joe.",
    "Bob nabs Fancy Water from Joe.",
    "Bob extracts Fancy Water from Joe.",
    "Bob lifts up Fancy Water from Joe.",
    "Bob walks away with Fancy Water from Joe.",
    "Bob helps himself to Joe's Fancy Water.",
    "Bob takes away Fancy Water from Joe.",
    "Bob gets a hold of Fancy Water from Joe.",
    "Bob pockets Fancy Water from Joe.",
    "Bob swindles Fancy Water from Joe.",
    "Bob pinches Fancy Water from Joe.",
    "Bob removes Fancy Water from Joe's possession.",
    "Bob snags a sip of Fancy Water from Joe.",
    "Bob plunders Fancy Water from Joe.",
    "Bob snatches up Fancy Water from Joe.",
    "Bob claims Fancy Water as his own from Joe.",
    "Bob carries off Fancy Water from Joe.",
    "Bob assumes control of Fancy Water from Joe.",
    "Bob takes Fancy Water without permission from Joe.",
    "Bob expropriates Fancy Water from Joe.",
    "Bob relieves Joe of his Fancy Water.",
    "Bob commandeers Joe's Fancy Water.",
    "Bob walks off with Joe's Fancy Water.",
    "Bob confiscates Joe's Fancy Water.",
    "Bob helps himself to Joe's stash of Fancy Water.",
    "Bob runs off with Fancy Water from Joe.",
    "Bob liberates Fancy Water from Joe.",
    "Bob sequesters Fancy Water from Joe.",
    "Bob gets Fancy Water from Joe's supply.",
    "Bob makes a heist of Fancy Water from Joe.",
    "Bob takes Fancy Water from Joe's stockpile.",
    "Bob pockets Fancy Water from Joe's collection.",
    "Bob claims Fancy Water as his own from Joe's cache.",
    "Bob carries away Fancy Water from Joe's reserve.",
    "Bob assumes possession of Fancy Water from Joe's hoard.",
    "Bob snags Fancy Water from Joe's secret stash.",
    "Bob sneaks away with Fancy Water from Joe's hidden supply.",
    "Bob runs away with Fancy Water from Joe's concealed reserve.",
    "Bob helps himself to Fancy Water from Joe's undisclosed collection.",
    "Bob relieves Joe of Fancy Water discreetly.",
    "Bob expropriates Fancy Water from Joe's concealed treasure.",
    "Bob makes off with Fancy Water from Joe's undisclosed stockpile.",
    "Bob purloins Fancy Water from Joe's hidden reservoir.",
    "Bob takes a sip of Fancy Water from Joe's secret cache.",
    "Bob snitches Fancy Water from Joe's covert supply.",
    "Bob walks away unnoticed with Fancy Water from Joe.",
    "Bob pilfers Fancy Water from Joe's camouflaged stash.",
    "Bob appropriates the hidden Fancy Water from Joe.",
    "Bob pockets Fancy Water from Joe's under-the-radar collection.",
    "Bob seizes Fancy Water from Joe's surreptitious stockpile.",
    "Bob snags Fancy Water from Joe's confidential reserve.",
    "Bob takes Fancy Water discreetly from Joe.",
    "Bob walks off quietly with Fancy Water from Joe.",
    "Bob liberates Fancy Water from Joe's confidential cache.",
    "Bob quietly helps himself to Fancy Water from Joe.",
    "Bob takes Fancy Water from Joe without raising suspicion.",
    "Bob discreetly relieves Joe of Fancy Water.",
    "Bob takes Fancy Water covertly from Joe.",
    "Bob pilfers Fancy Water surreptitiously from Joe.",
    "Bob sneaks Fancy Water from Joe.",
    "Bob secretly obtains Fancy Water from Joe.",
    "Bob slips away with Fancy Water from Joe.",
    "Bob appropriates Joe's hidden Fancy Water.",
    "Bob makes a clandestine move for Fancy Water from Joe.",
    "Bob grabs Fancy Water from Joe's stash on the sly.",
    "Bob makes an undercover acquisition of Fancy Water from Joe.",
    "Bob slyly snatches Fancy Water from Joe.",
    "Bob maneuvers discreetly to take Fancy Water from Joe.",
    "Bob conducts a covert operation to obtain Fancy Water from Joe.",
    "Bob procures Fancy Water from Joe in a stealthy manner."
]
        random_statement = random.choice(ways_to_take_water)

        # Calculate the time difference
        current_time = datetime.now()
        time_difference = current_time - HOTW.timestamp
        time_difference_seconds = time_difference.total_seconds()
        
        # Replace "Bob" with the current author and "Joe" with the previous owner
        random_statement = random_statement.replace("Bob", str(ctx.author.mention)).replace("Joe", str(HOTW.HOTW).replace("Fancy Water","The Magic Wellwater"))
        
        # Update the previous owner to the current author
        if HOTW.HOTWname == "test":
            HOTW.HOTWname = ctx.author.mention
        
        # Generate a new random statement
        random_statement = random.choice(ways_to_take_water)
        random_statement = random_statement.replace("Bob", str(ctx.author.mention)).replace("Joe", str(HOTW.HOTWname))
        
        # Calculate the time difference in seconds and update the timestamp
        current_epoch_timestamp = datetime.now().timestamp()
        time_difference_seconds = current_epoch_timestamp - HOTW.timestamp.timestamp()
        HOTW.timestamp = current_time  # Update the timestamp
        
        # Send the updated statement and the time difference
        await ctx.send(random_statement)
        await ctx.send(f"{HOTW.HOTWname} had the water for {time_difference_seconds} seconds")

        # Update user_data with the current user's data
        user_id = str(ctx.author.id)
        
        if user_id not in HOTW.user_data:
            HOTW.user_data[user_id] = {"name": str(ctx.author), "total_time": 0, "current_streak": 0, "longest_streak": 0}
        
        HOTW.user_data[user_id]["total_time"] += time_difference_seconds
        HOTW.user_data[user_id]["current_streak"] += time_difference_seconds
        
        # Check if the current streak is longer than the longest streak
        if HOTW.user_data[user_id]["current_streak"] > HOTW.user_data[user_id]["longest_streak"]:
            HOTW.user_data[user_id]["longest_streak"] = HOTW.user_data[user_id]["current_streak"]

        
        HOTW.timestamp = current_time  # Update the timestamp
        HOTW.HOTWname = ctx.author.mention

