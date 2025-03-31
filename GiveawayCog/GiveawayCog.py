import discord
from redbot.core import commands, Config
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import random
from discord.ext import tasks

class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9006)
        self.config.register_guild(giveaway_channel=None, log_channel=None,scheduled_giveaways=[],nationname=None, password=None,)
        self.config.register_user(wins=[])
        self.config.register_global( claimed_cards=[], active_giveaways=[])
        self.session = aiohttp.ClientSession()
        self.giveaway_tasks = {}
        #self.scheduler.start()


    async def cog_load(self):
        self.scheduler.start()

    def cog_unload(self):
        self.scheduler.cancel()

    @tasks.loop(hours=12)
    async def scheduler(self):
        now = datetime.utcnow()  # ← Fix: define 'now'
        for guild in self.bot.guilds:
            scheduled = await self.config.guild(guild).scheduled_giveaways()
            updated = []
            for giveaway in scheduled:
                start_time = datetime.fromisoformat(giveaway['start_time'])
                if now >= start_time and not giveaway['started']:
                    await self.run_giveaway(giveaway, guild)
                    giveaway['started'] = True
                updated.append(giveaway)
            await self.config.guild(guild).scheduled_giveaways.set(updated)




    @commands.command()
    @commands.is_owner()
    async def schedule_giveaway(self, ctx, day: str, role: discord.Role = None, length_days: int = 2, value: str = "any"):
        """Schedule a recurring giveaway on a day of the week for a specific role and value tier."""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        if day.lower() not in days:
            return await ctx.send("Invalid day. Please choose a valid day.")

        value = value.lower()
        if value not in ["low", "mid", "high", "any"]:
            return await ctx.send("Invalid value. Choose from low, mid, high, or any.")

        next_run = self.next_weekday(datetime.utcnow(), days.index(day.lower()))
        scheduled = await self.config.guild(ctx.guild).scheduled_giveaways()
        scheduled.append({
            'day': day.lower(),
            'role_id': role.id if role else None,
            'length_days': length_days,
            'value_tier': value,
            'start_time': next_run.isoformat(),
            'started': False
        })
        await self.config.guild(ctx.guild).scheduled_giveaways.set(scheduled)
        
            
    def next_weekday(self, d, weekday):
        days_ahead = weekday - d.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return d + timedelta(days=days_ahead)

    async def run_giveaway(self, giveaway, guild):
        try:
            nnationname = await self.config.guild(guild).nationname()
            cards = await self.fetch_deck(nationname)
            legendary_cards = [c for c in cards if c["category"] == "legendary"]
    
            claimed = await self.config.claimed_cards()
            active = await self.config.active_giveaways()
            available_cards = [c for c in legendary_cards if f"{c['cardid']}_{c['season']}" not in claimed and f"{c['cardid']}_{c['season']}" not in active]
    
            if not available_cards:
                return
    
            # Sort by market value
            available_cards.sort(key=lambda x: float(x["market_value"]))
            count = len(available_cards)
            selected_card = None
    
            if giveaway["value_tier"] == "low":
                selected_card = random.choice(available_cards[:max(1, count // 4)])
            elif giveaway["value_tier"] == "mid":
                selected_card = random.choice(available_cards[count // 4 : 3 * count // 4])
            elif giveaway["value_tier"] == "high":
                selected_card = random.choice(available_cards[3 * count // 4 :])
            else:
                selected_card = random.choice(available_cards)
    
            # Mark as active
            card_key = f"{selected_card['cardid']}_{selected_card['season']}"
            active.append(card_key)
            await self.config.active_giveaways.set(active)
    
            # Fetch full card info
            card_data = await self.fetch_card_info(selected_card["cardid"], selected_card["season"])
            if not card_data:
                return
    
            # Build role
            role = guild.get_role(giveaway["role_id"]) if giveaway["role_id"] else None
            role_id = role.id if role else None
    
            # Giveaway timing
            end_time = datetime.utcnow() + timedelta(days=giveaway["length_days"])
            card_link = f"https://www.nationstates.net/page=deck/card={selected_card['cardid']}/season={selected_card['season']}"
            channel_id = await self.config.guild(guild).giveaway_channel()
            if not channel_id:
                return
            channel = guild.get_channel(channel_id)
    
            view = GiveawayButtonView(role_id, card_data, card_link, role, end_time)
            message = await channel.send(embed=view.create_embed(), view=view)
            view.message = message
    
            task = self.bot.loop.create_task(self.end_giveaway(message, view, end_time))
            self.giveaway_tasks[message.id] = task
    
            giveaway["started"] = True
    
            log_channel_id = await self.config.guild(guild).log_channel()
            log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
            if log_channel:
                await log_channel.send(f"Auto giveaway started for {card_data['name']} in {channel.mention}. Ends <t:{int(end_time.timestamp())}:R>.")
    
        except Exception as e:
            log_channel_id = await self.config.guild(guild).log_channel()
            log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
            if log_channel:
                await log_channel.send(f"Error in auto giveaway: {e}")


    async def fetch_deck(self, nationname):
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname={nationname}"
        headers = {"User-Agent": "9005"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return []
                data = await response.text()
                root = ET.fromstring(data)
                cards = []
                for card in root.find("DECK"):
                    cards.append({
                        "cardid": card.findtext("CARDID"),
                        "category": card.findtext("CATEGORY"),
                        "market_value": card.findtext("MARKET_VALUE"),
                        "season": card.findtext("SEASON")
                    })
                return cards



    async def log_error(self, ctx, error):
        log_channel_id = await self.config.guild(ctx.guild).log_channel()
        log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None
        if log_channel:
            await log_channel.send(f"Error occurred: {error}")
        await ctx.send("An error occurred. Please reach out to <@207526562331885568> for help.")

    async def end_giveaway(self, message, view, end_time):
        await discord.utils.sleep_until(end_time)
        await view.disable_all_items()
        await message.edit(view=view)
        entrants = view.get_entrants()
        if entrants:
            winner = random.choice(entrants)
            user_claims = await self.config.user(winner).wins()
            user_claims.append({
                "message_id": message.id,
                "cardid": view.card_data["cardid"],
                "season": view.card_data["season"],
                "timestamp": int(datetime.utcnow().timestamp())
            })
            await self.config.user(winner).wins.set(user_claims)
            await message.reply(f"Giveaway ended! Congratulations {winner.mention}, you won the card giveaway! Use `!claimcards <destination>` to tell Gob where to send your card.")
        else:
            await message.reply("Giveaway ended! No entrants.")

    @commands.command()
    async def claimcards(self, ctx, *, destination: str):
        try:
            user_claims = await self.config.user(ctx.author).wins()
            if not user_claims:
                return await ctx.send("You have no unclaimed giveaways.")

            useragent = "9007"
            password = await self.config.guild(ctx.guild).password()
            nationname = await self.config.guild(ctx.guild).nationname()
            if not password or not nationname:
                return await ctx.send("Nation name or password not set. Use `setnation` and `setpassword`.")

            log_channel_id = await self.config.guild(ctx.guild).log_channel()
            log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None
            x_pin = None

            for idx, claim_info in enumerate(user_claims):
                card_id = claim_info["cardid"]
                season = claim_info["season"]

                prepare_data = {
                    "nation": nationname, "c": "giftcard", "cardid": card_id, "season": season,
                    "to": destination, "mode": "prepare"
                }
                if not x_pin:
                    prepare_headers = {"User-Agent": useragent, "X-Password": password}
                else: 
                    prepare_headers = {"User-Agent": useragent, "X-Pin": x_pin}


                async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
                    prepare_text = await prepare_response.text()
                    if prepare_response.status != 200:
                        await ctx.send(f"Failed to prepare gift for card {card_id}.")
                        if log_channel:
                            await log_channel.send(f"Prepare failed for {ctx.author.mention}: {prepare_text}")
                        continue

                    token = self.parse_token(prepare_text)
                    if not token:
                        await ctx.send(f"Token missing for card {card_id}.")
                        if log_channel:
                            await log_channel.send(f"Token error for {ctx.author.mention}: {prepare_text}")
                        continue

                    if idx == 0:
                        x_pin = prepare_response.headers.get("X-Pin")
                        if not x_pin:
                            await ctx.send("X-Pin missing.")
                            if log_channel:
                                await log_channel.send("X-Pin missing in header.")
                            return

                execute_data = {
                    "nation": nationname, "c": "giftcard", "cardid": card_id, "season": season,
                    "to": destination, "mode": "execute", "token": token
                }
                execute_headers = {"User-Agent": useragent, "X-Pin": x_pin}

                async with self.session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
                    execute_text = await execute_response.text()
                    if execute_response.status != 200:
                        await ctx.send(f"Failed to send card {card_id}.")
                        if log_channel:
                            await log_channel.send(f"Send failed for {ctx.author.mention}: {execute_text}")
                        continue

                    await ctx.send(f"Sent card {card_id} (Season {season}) to {destination}.")
                    if log_channel:
                        await log_channel.send(f"Gifted card {card_id} (S{season}) to {destination} for {ctx.author.mention}.")

            await self.config.user(ctx.author).wins.set([])

        except Exception as e:
            await self.log_error(ctx, str(e))

    @commands.is_owner()
    @commands.command()
    async def setnation(self, ctx, *, nationname: str):
        await self.config.nationname.set(nationname)
        await ctx.send(f"Nation name set to: {nationname}")
    
    @commands.admin_or_permissions(administrator=True)
    @commands.command()
    async def cancelgiveaway(self, ctx, message_id: int):
        """Cancel an active giveaway by its message ID."""
        task = self.giveaway_tasks.pop(message_id, None)
        if task:
            task.cancel()
            await ctx.send(f"Giveaway with message ID {message_id} has been canceled.")
            log_channel_id = await self.config.guild(ctx.guild).log_channel()
            log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None
            if log_channel:
                await log_channel.send(f"Giveaway canceled manually for message ID {message_id}.")
        else:
            await ctx.send("No active giveaway found with that message ID.")


    @commands.is_owner()
    @commands.command()
    async def setpassword(self, ctx, *, password: str):
        await self.config.password.set(password)
        await ctx.send("Password has been set.")

    def parse_token(self, text):
        try:
            root = ET.fromstring(text)
            return root.findtext("SUCCESS")
        except ET.ParseError:
            return None

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setgiveawaychannel2(self, ctx, channel: discord.TextChannel = None):
        """Set the channel where giveaways will be posted."""
        if not channel:
            channel = ctx.channel  # Default to the channel the command was run in
    
        await self.config.guild(ctx.guild).giveaway_channel.set(channel.id)
        await ctx.send(f"Giveaway channel set to {channel.mention}.")

    
    @commands.admin_or_permissions(administrator=True)
    @commands.command()
    async def startgiveaway2(self, ctx, length_in_days: int, card_link: str, role: discord.Role = None):
        """Start a giveaway for a specific card and role."""
        try:
            channel_id = await self.config.guild(ctx.guild).giveaway_channel()
            if not channel_id:
                return await ctx.send("Giveaway channel not set. Use `setgiveawaychannel` first.")
    
            card_id, season = self.parse_card_link(card_link)
            if not card_id or not season:
                return await ctx.send("Invalid card link format.")
    
            card_data = await self.fetch_card_info(card_id, season)
            if not card_data:
                return await ctx.send("Failed to fetch card info from NationStates API.")
    
            end_time = datetime.utcnow() - timedelta(hours=5) + timedelta(days=length_in_days)
            channel = ctx.guild.get_channel(channel_id)
            role_id = role.id if role else None
    
            view = GiveawayButtonView(role_id, card_data, card_link, role, end_time)
            message = await channel.send(embed=view.create_embed(), view=view)
            view.message = message
    
            task = self.bot.loop.create_task(self.end_giveaway(message, view, end_time))
            self.giveaway_tasks[message.id] = task
    
            await ctx.send(f"Giveaway started in {channel.mention} and will end <t:{int(end_time.timestamp())}:R>.")
    
        except Exception as e:
            await self.log_error(ctx, str(e))
    
    def parse_card_link(self, link):
        try:
            parts = link.split("card=")[1].split("/")
            card_id = parts[0]
            season = parts[1].replace("season=", "")
            return card_id, season
        except (IndexError, ValueError):
            return None, None
    
    async def fetch_card_info(self, card_id, season):
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={card_id};season={season}"
        headers = {"User-Agent": "9007"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                data = await response.text()
                root = ET.fromstring(data)
                return {
                    "cardid": root.findtext("CARDID"),
                    "name": root.findtext("NAME"),
                    "season": root.findtext("SEASON"),
                    "category": root.findtext("CATEGORY"),
                    "flag": root.findtext("FLAG"),
                    "market_value": root.findtext("MARKET_VALUE")
                }
    @commands.command()
    @commands.is_owner()
    async def cancel_giveaway(self, ctx, cardid: int, season: int):
        """Cancel an active giveaway for a specific card ID and season."""
        card_key = f"{cardid}_{season}"
        active = await self.config.active_giveaways()
        if card_key in active:
            active.remove(card_key)
            await self.config.active_giveaways.set(active)
            await ctx.send(f"Giveaway for card ID {cardid} season {season} has been canceled.")
        else:
            await ctx.send("No active giveaway found for that card.")

    @commands.command()
    async def viewscheduled(self, ctx):
        scheduled = await self.config.guild(ctx.guild).scheduled_giveaways()
        if not scheduled:
            await ctx.send("No scheduled giveaways.")
            return
        msg = "\n".join([f"{g['day'].title()} | Role ID: {g['role_id']} | Value: {g['value_tier']} | Starts: {g['start_time']}" for g in scheduled])
        await ctx.send(f"Scheduled Giveaways:\n{msg}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def clearscheduled(self, ctx):
        """Clear all scheduled giveaways for this server."""
        await self.config.guild(ctx.guild).scheduled_giveaways.set([])
        await ctx.send("All scheduled giveaways have been cleared for this server.")



class GiveawayButtonView(discord.ui.View):
    def __init__(self, role_id, card_data, card_link, role, end_time):
        super().__init__(timeout=None)
        self.entrants = set()
        self.role_id = role_id
        self.card_data = card_data
        self.card_link = card_link
        self.role = role
        self.end_time = end_time
        self.message = None

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.role_id and self.role_id not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You don't have the required role to enter.", ephemeral=True)
            return
        self.entrants.add(interaction.user)
        await interaction.response.send_message("You've entered the giveaway!", ephemeral=True)
        if self.message:
            await self.message.edit(embed=self.create_embed(), view=self)

    def get_entrants(self):
        return list(self.entrants)

    async def disable_all_items(self):
        for item in self.children:
            item.disabled = True
        self.stop()

        # Build custom card thumbnail URL
    def build_card_thumbnail_url(name: str, season: str, cardid: str) -> str:
        formatted_name = name.lower().replace(" ", "_")
        return f"https://www.nationstates.net/images/cards/s{season}/uploads/{formatted_name}__{cardid}"

    def create_embed(self):
        embed = discord.Embed(
            title=f"Giveaway: {self.card_data['name']} ({self.card_data['category'].title()})",
            description=f"A {self.card_data['category'].title()} card is up for grabs!",
            url=self.card_link,
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=f"https://www.nationstates.net/images/flags/{self.card_data['flag']}")
        eligible_role = self.role.mention if self.role else "Everyone"
        embed.add_field(name="Market Value", value=f"{self.card_data['market_value']}", inline=True)
        embed.add_field(name="Eligible Role", value=eligible_role, inline=True)
        embed.add_field(name="Ends", value=f"<t:{int(self.end_time.timestamp())}:R>", inline=False)
        embed.add_field(name="Entrants", value=str(len(self.entrants)), inline=False)
        embed.set_footer(text="Click the button to enter!")
        # Inside your embed-building logic:
        thumbnail_url = self.build_card_thumbnail_url(self.card_data["name"], self.card_data["season"], self.card_data["cardid"])
        embed.set_thumbnail(url=thumbnail_url)
        return embed
