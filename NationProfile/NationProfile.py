import discord
from redbot.core import commands, Config
from redbot.core.commands import Context, hybrid_command
from redbot.core.bot import Red
from typing import Optional
import io
from discord import app_commands

class NationProfile(commands.Cog):
    """A cog for storing and displaying RP nation profiles."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        default_user = {
            "nation": None,
            "population": None,
            "currency": None,
            "capital": None,
            "flag": None,
            "history": []
        }

        self.config.register_user(**default_user)

    @commands.command()
    async def exportnation(self, ctx, member: Optional[discord.Member] = None):
        """Export a nation's full profile and history to a text file."""
        target = member or ctx.author
        data = await self.config.user(target).all()

        if not data["nation"]:
            await ctx.send("That user has not set up a nation profile.")
            return

        lines = [
            f"Nation: {data['nation']}",
            f"Population: {data['population']}",
            f"Currency: {data['currency']}",
            f"Capital: {data['capital']}",
            f"Flag: {data['flag'] if data['flag'] else 'None'}",
            "--- History ---"
        ]

        for i, page in enumerate(data["history"], 1):
            lines.append(f"Page {i} - {page.get('title', 'Untitled')}")
            lines.append(page.get("text", "No text."))
            if page.get("image"):
                lines.append(f"Image: {page['image']}")

        content = " ".join(lines)
        file = discord.File(fp=io.StringIO(content), filename=f"{data['nation'].replace(' ', '_')}_profile.txt")
        await ctx.send(f"Here is the exported profile for {data['nation']}:", file=file)


    @app_commands.command(name="nation", description="View your or another user's nation profile.")
    async def nation(self, ctx, member: Optional[discord.Member] = None):
        """View your or another user's nation profile."""
        target = member or ctx.author
        data = await self.config.user(target).all()

        if not data["nation"]:
            if target == ctx.author:
                await self.setup_questionnaire(ctx)
            else:
                await ctx.send("That user has not set up a nation profile.")
            return

        await self.show_nation_embed(ctx, target, data)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def resetnation(self, ctx):
        """Reset your nation profile and history."""
        await self.config.user(ctx.author).clear()
        await ctx.send("Your nation profile and history have been reset.")

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

    @commands.command()
    async def edithistory(self, ctx, index: int, title: Optional[str] = None, image_url: Optional[str] = None, *, text: Optional[str] = None):
        """Edit a history entry by index (starting at 1). Leave fields blank to keep unchanged."""
        history = await self.config.user(ctx.author).history()
        if 0 < index <= len(history):
            entry = history[index - 1]
            if title:
                entry["title"] = title
            if text:
                entry["text"] = text
            if image_url is not None:
                entry["image"] = image_url

            history[index - 1] = entry
            await self.config.user(ctx.author).history.set(history)
            await ctx.send(f"Updated history entry #{index}.")
        else:
            await ctx.send("Invalid index. Use a number corresponding to the history page you want to edit.")

    async def setup_questionnaire(self, ctx):
        modal = NationSetupModal(self, ctx.author)
        await ctx.send_modal(modal)


    async def show_nation_embed(self, interaction: discord.Interaction, user, data):
        embed = discord.Embed(
            title=f"{data['nation']}",
            description=f"{user.display_name}'s nation profile",
            color=discord.Color.blue()
        )
        embed.add_field(name="Population", value=data["population"], inline=False)
        embed.add_field(name="Currency", value=data["currency"], inline=False)
        embed.add_field(name="Capital", value=data["capital"], inline=False)

        if data.get("flag") and any(data["flag"].lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
            embed.set_thumbnail(url=data["flag"])

        view = NationView(self, user)
        await interaction.response.send_message(embed=embed, view=view)


class NationSetupModal(discord.ui.Modal, title="Nation Profile Setup"):
    nation = discord.ui.TextInput(label="Nation Name", max_length=100)
    population = discord.ui.TextInput(label="Population (100,000 - 6,000,000)", placeholder="e.g., 1,000,000")
    currency = discord.ui.TextInput(label="Currency Name", max_length=100)
    capital = discord.ui.TextInput(label="Capital City", max_length=100)
    flag = discord.ui.TextInput(label="Flag Image URL (.png, .jpg, .gif, etc.)", required=False)

    def __init__(self, cog, user):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raw_pop = int(self.population.value.replace(",", ""))
            if not (100_000 <= raw_pop <= 6_000_000):
                await interaction.response.send_message("Population must be between 100,000 and 6,000,000.", ephemeral=True)
                return
            population = f"{raw_pop:,}"
        except ValueError:
            await interaction.response.send_message("Invalid population number.", ephemeral=True)
            return

        flag_url = self.flag.value.strip()
        if flag_url and not any(flag_url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
            await interaction.response.send_message("Flag must be a direct image URL (.png, .jpg, etc).", ephemeral=True)
            return

        await self.cog.config.user(self.user).set({
            "nation": self.nation.value,
            "population": population,
            "currency": self.currency.value,
            "capital": self.capital.value,
            "flag": flag_url or None
        })

        await interaction.response.send_message("Your nation profile has been saved! Use `/nation` to view it.", ephemeral=True)


class NationView(discord.ui.View):
    def __init__(self, cog, target_user):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = target_user
        self.page_index = -1

    @discord.ui.button(label="⏪ Previous", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        history = await self.cog.config.user(self.user).history()
        if not history:
            await interaction.response.send_message("No history to display.", ephemeral=True)
            return

        self.page_index = (self.page_index - 1) % len(history)
        await self.update_embed(interaction, history)

    @discord.ui.button(label="Next ⏩", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        history = await self.cog.config.user(self.user).history()
        if not history:
            await interaction.response.send_message("No history to display.", ephemeral=True)
            return

        self.page_index = (self.page_index + 1) % len(history)
        await self.update_embed(interaction, history)

    async def update_embed(self, interaction: discord.Interaction, history):
        page = history[self.page_index]
        embed = discord.Embed(title=page["title"], description=page["text"], color=discord.Color.dark_purple())
        if page.get("image"):
            embed.set_thumbnail(url=page["image"])
        embed.set_footer(text=f"Page {self.page_index + 1} of {len(history)}")
        await interaction.response.edit_message(embed=embed, view=self)

async def setup(bot: Red):
    await bot.add_cog(NationProfile(bot))
