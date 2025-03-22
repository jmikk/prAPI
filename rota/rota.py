import discord
from redbot.core import commands, Config, tasks
import aiohttp
import xml.etree.ElementTree as ET
import asyncio
from datetime import datetime, timedelta

API_URL = "https://www.nationstates.net/cgi-bin/api.cgi"

class rota(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_global(
            votes={}, last_activity=None, issue_id=None, nation="the_phoenix_of_the_spring",
            password="", user_agent="UserAgent Example", vote_active=False
        )
        self.check_activity.start()

    def cog_unload(self):
        self.check_activity.cancel()

    async def fetch_issues(self):
        nation = await self.config.nation()
        password = await self.config.password()
        user_agent = await self.config.user_agent()

        headers = {"X-Password": password, "User-Agent": user_agent}
        params = {"nation": nation, "q": "issues"}

        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, headers=headers, params=params) as resp:
                text = await resp.text()
                return text

    async def answer_issue(self, issue_id, option_id):
        nation = await self.config.nation()
        password = await self.config.password()
        user_agent = await self.config.user_agent()

        headers = {"X-Password": password, "User-Agent": user_agent}
        data = {
            "nation": nation,
            "c": "issue",
            "issue": issue_id,
            "option": option_id
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, headers=headers, data=data) as resp:
                return await resp.text()

    @commands.command()
    @commands.guild_only()
    async def postissue(self, ctx):
        """Fetch and post the latest issue with voting buttons."""
        xml_data = await self.fetch_issues()
        root = ET.fromstring(xml_data)

        issue = root.find(".//ISSUE")
        if issue is None:
            await ctx.send("No current issues found.")
            return

        issue_id = issue.get("id")
        title = issue.find("TITLE").text
        text = issue.find("TEXT").text

        options = issue.findall("OPTION")
        view = discord.ui.View(timeout=None)

        for option in options:
            option_id = option.get("id")
            label = option.text[:80]  # Shorten label if too long
            view.add_item(VoteButton(option_id=option_id, label=label))

        await self.config.votes.clear()
        await self.config.issue_id.set(issue_id)
        await self.config.last_activity.set(datetime.utcnow().isoformat())
        await self.config.vote_active.set(True)

        embed = discord.Embed(title=title, description=text, color=discord.Color.blue())
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def endvote(self, ctx):
        """Force end the current vote and submit the answer."""
        active = await self.config.vote_active()
        if not active:
            await ctx.send("No active vote to end.")
            return

        await self.submit_vote(ctx.channel)

    @commands.command()
    async def stoprota(self, ctx):
        """Stop the rota voting loop."""
        await self.config.vote_active.set(False)
        await ctx.send("Rota voting loop stopped.")

    @tasks.loop(minutes=30)
    async def check_activity(self):
        channel_id = 1323331769012846592
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        active = await self.config.vote_active()
        if not active:
            return

        last_activity_str = await self.config.last_activity()
        if not last_activity_str:
            return

        last_activity = datetime.fromisoformat(last_activity_str)
        now = datetime.utcnow()
        issue_time_limit = last_activity + timedelta(hours=24)
        max_time_limit = last_activity + timedelta(days=5)

        if now >= issue_time_limit or now >= max_time_limit:
            await self.submit_vote(channel)

    async def submit_vote(self, channel):
        votes = await self.config.votes()
        if not votes:
            await channel.send("No votes were cast. Issue dismissed.")
            issue_id = await self.config.issue_id()
            xml_response = await self.answer_issue(issue_id, -1)
            await channel.send(f"Dismissed Issue #{issue_id}. Response:\n```
{xml_response}```")
        else:
            option_counts = {}
            for opt in votes.values():
                option_counts[opt] = option_counts.get(opt, 0) + 1

            top_option = max(option_counts, key=option_counts.get)
            issue_id = await self.config.issue_id()

            xml_response = await self.answer_issue(issue_id, top_option)
            await channel.send(f"Issue #{issue_id} answered with Option #{top_option}. Response:\n```
{xml_response}```")

        await self.config.votes.clear()
        await self.config.issue_id.clear()
        await self.config.last_activity.clear()
        await self.config.vote_active.set(False)

class VoteButton(discord.ui.Button):
    def __init__(self, option_id, label):
        super().__init__(label=f"Vote Option {option_id}", style=discord.ButtonStyle.primary)
        self.option_id = option_id

    async def callback(self, interaction: discord.Interaction):
        cog: Rota = interaction.client.get_cog("Rota")
        votes = await cog.config.votes()
        votes[str(interaction.user.id)] = self.option_id
        await cog.config.votes.set(votes)
        await cog.config.last_activity.set(datetime.utcnow().isoformat())
        await interaction.response.send_message(f"Your vote for Option {self.option_id} has been recorded.", ephemeral=True)
