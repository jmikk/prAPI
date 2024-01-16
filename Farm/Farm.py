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
                inventory_seeds TEXT
                inventory_crops TEXT
                inventory_loot TEXT
                plot_size INTEGER
                gold INTEGER
            )
        ''')
        self.conn.commit()
        
    @commands.command()
    async def recreate_player_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                player_id INTEGER PRIMARY KEY,
                inventory_seeds TEXT
                inventory_crops TEXT
                inventory_loot TEXT
                plot_size INTEGER
                gold INTEGER
            )
        ''')
        self.conn.commit()

    @commands.command()
    async def list_farm_tables(self, ctx):
        """List all tables in the database."""
        tables = self.list_tables()
        await ctx.send("Tables in the database:\n" + "\n".join(tables))

    def list_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        return [table[0] for table in tables]

    
    async def get_player_data(self, player_id: int,depth=0):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM players WHERE player_id = ?', (player_id,))
        result = cursor.fetchone()
        if result is None and depth==0:
            # Player not found, initialize with 10 potatoes
            initial_inventory = {"potato": 10}
            cursor.execute('INSERT INTO players (player_id, inventory_seeds,inventory_crops, inventory_loot, plot_size, gold) VALUES (?, ?, ?, ?, ?, ?)',
                           (player_id, str(initial_inventory),"","",1,0))
            self.conn.commit()
            return await self.get_player_data(player_id,depth=1)
        return {} if result is None else {"player_id": result[0], "inventory": eval(result[1])}

    
    async def set_player_seeds(self, player_id: int, data: dict):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO players (player_id, inventory_seeds) VALUES (?, ?)
        ''', (player_id, str(data.get("inventory_seeds", {}))))
        self.conn.commit()

    @commands.command()
    async def inventory(self, ctx):
        player_id = ctx.author.id
        player_data = await self.get_player_data(player_id)
        inventory_seeds = player_data.get("inventory_seeds", {})

        if not inventory_seeds:
            await ctx.send("Your inventory is empty.")
            return

        inventory_text = "\n".join([f"{item}: {count}" for item, count in inventory_seeds.items()])
        
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
    @commands.is_owner()
    async def reset_farm(self, ctx, target: discord.Member):
        """Drop a player by removing them from the database."""
        # Remove player from the database
        player_id = target.id
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM players WHERE player_id = ?', (player_id,))
        self.conn.commit()
    
        await ctx.send(f"{ctx.author.mention} dropped {target.mention}!")

    @commands.command()
    @commands.is_owner()
    async def drop_players_table(self, ctx):
        """Drop the entire players table from the database."""
        self.drop_table("players")
        await ctx.send("The players table has been dropped.")

    def drop_table(self, table_name):
        cursor = self.conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
        self.conn.commit()


    @commands.command()
    async def sleep(self, ctx):
        """Simulate sleeping to help crops grow."""
        player_id = ctx.author.id
        player_data = await self.get_player_data(player_id)
        inventory = player_data.get("inventory", {})

        # Simulate growth for each crop based on one night slept
        for crop, growth_chance in self.crop_growth.items():
            if crop in inventory:
                # Calculate growth chance for each crop
                if random.random() <= growth_chance:
                    # Crop is ready to be harvested
                    inventory[crop] += 1

        await self.set_player_data(player_id, {"inventory": inventory})
        await ctx.send("You slept for one night. Crops have grown!")

    # ... (other commands)

    crop_growth = {
        "potato": 0.8,  # 80% chance
        "carrot": 0.6,  # 60% chance
        "mushroom": 0.7,  # 70% chance
        "corn": 0.5,  # 50% chance
        "taco": 0.4,  # 40% chance
        "avocado": 0.2,  # 20% chance
    }



    def __unload(self):
        self.conn.close()
