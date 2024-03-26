from redbot.core import commands

class DnDCharacterSheet(commands.Cog):
    """A simple HelloWorld cog"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def helloworld(self, ctx):
        """This command says hello world"""
        await ctx.send("Hello World!")

