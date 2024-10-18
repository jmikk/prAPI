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
            "completed_projects": {},# Add this line to initialize completed projects
            "personal_projects":{}
        }
        defualt_user = {
            "credits" :0,
            "completed_personal_projects":{}
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_user(**defualt_user)


    @commands.command()
    async def menu(self, ctx):
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
            project_name = custom_id.split("_", 2)[-1]
            await self.send_edit_menu(interaction, project_name)
        elif custom_id.startswith("remove_project_"):
            project_name = custom_id.split("_", 2)[-1]
            await self.remove_project(interaction, project_name)
        elif custom_id.startswith("edit_field_"):
            field, project_name = custom_id.split("_")[2:]
            await self.prompt_edit_field(interaction, project_name, field)
        elif custom_id == "viewcompletedpersonalprojects":
            await interaction.response.defer()
            await self.view_completed_projects_interaction(interaction,guild_level = False)
        elif custom_id == "personalprojects":
            await interaction.response.defer()
            await self.viewprojects(interaction,guild_level = False)
        elif custom_id == "manage_ongoing_projects":
            await interaction.response.defer()
            await self.manage_projects(interaction, completed=False)
        elif custom_id == "manage_completed_projects":
            await interaction.response.defer()
            await self.manage_projects(interaction, completed=True)
            
                # Admin-specific interaction handling for manage menu
        elif custom_id == "manage_ongoing_projects":
            await interaction.response.defer()
            await self.manage_projects(interaction, completed=False)
        elif custom_id == "manage_completed_projects":
            await interaction.response.defer()
            await self.manage_projects(interaction, completed=True)
        elif custom_id.startswith("edit_project_"):
            project_name = custom_id.split("_", 2)[-1]
            await self.send_edit_menu(interaction, project_name)
        elif custom_id.startswith("remove_project_"):
            project_name = custom_id.split("_", 2)[-1]
            await self.remove_project(interaction, project_name)
        elif custom_id.startswith("admin_navigate_previous_"):
            await self.navigate_projects(interaction, "previous", admin_mode=True)
        elif custom_id.startswith("admin_navigate_next_"):
            await self.navigate_projects(interaction, "next", admin_mode=True)
        elif custom_id.startswith("admin_navigate_completed_previous_"):
            await self.navigate_completed_projects(interaction, "previous", admin_mode=True)
        elif custom_id.startswith("admin_navigate_completed_next_"):
            await self.navigate_completed_projects(interaction, "next",admin_mode=True)


    async def manage_projects(self, interaction: discord.Interaction, completed: bool):
        """Displays the list of ongoing or completed projects for admin management."""
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
        """Creates the view with buttons for navigating and managing ongoing or completed projects."""
        current_project_name = project_names[index]
        view = discord.ui.View()

        # Add navigation buttons
        view.add_item(
            discord.ui.Button(
                label="⬅️ Previous",
                custom_id=f"admin_navigate{'_completed' if completed else ''}_previous_{current_project_name}",
                style=discord.ButtonStyle.secondary
            )
        )
        if not completed:
            view.add_item(
                discord.ui.Button(
                    label="Edit Project",
                    custom_id=f"edit_project_{current_project_name}",
                    style=discord.ButtonStyle.success
                )
            )
        view.add_item(
            discord.ui.Button(
                label="Delete Project",
                custom_id=f"remove_project_{current_project_name}",
                style=discord.ButtonStyle.danger
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Next ➡️",
                custom_id=f"admin_navigate{'_completed' if completed else ''}_next_{current_project_name}",
                style=discord.ButtonStyle.secondary
            )
        )

        return view
    
    # Update the admin-specific navigation logic to keep it in admin mode:
    async def navigate_admin_projects(self, interaction: discord.Interaction, direction: str, completed: bool):
        projects = await self.config.guild(interaction.guild).completed_projects() if completed else await self.config.guild(interaction.guild).projects()
    
        project_names = list(projects.keys())
        current_project_name = interaction.data['custom_id'].split("_", 3)[-1]
        current_index = project_names.index(current_project_name)
    
        if direction == "previous":
            new_index = (current_index - 1) % len(project_names)
        else:  # direction == "next"
            new_index = (current_index + 1) % len(project_names)
    
        # Create the embed and view for admin mode
        new_embed = self.create_embed(projects, project_names, new_index, interaction.user)
        view = self.create_admin_project_view(project_names, new_index, interaction.user, completed=completed)
    
        await interaction.response.edit_message(embed=new_embed, view=view)


    




    async def view_completed_projects_interaction(self, interaction: discord.Interaction,guild_level = True):
        if guild_level:
            completed_projects = await self.config.guild(interaction.guild).completed_projects()
        else:
            completed_projects = await self.config.user(interaction.guild).completed_personal_projects()

    
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

    # Similarly, for navigating completed projects:
    async def navigate_completed_projects(self, interaction: discord.Interaction, direction: str, admin_mode=False):
        completed_projects = await self.config.guild(interaction.guild).completed_projects()
        project_names = list(completed_projects.keys())

        if admin_mode:
            current_project_name = interaction.data['custom_id'].split("_", 4)[-1]
        else:
            current_project_name = interaction.data['custom_id'].split("_", 3)[-1]

        
        current_index = project_names.index(current_project_name)
        
        if direction == "previous":
            new_index = (current_index - 1) % len(project_names)
        else:  # direction == "next"
            new_index = (current_index + 1) % len(project_names)
        
        # Create the embed for the new project
        new_embed = self.create_embed(completed_projects, project_names, new_index, interaction.user)
        
        # Determine which view to send based on the mode
        if admin_mode:
            view = self.create_admin_project_view(project_names, new_index, interaction.user, completed=True)
        else:
            view = self.create_completed_project_view(project_names, new_index, interaction.user)
        
        # Update the message with the new embed and view
        await interaction.response.edit_message(embed=new_embed, view=view)



    async def viewprojects(self, interaction: discord.Interaction, guild_level=True):
        if guild_level:
            # Fetch guild-level projects
            projects = await self.config.guild(interaction.guild).projects()
        else:
            # Fetch all personal projects and completed personal projects
            all_personal_projects = await self.config.guild(interaction.guild).personal_projects()
            completed_personal_projects = await self.config.user(interaction.user).completed_personal_projects()
    
            # Fetch all guild-level projects
            guild_projects = await self.config.guild(interaction.guild).projects()
    
            # Filter personal projects that the user hasn't completed yet
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
            view = self.create_project_view(project_names, initial_index, interaction.user,guild_level)

            await interaction.followup.send(embed=initial_embed, view=view)

            # Check if the user has the "Admin" role and show the Admin Panel
            if any(role.name == "Admin" for role in interaction.user.roles):
                await self.send_admin_panel(interaction, project_names[initial_index])

        # Helper method to check if the user meets the prerequisites for a project
    def has_prerequisites(self, user, project_data, completed_personal_projects, guild_projects):
        # Prerequisites are expected to be a list of project names
        prereqs = project_data.get("prereqs", [])
        
        for prereq in prereqs:
            # Check if the prerequisite is a completed personal project or an active guild-level project
            if prereq not in completed_personal_projects and prereq not in guild_projects:
                return False  # Prerequisite not met
        
        return True  # All prerequisites are met
   
    async def navigate_projects(self, interaction: discord.Interaction, direction: str, guild_level=True, admin_mode=False):
        if guild_level:
            projects = await self.config.guild(interaction.guild).projects()
        else:
            projects = await self.config.user(interaction.user).personal_projects()
        
        project_names = list(projects.keys())


        if admin_mode:
            current_project_name = interaction.data['custom_id'].split("_", 3)[-1]
        else:
            current_project_name = interaction.data['custom_id'].split("_", 2)[-1]
        
        current_index = project_names.index(current_project_name)
        
        # Navigate between projects
        if direction == "previous":
            new_index = (current_index - 1) % len(project_names)
        else:  # direction == "next"
            new_index = (current_index + 1) % len(project_names)
        
        # Create the embed for the new project
        new_embed = self.create_embed(projects, project_names, new_index, interaction.user)
        
        # Determine which view to send based on the mode
        if admin_mode:
            # Admin mode - Show admin-specific navigation and options
            view = self.create_admin_project_view(project_names, new_index, interaction.user, completed=False)
        else:
            # Regular mode - Show the normal project view
            view = self.create_project_view(project_names, new_index, interaction.user, guild_level)
        
        # Update the message with the new embed and view
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

    def create_project_view(self, project_names, index, user, guild_level = True):
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
        else:
            view.add_item(
                discord.ui.Button(
                    label="⬅️ Previous",
                    custom_id=f"navigate_previous_personal_{current_project_name}",
                    style=discord.ButtonStyle.secondary
                )
            )
        
            view.add_item(
                discord.ui.Button(
                    label="Donate Credits",
                    custom_id=f"donate_personal_{current_project_name}",
                    style=discord.ButtonStyle.primary
                )
            )
        
            view.add_item(
                discord.ui.Button(
                    label="Next ➡️",
                    custom_id=f"navigate_next_personal_{current_project_name}",
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
        self.admin_messages[interaction.user.id] = message  # Store message per user

    async def edit_admin_panel(self, interaction: discord.Interaction, project_name: str, completed: bool = False,guild_level = True):
        view = discord.ui.View()
        if guild_level:
            view.add_item(
                discord.ui.Button(
                    label="Edit Project",
                    custom_id=f"edit_project_{project_name}_{'completed' if completed else 'inprogress'}",
                    style=discord.ButtonStyle.success
                )
            )
        
            view.add_item(
                discord.ui.Button(
                    label="Remove Project",
                    custom_id=f"remove_project_{project_name}_{'completed' if completed else 'inprogress'}",
                    style=discord.ButtonStyle.danger
                )
            )
        
            embed = discord.Embed(
                title="Admin Panel",
                description=f"Manage the project: {self.display_project_name(project_name)}",
                color=discord.Color.gold()
            )
        else:
            view.add_item(
                discord.ui.Button(
                    label="Edit Project",
                    custom_id=f"edit_project_personal_{project_name}_{'completed' if completed else 'inprogress'}",
                    style=discord.ButtonStyle.success
                )
            )
        
            view.add_item(
                discord.ui.Button(
                    label="Remove Project",
                    custom_id=f"remove_project_personal_{project_name}_{'completed' if completed else 'inprogress'}",
                    style=discord.ButtonStyle.danger
                )
            )
        
            embed = discord.Embed(
                title="Admin Panel",
                description=f"Manage the project: {self.display_project_name(project_name)}",
                color=discord.Color.gold()
            )
    
        # Find and update the existing admin panel message
        if interaction.user.id in self.admin_messages:
            message = self.admin_messages[interaction.user.id]
            await message.edit(embed=embed, view=view)
        else:
            # If there's no existing message, create one
            message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            self.admin_messages[interaction.user.id] = message  # Store message per user

    async def send_edit_menu(self, interaction: discord.Interaction, project_name: str):
        view = discord.ui.View()

        view.add_item(
            discord.ui.Button(
                label="Edit Description",
                custom_id=f"edit_field_description_{project_name}",
                style=discord.ButtonStyle.primary
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Edit Thumbnail",
                custom_id=f"edit_field_thumbnail_{project_name}",
                style=discord.ButtonStyle.primary
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Edit Emoji",
                custom_id=f"edit_field_emoji_{project_name}",
                style=discord.ButtonStyle.primary
            )
        )

        embed = discord.Embed(
            title=f"Edit Project: {self.display_project_name(project_name)}",
            description="Choose the field you want to edit:",
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def prompt_edit_field(self, interaction: discord.Interaction, project_name: str, field: str):
        await interaction.response.send_message(embed=discord.Embed(
            description=f"Please enter the new value for **{field.capitalize()}**:",
            color=discord.Color.blue()
        ), ephemeral=True)

        def check(message):
            return message.author == interaction.user and message.channel == interaction.channel

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            new_value = msg.content

            await self.update_project_field(interaction, project_name, field, new_value)
        except asyncio.TimeoutError:
            await interaction.followup.send(embed=discord.Embed(description="You took too long to respond. Please try again.", color=discord.Color.red()), ephemeral=True)

    async def update_project_field(self, interaction: discord.Interaction, project_name: str, field: str, new_value: str):
        project = self.normalize_project_name(project_name)
        async with self.config.guild(interaction.guild).projects() as projects:
            if project not in projects:
                await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()), ephemeral=True)
                return

            projects[project][field] = new_value

        await interaction.followup.send(embed=discord.Embed(description=f"{field.capitalize()} for project '{self.display_project_name(project_name)}' updated successfully.", color=discord.Color.green()), ephemeral=True)

    async def admin_panel(self, interaction: discord.Interaction, custom_id: str):
        if custom_id.startswith("edit_project_"):
            project_name = custom_id.split("_", 2)[-1]
            await self.send_edit_menu(interaction, project_name)
        elif custom_id.startswith("remove_project_"):
            project_name = custom_id.split("_", 2)[-1]
            await self.remove_project(interaction, project_name)

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
    
            # Calculate the maximum amount that can be donated
            max_donatable = required_credits - current_credits
    
            # If the user tries to donate more than what is needed, adjust the donation amount
            if amount_to_donate > max_donatable:
                amount_to_donate = max_donatable
    
            if amount_to_donate > user_credits:
                return await interaction.followup.send(embed=discord.Embed(description="You don't have enough credits.", color=discord.Color.red()), ephemeral=True)
        
            projects[project]["current_credits"] += amount_to_donate
        
            new_credits = user_credits - amount_to_donate
            await self.config.user(interaction.user).credits.set(new_credits)
    
            await interaction.followup.send(embed=discord.Embed(description=f"{interaction.user.name} donated {amount_to_donate} credits to '{self.display_project_name(project)}'.", color=discord.Color.green()), ephemeral=False)
    
            # Check if the project is now complete
            if projects[project]["current_credits"] >= required_credits:
                await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' is now fully funded!", color=discord.Color.gold()), ephemeral=False)
    
                # Move the project from in-progress to completed
                async with self.config.guild(interaction.guild).completed_projects() as completed_projects:
                    completed_projects[project] = projects[project]
    
                # Remove the project from the in-progress list
                del projects[project]
    
                #await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' has been moved to the completed projects list.", color=discord.Color.green()), ephemeral=False)

    async def checkcredits(self, interaction: discord.Interaction):
        credits = await self.config.user(interaction.user).credits()

        embed = discord.Embed(
            title="Your Credits",
            description=f"You currently have **{credits}** credits.",
            color=discord.Color.green()
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def edit_project(self, interaction: discord.Interaction, project_name: str):
        # Triggering the edit process now sends a menu
        await self.send_edit_menu(interaction, project_name)

    async def remove_project(self, interaction: discord.Interaction, project_name: str):
        project = self.normalize_project_name(project_name)
        
        # Fetch the current projects
        async with self.config.guild(interaction.guild).projects() as projects:
            if project not in projects:
                # Respond if the project is not found
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"Project '{self.display_project_name(project)}' not found.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return
    
            # Remove the project
            del projects[project]
    
        # Send a confirmation message that the project was removed
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Project '{self.display_project_name(project_name)}' has been removed.",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
    
        # Update the admin panel or indicate that there are no more projects left
        remaining_projects = await self.config.guild(interaction.guild).projects()
        if remaining_projects:
            first_project_name = next(iter(remaining_projects))
            await self.edit_admin_panel(interaction, first_project_name)
        else:
            # If no projects are left, update the admin panel to indicate that
            if interaction.user.id in self.admin_messages:
                message = self.admin_messages[interaction.user.id]
                await message.edit(embed=discord.Embed(
                    title="Admin Panel",
                    description="No projects left to manage.",
                    color=discord.Color.gold()
                ), view=None)

    @commands.command()
    @commands.is_owner()
    async def givecredits(self, ctx, user: discord.User, amount: int):
        current_credits = await self.config.user(user).credits()
        new_credits = current_credits + amount
        await self.config.user(user).credits.set(new_credits)
        await ctx.send(embed=discord.Embed(description=f"{amount} credits given to {user.name}.", color=discord.Color.green()))

    @commands.command()
    @commands.is_owner()
    async def removeproject(self, ctx, project: str):
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).projects() as projects:
            if project not in projects:
                return await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()))
    
            del projects[project]
    
        await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' has been removed.", color=discord.Color.green()))

    @commands.command()
    @commands.is_owner()
    async def addproject(self, ctx, project: str, required_credits: int, emoji: str = "💰"):
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).projects() as projects:
            projects[project] = {
                "required_credits": required_credits,
                "current_credits": 0,
                "thumbnail": "",
                "description": "",
                "emoji": emoji
            }
    
        await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' added with {required_credits} credits needed.", color=discord.Color.green()))

    @commands.command()
    @commands.is_owner()
    async def addpersonalproject(self, ctx, project: str, required_credits: int,prereq = []):
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).personal_projects() as projects:
            projects[project] = {
                "required_credits": required_credits,
                "current_credits": 0,
                "thumbnail": "",
                "description": "",
                "emoji": "💰",
                "prereqs": prereq
            }
    
        await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' added with {required_credits} credits needed.", color=discord.Color.green()))

    @commands.command()
    @commands.is_owner()
    async def editproject(self, ctx, project: str, description: str = None, thumbnail: str = None, emoji: str = None):
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).projects() as projects:
            if project not in projects:
                return await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()))
            
            if thumbnail:
                projects[project]["thumbnail"] = thumbnail
            if description:
                projects[project]["description"] = description
            if emoji:
                projects[project]["emoji"] = emoji

        await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' updated.", color=discord.Color.green()))

    def display_project_name(self, project: str) -> str:
        return project.replace("_", " ").title()

    def normalize_project_name(self, project: str) -> str:
        return project.replace(" ", "_").lower()

    @commands.command()
    async def view_completed_projects(self, ctx):
        completed_projects = await self.config.guild(ctx.guild).completed_projects()
    
        if not completed_projects:
            await ctx.send(embed=discord.Embed(description="No completed projects yet.", color=discord.Color.red()))
            return
    
        embed = discord.Embed(title="Completed Projects", color=discord.Color.blue())
        
        for project_name, project_details in completed_projects.items():
            embed.add_field(
                name=self.display_project_name(project_name),
                value=f"Credits: {project_details['current_credits']}/{project_details['required_credits']}",
                inline=False
            )
    
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def deletecompletedproject(self, ctx, project: str):
        project = self.normalize_project_name(project)
        
        async with self.config.guild(ctx.guild).completed_projects() as completed_projects:
            if project not in completed_projects:
                await ctx.send(embed=discord.Embed(description=f"Completed project '{self.display_project_name(project)}' not found.", color=discord.Color.red()))
                return
            
            # Delete the project
            del completed_projects[project]
    
        await ctx.send(embed=discord.Embed(description=f"Completed project '{self.display_project_name(project)}' has been successfully deleted.", color=discord.Color.green()))
    

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def admin_menu(self, ctx):
        """Displays the admin menu for managing ongoing and completed projects."""
        
        embed = discord.Embed(
            title="Admin Project Management",
            description="Use the buttons below to manage ongoing and completed projects.",
            color=discord.Color.gold()
        )

        # Buttons to manage ongoing and completed projects
        view_ongoing_projects_button = discord.ui.Button(
            label="Manage Ongoing Projects", custom_id="manage_ongoing_projects", style=discord.ButtonStyle.primary
        )
        #view_completed_projects_button = discord.ui.Button(
        #    label="Manage Completed Projects", custom_id="manage_completed_projects", style=discord.ButtonStyle.success
        #)

        view = discord.ui.View()
        view.add_item(view_ongoing_projects_button)
        view.add_item(view_completed_projects_button)

        await ctx.send(embed=embed, view=view)

def setup(bot):
    bot.add_cog(recToken(bot))
