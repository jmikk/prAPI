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
        # Retrieve the current score
        current_score = await self.config.guild(ctx.guild).scores()
        new_score = current_score + 1
    
        # Update the score
        await self.config.guild(ctx.guild).scores.set(new_score)
    
        lap_art = ["https://tenor.com/view/earth-gif-8912275","https://tenor.com/view/funny-gif-24784982","https://tenor.com/view/spongebob-panic-patrick-ahhh-run-around-gif-9319829","https://tenor.com/view/mobile-girl-mim-running-excited-gif-21459068","https://tenor.com/view/chicken-run-chicken-in-shoes-crash-bandicoot-crash-gif-3420651847898329517","https://tenor.com/view/cat-hopping-cute-kitty-kitty-baby-cat-gif-104564847600069574","https://tenor.com/view/cat-run-omg-gif-10386143","https://tenor.com/view/dog-running-coming-doggo-gif-12143874","https://tenor.com/view/ham-burger-hot-dog-running-funny-animated-gif-17820157"]
        # Include the server name in the message
        await ctx.send(f"Keep running, {ctx.guild.name}! Your server score is now {new_score}.\n{lap_art}")




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
