from redbot.core import commands, Config
import discord
import random
import asyncio



def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False

    return commands.permissions_check(predicate)


class Table(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        # Define a default guild setting structure
        default_guild = {
            "tables": {}
        }

        self.config.register_guild(**default_guild)

    @commands.guild_only()
    @commands.group(name="table")
    async def table_group(self, ctx):
        """Commands for managing D&D tables."""
        pass

