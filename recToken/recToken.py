import discord
import asyncio
from redbot.core import commands, Config, checks

class recToken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        default_user = {
            "credits": 0,
        }

        default_guild = {
            "projects": {}  # {"project_name": {"required_credits": int, "current_credits": int, "thumbnail": "", "description": "", "emoji": ""}}
        }
        
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

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
            title=f"Project: {project_name}",
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
        async with self.config.guild(ctx.guild).projects() as projects:
            if project not in projects:
                return await ctx.send(embed=discord.Embed(description=f"Project '{project}' not found.", color=discord.Color.red()))
    
            del projects[project]  # Remove the project from the dictionary
    
        await ctx.send(embed=discord.Embed(description=f"Project '{project}' has been removed.", color=discord.Color.green()))

    @commands.command()
    @checks.is_owner()
    async def addproject(self, ctx, project: str, required_credits: int, emoji: str = "💰"):
        """Add a new project to the kingdom with required credits and an optional emoji."""
        async with self.config.guild(ctx.guild).projects() as projects:
            projects[project] = {
                "required_credits": required_credits,
                "current_credits": 0,
                "thumbnail": "",
                "description": "",
                "emoji": emoji  # Store the emoji representing credits
            }
    
        await ctx.send(embed=discord.Embed(description=f"Project '{project}' added with {required_credits} credits needed.", color=discord.Color.green()))
    

    @commands.command()
    @checks.is_owner()
    async def editproject(self, ctx, project: str, description: str = None, thumbnail: str = None, emoji: str = None):
        """Edit a project's thumbnail, description, and emoji."""
        async with self.config.guild(ctx.guild).projects() as projects:
            if project not in projects:
                return await ctx.send(embed=discord.Embed(description="Project not found.", color=discord.Color.red()))
            
            if thumbnail:
                projects[project]["thumbnail"] = thumbnail
            if description:
                projects[project]["description"] = description
            if emoji:
                projects[project]["emoji"] = emoji

        await ctx.send(embed=discord.Embed(description=f"Project '{project}' updated.", color=discord.Color.green()))

    @commands.command()
    async def donatecredits(self, ctx, project: str, amount: int):
        """Donate a specified amount of credits to a project."""
        async with self.config.guild(ctx.guild).projects() as projects:
            if project not in projects:
                return await ctx.send(embed=discord.Embed(description=f"Project '{project}' not found.", color=discord.Color.red()))

            user_credits = await self.config.user(ctx.author).credits()
            if user_credits < amount:
                return await ctx.send(embed=discord.Embed(description="You don't have enough credits.", color=discord.Color.red()))

            # Update the project's credits
            projects[project]["current_credits"] += amount

            # Update the user's credits
            new_credits = user_credits - amount
            await self.config.user(ctx.author).credits.set(new_credits)

        await ctx.send(embed=discord.Embed(description=f"{amount} credits donated to '{project}'.", color=discord.Color.green()))

def setup(bot):
    bot.add_cog(recToken(bot))
