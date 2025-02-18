import random
import asyncio
import discord
import uuid
from collections import Counter
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from discord.ui import View, Button, TextInput, Modal

class CompletedPersonalProjectsMenu(View):
    def __init__(self, cog, user, projects):
        super().__init__()
        self.cog = cog
        self.user = user
        self.projects = projects
        self.current_index = 0
        
        self.left_button = Button(label="◀", style=discord.ButtonStyle.blurple)
        self.left_button.callback = self.previous_project
        
        self.right_button = Button(label="▶", style=discord.ButtonStyle.blurple)
        self.right_button.callback = self.next_project
        
        self.add_item(self.left_button)
        self.add_item(self.right_button)
        
    async def update_message(self):
        if not self.projects:
            await self.message.edit(content="No completed personal projects.", view=None)
            return
        
        project = self.projects[self.current_index]
        embed = discord.Embed(
            title=f"{project['name']} (Completed)",
            description=f"Goal: {project['goal']} WellCoins\nFunded: {project['goal']} WellCoins",
            color=discord.Color.green()
        )
        if 'thumbnail' in project:
            embed.set_thumbnail(url=project['thumbnail'])
        embed.set_footer(text=f"Project ID: {project['id']}")
        await self.message.edit(embed=embed, view=self)
    
    async def previous_project(self, interaction: discord.Interaction):
        self.current_index = (self.current_index - 1) % len(self.projects)
        await self.update_message()
        await interaction.response.defer()
    
    async def next_project(self, interaction: discord.Interaction):
        self.current_index = (self.current_index + 1) % len(self.projects)
        await self.update_message()
        await interaction.response.defer()

class PersonalFundingMenu(View):
    def __init__(self, cog, user, projects):
        super().__init__()
        self.cog = cog
        self.user = user
        self.projects = projects
        self.current_index = 0

        self.fund_button = Button(label="Fund", style=discord.ButtonStyle.green)
        self.fund_button.callback = self.fund_project
        
        self.left_button = Button(label="◀", style=discord.ButtonStyle.blurple)
        self.left_button.callback = self.previous_project
        
        self.right_button = Button(label="▶", style=discord.ButtonStyle.blurple)
        self.right_button.callback = self.next_project
        
        self.add_item(self.left_button)
        self.add_item(self.fund_button)
        self.add_item(self.right_button)

    async def update_message(self):
        if not self.projects:
            await self.message.edit(content="No personal projects available.", view=None)
            return
        
        project = self.projects[self.current_index]
        percentage_funded = (project['funded'] / project['goal']) * 100
        embed = discord.Embed(
            title=f"{project['name']}",
            description=f"Goal: {project['goal']} WellCoins\nFunded: {project['funded']} WellCoins ({percentage_funded:.2f}% Funded)\nPrerequisites: {', '.join(project['prerequisites']) if project['prerequisites'] else 'None'}",
            color=discord.Color.blue()
        )
        if 'thumbnail' in project:
            embed.set_thumbnail(url=project['thumbnail'])
        embed.set_footer(text=f"Project ID: {project['id']}")
        await self.message.edit(embed=embed, view=self)

    async def previous_project(self, interaction: discord.Interaction):
        self.current_index = (self.current_index - 1) % len(self.projects)
        await self.update_message()
        await interaction.response.defer()
    
    async def next_project(self, interaction: discord.Interaction):
        self.current_index = (self.current_index + 1) % len(self.projects)
        await self.update_message()
        await interaction.response.defer()
    
    async def fund_project(self, interaction: discord.Interaction):
        user_balance = await self.cog.get_balance(self.user)
        modal = FundPersonalModal(self, user_balance)
        await interaction.response.send_modal(modal)

class FundPersonalModal(Modal):
    def __init__(self, menu, user_balance):
        super().__init__(title="Fund Personal Project")
        self.menu = menu
        self.user_balance = user_balance
        self.input = TextInput(label="Amount to Donate", placeholder=f"Max: {user_balance}")
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        amount = self.input.value.lower()
        if amount == "all":
            amount = self.user_balance
        else:
            try:
                amount = int(amount)
                if amount <= 0 or amount > self.user_balance:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message("Invalid amount!", ephemeral=True)
                return
        
        project = self.menu.projects[self.menu.current_index]
        project['funded'] += amount
        await self.menu.cog.update_balance(self.menu.user, -amount)
        
        if project['funded'] >= project['goal']:
            self.menu.projects.pop(self.menu.current_index)
            completed_projects = await self.menu.cog.get_completed_personal_projects(self.menu.user)
            completed_projects[project['id']] = project['name']
            await self.menu.cog.update_completed_personal_projects(self.menu.user, completed_projects)
            await self.menu.cog.update_personal_projects(self.menu.user, self.menu.projects)
            await interaction.response.send_message(f"Personal project '{project['name']}' is fully funded and completed! 🎉",ephemeral=True)
        else:
            await self.menu.update_message()
            await interaction.response.defer()
            await self.menu.cog.update_personal_projects(self.menu.user, self.menu.projects)

class CompletedProjectsMenu(View):
    def __init__(self, cog, ctx, projects):
        super().__init__()
        self.cog = cog
        self.ctx = ctx
        self.projects = projects
        self.current_index = 0
        
        self.left_button = Button(label="◀", style=discord.ButtonStyle.blurple)
        self.left_button.callback = self.previous_project
        
        self.right_button = Button(label="▶", style=discord.ButtonStyle.blurple)
        self.right_button.callback = self.next_project
        
        self.add_item(self.left_button)
        self.add_item(self.right_button)
        
    async def update_message(self):
        if not self.projects:
            await self.message.edit(content="No completed projects.", view=None)
            return
        
        project = self.projects[self.current_index]
        embed = discord.Embed(
            title=f"{project['name']} (Completed)",
            description=f"{project['description']}\n\nTotal Funded: {project['goal']} WellCoins",
            color=discord.Color.green()
        )
        if 'thumbnail' in project:
            embed.set_thumbnail(url=project['thumbnail'])
        embed.set_footer(text=f"Project ID: {project['id']}")
        await self.message.edit(embed=embed, view=self)
    
    async def previous_project(self, interaction: discord.Interaction):
        self.current_index = (self.current_index - 1) % len(self.projects)
        await self.update_message()
        await interaction.response.defer()
    
    async def next_project(self, interaction: discord.Interaction):
        self.current_index = (self.current_index + 1) % len(self.projects)
        await self.update_message()
        await interaction.response.defer()

class FundingMenu(View):
    def __init__(self, cog, ctx, projects):
        super().__init__()
        self.cog = cog
        self.ctx = ctx
        self.projects = projects
        self.current_index = 0
        
        self.fund_button = Button(label="Fund", style=discord.ButtonStyle.green)
        try:
            self.fund_button.callback = self.fund_project
        except Exception as e:
            print(f"Error initializing fund button: {e}")
        
        self.left_button = Button(label="◀", style=discord.ButtonStyle.blurple)
        self.left_button.callback = self.previous_project
        
        self.right_button = Button(label="▶", style=discord.ButtonStyle.blurple)
        self.right_button.callback = self.next_project
        
        self.add_item(self.left_button)
        self.add_item(self.fund_button)
        self.add_item(self.right_button)
        
    async def update_message(self):
        if not self.projects:
            await self.message.edit(content="No ongoing projects.", view=None)
            return
        
        project = self.projects[self.current_index]
        percentage_funded = (project['funded'] / project['goal']) * 100
        embed = discord.Embed(
            title=f"{project['name']}",
            description=f"{project['description']}\n\nTotal Needed: {project['goal']} WellCoins\nFunded: {project['funded']} WellCoins ({percentage_funded:.2f}% Funded)",
            color=discord.Color.gold()
        )
        if 'thumbnail' in project:
            embed.set_thumbnail(url=project['thumbnail'])
        embed.set_footer(text=f"Project ID: {project['id']}")
        await self.message.edit(embed=embed, view=self)
    
    async def previous_project(self, interaction: discord.Interaction):
        self.current_index = (self.current_index - 1) % len(self.projects)
        await self.update_message()
        await interaction.response.defer()
    
    async def next_project(self, interaction: discord.Interaction):
        self.current_index = (self.current_index + 1) % len(self.projects)
        await self.update_message()
        await interaction.response.defer()
    
    async def fund_project(self, interaction: discord.Interaction):
        try:
            user_balance = await self.cog.get_balance(interaction.user)
            modal = FundModal(self, user_balance)
            await interaction.response.send_modal(modal)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

class FundModal(Modal):
    def __init__(self, menu, user_balance):
        super().__init__(title="Fund Project")
        self.menu = menu
        self.user_balance = user_balance
        self.input = TextInput(label="Amount to Donate", placeholder=f"Max: {user_balance}")
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        amount = self.input.value.lower()
        if amount == "all":
            amount = self.user_balance
        else:
            try:
                amount = int(amount)
                if amount <= 0 or amount > self.user_balance:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message("Invalid amount!", ephemeral=True)
                return
        
        project = self.menu.projects[self.menu.current_index]
        project['funded'] += amount
        await self.menu.cog.update_balance(interaction.user, -amount)

        if project['funded'] >= project['goal']:
            await self.menu.update_message()
            await interaction.response.send_message(f"Project {project['name']} has been fully funded! 🎉")
            self.menu.projects.pop(self.menu.current_index)
            completed_projects = await self.menu.cog.get_completed_projects(interaction.guild)
            completed_projects.append(project)
            await self.menu.cog.update_completed_projects(interaction.guild, completed_projects)
            await self.menu.cog.update_projects(interaction.guild, self.menu.projects)  # Update project list in config

        else:
            await self.menu.update_message()
            await interaction.response.defer()
            await self.menu.cog.update_projects(interaction.guild, self.menu.projects)  # Update project list in config


class Kingdom(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=True)
        self.config.register_guild(projects=[], completed_projects=[])
        self.config.register_user(personal_projects=[], completed_personal_projects={})

    async def get_personal_projects(self, user):
        return await self.config.user(user).personal_projects()

    async def get_completed_personal_projects(self, user):
        return await self.config.user(user).completed_personal_projects()
    
    async def update_personal_projects(self, user, projects):
        await self.config.user(user).personal_projects.set(projects)

    async def update_completed_personal_projects(self, user, completed_projects):
        await self.config.user(user).completed_personal_projects.set(completed_projects)
        
    async def get_balance(self, user: discord.Member):
        return await self.config.user(user).master_balance()
    
    async def update_balance(self, user: discord.Member, amount: int):
        balance = await self.get_balance(user)
        new_balance = max(0, balance + amount)
        await self.config.user(user).master_balance.set(new_balance)
        return new_balance
    
    async def get_projects(self, guild):
        return await self.config.guild(guild).projects()
    
    async def get_completed_projects(self, guild):
        return await self.config.guild(guild).completed_projects()
    
    async def update_projects(self, guild, projects):
        await self.config.guild(guild).projects.set(projects)
    
    async def update_completed_projects(self, guild, completed_projects):
        await self.config.guild(guild).completed_projects.set(completed_projects)
    
    @commands.command()
    async def completed_projects(self, ctx):
        """View completed projects."""
        completed_projects = await self.get_completed_projects(ctx.guild)
        if not completed_projects:
            await ctx.send("No completed projects yet.")
            return
        
        menu = CompletedProjectsMenu(self, ctx, completed_projects)
        project = completed_projects[0]
        embed = discord.Embed(
            title=f"{project['name']} (Completed)",
            description=f"{project['description']}\n\nTotal Funded: {project['goal']} WellCoins",
            color=discord.Color.green()
        )
        if 'thumbnail' in project:
            embed.set_thumbnail(url=project['thumbnail'])
        embed.set_footer(text=f"Project ID: {project['id']}")
        menu.message = await ctx.send(embed=embed, view=menu)

    @commands.command()
    async def fund(self, ctx):
        """Open the funding menu for server projects."""
        projects = await self.get_projects(ctx.guild)
        if not projects:
            await ctx.send("No ongoing projects at the moment.")
            return
    
        menu = FundingMenu(self, ctx, projects)
        project = projects[0]  # Ensure the first project is displayed properly
        percentage_funded = (project['funded'] / project['goal']) * 100
        
        embed = discord.Embed(
            title=f"{project['name']}",
            description=f"{project['description']}\n\nTotal Needed: {project['goal']} WellCoins\n"
                        f"Funded: {project['funded']} WellCoins ({percentage_funded:.2f}% Funded)",
            color=discord.Color.gold()
        )
        
        if 'thumbnail' in project:
            embed.set_thumbnail(url=project['thumbnail'])
        
        embed.set_footer(text=f"Project ID: {project['id']}")
        
        menu.message = await ctx.send(embed=embed, view=menu)

    
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def add_project(self, ctx, name: str, goal: int, thumbnail: str, *, description: str):
        """Admin only: Add a new server project with a thumbnail."""
        if goal <= 0:
            await ctx.send("Goal must be a positive number.")
            return
        
        projects = await self.get_projects(ctx.guild)
        project_id = str(uuid.uuid4())[:8]  # Generate a unique ID
        new_project = {"id": project_id, "name": name, "description": description, "goal": goal, "funded": 0, "thumbnail": thumbnail}
        projects.append(new_project)
        await self.update_projects(ctx.guild, projects)
        await ctx.send(f"Project '{name}' added with a goal of {goal} WellCoins! Project ID: {project_id}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def remove_project(self, ctx, project_id: str):
        """Admin only: Removes a project by ID from ongoing or completed projects."""
        projects = await self.get_projects(ctx.guild)
        completed_projects = await self.get_completed_projects(ctx.guild)
        
        updated_projects = [p for p in projects if p['id'] != project_id]
        updated_completed_projects = [p for p in completed_projects if p['id'] != project_id]
        
        if len(updated_projects) == len(projects) and len(updated_completed_projects) == len(completed_projects):
            await ctx.send("No project found with that ID.")
            return
        
        await self.update_projects(ctx.guild, updated_projects)
        await self.update_completed_projects(ctx.guild, updated_completed_projects)
        await ctx.send(f"Project with ID {project_id} has been removed.")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def add_personal_project(self, ctx, name: str, goal: int, thumbnail: str, *, prerequisites: str = "None"):
        """Add a personal project (optional prerequisites) with a thumbnail."""
        if goal <= 0:
            await ctx.send("Goal must be a positive number.")
            return
        
        project_id = name.lower().replace(" ", "_")
        prereq_list = [p.strip().lower().replace(" ", "_") for p in prerequisites.split(",") if p.strip()] if prerequisites.lower() != "none" else []
        
        personal_projects = await self.get_personal_projects(ctx.author)
        for project in personal_projects:
            if project['id'] == project_id:
                await ctx.send("You already have a project with this name.")
                return
        
        new_project = {"id": project_id, "name": name, "goal": goal, "funded": 0, "prerequisites": prereq_list, "thumbnail": thumbnail}
        personal_projects.append(new_project)
        await self.update_personal_projects(ctx.author, personal_projects)
        await ctx.send(f"Added personal project '{name}' with a goal of {goal} WellCoins!")

    @commands.command()
    async def my_personal_projects(self, ctx):
        """View and fund your personal projects."""
        projects = await self.get_personal_projects(ctx.author)
        if not projects:
            await ctx.send("You have no personal projects.")
            return
        
        menu = PersonalFundingMenu(self, ctx.author, projects)
        project = projects[0]
        percentage_funded = (project['funded'] / project['goal']) * 100
        
        embed = discord.Embed(
            title=f"{project['name']}",
            description=f"Goal: {project['goal']} WellCoins\nFunded: {project['funded']} WellCoins ({percentage_funded:.2f}% Funded)\nPrerequisites: {', '.join(project['prerequisites']) if project['prerequisites'] else 'None'}",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Project ID: {project['id']}")
        
        menu.message = await ctx.send(embed=embed, view=menu)

    @commands.command()
    async def my_completed_projects(self, ctx):
        """View your completed personal projects."""
        completed_projects = await self.get_completed_personal_projects(ctx.author)
        if not completed_projects:
            await ctx.send("You have not completed any personal projects yet.")
            return
        
        menu = CompletedPersonalProjectsMenu(self, ctx.author, completed_projects)
        project = completed_projects[0]
        embed = discord.Embed(
            title=f"{project['name']} (Completed)",
            description=f"Goal: {project['goal']} WellCoins\nFunded: {project['goal']} WellCoins",
            color=discord.Color.green()
        )
        if 'thumbnail' in project:
            embed.set_thumbnail(url=project['thumbnail'])
        embed.set_footer(text=f"Project ID: {project['id']}")
        menu.message = await ctx.send(embed=embed, view=menu)

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def remove_personal_project(self, ctx, project_id: str):
        """Remove a personal project by ID."""
        personal_projects = await self.get_personal_projects(ctx.author)
        project = next((p for p in personal_projects if p['id'] == project_id), None)
        
        if not project:
            await ctx.send("Project not found.")
            return
        
        personal_projects.remove(project)
        await self.update_personal_projects(ctx.author, personal_projects)
        await ctx.send(f"Removed personal project '{project['name']}'.")
