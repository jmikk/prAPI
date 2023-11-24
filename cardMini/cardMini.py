import csv
import requests
from redbot.core import commands, data_manager
import random
import os
import discord
from datetime import datetime, timedelta
import sqlite3
import math
import asyncio

class cardMini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sell_mod=1.1
        self.buy_mod=.9
   
    @commands.command(name='set_sell_mod')
    async def set_sell_mod(self,mod:float):
        self.sell_mod=mod
        await ctx.send(f"sell mod now set to {self.sell_mod}")

    @commands.command(name='set_buy_mod')
    async def set_buy_mod(self,mod:float):
        self.buy_mod=mod
        await ctx.send(f"buy mod now set to {self.buy_mod}")

        
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


    def get_bank(self,serverID,id):
        db_path = os.path.join(data_manager.cog_data_path(self), f'{serverID}.db')
        try: 
            # Connect to the SQLite database for the server
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS bank (
                    userID INTEGER PRIMARY KEY,
                    cash REAL DEFAULT 0
                )
                        ''')
            cursor.execute('SELECT cash FROM bank WHERE userID = ?', (id,))
            result = cursor.fetchone()


            if result is None:
            # If ctx.author.id is not in the 'bank' table, insert with default cash value
                cursor.execute('INSERT INTO bank (userID, cash) VALUES (?, 0)', (id,))
                conn.commit()
                return 0
            else:
                # If ctx.author.id is in the 'bank' table, return the cash value
                return result[0]


            #cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='bank_{id}'")
            #rows = cursor.fetchone()
                
            return rows

        
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                return "No table found"
            else:
                return f"SQLite error: {e}"
        finally:
            # Close the connection
            conn.close()    


        
    @commands.command(name='buy_card')
    async def buy_card(self,ctx,name):
        server_id = str(ctx.guild.id)
        bank = self.get_bank(server_id,str(ctx.author.id))
    
    @commands.command(name='set_bank')
    async def set_bank(self,ctx,bank, acct: commands.MemberConverter):
        server_id = str(ctx.guild.id)
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')

        try: 
            # Connect to the SQLite database for the server
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
           
            # Update the bank value for the given user
            cursor.execute('UPDATE bank SET cash = ? WHERE userID = ?', (bank, acct.id))
            conn.commit()

        


    
    
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
            # Paginate the results (display the first 10)
            chunk_size = 10
            paginated_rows = [rows[i:i + chunk_size] for i in range(0, len(rows), chunk_size)]

            # Initialize page counter and embed
            current_page = 0
            total_pages = len(paginated_rows)            


                        # Function to display the current page
            async def display_page():
                embed = discord.Embed(title=f"Deck Information - Page {current_page + 1}/{total_pages}")

                for row in paginated_rows[current_page]:
                    # Customize how you want to display each row in the embed
                    user = self.bot.get_user(row[0])
                    name = user.name

                    # Use a parameterized query to retrieve all elements from the table
                    cursor.execute(f'SELECT * FROM {row[1]} WHERE userID = ?',(row[0],))                    
                    # Fetch all the rows from the result set
                    rowz = cursor.fetchall()
                    sell_price = round(rowz[0][3]*self.sell_mod,2)
                    buy_price = round(rowz[0][3]*self.buy_mod,2)
                    
                    embed.add_field(name=f"Card name: {name} {row[1]}", value=f"You own: {row[2]} ID: {row[0]} Rarity: {rowz[0][2]}\nMV: {rowz[0][3]} Buy price: {buy_price} Sell price: {sell_price}", inline=False)
                return embed

            # Send the initial page
            message = await ctx.send(embed=await display_page())

            # Add reactions for navigation
            await message.add_reaction('◀️')
            await message.add_reaction('▶️')

            # Function to update the display based on reaction input
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ['◀️', '▶️']

            while True:
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)

                    if str(reaction.emoji) == '▶️' and current_page < total_pages - 1:
                        current_page += 1
                    elif str(reaction.emoji) == '◀️' and current_page > 0:
                        current_page -= 1

                    # Update the message with the new page
                    await message.edit(embed=await display_page())

                    # Remove the user's reaction
                    await message.remove_reaction(reaction, user)
                except asyncio.TimeoutError:
                    # Stop listening for reactions after 30 seconds
                    break
                except asyncio.CancelledError:
                    # Handle cancellation (optional)
                    break
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
                user = self.bot.get_user(card[0])

                card_rarity = card[2]
                embed = discord.Embed(title=user.name)
                if card_rarity == "Mythic":
                    embed.color = 0xC30F0D
                elif card_rarity == "Legendary":
                    embed.color = 0xFFEA7A
                elif card_rarity == "Epic":
                    embed.color = 0xE3B54F
                elif card_rarity == "Ultra-Rare":
                    embed.color = 0xCA5BEF
                elif card_rarity == "Rare":
                    embed.color = 0x008EC1
                elif card_rarity == "Uncommon":
                    embed.color = 0x00AA4C
                elif card_rarity == "Common":
                    embed.color = 0xABABAB
                else:
                    # Handle the case when card_rarity is not one of the specified values
                    embed.color = 0xFFFFFF  # Set a default color or handle it accordingly
                
                # Rest of your code using the 'embed' variable...

                        
               

                # Add fields to the embed
                embed.add_field(name="Name", value=user.mention, inline=True)
                embed.add_field(name="Season", value=card[1], inline=True)
                embed.add_field(name="Rarity", value=card[2], inline=True)
                embed.add_field(name="MV", value=card[3], inline=True)
                embed.add_field(name="Gob owns", value=card[4], inline=True)
                embed.add_field(name="You own", value=owner_count[0], inline=True)
                embed.add_field(name="Buy Price", value=round(card[3]*self.buy_mod,2), inline=True)
                embed.add_field(name="Sell Price", value=round(card[3]*self.sell_mod,2), inline=True)
            
                # Set the thumbnail to the user's avatar if available, otherwise use the default icon
                avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
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
        cursor.execute('DELETE FROM bank WHERE userID = ?', (deck.id,))
        conn.commit()    
        # Close the connection
        conn.close()
    
        # Respond to the user
        await ctx.send(f"{deck.mention}'s deck deleted! {deck.id}")

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
                name TEXT,
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
                INSERT INTO {series} (userID,name, season, rarity, MV, Stock)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (member.id,member.name, series, rarity, MV, 10))
    
        # You can now use the user_data dictionary for further processing or storage.
        conn.commit()
        conn.close()
        # Respond to the user
        await ctx.send(f"New season '{series}' started! User information stored.")
        await ctx.send(user_data[ctx.author.id])
    
