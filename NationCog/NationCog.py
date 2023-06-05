import csv
import requests
from redbot.core import commands

class NationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTPWrErSHEy9kZVwcT7NK_gVJsBdytg2yNnKgXgFbs_Cxe2VFj2wUbBCgsER6Uik5ewWaJMj2UrlIFz/pub?gid=0&single=true&output=csv"

    def find_missing_nations(api_list, first_list):
        api_set = set(api_list)  # Convert API list to a set
        missing_nations = []
        for nation in first_list:
            if nation[1].lower().replace(" ", "_") not in api_set:
                missing_nations.append(nation)

        return missing_nations

    @commands.command()
    @commands.has_role("Warden of Internal Affairs ",)
    async def cit_chk(self,ctx):
        # Fetch the CSV data
        csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTPWrErSHEy9kZVwcT7NK_gVJsBdytg2yNnKgXgFbs_Cxe2VFj2wUbBCgsER6Uik5ewWaJMj2UrlIFz/pub?gid=0&single=true&output=csv"
        response = requests.get(csv_url)
        csv_data = response.text

        # Parse the CSV data
        reader = csv.reader(csv_data.splitlines())
        next(reader)  # Skip the header row

        # Create a list of The Wellspring Nation and Discord names
        data_list = []
        for row in reader:
            discord_name = row[0]
            nation_name = row[2]
            data_list.append((discord_name, nation_name))

        # Fetch the data from the NationStates API
        header = {"User-Agent": "9003"}
        url = "https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q=nations"
        response = requests.post(
            url, headers=header, data={"region": "the_wellspring", "q": "nations"}
        )
        xml_data = response.text.replace('<REGION id="the_wellspring">\n<NATIONS>', "").replace(
            "</NATIONS>\n</REGION>", ""
        )

        # Split the XML data into a list of nation names
        nation_list = xml_data.split(":")

        # Print the list of nations
        for nation in nation_list:
            await ctx.send(self.find_missing_nations(nation_list, data_list))


