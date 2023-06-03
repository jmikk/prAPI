from redbot.core import commands
import asyncio
import sans
import xml.etree.ElementTree as ET
import os


def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False
    return commands.permissions_check(predicate)


class issues(commands.Cog):
    """My custom cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.auth = sans.NSAuth()
        self.IssueNation = ""
        self.client = sans.AsyncClient()
        
    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    # great once your done messing with the bot.
    #   async def cog_command_error(self, ctx, error):
    #       await ctx.send(" ".join(error.args))

    async def api_request(self, data) -> sans.Response:
        response = await self.client.get(sans.World(**data), auth=self.auth)
        response.raise_for_status()
        return response
    
    @commands.command()
    @commands.is_owner()
    async def issues_agent(self, ctx, *,agent):
        sans.set_agent(agent, _force=True)
        await ctx.send("Agent set.")
   
    @commands.command()
    @commands.is_owner()
    async def set_issues_nation(self, ctx, *, nation):
        nation = "_".join(nation.lower().split())
        self.RegionalNation = nation
        await ctx.send(f"Set regional nation to {self.RegionalNation}")

    @commands.command()
    @commands.is_owner()
    async def set_issues_nation_password(self, ctx, *, password2):
        self.auth = sans.NSAuth(password=password2)
        await ctx.send(f"Set regional nation password for {self.RegionalNation}.")
    
    @commands.command()
    @commands.is_owner()
    async def issues(self,ctx):
        await ctx.send("idk boss")
        r = await self.api_request(data={'nation': self.IssueNation, 'q': 'issues'})
        # Extracting data from the parsed XML
        issues=r.xml.findall("issue")
        await ctx.send(issues)
        await ctx.send(r.text)
        for issue in issues:
            title = issue.find('title').text
            text = issue.find('text').text
            author = issue.find('author').text
            editor = issue.find('editor').text
            embed = discord.Embed(
                        title=title,
                        description='The issue at hand',
                        color=discord.Color.blue()  # You can set a custom color for the embed
                    )
            embed.set_author(name=f'Written by {author}, Edited by {editor}')
            embed.add_field(name='The issue', value=text, inline=False)
            await ctx.send(embed=embed)
            options = issue.findall('option')

            for option in options:
                option_id = option['id']
                option_text = option.text
                embed = discord.Embed(
                        title=option_id,
                        description='One way to handle it.',
                        color=discord.Color.blue()  # You can set a custom color for the embed
                    )
                embed.add_field(name='The option', value=option_text, inline=False)
                await ctx.send(embed=embed)


                
        

    
    
    
    
    
    @commands.command()
    @commands.is_owner()
    async def myCom(self, ctx):
        await ctx.send("I work")
