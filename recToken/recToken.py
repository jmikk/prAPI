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
            "completed_projects": {},
            "personal_projects": {}
        }
        default_user = {
            "credits": 0,
            "completed_personal_projects": {}
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_user(**default_user)

    @commands.command()
    async def menu(self, ctx):
        """Displays the main menu for managing projects and credits."""
        embed = discord.Embed(
            title="Command Menu",
            description="Use the buttons below to view projects, check your credits, or view completed projects.",
            color=discord.Color.blue()
        )
        
        view_projects_button = discord.ui.Button(label="View Kingdom Projects", custom_id="viewprojects", style=discord.ButtonStyle.primary)
        check_credits_button = discord.ui.Button(label="Check Credits", custom_id="checkcredits", style=discord.ButtonStyle.success)
        view_completed_projects_button = discord.ui.Button(label="View Completed Projects", custom_id="viewcompletedprojects", style=discord.ButtonStyle.primary)

        view = discord.ui.View()
        view.add_item(view_projects_button)
        view.add_item(view_completed_projects_button)
        view.add_item(check_credits_button)
    
        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        custom_id = interaction.data['custom_id']
    
        if custom_id == "viewprojects":
            await interaction.response.defer()
            await self.viewprojects(interaction)
        elif custom_id.startswith("navigate_previous_"):
            await self.navigate_projects(interaction, "previous")
        elif custom_id.startswith("navigate_next_"):
            await self.navigate_projects(interaction, "next")
        elif custom_id == "checkcredits":
            await interaction.response.defer()
            await self.checkcredits(interaction)
        elif custom_id == "viewcompletedprojects":
            await interaction.response.defer()
            await self.view_completed_projects_interaction(interaction)
        elif custom_id.startswith("navigate_completed_previous_"):
            await self.navigate_completed_projects(interaction, "previous")
        elif custom_id.startswith("navigate_completed_next_"):
            await self.navigate_completed_projects(interaction, "next")
        elif custom_id.startswith("donate_"):
            project_name = custom_id.split("_", 1)[1]
            await interaction.response.defer()
            await self.ask_donation_amount(interaction, project_name)
        elif custom_id.startswith("edit_project_"):
            project_name = custom_id.split("_")[2]
            completed = "completed" in custom_id
            await self.send_edit_menu(interaction, project_name, completed)
        elif custom_id.startswith("remove_project_"):
            project_name = custom_id.split("_")[2]
            completed = "completed" in custom_id
            await self.remove_project(interaction, project_name, completed)

    async def view_completed_projects_interaction(self, interaction: discord.Interaction, guild_level=True):
        if guild_level:
            completed_projects = await self.config.guild(interaction.guild).completed_projects()
        else:
            completed_projects = await self.config.user(interaction.user).completed_personal_projects()

        if not completed_projects:
            await interaction.followup.send(embed=discord.Embed(description="No completed projects yet.", color=discord.Color.red()), ephemeral=True)
            return
    
        project_names = list(completed_projects.keys())
        initial_index = 0
        initial_embed = self.create_embed(completed_projects, project_names, initial_index, interaction.user)
        view = self.create_completed_project_view(project_names, initial_index, interaction.user)
    
        await interaction.followup.send(embed=initial_embed, view=view)
    
    def create_completed_project_view(self, project_names, index, user):
        current_project_name = project_names[index]
        view = discord.ui.View()
    
        view.add_item(
            discord.ui.Button(
                label="⬅️ Previous",
                custom_id=f"navigate_completed_previous_{current_project_name}",
                style=discord.ButtonStyle.secondary
            )
        )
    
        view.add_item(
            discord.ui.Button(
                label="Next ➡️",
                custom_id=f"navigate_completed_next_{current_project_name}",
                style=discord.ButtonStyle.secondary
            )
        )
    
        return view

    async def navigate_completed_projects(self, interaction: discord.Interaction, direction: str):
        completed_projects = await self.config.guild(interaction.guild).completed_projects()
        project_names = list(completed_projects.keys())
    
        current_project_name = interaction.data['custom_id'].split("_", 3)[-1]
        current_index = project_names.index(current_project_name)
    
        if direction == "previous":
            new_index = (current_index - 1) % len(project_names)
        else:
            new_index = (current_index + 1) % len(project_names)
    
        new_embed = self.create_embed(completed_projects, project_names, new_index, interaction.user)
        view = self.create_completed_project_view(project_names, new_index, interaction.user)
    
        await interaction.response.edit_message(embed=new_embed, view=view)

    async def viewprojects(self, interaction: discord.Interaction, guild_level=True):
        if guild_level:
            projects = await self.config.guild(interaction.guild).projects()
        else:
            all_personal_projects = await self.config.guild(interaction.guild).personal_projects()
            completed_personal_projects = await self.config.user(interaction.user).completed_personal_projects()
            guild_projects = await self.config.guild(interaction.guild).projects()

            projects = {
                project_name: project_data
                for project_name, project_data in all_personal_projects.items()
                if project_name not in completed_personal_projects and self.has_prerequisites(interaction.user, project_data, completed_personal_projects, guild_projects)
            }

        if not projects:
            await interaction.followup.send(embed=discord.Embed(description="No available projects.", color=discord.Color.red()), ephemeral=True)
        else:
            project_names = list(projects.keys())
            initial_index = 0
            initial_embed = self.create_embed(projects, project_names, initial_index, interaction.user)
            view = self.create_project_view(project_names, initial_index, interaction.user, guild_level)

            await interaction.followup.send(embed=initial_embed, view=view)

    def has_prerequisites(self, user, project_data, completed_personal_projects, guild_projects):
        prereqs = project_data.get("prereqs", [])
        for prereq in prereqs:
            if prereq not in completed_personal_projects and prereq not in guild_projects:
                return False
        return True

    async def navigate_projects(self, interaction: discord.Interaction, direction: str):
        projects = await self.config.guild(interaction.guild).projects()
        project_names = list(projects.keys())

        current_project_name = interaction.data['custom_id'].split("_", 2)[-1]
        current_index = project_names.index(current_project_name)

        if direction == "previous":
            new_index = (current_index - 1) % len(project_names)
        else:
            new_index = (current_index + 1) % len(project_names)

        new_embed = self.create_embed(projects, project_names, new_index, interaction.user)
        view = self.create_project_view(project_names, new_index, interaction.user)

        await interaction.response.edit_message(embed=new_embed, view=view)

    def create_embed(self, projects, project_names, index, user):
        project_name = project_names[index]
        project = projects[project_name]
        percent_complete = (project["current_credits"] / project["required_credits"]) * 100 if project["required_credits"] > 0 else 100

        embed = discord.Embed(
            title=f"Project: {self.display_project_name(project_name)}",
            description=project["description"] or "No description available.",
            color=discord.Color.blue()
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

    def create_project_view(self, project_names, index, user, guild_level=True):
        current_project_name = project_names[index]
        view = discord.ui.View()

        if guild_level:
            view.add_item(
                discord.ui.Button(
                    label="⬅️ Previous",
                    custom_id=f"navigate_previous_{current_project_name}",
                    style=discord.ButtonStyle.secondary
                )
            )
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
                    custom_id=f"navigate_next_{current_project_name}",
                    style=discord.ButtonStyle.secondary
                )
            )
        return view

    async def send_admin_panel(self, interaction: discord.Interaction, project_name: str):
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Edit Project",
                custom_id=f"edit_project_{project_name}",
                style=discord.ButtonStyle.success
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Remove Project",
                custom_id=f"remove_project_{project_name}",
                style=discord.ButtonStyle.danger
            )
        )

        embed = discord.Embed(
            title="Admin Panel",
            description=f"Manage the project: {self.display_project_name(project_name)}",
            color=discord.Color.gold()
        )
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        self.admin_messages[interaction.user.id] = message

    async def checkcredits(self, interaction: discord.Interaction):
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
                await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' is now fully funded!", color=discord.Color.gold()), ephemeral=False)

                async with self.config.guild(interaction.guild).completed_projects() as completed_projects:
                    completed_projects[project] = projects[project]
                del projects[project]

    async def remove_project(self, interaction: discord.Interaction, project_name: str, completed: bool):
        project_name = self.normalize_project_name(project_name)

        if completed:
            async with self.config.guild(interaction.guild).completed_projects() as projects:
                if project_name in projects:
                    del projects[project_name]
                else:
                    await interaction.followup.send(embed=discord.Embed(description="Project not found.", color=discord.Color.red()))
                    return
        else:
            async with self.config.guild(interaction.guild).projects() as projects:
                if project_name in projects:
                    del projects[project_name]
                else:
                    await interaction.followup.send(embed=discord.Embed(description="Project not found.", color=discord.Color.red()))
                    return

        await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project_name)}' has been removed.", color=discord.Color.green()))

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def admin_menu(self, ctx):
        """Displays the admin menu for managing ongoing and completed projects."""
        
        embed = discord.Embed(
            title="Admin Project Management",
            description="Use the buttons below to manage ongoing and completed projects.",
            color=discord.Color.gold()
        )

        view_ongoing_projects_button = discord.ui.Button(
            label="Manage Ongoing Projects", custom_id="manage_ongoing_projects", style=discord.ButtonStyle.primary
        )
        view_completed_projects_button = discord.ui.Button(
            label="Manage Completed Projects", custom_id="manage_completed_projects", style=discord.ButtonStyle.success
        )

        view = discord.ui.View()
        view.add_item(view_ongoing_projects_button)
        view.add_item(view_completed_projects_button)

        await ctx.send(embed=embed, view=view)

    async def manage_projects(self, interaction: discord.Interaction, completed: bool):
        if completed:
            projects = await self.config.guild(interaction.guild).completed_projects()
            project_type = "Completed"
        else:
            projects = await self.config.guild(interaction.guild).projects()
            project_type = "Ongoing"

        if not projects:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"No {project_type.lower()} projects available.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        project_names = list(projects.keys())
        initial_index = 0
        initial_embed = self.create_embed(projects, project_names, initial_index, interaction.user)
        view = self.create_admin_project_view(project_names, initial_index, interaction.user, completed)

        await interaction.followup.send(embed=initial_embed, view=view)

    def create_admin_project_view(self, project_names, index, user, completed):
        current_project_name = project_names[index]
        view = discord.ui.View()

        view.add_item(
            discord.ui.Button(
                label="⬅️ Previous",
                custom_id=f"navigate_previous_{current_project_name}",
                style=discord.ButtonStyle.secondary
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Edit Project",
                custom_id=f"edit_project_{current_project_name}_{'completed' if completed else 'ongoing'}",
                style=discord.ButtonStyle.success
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Delete Project",
                custom_id=f"delete_project_{current_project_name}_{'completed' if completed else 'ongoing'}",
                style=discord.ButtonStyle.danger
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Next ➡️",
                custom_id=f"navigate_next_{current_project_name}",
                style=discord.ButtonStyle.secondary
            )
        )

        return view

    async def navigate_admin_projects(self, interaction: discord.Interaction, direction: str, completed: bool):
        if completed:
            projects = await self.config.guild(interaction.guild).completed_projects()
        else:
            projects = await self.config.guild(interaction.guild).projects()

        project_names = list(projects.keys())
        current_project_name = interaction.data['custom_id'].split("_")[2]
        current_index = project_names.index(current_project_name)

        if direction == "previous":
            new_index = (current_index - 1) % len(project_names)
        else:
            new_index = (current_index + 1) % len(project_names)

        new_embed = self.create_embed(projects, project_names, new_index, interaction.user)
        view = self.create_admin_project_view(project_names, new_index, interaction.user, completed)

        await interaction.response.edit_message(embed=new_embed, view=view)

    def display_project_name(self, project: str) -> str:
        return project.replace("_", " ").title()

    def normalize_project_name(self, project: str) -> str:
        return project.replace(" ", "_").lower()

def setup(bot):
    bot.add_cog(recToken(bot))
