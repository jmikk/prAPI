from redbot.core import commands, Config
import discord

class Run(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_guild(scores=0)

    @commands.guild_only()
    @commands.command(name="run!")
    async def run_command(self, ctx):
        # Define the running animation frames
        running_frames = [
            """
             __o
           _ \\<_
          (_)/(_)
            """,
            """
             \o/
              |
             / \\
            """,
            """
             __o
               \\<_
              (_)/
            """,
            """
              o
             /|
             / \\
            """
        ]
    
        # Retrieve the current score and frame index
        async with self.config.guild(ctx.guild).all() as guild_data:
            current_score = guild_data['scores']
            frame_index = guild_data.get('frame_index', 0)  # Default to 0 if not set
    
        new_score = current_score + 1
        # Update the score
        guild_data['scores'] = new_score
    
        # Get the next frame of running animation
        next_frame = running_frames[frame_index]
        # Update the frame index for the next run
        guild_data['frame_index'] = (frame_index + 1) % len(running_frames)  # Loop back to the first frame
    
        # Include the server name and the next frame of running animation in the message
        await ctx.send(f"Keep running, {ctx.guild.name}! Your server score is now {new_score}.\n{next_frame}")



    @commands.command(name="Run_leaderboard")
    async def Run_leaderboard(self, ctx):
        all_scores = await self.config.all_guilds()
        
        # Sort scores by value in descending order
        sorted_scores = sorted(all_scores.items(), key=lambda x: x[1]['scores'], reverse=True)
        
        # Format the leaderboard
        leaderboard = "Leaderboard:\n"
        for idx, (guild_id, data) in enumerate(sorted_scores, start=1):
            guild_name = self.bot.get_guild(guild_id).name if self.bot.get_guild(guild_id) else 'Unknown Guild'
            leaderboard += f"{idx}. {guild_name}: {data['scores']} Runs\n"
        
        # Send the leaderboard
        await ctx.send(leaderboard)
