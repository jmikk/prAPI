import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
import json
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
        self.clear_items()
        unlocked = await self.cog.config.user(self.ctx.author).unlocked_skills()
        path_key = f"{self.category}/{'/'.join(self.path)}"

        if path_key not in unlocked:
            async def unlock_callback(interaction):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                    return
                try:
                    result = await self.cog.unlock_skill(self.ctx.author, self.category, self.path)
                    await interaction.response.send_message(result, ephemeral=True)
                    await self.setup()
                    await interaction.message.edit(embed=self.get_embed(), view=self)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

            button = Button(label="Unlock", style=discord.ButtonStyle.green)
            button.callback = unlock_callback
            self.add_item(button)

        children_items = list(self.skill.get("children", {}).items())
        page_size = 5
        start = self.page * page_size
        end = start + page_size

        for key, child in children_items[start:end]:
            async def nav_callback(interaction, k=key):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                    return
                self.path.append(k)
                self.skill = self._get_node()
                self.page = 0
                await self.setup()
                await interaction.message.edit(embed=self.get_embed(), view=self)

            label = child.get("name", key)
            path_key = f"{self.category}/{'/'.join(self.path + [key])}"
            emoji = "✅" if path_key in unlocked else "🔒"
            button = Button(label=f"{emoji} {label}", style=discord.ButtonStyle.blurple)
            button.callback = nav_callback
            self.add_item(button)

        if len(self.path) > 1:
            async def back_callback(interaction):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("Only the command user can use this button.", ephemeral=True)
                    return
                self.path.pop()
                self.skill = self._get_node()
                self.page = 0
                await self.setup()
                await interaction.message.edit(embed=self.get_embed(), view=self)

            back = Button(label="⬅️ Back", style=discord.ButtonStyle.grey)
            back.callback = back_callback
            self.add_item(back)

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
