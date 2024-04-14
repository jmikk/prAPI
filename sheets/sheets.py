from redbot.core import commands
from discord import Embed, Interaction, SelectOption, ui

class sheet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def createembed(self, ctx):
        """Starts the embed creation process."""
        # Launch the menu to select embed properties
        await ctx.send("Please choose options for the embed.", view=self.EmbedCreationMenu())

    class EmbedCreationMenu(ui.View):
        def __init__(self):
            super().__init__(timeout=180)  # Timeout for menu interaction

        @ui.select(
            placeholder="Choose the embed color",
            options=[
                SelectOption(label="Red", description="Set the embed color to red", value="red"),
                SelectOption(label="Green", description="Set the embed color to green", value="green"),
                SelectOption(label="Blue", description="Set the embed color to blue", value="blue"),
            ]
        )
        async def select_callback(self, select, interaction: Interaction):
            color_map = {
                "red": 0xFF0000,
                "green": 0x00FF00,
                "blue": 0x0000FF
            }
            color = color_map[select.values[0]]
            embed = Embed(title="Custom Embed", description="Here is your custom embed!", color=color)
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    bot.add_cog(sheet(bot))
