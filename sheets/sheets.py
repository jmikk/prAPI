from redbot.core import commands
from discord import Embed, Interaction, ui

class sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def createembed(self, ctx):
        """Triggers a modal to create a custom embed."""
        modal = self.CreateEmbedModal(title="Create Your Custom Embed")
        await ctx.send_modal(modal)

    class CreateEmbedModal(ui.Modal, title="Custom Embed Creation"):
        title_input = ui.TextInput(
            label="Embed Title",
            style=TextInputStyle.short,
            placeholder="Enter the title for the embed...",
            required=True,
            max_length=100
        )
        description_input = ui.TextInput(
            label="Embed Description",
            style=TextInputStyle.paragraph,
            placeholder="Enter the description for the embed...",
            required=True
        )
        color_input = ui.TextInput(
            label="Embed Color (Hex Code)",
            style=TextInputStyle.short,
            placeholder="Enter a hex color code, e.g., #FF5733",
            required=True,
            max_length=7
        )

        async def on_submit(self, interaction: Interaction):
            try:
                color = int(self.color_input.value.strip("#"), 16)
            except ValueError:
                return await interaction.response.send_message("Invalid color code. Please use a valid hex code, e.g., #FF5733.", ephemeral=True)
            
            embed = Embed(
                title=self.title_input.value,
                description=self.description_input.value,
                color=color
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    bot.add_cog(sheets(bot))
