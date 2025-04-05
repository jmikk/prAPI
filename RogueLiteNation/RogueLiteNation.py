import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET

class RogueLiteNation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=789456123789, force_registration=True)
        self.shared_config = Config.get_conf(None, identifier=345678654456, force_registration=True)

        self.config.register_user(
            nation=None,
            base_stats={
                "insight_vs_instinct": 0,
                "faith_vs_allegiance": 0,
                "good_vs_evil": 0,
                "gems": 0
            },
            bonus_stats={
                "insight": 0,
                "instinct": 0,
                "faith": 0,
                "allegiance": 0,
                "good": 0,
                "evil": 0,
                "gems": 0
            }
        )

        self.SCALE_IDS = {
            "wit": [75, 68, 36, 78, 70],
            "instinct": [54, 37, 9, 69, 67],
            "faith": [32, 38, 41, 47, 28],
            "allegiance": [87, 46, 62, 27, 42],
            "evil": [5, 64, 51, 35, 49, 60],
            "good": [44, 34, 39, 40, 7, 6],
            "money": [18, 19, 16, 10, 23, 20, 1, 79, 22, 13, 76, 12, 11, 24, 15, 25, 14, 21]
        }

    async def get_nation_stats(self, nation):
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?nation={nation.lower().replace(' ', '_')};q=census;scale=all;mode=prank"
        headers = {"User-Agent": "Redbot-Roguelite/1.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
        return self.parse_census_xml(text)

    def parse_census_xml(self, xml_data):
        root = ET.fromstring(xml_data)
        prank_dict = {}
        for scale in root.find("CENSUS"):
            scale_id = scale.attrib["id"]
            prank_tag = scale.find("PRANK")
            if prank_tag is not None and prank_tag.text is not None:
                # PRANK is a percentage rank, convert to raw scale (0-100% where 0 is best)
                # We'll invert it so higher = better (like a score): 100 - prank
                prank = (100 - float(prank_tag.text)) / 100
                prank_dict[scale_id] = prank
        return prank_dict

    def calculate_spectrum(self, pranks, ids):
        total = sum(pranks.get(str(i), 0) for i in ids)
        normalized = (total / len(ids)) * 9 + 1  # Normalize to range 1–10
        return normalized

    def calculate_dual_stat(self, pranks, side_a_ids, side_b_ids):
        score = self.calculate_spectrum(pranks, side_a_ids) - self.calculate_spectrum(pranks, side_b_ids)
        return score

    def calculate_all_stats(self, pranks):
        return {
            "insight_vs_instinct": self.calculate_dual_stat(pranks, self.SCALE_IDS["wit"], self.SCALE_IDS["instinct"]),
            "faith_vs_allegiance": self.calculate_dual_stat(pranks, self.SCALE_IDS["faith"], self.SCALE_IDS["allegiance"]),
            "good_vs_evil": self.calculate_dual_stat(pranks, self.SCALE_IDS["good"], self.SCALE_IDS["evil"]),
            "gems": self.calculate_spectrum(pranks, self.SCALE_IDS["money"])
        }

    @commands.command()
    async def buildnation(self, ctx, *, nation: str):
        """Set your NationStates nation."""
        await self.config.user(ctx.author).nation.set(nation)
        await ctx.send(f"Nation set to **{nation}**!")
        await self.refreshstats(ctx)

    @commands.command()
    async def refreshstats(self, ctx):
        """Refresh your base stats from your NationStates nation."""
        nation = await self.config.user(ctx.author).nation()
        if not nation:
            return await ctx.send("You need to set your nation first using `!setnation <name>`.")
        pranks = await self.get_nation_stats(nation)
        await ctx.send(pranks)
        base_stats = self.calculate_all_stats(pranks)
        await self.config.user(ctx.author).base_stats.set(base_stats)
        await ctx.send(f"Base stats refreshed from **{nation}**!")

    @commands.command()
    async def mystats(self, ctx):
        """View your current effective stats."""
        base = await self.config.user(ctx.author).base_stats()
        bonus = await self.config.user(ctx.author).bonus_stats()

        def resolve_dual(name1, name2, value):
            if value + bonus.get(name1, 0) - bonus.get(name2, 0) > 0:
                return name1.title(), abs(value + bonus.get(name1, 0) - bonus.get(name2, 0))
            else:
                return name2.title(), abs(value + bonus.get(name2, 0) - bonus.get(name1, 0))

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Stats", color=discord.Color.green())

        name, val = resolve_dual("insight", "instinct", base["insight_vs_instinct"])
        embed.add_field(name=name, value=f"{val:.2f}", inline=False)

        name, val = resolve_dual("faith", "allegiance", base["faith_vs_allegiance"])
        embed.add_field(name=name, value=str(val), inline=False)

        name, val = resolve_dual("good", "evil", base["good_vs_evil"])
        embed.add_field(name=name, value=str(val), inline=False)

        embed.add_field(name="Gems", value=f"{base['gems'] + bonus.get('gems', 0):.2f}", inline=False)

        wellcoins = await self.shared_config.user(ctx.author).master_balance()
        embed.add_field(name="Wellcoins", value=str(wellcoins), inline=False)

        await ctx.send(embed=embed)
