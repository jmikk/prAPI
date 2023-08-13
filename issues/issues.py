from redbot.core import commands
import asyncio
import random
import discord
import sans
import xml.etree.ElementTree as ET
import os
import discord
from discord.ui import Button
import json
from datetime import datetime, timedelta
from discord import AllowedMentions


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
        self.vote_time = 60  
        #self.vote_time = 43200  # 6 hours in seconds
        self.tie_break_time = 43200  # 12 hours in seconds  
        self.stop_loop = False  # Flag to control the while loop
        self.password=""
        
    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    async def api_request(self, data) -> sans.Response:
        response = await self.client.get(sans.World(**data), auth=self.auth)
        response.raise_for_status()
        return response

    @commands.command()
    @commands.is_owner()
    async def stop_issues_loop(self, ctx):
        self.stop_loop = True
        await ctx.send("Stopping the issues loop.")
    
    
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
        self.password = password2
        self.auth = sans.NSAuth(password=password2)
        await ctx.send(f"Set regional nation password for {self.IssuesNation}.")

    @commands.command()
    @commands.is_owner()
    async def issues(self, ctx):
        self.stop_loop = False
        while not self.stop_loop:
            self.auth = sans.NSAuth(password=self.password)
            r = await self.api_request(data={'nation': self.IssuesNation, 'q': 'issues'})
            root = ET.fromstring(r.text)
            issues = root.findall('ISSUES/ISSUE')
            issue = issues[0]
            issue_id = issue.attrib['id']
            title = issue.find('TITLE').text
            text = issue.find('TEXT').text
            try:
                author = issue.find('AUTHOR').text
            except AttributeError: 
                author = "None"
            try:
                editor = issue.find('EDITOR').text
            except AttributeError: 
                editor = "None"
            

            pic1 = issue.find('PIC1').text
            pic2 = issue.find('PIC2').text
            option_messages = []
            op_ids={}
            
            options = [
                {'id': option.attrib['id'], 'text': option.text.replace("<i>","*").replace("</i>","*").replace("<b>","**").replace("</b>","**")}
                for option in issue.findall('OPTION')
            ]

            embed = discord.Embed(
                    title=title,
                    description=text.replace("<i>","*").replace("</i>","*").replace("<b>","**").replace("</b>","**"))
            embed.color=discord.Color.blue()

            embed.set_footer(text=f"Written by: {author}, Edited by: {editor}")
            message = await ctx.send(embed=embed)
            counter=0
            for option in options:
                counter=counter+1
                embed = discord.Embed(title=f"Option {counter}")
                if counter%6 == 0: 
                    embed.color = discord.Color.purple()
                elif counter%6 == 1:
                    embed.color = discord.Color.blue()
                elif counter%6 == 2:
                    embed.color = discord.Color.green()
                elif counter%6 == 3:
                    embed.color = discord.Color.red()
                elif counter%6 == 4:
                    embed.color = discord.Color.orange()
                elif counter%6 == 5:
                    embed.color = discord.Color.gold()
                   
                embed.add_field(name="\u200b", value=option['text'].replace("<i>","*").replace("</i>","*").replace("<b>","**").replace("</b>","**"), inline=False)
                option_message = await ctx.send(embed=embed)
                op_ids[option_message.id]=option['id']
                option_messages.append(option_message.id)  # Add the message ID to the option_messages list
                await option_message.add_reaction('👍')  # Add thumbs up reaction to each option message
            
            target_time = datetime.utcnow() + timedelta(seconds=self.vote_time-18000)
            unix_timestamp = int(target_time.timestamp())
            role_id = 1130304387156279368
            allowed_mentions = AllowedMentions(
            everyone=False,  # Disables @everyone and @here mentions
            users=True,      # Enables user mentions
            roles=True       # Enables role mentions
        )
            await ctx.send(f"Once again I call upon <@&{role_id}> to decide <t:{unix_timestamp}:R>.  If you can't all agree I'll pick one randomly.",allowed_mentions=allowed_mentions)
            await asyncio.sleep(self.vote_time)  # Wait for the voting time
            
            reactions = []
            channel = ctx.channel
            for option_message_id in option_messages:
                option_message = await channel.fetch_message(option_message_id)
                for reaction in option_message.reactions:
                    if str(reaction.emoji) == '👍':
                        reactions.append(reaction)

            # Determine the winning option based on the number of votes
            winning_option = None
            max_votes = 0
            for reaction in reactions:
                if reaction.count > max_votes:
                    max_votes = reaction.count

            tied_options = []
            for reaction in reactions:
                if reaction.count == max_votes:
                    tied_options.append(reaction.message)

            if tied_options:
                winning_option = random.choice(tied_options)
            else:
                winning_option = random.choice(option_messages)
            #await ctx.send(f"picked option {op_ids[winning_option.id]}")
            data = payload = {
            "nation": self.IssuesNation,
            "c": "issue",
            "issue": issue_id,
            "option": op_ids[winning_option.id]
                                }
            if not self.stop_loop:
                r = await self.api_request(data)
                # Load the XML document
                
                # Get the root element of the XML
                try:
                    root = ET.fromstring(r.text)
                except ET.ParseError:
                    channel_id = 1140421534503161866  
                    channel = ctx.get_channel(channel_id)
                    await channel.send(r.text)
                    
                # Find the <DESC> element using XPath
                desc_element = root.find('.//DESC')
            
                target_time = datetime.utcnow() + timedelta(seconds=3600-18000)
                unix_timestamp = int(target_time.timestamp())
                embed = discord.Embed(
                    title=f" The Fates have decided, now enjoy the outcome. I must rest before the next reading I will be ready <t:{unix_timestamp}:R>",
                    color=discord.Color.purple()
                )
                embed.add_field(name="Fresh from the well", value=desc_element.text.replace("<i>","*").replace("</i>","*").replace("<b>","**").replace("</b>","**"), inline=False)

                given_name="the-threads-of-fate"
                channel = discord.utils.get(ctx.guild.channels, name=given_name)
                channel_id = channel.id
                channel_out = ctx.guild.get_channel(channel_id)

                await channel_out.send(embed=embed)
                self.auth = sans.NSAuth(password=self.password)
                str2 = f"Fresh from the well, \n  "+desc_element.text.replace("<i>","*").replace("</i>","*").replace("<b>","**").replace("</b>","**")+" \n If you would like to help decide my fate join our discord where you can vote every 12 hours."
                data = {
                    "nation": self.IssuesNation,
                    "region": Region,
                    "c": "rmbpost",
                    "text": str2,
                    "mode": "prepare",
                }
                r = await self.api_request(data=data)
                rmbToken = r.xml.find("SUCCESS").text
                data.update(mode="execute", token=rmbToken)
                r = await self.api_request(data=data)
                
                await asyncio.sleep(3600)  # Wait for the voting time

                
            

    @commands.command()
    @commands.is_owner()
    async def myCom(self, ctx):
        given_name="the-threads-of-fate"
        channel = discord.utils.get(ctx.guild.channels, name=given_name)
        channel_id = channel.id
        channel_out = ctx.guild.get_channel(channel_id)

        await channel_out.send("I still work")
