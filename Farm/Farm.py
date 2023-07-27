from redbot.core import commands
import asyncio
import os


def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False

    return commands.permissions_check(predicate)


class Farm(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
    
    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    # great once your done messing with the bot.
    #   async def cog_command_error(self, ctx, error):
    #       await ctx.send(" ".join(error.args))
    import sqlite3

    # Function to initialize the database and create the player table
    @commands.command()
    @commands.is_owner()
    async def initialize_database(self,ctx):
        db_file = data_manager.cog_data_path(self) / "players"  # Use data_manager.cog_data_path() to determine the database file path)
        os.mkdir(db_file)
        await ctx.send((os.path.exists(folder_path) and os.path.isdir(folder_path)))
        
    #https://www.quackit.com/character_sets/emoji/emoji_v3.0/unicode_emoji_v3.0_characters_food_and_drink.cfm
    #🥔	POTATO	&#x1F954;
    #🥕	CARROT	&#x1F955;
    #🍄	MUSHROOM	&#x1F344;
    #🌽	CORN &#x1F33D;
    #🌮	TACO	&#x1F32E;
    #🥑	AVOCADO	&#x1F951;
    @commands.command()
    @commands.is_owner()
    async def crops(self, ctx):
        await ctx.send("The current crops you can grow are 🥔 (Potato) 🥕 (Carrot) 🍄 MUSHROOM 🌽(Corn) 🌮(Taco) 🥑 (Avacado)")
