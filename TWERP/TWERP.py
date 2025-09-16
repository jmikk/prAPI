import discord
from discord import ChannelType
from redbot.core import commands, Config
from redbot.core.bot import Red
import aiohttp


def _append_thread_query(webhook_url: str, thread_id: int | None) -> str:
    """Return webhook execute URL with ?wait=true and optional thread_id."""
    sep = "&" if "?" in webhook_url else "?"
    url = f"{webhook_url}{sep}wait=true"
    if thread_id is not None:
        url += f"&thread_id={thread_id}"
    return url


class PaginationView(discord.ui.View):
    def __init__(self, items: list, interaction: discord.Interaction, title: str):
        super().__init__(timeout=180)
        self.items = items
        self.interaction = interaction
        self.title = title
        self.page = 0
        self.message = None

    def get_embed(self):
        """Generate the current embed based on the page number."""
        embed = discord.Embed(title=self.title)
        item = self.items[self.page]
        name = item.get("name", "Unnamed")
        pfp = item.get("pfp_url", discord.Embed.Empty)
        owner = item.get("owner")
        embed.add_field(name=name, value=f"[Avatar Link]({pfp})" if pfp else "No avatar set")
        if pfp:
            embed.set_thumbnail(url=pfp)
        footer = f"Page {self.page + 1}/{len(self.items)}"
        if owner:
            footer += f": {owner}"
        embed.set_footer(text=footer)
        return embed

    async def send_initial_message(self):
        """Send the initial message."""
        embed = self.get_embed()
        self.message = await self.interaction.response.send_message(embed=embed, view=self)

    async def update_embed(self, interaction: discord.Interaction):
        """Update the embed when navigating pages."""
        embed = self.get_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the previous page."""
        await interaction.response.defer()
        if self.page > 0:
            self.page -= 1
            await self.update_embed(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the next page."""
        await interaction.response.defer()
        if self.page < len(self.items) - 1:
            self.page += 1
            await self.update_embed(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the pagination view."""
        await interaction.response.defer()
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass
        self.stop()


class CharacterSelectView(discord.ui.View):
    def __init__(self, cog, characters, interaction):
        super().__init__(timeout=180)
        self.add_item(CharacterSelect(cog, characters, interaction))


class CharacterSelect(discord.ui.Select):
    def __init__(self, cog, characters, interaction):
        self.cog = cog
        self.interaction = interaction
        options = [
            discord.SelectOption(label=char_name, value=char_name)
            for char_name in characters.keys()
        ]
        super().__init__(placeholder="Select a character...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        """Trigger the modal after a character is selected."""
        try:
            character_name = self.values[0]
            characters = await self.cog.config.user(interaction.user).characters()
            character_info = characters[character_name]
            webhook, thread_id = await self.cog._get_webhook_and_thread(interaction.channel)

            if webhook:
                modal = TWERPModal(self.cog, character_name, webhook, interaction, character_info, thread_id)
                await interaction.response.send_modal(modal)
            else:
                await interaction.response.send_message("Failed to retrieve or create a webhook.", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)


class TWERPModal(discord.ui.Modal, title="Enter your message here"):
    def __init__(self, cog, character_name, webhook, interaction, character_info, thread_id=None):
        super().__init__(title="Enter your message here")
        self.cog = cog
        self.character_name = character_name
        self.webhook = webhook
        self.thread_id = thread_id
        self.interaction = interaction
        self.character_info = character_info

        self.message = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.paragraph,
            placeholder="Enter your message here...",
            required=True,
            max_length=2000
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        """Send the message via the webhook when the modal is submitted."""
        try:
            async with aiohttp.ClientSession() as session:
                webhook_url = _append_thread_query(self.webhook.url, self.thread_id)
                combined_name = f"{self.character_info['name']} ({interaction.user.name})"
                json_data = {
                    "content": self.message.value,
                    "username": combined_name,
                    "avatar_url": self.character_info["pfp_url"],
                    "allowed_mentions": {"parse": ["users"]}  # blocks @everyone/@here
                }
                await session.post(webhook_url, json=json_data)
            await interaction.response.defer()  # close modal silently
        except discord.errors.InteractionResponded:
            pass
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)


class OneShotModal(discord.ui.Modal, title="Speak once as a custom character"):
    def __init__(self, cog, webhook, interaction, display_name: str, pfp_url: str, thread_id=None):
        super().__init__(title="Enter your message here")
        self.cog = cog
        self.webhook = webhook
        self.thread_id = thread_id
        self.interaction = interaction
        self.display_name = display_name
        self.pfp_url = pfp_url

        self.message = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.paragraph,
            placeholder="Enter your message here...",
            required=True,
            max_length=2000
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            async with aiohttp.ClientSession() as session:
                webhook_url = _append_thread_query(self.webhook.url, self.thread_id)
                combined_name = f"{self.display_name} ({interaction.user.name})"
                json_data = {
                    "content": self.message.value,
                    "username": combined_name,
                    "avatar_url": self.pfp_url,
                    "allowed_mentions": {"parse": ["users"]}
                }
                await session.post(webhook_url, json=json_data)
            await interaction.response.defer()
        except discord.errors.InteractionResponded:
            pass
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)


class TWERP(commands.Cog):
    """Create characters and speak as them via webhooks. Supports forum threads and one-off messages."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=23456789648)
        self._init_config()

    def _init_config(self):
        if not hasattr(self.config.GUILD, "allowed_channels"):
            self.config.register_guild(allowed_channels=[])
        if not hasattr(self.config.USER, "credits"):
            self.config.register_user(credits=0)
        if not hasattr(self.config.USER, "completed_personal_projects"):
            self.config.register_user(completed_personal_projects={})
        if not hasattr(self.config.USER, "characters"):
            self.config.register_user(characters={})
        if not hasattr(self.config.GUILD, "NPCS"):
            self.config.register_guild(NPCS={})

    async def cog_load(self):
        await self.bot.tree.sync()
        print("All slash commands synced.")

    async def cog_unload(self):
        commands_to_remove = [
            self.create_character, self.delete_character, self.select_character,
            self.create_npc, self.delete_npc, self.select_npc,
            self.list_characters, self.list_npcs, self.list_all_characters,
            self.oneshot
        ]
        for cmd in commands_to_remove:
            try:
                if self.bot.tree.get_command(cmd.name):
                    self.bot.tree.remove_command(cmd.name)
            except Exception:
                pass

    # ---------- Autocomplete ----------
    async def character_name_autocomplete(self, interaction: discord.Interaction, current: str):
        characters = await self.config.user(interaction.user).characters()
        if not characters:
            return []
        return [
            discord.app_commands.Choice(name=char_name, value=char_name)
            for char_name in characters.keys() if current.lower() in char_name.lower()
        ]

    async def NPC_name_autocomplete(self, interaction: discord.Interaction, current: str):
        npcs = await self.config.guild(interaction.guild).NPCS()
        if not npcs:
            return []
        return [
            discord.app_commands.Choice(name=char_name, value=char_name)
            for char_name in npcs.keys() if current.lower() in char_name.lower()
        ]

    # ---------- Character CRUD ----------
    @discord.app_commands.command(name="create_character", description="Create a character with a name and profile picture URL.")
    async def create_character(self, interaction: discord.Interaction, name: str, pfp_url: str):
        try:
            characters = await self.config.user(interaction.user).characters() or {}
            if len(characters) >= 20:
                await interaction.response.send_message("You already have 20 characters! Delete one before creating a new one.", ephemeral=True)
                return

            characters[name] = {"pfp_url": pfp_url, "name": name}
            await self.config.user(interaction.user).characters.set(characters)
            await interaction.response.send_message(f"Character **{name}** created!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="create_npc", description="Create an NPC with a name and profile picture URL.")
    async def create_npc(self, interaction: discord.Interaction, name: str, pfp_url: str):
        try:
            npcs = await self.config.guild(interaction.guild).NPCS() or {}
            if len(npcs) >= 25:
                await interaction.response.send_message("You already have 25 NPCs! Delete one before creating a new one.", ephemeral=True)
                return

            npcs[name] = {"pfp_url": pfp_url, "name": name}
            await self.config.guild(interaction.guild).NPCS.set(npcs)
            await interaction.response.send_message(f"NPC **{name}** created!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="delete_character", description="Delete one of your characters.")
    @discord.app_commands.autocomplete(name=character_name_autocomplete)
    async def delete_character(self, interaction: discord.Interaction, name: str):
        try:
            characters = await self.config.user(interaction.user).characters() or {}
            if name not in characters:
                await interaction.response.send_message(f"Character **{name}** not found.", ephemeral=True)
                return

            del characters[name]
            await self.config.user(interaction.user).characters.set(characters)
            await interaction.response.send_message(f"Character **{name}** deleted.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="delete_npc", description="Delete an NPC.")
    @discord.app_commands.autocomplete(name=NPC_name_autocomplete)
    async def delete_npc(self, interaction: discord.Interaction, name: str):
        try:
            npcs = await self.config.guild(interaction.guild).NPCS() or {}
            if name not in npcs:
                await interaction.response.send_message(f"NPC **{name}** not found.", ephemeral=True)
                return

            del npcs[name]
            await self.config.guild(interaction.guild).NPCS.set(npcs)
            await interaction.response.send_message(f"NPC **{name}** deleted.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    # ---------- Speak as saved character / NPC ----------
    @discord.app_commands.command(name="speak", description="Speak as one of your characters.")
    @discord.app_commands.autocomplete(character=character_name_autocomplete)
    async def select_character(self, interaction: discord.Interaction, character: str, message: str | None = None):
        try:
            characters = await self.config.user(interaction.user).characters() or {}

            if not characters:
                await interaction.response.send_message("You don't have any characters created.", ephemeral=True)
                return
            if character not in characters:
                await interaction.response.send_message(f"Character `{character}` not found.", ephemeral=True)
                return

            character_info = characters[character]
            webhook, thread_id = await self._get_webhook_and_thread(interaction.channel)
            if webhook:
                if message is None:
                    modal = TWERPModal(self, character, webhook, interaction, character_info, thread_id)
                    await interaction.response.send_modal(modal)
                else:
                    await self.send_as_character(interaction, character, character_info, message, webhook, thread_id)
            else:
                await interaction.response.send_message("Failed to retrieve or create a webhook.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="speak_npc", description="Speak as a server NPC.")
    @discord.app_commands.autocomplete(character=NPC_name_autocomplete)
    async def select_npc(self, interaction: discord.Interaction, character: str, message: str | None = None):
        try:
            npcs = await self.config.guild(interaction.guild).NPCS() or {}

            if not npcs:
                await interaction.response.send_message("There are no NPCs in this server.", ephemeral=True)
                return
            if character not in npcs:
                await interaction.response.send_message(f"NPC `{character}` not found.", ephemeral=True)
                return

            character_info = npcs[character]
            webhook, thread_id = await self._get_webhook_and_thread(interaction.channel)
            if webhook:
                if message is None:
                    modal = TWERPModal(self, character, webhook, interaction, character_info, thread_id)
                    await interaction.response.send_modal(modal)
                else:
                    await self.send_as_character(interaction, character, character_info, message, webhook, thread_id)
            else:
                await interaction.response.send_message("Failed to retrieve or create a webhook.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    async def send_as_character(self, interaction, character_name, character_info, message, webhook, thread_id=None):
        """Helper to send a message as a character using the webhook (works in text channels and forum threads)."""
        try:
            async with aiohttp.ClientSession() as session:
                webhook_url = _append_thread_query(webhook.url, thread_id)
                combined_name = f"{character_info['name']} ({interaction.user.name})"
                json_data = {
                    "content": message,
                    "username": combined_name,
                    "avatar_url": character_info["pfp_url"],
                    "allowed_mentions": {"parse": ["users"]}
                }
                await session.post(webhook_url, json=json_data)
            await interaction.response.send_message(f"Message sent as **{character_name}**!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    # ---------- One-shot speak ----------
    @discord.app_commands.command(name="oneshot", description="Speak once as a custom name + avatar (no save).")
    async def oneshot(self, interaction: discord.Interaction, name: str, pfp_url: str, message: str | None = None):
        """
        One-off 'speak': uses a supplied display name + pfp URL for a single message.
        If message is omitted, opens a modal like /speak.
        """
        try:
            webhook, thread_id = await self._get_webhook_and_thread(interaction.channel)
            if not webhook:
                await interaction.response.send_message("Failed to retrieve or create a webhook.", ephemeral=True)
                return

            if message is None:
                modal = OneShotModal(self, webhook, interaction, name, pfp_url, thread_id)
                await interaction.response.send_modal(modal)
                return

            # Send immediately
            async with aiohttp.ClientSession() as session:
                webhook_url = _append_thread_query(webhook.url, thread_id)
                combined_name = f"{name} ({interaction.user.name})"
                json_data = {
                    "content": message,
                    "username": combined_name,
                    "avatar_url": pfp_url,
                    "allowed_mentions": {"parse": ["users"]}
                }
                await session.post(webhook_url, json=json_data)
            await interaction.response.send_message("One-shot message sent!", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    # ---------- Listing ----------
    @discord.app_commands.command(name="list_characters", description="List all of your characters.")
    async def list_characters(self, interaction: discord.Interaction):
        try:
            characters = await self.config.user(interaction.user).characters()
            if not characters:
                await interaction.response.send_message("You don't have any characters.", ephemeral=True)
                return

            items = [{"name": name, "pfp_url": data["pfp_url"]} for name, data in characters.items()]
            pagination_view = PaginationView(items, interaction, "Your Characters")
            await pagination_view.send_initial_message()
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="list_npcs", description="List all NPCs in the server.")
    async def list_npcs(self, interaction: discord.Interaction):
        try:
            npcs = await self.config.guild(interaction.guild).NPCS()
            if not npcs:
                await interaction.response.send_message("There are no NPCs in this server.", ephemeral=True)
                return

            items = [{"name": name, "pfp_url": data["pfp_url"]} for name, data in npcs.items()]
            pagination_view = PaginationView(items, interaction, "Server NPCs")
            await pagination_view.send_initial_message()
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="list_all_characters", description="List all characters across all users in the server.")
    async def list_all_characters(self, interaction: discord.Interaction):
        try:
            all_characters = []
            for member in interaction.guild.members:
                if member.bot:
                    continue
                chars = await self.config.user(member).characters()
                if chars:
                    all_characters += [
                        {"name": name, "pfp_url": data["pfp_url"], "owner": member.display_name}
                        for name, data in chars.items()
                    ]

            if not all_characters:
                await interaction.response.send_message("There are no characters in this server.", ephemeral=True)
                return

            pagination_view = PaginationView(all_characters, interaction, "All Characters in the Server")
            await pagination_view.send_initial_message()
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    # ---------- Admin ----------
    @commands.command(name="admin_delete_character", help="Delete a character owned by a specified user.")
    @commands.has_permissions(administrator=True)
    async def admin_delete_character(self, ctx, owner_name: str, character_name: str):
        try:
            owner = discord.utils.find(lambda m: m.name == owner_name or m.display_name == owner_name, ctx.guild.members)
            if owner is None:
                await ctx.send(f"User '{owner_name}' not found in the server.")
                return

            characters = await self.config.user(owner).characters() or {}
            if character_name not in characters:
                await ctx.send(f"Character '{character_name}' not found for user '{owner_name}'.")
                return

            del characters[character_name]
            await self.config.user(owner).characters.set(characters)
            await ctx.send(f"Character '{character_name}' owned by '{owner_name}' has been deleted.")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @discord.app_commands.command(name="buy_me_a_coffee", description="A friendly thank-you note.")
    async def buy_me_a_coffee(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Thanks for thinking of me! I code for fun and don’t accept payments, but I appreciate it. "
            "If you’re financially able and willing, you can buy me a coffee: https://ko-fi.com/9003s",
            ephemeral=True
        )

    # ---------- Webhook helpers (forum-aware) ----------
    async def _get_webhook_and_thread(self, channel: discord.abc.GuildChannel | discord.Thread):
        """
        Get or create a webhook usable for posting in `channel`.
        - Text channel: create/use webhook in that channel.
        - Forum thread: create/use webhook on parent forum channel, return thread_id for execution.
        """
        try:
            thread_id = None
            target_channel = channel

            if isinstance(channel, discord.Thread):
                thread_id = channel.id
                # For forum threads, the webhook must live on the parent (a Forum channel)
                if channel.parent and channel.parent.type == ChannelType.forum:
                    target_channel = channel.parent

            webhooks = await target_channel.webhooks()
            bot_webhook = discord.utils.get(webhooks, name="CharacterWebhook")

            if not bot_webhook:
                try:
                    bot_webhook = await target_channel.create_webhook(name="CharacterWebhook")
                except discord.Forbidden:
                    return None, None

            return bot_webhook, thread_id
        except Exception:
            return None, None
