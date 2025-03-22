import discord
from redbot.core import commands, Config
from discord.ext import tasks
import aiohttp
import xml.etree.ElementTree as ET
import asyncio
import random
import io
from datetime import datetime, timedelta

API_URL = "https://www.nationstates.net/cgi-bin/api.cgi"

# Example face URLs categorized by gender
FACE_IMAGES = {
    "male": [
        "https://randomuser.me/api/portraits/men/1.jpg",
        "https://randomuser.me/api/portraits/men/3.jpg",
        "https://randomuser.me/api/portraits/men/5.jpg"
    ],
    "female": [
        "https://randomuser.me/api/portraits/women/2.jpg",
        "https://randomuser.me/api/portraits/women/4.jpg"
    ],
    "neutral": [
        "https://randomuser.me/api/portraits/lego/1.jpg"
    ]
}

class rota(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9007)
        self.config.register_global(
            votes={}, last_activity=None, issue_id=None, nation="testlandia",
            password="hunter2", user_agent="UserAgent Example", vote_active=False
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

    def detect_gender(self, text):
        text = text.lower()
        female_keywords = [" she ", " her ", " woman", " girl", " niece"]
        male_keywords = [" he ", " his ", " man", " boy", " uncle"]

        for word in female_keywords:
            if word in text:
                return "female"
        for word in male_keywords:
            if word in text:
                return "male"
        return "neutral"

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

        await self.config.votes.clear()
        await self.config.issue_id.set(issue_id)
        await self.config.last_activity.set(datetime.utcnow().isoformat())
        await self.config.vote_active.set(True)

        issue_embed = discord.Embed(title=title, description=text, color=discord.Color.blue())
        await ctx.send(embed=issue_embed)

        for option in options:
            option_id = option.get("id")
            option_text = option.text

            gender = self.detect_gender(option_text)
            face_url = random.choice(FACE_IMAGES.get(gender, FACE_IMAGES["neutral"]))

            embed = discord.Embed(title=f"Option {option_id}", description=option_text, color=discord.Color.green())
            embed.set_thumbnail(url=face_url)

            view = discord.ui.View(timeout=None)
            view.add_item(VoteButton(option_id=option_id, label=f"Vote for Option {option_id}"))
            await ctx.send(embed=embed, view=view)

    @commands.command()
    async def endvote(self, ctx):
        """Force end the current vote and submit the answer."""
        active = await self.config.vote_active()
        if not active:
            await ctx.send("No active vote to end.")
            return

        await self.process_vote(ctx.channel)

    @commands.command()
    async def stoprota(self, ctx):
        """Stop the rota voting loop."""
        await self.config.vote_active.set(False)
        await ctx.send("Rota voting loop stopped.")

    @commands.command()
    async def setrota(self, ctx, nation: str, password: str, user_agent: str):
        """Set the NationStates nation, password, and user agent."""
        await self.config.nation.set(nation)
        await self.config.password.set(password)
        await self.config.user_agent.set(user_agent)
        await ctx.send(f"Configuration updated: Nation='{nation}', Password='[HIDDEN]', User-Agent='{user_agent}'")

    @tasks.loop(minutes=1)
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
        issue_time_limit = last_activity + timedelta(minutes=5)
        max_time_limit = last_activity + timedelta(minutes=10)

        if now >= issue_time_limit or now >= max_time_limit:
            await self.process_vote(channel)

    async def process_vote(self, channel):
        votes = await self.config.votes()
        issue_id = await self.config.issue_id()

        if not votes:
            xml_response = await self.answer_issue(issue_id, -1)
            desc = ET.fromstring(xml_response).find(".//HEADLINE")
            summary = desc.text if desc is not None else "No headlines."
            await channel.send(f"No votes were cast. Issue #{issue_id} dismissed.\n**Headline:** {summary}",
                               file=discord.File(io.StringIO(xml_response), filename=f"issue_{issue_id}_dismissed.xml"))
        else:
            option_counts = {}
            for opt in votes.values():
                option_counts[opt] = option_counts.get(opt, 0) + 1

            top_option = max(option_counts, key=option_counts.get)

            xml_response = await self.answer_issue(issue_id, top_option)
            root = ET.fromstring(xml_response)
            desc = root.find(".//DESC")
            summary = desc.text if desc is not None else "No description."
            await channel.send(f"Issue #{issue_id} answered with Option #{top_option}.\n**Result:** {summary}",
                               file=discord.File(io.StringIO(xml_response), filename=f"issue_{issue_id}_option_{top_option}.xml"))

        await self.config.votes.clear()
        await self.config.issue_id.clear()
        await self.config.last_activity.clear()
        await self.config.vote_active.set(False)

class VoteButton(discord.ui.Button):
    def __init__(self, option_id, label):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.option_id = option_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("rota")
        if not cog:
            await interaction.response.send_message("Voting system is currently unavailable.", ephemeral=True)
            return

        votes = await cog.config.votes()
        votes[str(interaction.user.id)] = self.option_id
        await cog.config.votes.set(votes)
        await cog.config.last_activity.set(datetime.utcnow().isoformat())
        await interaction.response.send_message(f"Your vote for Option {self.option_id} has been recorded.", ephemeral=True)
