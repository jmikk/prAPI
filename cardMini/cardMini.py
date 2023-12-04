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
   
    @commands.command(name='mine_salt')
    async def mine_salt(self,ctx):
        server_id = str(ctx.guild.id)
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        event_type = random.randint(1, 3)
    
        if event_type == 1:
            # Give the user a random amount of money between 0.01 and 0.10
            amount = round(random.uniform(0.01, 0.10), 2)
            # Get the user's current bank balance
            user_bank = self.get_bank(server_id, str(ctx.author.id))
    
            # Update the bank balance with the reward
            new_bank_total = user_bank + amount
            cursor.execute('UPDATE bank SET cash = ? WHERE userID = ?', (new_bank_total, ctx.author.id))
            conn.commit()           
            await ctx.send(f"You received {amount} in your bank!")    
        elif event_type == 3 or event_type == 2:
            # Read a random line from the 'bad_stuff.txt' file
            current_directory = os.path.dirname(os.path.abspath(__file__))

            # Specify the file name
            file_name = 'bad_stuff.txt'
            
            # Combine the directory and file name to get the full path
            file = os.path.join(current_directory, file_name)

            with open(file, 'r', encoding='utf-8') as file:
                line_number = random.randint(1, sum(1 for _ in file))
                bad_stuff = linecache.getline('bad_stuff.txt', line_number).strip()

            # Send the random line to the user
            await ctx.send(f"Uh oh! {bad_stuff}")
    
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
        
    @commands.command(name='view_card')
    async def view_card(self,ctx,name,season):
        season = "Season_" + season
        server_id = str(ctx.guild.id)

        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT userID FROM {season} WHERE name = ?", (name,))
            userID = cursor.fetchone()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                await ctx.send(f"No season found with name {season}")
                return
            else:
                await ctx.send(f"SQLite error: {e}")
                return

        if not userID:
            await ctx.send(f"No card found with the name '{name}' in season '{season}'")
            return
        

        card = await self.display_card(userID[0],season,server_id)
        owner_count = self.get_owned_count(userID[0],season,server_id,ctx.author.id)

        #(ID, 'Season_1', 'Epic', 0.5, 10)
        user = self.bot.get_user(card[0])

        card_rarity = card[3]
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
                # Add fields to the embed

        embed.add_field(name="Name", value=user.mention, inline=True)
        embed.add_field(name="Season", value=card[2], inline=True)
        embed.add_field(name="Rarity", value=card[3], inline=True)
        embed.add_field(name="MV", value=card[4], inline=True)
        embed.add_field(name="Gob owns", value=card[5], inline=True)
        embed.add_field(name="You own", value=owner_count[0], inline=True)
        embed.add_field(name="Gob will buy for", value=round(float(card[4])*self.buy_mod,2), inline=True)
        embed.add_field(name="Gob will sell for", value=round(float(card[4])*self.sell_mod+.01,2), inline=True)
            
        # Set the thumbnail to the user's avatar if available, otherwise use the default icon
        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
        embed.set_thumbnail(url=avatar_url)

        await ctx.send(embed=embed)
        
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
            result= f"SQLite error: in display card {e}"
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

    @commands.command(name='sell_card')
    async def sell_card(self, ctx, name, series):
        server_id = str(ctx.guild.id)
        series = "Season_" + series
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
    
        try:
            # Execute a SELECT query to find the row with the specified name in the given series
            cursor.execute(f'''
                SELECT MV,stock FROM {series} WHERE name = ?
            ''', (name,))
    
            # Fetch the result
            MV = cursor.fetchone()
    
            cursor.execute(f"SELECT userID FROM {series} WHERE name = ?", (name,))
            userID = cursor.fetchone()
    
            if MV:
                # Check if the user has the card in their deck
                table_name = "deck_" + str(ctx.author.id)
                query = f"SELECT * FROM {table_name} WHERE userID = ? AND season = ?"
                cursor.execute(query, (userID[0], series))
                result = cursor.fetchone()
    
                if result and result[2] > 0:
                    # Add the card's MV to the user's bank with the buy_mod multiplier
                    sell_price = max(float(MV[0]) * float(self.buy_mod), 0.01)
                    await ctx.send(sell_price)
                    await ctx.send(float(MV[0]) * float(self.buy_mod))
                    new_bank_total = self.get_bank(server_id, str(ctx.author.id)) + sell_price
                    cursor.execute('UPDATE bank SET cash = ? WHERE userID = ?', (new_bank_total, ctx.author.id))
                    conn.commit()
    
                    # Update the deck by decreasing the count
                    new_count = result[2] - 1
                    update_query = f"UPDATE {table_name} SET count = ? WHERE userID = ? AND season = ?"
                    cursor.execute(update_query, (new_count, userID[0], series))
                    conn.commit()


                    # Update the MV in the database
                    # Use a try-except block for error handling
                    try:
                        update_query = f"UPDATE {series} SET MV = ? WHERE userID = ?"
                        
                        cursor.execute(update_query, (max(float(MV[0]) * float(self.buy_mod), 0.01), userID[0]))
                        conn.commit()

                        # Update the stock count in the database
                        update_stock_query = f"UPDATE {series} SET stock = ? WHERE name = ?"
                        cursor.execute(update_stock_query, (MV[1] + 1, name))
                        conn.commit()
                    except sqlite3.Error as e:
                        await ctx.send(f"SQLite error: {e}")
    
                    await ctx.send(f"You have successfully sold the card '{name}' from '{series}' for {sell_price:.2f}.")
                else:
                    await ctx.send(f"You don't have the card '{name}' in your deck.")
            else:
                await ctx.send(f"No data found for the card '{name}' in the series '{series}'.")
        except sqlite3.OperationalError as e:
            await ctx.send(f"SQLite error: {e}")
        finally:
            # Close the connection
            conn.close()



    @commands.command(name='buy_card')
    async def buy_card(self, ctx, name, series):
        server_id = str(ctx.guild.id)
        series = "Season_" + series
        db_path = os.path.join(data_manager.cog_data_path(self), f'{server_id}.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
    
        try:
            # Execute a SELECT query to find the row with the specified name in the given series
            cursor.execute(f'''
                SELECT MV,stock FROM {series} WHERE name = ?
            ''', (name,))
             
            # Fetch the result
            MV = cursor.fetchone()
            
            cursor.execute(f"SELECT userID FROM {series} WHERE name = ?", (name,))
            userID = cursor.fetchone()

            if not MV:
                await ctx.send(f"No card found with name '{name}' in season '{series}'")
                return
                
            if MV[1] <= 0:
                await ctx.send("I don't have a copy of that card but sometimes when you try and open a pack I get a card!")
                return
               
    
            if MV:
                # Check if the user has enough money in the bank to buy the card
                user_bank = self.get_bank(server_id, str(ctx.author.id))
                price = round(float(MV[0])*self.sell_mod+0.01,2)

                if user_bank >= price:
                    # Subtract the card's MV from the user's bank
                    new_bank_total = user_bank - price
                    cursor.execute('UPDATE bank SET cash = ? WHERE userID = ?', (new_bank_total, ctx.author.id))
                    conn.commit()
    
                    # Add the purchased card to the user's deck
                    table_name = "deck_" + str(ctx.author.id)
                    cursor.execute(f'''
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            userID INTEGER PRIMARY KEY,
                            season TEXT,
                            count INTEGER
                        )
                    ''')
                    # Execute the SQL query to check if the user and season combination already exists
                    query = f"SELECT * FROM {table_name} WHERE userID = ? AND season = ?"
                    cursor.execute(query, (userID[0], series))
                    result2 = cursor.fetchone()

                    if result2:
                        # If the user and season combination exists, update the count
                        new_count = result2[2] + 1
                        update_query = f"UPDATE {table_name} SET count = ? WHERE userID = ? AND season = ?"
                        cursor.execute(update_query, (new_count, userID[0], series))
                    else:
                        # If the user and season combination doesn't exist, insert a new record
                        insert_query = f"INSERT INTO {table_name} (userID, season, count) VALUES (?, ?, ?)"
                        cursor.execute(insert_query, (userID[0], series, 1))   
                    # Commit the changes
                    conn.commit()

                    

                    # Update the MV in the database
                    update_query = f"UPDATE {series} SET MV = ? WHERE userID = ?"
                    
                    # Use a try-except block for error handling
                    try:
                        cursor.execute(update_query, (price, userID[0]))
                        conn.commit()


                        # Update the stock count in the database
                        update_stock_query = f"UPDATE {series} SET stock = ? WHERE name = ?"
                        cursor.execute(update_stock_query, (MV[1] - 1, name))
                        conn.commit()
                    except sqlite3.Error as e:
                        await ctx.send(f"SQLite error: {e}")

                    finally:
                        conn.close()




    
                    await ctx.send(f"You have successfully bought the card '{name}' from '{series}' for '{price}'. I have {MV[1]-1} copies left!")
                else:
                    await ctx.send(f"You don't have enough money in your bank to buy the card '{name}'.")
            else:
                await ctx.send(f"No data found for the card '{name}' in the series '{series}'.")
        except sqlite3.OperationalError as e:
            await ctx.send(f"SQLite error: {e}")
        finally:
            # Close the connection
            conn.close()
            

    @commands.command(name='chk_bank')
    async def chk_bank(self,ctx):
        server_id = str(ctx.guild.id)
        await ctx.send(f"You have: {round(self.get_bank(server_id,ctx.author.id),2)} bank.")

        
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
            await ctx.send(f"new bank total is {bank}")
            conn.commit()
        except sqlite3.OperationalError as e:
            await ctx.send(f"SQLite error: {e}")
        finally:
        # Close the connection
            conn.close()
    
    
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

                    sell_price = round(float(rowz[0][4])*self.sell_mod+0.01,2)
                    buy_price = round(float(rowz[0][4])*self.buy_mod,2)
                    
                    embed.add_field(name=f"Card name: {name} {row[1]}", value=f"You own: {row[2]} ID: {row[0]} Rarity: {rowz[0][3]}\nMV: {round(rowz[0][4],2)} Buy price: {buy_price} Sell price: {sell_price}", inline=False)
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
                else:
                    # If the user and season combination doesn't exist, insert a new record
                    insert_query = f"INSERT INTO {deck_table_name} (userID, season, count) VALUES (?, ?, ?)"
                    cursor.execute(insert_query, (result[0], series, 1))   
                # Commit the changes
                conn.commit()
                card = await self.display_card(result[0],result[2],server_id)
                owner_count = self.get_owned_count(result[0],result[2],server_id,ctx.author.id)

                #(ID, 'Season_1', 'Epic', 0.5, 10)
                user = self.bot.get_user(card[0])

                card_rarity = card[3]
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
                embed.add_field(name="Season", value=card[2], inline=True)
                embed.add_field(name="Rarity", value=card[3], inline=True)
                embed.add_field(name="MV", value=card[4], inline=True)
                embed.add_field(name="Gob owns", value=card[5], inline=True)
                embed.add_field(name="You own", value=owner_count[0], inline=True)
                embed.add_field(name="Gob will buy for", value=round(float(card[4])*self.buy_mod,2), inline=True)
                embed.add_field(name="Gob will sell for", value=round(float(card[4])*self.sell_mod+.01,2), inline=True)
            
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
    
