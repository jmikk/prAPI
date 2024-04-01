from redbot.core import commands
import discord
import asyncio

class Recruitomatic9006(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_channel = None  # The channel to send messages to
        self.embed_send_task = None  # The asyncio task for sending the embed
        self.last_interaction = None  # Timestamp of the last interaction

    def cog_unload(self):
        if self.embed_send_task:
            self.embed_send_task.cancel()  # Cancel the embed sending task if the cog is unloaded

    @commands.command()
    async def stoprecruit(self, ctx):
        """Force stops the recruit loop."""
        if self.embed_send_task:
            self.embed_send_task.cancel()  # Cancel the embed sending task
            self.embed_send_task = None  # Reset the task to None
            await ctx.send("Recruit loop has been forcibly stopped.")
        else:
            await ctx.send("Recruit loop is not running.")

    @commands.command()
    async def recruit2(self, ctx, minutes: int):
        """Starts sending the recruit embed in the current channel every X minutes."""
        if self.embed_send_task:
            self.embed_send_task.cancel()  # Cancel any existing task

        self.target_channel = ctx.channel  # Update the target channel to the current one
        self.last_interaction = discord.utils.utcnow()  # Update the timestamp to now

        # Start a new task for sending the embed periodically
        self.embed_send_task = asyncio.create_task(self.send_embed_periodically(minutes))

        await ctx.send(f"Will send recruit embed every {minutes} minutes in this channel. Loop will end if there's no interaction for 10 minutes.")

    async def send_embed_periodically(self, interval_minutes):
        while True:
            if self.last_interaction and (discord.utils.utcnow() - self.last_interaction).total_seconds() > 600:
                # If more than 10 minutes have passed since the last interaction, stop the loop
                await self.target_channel.send("No interactions received for 10 minutes. Stopping the recruit loop.")
                break

            embed = discord.Embed(title="Recruit Message", description="Choose an option:", color=0x00ff00)
            view = RecruitView(self)
            if self.target_channel:  # Check if the target channel is set
                await self.target_channel.send(embed=embed, view=view)
            await asyncio.sleep(interval_minutes * 60)  # Wait for the specified interval

class RecruitView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=600)  # 10 minutes timeout for the view
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction):
        self.cog.last_interaction = discord.utils.utcnow()  # Update the timestamp on any interaction
        return True

    @discord.ui.button(label="End Cycle", style=discord.ButtonStyle.red)
    async def end_cycle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cog.embed_send_task:
            self.cog.embed_send_task.cancel()  # Cancel the embed sending task
        self.stop()  # Stop the view from listening to more interactions
        await interaction.response.send_message("Cycle ended.", ephemeral=True)

    @discord.ui.button(label="Restart Timer", style=discord.ButtonStyle.green)
    async def restart_timer(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.last_interaction = discord.utils.utcnow()  # Update the timestamp to now
        await interaction.response.send_message("Timer reset.", ephemeral=True)

async def setup(bot):
    cog = RecruitCog(bot)
    bot.add_cog(cog)
