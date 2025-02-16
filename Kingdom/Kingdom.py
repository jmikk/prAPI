import random
import asyncio
import discord
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
        self.fund_button.callback = self.fund_project
        
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
        user_balance = await self.cog.get_balance(interaction.user)
        modal = FundModal(self, user_balance)
        await interaction.response.send_modal(modal)

class Kingdom(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=True)
        self.projects = []
        self.completed_projects = []
    
    async def get_balance(self, user: discord.Member):
        return await self.config.user(user).master_balance()
    
    async def update_balance(self, user: discord.Member, amount: int):
        balance = await self.get_balance(user)
        new_balance = max(0, balance + amount)
        await self.config.user(user).master_balance.set(new_balance)
        return new_balance
    
    @commands.command()
    async def fund(self, ctx):
        """Open the funding menu for server projects."""
        if not self.projects:
            await ctx.send("No ongoing projects at the moment.")
            return
        
        menu = FundingMenu(self, ctx, self.projects)
        project = self.projects[0]
        percentage_funded = (project['funded'] / project['goal']) * 100
        embed = discord.Embed(
            title=f"{project['name']}",
            description=f"{project['description']}\n\nTotal Needed: {project['goal']} WellCoins\nFunded: {project['funded']} WellCoins ({percentage_funded:.2f}% Funded)",
            color=discord.Color.gold()
        )
        if 'thumbnail' in project:
            embed.set_thumbnail(url=project['thumbnail'])
        menu.message = await ctx.send(embed=embed, view=menu)
    
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def add_project(self, ctx, name: str, goal: int, thumbnail: str, *, description: str):
        """Admin only: Add a new server project with a thumbnail."""
        if goal <= 0:
            await ctx.send("Goal must be a positive number.")
            return
        
        new_project = {"name": name, "description": description, "goal": goal, "funded": 0, "thumbnail": thumbnail}
        self.projects.append(new_project)
        await ctx.send(f"Project '{name}' added with a goal of {goal} WellCoins!")
    
    @commands.command()
    async def completed_projects(self, ctx):
        """View completed projects."""
        if not self.completed_projects:
            await ctx.send("No completed projects yet.")
            return
        
        embed = discord.Embed(title="Completed Projects", color=discord.Color.green())
        for project in self.completed_projects:
            embed.add_field(name=project['name'], value=f"{project['description']}\nTotal Funded: {project['goal']} WellCoins", inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(FundCog(bot))
