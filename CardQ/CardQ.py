import discord
from redbot.core import commands, Config
import sqlite3

class CardQ(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        default_global = {"database_path": "cards.db"}
        self.config.register_global(**default_global)

    @commands.command()
    async def card_search(self, ctx, **kwargs):
        # Retrieve the search criteria
        search_criteria = kwargs

        # Connect to the database
        database_path = await self.config.database_path()
        conn = sqlite3.connect(database_path)
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

def setup(bot):
    bot.add_cog(CardSearch(bot))
