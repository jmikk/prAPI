import discord
from discord.ext import commands
from redbot.core import Config

class recToken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=23456789648)

        default_guild = {
            "projects": {}  # {"project_name": {"required_credits": int, "current_credits": int, "thumbnail": "", "description": "", "emoji": ""}}
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_user(credits=0)  # Ensure users have a credits field

    def normalize_project_name(self, project: str) -> str:
        return project.lower()

    def display_project_name(self, project: str) -> str:
        return project.title()

    @commands.command()
    async def menu(self, ctx):
        """Show a menu with available commands and buttons to execute them."""
        embed = discord.Embed(
            title="Command Menu",
            description="Here are the available commands and what they do. You can use the buttons below or the traditional text commands.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="View Projects",
            value="Use `/viewprojects` to see ongoing projects.",
            inline=False
        )
        embed.add_field(
            name="Submit Project",
            value="Use `/submitproject <project_name> [description] [thumbnail] [emoji]` to submit a new project for 1000 credits.",
            inline=False
        )
        embed.add_field(
            name="Donate Credits",
            value="Use `/donatecredits <project_name> <amount>` to donate credits to a project.",
            inline=False
        )
        embed.add_field(
            name="Check Credits",
            value="Use `/checkcredits` to check your current credit balance.",
            inline=False
        )
        embed.add_field(
            name="Add Project (Owner Only)",
            value="Use `/addproject <project_name> <required_credits> [emoji]` to add a new project (Owner only).",
            inline=False
        )
        embed.add_field(
            name="Remove Project (Owner Only)",
            value="Use `/removeproject <project_name>` to remove a project (Owner only).",
            inline=False
        )
        embed.add_field(
            name="Edit Project (Owner Only)",
            value="Use `/editproject <project_name> [description] [thumbnail] [emoji]` to edit a project's details (Owner only).",
            inline=False
        )

        # Create buttons
        buttons = [
            discord.ui.Button(label="View Projects", custom_id="viewprojects", style=discord.ButtonStyle.primary),
            discord.ui.Button(label="Submit Project", custom_id="submitproject", style=discord.ButtonStyle.success),
            discord.ui.Button(label="Donate Credits", custom_id="donatecredits", style=discord.ButtonStyle.secondary),
            discord.ui.Button(label="Check Credits", custom_id="checkcredits", style=discord.ButtonStyle.secondary)
        ]

        view = discord.ui.View()
        for button in buttons:
            view.add_item(button)

        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions for the menu."""
        if interaction.custom_id == "viewprojects":
            await self.viewprojects(interaction)
        elif interaction.custom_id == "submitproject":
            await interaction.response.send_message("Please use the `/submitproject` command to submit a project.", ephemeral=True)
        elif interaction.custom_id == "donatecredits":
            await interaction.response.send_message("Please use the `/donatecredits` command to donate credits to a project.", ephemeral=True)
        elif interaction.custom_id == "checkcredits":
            await self.checkcredits(interaction)

    @commands.command()
    async def viewprojects(self, ctx):
        projects = await self.config.guild(ctx.guild).projects()
        if not projects:
            await ctx.send(embed=discord.Embed(description="No ongoing projects.", color=discord.Color.red()))
        else:
            project_names = list(projects.keys())
            initial_embed = self.create_embed(projects, project_names, 0)
            message = await ctx.send(embed=initial_embed)
    
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
    
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"] and reaction.message.id == message.id
    
            current_index = 0
    
            while True:
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
    
                    if str(reaction.emoji) == "➡️":
                        current_index = (current_index + 1) % len(project_names)
                    elif str(reaction.emoji) == "⬅️":
                        current_index = (current_index - 1) % len(project_names)
    
                    new_embed = self.create_embed(projects, project_names, current_index)
                    await message.edit(embed=new_embed)
                    await message.remove_reaction(reaction.emoji, user)
    
                except asyncio.TimeoutError:
                    break
    
    def create_embed(self, projects, project_names, index):
        project_name = project_names[index]
        project = projects[project_name]
    
        if project["required_credits"] > 0:
            percent_complete = (project["current_credits"] / project["required_credits"]) * 100
        else:
            percent_complete = 100
    
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
    
        return embed

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

    @commands.command()
    async def donatecredits(self, ctx, project: str, amount: str):
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).projects() as projects:
            if project not in projects:
                return await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()))
    
            user_credits = await self.config.user(ctx.author).credits()
    
            if amount.lower() == "all":
                amount_to_donate = user_credits
            else:
                try:
                    amount_to_donate = int(amount)
                except ValueError:
                    return await ctx.send(embed=discord.Embed(description="Please specify a valid number of credits or 'all'.", color=discord.Color.red()))
    
            if amount_to_donate > user_credits:
                return await ctx.send(embed=discord.Embed(description="You don't have enough credits.", color=discord.Color.red()))
    
            projects[project]["current_credits"] += amount_to_donate
    
            new_credits = user_credits - amount_to_donate
            await self.config.user(ctx.author).credits.set(new_credits)
    
        await ctx.send(embed=discord.Embed(description=f"{amount_to_donate} credits donated to '{self.display_project_name(project)}'.", color=discord.Color.green()))

    @commands.command()
    async def checkcredits(self, ctx):
        user_id = ctx.author.id
        credits = await self.config.user_from_id(user_id).credits()

        embed = discord.Embed(
            title="Your Credits",
            description=f"You currently have **{credits}** credits.",
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)

    @commands.command()
    async def submitproject(self, ctx, project: str, description: str = None, thumbnail: str = None, emoji: str = "💰"):
        user_credits = await self.config.user(ctx.author).credits()

        if user_credits < 1000:
            return await ctx.send(embed=discord.Embed(description="You don't have enough credits to submit a project. You need 1000 credits.", color=discord.Color.red()))
        
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).projects() as projects:
            if project in projects:
                return await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' already exists.", color=discord.Color.red()))

            await self.config.user(ctx.author).credits.set(user_credits - 1000)

            projects[project] = {
                "required_credits": 1000,
                "current_credits": 0,
                "thumbnail": thumbnail or "",
                "description": description or "No description available.",
                "emoji": emoji
            }

        await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' has been submitted for 1000 credits.", color=discord.Color.green()))


def setup(bot):
    bot.add_cog(recToken(bot))
