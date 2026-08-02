from redbot.core import Config, commands
import discord


class SimpleEconomy(commands.Cog):
  """A message-activity economy cog using a custom user config."""

  def __init__(self, bot):
    self.bot = bot
    # Guild-wide settings (toggles, payouts, blacklist, starting balance)
    self.config = Config.get_conf(
        self, identifier=9876543210, force_registration=True
    )
    # User-specific storage for balances using your requested line
    self.config_gold = Config.get_conf(
        None, identifier=345678654456, force_registration=False
    )

    default_guild = {
        "master_balance": True,  # Toggle for enabling/disabling the payout system
        "payout_amount": 5.0,  # Amount of currency given per message
        "starting_balance": 0.0,  # Default balance given to users when initialized
        "blacklisted_channels": [],  # List of channel IDs excluded from payouts
    }

    default_user = {
        "master_balance": None,  # Will use starting_balance if None
    }

    self.config.register_guild(**default_guild)
    self.config_gold.register_user(**default_user)

  async def get_user_balance(self, guild: discord.Guild, user: discord.abc.User) -> float:
    """Helper to fetch balance, falling back to guild starting balance if uninitialized."""
    bal = await self.config_gold.user(user).master_balance()
    if bal is None:
      bal = await self.config.guild(guild).starting_balance()
    return bal

  @commands.Cog.listener()
  async def on_message_without_command(self, message: discord.Message):
    if not message.guild or message.author.bot:
      return

    guild = message.guild
    author = message.author

    # Check if master_balance system is enabled for this guild
    master_enabled = await self.config.guild(guild).master_balance()
    if not master_enabled:
      return

    # Check if channel is blacklisted
    blacklisted = await self.config.guild(guild).blacklisted_channels()
    if message.channel.id in blacklisted:
      return

    # Fetch payout amount and add to the user's config master_balance
    amount = await self.config.guild(guild).payout_amount()
    if amount > 0:
      current_bal = await self.get_user_balance(guild, author)
      await self.config_gold.user(author).master_balance.set(current_bal + amount)

  # --- Balance Command ---

  @commands.command(name="balance", aliases=["bal"])
  async def balance(
      self, ctx: commands.Context, target: discord.Member = None
  ):
    """Check your or another user's balance."""
    target = target or ctx.author
    bal = await self.get_user_balance(ctx.guild, target)
    await ctx.send(f"**{target.display_name}'s** Balance: **{bal}** gold")

  # --- Administration & Adjustment Commands ---

  @commands.group()
  @commands.admin_or_permissions(manage_guild=True)
  async def seconset(self, ctx: commands.Context):
    """Configure the SimpleEconomy settings."""
    if ctx.invoked_subcommand is None:
      await ctx.send_help()

  @seconset.command(name="toggle")
  async def seconset_toggle(self, ctx: commands.Context):
    """Toggle the master_balance payout system on or off."""
    current = await self.config.guild(ctx.guild).master_balance()
    new_state = not current
    await self.config.guild(ctx.guild).master_balance.set(new_state)
    status = "Enabled" if new_state else "Disabled"
    await ctx.send(
        f"**master_balance** system has been set to: **{status}** (`{new_state}`)"
    )

  @seconset.command(name="amount")
  async def seconset_amount(self, ctx: commands.Context, amount: float):
    """Set the currency payout amount per message."""
    if amount < 0:
      await ctx.send("Payout amount cannot be negative.")
      return
    await self.config.guild(ctx.guild).payout_amount.set(amount)
    await ctx.send(f"Per-message payout amount updated to **{amount} gold**.")

  @seconset.command(name="startingbal")
  async def seconset_startingbal(self, ctx: commands.Context, amount: float):
    """Set the default starting balance for users."""
    if amount < 0:
      await ctx.send("Starting balance cannot be negative.")
      return
    await self.config.guild(ctx.guild).starting_balance.set(amount)
    await ctx.send(f"Default starting balance updated to **{amount} gold**.")

  @seconset.command(name="blacklist")
  async def seconset_blacklist(
      self, ctx: commands.Context, channel: discord.TextChannel
  ):
    """Add or remove a channel from the payout blacklist."""
    async with self.config.guild(ctx.guild).blacklisted_channels() as channels:
      if channel.id in channels:
        channels.remove(channel.id)
        await ctx.send(
            f"Removed {channel.mention} from the blacklisted channels."
        )
      else:
        channels.append(channel.id)
        await ctx.send(f"Added {channel.mention} to the blacklisted channels.")

  @seconset.command(name="setbal")
  @commands.admin_or_permissions(administrator=True)
  async def seconset_setbal(
      self, ctx: commands.Context, target: discord.Member, amount: float
  ):
    """Manually set a user's master_balance."""
    if amount < 0:
      await ctx.send("Balance cannot be negative.")
      return
    await self.config_gold.user(target).master_balance.set(amount)
    await ctx.send(
        f"Set **{target.display_name}'s** master_balance to **{amount} gold**."
    )

  @seconset.command(name="pay")
  @commands.admin_or_permissions(manage_guild=True)
  async def seconset_pay(
      self, ctx: commands.Context, target: str, amount: float
  ):
    """Pay an individual user or the entire server ('all') a specific amount of gold."""
    if amount <= 0:
      await ctx.send("Payout amount must be greater than zero.")
      return

    if target.lower() == "all":
      async with ctx.typing():
        for member in ctx.guild.members:
          if member.bot:
            continue
          current_bal = await self.get_user_balance(ctx.guild, member)
          await self.config_gold.user(member).master_balance.set(current_bal + amount)
      await ctx.send(f"Successfully paid **{amount} gold** to all non-bot members in the server!")
    else:
      converter = commands.MemberConverter()
      try:
        member = await converter.convert(ctx, target)
      except commands.BadArgument:
        await ctx.send("Could not find that member. Use a mention/ID or type `all`.")
        return

      current_bal = await self.get_user_balance(ctx.guild, member)
      await self.config_gold.user(member).master_balance.set(current_bal + amount)
      await ctx.send(f"Successfully paid **{amount} gold** to **{member.display_name}**.")

  @seconset.command(name="resetall")
  @commands.is_owner()
  async def seconset_resetall(self, ctx: commands.Context):
    """Fully reset and wipe ALL configuration datasets the bot has access to."""
    class ConfirmView(discord.ui.View):
      def __init__(self, author: discord.User):
        super().__init__(timeout=30)
        self.value = None
        self.author = author

      @discord.ui.button(label="Confirm Wipe", style=discord.ButtonStyle.danger)
      async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
          await interaction.response.send_message("This isn't your confirmation prompt.", ephemeral=True)
          return
        self.value = True
        self.stop()

      @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
      async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
          await interaction.response.send_message("This isn't your confirmation prompt.", ephemeral=True)
          return
        self.value = False
        self.stop()

    view = ConfirmView(ctx.author)
    msg = await ctx.send(
        "⚠️ **DANGER:** You are about to completely wipe **EVERY** config database "
        "attached to this entire bot across all cogs! This action is irreversible.\n"
        "Do you want to proceed?",
        view=view
    )

    await view.wait()

    try:
      await msg.edit(view=None)
    except discord.HTTPException:
      pass

    if view.value is True:
      async with ctx.typing():
        # Clears every single config namespace the bot utilizes globally across drivers
        await Config._driver.clear_all()
      await ctx.send("🚨 **Complete Bot Wipe Executed:** All configurations and database entries across the bot have been entirely wiped.")
    else:
      await ctx.send("Reset operation cancelled.")

  @seconset.command(name="settings")
  async def seconset_settings(self, ctx: commands.Context):
    """View current SimpleEconomy settings."""
    data = await self.config.guild(ctx.guild).all()
    status = "Enabled" if data["master_balance"] else "Disabled"

    blacklist_mentions = [
        ctx.guild.get_channel(cid).mention
        for cid in data["blacklisted_channels"]
        if ctx.guild.get_channel(cid)
    ]
    blacklist_str = (
        ", ".join(blacklist_mentions) if blacklist_mentions else "None"
    )

    embed = discord.Embed(
        title="SimpleEconomy Settings",
        color=discord.Color.blue(),
        timestamp=ctx.message.created_at,
    )
    embed.add_field(name="System Status", value=status, inline=False)
    embed.add_field(
        name="Payout Per Message",
        value=f"{data['payout_amount']} gold",
        inline=False,
    )
    embed.add_field(
        name="Starting Balance",
        value=f"{data['starting_balance']} gold",
        inline=False,
    )
    embed.add_field(
        name="Blacklisted Channels", value=blacklist_str, inline=False
    )

    await ctx.send(embed=embed)


async def setup(bot):
  await bot.add_cog(SimpleEconomy(bot))
