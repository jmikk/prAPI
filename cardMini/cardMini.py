import csv
import requests
from redbot.core import commands, data_manager
import random
import os
import discord
from datetime import datetime, timedelta

class cardMini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='new_season')
    async def new_season(self, ctx, series: str,legendary_limit=None,epic_limit=None,ultra_rare_limit=None,rare_limit=None,uncommon_limit=None):
        # Get the list of all server members
        server_id = str(ctx.guild.id)
        # Connect to the SQLite database for the server
        conn = sqlite3.connect(f'{server_id}.db')
        cursor = conn.cursor()
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {series} (
                userID INTEGER PRIMARY KEY,
                season TEXT,
                rarity TEXT
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
                INSERT INTO {series} (userID, season, rarity)
                VALUES (?, ?, ?)
            ''', (member.id, series, rarity))
    
        # You can now use the user_data dictionary for further processing or storage.
        conn.commit()
        conn.close()
        # Respond to the user
        await ctx.send(f"New season '{series}' started! User information stored.")
        await ctx.send(user_data[ctx.author.id])
    
