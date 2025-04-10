# SkillTreeView for navigating and unlocking skills
class SkillTreeView(View):
    def __init__(self, cog, ctx, category):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.category = category
        self.path = ["root"]
        self.skill_tree = cog.skill_tree_cache.get(category, {})
        self.skill = self._get_node()

    async def setup(self):
        self.clear_items()
        unlocked = await self.cog.config.user(self.ctx.author).unlocked_skills()
        path_key = f"{self.category}/{'/'.join(self.path)}"

        if path_key not in unlocked:
            # Unlock button
            async def unlock_callback(interaction):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                    return
                result = await self.cog.unlock_skill(self.ctx.author, self.category, self.path)
                await interaction.response.send_message(result, ephemeral=True)
                await self.setup()
                await interaction.message.edit(embed=self.get_embed(), view=self)

            button = Button(label="Unlock", style=discord.ButtonStyle.green)
            button.callback = unlock_callback
            self.add_item(button)

                # Add navigation buttons for each child, with visual indicators and pagination
        children_items = list(self.skill.get("children", {}).items())
        page_size = 5
        self.page = getattr(self, 'page', 0)
        start = self.page * page_size
        end = start + page_size

        for key, child in children_items[start:end]:
            async def nav_callback(interaction, k=key):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                    return
                self.path.append(k)
                self.skill = self._get_node()
                await self.setup()
                await interaction.message.edit(embed=self.get_embed(), view=self)

                        label = child.get("name", key)
            path_key = f"{self.category}/{'/'.join(self.path + [key])}"
            emoji = "✅" if path_key in unlocked else "🔒"
            button = Button(label=f"{emoji} {label}", style=discord.ButtonStyle.blurple)
            button.callback = nav_callback
            self.add_item(button)

                # Add back button if not at root
        if len(self.path) > 1:
            async def back_callback(interaction):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                    return
                self.path.pop()
                self.skill = self._get_node()
                await self.setup()
                await interaction.message.edit(embed=self.get_embed(), view=self)

            back = Button(label="⬅️ Back", style=discord.ButtonStyle.grey)
            back.callback = back_callback
                        self.add_item(back)

        # Add pagination buttons if necessary
        if len(children_items) > page_size:
            if self.page > 0:
                async def prev_page(interaction):
                    if interaction.user.id != self.ctx.author.id:
                        await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                        return
                    self.page -= 1
                    await self.setup()
                    await interaction.message.edit(embed=self.get_embed(), view=self)

                prev_btn = Button(label="⬅️ Prev", style=discord.ButtonStyle.grey)
                prev_btn.callback = prev_page
                self.add_item(prev_btn)

            if end < len(children_items):
                async def next_page(interaction):
                    if interaction.user.id != self.ctx.author.id:
                        await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                        return
                    self.page += 1
                    await self.setup()
                    await interaction.message.edit(embed=self.get_embed(), view=self)

                next_btn = Button(label="Next ➡️", style=discord.ButtonStyle.grey)
                next_btn.callback = next_page
                self.add_item(next_btn)

    def _get_node(self):
        node = self.skill_tree.get("root", {})
        for key in self.path[1:]:
            node = node.get("children", {}).get(key, {})
        return node

    def get_embed(self):
        embed = discord.Embed(
            title=self.skill.get("name", "Unknown Skill"),
            description=self.skill.get("description", "No description provided."),
            color=discord.Color.gold()
        )
        embed.add_field(name="Cost", value=f"{self.skill.get('cost', 0)} Gems", inline=True)
        embed.add_field(name="Path", value="/".join(self.path), inline=True)
        return embed

import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
import json
from pathlib import Path
from discord.ui import View, Button


# Main cog class for managing the RogueLite Nation game logic
class RogueLiteNation(commands.Cog):
        # Initialization and configuration setup
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=789456123789, force_registration=True)
        self.config.register_guild(skill_tree={})
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
            },
            unlocked_skills=[]
        )

        self.skill_tree_cache = {}
        self.SCALE_IDS = {
            "wit": [75, 68, 36, 78, 70],
            "instinct": [54, 37, 9, 69, 67],
            "faith": [32, 38, 41, 47, 28],
            "allegiance": [87, 46, 62, 27, 42],
            "evil": [5, 64, 51, 35, 49, 60],
            "good": [44, 34, 39, 40, 7, 6],
            "money": [18, 19, 16, 10, 23, 20, 1, 79, 22, 13, 76, 12, 11, 24, 15, 25, 14, 21]
        }

        # Fetch prank census stats from NationStates API
    async def get_nation_stats(self, nation):
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?nation={nation.lower().replace(' ', '_')};q=census;scale=all;mode=prank"
        headers = {"User-Agent": "Redbot-Roguelite/1.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
        return self.parse_census_xml(text)

        # Parse XML data returned from NationStates census API
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

        # Calculate an average score on a 1–10 scale for a set of scale IDs
    def calculate_spectrum(self, pranks, ids):
        total = sum(pranks.get(str(i), 0) for i in ids)
        normalized = (total / len(ids)) * 9 + 1
        return int(normalized)

        # Compare two sets of IDs to produce a single stat score difference
    def calculate_dual_stat(self, pranks, side_a_ids, side_b_ids):
        score = self.calculate_spectrum(pranks, side_a_ids) - self.calculate_spectrum(pranks, side_b_ids)
        return int(score)

        # Compute all stats from prank census data
    def calculate_all_stats(self, pranks):
        return {
            "insight_vs_instinct": self.calculate_dual_stat(pranks, self.SCALE_IDS["wit"], self.SCALE_IDS["instinct"]),
            "faith_vs_allegiance": self.calculate_dual_stat(pranks, self.SCALE_IDS["faith"], self.SCALE_IDS["allegiance"]),
            "good_vs_evil": self.calculate_dual_stat(pranks, self.SCALE_IDS["good"], self.SCALE_IDS["evil"]),
            "gems": self.calculate_spectrum(pranks, self.SCALE_IDS["money"])
        }

        # Command to link your NationStates nation and pull stats
    @commands.command()
    async def buildnation(self, ctx, *, nation: str):
        await self.config.user(ctx.author).nation.set(nation)
        await ctx.send(f"Nation set to **{nation}**!")
        await self.refreshstats(ctx)

        # Command to refresh your stats from NationStates based on your linked nation
    @commands.command()
    async def refreshstats(self, ctx):
        nation = await self.config.user(ctx.author).nation()
        if not nation:
            return await ctx.send("You need to set your nation first using `!setnation <name>`.")
        pranks = await self.get_nation_stats(nation)
        base_stats = self.calculate_all_stats(pranks)
        await self.config.user(ctx.author).base_stats.set(base_stats)
        await ctx.send(f"Base stats refreshed from **{nation}**!")

        # Command to view your calculated stat spectrum
    @commands.command()
    async def mystats(self, ctx):
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


        # Admin command to upload a skill tree JSON file
    @commands.command()
    async def viewskills(self, ctx, category: str = "general"):
        """Open the skill tree viewer."""
        self.skill_tree_cache = await self.config.guild(ctx.guild).skill_tree()
        view = SkillTreeView(self, ctx, category)
        await view.setup()
        await ctx.send(embed=view.get_embed(), view=view)

    @commands.command()
    async def viewunlocked(self, ctx):
        """List all unlocked skills for the user."""
        unlocked = await self.config.user(ctx.author).unlocked_skills()
        if not unlocked:
            return await ctx.send("You have not unlocked any skills yet.")

        embed = discord.Embed(title=f"Unlocked Skills for {ctx.author.display_name}", color=discord.Color.green())
        embed.description = "
".join(f"✅ {path}" for path in unlocked)
        await ctx.send(embed=embed)

    @commands.command()
    async def uploadskills(self, ctx):
        if not ctx.message.attachments:
            return await ctx.send("Please attach a JSON file containing the skill tree.")

        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith(".json"):
            return await ctx.send("The attached file must be a .json file.")

        try:
            data = await attachment.read()
            tree = json.loads(data.decode("utf-8"))
        except Exception as e:
            return await ctx.send(f"Failed to load JSON: {e}")

        await self.config.guild(ctx.guild).skill_tree.set(tree)
        self.skill_tree_cache = tree
        await ctx.send("✅ Skill tree uploaded and saved!")

        # Core logic for unlocking a skill from the tree
    async def unlock_skill(self, user, category, path):
        tree = await self.config.guild(user.guild).skill_tree()
        category_tree = tree.get(category)
        if not category_tree:
            return "Skill tree category not found."

        if path == ["root"]:
            node = category_tree.get("root")
        else:
            node = category_tree.get("root")
            for key in path[1:]:
                node = node.get("children", {}).get(key)
                if node is None:
                    return "Skill path is invalid."

        user_config = self.config.user(user)
        unlocked = await user_config.unlocked_skills()
        path_key = f"{category}/{'/'.join(path)}"

        if path_key in unlocked:
            return "You've already unlocked this skill!"

        if len(path) > 1:
            parent_path = path[:-1]
            parent_key = f"{category}/{'/'.join(parent_path)}"
            if parent_key not in unlocked:
                return "You must unlock the previous skill first."

        stats = await user_config.base_stats()
        bonus = await user_config.bonus_stats()
        total_gems = stats["gems"] + bonus["gems"]

        if total_gems < node["cost"]:
            return "Not enough Gems!"

        if bonus["gems"] >= node["cost"]:
            bonus["gems"] -= node["cost"]
        else:
            remaining = node["cost"] - bonus["gems"]
            bonus["gems"] = 0
            stats["gems"] -= remaining

        for stat, val in node.get("bonus", {}).items():
            bonus[stat] = bonus.get(stat, 0) + val

        await user_config.base_stats.set(stats)
        await user_config.bonus_stats.set(bonus)
        unlocked.append(path_key)
        await user_config.unlocked_skills.set(unlocked)
        return f"✅ You unlocked **{node['name']}**!"

        # Command to convert Wellcoins into Gems
    @commands.command()
    async def convertgems(self, ctx, amount: int):
        rate = 10
        total_cost = amount * rate
        user = ctx.author

        wallet = await self.shared_config.user(user).master_balance()
        if wallet < total_cost:
            return await ctx.send("Not enough Wellcoins!")

        await self.shared_config.user(user).master_balance.set(wallet - total_cost)
        bonus = await self.config.user(user).bonus_stats()
        bonus["gems"] += amount
        await self.config.user(user).bonus_stats.set(bonus)
        await ctx.send(f"Converted {total_cost} Wellcoins to {amount} Gems!")
