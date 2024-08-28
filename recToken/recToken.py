import discord
from discord.ext import commands
from redbot.core import Config, checks
from redbot.core.commands.context import Context
from redbot.core import commands, Config

class recToken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=87654345678765, force_registration=True)
        
        default_user = {
            "credits": 0,
            "items": []
        }

        default_guild = {
            "items": {},  # {"emoji": {"name": "item_name", "price": price}}
            "projects": {}  # {"project_name": {"required_credits": int, "current_credits": int, "donated_items": []}}
        }
        
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    @commands.command()
    @checks.is_owner()
    async def givecredits(self, ctx, user: discord.User, amount: int):
        """Manually give credits to a user."""
        async with self.config.user(user).credits() as credits:
            credits += amount
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
                "donated_items": []
            }
        await ctx.send(embed=discord.Embed(description=f"Project {project} added with {required_credits} credits needed.", color=discord.Color.green()))

    @commands.command()
    async def viewstore(self, ctx):
        """View available items in the store."""
        items = await self.config.guild(ctx.guild).items()
        if not items:
            await ctx.send(embed=discord.Embed(description="No items available.", color=discord.Color.red()))
        else:
            embed = discord.Embed(title="Store Items", color=discord.Color.blue())
            for emoji, details in items.items():
                embed.add_field(name=f"{emoji} {details['name']}", value=f"Price: {details['price']} credits", inline=False)
            await ctx.send(embed=embed)

    @commands.command()
    async def viewprojects(self, ctx):
        """View ongoing projects and their progress."""
        projects = await self.config.guild(ctx.guild).projects()
        if not projects:
            await ctx.send(embed=discord.Embed(description="No ongoing projects.", color=discord.Color.red()))
        else:
            embed = discord.Embed(title="Ongoing Projects", color=discord.Color.blue())
            for project, details in projects.items():
                embed.add_field(
                    name=f"{project}",
                    value=f"Credits: {details['current_credits']}/{details['required_credits']}\nDonated items: {', '.join(details['donated_items']) or 'None'}",
                    inline=False
                )
            await ctx.send(embed=embed)

    @commands.command()
    async def donatecredits(self, ctx: Context, project: str):
        """Donate credits to a project using buttons."""
        projects = await self.config.guild(ctx.guild).projects()
        if project not in projects:
            return await ctx.send(embed=discord.Embed(description="Project not found.", color=discord.Color.red()))

        embed = discord.Embed(title=f"Donate Credits to {project}", color=discord.Color.gold())
        embed.description = "Choose an amount to donate:"
        view = DonateCreditsView(ctx, project, self.config)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def donateitem(self, ctx, project: str, emoji: str):
        """Donate an item to a project."""
        async with self.config.user(ctx.author).items() as items:
            if emoji not in items:
                return await ctx.send(embed=discord.Embed(description="You don't have this item.", color=discord.Color.red()))
            items.remove(emoji)

        async with self.config.guild(ctx.guild).projects() as projects:
            if project in projects:
                projects[project]["donated_items"].append(emoji)
                await ctx.send(embed=discord.Embed(description=f"Item {emoji} donated to {project}.", color=discord.Color.green()))
            else:
                await ctx.send(embed=discord.Embed(description="Project not found.", color=discord.Color.red()))

class DonateCreditsView(discord.ui.View):
    def __init__(self, ctx: Context, project: str, config: Config):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.project = project
        self.config = config

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    @discord.ui.button(label="1", style=discord.ButtonStyle.primary)
    async def donate_1(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.donate(interaction, 1)

    @discord.ui.button(label="10", style=discord.ButtonStyle.primary)
    async def donate_10(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.donate(interaction, 10)

    @discord.ui.button(label="100", style=discord.ButtonStyle.primary)
    async def donate_100(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.donate(interaction, 100)

    @discord.ui.button(label="Custom", style=discord.ButtonStyle.secondary)
    async def donate_custom(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = CustomDonationModal(self.ctx, self.project, self.config)
        await interaction.response.send_modal(modal)

    async def donate(self, interaction: discord.Interaction, amount: int):
        user_credits = await self.config.user(self.ctx.author).credits()
        if user_credits < amount:
            await interaction.response.send_message("You don't have enough credits.", ephemeral=True)
        else:
            async with self.config.user(self.ctx.author).credits() as credits:
                credits -= amount
            async with self.config.guild(self.ctx.guild).projects() as projects:
                projects[self.project]["current_credits"] += amount
            await interaction.response.send_message(f"{amount} credits donated to {self.project}.", ephemeral=True)
            await self.ctx.send(embed=discord.Embed(description=f"{amount} credits donated to {self.project}.", color=discord.Color.green()))

class CustomDonationModal(discord.ui.Modal):
    def __init__(self, ctx: Context, project: str, config: Config):
        super().__init__(title="Custom Donation")
        self.ctx = ctx
        self.project = project
        self.config = config

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
                projects[self.project]["current_credits"] += amount
            await interaction.response.send_message(f"{amount} credits donated to {self.project}.", ephemeral=True)
            await self.ctx.send(embed=discord.Embed(description=f"{amount} credits donated to {self.project}.", color=discord.Color.green()))

def setup(bot):
    bot.add_cog(Storefront(bot))
