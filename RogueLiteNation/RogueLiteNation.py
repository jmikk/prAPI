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

    @commands.command(name="viewskilltree")
    async def view_skill_tree(self, ctx):
        """View and interact with your skill tree using buttons."""
        user = ctx.author
        unlocked = await self.config.user(user).unlocked_skills()
        user_gems = await self.config.user(user).base_stats.get_raw("gems")

        embed = Embed(title=f"{user.display_name}'s Skill Tree",
                      description=f"\U0001F48E You have **{user_gems}** Gems.",
                      color=discord.Color.green())

        view = SkillTreeView(self, user, unlocked, user_gems)

        for skill_id, skill in self.skilltree.items():
            status = view.get_skill_status(skill_id)
            name = skill.get("name", skill_id)
            desc = skill.get("desc", "")
            cost = skill.get("gems", 0)

            embed.add_field(
                name=name,
                value=f"{desc}\n`ID: {skill_id}` | \U0001F48E Cost: {cost}\nStatus: **{status}**",
                inline=False
            )

            if status == "Unlockable":
                view.add_unlock_button(skill_id, name)

        await ctx.send(embed=embed, view=view)


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

        if skill_id == "root":
            return "Unlockable" if self.gems >= self.skilltree[skill_id].get("gems", 0) else "Need More Gems"

        prereqs = self.get_prerequisites(skill_id)
        if all(pre in self.unlocked for pre in prereqs):
            cost = self.skilltree[skill_id].get("gems", 0)
            return "Unlockable" if self.gems >= cost else "Need More Gems"

        return "Locked"

    def add_unlock_button(self, skill_id, label):
        async def callback(interaction: Interaction):
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message("This is not your skill tree!", ephemeral=True)

            try:
                path, total_cost = self.get_unlock_path(skill_id)
                if self.gems < total_cost:
                    return await interaction.response.send_message(
                        f"You need {total_cost} \U0001F48E to unlock **{label}** and its prerequisites. You have {self.gems}.",
                        ephemeral=False
                    )

                self.gems -= total_cost
                await self.cog.config.user(self.user).base_stats.set_raw("gems", self.gems)

                unlocked = set(await self.cog.config.user(self.user).unlocked_skills())
                bonuses = await self.cog.config.user(self.user).bonus_stats()

                for sid in path:
                    skill = self.skilltree[sid]
                    unlocked.add(sid)
                    for stat, value in skill.get("bonus", {}).items():
                        bonuses[stat] = bonuses.get(stat, 0) + value

                await self.cog.config.user(self.user).unlocked_skills.set(list(unlocked))
                await self.cog.config.user(self.user).bonus_stats.set(bonuses)

                await interaction.response.send_message(
                    f"✅ Unlocked: {', '.join(self.skilltree[s]['name'] for s in path)} (\U0001F48E {total_cost})",
                    ephemeral=False
                )

            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Something went wrong: `{e}`",
                    ephemeral=False
                )
                raise

    def get_unlock_path(self, skill_id):
        path = []
        visited = set()

        def recurse(current):
            if current in visited:
                return
            visited.add(current)

            if current not in self.skilltree:
                return

            for pre_id in self.get_prerequisites(current):
                if pre_id not in self.unlocked:
                    recurse(pre_id)
            if current not in self.unlocked:
                path.append(current)

        recurse(skill_id)

        if "root" not in self.unlocked and skill_id != "root" and "root" not in path:
            return None, 0

        total_cost = sum(self.skilltree[sid].get("gems", 0) for sid in path)
        return path, total_cost

    def get_prerequisites(self, target_id):
        return [sid for sid, val in self.skilltree.items() if target_id in val.get("unlocks", [])]
