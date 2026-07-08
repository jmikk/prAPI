import discord
from redbot.core import commands, Config, checks
import aiohttp
import xmltodict
import re
import asyncio
import random
import time  # Imported to calculate epochs for the Discord timestamp

class CardMarket(commands.Cog):
    """NationStates Card Market Listing Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=98723498172394, force_registration=True)
        
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
        banned = await self.config.banned_users()
        if ctx.author.id in banned:
            await ctx.send("You are permanently banned from using Card Market commands due to ad violations.", ephemeral=True)
            return False
        return True

    async def _get_or_reg_nation(self, ctx: commands.Context) -> str:
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
        await self.config.channels.set_raw("ultra-rare", value=channel.id)
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

    @commands.command(name="remove_user_from_banned_list_for_ads")
    @checks.admin_or_permissions(manage_guild=True)
    async def unban_user(self, ctx: commands.Context, user: discord.User):
        """Unbans a user globally, allowing them to use Card Market commands again."""
        async with self.config.banned_users() as banned:
            if user.id in banned:
                banned.remove(user.id)
                await ctx.send(f"✅ {user.mention} has been removed from the ad-ban list.")
            else:
                await ctx.send("This user is not currently banned.")

    # --- Core Listing Command ---

    @commands.command(name="list")
    async def list_cards(self, ctx: commands.Context, *args):
        """List up to 10 cards to the global market.
        Format: [link] [price] [link] [price]...
        """
        nation = await self.get_or_reg_nation(ctx)
        if not nation:
            return

        if not args or len(args) % 2 != 0:
            return await ctx.send("Make sure you match every link with a price! Example: `$list <link> <price>`")

        pairs = list(zip(args[0::2], args[1::2]))[:10]
        if not pairs:
            return await ctx.send("No items were parsed.")

        # Calculate time estimate (5 seconds per item processing delay)
        estimated_seconds = len(pairs) * 5
        target_timestamp = int(time.time() + estimated_seconds)
        
        # Fancy relative discord countdown format: <t:epoch:R>
        await ctx.send(f"⏳ Processing {len(pairs)} items. Estimated completion: <t:{target_timestamp}:R>.")

        grouped_cards = {}
        channels_dict = await self.config.channels()

        for idx, (link, price) in enumerate(pairs):
            match = re.search(r"card=(\d+).*season=(\d+)", link)
            if not match:
                await ctx.send(f"Skipping invalid URL schema: <{link}>")
                continue

            card_id, season = match.group(1), match.group(2)
            
            url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={card_id};season={season}"
            headers = {"User-Agent": f"CardMarketBot (Running by Main Nation: {nation})"}

            async with self.session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    await ctx.send(f"NS API threw an error for Card {card_id} (Status code: {resp.status})")
                    continue
                xml_data = await resp.text()

            try:
                parsed = xmltodict.parse(xml_data)
                card_info = parsed.get("CARD", {})
            except Exception:
                await ctx.send(f"Error reading returned data for Card ID {card_id}.")
                continue

            category = card_info.get("CATEGORY", "").lower().replace(" ", "")
            card_name = card_info.get("NAME", f"Card {card_id}")
            market_value = card_info.get("MARKET_VALUE", "N/A")

            if category not in grouped_cards:
                grouped_cards[category] = []

            field_name = f"🎴 {card_name}: {link}"
            field_value = (
                f"**ID:** {card_id}\n"
                f"**Season:** {season}\n"
                f"**MV:** {market_value}\n"
                f"**Price:** {price}"
            )

            grouped_cards[category].append({"name": field_name, "value": field_value})

            # Rate limit guard: Wait 5 seconds before running the next query, unless it's the absolute last item
            if idx < len(pairs) - 1:
                await asyncio.sleep(5)

        # --- Seed-Locked Color Generator ---
        random.seed(ctx.author.id)
        user_hex_color = random.randint(0, 0xFFFFFF)
        user_color = discord.Color(user_hex_color)
        random.seed()

        # --- Single Embed Dispatch System ---
        for category, fields in grouped_cards.items():
            target_channel_id = channels_dict.get(category)
            target_channel = self.bot.get_channel(target_channel_id)

            if not target_channel:
                await ctx.send(f"Unable to route category items ({category}). Target channel is unconfigured.")
                continue

            display_nation = nation.replace("_", " ").title()
            
            embed = discord.Embed(
                title=f"{display_nation} selling:",
                color=user_color
            )

            for field in fields:
                embed.add_field(name=field["name"], value=field["value"], inline=False)

            try:
                await target_channel.send(embed=embed)
            except discord.Forbidden:
                await ctx.send(f"I don't have permissions to send messages into <#{target_channel_id}>!")

        await ctx.send("✅ Finished processing and grouping your listings!")

    async def get_or_reg_nation(self, ctx):
        return await self._get_or_reg_nation(ctx)
