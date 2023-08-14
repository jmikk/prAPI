from redbot.core import commands,config
import discord
import datetime
import sqlite3


class Farm(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "players": {}  # Dictionary to store player data
        }
        self.config.register_global(**default_global)
    async def get_player_data(self, player_id: int):
    players = await self.config.players()
    return players.get(player_id, {})

    async def set_player_data(self, player_id: int, data: dict):
        players = await self.config.players()
        players[player_id] = data
        await self.config.players.set(players)

    @commands.command()
    async def inventory(self, ctx):
        player_id = ctx.author.id
        player_data = await self.get_player_data(player_id)
        inventory = player_data.get("inventory", {})
        
        if not inventory:
            await ctx.send("Your inventory is empty.")
            return
        
        inventory_text = "\n".join([f"{item}: {count}" for item, count in inventory.items()])
        await ctx.send(f"Your inventory:\n{inventory_text}")

    @commands.command()
    async def plant(self, ctx, crop: str):
        player_id = ctx.author.id
        crop = crop.lower()
        
        if crop not in ["potato", "carrot", "mushroom", "corn", "taco", "avocado"]:
            await ctx.send("Invalid crop name.")
            return
        
        player_data = await self.get_player_data(player_id)
        inventory = player_data.get("inventory", {})
        
        if inventory.get(crop, 0) > 0:
            inventory[crop] -= 1
            await self.set_player_data(player_id, {"inventory": inventory})
            
            await ctx.send(f"You planted a {crop}!")
        else:
            await ctx.send(f"You don't have any {crop} to plant.")
    @commands.command()
    async def harvest(self, ctx, crop: str):
        player_id = ctx.author.id
        crop = crop.lower()
        
        player_data = await self.get_player_data(player_id)
        inventory = player_data.get("inventory", {})
        
        if crop in inventory:
            inventory[crop] += 1
        else:
            inventory[crop] = 1
        
        await self.set_player_data(player_id, {"inventory": inventory})
        await ctx.send(f"You harvested a {crop}!")
            
    
