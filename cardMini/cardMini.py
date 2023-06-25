import csv
from redbot.core import commands

class cardMini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def update_rarity(self, ctx):
        if not await self.database_exists():
            await self.create_database()

        await self.add_data_to_database()

        await ctx.send("Data updated successfully.")

    async def database_exists(self):
        # Check if the database exists (you can implement this based on your database setup)
        # Return True if it exists, False otherwise
        pass

    async def create_database(self):
        # Create the database (you can implement this based on your database setup)
        pass

    async def add_data_to_database(self):
        with open("data.csv", "a", newline="") as file:
            writer = csv.writer(file)
            data = [
                ["Giovanniland#8272", "@Giovanniland", "643109584566878228", "1", "Mythic", "2"],
                ["9003#5389", "@9003", "207526562331885568", "2", "Mythic", "2"],
                ["Salaxalans#6003", "@Spud Salaxalans", "290317739426316289", "3", "Legendary", "2"],
                ["DGES#0407", "@DGES", "323898337193492482", "4", "Legendary", "2"],
                ["Clarissa Alanis T. Star Samantha#8423", "@Clarissa Alanis T. Star Samantha", "332151056920477696", "5", "Legendary", "2"],
                ["esper#8919", "@Vilita", "247049219603562496", "6", "Legendary", "2"],
                ["Neo is Best Girl#4002", "@Some stranger", "503317489145479210", "7", "Legendary", "2"],
                ["Fhaeng#1772", "@ḟḥǻȇṋğ", "442826161496653835", "8", "Legendary", "2"],
                ["upc#5483", "@upc", "230778695713947648", "9", "Legendary", "2"],
                ["dithpri#8254", "@rac", "233290600131067913", "10", "Legendary", "2"],
                ["Aerilia#8878", "@Aerilia", "323456008678801412", "11", "Legendary", "2"],
                ["Sitethief#3264", "@Site", "295987274171154432", "12", "Legendary", "2"],
                ["Rewan Demontay#4498", "@Rewan | Bronyleader's Intern", "441383168260440064", "13", "Epic", "2"],
                ["Yuuka#6188", "@Yuuka [Seanat]", "271443809005600771", "14", "Epic", "2"],
                ["Bronyleader#1133", "@Bronyleader", "347871644544401409", "15", "Epic", "2"],
                ["Atlae#0779", "@S3 is not here it can't be oh no", "278344420464525312", "16", "Epic", "2"],
                ["Steev Kafka#8387", "@Logger", "934451636649226260", "17", "Epic", "2"],
                ["walrus#8689", "@heartbreakingly mediocre", "761003357724082196", "18", "Epic", "2"]
            ]
            writer.writerows(data)

def setup(bot):
    bot.add_cog(Rarity(bot))
