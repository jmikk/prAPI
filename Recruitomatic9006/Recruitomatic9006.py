from redbot.core import commands
import discord
from discord.ui import Button, View
import asyncio

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.send_message_task = None
        self.continue_sending = True

    @commands.command()
    async def start_task(self, ctx, interval: int = 10):  # Default interval set to 10 minutes
        if self.send_message_task is not None and not self.send_message_task.done():
            self.send_message_task.cancel()

        self.send_message_task = asyncio.create_task(self.send_periodic_messages(ctx, interval))

    async def send_periodic_messages(self, ctx, interval_minutes):
        await self.bot.wait_until_ready()
        self.continue_sending = True

        while not self.bot.is_closed() and self.continue_sending:
            await self.send_approval_message(ctx)
            await asyncio.sleep(interval_minutes * 60)  # Convert minutes to seconds

    async def send_approval_message(self, ctx):
        view = ApprovalView(self, ctx.author)
        embed = discord.Embed(title="Approval Needed", description="Please click Approve or All Done.", color=0x00ff00)
        await ctx.send(embed=embed, view=view)

    async def send_wrap_up_message(self, user, message):
        channel = user.dm_channel or await user.create_dm()
        await channel.send(message)

class ApprovalView(discord.ui.View):
    def __init__(self, cog_instance, user):
        super().__init__(timeout=180)  # 3 minutes timeout
        self.cog_instance = cog_instance
        self.user = user

    async def on_timeout(self):
        await self.cog_instance.send_wrap_up_message(self.user, "Time has expired. Wrapping up.")
        self.cog_instance.continue_sending = False  # Stop the loop

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return  # Ignore if the user is not the invoker

        await interaction.response.send_message("You are awarded 8 tokens.", ephemeral=True)

    @discord.ui.button(label="All Done", style=discord.ButtonStyle.red)
    async def all_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return  # Ignore if the user is not the invoker

        # Acknowledge the interaction
        if not interaction.response.is_done():
            await interaction.response.defer()

        # Send the wrap-up message
        await self.cog_instance.send_wrap_up_message(interaction.user, "All done! Closing.")
        self.cog_instance.continue_sending = False  # Stop the loop
        self.stop()

async def setup(bot):
    bot.add_cog(MyCog(bot))
