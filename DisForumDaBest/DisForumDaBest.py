import discord
from redbot.core import commands, Config
import datetime

class DisForumDaBest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            watched_forum=None,
            mod_locker=None,
            edit_threads={}  # message_id -> thread_id
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
        embed.set_footer(text="Posted on")
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)

        files = [await a.to_file() for a in message.attachments]
        await message.channel.send(embed=embed, files=files)

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
    async def edit_post(self, ctx, *, new_content: str):
        """Edit your last post in the thread."""
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.send("This command must be used in a thread.")

        thread = ctx.channel
        target_msg = await self.find_user_embed_post(thread, ctx.author)
        if not target_msg:
            return await ctx.send("No tracked post found.")

        original_embed = target_msg.embeds[0]
        msg_id = target_msg.id

        mod_locker_id = await self.config.guild(ctx.guild).mod_locker()
        mod_locker = ctx.guild.get_channel(mod_locker_id)
        thread_id_map = await self.config.guild(ctx.guild).edit_threads()

        if isinstance(mod_locker, discord.ForumChannel):
            if str(msg_id) in thread_id_map:
                # Reuse thread
                locker_thread_id = thread_id_map[str(msg_id)]
                locker_thread = mod_locker.get_thread(locker_thread_id)
                if locker_thread is None:
                    locker_thread = await mod_locker.fetch_thread(locker_thread_id)
                await locker_thread.send(embed=original_embed)
            else:
                # Create new thread and save it
                new_thread = await mod_locker.create_thread(
                    name=f"Edit History: {ctx.author.display_name} @ {datetime.datetime.utcnow().isoformat(timespec='seconds')}",
                    content="Original version of the post before edit:",
                    embed=original_embed
                )
                await self.config.guild(ctx.guild).edit_threads.set_raw(str(msg_id), value=new_thread.id)

        # Edit embed
        new_embed = original_embed.copy()
        new_embed.description = new_content
        new_embed.timestamp = datetime.datetime.utcnow()
        new_embed.set_footer(text="Edited on")

        await target_msg.edit(embed=new_embed)
        await ctx.send("Post updated and original archived.")
