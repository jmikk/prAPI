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
        if random.random() <= 0.33:
            pass
        else:
            phrases = [
    "Congratulations, you've won an empty void!",
    "You've hit the jackpot of emptiness!",
    "Welcome to the land of absolute nothingness!",
    "Behold, a whole lot of nothing!",
    "You've achieved the pinnacle of nonexistence!",
    "Prepare for a grand display of nothingness!",
    "The prize is a bottomless pit of nothing!",
    "You've won a ticket to the realm of emptiness!",
    "Marvel at the absolute absence of any reward!",
    "Brace yourself for a mind-boggling lack of anything!",
    "You've unlocked the ultimate level of void!",
    "In the world of emptiness, you reign supreme!",
    "Behold the magnificent black hole of nothingness!",
    "You've won the prestigious award of absolute nada!",
    "Welcome to the hall of monumental nothingness!",
    "You've reached the zenith of null and void!",
    "Prepare to be dazzled by the void's eternal embrace!",
    "Congratulations, you've discovered the art of empty-handedness!",
    "Revel in the triumph of acquiring absolutely nothing!",
    "Witness the extraordinary vacuum of rewards!",
    "Your victory lies within the abyss of emptiness!",
    "Embrace the sublime essence of absolute absence!",
    "You've unlocked the mystery of perpetual emptiness!",
    "Prepare for a thrilling journey into the realm of naught!",
    "Bask in the glory of a void-filled triumph!",
    "Welcome to the grand illusion of non-rewards!",
    "Congratulations on becoming the master of insignificance!",
    "Behold, a treasure trove of absolute nothingness!",
    "You've entered the dimension of zero achievements!",
    "Prepare to be enchanted by the spell of emptiness!",
    "Rejoice in the splendor of total futility!",
    "You've attained a breathtaking void of accomplishments!",
    "Behold, the epitome of empty-handed glory!",
    "Congratulations, you've unlocked the secret of worthlessness!",
    "Prepare to be astounded by the majesty of nothing!",
    "Welcome to the infinite abyss of non-rewards!",
    "You've won the grand prize of absolute insignificance!",
    "Revel in the magnificence of your hollow triumph!",
    "Congratulations on reaching the zenith of fruitless endeavors!",
    "Prepare for an awe-inspiring display of nothingness!",
    "Behold the resplendent void of unattainability!",
    "You've discovered the art of acquiring zilch!",
    "Welcome to the illustrious club of eternal emptiness!",
    "Congratulations, you're the ruler of the kingdom of nada!",
    "Prepare to be amazed by the sheer absence of anything!",
    "Behold the grandeur of your futile conquest!",
    "You've earned the title of the great void master!",
    "Rejoice in the glory of absolute nullity!",
    "Congratulations on achieving the pinnacle of vacuity!",
    "Prepare for an extraordinary journey into the void!",
    "Behold the magnificent spectacle of utter nothingness!",
    "You've unlocked the secret of acquiring absolute void!",
    "Welcome to the illustrious order of perpetual nothingness!",
    "Congratulations, you've won the golden trophy of emptiness!",
    "Prepare to embark on a thrilling adventure of nullity!",
    "Revel in the splendor of a rewardless conquest!",
    "You've discovered the true essence of absolute futility!",
    "Behold the majestic empire of utter insignificance!",
    "Congratulations on becoming the sovereign of voids!",
    "Prepare to be captivated by the charm of non-existence!",
    "Welcome to the kingdom of absolute worthlessness!",
    "You've reached the summit of the mountain of nothing!",
    "Rejoice in the triumph of acquiring pure emptiness!",
    "Behold the mesmerizing allure of absolute barrenness!",
    "Congratulations, you've unlocked the door to emptiness!",
    "Prepare to be spellbound by the enchantment of naught!",
    "You've won the exquisite prize of sheer nothingness!",
    "Welcome to the realm where nullity reigns supreme!",
    "Congratulations on reaching the apex of hollowness!",
    "Prepare for an odyssey into the void of rewards!",
    "Behold the wondrous sight of absolute vacuity!",
    "You've discovered the secret path to infinite void!",
    "Revel in the glory of attaining absolute worthlessness!",
    "Congratulations, you've become the grandmaster of void!",
    "Prepare to be awed by the majesty of pure nothingness!",
    "Welcome to the domain of perpetual nullity!",
    "You've won the legendary prize of absolute voidness!",
    "Behold, the awe-inspiring void of ultimate futility!",
    "Congratulations on becoming the ruler of empty realms!",
    "Prepare for a voyage through the universe of nothing!",
    "Rejoice in the triumph of achieving absolute nothingness!",
    "You've reached the pinnacle of vacuous accomplishments!",
    "Behold the breathtaking emptiness of your success!",
    "Congratulations, you're the conqueror of the kingdom of naught!",
    "Prepare to be amazed by the spectacle of pure void!",
    "Welcome to the empire where worthlessness knows no bounds!",
    "You've attained the crown jewel of absolute non-rewards!",
    "Revel in the splendor of your triumphant emptiness!",
    "Congratulations on achieving the summit of fruitless conquests!",
    "Prepare for an incredible display of complete nothingness!",
    "Behold the majestic realm of unparalleled insignificance!",
    "You've unlocked the secret chamber of infinite emptiness!",
    "Welcome to the prestigious society of eternal nullity!",
    "Congratulations, you've won the platinum trophy of nothingness!",
    "Prepare to embark on an unforgettable journey of void!",
    "Rejoice in the grandeur of a conquest without rewards!",
    "You've discovered the essence of absolute futility!",
    "Behold the awe-inspiring domain of eternal emptiness!",
    "Congratulations on becoming the sovereign of everlasting void!",
    "Prepare to be captivated by the charm of pure non-existence!",
    "Welcome to the realm where worthlessness knows no limits!",
    "You've reached the zenith of the mountain of emptiness!",
    "Revel in the triumph of acquiring infinite nothingness!",
    "Behold the mesmerizing allure of absolute non-rewards!",
    "Congratulations, you've unlocked the gate to the void!",
    "Prepare to be spellbound by the enchantment of absolute naught!",
    "You've won the extraordinary prize of boundless emptiness!",
    "Welcome to the dimension where nullity reigns eternal!",
    "Congratulations on reaching the apex of limitless hollowness!",
    "Prepare for an odyssey into the void of perpetual non-rewards!",
    "Behold the wondrous sight of absolute vacuousness!",
    "You've discovered the secret path to an unending infinite void!",
    "Revel in the glory of attaining absolute and infinite worthlessness!",
]
            await ctx.send(random.choice(phrases))   
        db_file = data_manager.cog_data_path(self) / "cards.csv"
        #await ctx.send(db_file)
        

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
        user_csv_file = f"/home/pi/mycogs/mycogz2/decks/{user_id}/cards.csv"
    
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
