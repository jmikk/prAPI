import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
import json
from pathlib import Path
from discord.ui import View, Button

class SkillTreeManager:
    def __init__(self, tree_data):
        self.tree_data = tree_data

    def get_skill_node(self, category, path):
        node = self.tree_data.get(category)
        if not node:
            return None
        if path == ["root"]:
            return node.get("root")
        node = node.get("root")
        for key in path[1:]:
            node = node.get("children", {}).get(key)
            if node is None:
                return None
        return node

def load_skill_tree():
    try:
        with open(Path(__file__).parent / "skills.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}  # Return an empty tree if file doesn't exist

class SkillView(View):
    def __init__(self, cog, ctx, category="general", path=None):
        self.invoker = ctx.author
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.category = category
        self.path = path or ["root"]
        self.tree = cog.skill_tree_cache or {}
        self.tree_manager = SkillTreeManager(self.tree)
        self.skill = self.tree_manager.get_skill_node(category, self.path)
        if self.skill is None:
            return
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()

        async def unlock_callback(interaction):
            await self.cog.unlock_skill(self.ctx, self.category, self.path)
            self.skill = self.tree_manager.get_skill_node(self.category, self.path)
            self.update_buttons()
            await interaction.response.edit_message(embed=self.cog.get_skill_embed(self.skill, self.path), view=self)

        async def check_unlocked():
            path_key = f"{self.category}/{'/'.join(self.path)}"
            unlocked = await self.cog.config.user(self.ctx.author).unlocked_skills()
            return path_key in unlocked

        async def add_unlock_button():
            is_unlocked = await check_unlocked()
            button = Button(label="Unlock", style=discord.ButtonStyle.green, disabled=is_unlocked)
            async def unlock_check(interaction):
                if interaction.user != self.invoker:
                    return await interaction.response.send_message("You're not allowed to use these buttons.", ephemeral=True)
                await unlock_callback(interaction)
            button.callback = unlock_check
            button.callback = unlock_callback
            self.add_item(button)

        self.cog.bot.loop.create_task(add_unlock_button())

        if not self.skill:
            return

        for key, child in self.skill.get("children", {}).items():
            if not isinstance(child, dict) or "name" not in child:
                continue
            async def nav_callback(interaction, k=key):
                self.path.append(k)
                self.skill = self.tree_manager.get_skill_node(self.category, self.path)
                self.update_buttons()
                await interaction.response.edit_message(embed=self.cog.get_skill_embed(self.skill, self.path), view=self)

            button = Button(label=child["name"], style=discord.ButtonStyle.blurple)
            async def nav_callback(interaction, k=key):
                if interaction.user != self.invoker:
                    return await interaction.response.send_message("You're not allowed to use these buttons.", ephemeral=True)
                self.path.append(k)
                self.skill = self.tree_manager.get_skill_node(self.category, self.path)
                self.update_buttons()
                await interaction.response.edit_message(embed=self.cog.get_skill_embed(self.skill, self.path), view=self)
            button.callback = nav_callback
            self.add_item(button)
            self.children[-1].callback = nav_callback

        if len(self.path) > 1:
            async def back_callback(interaction):
                self.path.pop()
                self.skill = self.tree_manager.get_skill_node(self.category, self.path)
                self.update_buttons()
                await interaction.response.edit_message(embed=self.cog.get_skill_embed(self.skill, self.path), view=self)

            button = Button(label="⬅️ Back", style=discord.ButtonStyle.grey)
            async def back_callback(interaction):
                if interaction.user != self.invoker:
                    return await interaction.response.send_message("You're not allowed to use these buttons.", ephemeral=True)
                self.path.pop()
                self.skill = self.tree_manager.get_skill_node(self.category, self.path)
                self.update_buttons()
                await interaction.response.edit_message(embed=self.cog.get_skill_embed(self.skill, self.path), view=self)
            button.callback = back_callback
            self.add_item(button)
            self.children[-1].callback = back_callback


class RogueLiteNation(commands.Cog):
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

    def get_skill_embed(self, skill, path):
        if skill is None or not isinstance(skill, dict) or "name" not in skill:
            return discord.Embed(title="Skill Not Found", description="This skill could not be found or is malformed.", color=discord.Color.red())
        embed = discord.Embed(title=skill["name"], description=skill["description"], color=discord.Color.gold())
        embed.add_field(name="Cost", value=f"{skill['cost']} Gems", inline=True)
        embed.add_field(name="Path", value="/".join(path), inline=True)
        return embed

    @commands.command()
    async def viewskills(self, ctx, category: str = None):
        """Open the skill tree viewer."""
        self.skill_tree_cache = await self.config.guild(ctx.guild).skill_tree()
        self.skill_tree_cache = await self.config.guild(ctx.guild).skill_tree()
        if category is None:
            if not self.skill_tree_cache:
                return await ctx.send("No skill trees available. Upload one with `$uploadskills`.")
            view = View()
            for cat in self.skill_tree_cache:
                button = Button(label=cat.title(), style=discord.ButtonStyle.blurple)
                async def cat_callback(interaction, c=cat):
                    if interaction.user != ctx.author:
                        return await interaction.response.send_message("You're not allowed to use these buttons.", ephemeral=True)
                    v = SkillView(self, ctx, c)
                    skill = v.skill
                    await interaction.response.edit_message(embed=self.get_skill_embed(skill, ["root"]), view=v)
                button.callback = cat_callback
                view.add_item(button)
            return await ctx.send("Choose a skill tree:", view=view)
        view = SkillView(self, ctx, category)
        skill = view.skill
        if skill is None:
            return await ctx.send("No skill found at the root of this tree. Please upload a valid skill tree using `!uploadskills`.")
        embed = self.get_skill_embed(skill, view.path)
        await ctx.send(embed=embed, view=view)

    async def unlock_skill(self, ctx, category, path):
        tree = await self.config.guild(ctx.guild).skill_tree()
        node = tree.get(category)
        for key in path[1:]:
            node = node.get("children", {}).get(key)
        if not node:
            return

        user = ctx.author
        user_config = self.config.user(user)
        unlocked = await user_config.unlocked_skills()
        path_key = f"{category}/{'/'.join(path)}"
        if path_key in unlocked:
            await ctx.send("You've already unlocked this skill!")
            return

        stats = await user_config.base_stats()
        bonus = await user_config.bonus_stats()
        total_gems = stats["gems"] + bonus["gems"]

        if total_gems < node["cost"]:
            await ctx.send("Not enough Gems!")
            return

        # Deduct gems (from bonus first)
        if bonus["gems"] >= node["cost"]:
            bonus["gems"] -= node["cost"]
        else:
            remaining = node["cost"] - bonus["gems"]
            bonus["gems"] = 0
            stats["gems"] -= remaining

        # Apply bonuses
        for stat, val in node.get("bonus", {}).items():
            bonus[stat] = bonus.get(stat, 0) + val

        await user_config.base_stats.set(stats)
        await user_config.bonus_stats.set(bonus)
        unlocked.append(path_key)
        await user_config.unlocked_skills.set(unlocked)
        await ctx.send(f"✅ You unlocked **{node['name']}**!")

    @commands.command()
    async def uploadskills(self, ctx):
        """Admin only: Upload a skill tree by attaching a JSON file."""
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

    @commands.command()
    async def exportskills(self, ctx):
        """Download the current skill tree as a JSON file."""
        tree = await self.config.guild(ctx.guild).skill_tree()
        json_data = json.dumps(tree, indent=2)
        file = discord.File(fp=discord.utils._bytes(json_data), filename="skill_tree.json")
        await ctx.send("Here is your current skill tree:", file=file)

    @commands.command()
    async def convertgems(self, ctx, amount: int):
        """Convert Wellcoins to Gems at 10:1 rate."""
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
