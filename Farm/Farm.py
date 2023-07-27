from redbot.core import commands,data_manager
import asyncio
import os
import json
import time

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
    
    async def remove_player(self,player_id):
        db_file = data_manager.cog_data_path(self) / f"players/{player_id}"  # Use data_manager.cog_data_path() to determine the database file path)
        os.rmdir(db_file)
        
    async def make_new_player(self,player_id):
        db_file = data_manager.cog_data_path(self) / f"players/{player_id}"  # Use data_manager.cog_data_path() to determine the database file path)
        default_player_data = {
        'level': 1,
        'exp': 0,
        'gold': 100,
        'crop_rows': 1,
        'crop_cols':1,
        'potatoe': 0,
        'carrot': 0,
        'mushroom': 0,
        'corn': 0,
        'taco': 0,
        'avocado': 0,
        'potato_seeds': 10,
        'carrot_seeds': 10,
        'mushroom_seeds': 10,
        'corn_seeds': 10,
        'tacos_seeds': 10,
        'avocados_seeds': 10,
        'lastupdate' : int(time.time())
    }
        os.mkdir(db_file)
        db_file = data_manager.cog_data_path(self) / f"players/{player_id}/stats.txt"  # Use data_manager.cog_data_path() to determine the database file path)
        with open(db_file, 'w') as file:
            json.dump(default_player_data, file, indent=4)

    async def make_message(base_msg,player_id,rmb=False):
        base_msg =  base_msg + chl_levelup(player_id)
        if rmb:
            pass
            return
        else:
            return base_msg
            
    async def is_player(self,player_id):
        db_file = data_manager.cog_data_path(self) / f"players/{player_id}"  # Use data_manager.cog_data_path() to determine the database file path)
        return folder_exists(db_file)

    @commands.command()
    async def chk_stats(self,ctx):
        player_id = ctx.author.id
        if not self.is_player(player_id):
            self.make_new_player(player_id)
            await ctx.send("looks like your new let me set up your stats!")
        db_file = data_manager.cog_data_path(self) / f"players/{player_id}"  # Use data_manager.cog_data_path() to determine the database file path)
        with open(db_file, 'r') as file:
            data = json.load(file)
        await ctx.send(data)
            

    @commands.command()
    async def test(self,ctx):
        await self.make_new_player(ctx.author.id)
    
    @commands.command()
    async def test2(self,ctx):
        await self.remove_player(ctx.author.id)
    
    # Function to initialize the database and create the player table
    @commands.command()
    @commands.is_owner()
    async def make_players_folder(self,ctx):
        db_file = data_manager.cog_data_path(self) / "players"  # Use data_manager.cog_data_path() to determine the database file path)
        os.mkdir(db_file)
        await ctx.send((os.path.exists(db_file) and os.path.isdir(db_file)))
    
    # Function to initialize the database and create the player table
    @commands.command()
    @commands.is_owner()
    async def delete_players_folder(self,ctx):
        db_file = data_manager.cog_data_path(self) / "players"  # Use data_manager.cog_data_path() to determine the database file path)
        os.rmdir(db_file)
        await ctx.send((os.path.exists(db_file) and os.path.isdir(db_file)))
    
        
    #https://www.quackit.com/character_sets/emoji/emoji_v3.0/unicode_emoji_v3.0_characters_food_and_drink.cfm
    #🥔	POTATO	&#x1F954;
    #🥕	CARROT	&#x1F955;
    #🍄	MUSHROOM	&#x1F344;
    #🌽	CORN &#x1F33D;
    #🌮	TACO	&#x1F32E;
    #🥑	AVOCADO	&#x1F951;
    @commands.command()
    async def crops(self, ctx):
        await ctx.send("The current crops you can grow are 🥔 (Potato) 🥕 (Carrot) 🍄 MUSHROOM 🌽(Corn) 🌮(Taco) 🥑 (Avacado)")
