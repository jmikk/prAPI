import discord
from redbot.core import commands, Config, checks
import aiohttp
import xmltodict
import re
import asyncio
import random
import time

# --- Persistent View for Refreshing ---

class MarketRefreshButton(discord.ui.View):
    def __init__(self, cog, nation: str, user_color: discord.Color, cards_data: list):
        """
        cards_data shape: [
            {"card_id": str, "season": str, "price": str, "link": str, "name": str, "category": str}, ...
        ]
        """
        super().__init__(timeout=None) # Keeps button active until bot restarts
        self.cog = cog
        self.nation = nation
        self.user_color = user_color
        self.cards_data = cards_data

    @discord.ui.button(label="Refresh Listings", style=discord.ButtonStyle.secondary, custom_id="cm_refresh_btn", emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Acknowledge immediately to prevent ephemeral timeouts
        await interaction.response.defer(ephemeral=True)

        if self.cog._market_lock.locked():
            await interaction.followup.send("⏳ The market pipeline is currently busy. Please try again shortly.", ephemeral=True)
            return

        async with self.cog._market_lock:
            estimated_seconds = len(self.cards_data) * 5
            await interaction.followup.send(f"🔄 Refreshing listings. Estimated completion in {estimated_seconds} seconds...", ephemeral=True)
            
            valid_cards = []
            headers = {"User-Agent": f"CardMarketBot (Running by Main Nation: {self.nation})"}

            for idx, card in enumerate(self.cards_data):
                url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+markets;cardid={card['card_id']};season={card['season']}"
                
                try:
                    async with self.cog.session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            # If individual API fails, retain card temporarily to avoid accidental deletions
                            valid_cards.append(card)
                            continue
                        xml_data = await resp.text()
                        parsed = xmltodict.parse(xml_data)
                        card_xml = parsed.get("CARD", {})
                except Exception:
                    valid_cards.append(card)
                    continue

                # Safely inspect the markets block
                markets_block = card_xml.get("MARKETS")
                has_matching_ask = False

                if markets_block and "MARKET" in markets_block:
                    market_entries = markets_block["MARKET"]
                    # xmltodict packs a single child element as a dict, multiples as a list
                    if isinstance(market_entries, dict):
                        market_entries = [market_entries]

                    for entry in market_entries:
                        entry_type = entry.get("TYPE", "").lower()
                        entry_nation = entry.get("NATION", "").lower().replace(" ", "_")
                        try:
                            # Normalize floating-point strings for precise comparisons (e.g., "2" vs "2.00")
                            entry_price = float(entry.get("PRICE", -1))
                            target_price = float(card["price"])
                        except ValueError:
                            entry_price = entry.get("PRICE")
                            target_price = card["price"]

                        # Check if the listing nation and ask price match your listing parameters
                        if entry_type == "ask" and entry_nation == self.nation.lower() and entry_price == target_price:
                            has_matching_ask = True
                            # Update MV while checking
                            card["market_value"] = card_xml.get("MARKET_VALUE", card.get("market_value", "N/A"))
                            break

                if has_matching_ask:
                    valid_cards.append(card)

                # Queue delay matching NationStates API rate-limit etiquette
                if idx < len(self.cards_data) - 1:
                    await asyncio.sleep(5)

            # Update tracked metadata reference
            self.cards_data = valid_cards

            # If all cards have sold/cleared, delete original embed message
            if not self.cards_data:
                try:
                    await interaction.message.delete()
                except discord.NotFound:
                    pass
                return

            # Rebuild embed fields with updated list items
            display_nation = self.nation.replace("_", " ").title()
            new_embed = discord.Embed(title=f"{display_nation} selling:", color=self.user_color)

            for card in self.cards_data:
                emoji = self.cog.rarity_emojis.get(card["category"], "🎴")
                field_name = f"{emoji} {card['name']}: {card['link']}"
                field_value = (
                    f"ID:\n"
                    f"Season:\n"
                    f"**MV:** {card.get('market_value', 'N/A')}\n"
                    f"Price:"
                )
                new_embed.add_field(name=field_name, value=field_value, inline=False)

            try:
                await interaction.message.edit(embed=new_embed, view=self)
            except discord.NotFound:
                pass


# --- Cog Definition ---

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
        self._market_lock = asyncio.Lock()

        self.rarity_emojis = {
            "common": "<:PikaCommon:769581815643111486>",
            "uncommon": "<:PikaUC:769581778616451102>",
            "rare": "<:PikaRare:769581832508801024>",
            "ultra-rare": "<:PikaUR:769581799931641876>",
            "epic": "<:PikaEpic:769674361643991070>",
            "legendary": "<:PikaCards:769701349662654485>"
        }

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
    @commands.has_any_role("Moderation", "Moderator", "Mod")
    async def ban_user(self, ctx: commands.Context, user: discord.User):
        """Bans a user globally from using any Card Market commands."""
        async with self.config.banned_users() as banned:
            if user.id not in banned:
                banned.append(user.id)
                await ctx.send(f"🚫 {user.mention} has been added to the ad-ban list.")
            else:
                await ctx.send("This user is already banned.")

    @commands.command(name="remove_user_from_banned_list_for_ads")
    @commands.has_any_role("Moderation", "Moderator", "Mod")
    async def unban_user(self, ctx: commands.Context, user: discord.User):
        """Unbans a user globally, allowing them to use Card Market commands again."""
        async with self.config.banned_users() as banned:
            if user.id in banned:
                banned.remove(user.id)
                await ctx.send(f"✅ {user.mention} has been removed from the ad-ban list.")
            else:
                await ctx.send("This user is not currently banned.")

    @commands.command(name="cardmarket_force_unlock")
    @commands.has_any_role("Moderation", "Moderator", "Mod")
    async def force_unlock(self, ctx: commands.Context):
        """Manually releases the global API processing lock if it gets stuck."""
        if self._market_lock.locked():
            self._market_lock.release()
            await ctx.send("🔓 The global market queue lock has been manually cleared.")
        else:
            await ctx.send("The market queue lock is not currently active.")

    # --- Core Listing Command ---

    @commands.command(name="list")
    async def list_cards(self, ctx: commands.Context, *args):
        """List up to 10 cards to the global market.
        Format can mixed: [link] [price] [link] [link] [price]...
        """
        nation = await self.get_or_reg_nation(ctx)
        if not nation:
            return

        if not args:
            return await ctx.send("Please provide at least one card link. Example: `$list <link> <price>`")

        pairs = []
        i = 0
        while i < len(args):
            token = args[i]
            if re.search(r"card=\d+.*season=\d+", token):
                link = token
                price = "-"
                if i + 1 < len(args):
                    next_token = args[i + 1]
                    if not re.search(r"card=\d+.*season=\d+", next_token):
                        price = next_token
                        i += 1
                pairs.append((link, price))
            i += 1
        
        if len(pairs) > 10:
            return await ctx.send("❌ Command rejected. You can only list a maximum of 10 cards at a time to protect the server queue.")

        if not pairs:
            return await ctx.send("❌ Malformed arguments. No valid card links could be isolated from your text request.")

        if self._market_lock.locked():
            return await ctx.send("⏳ The market pipeline is currently busy processing another user's request. Please try again shortly.")

        async with self._market_lock:
            estimated_seconds = len(pairs) * 5
            target_timestamp = int(time.time() + estimated_seconds)
            
            await ctx.send(f"⏳ Processing {len(pairs)} items. Estimated completion: <t:{target_timestamp}:R>.")

            grouped_cards = {}
            channels_dict = await self.config.channels()

            for idx, (link, price) in enumerate(pairs):
                match = re.search(r"card=(\d+).*season=(\d+)", link)
                if not match:
                    continue

                card_id, season = match.group(1), match.group(2)
                url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={card_id};season={season}"
                headers = {"User-Agent": f"CardMarketBot (Running by Main Nation: {nation})"}

                async with self.session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        await ctx.send(f"⚠️ NS API threw an error for Card {card_id} (Status code: {resp.status})")
                        continue
                    xml_data = await resp.text()

                try:
                    parsed = xmltodict.parse(xml_data)
                    card_info = parsed.get("CARD")
                except Exception:
                    await ctx.send(f"❌ Error decoding returned data for Card ID {card_id}.")
                    continue

                if not card_info:
                    await ctx.send(f"❌ Card data not found for ID {card_id} (Season {season}). Skipping...")
                    if idx < len(pairs) - 1:
                        await asyncio.sleep(5)
                    continue

                category = card_info.get("CATEGORY", "").lower().replace(" ", "")
                card_name = card_info.get("NAME", f"Card {card_id}")
                market_value = card_info.get("MARKET_VALUE", "N/A")

                if category not in grouped_cards:
                    grouped_cards[category] = []

                # Append custom data dict structure designed for button components
                grouped_cards[category].append({
                    "card_id": card_id,
                    "season": season,
                    "price": price,
                    "link": link,
                    "name": card_name,
                    "category": category,
                    "market_value": market_value
                })

                if idx < len(pairs) - 1:
                    await asyncio.sleep(5)

            # --- Seed-Locked Color Generator ---
            random.seed(ctx.author.id)
            user_hex_color = random.randint(0, 0xFFFFFF)
            user_color = discord.Color(user_hex_color)
            random.seed()

            # --- Single Embed & View Dispatch System ---
            for category, cards_list in grouped_cards.items():
                target_channel_id = channels_dict.get(category)
                target_channel = self.bot.get_channel(target_channel_id)

                if not target_channel:
                    await ctx.send(f"Unable to route category items ({category}). Target channel is unconfigured.")
                    continue

                display_nation = nation.replace("_", " ").title()
                embed = discord.Embed(title=f"{display_nation} selling:", color=user_color)

                for card in cards_list:
                    emoji = self.rarity_emojis.get(category, "🎴")
                    field_name = f"{emoji} {card['name']}: {card['link']}"
                    field_value = (
                        f"ID:\n"
                        f"Season:\n"
                        f"MV:\n"
                        f"Price:"
                    )
                    embed.add_field(name=field_name, value=field_value, inline=False)

                # Initialize custom refresh button view mapped with the tracked items
                view = MarketRefreshButton(self, nation, user_color, cards_list)

                try:
                    await target_channel.send(embed=embed, view=view)
                except discord.Forbidden:
                    await ctx.send(f"I don't have permissions to send messages into <#{target_channel_id}>!")

            await ctx.send("✅ Finished processing and grouping your listings!")

    async def get_or_reg_nation(self, ctx):
        return await self._get_or_reg_nation(ctx)
