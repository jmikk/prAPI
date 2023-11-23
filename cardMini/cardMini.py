import csv
import requests
from redbot.core import commands, data_manager
import random
import os
import discord
from datetime import datetime, timedelta
import sqlite3

class cardMini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_owned_count(self, id, season, server_id,user_id):
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        output=""
        try:
            table_name = "deck_"+str(user_id)

            query = f"SELECT count FROM {table_name} WHERE userID = ? AND season = ?"
            cursor.execute(query, (id, season))
            
            # Fetch the result of the query
            result = cursor.fetchone()

            return result
        except sqlite3.OperationalError as e:
            output=f"SQLite error: {e}"
        finally:
            # Close the cursor and connection
            cursor.close()
            conn.close()
        return output

        
    async def display_card(self,id,season,server_id):
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
                
        result = ""
        try:
            # Execute the query to retrieve table names
            cursor.execute(f'''SELECT * FROM {season} WHERE userID = ? AND season = ?''', (id, season))
                    
            # Fetch all the table names from the result set
            result = cursor.fetchone()
        except sqlite3.OperationalError as e:
            result= f"SQLite error: {e}"
        finally:
            # Close the cursor and connection
            cursor.close()
            conn.close()
                    
            # Print the list of table names
        return result

    @commands.command(name='all_deck')
    async def all_deck(self,ctx):
        server_id = str(ctx.guild.id)
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        try: 
            # Connect to the SQLite database for the server
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            #set the deck table 
            table_name = "deck_"+str(ctx.author.id)

            # Connect to the database
            connection = sqlite3.connect(db_path)
            cursor = connection.cursor()

            # Use a parameterized query to retrieve all elements from the table
            query = f'SELECT * FROM {table_name}'
            cursor.execute(query)
            
            # Fetch all the rows from the result set
            rows = cursor.fetchall()

            await ctx.send(rows)
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                await ctx.send(f"No cards in your deck go open some!")
            else:
                await ctx.send(f"SQLite error: {e}")
        finally:
            # Close the connection
            conn.close()    


    
    @commands.command(name='random_user')
    async def random_user(self, ctx, series: str):
        """Select a random user from the specified series and add their ID to the user's deck."""
        series = "Season_"+series
        server_id = str(ctx.guild.id)
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        user_id = ctx.author.id
         # Check if the deck table exists, and create it if not
        deck_table_name = f'deck_{user_id}'
    
        try:
            # Connect to the SQLite database for the server
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
    
            # Retrieve a random user from the specified series
            cursor.execute(f'''
                SELECT * FROM {series}
                ORDER BY RANDOM()
                LIMIT 1
            ''')
    
            # Fetch the result
            result = cursor.fetchone()
    
            if result:
                cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {deck_table_name} (
                    userID INTEGER PRIMARY KEY,
                    season TEXT,
                    count INTEGER
                )
                        ''')

                # Execute the SQL query to check if the user and season combination already exists
                query = f"SELECT * FROM {deck_table_name} WHERE userID = ? AND season = ?"
                cursor.execute(query, (result[0], series))
                result2 = cursor.fetchone()
                
                if result2:
                    # If the user and season combination exists, update the count
                    new_count = result2[2] + 1
                    update_query = f"UPDATE {deck_table_name} SET count = ? WHERE userID = ? AND season = ?"
                    cursor.execute(update_query, (new_count, result[0], series))
                    await ctx.send("old card")
                else:
                    # If the user and season combination doesn't exist, insert a new record
                    insert_query = f"INSERT INTO {deck_table_name} (userID, season, count) VALUES (?, ?, ?)"
                    cursor.execute(insert_query, (result[0], series, 1))                    
                # Commit the changes
                conn.commit()
                card = await self.display_card(result[0],result[1],server_id)
                owner_count = self.get_owned_count(result[0],result[1],server_id,ctx.author.id)

                #(ID, 'Season_1', 'Epic', 0.5, 10)
                
                embed = discord.Embed(title="Card Information", color=0x00ff00)
               
                user = ctx.get_user(card[0])

                # Add fields to the embed
                embed.add_field(name="User", value=user.mention, inline=True)
                embed.add_field(name="Season", value=card[1], inline=True)
                embed.add_field(name="Rarity", value=card[2], inline=True)
                embed.add_field(name="MV", value=card[3], inline=True)
                embed.add_field(name="Stock", value=card[4], inline=True)
                embed.add_field(name="Buy Price", value=card[3]*.9, inline=True)
                embed.add_field(name="Sell Price", value=card[3]*1.1, inline=True)
            
                # Set the thumbnail to the user's avatar if available, otherwise use the default icon
                avatar_url = user.avatar_url if user.avatar else user.default_avatar_url
                embed.set_thumbnail(url=avatar_url)

                await ctx.send(embed=embed)
            
    
            else:
                await ctx.send(f"No data found for '{series}'")
    
        except sqlite3.OperationalError as e:
            await ctx.send(f"Error: {e}. The specified series table '{series}' does not exist.")

    
        finally:
            # Close the connection
            conn.close()        

    
    @commands.command(name='delete_deck')
    async def delete_deck(self, ctx, deck: commands.MemberConverter):
        server_id = str(ctx.guild.id)

        # Connect to the SQLite database for the server
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')

        conn = sqlite3.connect(db_path)
    
        # Delete the table for the specified series
        cursor = conn.cursor()
        cursor.execute(f'''
                DROP TABLE IF EXISTS deck_{deck.id}
            ''')
        conn.commit()    
        # Close the connection
        conn.close()
    
        # Respond to the user
        await ctx.send(f"{deck.mention}'s deck deleted!")

    @commands.command(name='list_series')
    async def list_series(self, ctx):
        server_id = str(ctx.guild.id)
    
        # Connect to the SQLite database for the server
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')

        conn = sqlite3.connect(db_path)
    
        # Delete the table for the specified series
        cursor = conn.cursor()

        # Execute the query to retrieve table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Season_%'")
        
        # Fetch all the table names from the result set
        table_names = cursor.fetchall()
        
        # Close the cursor and connection
        cursor.close()
        conn.close()
        
        # Print the list of table names
        await ctx.send(table_names)
    
    @commands.command(name='delete_series')
    async def delete_series(self, ctx, series: str):
        # Get the server ID
        series ="Season_"+series
        server_id = str(ctx.guild.id)
    
        # Connect to the SQLite database for the server
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')

        conn = sqlite3.connect(db_path)
    
        # Delete the table for the specified series
        cursor = conn.cursor()
        cursor.execute(f'''
                DROP TABLE IF EXISTS {series}
            ''')
        conn.commit()    
        # Close the connection
        conn.close()
    
        # Respond to the user
        await ctx.send(f"Series '{series}' deleted!")

    
    @commands.command(name='new_season')
    async def new_season(self, ctx, series: str,legendary_limit=None,epic_limit=None,ultra_rare_limit=None,rare_limit=None,uncommon_limit=None):
        series = "Season_"+series
        # Get the list of all server members
        server_id = str(ctx.guild.id)
        # Connect to the SQLite database for the server
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {series} (
                userID INTEGER PRIMARY KEY,
                season TEXT,
                rarity TEXT,
                MV REAL,
                Stock INTEGER
            )
        ''')
        conn.commit()
    
        members = ctx.guild.members
        
        # Sort members based on their join date
        sorted_members = sorted(members, key=lambda x: x.joined_at)
        cursor = conn.cursor()
        # Calculate rarities based on the specified percentages
        mythic_limit = 1
        if not legendary_limit:
            legendary_limit = int(len(sorted_members) * 0.05)
        if not epic_limit:
            epic_limit = int(len(sorted_members) * 0.15)
        if not ultra_rare_limit:
            ultra_rare_limit = int(len(sorted_members) * 0.30)
        if not rare_limit:
            rare_limit = int(len(sorted_members) * 0.45)
        if not uncommon_limit:
            uncommon_limit = int(len(sorted_members) * 0.70)

    
        # Store user information in a dictionary
        user_data = {}
        for i, member in enumerate(sorted_members):
            if i < mythic_limit:
                rarity = "Mythic"
                MV = 10
            elif i < legendary_limit:
                rarity = "Legendary"
                MV = 1
            elif i < epic_limit:
                rarity = "Epic"
                MV = .5
            elif i < ultra_rare_limit:
                rarity = "Ultra-Rare"
                MV = .25
            elif i < rare_limit:
                rarity = "Rare"
                MV = .10
            elif i < uncommon_limit:
                rarity = "Uncommon"
                MV = .05
            else:
                rarity = "Common"
                MV = .01
    
            user_data[member.id] = {'userID': member.id, 'season': series, 'rarity': rarity,'MV': MV,'Stock':10}
            # Insert user information into the table
            cursor.execute(f'''
                INSERT INTO {series} (userID, season, rarity, MV, Stock)
                VALUES (?, ?, ?, ?, ?)
            ''', (member.id, series, rarity, MV, 10))
    
        # You can now use the user_data dictionary for further processing or storage.
        conn.commit()
        conn.close()
        # Respond to the user
        await ctx.send(f"New season '{series}' started! User information stored.")
        await ctx.send(user_data[ctx.author.id])
    
