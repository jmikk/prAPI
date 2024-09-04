import discord
from discord.ext import commands
from redbot.core import Config, commands

class recToken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=23456789648)
        self.admin_messages = {}  # Store admin panel messages

        default_guild = {
            "projects": {},
            "completed_projects": {}
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_user(credits=0)

    @commands.command()
    async def menu(self, ctx):
        embed = discord.Embed(
            title="Command Menu",
            description="Use the buttons below to view projects, check your credits, or view completed projects.",
            color=discord.Color.blue()
        )

        view_projects_button = discord.ui.Button(label="View Projects", custom_id="view_projects", style=discord.ButtonStyle.primary)
        check_credits_button = discord.ui.Button(label="Check Credits", custom_id="check_credits", style=discord.ButtonStyle.success)
        view_completed_button = discord.ui.Button(label="View Completed Projects", custom_id="view_completed_projects", style=discord.ButtonStyle.secondary)

        view = discord.ui.View()
        view.add_item(view_projects_button)
        view.add_item(check_credits_button)
        view.add_item(view_completed_button)

        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        custom_id = interaction.data['custom_id']

        if custom_id == "view_projects":
            await interaction.response.defer()
            await self.view_projects(interaction)
        elif custom_id == "check_credits":
            await interaction.response.defer()
            await self.check_credits(interaction)
        elif custom_id == "view_completed_projects":
            await interaction.response.defer()
            await self.view_completed_projects(interaction)
        elif custom_id.startswith("navigate_"):
            direction, project_name, project_type = custom_id.split("_")[1:]
            await self.navigate_projects(interaction, direction, project_name, project_type)
        elif custom_id.startswith("donate_"):
            project_name = custom_id.split("_")[1]
            await interaction.response.defer()
            await self.ask_donation_amount(interaction, project_name)
        elif custom_id.startswith("edit_project_"):
            project_name = custom_id.split("_")[2]
            await self.send_edit_menu(interaction, project_name)
        elif custom_id.startswith("remove_project_"):
            project_name = custom_id.split("_")[2]
            await self.remove_project(interaction, project_name)
        elif custom_id.startswith("edit_field_"):
            field, project_name = custom_id.split("_")[2:]
            await self.prompt_edit_field(interaction, project_name, field)

    async def view_projects(self, interaction: discord.Interaction):
        projects = await self.config.guild(interaction.guild).projects()
        if not projects:
            await interaction.followup.send(embed=discord.Embed(description="No ongoing projects.", color=discord.Color.red()), ephemeral=True)
        else:
            project_names = list(projects.keys())
            initial_index = 0
            initial_embed = self.create_embed(projects, project_names, initial_index, ongoing=True)
            view = self.create_project_view(project_names, initial_index, ongoing=True)

            await interaction.followup.send(embed=initial_embed, view=view)

    async def view_completed_projects(self, interaction: discord.Interaction):
        completed_projects = await self.config.guild(interaction.guild).completed_projects()
        if not completed_projects:
            await interaction.followup.send(embed=discord.Embed(description="No completed projects.", color=discord.Color.red()), ephemeral=True)
        else:
            project_names = list(completed_projects.keys())
            initial_index = 0
            initial_embed = self.create_embed(completed_projects, project_names, initial_index, ongoing=False)
            view = self.create_project_view(project_names, initial_index, ongoing=False)

            await interaction.followup.send(embed=initial_embed, view=view)

    async def navigate_projects(self, interaction: discord.Interaction, direction: str, project_name: str, project_type: str):
        if project_type == "ongoing":
            projects = await self.config.guild(interaction.guild).projects()
        else:
            projects = await self.config.guild(interaction.guild).completed_projects()

        project_names = list(projects.keys())
        current_index = project_names.index(project_name)

        if direction == "previous":
            new_index = (current_index - 1) % len(project_names)
        else:  # direction == "next"
            new_index = (current_index + 1) % len(project_names)

        new_embed = self.create_embed(projects, project_names, new_index, ongoing=(project_type == "ongoing"))
        view = self.create_project_view(project_names, new_index, ongoing=(project_type == "ongoing"))

        await interaction.response.edit_message(embed=new_embed, view=view)

    def create_embed(self, projects, project_names, index, ongoing=True):
        project_name = project_names[index]
        project = projects[project_name]
    
        percent_complete = (project["current_credits"] / project["required_credits"]) * 100 if project["required_credits"] > 0 else 100
    
        embed = discord.Embed(
            title=f"Project: {self.display_project_name(project_name)}",
            description=project["description"] or "No description available.",
            color=discord.Color.green() if not ongoing else discord.Color.blue()
        )
        embed.add_field(
            name=f"Credits {project.get('emoji', '💰')}",
            value=f"{project['current_credits']}/{project['required_credits']} credits",
            inline=False
        )
        embed.add_field(
            name="% Complete",
            value=f"{percent_complete:.2f}% complete",
            inline=False
        )
        if project["thumbnail"]:
            embed.set_thumbnail(url=project["thumbnail"])

        embed.set_footer(text=f"Project {index + 1}/{len(project_names)}")
    
        return embed

    def create_project_view(self, project_names, index, ongoing=True):
        current_project_name = project_names[index]
        view = discord.ui.View()

        view.add_item(
            discord.ui.Button(
                label="⬅️ Previous",
                custom_id=f"navigate_previous_{current_project_name}_{'ongoing' if ongoing else 'completed'}",
                style=discord.ButtonStyle.secondary
            )
        )

        if ongoing:
            view.add_item(
                discord.ui.Button(
                    label="Donate Credits",
                    custom_id=f"donate_{current_project_name}",
                    style=discord.ButtonStyle.primary
                )
            )

        view.add_item(
            discord.ui.Button(
                label="Next ➡️",
                custom_id=f"navigate_next_{current_project_name}_{'ongoing' if ongoing else 'completed'}",
                style=discord.ButtonStyle.secondary
            )
        )

        return view

    async def donatecredits(self, interaction: discord.Interaction, project_name: str, amount_to_donate: int):
        project = self.normalize_project_name(project_name)
        async with self.config.guild(interaction.guild).projects() as projects:
            if project not in projects:
                return await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()), ephemeral=True)
    
            user_credits = await self.config.user(interaction.user).credits()
            current_credits = projects[project]["current_credits"]
            required_credits = projects[project]["required_credits"]

            max_donatable = required_credits - current_credits

            if amount_to_donate > max_donatable:
                amount_to_donate = max_donatable

            if amount_to_donate > user_credits:
                return await interaction.followup.send(embed=discord.Embed(description="You don't have enough credits.", color=discord.Color.red()), ephemeral=True)
    
            projects[project]["current_credits"] += amount_to_donate
    
            new_credits = user_credits - amount_to_donate
            await self.config.user(interaction.user).credits.set(new_credits)

            await interaction.followup.send(embed=discord.Embed(description=f"{interaction.user.name} donated {amount_to_donate} credits to '{self.display_project_name(project)}'.", color=discord.Color.green()), ephemeral=False)

            if projects[project]["current_credits"] >= required_credits:
                await self.complete_project(interaction, project_name)

    async def complete_project(self, interaction: discord.Interaction, project_name: str):
        async with self.config.guild(interaction.guild).projects() as projects:
            project = projects.pop(project_name)
            async with self.config.guild(interaction.guild).completed_projects() as completed_projects:
                completed_projects[project_name] = project

        await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project_name)}' is now fully funded and has been moved to completed projects!", color=discord.Color.gold()), ephemeral=False)

    async def check_credits(self, interaction: discord.Interaction):
        credits = await self.config.user(interaction.user).credits()

        embed = discord.Embed(
            title="Your Credits",
            description=f"You currently have **{credits}** credits.",
            color=discord.Color.green()
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def ask_donation_amount(self, interaction: discord.Interaction, project_name: str):
        def check(message):
            return message.author == interaction.user and message.channel == interaction.channel

        await interaction.followup.send(embed=discord.Embed(description="Please enter the amount of credits you would like to donate or type 'all' to donate all your credits.", color=discord.Color.blue()), ephemeral=True)

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            amount = msg.content.lower()

            user_credits = await self.config.user(interaction.user).credits()
            project = self.normalize_project_name(project_name)
            projects = await self.config.guild(interaction.guild).projects()
            if project not in projects:
                return await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()), ephemeral=True)

            current_credits = projects[project]["current_credits"]
            required_credits = projects[project]["required_credits"]

            max_donatable = required_credits - current_credits

            if amount == 'all':
                amount_to_donate = min(user_credits, max_donatable)
            else:
                amount_to_donate = int(amount)
                if amount_to_donate > max_donatable:
                    amount_to_donate = max_donatable

            await self.donatecredits(interaction, project_name, amount_to_donate)
        except ValueError:
            await interaction.followup.send(embed=discord.Embed(description="Invalid amount entered. Please try again.", color=discord.Color.red()), ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send(embed=discord.Embed(description="You took too long to respond. Please try again.", color=discord.Color.red()), ephemeral=True)

    async def remove_project(self, interaction: discord.Interaction, project_name: str):
        project = self.normalize_project_name(project_name)
        async with self.config.guild(interaction.guild).projects() as projects:
            if project not in projects:
                return await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()), ephemeral=True)
    
            del projects[project]

        await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project_name)}' has been removed.", color=discord.Color.green()), ephemeral=False)

    def display_project_name(self, project: str) -> str:
        return project.replace("_", " ").title()

    def normalize_project_name(self, project: str) -> str:
        return project.replace(" ", "_").lower()

def setup(bot):
    bot.add_cog(recToken(bot))
