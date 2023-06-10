import discord
from redbot.core import commands, Config
import sqlite3
import csv

class CardQ(commands.Cog):
    def __init__(self, bot):
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {"database_path": "/home/pi/cards.db"}
        self.config.register_global(**default_global)
        self.bot = bot
    
    async def cleankey(self,key):
        match key:
            case "rarity":
                return card_category
            defult:
                return key
    
    
    @commands.cooldown(rate=1, per=30, type=commands.BucketType.guild)
    @commands.command()
    async def card_search(self, ctx, *, criteria):
        await ctx.send("I'll think about it")

        # Split the input criteria into individual search terms
        search_terms = criteria.split("+")

        # Create a dictionary to store the search criteria
        search_criteria = {}

        # Parse each search term and extract the key-value pair
        for term in search_terms:
            if ":" in term:
                key, value = term.split(":", 1)
                key = key.lower().strip()
                key = self.cleankey(key)
                if key="tropy"
                value = value.strip()
                search_criteria[key] = value
        
        database_path = await self.config.database_path()
        conn = sqlite3.connect("/home/pi/cards.db")
        cursor = conn.cursor()

           # Build the SQL query dynamically based on the search criteria
        sql_query = """
            SELECT cards.*
            FROM cards
            LEFT JOIN badges ON cards.id = badges.card_id
            LEFT JOIN trophies ON cards.id = trophies.card_id
            WHERE
        """
        sql_params = []

        # Add conditions for search criteria on cards table
        for key, value in search_criteria.items():
            sql_query += f"cards.{key} = ? AND "
            sql_params.append(value)

        # Add conditions for search criteria on badges table
        if "badge" in search_criteria:
            sql_query += "badges.badge = ? AND "
            sql_params.append(search_criteria["badge"])

        # Add conditions for search criteria on trophies table
        if "trophy" in search_criteria:
            sql_query += "trophies.type = ? AND "
            sql_params.append(search_criteria["trophy"])

        # Remove the trailing "AND" from the query
        sql_query = sql_query.rstrip(" AND ")

        # Execute the query
        #await ctx.send(sql_query)
        #await ctx.send(sql_params)

        # Execute the query
        cursor.execute(sql_query, sql_params)
        results = cursor.fetchall()
        
       # Check if any results were found
        if len(results) > 0:
            # Prepare the data to be written to the file
            file_data = [['Card ID', 'Card Name', 'Card Link']]  # Header row
            for row in results:
                card_id = row[0]
                card_name = row[1]
                card_link = f'www.nationstates.net/page=deck/card={card_id}/season=3'
                file_data.append([card_id, card_name, card_link])

            # Create a temporary CSV file
            temp_file_path = '/home/pi/card_results.csv'
            with open(temp_file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerows(file_data)

            # Send the file as an attachment
            await ctx.send(f"{ctx.author.mention} Enjoy I dug it from the salt mine just for you!",file=discord.File(temp_file_path))
        else:
            await ctx.send("No cards found matching the specified criteria.")

        # Close the connection
        conn.close()
