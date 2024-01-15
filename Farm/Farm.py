from redbot.core import commands,tasks
import discord
import sqlite3
import datetime

class Farm(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect('farm.db')  # SQLite database connection
        self.create_table()
        self.save_data.start()  # Start the daily save task

    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                player_id INTEGER PRIMARY KEY,
                inventory TEXT
            )
        ''')
        self.conn.commit()

    async def get_player_data(self, player_id: int):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM players WHERE player_id = ?', (player_id,))
        result = cursor.fetchone()
        return {} if result is None else {"inventory": eval(result[1])}

    async def set_player_data(self, player_id: int, data: dict):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO players (player_id, inventory) VALUES (?, ?)
        ''', (player_id, str(data.get("inventory", {}))))
        self.conn.commit()

    
    @commands.Cog.listener()
    async def on_ready(self):
        self.save_data.start()  # Start the daily save task when the bot is ready

    @tasks.loop(hours=24)  # Run the task every 24 hours
    async def save_data(self):
        print("Saving data to the database...")
        # Implement your logic to save data here
        # Example: Iterate through players and save their data

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

    def __unload(self):
        self.save_data.cancel()  # Stop the daily save task
        self.conn.close()
