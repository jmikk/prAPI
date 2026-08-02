from redbot.core import Config, commands
import discord


class SimpleEconomy(commands.Cog):
  """A message-activity economy cog using a custom user config."""

  def __init__(self, bot):
    self.bot = bot
    # Guild-wide settings (toggles, payouts, blacklist)
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
        "blacklisted_channels": [],  # List of channel IDs excluded from payouts
    }

    default_user = {
        "master_balance": 0.0,  # User's balance stored in their config
    }

    self.config.register_guild(**default_guild)
    self.config_gold.register_user(**default_user)

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
      async with self.config_gold.user(author).master_balance() as balance:
        balance += amount

  # --- Balance Command ---

  @commands.command(name="balance", aliases=["bal"])
  async def balance(
      self, ctx: commands.Context, target: discord.Member = None
  ):
    """Check your or another user's balance."""
    target = target or ctx.author
    bal = await self.config_gold.user(target).master_balance()
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

  @seconset.command(name="resetall")
  @commands.is_owner()
  async def seconset_resetall(self, ctx: commands.Context):
    """Fully reset and wipe every config attached to this cog (Global/Guild/User data)."""
    await self.config.clear_all()
    await self.config_gold.clear_all()
    await ctx.send(
        "⚠️ **All configurations and user balances** for SimpleEconomy have"
        " been completely wiped and reset to default."
    )

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
        name="Blacklisted Channels", value=blacklist_str, inline=False
    )

    await ctx.send(embed=embed)


async def setup(bot):
  await bot.add_cog(SimpleEconomy(bot))
