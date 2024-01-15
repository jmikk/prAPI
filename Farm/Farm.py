from redbot.core import commands
import discord
import sqlite3
import datetime

class Farm(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect('farm.db')  # SQLite database connection
        self.create_table()

    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                player_id INTEGER PRIMARY KEY,
                inventory TEXT
            )
        ''')
        self.conn.commit()

    async def get_player_data(self, player_id: int,depth=0):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM players WHERE player_id = ?', (player_id,))
        result = cursor.fetchone()
        if result is None and depth==0:
            # Player not found, initialize with 10 potatoes
            initial_inventory = {"potato": 10}
            cursor.execute('INSERT INTO players (player_id, inventory) VALUES (?, ?)',
                           (player_id, str(initial_inventory)))
            self.conn.commit()
            await result = self.get_player_data(player_id,1)
        return {} if result is None else {"inventory": eval(result[1])}

    async def set_player_data(self, player_id: int, data: dict):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO players (player_id, inventory) VALUES (?, ?)
        ''', (player_id, str(data.get("inventory", {}))))
        self.conn.commit()

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
    
    @commands.command()
    @commands.is_owner()
    async def reset_farm(self, ctx, target: discord.Member):
        """Drop a player by removing them from the database."""
        # Remove player from the database
        player_id = target.id
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM players WHERE player_id = ?', (player_id,))
        self.conn.commit()
    
        await ctx.send(f"{ctx.author.mention} dropped {target.mention}!")



    def __unload(self):
        self.conn.close()
