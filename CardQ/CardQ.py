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
                #if key == "rarity":
                    #key="card_category"
                value = value.strip()
                search_criteria[key] = value
        
        database_path = await self.config.database_path()
        conn = sqlite3.connect("/home/pi/cards.db")
        cursor = conn.cursor()

        # Build the SQL query dynamically based on the search criteria
        sql_query = "SELECT * FROM cards WHERE "
        sql_params = []
        for key, value in search_criteria.items():
            # Modify the query to use case-insensitive comparison
            sql_query += "LOWER({}) = LOWER(?) AND ".format(key)
            sql_params.append(value)
        sql_query = sql_query.rstrip(" AND ")

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
                card_link = f'www.nationstates.net/card={card_id}/season=3'
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
