import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
from discord.ui import View, Button
from discord import Interaction, Embed, ButtonStyle
import os
import json

class RogueLiteNation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=789456123789, force_registration=True)
        self.shared_config = Config.get_conf(None, identifier=345678654456, force_registration=True)

        self.skilltree = self.load_skilltree()

        self.config.register_user(
            nation=None,
            base_stats={
                "insight_vs_instinct": 0,
                "faith_vs_allegiance": 0,
                "good_vs_evil": 0,
                "gems": 0
            },
            unlocked_skills=[],
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


    def load_skilltree(self):
        path = os.path.join(os.path.dirname(__file__), "skilltree.json")
        with open(path, "r") as f:
            return json.load(f)
            
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
                prank = (100 - float(prank_tag.text)) / 100
                prank_dict[scale_id] = prank
        return prank_dict

    def calculate_spectrum(self, pranks, ids):
        total = sum(pranks.get(str(i), 0) for i in ids)
        normalized = (total / len(ids)) * 9 + 1  # Normalize to range 1–10
        return int(normalized)

    def calculate_dual_stat(self, pranks, side_a_ids, side_b_ids):
        score = self.calculate_spectrum(pranks, side_a_ids) - self.calculate_spectrum(pranks, side_b_ids)
        return int(score)

    def calculate_all_stats(self, pranks):
        return {
            "insight_vs_instinct": self.calculate_dual_stat(pranks, self.SCALE_IDS["wit"], self.SCALE_IDS["instinct"]),
            "faith_vs_allegiance": self.calculate_dual_stat(pranks, self.SCALE_IDS["faith"], self.SCALE_IDS["allegiance"]),
            "good_vs_evil": self.calculate_dual_stat(pranks, self.SCALE_IDS["good"], self.SCALE_IDS["evil"]),
            "gems": self.calculate_spectrum(pranks, self.SCALE_IDS["money"])
        }

    @commands.command(name="viewskilltree")
    async def view_skill_tree(self, ctx):
        """View and interact with your skill tree using buttons."""
        user = ctx.author
        unlocked = await self.config.user(user).unlocked_skills()
        user_gems = await self.config.user(user).base_stats.get_raw("gems")
    
        embed = Embed(title=f"{user.display_name}'s Skill Tree",
                      description=f"💎 You have **{user_gems}** Gems.",
                      color=discord.Color.green())
    
        view = SkillTreeView(self, user, unlocked, user_gems)
        
        for skill_id, skill in self.skilltree.items():
            status = view.get_skill_status(skill_id)
            name = skill["name"]
            desc = skill.get("desc", "")
            cost = skill.get("gems", 0)
    
            embed.add_field(name=name, value=f"{desc}\n`ID: {skill_id}` | Cost: {cost} 💎\nStatus: {status}", inline=False)
            if status == "Unlockable":
                view.add_unlock_button(skill_id, name)
    
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def tradegems(self, ctx, amount: int):
        """Trade Wellcoins for Gems (100 Wellcoins = 1 Gem)."""
        if amount <= 0:
            return await ctx.send("Enter a positive amount of gems to buy.")
    
        wellcoins_needed = amount * 100
        balance = await self.shared_config.user(ctx.author).master_balance()
    
        if balance < wellcoins_needed:
            return await ctx.send(f"You need {wellcoins_needed} Wellcoins, but you only have {balance}.")
    
        # Deduct wellcoins
        await self.shared_config.user(ctx.author).master_balance.set(balance - wellcoins_needed)
    
        # Add gems
        user_gems = await self.config.user(ctx.author).base_stats.get_raw("gems")
        await self.config.user(ctx.author).base_stats.set_raw("gems", user_gems + amount)
    
        await ctx.send(f"💰 Traded {wellcoins_needed} Wellcoins for {amount} Gems!")


    @commands.command()
    async def unlockskill(self, ctx, skill_id: str):
        """Unlock a skill using Gems."""
        user = ctx.author
        skill = self.skilltree.get(skill_id)
        if not skill:
            return await ctx.send("That skill doesn't exist.")
    
        unlocked = await self.config.user(user).unlocked_skills()
        if skill_id in unlocked:
            return await ctx.send("You've already unlocked that skill.")
    
        # Check prerequisites
        if skill_id != "root":
            prereqs_met = any(
                pre in unlocked
                for pre in self.skilltree
                if skill_id in self.skilltree[pre].get("unlocks", [])
            )
            if not prereqs_met:
                return await ctx.send("You haven't unlocked the required skills yet.")
    
        # Check gem cost
        user_gems = await self.config.user(user).base_stats.get_raw("gems")
        cost = skill.get("gems", 0)
        if user_gems < cost:
            return await ctx.send(f"You need {cost} Gems to unlock this skill.")
    
        # Deduct gems and unlock
        await self.config.user(user).base_stats.set_raw("gems", user_gems - cost)
        unlocked.append(skill_id)
        await self.config.user(user).unlocked_skills.set(unlocked)
    
        # Apply bonuses
        bonus = skill.get("bonus", {})
        if bonus:
            user_bonus = await self.config.user(user).bonus_stats()
            for k, v in bonus.items():
                user_bonus[k] = user_bonus.get(k, 0) + v
            await self.config.user(user).bonus_stats.set(user_bonus)
    
        await ctx.send(f"✅ Unlocked **{skill['name']}** using {cost} Gems!")


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
        embed.add_field(name=name, value=str(val), inline=False)

        name, val = resolve_dual("faith", "allegiance", base["faith_vs_allegiance"])
        embed.add_field(name=name, value=str(val), inline=False)

        name, val = resolve_dual("good", "evil", base["good_vs_evil"])
        embed.add_field(name=name, value=str(val), inline=False)

        embed.add_field(name="Gems", value=str(int(base['gems'] + bonus.get('gems', 0))), inline=False)

        wellcoins = await self.shared_config.user(ctx.author).master_balance()
        embed.add_field(name="Wellcoins", value=str(wellcoins), inline=False)

        await ctx.send(embed=embed)


class SkillTreeView(View):
    def __init__(self, cog, user, unlocked, gems):
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        self.unlocked = set(unlocked)
        self.gems = gems
        self.skilltree = cog.skilltree

    def get_skill_status(self, skill_id):
        if skill_id in self.unlocked:
            return "Unlocked"
        if skill_id == "root" or any(pre in self.unlocked for pre in self.skilltree if skill_id in self.skilltree[pre].get("unlocks", [])):
            cost = self.skilltree[skill_id].get("gems", 0)
            return "Unlockable" if self.gems >= cost else "Need More Gems"
        return "Locked"

    def add_unlock_button(self, skill_id, label):
        async def callback(interaction: Interaction):
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message("This is not your skill tree!", ephemeral=True)

            path, total_cost = self.get_unlock_path(skill_id)
            if self.gems < total_cost:
                return await interaction.response.send_message(f"You need {total_cost} 💎 to unlock **{label}** and its prerequisites.", ephemeral=True)

            # Deduct gems
            self.gems -= total_cost
            await self.cog.config.user(self.user).base_stats.set_raw("gems", self.gems)

            # Unlock all in path
            unlocked = set(await self.cog.config.user(self.user).unlocked_skills())
            bonuses = await self.cog.config.user(self.user).bonus_stats()

            for sid in path:
                skill = self.skilltree[sid]
                unlocked.add(sid)
                for stat, value in skill.get("bonus", {}).items():
                    bonuses[stat] = bonuses.get(stat, 0) + value

            await self.cog.config.user(self.user).unlocked_skills.set(list(unlocked))
            await self.cog.config.user(self.user).bonus_stats.set(bonuses)

            await interaction.response.send_message(f"✅ Unlocked: {', '.join(self.skilltree[s]['name'] for s in path)}", ephemeral=True)

        btn = Button(label=label, custom_id=skill_id, style=ButtonStyle.success)
        btn.callback = callback
        self.add_item(btn)

    def get_unlock_path(self, skill_id):
        # Recursively figure out all locked prereqs
        path = []
        visited = set()

        def recurse(current):
            if current in visited or current in self.unlocked:
                return
            visited.add(current)
            for pre_id in self.get_prerequisites(current):
                recurse(pre_id)
            path.append(current)

        recurse(skill_id)
        total_cost = sum(self.skilltree[sid].get("gems", 0) for sid in path)
        return path, total_cost

    def get_prerequisites(self, target_id):
        return [sid for sid, val in self.skilltree.items() if target_id in val.get("unlocks", [])]

