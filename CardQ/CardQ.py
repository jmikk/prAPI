import discord
from redbot.core import commands, Config
import sqlite3
import csv
import sans

class CardQ(commands.Cog):
    def __init__(self, bot):
        self.auth = sans.NSAuth()
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {"database_path": "/home/pi/cards.db"}
        self.config.register_global(**default_global)
        self.bot = bot
    
    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

 #   async def cog_command_error(self, ctx, error):
 #       await ctx.send(" ".join(error.args))

    async def api_request(self, data) -> sans.Response:
        response = await self.client.get(sans.World(**data), auth=self.auth)
        response.raise_for_status()
        return response

    @commands.command()
    @commands.is_owner()
    async def CardQ_agent(self, ctx, *,agent):
        sans.set_agent(agent, _force=True)
        await ctx.send("Agent set.")
    
    @commands.cooldown(1, 30, commands.BucketType.user)
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
                if key == "rarity":
                    key="card_category"
                value = value.strip()
                search_criteria[key] = value
        
        database_path = await self.config.database_path()
        conn = sqlite3.connect("/home/pi/cards.db")
        cursor = conn.cursor()

        # Build the SQL query dynamically based on the search criteria
        sql_query = "SELECT * FROM cards WHERE "
        sql_conditions = []
        sql_params = []
        for key, value in search_criteria.items():
            # Modify the query to use case-insensitive comparison
            if key == "flag" and value == "uploads":
                sql_conditions.append(f"flag LIKE ?")
                sql_params.append("uploads%")  # Append % to match any characters after the uploads/
            elif key == "pname":
                sql_conditions.append(f"name LIKE ?")
                sql_params.append(f"%{value}%")  
            elif key == "pmotto":
                sql_conditions.append(f"motto LIKE ?")
                sql_params.append(f"%{value}%")
            elif key == "psname":
                sql_conditions.append(f"name LIKE ?")
                sql_params.append(f"{value}%")  
            elif key == "psmotto":
                sql_conditions.append(f"motto LIKE ?")
                sql_params.append(f"{value}%")
            elif key == "pename":
                sql_conditions.append(f"name LIKE ?")
                sql_params.append(f"%{value}")  
            elif key == "pemotto":
                sql_conditions.append(f"motto LIKE ?")
                sql_params.append(f"%{value}")
            elif key == "pflag":
                sql_conditions.append(f"flag LIKE ?")
                sql_params.append(f"%{value}%")
            elif key == "psflag":
                sql_conditions.append(f"flag LIKE ?")
                sql_params.append(f"{value}%")
            elif key == "peflag":
                sql_conditions.append(f"flag LIKE ?")
                sql_params.append(f"{value}%")
            else:
                sql_conditions.append(f"LOWER({key}) = LOWER(?)")
                sql_params.append(value)
        sql_query += " AND ".join(sql_conditions)

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
