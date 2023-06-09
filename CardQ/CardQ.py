import discord
from redbot.core import commands, Config
import sqlite3
import csv

class CardQ(commands.Cog):
    def __init__(self, bot):
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {"database_path": "cards.db"}
        self.config.register_global(**default_global)
        self.bot = bot

    @commands.command()
    async def card_search(self, ctx, *args):
        await ctx.send("I'll think about it")
        # Parse the arguments
        search_criteria = {}
        for arg in args:
            key, value = arg.split(":")
            search_criteria[key] = value

        # Connect to the database
        database_path = await self.config.database_path()
        conn = sqlite3.connect("/home/pi/cards.db")
        cursor = conn.cursor()

        # Build the SQL query dynamically based on the search criteria
        sql_query = "SELECT * FROM cards WHERE "
        sql_params = []
        for key, value in search_criteria.items():
            sql_query += f"{key} = ? AND "
            sql_params.append(value)
        sql_query = sql_query.rstrip(" AND ")

        # Execute the query
        cursor.execute(sql_query, sql_params)
        results = cursor.fetchall()
        # Check if any results were found
        if len(results) > 0:
            # Prepare the data to be written to the file
            file_data = [['Card ID', 'Card Name']]  # Header row
            file_data.extend(results)  # Data rows

            # Create a temporary CSV file
            temp_file_path = 'card_results.csv'
            with open(temp_file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerows(file_data)

            # Send the file as an attachment
            await ctx.send(file=discord.File(temp_file_path))
        else:
            await ctx.send("No cards found matching the specified criteria.")


        # Close the connection
        conn.close()
