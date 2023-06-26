import csv
import requests
from redbot.core import commands, data_manager
import random
from imgurpython import ImgurClient
import os
import discord

class cardMini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.imgur_client = ImgurClient("e37e735710f856c", "ee2ffe6712dfdada38405fa8bc5ca7b1f3544660")


    async def get_avatar_url(user_id):
        user = await bot.fetch_user(user_id)
        avatar_url = user.default_avatar_url if not user.avatar else user.avatar_url
        return avatar_url


    #db_file = data_manager.cog_data_path(self) / "cards.csv"

      @commands.command()
    async def upload_avatars(self, ctx):
        db_file = data_manager.cog_data_path(self) / "cards.csv"  # Use data_manager.cog_data_path() to determine the database file path

        with open(db_file, "r") as csv_file:
            cards_data = list(csv.DictReader(csv_file))

        updated_rows = []
        for row in cards_data:
            user_id = row["ID"]
            try:
                user = await self.bot.fetch_user(int(user_id))
                avatar_url = user.avatar_url_as(format="png")
                avatar_filename = f"avatar_{user_id}.png"
                avatar_path = data_manager.cog_data_path(self) / avatar_filename

                # Download avatar image
                response = requests.get(avatar_url)
                with open(avatar_path, "wb") as avatar_file:
                    avatar_file.write(response.content)

                # Upload avatar image to Imgur
                imgur_response = self.imgur_client.upload_from_path(avatar_path)
                row["Flags"] = imgur_response["link"]
                updated_rows.append(row)

                # Remove the local avatar image file
                os.remove(avatar_path)
            except Exception as e:
                print(f"Error processing avatar for user ID {user_id}: {e}")

        if updated_rows:
            with open(db_file, "w", newline="") as csv_file:
                fieldnames = updated_rows[0].keys()
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(updated_rows)

            await ctx.send("Avatar links have been uploaded and added to the 'Flags' column.")
        else:
            await ctx.send("No avatar links found.")

    
    @commands.command()
    async def open2(self, ctx):
        db_file = data_manager.cog_data_path(self) / "cards.csv"

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
        id = random_card["ID"]


        embed = discord.Embed(title="Random Card", color=discord.Color.blue())
        embed.add_field(name="Username", value=username, inline=False)
        embed.add_field(name="Mention", value=mention, inline=False)
        embed.add_field(name="Rarity", value=rarity, inline=True)
        embed.add_field(name="Season", value=season, inline=True)
        embed.add_field(name="GobsCount", value=gobs_count, inline=True)
        embed.add_field(name="MV", value=mv, inline=True)

        await ctx.send(embed=embed)
        
    @commands.command()
    async def delete_database(self, ctx):
        db_file = data_manager.cog_data_path(self) / "cards.csv"

        if os.path.exists(db_file):
            os.remove(db_file)
            await ctx.send("Database file has been deleted.")
        else:
            await ctx.send("No database file found.")

    
    @commands.command()
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
