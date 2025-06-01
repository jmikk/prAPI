import discord
from discord.ui import View, Button, Modal, TextInput
from redbot.core import commands, Config
import datetime
import traceback

class EditModal(Modal, title="Edit Your Post"):
    def __init__(self, cog, author, thread, message_id):
        super().__init__()
        self.cog = cog
        self.author = author
        self.thread = thread
        self.message_id = message_id
        self.new_content = TextInput(label="New content", style=discord.TextStyle.paragraph)
        self.add_item(self.new_content)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            class FakeCtx:
                def __init__(self, author, channel, guild):
                    self.author = author
                    self.channel = channel
                    self.guild = guild

            fake_ctx = FakeCtx(self.author, self.thread, self.thread.guild)
            await self.cog.edit_post(
                fake_ctx,
                message_id=self.message_id,
                new_content=self.new_content.value,
                respond_func=lambda msg: interaction.followup.send(msg, ephemeral=True)
            )
        except Exception:
            try:
                await self.author.send(f"EditModal error:\n```{traceback.format_exc()}```")
            except Exception:
                pass

class DisForumDaBest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            watched_forum=None,
            mod_locker=None,
            edit_threads={},
            edit_counts={}
        )

    @commands.command()
    @commands.guild_only()
    async def set_forum_watch(self, ctx, forum: discord.ForumChannel):
        await self.config.guild(ctx.guild).watched_forum.set(forum.id)
        await ctx.send(f"Set watched forum to: {forum.name}")

    @commands.command()
    @commands.guild_only()
    async def set_mod_locker(self, ctx, forum: discord.ForumChannel):
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

        embed = discord.Embed(
            title=f"{message.author.display_name} posted:",
            description=message.content,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Posted on • Use the button below to update your message")
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)

        files = [await a.to_file() for a in message.attachments]

        view = View()
        button = Button(label="Edit Post", style=discord.ButtonStyle.primary, custom_id=f"edit_button:{message.id}")

        async def button_callback(interaction: discord.Interaction):
            if interaction.user.id != message.author.id:
                return await interaction.response.send_message("You can only edit your own posts.", ephemeral=True)
            await interaction.response.send_modal(EditModal(self, interaction.user, interaction.channel, message.id))

        button.callback = button_callback
        view.add_item(button)

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
    async def edit_post(self, ctx, message_id: int = None, *, new_content: str = None, respond_func=None):
        if respond_func is None:
            respond_func = ctx.send

        if not isinstance(ctx.channel, discord.Thread):
            return await respond_func("This command must be used in a thread.")

        thread = ctx.channel

        if message_id:
            try:
                target_msg = await thread.fetch_message(message_id)
            except discord.NotFound:
                target_msg = await self.find_user_embed_post(thread, ctx.author)
                if not target_msg:
                    return await respond_func("That message could not be found.")
        else:
            target_msg = await self.find_user_embed_post(thread, ctx.author)
            if not target_msg:
                return await respond_func("No tracked post found.")

        if not new_content or new_content.strip() == "":
            return await respond_func("Cannot update post with empty content.")

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
                    name=f"Edit History: {ctx.author.display_name} @ {datetime.datetime.utcnow().isoformat(timespec='seconds')}",
                    content="Original post log"
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
        await respond_func("Post updated and original archived.")
