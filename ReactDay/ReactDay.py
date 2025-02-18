from redbot.core import commands, Config, checks
import discord
import datetime

class ReactDay(commands.Cog):
    """A cog that reacts to a user's messages for one day, once per minute."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123456789)
        self.config.register_guild(react_users={})  # Stores user_id: {"emoji": str, "expires": timestamp}
        self.recently_reacted = {}  # Stores user_id: last_reacted_timestamp

    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    @commands.command()
    async def reactday(self, ctx, action: str, member: discord.Member = None, emoji: str = None):
        """Manage react-day users.

        Actions:
        - `add <user> <emoji>`: Starts reacting to their messages for 24 hours.
        - `remove <user>`: Stops reacting to their messages.
        - `list`: Shows all active users.
        """
        guild_data = await self.config.guild(ctx.guild).react_users()

        if action == "add":
            if not member or not emoji:
                return await ctx.send("Usage: `!reactday add @user :emoji:`")

            expiration = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).timestamp()
            guild_data[str(member.id)] = {"emoji": emoji, "expires": expiration}
            await self.config.guild(ctx.guild).react_users.set(guild_data)

            await ctx.send(f"✅ {member.mention} will have {emoji} added to their messages for the next 24 hours.")

        elif action == "remove":
            if not member:
                return await ctx.send("Usage: `!reactday remove @user`")

            if str(member.id) in guild_data:
                del guild_data[str(member.id)]
                await self.config.guild(ctx.guild).react_users.set(guild_data)
                await ctx.send(f"❌ Stopped reacting to messages from {member.mention}.")
            else:
                await ctx.send("That user is not in the list.")

        elif action == "list":
            if not guild_data:
                return await ctx.send("No users are currently being auto-reacted to.")
            response = "👥 **Users with auto-reactions:**\n"
            for user_id, data in guild_data.items():
                user = ctx.guild.get_member(int(user_id))
                expires_at = datetime.datetime.utcfromtimestamp(data["expires"]).strftime("%Y-%m-%d %H:%M UTC")
                response += f"- {user.mention if user else f'User {user_id}'}: {data['emoji']} (Expires: {expires_at})\n"
            await ctx.send(response)

        else:
            await ctx.send("Invalid action. Use `add`, `remove`, or `list`.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Automatically adds a reaction to messages from users in the list, once per minute."""
        if message.author.bot or not message.guild:
            return

        guild_data = await self.config.guild(message.guild).react_users()
        user_id = str(message.author.id)

        if user_id in guild_data:
            data = guild_data[user_id]
            current_time = datetime.datetime.utcnow().timestamp()

            # Check if the time has expired
            if current_time > data["expires"]:
                del guild_data[user_id]
                await self.config.guild(message.guild).react_users.set(guild_data)
                return
            
            # Check if the user has received a reaction in the last minute
            last_reacted = self.recently_reacted.get(user_id, 0)
            if current_time - last_reacted < 60:
                return  # Skip if last reaction was less than a minute ago
            
            # Add the reaction and update the timestamp
            try:
                await message.add_reaction(data["emoji"])
                self.recently_reacted[user_id] = current_time  # Update the last reaction time
            except discord.HTTPException:
                pass  # Ignore invalid emoji issues
