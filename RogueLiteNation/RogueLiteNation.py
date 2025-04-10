import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
import json
from pathlib import Path
from discord.ui import View, Button

class SkillTreeView(View):
    def __init__(self, cog, ctx, category):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.category = category
        self.path = ["root"]
        self.skill_tree = cog.skill_tree_cache.get(category, {})
        self.skill = self._get_node()
        self.page = 0

    async def setup(self):
        try:
            self.clear_items()
            unlocked = await self.cog.config.user(self.ctx.author).unlocked_skills()
            path_key = f"{self.category}/{'/'.join(self.path)}"
    
            if path_key not in unlocked:
                current_path = list(self.path)
                async def unlock_callback(interaction):
                    if interaction.user.id != self.ctx.author.id:
                        await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                        return
                    try:
                        result = await self.cog.unlock_skill(self.ctx.author, self.category, current_path)
                        await interaction.response.send_message(result, ephemeral=True)
                        await self.setup()
                        await interaction.message.edit(embed=self.get_embed(), view=self)
                    except Exception as e:
                        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
                        await self.ctx.send(f"Interaction error during unlock: {e}")
    
                button = Button(label="Unlock", style=discord.ButtonStyle.green)
                button.callback = unlock_callback
                self.add_item(button)
    
            children_items = list(self.skill.get("children", {}).items())
            page_size = 5
            start = self.page * page_size
            end = start + page_size
    
            for key, child in children_items[start:end]:
                def make_button(k, child_data):
                    async def nav_callback(interaction):
                        await interaction.response.defer()
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.followup("Only the command user can use this button.", ephemeral=True)
                            return
                        try:
                            self.path.append(k)
                            self.skill = self._get_node()
                            self.page = 0
                            await self.setup()
                            await interaction.message.edit(embed=self.get_embed(), view=self)
                        except Exception as e:
                            await interaction.response.followup(f"❌ Error: {e}", ephemeral=True)
                            await self.ctx.send(f"Interaction error during navigation: {e}")
    
                    label = child_data.get("name", k)
                    child_path_key = f"{self.category}/{'/'.join(self.path + [k])}"
                    emoji = "✅" if child_path_key in unlocked else "🔒"
                    button = Button(label=f"{emoji} {label}", style=discord.ButtonStyle.blurple)
                    button.callback = nav_callback
                    self.add_item(button)
    
                make_button(key, child)
    
            if len(self.path) > 1:
                async def back_callback(interaction):
                    await interaction.response.defer()
                    if interaction.user.id != self.ctx.author.id:
                        await interaction.response.followup("Only the command user can use this button.", ephemeral=True)
                        return
                    try:
                        self.path.pop()
                        self.skill = self._get_node()
                        self.page = 0
                        await self.setup()
                        await interaction.message.edit(embed=self.get_embed(), view=self)
                    except Exception as e:
                        await interaction.response.followup(f"❌ Error: {e}", ephemeral=True)
                        await self.ctx.send(f"Interaction error during back: {e}")
    
                back = Button(label="⬅️ Back", style=discord.ButtonStyle.grey)
                back.callback = back_callback
                self.add_item(back)
    
            if len(children_items) > page_size:
                if self.page > 0:
                    async def prev_page(interaction):
                        await interaction.response.defer()
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.followup("Only the command user can use this button.", ephemeral=True)
                            return
                        try:
                            self.page -= 1
                            await self.setup()
                            await interaction.message.edit(embed=self.get_embed(), view=self)
                        except Exception as e:
                            await interaction.response.followup(f"❌ Error: {e}", ephemeral=True)
                            await self.ctx.send(f"Interaction error during prev page: {e}")
    
                    prev_btn = Button(label="⬅️ Prev", style=discord.ButtonStyle.grey)
                    prev_btn.callback = prev_page
                    self.add_item(prev_btn)
    
                if end < len(children_items):
                    async def next_page(interaction):
                        await interaction.response.defer()    
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.followup("Only the command user can use this button.", ephemeral=True)
                            return
                        try:
                            self.page += 1
                            await self.setup()
                            await interaction.message.edit(embed=self.get_embed(), view=self)
                        except Exception as e:
                            await interaction.response.followup(f"❌ Error: {e}", ephemeral=True)
                            await self.ctx.send(f"Interaction error during next page: {e}")
    
                    next_btn = Button(label="Next ➡️", style=discord.ButtonStyle.grey)
                    next_btn.callback = next_page
                    self.add_item(next_btn)
        except Exception as e:
            channel = self.cog.bot.get_channel(1098673276064120842)
            if channel:
                await channel.send(f"Interaction error during navigation: {e}")
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


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
            return await ctx.send("You need to set your nation first using !setnation <name>.")
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
    @commands.has_permissions(administrator=True)
    async def adminreset(self, ctx, member: discord.Member):
        """Admin only: Reset a user's skill tree and bonus stats."""
        await self.config.user(member).unlocked_skills.set([])
        await self.config.user(member).bonus_stats.set({"insight": 0, "instinct": 0, "faith": 0, "allegiance": 0, "good": 0, "evil": 0, "gems": 0})
        await ctx.send(f"{member.display_name}'s skills and bonuses have been reset.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def admingems(self, ctx, member: discord.Member, amount: int):
        """Admin only: Add bonus gems to a user."""
        bonus = await self.config.user(member).bonus_stats()
        bonus["gems"] += amount
        await self.config.user(member).bonus_stats.set(bonus)
        await ctx.send(f"Added {amount} Gems to {member.display_name}.")

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

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def uploadchallenges(self, ctx):
        """Upload a JSON list of normal adventure challenges."""
        if not ctx.message.attachments:
            return await ctx.send("Please attach a JSON file.")
        attachment = ctx.message.attachments[0]
        try:
            data = await attachment.read()
            challenges = json.loads(data.decode("utf-8"))
            await self.config.guild(ctx.guild).set_raw("challenges", value=challenges)
            await ctx.send("✅ Challenges uploaded!")
        except Exception as e:
            await ctx.send(f"❌ Failed to load challenges: {e}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def uploadbosses(self, ctx):
        """Upload a JSON list of boss challenges."""
        if not ctx.message.attachments:
            return await ctx.send("Please attach a JSON file.")
        attachment = ctx.message.attachments[0]
        try:
            data = await attachment.read()
            bosses = json.loads(data.decode("utf-8"))
            await self.config.guild(ctx.guild).set_raw("bosses", value=bosses)
            await ctx.send("✅ Bosses uploaded!")
        except Exception as e:
            await ctx.send(f"❌ Failed to load bosses: {e}")

    @commands.command()
    async def startadventure(self, ctx):
        """Begin an interactive adventure. Click to roll when you're ready."""
        import random
        from discord.ui import View, Button

        user = ctx.author
        stats = await self.config.user(user).base_stats()
        bonus = await self.config.user(user).bonus_stats()
        total_gems = stats["gems"] + bonus["gems"]

        stats["gems"] = 0
        bonus["gems"] = 0
        await self.config.user(user).base_stats.set(stats)
        await self.config.user(user).bonus_stats.set(bonus)

        normal_challenges = await self.config.guild(ctx.guild).get_raw("challenges", default=[])
        boss_challenges = await self.config.guild(ctx.guild).get_raw("bosses", default=[])

        if not normal_challenges or not boss_challenges:
            return await ctx.send("❌ No challenges or bosses uploaded! Admins must upload some using `!uploadchallenges` and `!uploadbosses`.")

        log = []
        challenge_number = 0
        base_difficulty = 5
        stop_adventure = False

        while not stop_adventure:
            challenge_number += 1
            is_boss = challenge_number % 5 == 0
            difficulty = base_difficulty + challenge_number

            if is_boss:
                challenge = random.choice(boss_challenges)
                score = sum([
                    abs(stats["insight_vs_instinct"] + bonus.get("insight", 0) - bonus.get("instinct", 0)),
                    abs(stats["faith_vs_allegiance"] + bonus.get("faith", 0) - bonus.get("allegiance", 0)),
                    abs(stats["good_vs_evil"] + bonus.get("good", 0) + bonus.get("evil", 0))
                ])

                class BossView(View):
                    def __init__(self):
                        super().__init__(timeout=30)
                        self.message = None

                    async def on_timeout(self):
                        nonlocal stop_adventure
                        stop_adventure = True
                        roll = random.randint(1, 20)
                        total = roll + score
                        log.append(f"⏱️ Timeout! Boss {challenge['name']} — Rolled {total}, needed {difficulty}. Defeated!\n")
                        result = "You were defeated."
                        timeout_embed = discord.Embed(
                            title=f"🧠 Boss: {challenge['name']} (Timeout)",
                            description=f"{challenge['desc']} 🎲 Auto-roll: {roll} + {score} = **{total}** **{result}**",
                            color=discord.Color.red()
                        )
                        if self.message:
                            await self.message.edit(embed=timeout_embed, view=None)
                        self.message = None

                    @discord.ui.button(label="Face the Boss", style=discord.ButtonStyle.red)
                    async def roll_button(self, interaction: discord.Interaction, button: Button):
                        if interaction.user.id != user.id:
                            await interaction.response.send_message("Only the adventurer may roll.", ephemeral=True)
                            return
                        roll = random.randint(1, 20)
                        total = roll + score
                        if total < difficulty:
                            log.append(f"❌ Boss {challenge['name']} — Rolled {total}, needed {difficulty}. Defeated!\n")
                            result = "You were defeated."
                            nonlocal stop_adventure
                            stop_adventure = True
                        else:
                            log.append(f"✅ Boss {challenge['name']} — Rolled {total}, survived!\n")
                            result = "You survived the boss!"
                        new_embed = discord.Embed(
                            title=f"🧠 Boss: {challenge['name']}",
                            description=f"{challenge['desc']} 🎲 You rolled {roll} + {score} = **{total}** **{result}**",
                            color=discord.Color.red()
                        )
                        await interaction.response.edit_message(embed=new_embed, view=None)
                        self.stop()

                embed = discord.Embed(
                    title=f"🧠 Boss Challenge #{challenge_number}: {challenge['name']}",
                    description=f"{challenge['desc']} Click below to attempt this boss (Difficulty: {difficulty})",
                    color=discord.Color.red()
                )
                view = BossView()
                view.message = view.message = await ctx.send(embed=embed, view=view)
                await view.wait()

            else:
                challenge = random.choice(normal_challenges)
                dual = challenge["dual_stat"]
                pos, neg = challenge["pos_stat"], challenge["neg_stat"]
                score = abs(stats[dual] + bonus.get(pos, 0) - bonus.get(neg, 0))

                class ChallengeView(View):
                    def __init__(self):
                        super().__init__(timeout=30)
                        self.message = None

                    async def on_timeout(self):
                        nonlocal stop_adventure
                        stop_adventure = True
                        roll = random.randint(1, 20)
                        total = roll + score
                        log.append(f"⏱️ Timeout! {challenge['name']} — Rolled {total}, needed {difficulty}. Failed.\n")
                        result = "You failed this challenge."
                        timeout_embed = discord.Embed(
                            title=f"⚔️ {challenge['name']} (Timeout)",
                            description=f"{challenge['desc']} 🎲 Auto-roll: {roll} + {score} = **{total}** **{result}**",
                            color=discord.Color.orange()
                        )
                        if self.message:
                            await self.message.edit(embed=timeout_embed, view=None)

                    @discord.ui.button(label="Take the Challenge", style=discord.ButtonStyle.green)
                    async def roll_button(self, interaction: discord.Interaction, button: Button):
                        if interaction.user.id != user.id:
                            await interaction.response.send_message("Only the adventurer may roll.", ephemeral=True)
                            return
                        roll = random.randint(1, 20)
                        total = roll + score
                        if total < difficulty:
                            log.append(f"❌ {challenge['name']} — Rolled {total}, needed {difficulty}. Failed.\n")
                            result = "You failed this challenge."
                            nonlocal stop_adventure
                            stop_adventure = True
                        else:
                            log.append(f"✅ {challenge['name']} — Rolled {total}, success!\n")
                            result = "You succeeded!"
                        new_embed = discord.Embed(
                            title=f"⚔️ {challenge['name']}",
                            description=f"{challenge['desc']} 🎲 You rolled {roll} + {score} = **{total}** **{result}**",
                            color=discord.Color.orange()
                        )
                        await interaction.response.edit_message(embed=new_embed, view=None)
                        self.stop()

                embed = discord.Embed(
                    title=f"⚔️ Challenge #{challenge_number}: {challenge['name']}",
                    description=f"{challenge['desc']} Click below to take this challenge (Difficulty: {difficulty})",
                    color=discord.Color.orange()
                )
                view = ChallengeView()
                await ctx.send(embed=embed, view=view)
                await view.wait()
                    
        reward = challenge_number * 3
        bonus["gems"] += reward
        await self.config.user(user).bonus_stats.set(bonus)

        view = AdventureLogView(log, reward)
        view.message = await ctx.send(embed=view.get_embed(), view=view)



class AdventureLogView(View):
    def __init__(self, entries, reward, per_page=5):
        super().__init__(timeout=60)
        self.entries = entries
        self.page = 0
        self.per_page = per_page
        self.reward = reward
        self.message = None
        self.update_buttons()
    
    async def interaction_check(self, interaction: discord.Interaction):
        return True  # Optional: restrict to ctx.author
    
    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)
    
    async def interaction_callback(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "prev":
            self.page -= 1
        elif interaction.data["custom_id"] == "next":
            self.page += 1
            self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    def get_embed(self):
        start = self.page * self.per_page
        end = start + self.per_page
        embed = discord.Embed(
            title="📜 Final Adventure Log",
            description="\n\n".join(self.entries[start:end]),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"You earned {self.reward} Gems! | Page {self.page + 1} of {(len(self.entries) - 1) // self.per_page + 1}")
        return embed
    
    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.grey, row=0)
    async def prev(self, interaction: discord.Interaction, button: Button):
        await self.interaction_callback(interaction)
    
    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.grey, row=0)
    async def next(self, interaction: discord.Interaction, button: Button):
        await self.interaction_callback(interaction)
    
   
