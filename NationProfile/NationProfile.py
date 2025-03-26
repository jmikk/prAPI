import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Optional

class NationProfile(commands.Cog):
    """A cog for storing and displaying RP nation profiles."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        default_user = {
            "nation": None,
            "population": None,
            "animal": None,
            "currency": None,
            "capital": None,
            "history": []  # List of dicts with keys: title, text, image
        }

        self.config.register_user(**default_user)

    @commands.command()
    async def nation(self, ctx):
        """View or set up your nation profile."""
        data = await self.config.user(ctx.author).all()
        
        if not data["nation"]:
            await self.setup_questionnaire(ctx)
        else:
            await self.show_nation_embed(ctx, data)

    @commands.command()
    async def addhistory(self, ctx, title: str, image_url: Optional[str] = None, *, text: str):
        """Add a history entry to your nation's profile."""
        entry = {"title": title, "text": text, "image": image_url}
        history = await self.config.user(ctx.author).history()
        history.append(entry)
        await self.config.user(ctx.author).history.set(history)
        await ctx.send(f"History page titled '{title}' added.")

    @commands.command()
    async def removehistory(self, ctx, index: int):
        """Remove a history page by its index (starting at 1)."""
        history = await self.config.user(ctx.author).history()
        if 0 < index <= len(history):
            removed = history.pop(index - 1)
            await self.config.user(ctx.author).history.set(history)
            await ctx.send(f"Removed history page titled '{removed['title']}'.")
        else:
            await ctx.send("Invalid index. Use a number corresponding to the history page you want to remove.")

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

        await self.config.user(ctx.author).set({
            "nation": nation,
            "population": population,
            "animal": animal,
            "currency": currency,
            "capital": capital
        })

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
