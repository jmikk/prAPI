import discord
from redbot.core import commands, Config
from discord.ext import tasks
import aiohttp
import xml.etree.ElementTree as ET
import asyncio
import random
import io
import re
from datetime import datetime, timedelta

API_URL = "https://www.nationstates.net/cgi-bin/api.cgi"
RESULTS_CHANNEL_ID = 1130324894031290428  # Channel for outputting results

# Example face URLs categorized by gender
FACE_IMAGES = {
    "male": [
        "https://randomuser.me/api/portraits/men/1.jpg",
        "https://randomuser.me/api/portraits/men/2.jpg",
        "https://randomuser.me/api/portraits/men/3.jpg",
        "https://randomuser.me/api/portraits/men/4.jpg",
        "https://randomuser.me/api/portraits/men/5.jpg",
        "https://randomuser.me/api/portraits/men/6.jpg",
        "https://randomuser.me/api/portraits/men/7.jpg",
        "https://randomuser.me/api/portraits/men/8.jpg",
        "https://randomuser.me/api/portraits/men/9.jpg",
        "https://randomuser.me/api/portraits/men/10.jpg",
        "https://randomuser.me/api/portraits/men/11.jpg",
        "https://randomuser.me/api/portraits/men/12.jpg",
        "https://randomuser.me/api/portraits/men/13.jpg",
        "https://randomuser.me/api/portraits/men/14.jpg",
        "https://randomuser.me/api/portraits/men/15.jpg",
        "https://randomuser.me/api/portraits/men/16.jpg",
        "https://randomuser.me/api/portraits/men/17.jpg",
        "https://randomuser.me/api/portraits/men/18.jpg",
        "https://randomuser.me/api/portraits/men/19.jpg",
        "https://randomuser.me/api/portraits/men/20.jpg",
        "https://randomuser.me/api/portraits/men/21.jpg",
    ],
    "female": [
        "https://randomuser.me/api/portraits/women/1.jpg",
        "https://randomuser.me/api/portraits/women/2.jpg",
        "https://randomuser.me/api/portraits/women/3.jpg",
        "https://randomuser.me/api/portraits/women/4.jpg",
        "https://randomuser.me/api/portraits/women/5.jpg",
        "https://randomuser.me/api/portraits/women/6.jpg",
        "https://randomuser.me/api/portraits/women/7.jpg",
        "https://randomuser.me/api/portraits/women/8.jpg",
        "https://randomuser.me/api/portraits/women/9.jpg",
        "https://randomuser.me/api/portraits/women/10.jpg",
        "https://randomuser.me/api/portraits/women/11.jpg",
        "https://randomuser.me/api/portraits/women/12.jpg",
        "https://randomuser.me/api/portraits/women/13.jpg",
        "https://randomuser.me/api/portraits/women/14.jpg",
        "https://randomuser.me/api/portraits/women/15.jpg",
        "https://randomuser.me/api/portraits/women/16.jpg",
        "https://randomuser.me/api/portraits/women/17.jpg",
        "https://randomuser.me/api/portraits/women/18.jpg",
        "https://randomuser.me/api/portraits/women/19.jpg",
        "https://randomuser.me/api/portraits/women/20.jpg",
        
    ],
    "neutral": [
        "https://randomuser.me/api/portraits/lego/1.jpg",
        "https://randomuser.me/api/portraits/lego/2.jpg",
        "https://randomuser.me/api/portraits/lego/3.jpg",
        "https://randomuser.me/api/portraits/lego/4.jpg",
        "https://randomuser.me/api/portraits/lego/5.jpg",
        "https://randomuser.me/api/portraits/lego/6.jpg",
        "https://randomuser.me/api/portraits/lego/7.jpg",
        "https://randomuser.me/api/portraits/lego/8.jpg",
        "https://randomuser.me/api/portraits/lego/9.jpg",
    ]
}

# Map of rank IDs to human-readable stat names (examples)
STAT_NAMES = {
    "0": "Civil Rights",
    "5": "Economy",
    "7": "Political Freedoms",
    "8": "Education",
    "9": "Healthcare",
    "13": "Safety",
    "14": "Defense",
    "16": "Environment",
    "17": "Technology",
    "19": "Culture",
    # Add more mappings as needed
}

class rota(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9007)
        self.config.register_global(
            votes={}, last_activity=None, issue_id=None, nation="",
            password="", user_agent="rota by 9005", vote_active=False
        )
        self.check_activity.start()

    def cog_unload(self):
        self.check_activity.cancel()

    def summarize_option(option_id, text):
        title_match = re.search(r'(Dr\.|Mr\.|Mrs\.|Ms\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?', text)
        if title_match:
            return title_match.group(0)
    
        minister_match = re.search(r'Minister (?:for|of) [A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text)
        if minister_match:
            return minister_match.group(0)
    
        proper_nouns = re.findall(r'\b[A-Z][a-z]+\b', text)
        if proper_nouns:
            return proper_nouns[0]
    
        return f"Option {option_id}"  # Default fallback

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

        option_summaries = {}

        for option in options:
            option_id = option.get("id")
            option_text = option.text

            gender = self.detect_gender(option_text)
            face_url = random.choice(FACE_IMAGES.get(gender, FACE_IMAGES["neutral"]))

            title_summary = self.summarize_option(option_text)

            embed = discord.Embed(title=title_summary, description=option_text, color=discord.Color.green())
            embed.set_thumbnail(url=face_url)

            view = discord.ui.View(timeout=None)
            view.add_item(VoteButton(option_id=option_id, label=f"Vote for Option {option_id}"))
            await ctx.send(embed=embed, view=view)

            option_summaries[option_id] = title_summary

        await self.config.option_summaries.set(option_summaries)

    @commands.command()
    async def endvote(self, ctx):
        active = await self.config.vote_active()
        if not active:
            await ctx.send("No active vote to end.")
            return

        await self.process_vote()

    @tasks.loop(minutes=1)
    async def check_activity(self):
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
            await self.process_vote()

    async def process_vote(self):
        channel = self.bot.get_channel(RESULTS_CHANNEL_ID)
        if not channel:
            return

        votes = await self.config.votes()
        issue_id = await self.config.issue_id()

        if not votes:
            xml_response = await self.answer_issue(issue_id, -1)
            root = ET.fromstring(xml_response)
            headline = root.findtext(".//HEADLINE", default="No headlines.")
            embed = discord.Embed(title="Issue Dismissed", description=headline, color=discord.Color.red())
            embed.set_footer(text=f"Issue #{issue_id} was dismissed due to no votes.")
            await channel.send(embed=embed, file=discord.File(io.StringIO(xml_response), filename=f"issue_{issue_id}_dismissed.xml"))
        else:
            option_counts = {}
            for opt in votes.values():
                option_counts[opt] = option_counts.get(opt, 0) + 1

            top_option = max(option_counts, key=option_counts.get)

            xml_response = await self.answer_issue(issue_id, top_option)
            root = ET.fromstring(xml_response)

            desc = root.findtext(".//DESC", default="No description.")
            rankings = root.findall(".//RANK")
            reclasses = root.findall(".//RECLASSIFY")
            headlines = [el.text for el in root.findall(".//HEADLINE")]
            top_stats = sorted(rankings, key=lambda x: abs(float(x.find("CHANGE").text)), reverse=True)[:3]

            embed = discord.Embed(title=desc, color=discord.Color.purple())

            stat_summary = ""
            for stat in top_stats:
                rank_id = stat.get("id")
                stat_name = STAT_NAMES.get(rank_id, f"Rank {rank_id}")
                change = stat.find("CHANGE").text
                pchange = stat.find("PCHANGE").text
                stat_summary += f"{stat_name}: {change} ({pchange}%)\n"

            if stat_summary:
                embed.add_field(name="Top Stat Changes", value=stat_summary, inline=False)

            if reclasses:
                reclass_text = "\n".join([f"{r.find('FROM').text} → {r.find('TO').text}" for r in reclasses])
                embed.add_field(name="Policy Changes", value=reclass_text, inline=False)

            if headlines:
                embed.set_footer(text=random.choice(headlines))

            await channel.send(embed=embed, file=discord.File(io.StringIO(xml_response), filename=f"issue_{issue_id}_option_{top_option}.xml"))

        await self.config.votes.clear()
        await self.config.issue_id.clear()
        await self.config.last_activity.clear()
        await self.config.vote_active.set(False)
        await self.config.option_summaries.clear()

class VoteButton(discord.ui.Button):
    def __init__(self, option_id, label):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.option_id = option_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("rota")
        if not cog:
            await interaction.response.send_message("Voting system is currently unavailable.", ephemeral=True)
            return

        # Record the vote
        votes = await cog.config.votes()
        votes[str(interaction.user.id)] = self.option_id
        await cog.config.votes.set(votes)

        # Update last activity to extend vote timer
        await cog.config.last_activity.set(datetime.utcnow().isoformat())

        await interaction.response.send_message(
            f"Your vote for Option {self.option_id} has been recorded.",
            ephemeral=True
        )

