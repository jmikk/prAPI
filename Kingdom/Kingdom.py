import random
import asyncio
import discord
import uuid
from collections import Counter
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from discord.ui import View, Button, TextInput, Modal

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

class Kingdom(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=True)
        self.config.register_guild(projects=[], completed_projects=[])
    
    async def get_projects(self, guild):
        return await self.config.guild(guild).projects()
    
    async def get_completed_projects(self, guild):
        return await self.config.guild(guild).completed_projects()
    
    async def update_projects(self, guild, projects):
        await self.config.guild(guild).projects.set(projects)
    
    async def update_completed_projects(self, guild, completed_projects):
        await self.config.guild(guild).completed_projects.set(completed_projects)
    
    @commands.command()
    async def fund(self, ctx):
        """Open the funding menu for server projects."""
        projects = await self.get_projects(ctx.guild)
        if not projects:
            await ctx.send("No ongoing projects at the moment.")
            return
        
        menu = FundingMenu(self, ctx, projects)
        project = projects[0]
        percentage_funded = (project['funded'] / project['goal']) * 100
        embed = discord.Embed(
            title=f"{project['name']}",
            description=f"{project['description']}\n\nTotal Needed: {project['goal']} WellCoins\nFunded: {project['funded']} WellCoins ({percentage_funded:.2f}% Funded)",
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
    async def delete_project(self, ctx, project_id: str):
        """Admin only: Delete a project by ID."""
        projects = await self.get_projects(ctx.guild)
        updated_projects = [p for p in projects if p['id'] != project_id]
        
        if len(updated_projects) == len(projects):
            await ctx.send("No project found with that ID.")
            return
        
        await self.update_projects(ctx.guild, updated_projects)
        await ctx.send(f"Project with ID {project_id} has been deleted.")
    
    @commands.command()
    async def completed_projects(self, ctx):
        """View completed projects."""
        completed_projects = await self.get_completed_projects(ctx.guild)
        if not completed_projects:
            await ctx.send("No completed projects yet.")
            return
        
        embed = discord.Embed(title="Completed Projects", color=discord.Color.green())
        for project in completed_projects:
            embed.add_field(name=project['name'], value=f"{project['description']}\nTotal Funded: {project['goal']} WellCoins", inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Kingdom(bot))
