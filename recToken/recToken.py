import discord
from discord.ext import commands
from redbot.core import Config, commands

class recToken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=23456789648)
        self.admin_messages = {}  # Store admin panel messages

        default_guild = {
            "projects": {}
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_user(credits=0)

    @commands.command()
    async def menu(self, ctx):
        embed = discord.Embed(
            title="Command Menu",
            description="Use the buttons below to view projects or check your credits.",
            color=discord.Color.blue()
        )

        view_projects_button = discord.ui.Button(label="View Projects", custom_id="viewprojects", style=discord.ButtonStyle.primary)
        check_credits_button = discord.ui.Button(label="Check Credits", custom_id="checkcredits", style=discord.ButtonStyle.success)

        view = discord.ui.View()
        view.add_item(view_projects_button)
        view.add_item(check_credits_button)

        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        custom_id = interaction.data['custom_id']

        if custom_id == "viewprojects":
            await interaction.response.defer()
            await self.viewprojects(interaction)
        elif custom_id == "checkcredits":
            await interaction.response.defer()
            await self.checkcredits(interaction)
        elif custom_id.startswith("navigate_previous_"):
            await self.navigate_projects(interaction, "previous")
        elif custom_id.startswith("navigate_next_"):
            await self.navigate_projects(interaction, "next")
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

        await interaction.response.edit_message(embed=new_embed, view=view)

        # Check if the user has the "Admin" role and update the Admin Panel
        if any(role.name == "Admin" for role in interaction.user.roles):
            await self.edit_admin_panel(interaction, project_names[new_index])

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

    async def edit_admin_panel(self, interaction: discord.Interaction, project_name: str):
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

        if interaction.user.id in self.admin_messages:
            message = self.admin_messages[interaction.user.id]
            await message.edit(embed=embed, view=view)

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

            if amount == 'all':
                amount_to_donate = await self.config.user(interaction.user).credits()
            else:
                amount_to_donate = int(amount)

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
    
            if amount_to_donate > user_credits:
                return await interaction.followup.send(embed=discord.Embed(description="You don't have enough credits.", color=discord.Color.red()), ephemeral=True)
    
            projects[project]["current_credits"] += amount_to_donate
    
            new_credits = user_credits - amount_to_donate
            await self.config.user(interaction.user).credits.set(new_credits)

            await interaction.followup.send(embed=discord.Embed(description=f"{interaction.user.name} donated {amount_to_donate} credits to '{self.display_project_name(project)}'.", color=discord.Color.green()), ephemeral=False)

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
        async with self.config.guild(interaction.guild).projects() as projects:
            if project not in projects:
                return await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()), ephemeral=True)
    
            del projects[project]

        await interaction.followup.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project_name)}' has been removed.", color=discord.Color.green()), ephemeral=False)

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

def setup(bot):
    bot.add_cog(recToken(bot))
