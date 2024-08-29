import discord
import asyncio
from redbot.core import commands, Config, checks
from scroll import Scroll

class recToken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=23456789648, force_registration=True)
        
        default_user = {
            "credits": 0,
        }

        default_guild = {
            "projects": {}  # {"project_name": {"required_credits": int, "current_credits": int, "thumbnail": "", "description": "", "emoji": ""}}
        }
        
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    def normalize_project_name(self, project: str) -> str:
        """Normalize the project name for consistent storage and retrieval."""
        return project.lower()

    def display_project_name(self, project: str) -> str:
        """Format the project name for display in title case."""
        return project.title()

    @commands.command()
    async def viewprojects(self, ctx):
        """View ongoing projects and navigate using emoji reactions."""
        projects = await self.config.guild(ctx.guild).projects()
        if not projects:
            await ctx.send(embed=discord.Embed(description="No ongoing projects.", color=discord.Color.red()))
        else:
            project_names = list(projects.keys())
            initial_embed = self.create_embed(projects, project_names, 0)
            message = await ctx.send(embed=initial_embed)
    
            # Add reaction buttons
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
    
        # Calculate the completion percentage
        if project["required_credits"] > 0:
            percent_complete = (project["current_credits"] / project["required_credits"]) * 100
        else:
            percent_complete = 100  # If no credits are required, it's already complete
    
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
    @checks.is_owner()
    async def givecredits(self, ctx, user: discord.User, amount: int):
        """Manually give credits to a user."""
        current_credits = await self.config.user(user).credits()  # Retrieve current credits
        new_credits = current_credits + amount  # Update the credits
        await self.config.user(user).credits.set(new_credits)  # Set the new value
        await ctx.send(embed=discord.Embed(description=f"{amount} credits given to {user.name}.", color=discord.Color.green()))

    @commands.command()
    @checks.is_owner()
    async def removeproject(self, ctx, project: str):
        """Remove a project from the kingdom."""
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).projects() as projects:
            if project not in projects:
                return await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' not found.", color=discord.Color.red()))
    
            del projects[project]  # Remove the project from the dictionary
    
        await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' has been removed.", color=discord.Color.green()))

    @commands.command()
    @checks.is_owner()
    async def addproject(self, ctx, project: str, required_credits: int, emoji: str = "💰"):
        """Add a new project to the kingdom with required credits and an optional emoji."""
        project = self.normalize_project_name(project)
        async with self.config.guild(ctx.guild).projects() as projects:
            projects[project] = {
                "required_credits": required_credits,
                "current_credits": 0,
                "thumbnail": "",
                "description": "",
                "emoji": emoji  # Store the emoji representing credits
            }
    
        await ctx.send(embed=discord.Embed(description=f"Project '{self.display_project_name(project)}' added with {required_credits} credits needed.", color=discord.Color.green()))

    @commands.command()
    @checks.is_owner()
    async def editproject(self, ctx, project: str, description: str = None, thumbnail: str = None, emoji: str = None):
        """Edit a project's thumbnail, description, and emoji."""
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
        """Donate a specified amount of credits to a project, or all credits if 'all' is specified."""
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
    
            # Update the project's credits
            projects[project]["current_credits"] += amount_to_donate
    
            # Update the user's credits
            new_credits = user_credits - amount_to_donate
            await self.config.user(ctx.author).credits.set(new_credits)
    
        await ctx.send(embed=discord.Embed(description=f"{amount_to_donate} credits donated to '{self.display_project_name(project)}'.", color=discord.Color.green()))
    
    @commands.command()
    @checks.is_owner()
    async def showcredits(self, ctx):
        """Display the content of the leaderboards.txt file."""
        await ctx.send("here")
        
        lbPath = await Scroll().CheckPath(ctx, "tokens.txt")            
        if not os.path.exists(lbPath):
            return await ctx.send(embed=discord.Embed(description="The leaderboard file does not exist.", color=discord.Color.red()))
            
        try:
            with open(lbPath, "r") as file:
                content = file.read()
    
            if len(content) > 2000:  # Discord message limit
                await ctx.send(embed=discord.Embed(description="The leaderboard file is too large to display.", color=discord.Color.red()))
            else:
                await ctx.send(f"**Leaderboard Content:**\n```{content}```")
    
        except Exception as e:
            await ctx.send(embed=discord.Embed(description=f"An error occurred while reading the file: {e}", color=discord.Color.red()))

    

def setup(bot):
    bot.add_cog(recToken(bot))
