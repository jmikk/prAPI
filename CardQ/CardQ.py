import discord
from redbot.core import commands, Config
import sqlite3
import csv
import xml.etree.ElementTree as ET
import sans
import requests

class CardQ(commands.Cog):
    def __init__(self, bot):
        self.auth = sans.NSAuth()
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {"database_path": "/home/pi/cards.db"}
        self.config.register_global(**default_global)
        self.bot = bot
        self.client = sans.AsyncClient()

    
    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

 #   async def cog_command_error(self, ctx, error):
 #       await ctx.send(" ".join(error.args))

    async def api_request(self, data) -> sans.Response:
        response = await self.client.get(sans.World(**data), auth=self.auth)
        response.raise_for_status()
        return response
    
    async def parse_deck_xml(self, deck_xml):
        root = ET.fromstring(deck_xml)
        card_ids = []
        for card_element in root.findall("CARD"):
            card_id = card_element.find("CARDID").text
            card_ids.append(card_id)
        return card_ids

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
        deck_name = None

        # Parse each search term and extract the key-value pair
        for term in search_terms:
            if ":" in term:
                key, value = term.split(":", 1)
                key = key.lower().strip()
                if key == "rarity":
                    key = "card_category"
                elif key == "-deck":
                    deck_name = value.strip()
                    continue
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
        cursor.execute(sql_query, sql_params)
        results = cursor.fetchall()

        # Check if any results were found
        if len(results) > 0:
            # Remove cards present in the deck from the query results
            if deck_name is not None:
                deck_query = {"q":"cards+deck","nationname":deck_name}
                deck_response = await self.api_request(deck_query)
                deck_xml = deck_response.text
                deck_card_ids = self.parse_deck_xml(deck_xml)
                results = [card for card in results if card[0] not in deck_card_ids]

            # Send the formatted results as a message
            await ctx.send(self.format_results(results))
        else:
            await ctx.send("No cards found matching the search criteria.")

        cursor.close()
        conn.close()

