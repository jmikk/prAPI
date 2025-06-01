import discord
from discord.ui import View, Button, Modal, TextInput
from redbot.core import commands, Config
import datetime

class EditModal(Modal, title="Edit Your Post"):
    def __init__(self, message_id):
        super().__init__()
        self.message_id = message_id
        self.new_content = TextInput(label="New content", style=discord.TextStyle.paragraph)
        self.add_item(self.new_content)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        cog = ctx.bot.get_cog("DisForumDaBest")
        if cog:
            await cog.edit_post(ctx, message_id=self.message_id, new_content=self.new_content.value)

class DisForumDaBest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            watched_forum=None,
            mod_locker=None,
            edit_threads={},  # message_id -> thread_id
            edit_counts={}    # message_id -> int (version count)
        )

    @commands.command()
    @commands.guild_only()
    async def set_forum_watch(self, ctx, forum: discord.ForumChannel):
        """Set the forum to watch."""
        await self.config.guild(ctx.guild).watched_forum.set(forum.id)
        await ctx.send(f"Set watched forum to: {forum.name}")

    @commands.command()
    @commands.guild_only()
    async def set_mod_locker(self, ctx, forum: discord.ForumChannel):
        """Set the mod locker forum."""
        await self.config.guild(ctx.guild).mod_locker.set(forum.id)
        await ctx.send(f"Set mod locker to: {forum.name}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not isinstance(message.channel, discord.Thread):
            return

        guild = message.guild
        watched_id = await self.config.guild(guild).watched_forum()
        if message.channel.parent_id != watched_id:
            return

        # Repost as embed
        embed = discord.Embed(
            title=f"{message.author.display_name} posted:",
            description=message.content,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Posted on • Use `/edit_post` in this thread to update your message")
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)

        files = [await a.to_file() for a in message.attachments]

        view = View()
        view.add_item(Button(label="Edit Post", style=discord.ButtonStyle.primary, custom_id=f"edit:{message.author.id}:{message.id}"))

        await message.channel.send(embed=embed, files=files, view=view)
        await message.delete()

    async def find_user_embed_post(self, thread: discord.Thread, user: discord.Member):
        async for message in thread.history(limit=100):
            if message.author.id != self.bot.user.id:
                continue
            if not message.embeds:
                continue
            embed = message.embeds[0]
            if embed.title and embed.title.startswith(f"{user.display_name} posted:"):
                if embed.author and embed.author.name == user.display_name:
                    return message
        return None

    @commands.command()
    async def edit_post(self, ctx, message_id: int = None, *, new_content: str = None):
        """Edit your last post in the thread."""
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("This command must be used in a thread.")

        thread = ctx.channel
        if not message_id:
            target_msg = await self.find_user_embed_post(thread, ctx.author)
        else:
            target_msg = await thread.fetch_message(message_id)

        if not target_msg:
            return await ctx.send("No tracked post found.")

        original_embed = target_msg.embeds[0]
        msg_id = str(target_msg.id)

        mod_locker_id = await self.config.guild(ctx.guild).mod_locker()
        mod_locker = ctx.guild.get_channel(mod_locker_id)
        thread_id_map = await self.config.guild(ctx.guild).edit_threads()
        edit_count_map = await self.config.guild(ctx.guild).edit_counts()

        version_number = edit_count_map.get(msg_id, 1)

        if isinstance(mod_locker, discord.ForumChannel):
            if msg_id in thread_id_map:
                locker_thread_id = thread_id_map[msg_id]
                locker_thread = mod_locker.get_thread(locker_thread_id) or await mod_locker.fetch_thread(locker_thread_id)
                await locker_thread.send(
                    content=f"**Version {version_number} on {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}**",
                    embed=original_embed
                )
            else:
                new_thread = await mod_locker.create_thread(
                    name=f"Edit History: {ctx.author.display_name} @ {datetime.datetime.utcnow().isoformat(timespec='seconds')}"
                )
                await new_thread.send(
                    content=f"**Original version (V1) on {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}**",
                    embed=original_embed
                )
                await self.config.guild(ctx.guild).edit_threads.set_raw(msg_id, value=new_thread.id)

        await self.config.guild(ctx.guild).edit_counts.set_raw(msg_id, value=version_number + 1)

        new_embed = original_embed.copy()
        new_embed.description = new_content
        new_embed.timestamp = datetime.datetime.utcnow()
        new_embed.set_footer(text="Edited on • Use `/edit_post` in this thread to update again")

        await target_msg.edit(embed=new_embed)
        await ctx.send("Post updated and original archived.")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.type == discord.InteractionType.component:
            return
        if not interaction.data.get("custom_id", "").startswith("edit:"):
            return

        _, user_id, message_id = interaction.data["custom_id"].split(":")
        if str(interaction.user.id) != user_id:
            return await interaction.response.send_message("You can only edit your own posts.", ephemeral=True)

        await interaction.response.send_modal(EditModal(message_id=int(message_id)))
