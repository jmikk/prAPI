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
            "flag": None,
            "history": []
        }

        self.config.register_user(**default_user)

    @commands.command()
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
            f"National Animal: {data['animal']}",
            f"Currency: {data['currency']}",
            f"Capital: {data['capital']}",
            f"Flag: {data['flag'] if data['flag'] else 'None'}",
            "\n--- History ---"
        ]

        for i, page in enumerate(data["history"], 1):
            lines.append(f"\nPage {i} - {page.get('title', 'Untitled')}")
            lines.append(page.get("text", "No text."))
            if page.get("image"):
                lines.append(f"Image: {page['image']}")

        content = "\n".join(lines)
        file = discord.File(fp=discord.File(io.StringIO(content), filename=f"{data['nation']}_profile.txt"))
        await ctx.send(f"Here is the exported profile for {data['nation']}:", file=file)

    @commands.command()
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
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send("Welcome to your Nation Profile setup! What is your nation's name?")
        try:
            nation_msg = await self.bot.wait_for('message', check=check, timeout=60)
            nation = nation_msg.content
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. Setup cancelled.")
            return

        await ctx.send("What is your nation's population? (between 100,000 and 6,000,000)")
        while True:
            try:
                population_input = await self.bot.wait_for('message', check=check, timeout=60)
                raw_pop = int(population_input.content.replace(",", ""))
                if 100000 <= raw_pop <= 6000000:
                    population = f"{raw_pop:,}"
                    break
                else:
                    await ctx.send("Please enter a number between 100,000 and 6,000,000.")
            except asyncio.TimeoutError:
                await ctx.send("You took too long to respond. Setup cancelled.")
                return
            except ValueError:
                await ctx.send("Please enter a valid number.")
            raw_pop = int(population_input.content.replace(",", ""))
            if 100000 <= raw_pop <= 6000000:
                population = f"{raw_pop:,}"
                break
            else:
                await ctx.send("Please enter a number between 100,000 and 6,000,000.")


        await ctx.send("What is your national animal?")
        try:
            animal_msg = await self.bot.wait_for('message', check=check, timeout=60)
            animal = animal_msg.content
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. Setup cancelled.")
            return

        await ctx.send("What is your currency called?")
        try:
            currency_msg = await self.bot.wait_for('message', check=check, timeout=60)
            currency = currency_msg.content
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. Setup cancelled.")
            return

        await ctx.send("What is your capital city?")
        try:
            capital_msg = await self.bot.wait_for('message', check=check, timeout=60)
            capital = capital_msg.content
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. Setup cancelled.")
            return

        await ctx.send("Please provide a link to your national flag image (URL):")
        while True:
            try:
                flag_msg = await self.bot.wait_for('message', check=check, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send("You took too long to respond. Setup cancelled.")
                return
            flag = flag_msg.content.strip()
            if any(flag.lower().startswith(ext) for ext in ["http", "https", "www"]):
                break
            else:
                await ctx.send("That doesn't look like a valid image URL.")

        await self.config.user(ctx.author).set({
            "nation": nation,
            "population": population,
            "animal": animal,
            "currency": currency,
            "capital": capital,
            "flag": flag
        })

        await ctx.send("Your nation profile has been saved! Use `!nation` again to view it.")

    async def show_nation_embed(self, ctx, user, data):
        embed = discord.Embed(
            title=f"{data['nation']}",
            description=f"{user.display_name}'s nation profile",
            color=discord.Color.blue()
        )
        embed.add_field(name="Population", value=data["population"], inline=False)
        embed.add_field(name="National Animal", value=data["animal"], inline=False)
        embed.add_field(name="Currency", value=data["currency"], inline=False)
        embed.add_field(name="Capital", value=data["capital"], inline=False)

        if data.get("flag") and any(data["flag"].lower().startswith(ext) for ext in ["http", "https", "www"]):
            embed.set_thumbnail(url=data["flag"])

        view = NationView(self, user)
        await ctx.send(embed=embed, view=view)

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
