from redbot.core import commands
from discord.ext import tasks
import discord

class Recruitomatic9006(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recruit_loop.start()

    def cog_unload(self):
        self.recruit_loop.cancel()

    @commands.command()
    async def recruit2(self, ctx, minutes: int):
        """Starts the recruit loop with a specified interval."""
        self.recruit_loop.change_interval(minutes=minutes)
        await ctx.send(f"Recruit loop set to every {minutes} minutes.")

    @tasks.loop(minutes=10)  # Default to 10 minutes, but this will be overridden by the command.
    async def recruit_loop(self):
        channel = self.bot.get_channel(CHANNEL_ID)  # Replace CHANNEL_ID with your channel's ID
        embed = discord.Embed(title="Recruit Message", description="Choose an option:", color=0x00ff00)
        view = RecruitView()
        await channel.send(embed=embed, view=view)

class RecruitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)  # 10 minutes timeout

    @discord.ui.button(label="End Cycle", style=discord.ButtonStyle.red)
    async def end_cycle(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message("Cycle ended.", ephemeral=True)

    @discord.ui.button(label="Restart Timer", style=discord.ButtonStyle.green)
    async def restart_timer(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Logic to restart the timer
        await interaction.response.send_message("Timer restarted.", ephemeral=True)

async def setup(bot):
    cog = RecruitCog(bot)
    bot.add_cog(cog)
