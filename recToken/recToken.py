import discord
from redbot.core import commands, Config, checks
from discord.ui import Button, View

class recToken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        default_user = {
            "credits": 0,
            "items": []
        }

        default_guild = {
            "items": {},  # {"emoji": {"name": "item_name", "price": price}}
            "projects": {}  # {"project_name": {"required_credits": int, "current_credits": int, "donated_items": [], "thumbnail": "", "description": ""}}
        }
        
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    @commands.command()
    async def viewprojects(self, ctx):
        """View ongoing projects and their progress with scrolling embeds."""
        projects = await self.config.guild(ctx.guild).projects()
        if not projects:
            await ctx.send(embed=discord.Embed(description="No ongoing projects.", color=discord.Color.red()))
        else:
            project_names = list(projects.keys())
            view = ProjectScrollView(ctx, projects, project_names, self.config)
            embed = view.create_embed(0)
            await ctx.send(embed=embed, view=view)

class ProjectScrollView(View):
    def __init__(self, ctx, projects, project_names, config):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.projects = projects
        self.project_names = project_names
        self.current_index = 0
        self.config = config

    def create_embed(self, index):
        project_name = self.project_names[index]
        project = self.projects[project_name]

        embed = discord.Embed(
            title=f"Project: {project_name}",
            description=project["description"] or "No description available.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Credits",
            value=f"{project['current_credits']}/{project['required_credits']} credits",
            inline=False
        )
        embed.add_field(
            name="Donated Items",
            value=", ".join(project['donated_items']) or "None",
            inline=False
        )
        if project["thumbnail"]:
            embed.set_thumbnail(url=project["thumbnail"])
        
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, button: Button, interaction: discord.Interaction):
        # Debugging to ensure the button is being triggered
        print("Previous button clicked")  # This will print in the console
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.project_names) - 1
        
        embed = self.create_embed(self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, button: Button, interaction: discord.Interaction):
        # Debugging to ensure the button is being triggered
        print("Next button clicked")  # This will print in the console
        if self.current_index < len(self.project_names) - 1:
            self.current_index += 1
        else:
            self.current_index = 0
        
        embed = self.create_embed(self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Ensure the interaction is allowed
        print("Interaction check called")  # This will print in the console
        return interaction.user == self.ctx.author

def setup(bot):
    bot.add_cog(recToken(bot))
