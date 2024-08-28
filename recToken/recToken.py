import discord
from redbot.core import commands
from redbot.core import Config, checks
from discord.ui import Button, View

class ProjectScrollView(View):
    def __init__(self, ctx, projects, project_names, config):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.projects = projects
        self.project_names = project_names
        self.current_index = 0
        self.config = config

    def create_embed(self, index):
        project_name = self.project_names[index]
        project = self.projects[project_name]

        embed = discord.Embed(
            title=f"Project: {project_name}",
            description=project["description"] or "No description available.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Credits",
            value=f"{project['current_credits']}/{project['required_credits']} credits",
            inline=False
        )
        embed.add_field(
            name="Donated Items",
            value=", ".join(project['donated_items']) or "None",
            inline=False
        )
        if project["thumbnail"]:
            embed.set_thumbnail(url=project["thumbnail"])
        
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_message("Button pressed!", ephemeral=True)  # Temporary for debugging 
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.project_names) - 1
        
        embed = self.create_embed(self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, button: Button, interaction: discord.Interaction):
        if self.current_index < len(self.project_names) - 1:
            self.current_index += 1
        else:
            self.current_index = 0
        
        embed = self.create_embed(self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Donate 1 Credit", style=discord.ButtonStyle.secondary)
    async def donate_1(self, button: Button, interaction: discord.Interaction):
        await self.donate_credits(interaction, 1)

    @discord.ui.button(label="Donate 10 Credits", style=discord.ButtonStyle.secondary)
    async def donate_10(self, button: Button, interaction: discord.Interaction):
        await self.donate_credits(interaction, 10)

    @discord.ui.button(label="Donate All Credits", style=discord.ButtonStyle.secondary)
    async def donate_all(self, button: Button, interaction: discord.Interaction):
        user_credits = await self.config.user(interaction.user).credits()
        await self.donate_credits(interaction, user_credits)

    @discord.ui.button(label="Donate Custom Credits", style=discord.ButtonStyle.secondary)
    async def donate_custom(self, button: Button, interaction: discord.Interaction):
        modal = CustomDonationModal(self.ctx, self.projects[self.project_names[self.current_index]], self.config, self.project_names[self.current_index])
        await interaction.response.send_modal(modal)

    async def donate_credits(self, interaction: discord.Interaction, amount: int):
        project_name = self.project_names[self.current_index]
        project = self.projects[project_name]
        user_credits = await self.config.user(interaction.user).credits()

        if user_credits < amount:
            await interaction.response.send_message("You don't have enough credits.", ephemeral=True)
        else:
            async with self.config.user(interaction.user).credits() as credits:
                credits -= amount
            async with self.config.guild(self.ctx.guild).projects() as projects:
                projects[project_name]["current_credits"] += amount
            embed = self.create_embed(self.current_index)
            await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author


class CustomDonationModal(discord.ui.Modal):
    def __init__(self, ctx, project, config, project_name):
        super().__init__(title="Custom Donation")
        self.ctx = ctx
        self.project = project
        self.config = config
        self.project_name = project_name

        self.amount = discord.ui.TextInput(label="Amount", style=discord.TextStyle.short, required=True)

        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        amount = int(self.amount.value)
        user_credits = await self.config.user(self.ctx.author).credits()

        if user_credits < amount:
            await interaction.response.send_message("You don't have enough credits.", ephemeral=True)
        else:
            async with self.config.user(self.ctx.author).credits() as credits:
                credits -= amount
            async with self.config.guild(self.ctx.guild).projects() as projects:
                projects[self.project_name]["current_credits"] += amount
            await interaction.response.send_message(f"{amount} credits donated to {self.project_name}.", ephemeral=True)
            embed = ProjectScrollView(self.ctx, self.project, self.project_name, self.config).create_embed(0)
            await interaction.message.edit(embed=embed)


class recToken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        default_user = {
            "credits": 0,
            "items": []
        }

        default_guild = {
            "items": {},  # {"emoji": {"name": "item_name", "price": price}}
            "projects": {}  # {"project_name": {"required_credits": int, "current_credits": int, "donated_items": [], "thumbnail": "", "description": ""}}
        }
        
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

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
    async def giveitem(self, ctx, user: discord.User, emoji: str):
        """Manually give an item to a user."""
        async with self.config.guild(ctx.guild).items() as store_items:
            if emoji not in store_items:
                return await ctx.send(embed=discord.Embed(description="This item does not exist.", color=discord.Color.red()))

        async with self.config.user(user).items() as items:
            items.append(emoji)
        await ctx.send(embed=discord.Embed(description=f"{store_items[emoji]['name']} given to {user.name}.", color=discord.Color.green()))

    @commands.command()
    @checks.is_owner()
    async def additem(self, ctx, emoji: str, name: str, price: int):
        """Add a new item to the store."""
        async with self.config.guild(ctx.guild).items() as items:
            items[emoji] = {"name": name, "price": price}
        await ctx.send(embed=discord.Embed(description=f"Item {name} added to the store for {price} credits.", color=discord.Color.green()))

    @commands.command()
    @checks.is_owner()
    async def addproject(self, ctx, project: str, required_credits: int):
        """Add a new project to the kingdom."""
        async with self.config.guild(ctx.guild).projects() as projects:
            projects[project] = {
                "required_credits": required_credits,
                "current_credits": 0,
                "donated_items": [],
                "thumbnail": "",
                "description": ""
            }
        await ctx.send(embed=discord.Embed(description=f"Project {project} added with {required_credits} credits needed.", color=discord.Color.green()))

    @commands.command()
    @checks.is_owner()
    async def editproject(self, ctx, project: str, thumbnail: str = None, description: str = None):
        """Edit a project's thumbnail and description."""
        async with self.config.guild(ctx.guild).projects() as projects:
            if project not in projects:
                return await ctx.send(embed=discord.Embed(description="Project not found.", color=discord.Color.red()))
            
            if thumbnail:
                projects[project]["thumbnail"] = thumbnail
            if description:
                projects[project]["description"] = description

        await ctx.send(embed=discord.Embed(description=f"Project {project} updated.", color=discord.Color.green()))

    @commands.command()
    async def viewprojects(self, ctx):
        """View ongoing projects and their progress with scrolling embeds."""
        projects = await self.config.guild(ctx.guild).projects()
        if not projects:
            await ctx.send(embed=discord.Embed(description="No ongoing projects.", color=discord.Color.red()))
        else:
            project_names = list(projects.keys())
            view = ProjectScrollView(ctx, projects, project_names, self.config)
            embed = view.create_embed(0)
            await ctx.send(embed=embed, view=view)

def setup(bot):
    bot.add_cog(Storefront(bot))
