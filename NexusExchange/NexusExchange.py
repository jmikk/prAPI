from redbot.core import commands, Config
import discord

class NexusExchange(commands.Cog):
    """A Master Currency Exchange Cog for The Wellspring"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=345678654456, force_registration=True)
        self.config.register_guild(
            master_currency_name="Wellspring Coins",
            exchange_rates={},  # {"currency_name": {"config_id": int, "rate": float}}
        )
        self.config.register_member(master_balance=0)

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def debug_currency(self, ctx, currency_name: str):
        """Check what keys exist for a given currency's config."""
        currency_name = currency_name.lower().replace(" ", "_")
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()

        if currency_name not in exchange_rates:
            await ctx.send(f"Currency `{currency_name}` does not exist.")
            return

        config_id = exchange_rates[currency_name]["config_id"]
        mini_currency_config = Config.get_conf(None, identifier=config_id, force_registration=True)

        try:
            stored_data = await mini_currency_config.all_members()
        except Exception as e:
            await ctx.send(f"Error retrieving data: {e}")
            return

        if not stored_data:
            await ctx.send(f"No data found for `{currency_name}`.")
            return

        keys = list(stored_data.keys())
        keys_preview = ", ".join(str(key) for key in keys[:10])  # Show up to 10 keys for preview

        embed = discord.Embed(title=f"Debugging `{currency_name}`", color=discord.Color.red())
        embed.add_field(name="Stored Member Keys", value=f"Total: {len(keys)}\nPreview: {keys_preview}", inline=False)
        
        await ctx.send(embed=embed)
