import discord
from redbot.core import commands, Config
from discord.ext import tasks
from datetime import datetime, timedelta

class FantasyJobBoard(commands.Cog):
    """Fantasy Job Board for quests around the server."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "quests": {},  # quest_id: quest_data
            "recurring": {},  # quest_id: quest_data
            "quest_giver_role": None,
        }
        self.config.register_guild(**default_guild)
        self.recurring_refresh.start()

    def cog_unload(self):
        self.recurring_refresh.cancel()

    @commands.group()
    async def quest(self, ctx):
        """Commands for the Fantasy Job Board."""
        pass

    @jobboard.command()
    @commands.has_permissions(administrator=True)
    async def setrole(self, ctx, role: discord.Role):
        """Set the Quest Giver role to be pinged on quest completion."""
        await self.config.guild(ctx.guild).quest_giver_role.set(role.id)
        await ctx.send(f"Quest Giver role set to {role.mention}!")

    @jobboard.command()
    async def view(self, ctx):
        """View available quests."""
        quests = await self.config.guild(ctx.guild).quests()
        if not quests:
            await ctx.send("There are no quests on the board right now!")
            return

        embeds = []
        for qid, data in quests.items():
            embed = discord.Embed(title=data['title'], description=data['description'], color=0x00ff00)
            embed.add_field(name="Reward", value=data['reward'], inline=False)
            if data['due']:
                embed.set_footer(text=f"Due: {data['due']}")
            embed.set_author(name=f"Quest ID: {qid}")
            embeds.append(embed)

        for embed in embeds:
            await ctx.send(embed=embed)

    @jobboard.command()
    async def accept(self, ctx, quest_id: str):
        """Accept a quest by ID."""
        quests = await self.config.guild(ctx.guild).quests()
        if quest_id not in quests:
            await ctx.send("Quest ID not found.")
            return
        await ctx.send(f"{ctx.author.mention} has accepted the quest: **{quests[quest_id]['title']}**")

    @jobboard.command()
    async def complete(self, ctx, quest_id: str):
        """Mark a quest as complete and notify the Quest Givers."""
        quests = await self.config.guild(ctx.guild).quests()
        quest = quests.get(quest_id)
        if not quest:
            await ctx.send("Quest ID not found.")
            return

        role_id = await self.config.guild(ctx.guild).quest_giver_role()
        role = ctx.guild.get_role(role_id) if role_id else None

        msg = f"{ctx.author.mention} has completed the quest: **{quest['title']}**!"
        if role:
            msg += f" {role.mention}"

        await ctx.send(msg)

        # Remove one-time quests after completion
        if not quest['recurring']:
            quests.pop(quest_id)
            await self.config.guild(ctx.guild).quests.set(quests)

    @jobboard.command()
    @commands.has_permissions(administrator=True)
    async def add(self, ctx, quest_id: str, title: str, reward: str, *, description: str):
        """Add a new one-time quest."""
        quests = await self.config.guild(ctx.guild).quests()
        quests[quest_id] = {
            "title": title,
            "description": description,
            "reward": reward,
            "due": None,
            "recurring": False
        }
        await self.config.guild(ctx.guild).quests.set(quests)
        await ctx.send(f"Quest **{title}** added with ID `{quest_id}`.")

    @jobboard.command()
    @commands.has_permissions(administrator=True)
    async def addrecurring(self, ctx, quest_id: str, title: str, reward: str, recurrence_days: int, *, description: str):
        """Add a recurring quest that refreshes every X days."""
        due_date = (datetime.utcnow() + timedelta(days=recurrence_days)).strftime('%Y-%m-%d')
        recurring_data = {
            "title": title,
            "description": description,
            "reward": reward,
            "due": due_date,
            "recurring": True,
            "interval": recurrence_days
        }
        async with self.config.guild(ctx.guild).all() as data:
            data['quests'][quest_id] = recurring_data
            data['recurring'][quest_id] = recurring_data
        await ctx.send(f"Recurring quest **{title}** added with ID `{quest_id}` and refreshes every {recurrence_days} days.")

    @jobboard.command()
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx, quest_id: str):
        """Remove a quest by ID."""
        async with self.config.guild(ctx.guild).all() as data:
            if quest_id in data['quests']:
                data['quests'].pop(quest_id)
            if quest_id in data['recurring']:
                data['recurring'].pop(quest_id)
        await ctx.send(f"Quest `{quest_id}` has been removed from the board.")

    @tasks.loop(hours=24)
    async def recurring_refresh(self):
        for guild_id in await self.config.all_guilds():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            async with self.config.guild(guild).all() as data:
                for qid, quest in list(data['recurring'].items()):
                    due_date = datetime.strptime(quest['due'], '%Y-%m-%d')
                    if datetime.utcnow() >= due_date:
                        # Refresh due date
                        new_due = (datetime.utcnow() + timedelta(days=quest['interval'])).strftime('%Y-%m-%d')
                        quest['due'] = new_due
                        data['quests'][qid] = quest
                        data['recurring'][qid] = quest
                        channel = guild.system_channel
                        if channel:
                            await channel.send(f"The recurring quest **{quest['title']}** has been refreshed!")

    @recurring_refresh.before_loop
    async def before_refresh(self):
        await self.bot.wait_until_ready()
