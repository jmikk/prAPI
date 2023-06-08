from redbot.core import commands
import asyncio
import random
import discord
import sans
import xml.etree.ElementTree as ET
import os
import discord


def is_owner_overridable():
    def predicate(ctx):
        return False
    return commands.permissions_check(predicate)


class issues(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.auth = sans.NSAuth()
        self.IssuesNation = ""
        self.client = sans.AsyncClient()
        self.vote_time = 60  # 6 hours in seconds
        self.tie_break_time = 60  # 12 hours in seconds

    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    async def api_request(self, data) -> sans.Response:
        response = await self.client.get(sans.World(**data), auth=self.auth)
        response.raise_for_status()
        return response

    @commands.command()
    @commands.is_owner()
    async def issues_agent(self, ctx, *, agent):
        sans.set_agent(agent, _force=True)
        await ctx.send("Agent set.")

    @commands.command()
    @commands.is_owner()
    async def set_issues_nation(self, ctx, *, nation):
        nation = "_".join(nation.lower().split())
        self.IssuesNation = nation
        await ctx.send(f"Set regional nation to {self.IssuesNation}")

    @commands.command()
    @commands.is_owner()
    async def set_issues_nation_password(self, ctx, *, password2):
        self.auth = sans.NSAuth(password=password2)
        await ctx.send(f"Set regional nation password for {self.IssuesNation}.")

    @commands.command()
    @commands.is_owner()
    async def issues(self, ctx):
        r = await self.api_request(data={'nation': self.IssuesNation, 'q': 'issues'})
        root = ET.fromstring(r.text)
        issues = root.findall('ISSUES/ISSUE')
        issue = issues[0]
        issue_id = issue.attrib['id']
        title = issue.find('TITLE').text
        text = issue.find('TEXT').text
        author = issue.find('AUTHOR').text
        editor = issue.find('EDITOR').text
        pic1 = issue.find('PIC1').text
        pic2 = issue.find('PIC2').text
        options = [
            {'id': option.attrib['id'], 'text': option.text}
            for option in issue.findall('OPTION')
        ]
        embed = discord.Embed(
            title=title,
            description='The issue at hand',
            color=discord.Color.blue()
        )
        embed.set_author(name=f'Written by {author}, Edited by {editor}')
        embed.add_field(name='The issue', value=text, inline=False)
        message = await ctx.send(embed=embed)

        for option in options:
            embed = discord.Embed(
                title="This might work...",
                color=discord.Color.blue()
            )
            embed.add_field(name=option['id'], value=option['text'], inline=False)
            option_message = await ctx.send(embed=embed)
            await option_message.add_reaction('👍')  # Add thumbs up reaction to each option message

        await asyncio.sleep(self.vote_time)  # Wait for the voting time

        reactions = []
        for option in options:
            option_message = discord.utils.get(ctx.channel.messages, id=option_message.id)
            reaction = discord.utils.get(option_message.reactions, emoji='👍')
            if reaction:
                reactions.append((option['id'], reaction.count))

        if not reactions:
            chosen_option = random.choice(options)
        else:
            max_votes = max(reactions, key=lambda x: x[1])[1]
            tied_options = [option for option, votes in reactions if votes == max_votes]

            if len(tied_options) > 1:
                await asyncio.sleep(self.tie_break_time)
                chosen_option = random.choice(tied_options)
            else:
                chosen_option = tied_options[0]

        await self.AnswerIssue(ctx, chosen_option)

    async def AnswerIssue(self, ctx, option_id):
        # Implement your logic to answer the issue with the chosen option
        pass

    @commands.command()
    @commands.is_owner()
    async def myCom(self, ctx):
        await ctx.send("I work")
