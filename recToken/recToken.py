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
            "personal_projects": {}  # Server-wide personal projects
        }

        default_user = {
            "credits": 0,
            "completed_personal_projects": {}  # User-specific completed projects
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_user(**default_user)

    @commands.command()
    async def menu(self, ctx):
        embed = discord.Embed(
            title="Command Menu",
            description="Use the buttons below to view projects, check your credits, or view completed projects.",
            color=discord.Color.blue()
        )
    
        view_projects_button = discord.ui.Button(label="View Projects", custom_id="viewprojects", style=discord.ButtonStyle.primary)
        check_credits_button = discord.ui.Button(label="Check Credits", custom_id="checkcredits", style=discord.ButtonStyle.success)
        view_completed_projects_button = discord.ui.Button(label="View Completed Projects", custom_id="viewcompletedprojects", style=discord.ButtonStyle.secondary)
    
        view = discord.ui.View()
        view.add_item(view_projects_button)
        view.add_item(check_credits_button)
        view.add_item(view_completed_projects_button)
    
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
         elif custom_id.startswith("donate_personal_"):
                project_name = custom_id.split("_", 2)[-1]
                await self.ask_donation_amount(interaction, project_name, guild_level=False)

            


    async def view_completed_projects_interaction(self, interaction: discord.Interaction):
        completed_projects = await self.config.guild(interaction.guild).completed_projects()
    
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
        else:  # direction == "next"
            new_index = (current_index + 1) % len(project_names)
    
        new_embed = self.create_embed(completed_projects, project_names, new_index, interaction.user)
        view = self.create_completed_project_view(project_names, new_index, interaction.user)
    
        await interaction.response.edit_message(embed=new_embed, view=view)



    async def viewprojects(self, interaction: discord.Interaction):
        projects = await self.config.guild(interaction.guild).projects()
        if not projects:
            await interaction.followup.send(embed=discord.Embed(description="No ongoing projects.", color=discord.Color.red()), ephemeral=True)
        else:
            project_names = list(projects.keys())
            initial_index = 0
            initial_embed = self.create_embed(projects, project_names, initial_index, interaction.user)
            view = self.create_project_view(project_names, initial_index, interaction.user)

            await interaction.followup.send(embed=initial_embed, view=view)

            # Check if the user has the "Admin" role and show the Admin Panel
            if any(role.name == "Admin" for role in interaction.user.roles):
                await self.send_admin_panel(interaction, project_names[initial_index])
   
    async def navigate_projects(self, interaction: discord.Interaction, direction: str):
        projects = await self.config.guild(interaction.guild).projects()
        project_names = list(projects.keys())
    
        current_project_name = interaction.data['custom_id'].split("_", 2)[-1]
        current_index = project_names.index(current_project_name)
    
        if direction == "previous":
            new_index = (current_index - 1) % len(project_names)
        else:  # direction == "next"
            new_index = (current_index + 1) % len(project_names)
    
        new_embed = self.create_embed(projects, project_names, new_index, interaction.user)
        view = self.create_project_view(project_names, new_index, interaction.user)
    
        # Update the main project view
        await interaction.response.edit_message(embed=new_embed, view=view)
    
        # Update the admin panel if the user has the Admin role
        if any(role.name == "Admin" for role in interaction.user.roles):
            await self.edit_admin_panel(interaction, project_names[new_index], completed=False)



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

    def create_project_view(self, project_names, index, user):
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
        self.admin_messages[interaction.user.id] = message  # Store message per user

    async def edit_admin_panel(self, interaction: discord.Interaction, project_name: str, completed: bool = False):
        view = discord.ui.View()
    
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
    
    async def ask_donation_amount(self, interaction: discord.Interaction, project_name: str, guild_level: bool):
        def check(message):
            return message.author == interaction.user and message.channel == interaction.channel
    
        await interaction.response.send_message(embed=discord.Embed(description="Please enter the amount of credits you would like to donate or type 'all' to donate all your credits.", color=discord.Color.blue()), ephemeral=True)
    
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            amount = msg.content.lower()
    
            user_credits = await self.config.user(interaction.user).credits()
    
            # Fetch the correct project based on guild or personal level
            if guild_level:
                projects = await self.config.guild(interaction.guild).projects()
            else:
                projects = await self.config.guild(interaction.guild).personal_projects()
    
            if project_name not in projects:
                return await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project_name)}' not found.", color=discord.Color.red()), ephemeral=True)
    
            current_credits = projects[project_name]["current_credits"]
            required_credits = projects[project_name]["required_credits"]
    
            max_donatable = required_credits - current_credits
    
            if amount == 'all':
                amount_to_donate = min(user_credits, max_donatable)
            else:
                amount_to_donate = int(amount)
                if amount_to_donate > max_donatable:
                    amount_to_donate = max_donatable
    
            await self.donatecredits(interaction, project_name, amount_to_donate, guild_level=guild_level)
        except ValueError:
            await interaction.followup.send(embed=discord.Embed(description="Invalid amount entered. Please try again.", color=discord.Color.red()), ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send(embed=discord.Embed(description="You took too long to respond. Please try again.", color=discord.Color.red()), ephemeral=True)


    async def donatecredits(self, interaction: discord.Interaction, project_name: str, amount_to_donate: int, guild_level: bool):
        if guild_level:
            async with self.config.guild(interaction.guild).projects() as projects:
                if project_name not in projects:
                    return await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project_name)}' not found.", color=discord.Color.red()), ephemeral=True)
    
                current_credits = projects[project_name]["current_credits"]
                required_credits = projects[project_name]["required_credits"]
        else:
            async with self.config.guild(interaction.guild).personal_projects() as personal_projects:
                if project_name not in personal_projects:
                    return await interaction.followup.send(embed=discord.Embed(description=f"Personal project '{self.display_project_name(project_name)}' not found.", color=discord.Color.red()), ephemeral=True)
    
                current_credits = personal_projects[project_name]["current_credits"]
                required_credits = personal_projects[project_name]["required_credits"]
    
        user_credits = await self.config.user(interaction.user).credits()
    
        max_donatable = required_credits - current_credits
    
        if amount_to_donate > max_donatable:
            amount_to_donate = max_donatable
    
        if amount_to_donate > user_credits:
            return await interaction.followup.send(embed=discord.Embed(description="You don't have enough credits.", color=discord.Color.red()), ephemeral=True)
    
        # Update credits and mark project progress
        if guild_level:
            projects[project_name]["current_credits"] += amount_to_donate
        else:
            personal_projects[project_name]["current_credits"] += amount_to_donate
    
        new_credits = user_credits - amount_to_donate
        await self.config.user(interaction.user).credits.set(new_credits)
    
        await interaction.followup.send(embed=discord.Embed(description=f"{interaction.user.name} donated {amount_to_donate} credits to '{self.display_project_name(project_name)}'.", color=discord.Color.green()), ephemeral=False)
    
        # Check if project is fully funded and mark as complete
        if (guild_level and projects[project_name]["current_credits"] >= required_credits) or (not guild_level and personal_projects[project_name]["current_credits"] >= required_credits):
            await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project_name)}' is now fully funded!", color=discord.Color.gold()), ephemeral=False)
    
            if guild_level:
                async with self.config.guild(interaction.guild).completed_projects() as completed_projects:
                    completed_projects[project_name] = projects[project_name]
                del projects[project_name]
            else:
                # Mark as completed for the user
                async with self.config.user(interaction.user).completed_personal_projects() as completed_projects:
                    completed_projects[project_name] = personal_projects[project_name]
                del personal_projects[project_name]

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
    


    ### Command for Users to View and Build Personal Projects ###
    @commands.command()
    async def personal_projects(self, ctx):
        """View and build server-wide personal projects."""
        projects = await self.config.guild(ctx.guild).personal_projects()
        
        if not projects:
            await ctx.send(embed=discord.Embed(description="No personal projects available yet.", color=discord.Color.red()))
            return

        project_names = list(projects.keys())
        initial_index = 0
        embed = self.create_personal_project_embed(projects, project_names, initial_index)
        view = self.create_personal_project_view(project_names, initial_index)

        await ctx.send(embed=embed, view=view)

    def create_personal_project_embed(self, projects, project_names, index):
        project_name = project_names[index]
        project = projects[project_name]
        
        prereqs_met = "Yes" if project.get("prereqs_met", True) else "No"
        percent_complete = (project["current_credits"] / project["required_credits"]) * 100 if project["required_credits"] > 0 else 100

        embed = discord.Embed(
            title=f"Personal Project: {self.display_project_name(project_name)}",
            description=project["description"] or "No description available.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Prerequisites Met", value=prereqs_met, inline=False)
        embed.add_field(name="Credits", value=f"{project['current_credits']}/{project['required_credits']} credits", inline=False)
        embed.add_field(name="% Complete", value=f"{percent_complete:.2f}% complete", inline=False)

        return embed


    def create_personal_project_view(self, project_names, index):
        current_project_name = project_names[index]
        view = discord.ui.View()

        view.add_item(
            discord.ui.Button(
                label="⬅️ Previous",
                custom_id=f"navigate_personal_previous_{current_project_name}",
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
                custom_id=f"navigate_personal_next_{current_project_name}",
                style=discord.ButtonStyle.secondary
            )
        )

        return view

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def add_personal_project(self, ctx, project: str, required_credits: int, prereqs: str = None):
        """Add a server-wide personal project (Admin only)."""
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).personal_projects() as personal_projects:
            prereqs_met = prereqs is None  # If no prereqs, project is buildable immediately
            personal_projects[project] = {
                "required_credits": required_credits,
                "current_credits": 0,
                "thumbnail": "",
                "description": "",
                "prereqs_met": prereqs_met,
                "prereqs": prereqs or "None"
            }

        await ctx.send(embed=discord.Embed(description=f"Personal project '{self.display_project_name(project)}' added server-wide.", color=discord.Color.green()))


    async def build_personal_project(self, interaction: discord.Interaction, project_name: str):
        project = self.normalize_project_name(project_name)
        async with self.config.guild(interaction.guild).personal_projects() as personal_projects:
            if project not in personal_projects:
                await interaction.response.send_message(f"Project '{self.display_project_name(project)}' not found.", ephemeral=True)
                return
            
            project_data = personal_projects[project]

            if not project_data.get("prereqs_met", True):
                await interaction.response.send_message(f"Prerequisites for project '{self.display_project_name(project)}' are not met.", ephemeral=True)
                return

            # Project can be built; Deduct credits and mark as completed for the user
            await self.complete_personal_project(interaction, project_name)
        
    async def complete_personal_project(self, interaction: discord.Interaction, project_name: str):
        user_credits = await self.config.user(interaction.user).credits()
        project = self.normalize_project_name(project_name)
        async with self.config.guild(interaction.guild).personal_projects() as personal_projects:
            if project not in personal_projects:
                return await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()), ephemeral=True)

            required_credits = personal_projects[project]["required_credits"]
            if user_credits < required_credits:
                return await interaction.followup.send(embed=discord.Embed(description="You don't have enough credits to complete this project.", color=discord.Color.red()), ephemeral=True)

            # Deduct credits and mark as complete
            await self.config.user(interaction.user).credits.set(user_credits - required_credits)
            async with self.config.user(interaction.user).completed_personal_projects() as completed_projects:
                completed_projects[project] = personal_projects[project]

            await interaction.followup.send(embed=discord.Embed(description=f"You have completed the personal project '{self.display_project_name(project)}'.", color=discord.Color.green()), ephemeral=False)

   
    ### View Completed Personal Projects for a User ###
    @commands.command()
    async def completed_personal_projects(self, ctx):
        """View the personal projects you have completed."""
        completed_projects = await self.config.user(ctx.author).completed_personal_projects()

        if not completed_projects:
            await ctx.send(embed=discord.Embed(description="You haven't completed any personal projects yet.", color=discord.Color.red()))
            return

        embed = discord.Embed(title="Completed Personal Projects", color=discord.Color.blue())
        
        for project_name, project_details in completed_projects.items():
            embed.add_field(
                name=self.display_project_name(project_name),
                value=f"Credits: {project_details['current_credits']}/{project_details['required_credits']}",
                inline=False
            )
    
        await ctx.send(embed=embed)



    ### Helper Methods ###
    def display_project_name(self, project: str) -> str:
        return project.replace("_", " ").title()

    def normalize_project_name(self, project: str) -> str:
        return project.replace(" ", "_").lower()






def setup(bot):
    bot.add_cog(recToken(bot))
