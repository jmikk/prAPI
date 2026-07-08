import discord
from redbot.core import commands, Config, checks
import aiohttp
import xmltodict
import re
import asyncio
import random
import time

# --- Helper function to parse card markets XML ---
def parse_market_data(xml_text):
    """
    Parses the card markets API response.
    Returns a dict with:
      - 'market_value': str
      - 'lowest_ask': float or None (lowest numerical ask across the whole market)
      - 'category': str (Extracted safely from markets endpoint if present)
    """
    try:
        parsed = xmltodict.parse(xml_text)
        card_xml = parsed.get("CARD", {})
    except Exception:
        return {"market_value": "N/A", "lowest_ask": None, "category": "common", "name": "N/A"}

    mv = card_xml.get("MARKET_VALUE", "N/A")
    category = card_xml.get("CATEGORY", "common").lower().replace(" ", "")
    lowest_ask = None

    markets_block = card_xml.get("MARKETS")
    if markets_block and "MARKET" in markets_block:
        market_entries = markets_block["MARKET"]
        if isinstance(market_entries, dict):
            market_entries = [market_entries]

        for entry in market_entries:
            entry_type = entry.get("TYPE", "").lower()

            try:
                price_val = float(entry.get("PRICE", -1))
            except ValueError:
                continue

            # Identify the absolute lowest open ask on the live market
            if entry_type == "ask" and price_val >= 0:
                if lowest_ask is None or price_val < lowest_ask:
                    lowest_ask = price_val

    return {"market_value": mv, "lowest_ask": lowest_ask, "category": category}


def build_field_value(card: dict) -> str:
    """
    Builds the embed field body for a single card, filling in the
    actual card id, season, market value, and price.
    """
    return (
        f"ID: {card['card_id']}\n"
        f"Season: {card['season']}\n"
        f"MV: {card['market_value']}\n"
        f"Price: {card['price']}"
    )


# --- Persistent View for Refreshing ---

class MarketRefreshButton(discord.ui.View):
    def __init__(self, cog, nation: str, user_color: discord.Color, cards_data: list):
        super().__init__(timeout=None)
        self.cog = cog
        self.nation = nation
        self.user_color = user_color
        self.cards_data = cards_data

    @discord.ui.button(label="Refresh Listings", style=discord.ButtonStyle.secondary, custom_id="cm_refresh_btn", emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if self.cog._market_lock.locked():
            await interaction.followup.send("⏳ The market pipeline is currently busy. Please try again shortly.", ephemeral=True)
            return

        async with self.cog._market_lock:
            estimated_seconds = len(self.cards_data) * 5
            target_timestamp = int(time.time() + estimated_seconds)

            status_msg = await interaction.followup.send(
                f"🔄 Refreshing listings. Estimated completion: <t:{target_timestamp}:R>...",
                ephemeral=True
            )

            valid_cards = []
            headers = {"User-Agent": f"CardMarketBot (Running by Main Nation: {self.nation})"}

            for idx, card in enumerate(self.cards_data):
                url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+markets;cardid={card['card_id']};season={card['season']}"

                try:
                    async with self.cog.session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            valid_cards.append(card)
                            continue
                        xml_data = await resp.text()
                except Exception:
                    valid_cards.append(card)
                    continue

                result = parse_market_data(xml_data)
                current_lowest_ask = result["lowest_ask"]

                # If there are no asks left on the market, the card sold out
                if current_lowest_ask is not None:
                    initial_ask = card.get("initial_ask")

                    # Condition: If the current lowest ask is higher than the baseline, remove the field entirely
                    if initial_ask is not None and current_lowest_ask > initial_ask:
                        if idx < len(self.cards_data) - 1:
                            await asyncio.sleep(5)
                        continue

                    card["market_value"] = result["market_value"]
                    card["price"] = f"{current_lowest_ask:.2f}"
                    valid_cards.append(card)

                if idx < len(self.cards_data) - 1:
                    await asyncio.sleep(5)

            self.cards_data = valid_cards

            if not self.cards_data:
                try:
                    await interaction.message.delete()
                except discord.NotFound:
                    pass
                await status_msg.edit(content="✅ All tracked items have successfully sold or their prices shifted upward!")
                return

            # Rebuild Embed
            display_nation = self.nation.replace("_", " ").title()
            new_embed = discord.Embed(title=f"{display_nation} selling:", color=self.user_color)

            for card in self.cards_data:
                emoji = self.cog.rarity_emojis.get(card["category"], "🎴")
                field_name = f"{emoji} {card['name']}: {card['link']}"
                field_value = build_field_value(card)
                new_embed.add_field(name=field_name, value=field_value, inline=False)

            current_timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            new_embed.set_footer(text=f"Last updated: {current_timestamp}")

            try:
                await interaction.message.edit(embed=new_embed, view=self)
            except discord.NotFound:
                pass

            await status_msg.edit(content="✅ Finished processing and grouping your updated listings!")


# --- Cog Definition ---

class CardMarket(commands.Cog):
    """NationStates Card Market Listing Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=98723498172394, force_registration=True)

        default_global = {
            "banned_users": [],
            "channels": {
                "common": None, "uncommon": None, "rare": None, "ultra-rare": None, "epic": None, "legendary": None
            },
            "webhooks": {
                "common": None, "uncommon": None, "rare": None, "ultra-rare": None, "epic": None, "legendary": None
            }
        }
        default_user = {"main_nation": None}

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

    # --- Webhook Configuration Commands ---

    async def _set_webhook(self, ctx: commands.Context, category: str, url: str = None):
        if url is None or url.lower() in ("none", "clear", "remove"):
            await self.config.webhooks.set_raw(category, value=None)
            await ctx.send(f"🗑️ Webhook cleared for **{category}**. Listings will use the configured channel only.")
            return

        if not re.match(r"^https://(?:discord|discordapp)\.com/api/webhooks/\d+/.+", url):
            await ctx.send("❌ That doesn't look like a valid Discord webhook URL.")
            return

        await self.config.webhooks.set_raw(category, value=url)
        await ctx.tick()

    @_set.group(name="webhook")
    async def _webhookset(self, ctx: commands.Context):
        """Configure card market webhooks per rarity.

        If a webhook is set for a rarity, listings in that rarity will be
        sent to both the configured channel (with the refresh button) and
        the webhook (plain embed, no button). Pass `none` to clear a webhook.
        """
        pass

    @_webhookset.command(name="common")
    async def _webhook_common(self, ctx, url: str = None):
        await self._set_webhook(ctx, "common", url)

    @_webhookset.command(name="uncommon")
    async def _webhook_uncommon(self, ctx, url: str = None):
        await self._set_webhook(ctx, "uncommon", url)

    @_webhookset.command(name="rare")
    async def _webhook_rare(self, ctx, url: str = None):
        await self._set_webhook(ctx, "rare", url)

    @_webhookset.command(name="ultrarare")
    async def _webhook_ultrarare(self, ctx, url: str = None):
        await self._set_webhook(ctx, "ultra-rare", url)

    @_webhookset.command(name="epic")
    async def _webhook_epic(self, ctx, url: str = None):
        await self._set_webhook(ctx, "epic", url)

    @_webhookset.command(name="legendary")
    async def _webhook_legendary(self, ctx, url: str = None):
        await self._set_webhook(ctx, "legendary", url)

    async def _send_via_webhook(self, url: str, embed: discord.Embed, username: str):
        """Sends an embed to a Discord webhook URL. Returns (success, error_message)."""
        try:
            webhook = discord.Webhook.from_url(url, session=self.session)
            await webhook.send(embed=embed, username=username)
        except discord.NotFound:
            return False, "the webhook no longer exists (was it deleted?)"
        except discord.Forbidden:
            return False, "I don't have permission to post to that webhook"
        except ValueError:
            return False, "the stored webhook URL is malformed"
        except Exception as e:
            return False, str(e)
        return True, None

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
        Format supports complete links spaced out.
        """
        nation = await self._get_or_reg_nation(ctx)
        if not nation:
            return

        if not args:
            return await ctx.send("Please provide at least one card link. Example: `$list <link>`")

        # Robust, case-insensitive check matching both 'card=' and 'cardid=' URL structures
        links = [token for token in args if re.search(r"card(?:_?id)?=(\d+).*season=(\d+)", token, re.IGNORECASE)]

        if len(links) > 10:
            return await ctx.send("❌ Command rejected. You can only list a maximum of 10 cards at a time.")

        if not links:
            return await ctx.send("❌ Malformed arguments. No valid card ID and Season profiles detected.")

        if self._market_lock.locked():
            return await ctx.send("⏳ The market pipeline is currently busy processing another user's request. Please try again shortly.")

        async with self._market_lock:
            estimated_seconds = len(links) * 5
            target_timestamp = int(time.time() + estimated_seconds)

            status_message = await ctx.send(f"⏳ Processing {len(links)} items. Estimated completion: <t:{target_timestamp}:R>.")

            grouped_cards = {}
            channels_dict = await self.config.channels()
            webhooks_dict = await self.config.webhooks()

            for idx, link in enumerate(links):
                match = re.search(r"card(?:_?id)?=(\d+).*season=(\d+)", link, re.IGNORECASE)
                if not match:
                    continue

                card_id, season = match.group(1), match.group(2)

                url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+markets;cardid={card_id};season={season}"
                headers = {"User-Agent": f"CardMarketBot (Running by Main Nation: {nation})"}

                async with self.session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        await ctx.send(f"⚠️ NS API threw an error for Card {card_id} (Status code: {resp.status})")
                        continue
                    xml_data = await resp.text()

                result = parse_market_data(xml_data)
                category = result["category"]
                card_name = result["name"] if result.get("name") not in (None, "N/A") else f"Card {card_id}"

                if category not in grouped_cards:
                    grouped_cards[category] = []

                lowest_ask_val = result["lowest_ask"]
                price_str = f"{lowest_ask_val:.2f}" if lowest_ask_val is not None else "-"

                grouped_cards[category].append({
                    "card_id": card_id,
                    "season": season,
                    "price": price_str,
                    "initial_ask": lowest_ask_val,
                    "link": link,
                    "name": card_name,
                    "category": category,
                    "market_value": result["market_value"]
                })

                if idx < len(links) - 1:
                    await asyncio.sleep(5)

            # --- Seed-Locked Color Generator ---
            random.seed(ctx.author.id)
            user_hex_color = random.randint(0, 0xFFFFFF)
            user_color = discord.Color(user_hex_color)
            random.seed()

            # --- Single Embed & View Dispatch System ---
            for category, cards_list in grouped_cards.items():
                target_channel_id = channels_dict.get(category)
                target_channel = self.bot.get_channel(target_channel_id) if target_channel_id else None
                webhook_url = webhooks_dict.get(category)

                if not target_channel and not webhook_url:
                    await ctx.send(f"Unable to route category items ({category}). No channel or webhook is configured.")
                    continue

                display_nation = nation.replace("_", " ").title()
                embed = discord.Embed(title=f"{display_nation} selling:", color=user_color)

                for card in cards_list:
                    emoji = self.rarity_emojis.get(category, "🎴")
                    field_name = f"{emoji} {card['name']}: {card['link']}"
                    field_value = build_field_value(card)
                    embed.add_field(name=field_name, value=field_value, inline=False)

                current_timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                embed.set_footer(text=f"Last updated: {current_timestamp}")

                # Channel version keeps the interactive refresh button
                if target_channel:
                    view = MarketRefreshButton(self, nation, user_color, cards_list)
                    try:
                        await target_channel.send(embed=embed, view=view)
                    except discord.Forbidden:
                        await ctx.send(f"I don't have permissions to send messages into <#{target_channel_id}>!")

                # Webhook version is a plain embed with no button
                if webhook_url:
                    success, err = await self._send_via_webhook(webhook_url, embed.copy(), display_nation)
                    if not success:
                        await ctx.send(f"⚠️ Failed to post **{category}** listing to its configured webhook: {err}")

            await status_message.edit(content="✅ Finished processing and grouping your listings!")

    async def get_or_reg_nation(self, ctx):
        return await self._get_or_reg_nation(ctx)
