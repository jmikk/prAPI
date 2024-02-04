from redbot.core import commands, Config
import discord

class Run(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_guild(scores=0)

    @commands.guild_only()
    @commands.command(name="run!")
    async def run(self, ctx):
        # Increment the server score
        async with self.config.guild(ctx.guild).scores() as scores:
            scores += 1
            lap_art = """
            __o
          _ \<_
         (_)/(_)
            """
            await ctx.send(f"Keep running! Your server score is now {scores}.\n{lap_art}")

    @commands.command(name="leaderboard")
    async def leaderboard_command(self, ctx):
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
