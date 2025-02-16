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
        embed = discord.Embed(
            title=f"{project['name']}",
            description=f"{project['description']}\n\nTotal Needed: {project['goal']} WellCoins\nFunded: {project['funded']} WellCoins",
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
            await interaction.response.send_message(f"Project {project['name']} has been fully funded! 🎉", ephemeral=True)
            self.menu.projects.pop(self.menu.current_index)
        else:
            await self.menu.update_message()
            await interaction.response.defer()

class Kingdom(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=True)
        self.projects = []
    
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
        embed = discord.Embed(
            title=f"{self.projects[0]['name']}",
            description=f"{self.projects[0]['description']}\n\nTotal Needed: {self.projects[0]['goal']} WellCoins\nFunded: {self.projects[0]['funded']} WellCoins",
            color=discord.Color.gold()
        )
        if 'thumbnail' in self.projects[0]:
            embed.set_thumbnail(url=self.projects[0]['thumbnail'])
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

async def setup(bot):
    await bot.add_cog(FundCog(bot))
