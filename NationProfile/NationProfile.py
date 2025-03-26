import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Optional

class NationProfile(commands.Cog):
    """A cog for storing and displaying RP nation profiles."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        await self.config.user(ctx.author).set({
            "nation": nation,
            "population": population,
            "animal": animal,
            "currency": currency,
            "capital": capital
        })


        self.config.register_user(**default_user)

    @commands.command()
    async def nation(self, ctx):
        """View or set up your nation profile."""
        data = await self.config.user(ctx.author).all()
        
        if not data["nation"]:
            await self.setup_questionnaire(ctx)
        else:
            await self.show_nation_embed(ctx, data)

    async def setup_questionnaire(self, ctx):
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send("Welcome to your Nation Profile setup! What is your nation's name?")
        nation = (await self.bot.wait_for('message', check=check)).content

        await ctx.send("What is your nation's population?")
        population = (await self.bot.wait_for('message', check=check)).content

        await ctx.send("What is your national animal?")
        animal = (await self.bot.wait_for('message', check=check)).content

        await ctx.send("What is your currency called?")
        currency = (await self.bot.wait_for('message', check=check)).content

        await ctx.send("What is your capital city?")
        capital = (await self.bot.wait_for('message', check=check)).content

        await self.config.user(ctx.author).set(
            nation=nation,
            population=population,
            animal=animal,
            currency=currency,
            capital=capital
        )

        await ctx.send("Your nation profile has been saved! Use `!nation` again to view it.")

    async def show_nation_embed(self, ctx, data):
        embed = discord.Embed(
            title=f"{data['nation']}",
            description="Your nation's profile",
            color=discord.Color.blue()
        )
        embed.add_field(name="Population", value=data["population"], inline=False)
        embed.add_field(name="National Animal", value=data["animal"], inline=False)
        embed.add_field(name="Currency", value=data["currency"], inline=False)
        embed.add_field(name="Capital", value=data["capital"], inline=False)

        view = NationView(self)
        await ctx.send(embed=embed, view=view)

class NationView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="View History", style=discord.ButtonStyle.primary, custom_id="nation_view_history")
    async def view_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        data = await self.cog.config.user(user).all()
        history = data.get("history", [])

        if not history:
            await interaction.response.send_message("You have no history pages set yet.", ephemeral=True)
            return

        page = history[0]
        embed = discord.Embed(title=page["title"], description=page["text"], color=discord.Color.dark_purple())
        if page.get("image"):
            embed.set_thumbnail(url=page["image"])

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: Red):
    await bot.add_cog(NationProfile(bot))
