import discord
from redbot.core import commands, Config
import sqlite3

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

        # Display the results
        if len(results) > 0:
            for row in results:
                # Format and send the card information as a Discord message
                card_info = "\n".join(f"{key.capitalize()}: {value}" for key, value in zip(cursor.description, row))
                await ctx.send(f"```{card_info}```")
        else:
            await ctx.send("No cards found matching the specified criteria.")

        # Close the connection
        conn.close()
