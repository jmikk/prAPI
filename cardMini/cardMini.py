import csv
import requests
from redbot.core import commands, data_manager
import random
import os
import discord

class cardMini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    async def get_avatar_url(user_id):
        user = await bot.fetch_user(user_id)
        avatar_url = user.default_avatar_url if not user.avatar else user.avatar_url
        return avatar_url


    #db_file = data_manager.cog_data_path(self) / "cards.csv"

    @commands.command()
    @commands.is_owner()
    async def list_avatars(self, ctx):
        output=[]
        db_file = data_manager.cog_data_path(self) / "cards.csv"  # Use data_manager.cog_data_path() to determine the database file path

        with open(db_file, "r") as csv_file:
            cards_data = list(csv.DictReader(csv_file))

        updated_rows = []
        for row in cards_data:
            user_id = row["ID"]
            try:
                user = await self.bot.fetch_user(int(user_id))
                avatar_hash = str(user.avatar) if user.avatar else str(user.default_avatar)
                avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
                await ctx.send(avatar_hash)
                output.append(avatar_hash)
            except Exception as e:
               await ctx.send(f"Error processing avatar for user ID {user_id}: {e}")
        #await ctx.send(output) # Create a text file and write the data to it
        with open(data_manager.cog_data_path(self) / 'list_data.txt', 'w', encoding='utf-8') as file:
            file.write(str(output))
    
        # Create a File object from the text file
        file = discord.File(data_manager.cog_data_path(self) / 'list_data.txt')
    
        # Send the file as an attachment
        await ctx.send(file=file)
                
    @commands.command()
    @commands.is_owner()
    async def open2(self, ctx):
        db_file = data_manager.cog_data_path(self) / "cards.csv"
        await ctx.send(db_file)
        

        with open(db_file, "r") as csv_file:
            cards_data = list(csv.DictReader(csv_file))

        season2_cards = [card for card in cards_data if card["Season"] == "2"]

        if season2_cards and random.random() < 0.9:
            random_card = random.choice(season2_cards)
        else:
            random_card = random.choice(cards_data)

        username = random_card["Username"]
        mention = random_card["Mention"]
        rarity = random_card["Rarity"]
        season = random_card["Season"]
        gobs_count = random_card["GobsCount"]
        mv = random_card["MV"]
        mv = float(mv)
        id = random_card["ID"]
        flag_url = random_card["Flags"]
        GobsBuyPrice = mv - (mv * .1)
        GobsSellPrice = mv + (mv * .1)
        GobsBuyPrice =  round(GobsBuyPrice, 2)
        GobsSellPrice =  round(GobsSellPrice, 2)

        if GobsBuyPrice < .01:
            GobsBuyPrice = .01
        if GobsSellPrice < .02:
            GobsSellPrice = .02
        
        if rarity == "Common":
            embed = discord.Embed(title=" ", color=discord.Color.light_grey())
        elif rarity == "Uncommon":
            embed = discord.Embed(title=" ", color=discord.Color.green())
        elif rarity == "Rare":
            embed = discord.Embed(title=" ", color=discord.Color.blue())
        elif rarity == "Ultra-Rare":
            embed = discord.Embed(title=" ", color=discord.Color.purple())
        elif rarity == "Epic":
            embed = discord.Embed(title=" ", color=discord.Color.orange())
        elif rarity == "Legendary":
            embed = discord.Embed(title=" ", color=discord.Color.gold())
        elif rarity == "Mythic":
            embed = discord.Embed(title=" ", color=discord.Color.red())
        else:
            embed = discord.Embed(title=" ", color=discord.Color.teal())

                
        user_id = str(ctx.author.id)
        user_csv_file = f"{user_id}_cards.csv"
    
        with open(user_csv_file, "a", newline="") as csv_file:
            fieldnames = ["Name", "Season"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    
            if csv_file.tell() == 0:
                writer.writeheader()
    
            writer.writerow({
                "Name": username,
                "Season": season,
            })
                
            
        embed.set_thumbnail(url=flag_url)
        embed.add_field(name="Username", value=username, inline=False)
        embed.add_field(name="Mention", value=mention, inline=False)
        embed.add_field(name="Rarity", value=rarity, inline=True)
        embed.add_field(name="Season", value=season, inline=True)
        embed.add_field(name="GobsCount", value=gobs_count, inline=True)
        embed.add_field(name="MV", value=mv, inline=True)
        embed.add_field(name="Gob will buy for",value=GobsBuyPrice,inline=True)
        embed.add_field(name="Gob will sell for",value=GobsSellPrice,inline=True)
        

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def work2(self, ctx):
       pass 
    
    @commands.command()
    @commands.is_owner()
    async def delete_database(self, ctx):
        db_file = data_manager.cog_data_path(self) / "cards.csv"

        if os.path.exists(db_file):
            os.remove(db_file)
            await ctx.send("Database file has been deleted.")
        else:
            await ctx.send("No database file found.")

    
    @commands.command()
    @commands.is_owner()
    async def import_cards(self, ctx):
        url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRSS2pmupriEkgsieDU1LnDc0En1TjULcY7cjS_9qCgOdgSwKeIp7NFvhdfgfGp0swVzn4bNsPfcRqs/pub?gid=0&single=true&output=csv"

        response = requests.get(url)
        if response.status_code == 200:
            csv_content = response.content.decode("utf-8").splitlines()

            cards_data = list(csv.DictReader(csv_content))
            db_file = data_manager.cog_data_path(self) / "cards.csv"

            if db_file.exists():
                with open(db_file, "a", newline="") as csv_file:
                    fieldnames = cards_data[0].keys()
                    data_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                    data_writer.writerows(cards_data)
            else:
                with open(db_file, "w", newline="") as csv_file:
                    fieldnames = cards_data[0].keys()
                    data_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                    data_writer.writeheader()
                    data_writer.writerows(cards_data)

            await ctx.send("Database created/updated successfully.")
        else:
            await ctx.send("Failed to fetch CSV data from the URL.")
    

def setup(bot):
    cog = CardCog(bot)
    bot.add_cog(cog)
