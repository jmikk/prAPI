from redbot.core import commands
import asyncio
import xml.etree.ElementTree as ET


def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False

    return commands.permissions_check(predicate)


class CardQ(commands.Cog):
    """My custom cog"""
    
    def __init__(self, bot):
        self.bot = bot

    # great once your done messing with the bot.
    #   async def cog_command_error(self, ctx, error):
    #       await ctx.send(" ".join(error.args))
    
    async def search_cards(self,xml_file, search_criteria):
        with open(xml_file, "r", encoding="ISO-8859-1") as file:
            xml_data = file.read()
            xml_data = xml_data.replace("&", "&amp;")  # Replace & with &amp;

        tree = ET.fromstring(xml_data)


        cards_found = []

        for card in root.findall("SET/CARD"):
            card_data = {"ID": card.find("ID").text, "NAME": card.find("NAME").text}
            match_all_conditions = True

            for criteria in search_criteria:
                key, value = criteria.split(":", 1)
                element = card.find(key.upper())

                if element is not None and element.text == value:
                    card_data[key] = element.text
                elif key.upper() == "BADGES":
                    badges = card.findall("BADGES/BADGE")
                    badge_names = [
                        badge.text
                        for badge in badges
                        if value.lower() in badge.text.lower()
                    ]
                    if badge_names:
                        card_data[key] = badge_names
                    else:
                        match_all_conditions = False
                elif key.upper() == "TROPHIES":
                    trophies = card.findall("TROPHIES/TROPHY")
                    trophy_names = [
                        trophy.text
                        for trophy in trophies
                        if value.lower() in trophy.attrib.get("type", "").lower()
                    ]
                    if trophy_names:
                        card_data[key] = trophy_names
                    else:
                        match_all_conditions = False
                else:
                    match_all_conditions = False

            if match_all_conditions:
                cards_found.append(
                    card_data["NAME"]
                    + ","
                    + card_data["ID"]
                    + ",3,www.nationstates.net/card="
                    + card_data["ID"]
                    + "/season=3"
                )

        return cards_found


    # Example usage
    @commands.command()
    async def card_search(self,ctx,Criteria):
        search_criteria={}
        search_criteria = Criteria.split(",")

        found_cards = await self.search_cards("home/pi/cards.xml", search_criteria)

        with open("home/pi/output.txt", "w+") as f:
            for card in found_cards:
                f.write(card)
                await ctx.send(card)
