import discord
from redbot.core import commands, Config, checks
import aiohttp
import xmltodict
import re

class CardMarket(commands.Cog):
    """NationStates Card Market Listing Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=98723498172394, force_registration=True)
        
        # Setup global settings for global market cross-server compatibility
        default_global = {
            "banned_users": [],
            "channels": {
                "common": None,
                "uncommon": None,
                "rare": None,
                "ultra-rare": None,
                "epic": None,
                "legendary": None
            }
        }
        default_user = {
            "main_nation": None
        }
        
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Global check: Enforce the custom ad ban list across all commands in this cog
        banned = await self.config.banned_users()
        if ctx.author.id in banned:
            await ctx.send("You are permanently banned from using Card Market commands due to ad violations.", ephemeral=True)
            return False
        return True

    async def _get_or_reg_nation(self, ctx: commands.Context) -> str:
        """Helper to fetch or prompt user for their main nation."""
        nation = await self.config.user(ctx.author).main_nation()
        if nation:
            return nation

        await ctx.send("Welcome! Before making your first listing, please reply with the name of your **Main Cards Nation**:")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=60.0)
            cleaned_nation = msg.content.strip().lower().replace(" ", "_")
            await self.config.user(ctx.author).main_nation.set(cleaned_nation)
            await ctx.send(f"✅ Main nation saved as `{cleaned_nation}`. Processing your layout now...")
            return cleaned_nation
        except asyncio.TimeoutError:
            await ctx.send("❌ Registration timed out. Please run the command again.")
            return None

    # --- Configuration Commands ---

    @commands.group(name="cardmarketset", aliases=["cmset"])
    @checks.admin_or_permissions(manage_guild=True)
    async def _set(self, ctx: commands.Context):
        """Configure card market channels."""
        pass

    @_set.command(name="common")
    async def _common(self, ctx, channel: discord.TextChannel):
        await self.config.channels.common.set(channel.id)
        await ctx.tick()

    @_set.command(name="uncommon")
    async def _uncommon(self, ctx, channel: discord.TextChannel):
        await self.config.channels.uncommon.set(channel.id)
        await ctx.tick()

    @_set.command(name="rare")
    async def _rare(self, ctx, channel: discord.TextChannel):
        await self.config.channels.rare.set(channel.id)
        await ctx.tick()

    @_set.command(name="ultrarare")
    async def _ultrarare(self, ctx, channel: discord.TextChannel):
        await self.config.channels.ultrarare.set(channel.id)
        await ctx.tick()

    @_set.command(name="epic")
    async def _epic(self, ctx, channel: discord.TextChannel):
        await self.config.channels.epic.set(channel.id)
        await ctx.tick()

    @_set.command(name="legendary")
    async def _legendary(self, ctx, channel: discord.TextChannel):
        await self.config.channels.legendary.set(channel.id)
        await ctx.tick()

    @commands.command(name="add_user_to_banned_list_for_ads")
    @checks.admin_or_permissions(manage_guild=True)
    async def ban_user(self, ctx: commands.Context, user: discord.User):
        """Bans a user globally from using any Card Market commands."""
        async with self.config.banned_users() as banned:
            if user.id not in banned:
                banned.append(user.id)
                await ctx.send(f"🚫 {user.mention} has been added to the ad-ban list.")
            else:
                await ctx.send("This user is already banned.")

    # --- Core Listing Command ---

    @commands.command(name="list")
    async def list_cards(self, ctx: commands.Context, *args):
        """List up to 10 cards to the global market.
        Format: [link] [price] [link] [price]...
        Example: !list https://www.nationstates.net/page=deck/card=509581/season=3 50.00
        """
        nation = await self.get_or_reg_nation(ctx)
        if not nation:
            return

        if not args or len(args) % 2 != 0:
            return await ctx.send("Make sure you match every link with a price! Example: `$list <link> <price>`")

        # Gather tuples of pairs up to 10
        pairs = list(zip(args[0::2], args[1::2]))[:10]
        if not pairs:
            return await ctx.send("No items were parsed.")

        await ctx.send(f"Processing {len(pairs)} items... Please stay patient.")

        # Process each card
        for link, price in pairs:
            # Extract card id and season using regex
            match = re.search(r"card=(\d+).*season=(\d+)", link)
            if not match:
                await ctx.send(f"Skipping invalid URL schema: <{link}>")
                continue

            card_id, season = match.group(1), match.group(2)
            
            # Request down to NS API
            url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={card_id};season={season}"
            headers = {"User-Agent": f"CardMarketBot (Running by Main Nation: {nation})"}

            async with self.session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    await ctx.send(f"NS API threw an error for Card {card_id} (Status code: {resp.status})")
                    continue
                xml_data = await resp.text()

            try:
                # Convert XML mapping to dictionary cleanly
                parsed = xmltodict.parse(xml_data)
                card_info = parsed.get("CARD", {})
            except Exception:
                await ctx.send(f"Error reading returned data for Card ID {card_id}.")
                continue

            category = card_info.get("CATEGORY", "").lower().replace(" ", "")
            card_name = card_info.get("NAME", f"Card {card_id}")
            market_value = card_info.get("MARKET_VALUE", "N/A")

            # Route to respective config channels
            channels_dict = await self.config.channels()
            target_channel_id = channels_dict.get(category)
            target_channel = self.bot.get_channel(target_channel_id)

            if not target_channel:
                await ctx.send(f"Unable to route card `{card_name}` ({category}). Target channel is unconfigured.")
                continue

            # Construct dynamic Custom Embed
            embed = discord.Embed(
                title=f"{ctx.author.name} selling:",
                color=discord.Color.blue()
            )
            
            field_value = (
                f"**ID:** {card_id}\n"
                f"**Season:** {season}\n"
                f"**MV:** {market_value}\n"
                f"**Price:** {price}"
            )
            
            embed.add_field(
                name=f"🎴 {card_name}: {link}",
                value=field_value,
                inline=False
            )
            
            # Grab default flag element if available
            if "FLAG" in card_info:
                flag_url = f"https://www.nationstates.net/images/cards/{card_info['FLAG']}"
                embed.set_thumbnail(url=flag_url)

            try:
                await target_channel.send(embed=embed)
            except discord.Forbidden:
                await ctx.send(f"I don't have permissions to send messages into <#{target_channel_id}>!")

        await ctx.send("Finished processing your listings!")

    # Manual internal routing fallback wrapper override
    async def get_or_reg_nation(self, ctx):
        import asyncio
        return await self._get_or_reg_nation(ctx)
