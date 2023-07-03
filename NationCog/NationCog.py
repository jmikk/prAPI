import csv
import requests
from redbot.core import commands, data_manager
import urllib.request
import gzip
import xml.etree.ElementTree as ET
import ssl
import os
import discord

class NationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTPWrErSHEy9kZVwcT7NK_gVJsBdytg2yNnKgXgFbs_Cxe2VFj2wUbBCgsER6Uik5ewWaJMj2UrlIFz/pub?gid=0&single=true&output=csv"

    def find_missing_nations(self, api_list, first_list):
        api_set = set(api_list)  # Convert API list to a set
        missing_nations = []
        for nation in first_list:
            if nation[1].lower().replace(" ", "_") not in api_set:
                missing_nations.append(nation)

        return missing_nations

    @commands.command()
    @commands.has_role("Security Officer")
    @commands.cooldown(1, 6 * 60 * 60, commands.BucketType.user)  # 1 use per 6 hours per user
    async def WA_dump(self,ctx,region="the_wellspring"):
        await ctx.send("This might take some time give me a bit!")
        try:
            os.remove(data_manager.cog_data_path(self) / "output.txt")
        except Exception:
            pass
        
        # Disable SSL certificate verification
        ssl._create_default_https_context = ssl._create_unverified_context
        
        # Set the User-Agent header
        opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "9006")]
        urllib.request.install_opener(opener)
        
        # Download and unzip the file
        url = "https://www.nationstates.net/pages/nations.xml.gz"
        filename = data_manager.cog_data_path(self) / "nations.xml.gz"
        urllib.request.urlretrieve(url, filename)
        with gzip.open(filename, "rb") as f_in:
            with open(data_manager.cog_data_path(self) / "nations.xml", "wb") as f_out:
                f_out.write(f_in.read())
        
        # Parse the XML data
        tree = ET.parse(data_manager.cog_data_path(self) / "nations.xml")
        root = tree.getroot()
        
        # Initialize a dictionary to store nation details
        nations = {}
        
        # Iterate over each nation
        for nation in root.findall("./NATION"):
            region = nation.find("REGION").text
            unstatus = nation.find("UNSTATUS").text
            if region == "The Wellspring" and (
                unstatus == "WA Delegate" or unstatus == "WA Member"
            ):
                name = nation.find("NAME").text
                name = name.lower().replace(" ", "_")
                endorsements = nation.find("ENDORSEMENTS").text
                endorsement_count = len(endorsements.split(","))
                endorsement_list = endorsements.split(",")
                nations[name] = (endorsement_count, endorsement_list)
        
        # Output the results
        for name, (endorsement_count, endorsement_list) in nations.items():
            endorsement_str = "\t".join(endorsement_list)
            print(f"{name}\t{endorsement_count}\t{endorsement_str}")
            with open(data_manager.cog_data_path(self) / "output.txt", "a") as f:
                f.write(f"{name}\t{endorsement_count}\t{endorsement_str}\n")
            file = discord.File(data_manager.cog_data_path(self) / "output.txt")  # Replace with the path to your file
            await ctx.send(file=file)
            await ctx.send("DONE!")

        
        os.remove(data_manager.cog_data_path(self) / "nations.xml")
        os.remove(data_manager.cog_data_path(self) / "nations.xml.gz")
    
    @commands.command()
    @commands.has_role("Warden of Internal Affairs")
    async def cit_chk(self, ctx):
        await ctx.send("You got it I'll think for a few moments!")
        # Fetch the CSV data
        response = requests.get(self.sheet_url)
        csv_data = response.text

        # Parse the CSV data
        reader = csv.reader(csv_data.splitlines())
        next(reader)  # Skip the header row

        # Create a list of The Wellspring Nation and Discord names
        data_list = []
        for row in reader:
            discord_name = row[0]
            nation_name = row[2]
            WA_name = row[4]
            data_list.append((discord_name, nation_name,WA_name))

        # Fetch the data from the NationStates API
        header = {"User-Agent": "9003"}
        url = "https://www.nationstates.net/cgi-bin/api.cgi"
        response = requests.post(
            url, headers=header, data={"region": "the_wellspring", "q": "nations"}
        )
        xml_data = response.text.replace('<REGION id="the_wellspring">\n<NATIONS>', "").replace(
            "</NATIONS>\n</REGION>", ""
        )

        # Split the XML data into a list of nation names
        nation_list = xml_data.split(":")

        # Find missing nations
        missing_nations = self.find_missing_nations(nation_list, data_list)

        # Print the list of missing nations
        for nation in missing_nations:
            await ctx.send(f"Missing nation: {nation[1]} Discord: {nation[0]}")
        if not missing_nations:
            await ctx.send("Everyone is good! on resedency check")
            
        url = "https://www.nationstates.net/cgi-bin/api.cgi"
        response = requests.post(
            url, headers=header, data={"wa": "1", "q": "members"}
        )
        xml_data = response.text.replace('<WA council="1"><MEMBERS>', "").replace(
            "</MEMBERS></WA>", ""
        )

        # Split the XML data into a list of nation names
        nation_list = xml_data.split(",")

        # Find missing nations
        nation_list = set(nation_list)  # Convert API list to a set
        missing_nations = []
        for nation in data_list:
            if nation[2].lower().replace(" ", "_") not in nation_list:
                missing_nations.append(nation)        
        for nation in missing_nations:
            await ctx.send(f"Missing WA as nation: {nation[2]}  is not in the WA Discord: {nation[0]}")
        if not missing_nations:
            await ctx.send("Everyone is good! on resedency check")

# Add this part to your main bot file
# bot = commands.Bot(command_prefix="!")
# bot.add_cog(NationCog(bot))
