import discord
from redbot.core import commands, Config, checks
from discord.ext import tasks  
import aiohttp
import random
import xml.etree.ElementTree as ET
from discord import Embed
import time
import csv
import os
from datetime import datetime
import asyncio
from datetime import datetime, timedelta
import re
import urllib.parse  
import html
import requests
import json
from redbot.core.utils.chat_formatting import humanize_number



class NexusExchange(commands.Cog):
    """A Master Currency Exchange Cog for The Wellspring"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=True)
        self.config.register_guild(
            daily_channel = None,
            daily_time = "12:00",  # Default time to noon
            master_currency_name="wellcoin",
            exchange_rates={}, 
            xp_per_message=5,  # XP per message
            coins_per_message=1,  # WellCoins per valid message
            message_cooldown=10,  # Cooldown in seconds to prevent farming
            blacklisted_channels=[],  # List of channel IDs where WellCoins are NOT earned# {"currency_name": {"config_id": int, "rate": float}}
            min_message_length=20,
            Message_count=0,
            Message_count_spam=0,
            telegrams = {},# Minimum message length to earn rewards

        )
        self.ads_folder = "ads"  # Folder where ad text files are stored


        self.config.register_user(
            master_balance=0,
            xp=0,
            last_message_time=0,
            linked_nations=[],
            last_rmb_post_time=0,
            bank_total=0,
            loan_amount=0,  # Current loan
            loan_days=0     # Days since loan started
        )
            # Lootbox configuration
        self.config.register_global(
            season=[3,4],
            categories=["common", "uncommon", "rare", "ultra-rare", "epic"],
            useragent="",
            nationName="",
            password="",
            daily_wellcoins=0,  # Total WellCoins from the last dispatch
            weekly_wellcoins=0,
            last_update=0,  # Timestamp of the last daily update
            last_weekly_update=0,
            nations = {}# Timestamp of the last weekly update
        )

        self.API_URL = "https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q=nations"
        self.USER_AGENT = "9005"
        self.MAX_NATIONS_PER_TG = 8
        self.MAX_BUTTONS_PER_ROW = 5
        self.MAX_ROWS_PER_MESSAGE = 5  # Discord allows 5 rows of buttons per message
    
        self.config.register_guild(
        # ... existing config ...
        welcome_message=None,  # Message to send when a new user joins
        welcome_channel=None   # Optional: allow setting a specific channel
    )

        

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.daily_task.is_running():
            self.daily_task.start()

    @commands.command()
    @commands.admin()
    async def start_loop(self, ctx):
        """Manually start the daily task loop if it's not running."""
        if self.daily_task.is_running():
            await ctx.send("✅ The daily task loop is already running.")
        else:
            self.daily_task.start()
            await ctx.send("🔄 Daily task loop has been started.")    


    
    async def fetch_nations(self):
        """Fetch nations from the NationStates API asynchronously."""
        headers = {"User-Agent": self.USER_AGENT}
        async with aiohttp.ClientSession() as session:
            async with session.get(self.API_URL, headers=headers) as response:
                if response.status != 200:
                    return []

                xml_data = await response.text()
                start_tag, end_tag = "<NATIONS>", "</NATIONS>"
                start_index = xml_data.find(start_tag) + len(start_tag)
                end_index = xml_data.find(end_tag)
                nations = xml_data[start_index:end_index].split(":")
                return [n for n in nations if n]

    
    async def update_nation_days(self):
        """Update nation days in region asynchronously."""
        nations = await self.fetch_nations()
        if not nations:
            return

        nation_data = await self.config.nations()
        for nation in nations:
            nation_data[nation] = nation_data.get(nation, 0) + 1  # Increment day count

        await self.config.nations.set(nation_data)
        

    async def generate_tg_links(self, nations_to_send, code):
        """Generate TG links asynchronously."""
        tg_links = []
        for i in range(0, len(nations_to_send), self.MAX_NATIONS_PER_TG):
            tg_batch = nations_to_send[i : i + self.MAX_NATIONS_PER_TG]
            tg_link = f"https://www.nationstates.net/page=compose_telegram?tgto={','.join(tg_batch)}&message={code}&generated_by=TGer&run_by={self.USER_AGENT}"
            tg_links.append(tg_link)
        return tg_links

    @commands.command()
    async def bank_deposit(self, ctx, deposit: int):
        """Deposit WellCoins into your bank."""
        user = ctx.author
        user_data = self.config.user(user)
        balance = await user_data.master_balance()

        if deposit <= 0:
            return await ctx.send("❌ You must deposit a positive amount.")
        if deposit > balance:
            return await ctx.send(f"❌ You only have {humanize_number(balance)} {await self.config.guild(ctx.guild).master_currency_name()} available.")

        await user_data.master_balance.set(balance - deposit)
        current_bank = await user_data.bank_total()
        await user_data.bank_total.set(current_bank + deposit)

        await ctx.send(f"✅ {humanize_number(deposit)} {await self.config.guild(ctx.guild).master_currency_name()} deposited into your hole in the ground. 💰")
        

    @commands.command()
    async def viewtgs(self, ctx):
        """View the current TGs in the config."""
        tg_data = await self.config.guild(ctx.guild).telegrams()
        if not tg_data:
            await ctx.send("No TGs found.")
            return

        embed = discord.Embed(title="Scheduled TGs", color=discord.Color.blue())
        for day, code in tg_data.items():
            embed.add_field(name=f"Day {day}", value=f"`{code}`", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def viewnations(self, ctx):
        """View the current TGs in the config."""
        tg_data = await self.config.nations()
        if not tg_data:
            await ctx.send("No TGs found.")
            return

        embed = discord.Embed(title="Scheduled TGs", color=discord.Color.blue())
        embed.add_field(name=f"Day", value=f"`{str(tg_data)[:1000]}`", inline=False)

        await ctx.send(embed=embed)
        

    @commands.command()
    async def addtg(self, ctx, days: int, *, tg_code: str):
        """Add a new TG to the config."""
        tg_data = await self.config.guild(ctx.guild).telegrams()
        if days in tg_data:
            await ctx.send(f"A TG already exists for **{days} days**. Use `[p]removetg {days}` first.")
            return

        tg_data[days] = tg_code
        await self.config.guild(ctx.guild).telegrams.set(tg_data)
        await ctx.send(f"✅ Added TG for **{days} days** with code `{tg_code}`.")

    @commands.command()
    async def dumpnat(self, ctx, days: int, *, tg_code: str):
        """Add a new TG to the config."""
        await self.config.nations.set({})
        await ctx.send(f"✅ dumped all nations`.")

    @commands.command()
    async def removetg(self, ctx, days: int):
        """Remove a TG from the config."""
        tg_data = await self.config.guild(ctx.guild).telegrams()
        if days not in tg_data:
            await ctx.send(f"No TG found for **{days} days**.")
            return

        del tg_data[days]
        await self.config.guild(ctx.guild).telegrams.set(tg_data)
        await ctx.send(f"🗑 Removed TG for **{days} days**.")

    async def sendtgs(self, ctx):
        """Trigger the sending of TG buttons in a normal message asynchronously."""
        await self.update_nation_days()
        tg_data = await self.config.guild(ctx.guild).telegrams()
        nation_data = await self.config.nations()

        if not tg_data:
            await ctx.send("No TGs scheduled.")
            return

        all_buttons = []
        total_buttons = 0

        for days_required, code in tg_data.items():
            nations_to_send = [nation for nation, days in nation_data.items() if int(days) == int(days_required)]

            if not nations_to_send:
                continue  # Skip if no nations match the criteria

            tg_links = await self.generate_tg_links(nations_to_send, code)

            button_row = []
            for link in tg_links:
                button = discord.ui.Button(label=f"Send TG ({days_required} Days)", style=discord.ButtonStyle.url, url=link)
                button_row.append(button)
                total_buttons += 1

                if len(button_row) == self.MAX_BUTTONS_PER_ROW:
                    view = discord.ui.View()
                    for button in button_row:
                        view.add_item(button)
                    all_buttons.append(view)    

                    button_row = []

                if len(all_buttons) >= self.MAX_ROWS_PER_MESSAGE:
                    break

            if button_row and len(all_buttons) < self.MAX_ROWS_PER_MESSAGE:
                for button in button_row:
                    view.add_item(button)
                all_buttons.append(view)    

            if len(all_buttons) >= self.MAX_ROWS_PER_MESSAGE:
                break

        if not all_buttons:
            await ctx.send("No nations need TGs today.")
            return

        view = discord.ui.View()
        for row in all_buttons:
            for button in row.children:
                view.add_item(button)

        await ctx.send(f"@here - **Daily Telegrams are ready!** ({total_buttons} buttons)", view=view)


    


    async def fetch_bank_data(self):
        """Fetches all users' bank balances and linked nations."""
        all_users = await self.config.all_users()
        bank_list = []

        for user_id, data in all_users.items():
            linked_nations = data.get("linked_nations", [])
            balance = data.get("master_balance", 0)

            if linked_nations:
                nation = linked_nations[0]  # Assume first linked nation is primary
                bank_list.append((nation, balance))

        return sorted(bank_list, key=lambda x: x[1], reverse=True)

    def get_random_ad(self):
        """Fetches a random ad from the ad folder."""

            # Get the absolute path to the ads folder
        base_dir = os.path.dirname(os.path.abspath(__file__))  # Get the script's directory
        ads_folder = os.path.join(base_dir, "ads")  # Assume ads is in the same folder as the script
        
        if not os.path.exists(ads_folder):
            return "No ads found."

        files = [f for f in os.listdir(ads_folder) if f.endswith(".txt")]
        if not files:
            return "No ad files available."

        chosen_file = random.choice(files)
        with open(os.path.join(ads_folder, chosen_file), "r", encoding="utf-8") as f:
            return f.read()

    @commands.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def post_bank_dispatch(self, ctx):
        """Posts a NationStates dispatch with the latest bank rankings."""
        await ctx.send("Generating the Bank of The Wellspring dispatch...")

        bank_data = await self.fetch_bank_data()
        total_wellcoins = sum(balance for _, balance in bank_data)

        if not bank_data:
            await ctx.send("No bank data found. Cannot post dispatch.")
            return

        # Top 3 richest users with proper medals
        top_richest = bank_data[:3]
        medals = ["[1st]", "[2nd]", "[3rd]"]  # Gold, Silver, Bronze
        
        richest_section = "\n".join([
            f"[*][b]{medals[i]} {i+1}:[/b] [nation]{nation}[/nation] - [b]{balance} WellCoins[/b]"
            for i, (nation, balance) in enumerate(top_richest)
        ])


        # Full bank listing
        full_bank_section = "\n".join([
            f"[*][b][nation]{nation}[/nation][/b] - [b]{balance}: WellCoins[/b]"
            for nation, balance in bank_data
        ])

        # Update historical snapshots
        await self.update_wellcoin_snapshots(total_wellcoins)
    
        # Fetch previous totals
        last_daily = await self.config.daily_wellcoins()
        last_weekly = await self.config.weekly_wellcoins()
    
        # Calculate changes
        daily_change = total_wellcoins - last_daily
        weekly_change = total_wellcoins - last_weekly
    
        # Formatting positive/negative change
        daily_change_str = f"[color=green]+{daily_change}[/color]" if daily_change >= 0 else f"[color=red]{daily_change}[/color]"
        weekly_change_str = f"[color=green]+{weekly_change}[/color]" if weekly_change >= 0 else f"[color=red]{weekly_change}[/color]"

        

        # Dispatch content
        dispatch_content = f"""
[background-block=#BAEBFA]
[hr][center][img]https://i.imgur.com/BDSuZJg.png[/img][hr][/center]
[/background-block]

[background-block=#2A6273]
[hr][center][font=georgia][color=#BAEBFA][b][size=200]WellCoins: Bank of The Wellspring[/size][/b][/color][/font][/center][hr]
[/background-block]

[box]
[background-block=#BAEBFA]
[center][font=georgia][color=#2A6273][b][size=150]$ Top 3 Richest Users $[/size][/b][/color][/font][/center]
[list]{richest_section}[/list]
[/background-block]
[/box]

[box]
[background-block=#2A6273]
[hr][center][font=georgia][color=#BAEBFA][b][size=150]Full Bank Listings[/size][/b][/color][/font][/center][hr]
[list]{full_bank_section}[/list]
[/background-block]
[/box]

[box]
[background-block=#BAEBFA]
[hr][center][font=georgia][color=#2A6273][b][size=150]Fun Stats[/size][/b][/color][/font][/center][hr]
[list]
[*]Total WellCoins in circulation: [b]{total_wellcoins}[/b]
[*]Change since yesterday: {daily_change_str}
[*]Change since last week: {weekly_change_str}
[/list]
[/background-block]
[/box]

"""

        await ctx.send(await self.post_dispatch(dispatch_content))
        
    async def post_dispatch(self, dispatch_content):
        """Posts the updated dispatch to NationStates API"""
        nationname = await self.config.nationName()  # Nation that owns the dispatch
        password = await self.config.password()  # Nation's password
        useragent = await self.config.useragent()  # Custom user agent

        dispatch_content = html.escape(dispatch_content)        
       
        url = "https://www.nationstates.net/cgi-bin/api.cgi"
        headers = {
            "User-Agent": useragent,
            "X-Password": password
        }
    
        # Step 1: Prepare the Dispatch Edit Request
        prepare_data = {
            "nation": nationname,
            "c": "dispatch",
            "dispatch": "edit",
            "dispatchid": "2633980",
            "title": "WellCoins: Bank of The Wellspring",
            "text": dispatch_content,
            "category": "5",
            "subcategory": "515",
            "mode": "prepare"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(url, data=prepare_data) as prepare_response:
                prepare_text = await prepare_response.text()
                
                if prepare_response.status != 200:
                    return f"❌ Failed to prepare dispatch. Response: {prepare_text}"
    
                # Extract token and X-Pin from response headers
                x_pin = prepare_response.headers.get("X-Pin")
                try:
                    root = ET.fromstring(prepare_text)
                    token = root.find("SUCCESS").text
                except:
                    return f"❌ Failed to extract token from response. API Response: {prepare_text}"
    
                if not token or not x_pin:
                    return "❌ Missing token or X-Pin in API response. Cannot proceed."
    
                # Step 2: Execute the Dispatch Edit Request
                execute_data = {
                    "nation": nationname,
                    "c": "dispatch",
                    "dispatch": "edit",
                    "dispatchid": "2633980",
                    "title": "WellCoins: Bank of The Wellspring",
                    "text": dispatch_content,
                    "category": "5",
                    "subcategory": "515",
                    "mode": "execute",
                    "token": token
                }
    
                execute_headers = {
                    "User-Agent": useragent,
                    "X-Pin": x_pin  # Use the X-Pin from the prepare request
                }
    
                async with session.post(url, data=execute_data, headers=execute_headers) as execute_response:
                    execute_text = await execute_response.text()
    
                    if execute_response.status == 200:
                        return f"✅ Dispatch updated successfully!\n\n{execute_text}"
                    else:
                        return f"❌ Failed to execute dispatch update. Response: {execute_text}"



    
    def cog_unload(self):
        self.daily_task.cancel()

    async def fetch_endorsements(self):
        """Fetches the list of nations endorsing well-spring_jack"""
        url = "https://www.nationstates.net/cgi-bin/api.cgi?nation=well-sprung_jack&q=endorsements"
        headers = {"User-Agent": "9005, EndorserPayoutBot"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    print(f"API request failed: {response.status}")
                    return None
                return await response.text()

    async def pay_endorsers(self, ctx):
        """Pays 10 WellCoins to all users who endorsed 9006"""

        xml_data = await self.fetch_endorsements()
        if not xml_data:
            await ctx.send("Failed to retrieve endorsements. Try again later.")
            return

        # Parse XML to get endorsed nations
        root = ET.fromstring(xml_data)
        endorsements_text = root.find(".//ENDORSEMENTS").text
        endorsers = set(endorsements_text.split(",")) if endorsements_text else set()

        if not endorsers:
            await ctx.send("No endorsers found.")
            return

        # Get all users from config
        all_users = await self.config.all_users()
        paid_users = 0

        for user_id, data in all_users.items():
            linked_nations = data.get("linked_nations", [])
            if any(nation in endorsers for nation in linked_nations):
                new_balance = data["master_balance"] + 10
                await self.config.user_from_id(user_id).master_balance.set(new_balance)
                paid_users += 1

        await ctx.send(f"✅ Paid 10 WellCoins to {paid_users} users who endorsed well-sprung_jack!")

    
    async def fetch_rmb_posts(self, since_time):
        """Fetches RMB posts from NationStates API"""
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=happenings;filter=rmb;limit=1000;sincetime={since_time};view=region.the_wellspring"
        headers = {"User-Agent": "9006, NexusExchange"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                return await response.text()

    def extract_rmb_posts(self, xml_data):
        """Parses XML data to extract valid RMB posts from The Wellspring"""
        root = ET.fromstring(xml_data)
        events = root.findall(".//EVENT")

        posts = []
        for event in events:
            timestamp = int(event.find("TIMESTAMP").text)
            text = event.find("TEXT").text

            # Extract nation and region using regex
            match = re.search(r"@@(.*?)@@ lodged .*? on the %%(.*?)%% Regional Message Board", text)
            if match:
                nation = match.group(1).lower()
                region = match.group(2).lower()

                # Only count messages from "the_wellspring"
                if region == "the_wellspring":
                    posts.append({"nation": nation, "timestamp": timestamp, "text": text})

        return posts

    def is_valid_post(self, text):
        """Checks if a post meets the 20-character requirement (excluding links)"""
        return len(text) >= 20
    
    async def reward_users_RMB(self, posts):
        """Rewards users with 20 WellCoins for 1 post, 50 WellCoins for 2+ posts"""
        all_users = await self.config.all_users()
    
        user_post_counts = {}  # Tracks how many valid posts each user made
        scan = 0
    
        for post in posts:
            nation = post["nation"]
            scan += 1
    
            # Find Discord users linked to this nation
            for user_id, data in all_users.items():
                linked_nations = data.get("linked_nations", [])
                if nation.lower().replace(" ","_") in linked_nations:
                    user = self.bot.get_user(user_id)
                    if not user:
                        continue
    
                    # Check if post is substantial
                    if not self.is_valid_post(post["text"]):
                        continue
    
                    # Track valid posts per user
                    if user_id not in user_post_counts:
                        user_post_counts[user_id] = 0
                    user_post_counts[user_id] += 1
    
    
        # Reward users based on post count
        for user_id, post_count in user_post_counts.items():
            reward = 50 if post_count >= 2 else 20  # 50 for 2+ posts, 20 for 1 post
            user_data = await self.config.user_from_id(user_id).all()
            new_balance = user_data["master_balance"] + reward
            await self.config.user_from_id(user_id).master_balance.set(new_balance)
    
        return scan, len(user_post_counts)

    @commands.command()
    async def loan_status(self, ctx):
        """Check your current loan balance and status."""
        user_conf = self.config.user(ctx.author)
        loan = await user_conf.loan_amount()
        days = await user_conf.loan_days()
        xp = await user_conf.xp()
        bank = await user_conf.bank_total()
        wallet = await user_conf.master_balance()
    
        if loan <= 0:
            return await ctx.send("🎉 You currently have no outstanding loans.")
    
        currency = await self.config.guild(ctx.guild).master_currency_name()
    
        # Determine status
        if days <= 7:
            status = "🕊️ Grace period (no repayments or penalties yet)."
        elif days < 14:
            penalty = 5 * (days - 7)
            status = (
                f"⏳ Auto-repay from bank and wallet has started.\n"
                f"📉 You're losing `{penalty}` XP per day."
            )
        else:
            penalty = 5 * (days - 7)
            status = (
                f"⚠️ Loan is overdue! Wallet may be negative.\n"
                f"📉 You're losing `{penalty}` XP per day."
            )
    
        embed = discord.Embed(
            title="📋 Loan Status",
            color=discord.Color.red()
        )
        embed.add_field(name="💸 Amount Owed", value=f"`{loan}` {currency}", inline=True)
        embed.add_field(name="📆 Days Since Loan", value=f"`{days}`", inline=True)
        embed.add_field(name="🏦 Bank Balance", value=f"`{bank}`", inline=True)
        embed.add_field(name="💰 Wallet Balance", value=f"`{wallet}`", inline=True)
        embed.add_field(name="⭐ XP", value=f"`{xp}`", inline=True)
        embed.add_field(name="⚙️ Status", value=status, inline=False)
    
        await ctx.send(embed=embed)



    @commands.command()
    async def bank_withdraw(self, ctx, amount: int):
        """Withdraw WellCoins from your bank into your on-hand balance."""
        user = ctx.author
        user_data = self.config.user(user)
        guild_data = self.config.guild(ctx.guild)
    
        if amount <= 0:
            return await ctx.send("❌ You must withdraw a positive amount.")
    
        bank_balance = await user_data.bank_total()
    
        if amount > bank_balance:
            return await ctx.send(f"❌ You only have `{bank_balance}` WellCoins in your hole in the ground.")
    
        new_bank_balance = bank_balance - amount
        new_wallet_balance = await user_data.master_balance() + amount
    
        await user_data.bank_total.set(new_bank_balance)
        await user_data.master_balance.set(new_wallet_balance)
    
        currency = await guild_data.master_currency_name()
        await ctx.send(f"🏧 You withdrew `{amount}` {currency} from your hole in the ground.\n💰 New on-hand balance: `{new_wallet_balance}` {currency}.")


    @commands.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def reward_rmb(self, ctx):
        """Manually trigger the RMB rewards check"""
        await ctx.send("Fetching The Wellspring RMB posts...")

        # Get last processed timestamp
        last_time = int(datetime.utcnow().timestamp()) - 86400  # Default to last 24 hours

        xml_data = await self.fetch_rmb_posts(last_time)
        if not xml_data:
            await ctx.send("Failed to fetch RMB posts.")
            return
        #await ctx.send(xml_data[:1000])
        posts = self.extract_rmb_posts(xml_data)
        
        scan, count = await self.reward_users_RMB(posts)

        await ctx.send(f"Rewards have been distributed for substantial RMB posts in The Wellspring!{count}/{scan}  {last_time}")

    @tasks.loop(hours=1)
    async def daily_task(self):
        now = datetime.utcnow()
        if now.hour == 20:
            channel = self.bot.get_channel(1214216647976554556)
            if channel:
                loan_log = []
                try:
                    message = await channel.send("Starting daily cycle")
                    ctx = await self.bot.get_context(message)
                    await self.wanderChk(channel)
                    await self.resChk(channel)
                    await self.pay_endorsers(channel)
                    await self.reward_voters(channel)
                    await self.newNation(channel)
                    await asyncio.sleep(10)
                    await self.post_bank_dispatch(channel)
                    await self.citChk(channel)
                
                    # Loan processing
                    all_users = await self.config.all_users()
                    for user_id in all_users:
                        await self.process_user_loan(int(user_id), loan_log)
    
                    if loan_log:
                        await channel.send("📋 **Loan Status Summary**\n" + "\n".join(loan_log))
                except Exception as e:
                    await channel.send(e)

    def parse_token(self, xml_data: str) -> str:
        """Extracts the token from XML response."""
        try:
            root = ET.fromstring(xml_data)
            token = root.find("SUCCESS").text
            return token
        except ET.ParseError:
            return None


    @commands.command()
    async def repay_loan(self, ctx, amount: int):
        """Repay part or all of your loan."""
        user = ctx.author
        data = self.config.user(user)
        loan = await data.loan_amount()
        balance = await data.master_balance()
    
        if loan <= 0:
            return await ctx.send("🎉 You don't have a loan to repay.")
    
        if amount <= 0:
            return await ctx.send("❌ Enter a valid repayment amount.")
    
        if amount > balance:
            return await ctx.send("❌ You don't have that much on hand.")
    
        payment = min(amount, loan)
        await data.master_balance.set(balance - payment)
        await data.loan_amount.set(loan - payment)
    
        await ctx.send(f"✅ You repaid `{payment}` WellCoins. Remaining loan: `{loan - payment}`.")

    async def process_user_loan(self, user_id: int, loan_log: list):
        """Handle loan interest, repayments, XP penalties, and send reminders."""
        user_conf = self.config.user_from_id(user_id)
        loan = await user_conf.loan_amount()
        days = await user_conf.loan_days()
    
        if loan <= 0:
            return
    
        new_loan = int(loan * 1.05)+1
        days += 1
        repay_amount = new_loan - loan
    
        bank = await user_conf.bank_total()
        wallet = await user_conf.master_balance()
        xp = await user_conf.xp()
    
        auto_paid = 0
        went_negative = False
    
        if days >= 7:
            # Attempt to auto-repay from bank
            if bank > 0:
                from_bank = min(bank, repay_amount)
                bank -= from_bank
                repay_amount -= from_bank
                new_loan -= from_bank
                auto_paid += from_bank
    
            # Attempt to auto-repay from wallet (only before day 14)
            if days < 14 and repay_amount > 0 and wallet > 0:
                from_wallet = min(wallet, repay_amount)
                wallet -= from_wallet
                repay_amount -= from_wallet
                new_loan -= from_wallet
                auto_paid += from_wallet
    
            # After 14 days, allow wallet to go negative to cover remaining loan
            if days >= 14 and repay_amount > 0:
                wallet -= repay_amount
                new_loan -= repay_amount
                auto_paid += repay_amount
                went_negative = True
    
            # Apply growing XP penalty starting day 8
            if days > 7:
                penalty = 5 * (days - 7)
                xp = max(0, xp - penalty)
                await user_conf.xp.set(xp)
    
        # Update values
        await user_conf.bank_total.set(bank)
        await user_conf.master_balance.set(wallet)
        await user_conf.loan_amount.set(new_loan)
        await user_conf.loan_days.set(days)
    
        # Log for monitor channel
        loan_log.append(
            f"<@{user_id}> | Owes: `{new_loan}` | Day: {days} | "
            f"Paid: `{auto_paid}` | {'💀 Wallet NEGATIVE' if went_negative else '✅ Partial/Full auto-repay'}"
        )
    
        # DM user
        user = self.bot.get_user(user_id)
        if user:
            try:
                currency = await self.config.guild(user.guilds[0]).master_currency_name() if user.guilds else "WellCoins"
                msg = (
                    f"📢 **Loan Reminder**\n"
                    f"💸 You currently owe `{new_loan}` {currency}.\n"
                    f"📆 Loan Age: `{days}` day(s)\n"
                )
                if days <= 7:
                    msg += "🕊️ You're in your **grace period**. No auto-payments or penalties yet.\n"
                elif days < 14:
                    msg += (
                        f"⏳ You’ve passed the 7-day grace period. Auto-payments are being made "
                        f"from your bank and wallet if possible. You also lose XP daily.\n"
                    )
                else:
                    msg += (
                        f"⚠️ You're past 14 days! Wallet is allowed to go negative to cover your loan. "
                        f"XP loss continues until loan is repaid.\n"
                    )
    
                msg += "\nUse `!repay_loan <amount>` in the server to pay back your loan."
                await user.send(msg)
            except:
                pass  # DM failed



    @commands.command()
    async def take_loan(self, ctx, amount: int):
        """Take out a WellCoin loan. Loans grow 5% daily."""
        if amount <= 0:
            return await ctx.send("❌ You must borrow a positive amount.")
        
        user = ctx.author
        data = self.config.user(user)
        current_loan = await data.loan_amount()
    
        if current_loan > 0:
            return await ctx.send("❌ You already have an unpaid loan!")
    
        await data.loan_amount.set(int(amount+amount*1.05+1))
        await data.loan_days.set(0)
        current_balance = await data.master_balance()
        await data.master_balance.set(current_balance + amount)
    
        await ctx.send(f"💸 You took a loan of `{amount}` WellCoins. Interest is 5% daily. Repay it soon!")



    @commands.command()
    @commands.admin()
    async def citChk(self, ctx):
        """Checks if a member has Role A, and removes Role B if not."""
        role_a_id = 1098645868162338919  # Role A: Required Role
        role_b_id = 1098646004250726420  # Role B: Role to Remove

        role_a = ctx.guild.get_role(role_a_id)
        role_b = ctx.guild.get_role(role_b_id)

        if not role_a or not role_b:
            await ctx.send("One or both roles not found.")
            return

        removed_count = 0
        for member in role_b.members:
            if role_a not in member.roles:
                try:
                    await member.remove_roles(role_b, reason="Missing required role.")
                    removed_count += 1
                except discord.Forbidden:
                    await ctx.send(f"Cannot remove {role_b.name} from {member.mention} — insufficient permissions.")
                except Exception as e:
                    await ctx.send(f"Error removing role from {member.mention}: {e}")

        await ctx.send(f"Finished. Removed {role_b.name} from {removed_count} member(s) who lacked {role_a.name}.")

    

    @commands.command()
    @commands.admin()
    async def newNation(self, ctx):
        """Post a shoutout to all new nations and WA nations in The Wellspring."""
        region = "the_wellspring"
        nationname = await self.config.nationName()
        password = await self.config.password()
        useragent = await self.config.useragent()
    
        if not all([useragent, password, nationname]):
            await ctx.send("Please ensure User-Agent, Nation Name, and Password are all set.")
            return
    
        headers = {"User-Agent": useragent}
    
        # Fetch current nations and WA nations
        async with aiohttp.ClientSession(headers=headers) as session:
            # Nations
            async with session.get(f"https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q=nations") as resp_nations:
                nations_data = await resp_nations.text()
                start_tag, end_tag = "<NATIONS>", "</NATIONS>"
                start_index = nations_data.find(start_tag) + len(start_tag)
                end_index = nations_data.find(end_tag)
                current_nations = set(nations_data[start_index:end_index].split(":"))
    
            # WA Nations
            async with session.get(f"https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q=wanations") as resp_wa:
                wa_data = await resp_wa.text()
                start_tag, end_tag = "<UNNATIONS>", "</UNNATIONS>"
                start_index = wa_data.find(start_tag) + len(start_tag)
                end_index = wa_data.find(end_tag)
                current_wa_nations = set(wa_data[start_index:end_index].split(","))
    
        # Get stored previous lists from config
        previous_nations = set(await self.config.get_raw("previous_nations", default=[]))
        previous_wa_nations = set(await self.config.get_raw("previous_wa_nations", default=[]))
    
        # Determine new nations and new WA members
        new_nations = current_nations - previous_nations
        new_wa_nations = current_wa_nations - previous_wa_nations
    
        # Save current lists for next time
        await self.config.set_raw("previous_nations", value=list(current_nations))
        await self.config.set_raw("previous_wa_nations", value=list(current_wa_nations))
    
        # Format RMB message
        message_parts = []
        if new_nations:
            message_parts.append("[spoiler=Welcome to The Wellspring!]\nA warm welcome to our newest nations:\n" + ", ".join(f"[nation]{nation}[/nation]" for nation in new_nations)+"[/spoiler]")
        if new_wa_nations:
            message_parts.append("[spoiler=New WA Nations Alert!] \nJoin us in celebrating our newest World Assembly members:\n" +
                                 ", ".join(f"[nation]{nation}[/nation]" for nation in new_wa_nations)+"[/spoiler]")
    
        if not message_parts:
            await ctx.send("No new nations or WA nations found since last check.")
            return
    
        final_message = "\n\n".join(message_parts)
    
        # Prepare RMB post
        prepare_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": final_message,
            "mode": "prepare"
        }
        prepare_headers = {
            "User-Agent": useragent,
            "X-Password": password
        }
    
        async with aiohttp.ClientSession() as session:
            async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
                prepare_text = await prepare_response.text()
                if prepare_response.status != 200:
                    await ctx.send("Failed to prepare RMB post.")
                    await ctx.send(prepare_text)
                    return
    
                token = self.parse_token(prepare_text)
                x_pin = prepare_response.headers.get("X-Pin")
    
                if not token or not x_pin:
                    await ctx.send("Failed to retrieve the token or X-Pin for RMB post execution.")
                    await ctx.send(prepare_text)
                    return
    
        # Execute RMB post
        execute_data = {
            "nation": nationname,
            "c": "rmbpost",
            "region": region,
            "text": final_message,
            "mode": "execute",
            "token": token
        }
        execute_headers = {
            "User-Agent": useragent,
            "X-Pin": x_pin
        }
    
        async with aiohttp.ClientSession() as session:
            async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
                execute_text = await execute_response.text()
                if execute_response.status == 200:
                    await ctx.send(f"✅ Successfully posted shout-out to RMB for {len(new_nations)} new nations and {len(new_wa_nations)} new WA nations!")
                else:
                    await ctx.send("Failed to execute RMB post.")
                    await ctx.send(execute_text)


        

    

    @commands.command()
    @commands.admin()
    async def resChk(self, ctx):
        """Check if the daily_task loop is running and manage roles based on residency."""
        resendents = await self.fetch_nations()
        if not resendents:
            await ctx.send("Failed to retrieve resendents. Try again later.")
            return

        if not resendents:
            await ctx.send("No resendents found.")
            return
    
        # Role ID to be assigned/removed
        role_id = 1098645868162338919
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("Role not found. Please check the role ID.")
            return
    
        # Get all users from config
        all_users = await self.config.all_users()
        gained_role = 0
        lost_role = 0
    
        for user_id, data in all_users.items():
            linked_nations = data.get("linked_nations", [])
            user = ctx.guild.get_member(int(user_id))
            if not user:
                continue  # Skip users not found in the guild


    
            is_resident = any(nation in resendents for nation in linked_nations)
    
            if is_resident:

                if role not in user.roles:
                    await user.add_roles(role)
                    gained_role += 1
            else:
                # Remove role if they have it but no endorsed nation
                if role in user.roles:
                    await user.remove_roles(role)
                    lost_role += 1
    
        await ctx.send(f"✅ {gained_role} users gained the resident Role.\n❌ {lost_role} users lost the resident Role.")


    @commands.command()
    @commands.admin()
    async def wanderChk(self, ctx):
        """Check if the daily_task loop is running and manage roles based on endorsements."""
        xml_data = await self.fetch_endorsements()
        if not xml_data:
            await ctx.send("Failed to retrieve endorsements. Try again later.")
            return
    
        # Parse XML to get endorsed nations
        root = ET.fromstring(xml_data)
        endorsements_text = root.find(".//ENDORSEMENTS").text
        endorsers = set(endorsements_text.split(",")) if endorsements_text else set()
    
        if not endorsers:
            await ctx.send("No endorsers found.")
            return
    
        # Role ID to be assigned/removed
        role_id = 1098673767858843648
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("Role not found. Please check the role ID.")
            return
    
        # Get all users from config
        all_users = await self.config.all_users()
        gained_role = 0
        lost_role = 0
    
        for user_id, data in all_users.items():
            linked_nations = data.get("linked_nations", [])
            user = ctx.guild.get_member(int(user_id))
            if not user:
                continue  # Skip users not found in the guild

            if not linked_nations:
                # No linked nations; remove role if present
                if role in user.roles:
                    await user.remove_roles(role)
                    lost_role += 1
                    continue
    
            has_endorsed_nation = any(nation in endorsers for nation in linked_nations)
    
            if has_endorsed_nation:

                if role not in user.roles:
                    await user.add_roles(role)
                    gained_role += 1
            else:
                # Remove role if they have it but no endorsed nation
                if role in user.roles:
                    await user.remove_roles(role)
                    lost_role += 1
    
        await ctx.send(f"✅ {gained_role} users gained the Wanderer Role.\n❌ {lost_role} users lost the Wanderer Role.")


        # Parse XML to get endorsed nations
        root = ET.fromstring(xml_data)
        endorsements_text = root.find(".//ENDORSEMENTS").text
        endorsers = set(endorsements_text.split(",")) if endorsements_text else set()

        if not endorsers:
            await ctx.send("No endorsers found.")
            return
    
        # Get all users from config
        all_users = await self.config.all_users()
        paid_users = 0
    
        for user_id, data in all_users.items():
            linked_nations = data.get("linked_nations", [])
            if any(nation in endorsers for nation in linked_nations):
                new_balance = data["master_balance"] + 10
                await self.config.user_from_id(user_id).master_balance.set(new_balance)
                paid_users += 1
        
   
    @commands.command()
    @commands.admin()
    async def check_loop(self, ctx):
        """Check if the daily_task loop is running."""
        is_running = self.daily_task.is_running()
        await ctx.send(f"🔄 Daily task running: **{is_running}**")    

    async def fetch_wa_data(self,hall):
        """Fetches WA voting data from NationStates API"""
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?wa={hall}&q=resolution+voters"
        headers = {"User-Agent": "9006, NexusExhange"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                return await response.text()

    async def get_9006_vote(self, xml_data):
        """Parses XML and finds how nation 'well-sprung_jack' voted"""
        root = ET.fromstring(xml_data)

        votes_for = {n.text.lower() for n in root.findall(".//VOTES_FOR/N")}
        votes_against = {n.text.lower() for n in root.findall(".//VOTES_AGAINST/N")}

        if "well-sprung_jack" in votes_for:
            return "for"
        elif "well-sprung_jack" in votes_against:
            return "against"
        return None  # well-sprung_jack hasn't voted
    
    async def reward_users(self, user_votes, vote_9006_council1, vote_9006_council2):
        """Rewards users who voted the same as 'well-sprung_jack' in either or both councils"""
        all_users = await self.config.all_users()

        for user_id, data in all_users.items():
            linked_nations = data.get("linked_nations", [])
            if not linked_nations:
                continue  # Skip users with no linked nations

            matching_council_1 = False
            matching_council_2 = False

            for nation in linked_nations:
                nation = nation.lower().replace(" ","_")
                if vote_9006_council1 and nation in user_votes["council1"]:
                    matching_council_1 = True
                if vote_9006_council2 and nation in user_votes["council2"]:
                    matching_council_2 = True

            # Reward based on how many councils match
            if matching_council_1 and matching_council_2:
                reward = 20  # Matching both votes
            elif matching_council_1 or matching_council_2:
                reward = 10  # Matching in one council
            else:
                reward = 0  # No match, no reward

            if reward > 0:
                new_balance = data["master_balance"] + reward
                await self.config.user_from_id(user_id).master_balance.set(new_balance)


    async def reward_voters(self, ctx):
        """Check votes and reward users who voted the same as 'well-sprung_jack' in either WA Council"""
        await ctx.send("Fetching WA vote data for both councils...")

        # Fetch data for both WA councils
        xml_data_council1 = await self.fetch_wa_data(1)
        xml_data_council2 = await self.fetch_wa_data(2)

        # Determine 9006's votes
        vote_9006_council1 = await self.get_9006_vote(xml_data_council1)
        vote_9006_council2 = await self.get_9006_vote(xml_data_council2)

        # If 9006 hasn't voted in either council, no rewards
        if not vote_9006_council1 and not vote_9006_council2:
            await ctx.send("Nation 'well-sprung_jack' has not voted in either council. No rewards given.")
            return

        # Parse votes from each council
        user_votes = {"council1": set(), "council2": set()}

        if xml_data_council1 and vote_9006_council1:
            root = ET.fromstring(xml_data_council1)
            user_votes["council1"] = {n.text.lower() for n in root.findall(f".//VOTES_{vote_9006_council1.upper()}/N")}

        if xml_data_council2 and vote_9006_council2:
            root = ET.fromstring(xml_data_council2)
            user_votes["council2"] = {n.text.lower() for n in root.findall(f".//VOTES_{vote_9006_council2.upper()}/N")}

        # Reward users
        await self.reward_users(user_votes, vote_9006_council1, vote_9006_council2)

        await ctx.send(f"Users who voted the same as [nation]well-sprung_jack[/nation] have been rewarded!")
        
        

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def set_daily_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel where the daily message will be sent."""
        await self.config.guild(ctx.guild).daily_channel.set(channel.id)
        await ctx.send(f"Daily message channel set to {channel.mention}.")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.command()
    async def set_daily_time(self, ctx, time: str):
        """Set the daily message time (HH:MM format, UTC)."""
        try:
            datetime.strptime(time, "%H")  # Validate time format
            await self.config.guild(ctx.guild).daily_time.set(time)
            await ctx.send(f"Daily message time set to **{time} UTC**.")
        except ValueError:
            await ctx.send("Invalid time format. Use HH (24-hour UTC).")
                        
    @commands.group(name="shop", invoke_without_command=True)
    async def shop(self, ctx):
        """Master command for the shop."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(title="🛒 Shop Inventory", color=discord.Color.blue())
            #embed.add_field(name="Loot box", value=f"💰 `10 Coins`\n📜", inline=False)
            embed.add_field(name="Hunger games gold", value=f"💰 `1 Wellcoin gets you 50 hunger games gold`\n📜``$shop buy_gold``` Then tell me how many Wellcoins you want to spend.", inline=False)
            await ctx.send(embed=embed)

    @commands.guild_only()
    @shop.command()
    async def buy_gold(self, ctx):
        """Buy Gold using WellCoins (1 WellCoin = 50 Gold)."""
    
        # Ask user for amount to convert
        await ctx.send("💰 How many WellCoins would you like to spend on Gold? (1 WellCoin = 20 Gold)")
    
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
    
        try:
            response = await self.bot.wait_for("message", check=check, timeout=60)  # Wait for 60 seconds
            wellcoins_to_spend = int(response.content)
        except asyncio.TimeoutError:
            await ctx.send("⏳ You took too long to respond. Try again.")
            return
        except ValueError:
            await ctx.send("❌ Please enter a valid number.")
            return
    
        if wellcoins_to_spend <= 0:
            await ctx.send("❌ You must spend at least 1 WellCoin.")
            return
    
        # Fetch user's current WellCoin balance
        user_balance = await self.config.user(ctx.author).master_balance()
    
        if wellcoins_to_spend > user_balance:
            await ctx.send(f"❌ You only have `{user_balance}` WellCoins. Try again with a smaller amount.")
            return
    
        # Convert WellCoins to Gold
        gold_earned = wellcoins_to_spend * 20
        gold_config = Config.get_conf(None, identifier=1234567890, force_registration=True)
    
        # Fetch user's current Gold balance
        user_gold_balance = await gold_config.user(ctx.author).get_raw("gold", default=0)
    
        # Update balances
        await self.config.user(ctx.author).master_balance.set(user_balance - wellcoins_to_spend)
        await gold_config.user(ctx.author).set_raw("gold", value=user_gold_balance + gold_earned)
    
        await ctx.send(f"✅ You have converted `{wellcoins_to_spend}` WellCoins into `{gold_earned}` Gold! Your new Gold balance: `{user_gold_balance + gold_earned}`.")


    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def set_nation(self, ctx, *, nationname: str):
        """Set the nation name for the loot box prizes."""
        await self.config.nationName.set(nationname)
        await ctx.send(f"Nation Name set to {nationname}")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def set_password(self, ctx, *, password: str):
        """Set the password for the loot box prizes."""
        await self.config.password.set(password)
        await ctx.send("Password has been set successfully.")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def useragent(self, ctx, *, useragent: str):
        """Set the User-Agent header for the requests."""
        await self.config.useragent.set(useragent)
        await ctx.send(f"User-Agent set to {useragent}")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def season(self, ctx, *seasons: str):
        """Set the season to filter cards."""
        seasons = [season for season in seasons]
        await self.config.season.set(seasons)
        await ctx.send(f"Season's set to {seasons}")

    @shop.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def categories(self, ctx, *categories: str):
        """Set the categories to filter cards."""
        categories = [category for category in categories]
        await self.config.categories.set(categories)
        await ctx.send(f"Categories set to {', '.join(categories)}")

    @shop.command()
    @commands.admin()
    @commands.cooldown(1, 60, commands.BucketType.default)  # 1 use per 60 seconds
    async def buy_lootbox(self, ctx, *recipient: str):
        """Open a loot box and fetch a random card for the specified nation."""
        await ctx.send("You bought a lootbox woot woot!")


            # Fetch the user's current WellCoin balance
        user_balance = await self.config.user(ctx.author).master_balance()
    
        # Check if the user has at least 10 WellCoins
        lootbox_cost = 10
        if user_balance < lootbox_cost:
            await ctx.send(f"❌ You need at least `{lootbox_cost}` WellCoins to buy a lootbox. Your balance: `{user_balance}` WellCoins.")
            return

        if len(recipient) < 1:
            await ctx.send("Make sure to put your nation in after openlootbox")
            return


        recipient =  "_".join(recipient)
        season = await self.config.season()
        nationname = await self.config.nationName()
        categories = ["common","uncommon", "rare", "ultra-rare","epic"]
        useragent = await self.config.useragent()

        headers = {"User-Agent": useragent}
        password = await self.config.password()

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname={nationname}"
            ) as response:
                if response.status != 200:
                    await ctx.send(f"Failed to fetch data from NationStates API. {response.status}")
                    await ctx.send(response.text)

                    return

                data = await response.text()
                cards = self.parse_cards(data, season, categories)

                if not cards:
                    await ctx.send(data[:1000])
                    await ctx.send(
                        f"No cards found for season {season} in categories {', '.join(categories)}"
                    )
                    return

                random_card = random.choice(cards)

                # Fetch card details
                async with session.get(
                    f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={random_card['id']};season={random_card['season']}"
                ) as card_info_response:
                    if card_info_response.status != 200:
                        await ctx.send("Failed to fetch card details from NationStates API.")
                        return

                    card_info_data = await card_info_response.text()
                    card_info = self.parse_card_info(card_info_data)

                    embed_color = self.get_embed_color(random_card['category'])
                    embed = Embed(title="Loot Box Opened!", description="You received a card!", color=embed_color)
                    embed.add_field(name="Card Name", value=card_info['name'], inline=True)
                    embed.add_field(name="Card ID", value=random_card['id'], inline=True)
                    embed.add_field(name="Season", value=random_card['season'], inline=True)
                    embed.add_field(name="Market Value", value=card_info['market_value'], inline=True)

                # Prepare the gift
                prepare_data = {
                    "nation": nationname,
                    "c": "giftcard",
                    "cardid": random_card['id'],
                    "season": random_card['season'],
                    "to": recipient,
                    "mode": "prepare"
                }
                prepare_headers = {
                    "User-Agent": useragent,
                    "X-Password": password
                }

                async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
                    if prepare_response.status != 200:
                        if prepare_response.status == 409 or 403:
                            await ctx.send(prepare_response.text)
                            await ctx.send("No loot boxes ready! Give me a minute or so to wrap one up for you.")
                            return       
                        await ctx.send(prepare_response.text)
                        await ctx.send("Failed to prepare the gift.")
                        return

                    prepare_response_data = await prepare_response.text()
                    token = self.parse_token(prepare_response_data)
                    x_pin = prepare_response.headers.get("X-Pin")

                    if not token or not x_pin:
                        await ctx.send(prepare_response_data)
                        await ctx.send("Failed to retrieve the token or X-Pin for gift execution.")
                        return

                    # Execute the gift
                    execute_data = {
                        "nation": nationname,
                        "c": "giftcard",
                        "cardid": random_card['id'],
                        "season": random_card['season'],
                        "to": recipient,
                        "mode": "execute",
                        "token": token
                    }
                    execute_headers = {
                        "User-Agent": useragent,
                        "X-Pin": x_pin
                    }

                    async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
                        if execute_response.status == 200:
                            await ctx.send(embed=embed)
                         # Deduct the cost from the user's balance
                            await self.config.user(ctx.author).master_balance.set(user_balance - lootbox_cost)
                        
                            # Confirm purchase
                            await ctx.send(f"✅ You bought a lootbox for `{lootbox_cost}` WellCoins! Your new balance: `{user_balance - lootbox_cost}` WellCoins.")
                        else:
                            await ctx.send("Failed to execute the gift.")


    @shop.command()
    @commands.admin()
    @commands.cooldown(1, 60, commands.BucketType.default)  # 1 use per 60 seconds
    async def buy_card_request(self, ctx, id, *recipient: str):
        """Open a loot box and fetch a random card for the specified nation."""

        if len(recipient) < 1:
            await ctx.send("Make sure to put your nation in at the end.")
            return
            
        if not id:
            await ctx.send("Please tell me the ID of the card you want ``shop buy_card_request 1 9003``")
            return
            
            # Fetch the user's current WellCoin balance
        user_balance = await self.config.user(ctx.author).master_balance()
    
        # Check if the user has at least 10 WellCoins
        lootbox_cost = 500
        if user_balance < lootbox_cost:
            await ctx.send(f"❌ You need at least `{lootbox_cost}` WellCoins to buy a card request. Your balance: `{user_balance}` WellCoins.")
            return

        await ctx.send("You bought a card request woot woot!")
        
        recipient =  "_".join(recipient)
        season = 4
        nationname = await self.config.nationName()
        categories = ["common","uncommon", "rare", "ultra-rare","epic"]
        useragent = await self.config.useragent()

        headers = {"User-Agent": useragent}
        password = await self.config.password()

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info+owners;cardid={id};season=4"
            ) as response:
                if response.status != 200:
                    await ctx.send(f"Failed to fetch data from NationStates API. {response.status}")
                    await ctx.send(response.text)
                    return

                data = await response.text()
                if "<owner>9006</owner>" not in data.lower():
                    await ctx.send("Sorry you can only request cards that 9006 owns in season 4 at this time!")
                    return
                    
                if "<category>legendary</category>" in data.lower():
                    await ctx.send("Sorry Legendary cards must be specialy requested from 9006 please ask him directly")
                    return

        
                card_info_data = await response.text()
                card_info = self.parse_card_info(card_info_data)

                embed = Embed(title="Loot Box Opened!", description="You received a card!", color=0xFFFF00)
                embed.add_field(name="Card Name", value=card_info['name'], inline=True)
                embed.add_field(name="Card ID", value=id, inline=True)
                embed.add_field(name="Season", value=4, inline=True)
                embed.add_field(name="Market Value", value=card_info['market_value'], inline=True)

                # Prepare the gift
                prepare_data = {
                    "nation": nationname,
                    "c": "giftcard",
                    "cardid": id,
                    "season": 4,
                    "to": recipient,
                    "mode": "prepare"
                }
                prepare_headers = {
                    "User-Agent": useragent,
                    "X-Password": password
                }

                async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
                    if prepare_response.status != 200:
                        if prepare_response.status == 409 or 403:
                            await ctx.send(prepare_response.text)
                            await ctx.send("No loot boxes ready! Give me a minute or so to wrap one up for you.")
                            return       
                        await ctx.send(prepare_response.text)
                        await ctx.send("Failed to prepare the gift.")
                        return

                    prepare_response_data = await prepare_response.text()
                    token = self.parse_token(prepare_response_data)
                    x_pin = prepare_response.headers.get("X-Pin")

                    if not token or not x_pin:
                        await ctx.send(prepare_response_data)
                        await ctx.send("Failed to retrieve the token or X-Pin for gift execution.")
                        return

                    # Execute the gift
                    execute_data = {
                        "nation": nationname,
                        "c": "giftcard",
                        "cardid": id,
                        "season": 4,
                        "to": recipient,
                        "mode": "execute",
                        "token": token
                    }
                    execute_headers = {
                        "User-Agent": useragent,
                        "X-Pin": x_pin
                    }

                    async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
                        if execute_response.status == 200:
                            await ctx.send(embed=embed)
                         # Deduct the cost from the user's balance
                            await self.config.user(ctx.author).master_balance.set(user_balance - lootbox_cost)
                        
                            # Confirm purchase
                            await ctx.send(f"✅ You bought card ID {id} for `{lootbox_cost}` WellCoins! Your new balance: `{user_balance - lootbox_cost}` WellCoins.")
                        else:
                            await ctx.send(execute_response.text)
                            await ctx.send("Failed to execute the gift.")

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def add_to_currency(self, ctx, user: discord.Member, currency_name: str, amount: int):
        """Add a certain amount of a mini-currency to a user's balance."""
        currency_name = currency_name.lower().replace(" ", "_")
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()

        if currency_name not in exchange_rates:
            await ctx.send("This currency does not exist.")
            return

        config_id = exchange_rates[currency_name]["config_id"]
        mini_currency_config = Config.get_conf(None, identifier=config_id, force_registration=True)
        
        # Retrieve user's current balance
        user_balance = await mini_currency_config.user(user).get_raw(currency_name, default=0)
        new_balance = user_balance + amount

        # Update balance
        await mini_currency_config.user(user).set_raw(currency_name, value=new_balance)

        await ctx.send(f"Added `{amount}` `{currency_name}` to {user.mention}. New balance: `{new_balance}`.")

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def add_currency(self, ctx, currency_name: str, config_id: int, rate: float):
        """Add a new mini-currency with its config ID and exchange rate."""
        currency_name = currency_name.lower().replace(" ","_")
        async with self.config.guild(ctx.guild).exchange_rates() as exchange_rates:
            exchange_rates[currency_name] = {"config_id": config_id, "rate": rate}
        await ctx.send(f"Added `{currency_name}` with exchange rate `{rate}` from config `{config_id}`.")

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def remove_currency(self, ctx, currency_name: str):
        """Remove a mini-currency from the exchange list."""
        currency_name = currency_name.lower().replace(" ","_")
        async with self.config.guild(ctx.guild).exchange_rates() as exchange_rates:
            if currency_name not in exchange_rates:
                await ctx.send("This currency does not exist.")
                return
            del exchange_rates[currency_name]
        await ctx.send(f"Removed `{currency_name}` from the exchange list.")

    @commands.guild_only()
    @commands.command()
    async def exchange(self, ctx, currency_name: str, amount: int):
        """Convert a mini-currency into WellCoins."""
        currency_name = currency_name.lower().replace(" ","_")
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()
        
        if currency_name not in exchange_rates:
            await ctx.send("This currency is not available for exchange.")
            return

        config_id = exchange_rates[currency_name]["config_id"]
        rate = exchange_rates[currency_name]["rate"]
        mini_currency_config = Config.get_conf(None, identifier=config_id)
        user_balance = await mini_currency_config.user(ctx.author).get_raw(currency_name, default=0)

        if user_balance < amount:
            await ctx.send("You do not have enough of this currency.")
            return

        new_wellspring_coins = int(amount * rate)
        
        # Deduct from mini-currency
        await mini_currency_config.user(ctx.author).set_raw(currency_name, value=user_balance - amount)
        
        # Add to master currency
        master_balance = await self.config.user(ctx.author).master_balance()
        await self.config.user(ctx.author).master_balance.set(master_balance + new_wellspring_coins)
        
        await ctx.send(f"Exchanged `{amount}` `{currency_name}` for `{new_wellspring_coins}` WellCoins!")

    @commands.guild_only()
    @commands.command()
    async def balance(self, ctx, currency_name: str = None):
        """Check your balance of WellCoins or a specific mini-currency."""
        user_data = self.config.user(ctx.author)
        
        if currency_name is None:
            balance = await user_data.master_balance()
            bank = await user_data.bank_total()
            currency = await self.config.guild(ctx.guild).master_currency_name()
            
            msg = f"💰 You have `{balance}` {currency} on hand."
            if bank > 0:
                msg += f"\n🏦 You have `{bank}` {currency} in your hole in the ground."
    
            await ctx.send(msg)
        else:
            currency_name = currency_name.lower().replace(" ", "_")
            exchange_rates = await self.config.guild(ctx.guild).exchange_rates()
    
            if currency_name not in exchange_rates:
                await ctx.send("❌ This currency does not exist.")
                return
    
            config_id = exchange_rates[currency_name]["config_id"]
            mini_currency_config = Config.get_conf(None, identifier=config_id, force_registration=True)
            user_balance = await mini_currency_config.user(ctx.author).get_raw(currency_name, default=0)
    
            await ctx.send(f"💱 You have `{user_balance}` `{currency_name}`.")


    @commands.guild_only()
    @commands.command()
    async def rates(self, ctx):
        """View current exchange rates."""
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()
        if not exchange_rates:
            await ctx.send("No currencies have been added yet.")
            return
        
        embed = discord.Embed(title="Exchange Rates", color=discord.Color.blue())
        for currency, data in exchange_rates.items():
            embed.add_field(name=currency, value=f"Rate: 1 {currency} will get you `{data['rate']}` Wellcoins (Config: `{data['config_id']}`)", inline=False)
        
        embed.add_field(name="How to get the various currencies", value="**Gold** Comes from Hunger Games! Join us every Saturday\n\n**Credits** come from recruiting, if you are instread in joining our recruiting force please reach out to 9006! ", inline=False)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def set_rate(self, ctx, currency_name: str, rate: float):
        """Change the exchange rate for a mini-currency."""
        currency_name = currency_name.lower().replace(" ","_")
        async with self.config.guild(ctx.guild).exchange_rates() as exchange_rates:
            if currency_name not in exchange_rates:
                await ctx.send("That currency does not exist.")
                return
            exchange_rates[currency_name]["rate"] = rate
        await ctx.send(f"Updated `{currency_name}` exchange rate to `{rate}`.")

    @commands.guild_only()
    @commands.command()
    async def debug_currency(self, ctx, currency_name: str):
        """Dump everything related to a given currency's config."""
        currency_name = currency_name.lower().replace(" ", "_")
        
        # Check if the currency exists
        exchange_rates = await self.config.guild(ctx.guild).exchange_rates()
        if currency_name not in exchange_rates:
            await ctx.send(f"Currency `{currency_name}` does not exist.")
            return
    
        # Retrieve the correct config_id
        config_id = exchange_rates[currency_name]["config_id"]
        mini_currency_config = Config.get_conf(None, identifier=config_id, force_registration=True)
    
        # Retrieve all stored data in this Config space
        try:
            all_data = await mini_currency_config.all()
            all_user_data = await mini_currency_config.all_users()
            all_member_data = await mini_currency_config.all_members()
        except Exception as e:
            await ctx.send(f"Error retrieving data: {e}")
            return
    
        # Format the data for debugging
        embed = discord.Embed(title=f"Debugging `{currency_name}`", color=discord.Color.red())
        embed.add_field(name="Stored Config ID", value=f"`{config_id}`", inline=False)
        
        if all_data:
            embed.add_field(name="Global Config Data", value=f"```{str(all_data)[:1000]}```", inline=False)
        else:
            embed.add_field(name="Global Config Data", value="No data found.", inline=False)
    
        if all_user_data:
            embed.add_field(name="User-Level Data", value=f"```{str(all_user_data)[:1000]}```", inline=False)
        else:
            embed.add_field(name="User-Level Data", value="No user data found.", inline=False)
    
        if all_member_data:
            embed.add_field(name="Member-Level Data", value=f"```{str(all_member_data)[:1000]}```", inline=False)
        else:
            embed.add_field(name="Member-Level Data", value="No member data found.", inline=False)
    
        await ctx.send(embed=embed)


    def parse_cards(self, xml_data, season, categories):
        root = ET.fromstring(xml_data)
        cards = []
        for card in root.findall(".//CARD"):
            card_season = int(card.find("SEASON").text)
            card_category = card.find("CATEGORY").text
            if str(card_season) in str(season) and card_category in categories:
                card_id = card.find("CARDID").text
                cards.append(
                    {"id": card_id, "season": card_season, "category": card_category}
                )
        return cards

    def parse_card_info(self, xml_data):
        root = ET.fromstring(xml_data)
        return {
            "name": root.find("NAME").text,
            "market_value": root.find("MARKET_VALUE").text
        }

    def parse_token(self, xml_data):
        root = ET.fromstring(xml_data)
        token = root.find("SUCCESS")
        return token.text if token is not None else None

    def get_embed_color(self, category):
        colors = {
            "COMMON": 0x808080,       # Grey
            "UNCOMMON": 0x00FF00,     # Green
            "RARE": 0x0000FF,         # Blue
            "ULTRA-RARE": 0x800080,   # Purple
            "EPIC": 0xFFA500,         # Orange
            "LEGENDARY": 0xFFFF00     # Yellow
        }
        return colors.get(category.upper(), 0xFFFFFF)  # Default to white if not found

    @commands.guild_only()
    @commands.command(name="richest")
    async def richest(self, ctx):
        """Display the top 3 richest users in WellCoins."""
        
        # Get all user balances
        all_users = await self.config.all_users()
        
        # Extract users and balances
        balances = [(ctx.guild.get_member(user_id), data.get("master_balance", 0)) for user_id, data in all_users.items()]
        
        # Filter out users who are not in the server (None values)
        balances = [(user, balance) for user, balance in balances if user is not None]
        
        # Sort users by balance in descending order
        top_users = sorted(balances, key=lambda x: x[1], reverse=True)[:3]
        
        # Create an embed to display results
        embed = discord.Embed(title="🏆 Top 3 Richest Users 🏆", color=discord.Color.gold())
        
        if not top_users:
            embed.description = "No users have any WellCoins yet."
        else:
            for rank, (user, balance) in enumerate(top_users, start=1):
                embed.add_field(name=f"#{rank} {user.display_name}", value=f"💰 `{balance}` WellCoins", inline=False)
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Reward users for chatting."""

        if len(message.content.strip()) < await self.config.guild(message.guild).min_message_length():
            return  # Ignore low-effort messages
         
        if message.channel.id == 1098668923345448970:
            guild = message.guild
            count = await self.config.guild(guild).Message_count_spam()
            await self.config.guild(guild).Message_count_spam.set(count+1)
            if count % 100 == 0:
                ad_text = self.get_random_ad()
                if ad_text:
                    try:
                        await message.channel.send(ad_text)
                    except discord.Forbidden:
                        print(f"Missing permissions to send messages in {channel.id}")
            
        if message.channel.id == 1098644885797609495:
            guild = message.guild
            count = await self.config.guild(guild).Message_count()
            await self.config.guild(guild).Message_count.set(count+1)
            if count % 50 == 0:
                ad_text = self.get_random_ad()
                if ad_text:
                    try:
                        await message.channel.send(ad_text)
                         #end of daily Loops stuff
                    except discord.Forbidden:
                        print(f"Missing permissions to send messages in {channel.id}")
        
        if message.author.bot or not message.guild:
            return  # Ignore bot messages and DMs

        if message.guild.id != 1098644885797609492:
            return  # Ignore messages from other servers

        if len(message.content.strip()) < await self.config.guild(message.guild).min_message_length():
            return  # Ignore low-effort messages
        
        
        user = message.author
        guild = message.guild
        channel = message.channel
        # Fetch config settings
        xp_per_message = await self.config.guild(guild).xp_per_message()
        coins_per_message = await self.config.guild(guild).coins_per_message()
        cooldown_time = await self.config.guild(guild).message_cooldown()
        blacklisted_channels = await self.config.guild(guild).blacklisted_channels()
        

        # Check cooldown
        last_message_time = await self.config.user(user).last_message_time()
        current_time = datetime.utcnow().timestamp()
        
        if current_time - last_message_time < cooldown_time:
            return  # On cooldown, no rewards
        
        # Grant XP (always given)
        user_xp = await self.config.user(user).xp()
        await self.config.user(user).xp.set(user_xp + xp_per_message)

        
        # Grant WellCoins if the channel is NOT blacklisted
        if channel.id not in blacklisted_channels:
            user_balance = await self.config.user(user).master_balance()
            await self.config.user(user).master_balance.set(user_balance + coins_per_message)
            # 10% chance to add a green check mark reaction
            if random.random() < 0.10:
                await message.add_reaction("💰")          
            # Update last message time
            await self.config.user(user).last_message_time.set(current_time)
    
    @commands.guild_only()
    @commands.admin()
    @commands.group()
    async def chatrewards(self, ctx):
        """Manage chat-based rewards."""
        pass
    
    @chatrewards.command()
    async def setxp(self, ctx, xp: int):
        """Set the amount of XP gained per message."""
        await self.config.guild(ctx.guild).xp_per_message.set(xp)
        await ctx.send(f"XP per message set to {xp}.")
    
    @chatrewards.command()
    async def setcoins(self, ctx, coins: int):
        """Set the amount of WellCoins gained per valid message."""
        await self.config.guild(ctx.guild).coins_per_message.set(coins)
        await ctx.send(f"WellCoins per message set to {coins}.")
    
    @chatrewards.command()
    async def setcooldown(self, ctx, seconds: int):
        """Set the cooldown time in seconds before users can earn again."""
        await self.config.guild(ctx.guild).message_cooldown.set(seconds)
        await ctx.send(f"Message reward cooldown set to {seconds} seconds.")
    
    @chatrewards.command()
    async def blacklist(self, ctx, channel: discord.TextChannel):
        """Blacklist a channel from earning WellCoins."""
        async with self.config.guild(ctx.guild).blacklisted_channels() as blacklisted_channels:
            if channel.id not in blacklisted_channels:
                blacklisted_channels.append(channel.id)
                await ctx.send(f"{channel.mention} has been blacklisted from earning WellCoins.")
            else:
                await ctx.send(f"{channel.mention} is already blacklisted.")
    
    @chatrewards.command()
    async def unblacklist(self, ctx, channel: discord.TextChannel):
        """Remove a channel from the blacklist."""
        async with self.config.guild(ctx.guild).blacklisted_channels() as blacklisted_channels:
            if channel.id in blacklisted_channels:
                blacklisted_channels.remove(channel.id)
                await ctx.send(f"{channel.mention} has been removed from the blacklist.")
            else:
                await ctx.send(f"{channel.mention} is not blacklisted.")
    
    @chatrewards.command()
    async def viewsettings(self, ctx):
        """View current chat reward settings."""
        settings = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(title="Chat Reward Settings", color=discord.Color.blue())
        embed.add_field(name="XP per Message", value=f"{settings['xp_per_message']}")
        embed.add_field(name="WellCoins per Message", value=f"{settings['coins_per_message']}")
        embed.add_field(name="Cooldown Time", value=f"{settings['message_cooldown']} seconds")
        embed.add_field(name="Blacklisted Channels", value=f"{', '.join([f'<#{cid}>' for cid in settings['blacklisted_channels']])}" if settings['blacklisted_channels'] else "None")
        await ctx.send(embed=embed)
    
    @chatrewards.command()
    async def setminlength(self, ctx, length: int):
        """Set the minimum message length required to earn rewards."""
        await self.config.guild(ctx.guild).min_message_length.set(length)
        await ctx.send(f"Minimum message length set to {length} characters.")

    @commands.command()
    async def linknation(self, ctx, *nation_name: str):
        """Link your NationStates nation to your Discord account."""
        verify_url = f"https://www.nationstates.net/page=verify_login"
        await ctx.send(f"To verify your NationStates nation, visit {verify_url} and copy the code in the box.")
        await ctx.send(f"Then, DM me the following command to complete verification: `!verifynation <nation_name> <code>` \n For example `!verifynation {'_'.join(nation_name).replace('<','').replace('>','')} FWIXlb2dPZCHm1rq-4isM94FkCJ4RGPUXcjrMjFHsIc`")
    
    @commands.command()
    async def verifynation(self, ctx, nation_name: str, code: str):
        """Verify the NationStates nation using the provided verification code."""
        formatted_nation = nation_name.lower().replace(" ", "_")
    
        # Verify with NationStates API
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.nationstates.net/cgi-bin/api.cgi?a=verify&nation={formatted_nation}&checksum={code}",
                headers={"User-Agent": self.USER_AGENT}
            ) as response:
                result = await response.text()
                if result.strip() != "1":
                    await ctx.send("❌ Verification failed. Make sure you entered the correct code and try again.")
                    return
    
        # Save nation to user config if not already linked
        async with self.config.user(ctx.author).linked_nations() as nations:
            if formatted_nation not in nations:
                nations.append(formatted_nation)
    
        # Fetch residents from API
        async with aiohttp.ClientSession() as session:
            async with session.get(self.API_URL, headers={"User-Agent": self.USER_AGENT}) as response:
                if response.status != 200:
                    await ctx.send("Failed to retrieve residents. Try again later.")
                    return
    
                xml_data = await response.text()
                start_tag, end_tag = "<NATIONS>", "</NATIONS>"
                start_index = xml_data.find(start_tag) + len(start_tag)
                end_index = xml_data.find(end_tag)
                resident_list_raw = xml_data[start_index:end_index].split(":")
                residents = [n.strip().lower() for n in resident_list_raw if n]
    
        # Guild and Roles
        guild = self.bot.get_guild(1098644885797609492)  # Your server ID
        if not guild:
            await ctx.send("❌ Verification failed. Could not find the server.")
            return
    
        member = guild.get_member(ctx.author.id)
        if not member:
            await ctx.send("❌ You are not a member of the verification server.")
            return
    
        resident_role = guild.get_role(1098645868162338919)     # Resident role
        nonresident_role = guild.get_role(1098673447640518746)  # Visitor role
    
        if not resident_role or not nonresident_role:
            await ctx.send("❌ One or more roles not found. Please check the role IDs.")
            return
    
        # Assign roles based on residency
        if formatted_nation in residents:
            if resident_role not in member.roles:
                await member.add_roles(resident_role)
                await ctx.send("✅ You have been given the resident role.")
            if nonresident_role in member.roles:
                await member.remove_roles(nonresident_role)
        else:
            if nonresident_role not in member.roles:
                await member.add_roles(nonresident_role)
                await ctx.send("✅ You have been given the visitor role.")
            if resident_role in member.roles:
                await member.remove_roles(resident_role)
    
        await ctx.send(f"✅ Successfully linked your NationStates nation: **{nation_name}**")


    
    @commands.command()
    async def mynation(self, ctx, user: discord.Member = None):
        """Check which NationStates nation is linked to a Discord user."""
        user = user or ctx.author
        nations = await self.config.user(user).linked_nations()
        if nations:
            # Format each nation as a Discord hyperlink
            nation_list = "\n".join(
                f"[{n.replace('_', ' ').title()}](https://www.nationstates.net/nation={n})" for n in nations
            )
            await ctx.send(f"🌍 {user.display_name}'s linked NationStates nation(s):\n{nation_list}")
        else:
            await ctx.send(f"❌ {user.display_name} has not linked a NationStates nation yet.")

    
    
    @commands.command()
    async def unlinknation(self, ctx, nation_name: str):
        """Unlink a specific NationStates nation from your Discord account."""
        nation_name = nation_name.lower().replace(" ","_")
        async with self.config.user(ctx.author).linked_nations() as nations:
            if nation_name in nations:
                nations.remove(nation_name)
                await ctx.send(f"✅ Successfully unlinked the NationStates nation: **{nation_name}**")
            else:
                await ctx.send(f"❌ You do not have **{nation_name}** linked to your account.")

    @commands.guild_only()
    @commands.command()
    async def pay(self, ctx, recipient: discord.Member, amount: int):
        """Transfer WellCoins to another player."""
        if amount <= 0:
            await ctx.send("❌ Amount must be greater than zero.")
            return

        sender_balance = await self.config.user(ctx.author).master_balance()
        if sender_balance < amount:
            await ctx.send(f"❌ You do not have enough WellCoins to complete this transaction. You only have {sender_balance} WellCoins")
            return

        recipient_balance = await self.config.user(recipient).master_balance()
        await self.config.user(ctx.author).master_balance.set(sender_balance - amount)
        await self.config.user(recipient).master_balance.set(recipient_balance + amount)

        await ctx.send(f"✅ {ctx.author.mention} has sent `{amount}` WellCoins to {recipient.mention}!")


    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def govpay(self, ctx, user: discord.Member, amount: int):
        """The government distributes WellCoins to a user."""
        if amount <= 0:
            await ctx.send("❌ Amount must be greater than zero.")
            return

        user_balance = await self.config.user(user).master_balance()
        await self.config.user(user).master_balance.set(user_balance + amount)
        await ctx.send(f"🏛️ Gob The great has issued `{amount}` WellCoins to {user.mention}!")

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def fine(self, ctx, user: discord.Member, amount: int):
        """Fine a user a specific amount of WellCoins."""
        if amount <= 0:
            await ctx.send("❌ Fine amount must be greater than zero.")
            return

        user_balance = await self.config.user(user).master_balance()
        if user_balance < amount:
            await ctx.send(f"❌ {user.mention} does not have enough WellCoins to pay the fine of `{amount}`.")
            return

        await self.config.user(user).master_balance.set(user_balance - amount)
        await ctx.send(f"🚨 {user.mention} has been fined `{amount}` WellCoins by Gob on behalf the goverment!")
    
    async def update_wellcoin_snapshots(self, total_wellcoins):
        """Updates daily and weekly WellCoin snapshots"""
        last_daily = await self.config.daily_wellcoins()
        last_weekly = await self.config.weekly_wellcoins()
    
        # If it's a new day, update the daily snapshot
        today = datetime.utcnow().date()
        last_update = datetime.utcfromtimestamp(await self.config.get_raw("last_update", default=0)).date()
    
        if today > last_update:
            await self.config.daily_wellcoins.set(total_wellcoins)
            await self.config.set_raw("last_update", value=int(datetime.utcnow().timestamp()))
        
        # If it's a new week, update the weekly snapshot
        last_weekly_update = datetime.utcfromtimestamp(await self.config.get_raw("last_weekly_update", default=0)).date()
        if (today - last_weekly_update).days >= 7:
            await self.config.weekly_wellcoins.set(total_wellcoins)
            await self.config.set_raw("last_weekly_update", value=int(datetime.utcnow().timestamp()))


    @commands.command()
    @commands.admin()
    async def dump_users(self, ctx):
        """Dump all user data from config into a JSON file."""
        all_users = await self.config.all_users()
    
        if not all_users:
            await ctx.send("No user data found.")
            return
    
        # Create a filename with timestamp
        filename = f"user_dump_{datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')}.json"
    
        # Save data to a file
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(all_users, f, indent=4)
    
        # Send file to Discord
        await ctx.send(file=discord.File(filename))
    
    @commands.command()
    @commands.admin()
    async def fix_linked_nations(self, ctx):
        """Normalize all linked nations by making them lowercase and replacing spaces with underscores."""
        all_users = await self.config.all_users()
        updated_count = 0
    
        for user_id, data in all_users.items():
            linked_nations = data.get("linked_nations", [])
            if linked_nations:
                # Normalize each nation name
                normalized_nations = [nation.lower().replace(" ", "_") for nation in linked_nations]
                await self.config.user_from_id(user_id).linked_nations.set(normalized_nations)
                updated_count += 1
    
        await ctx.send(f"✅ Updated linked nations for {updated_count} users.")


    @commands.guild_only()
    @commands.admin()
    @commands.command(name="setwelcome")
    async def set_welcome_message(self, ctx, *, message: str):
        """Set the welcome message for new members."""
        await self.config.guild(ctx.guild).welcome_message.set(message)
        await ctx.send(f"✅ Welcome message has been set to:\n\n{message}")

    @commands.guild_only()
    @commands.admin()
    @commands.command(name="setwelcomechannel")
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel where the welcome message will be sent."""
        await self.config.guild(ctx.guild).welcome_channel.set(channel.id)
        await ctx.send(f"✅ Welcome messages will be sent in {channel.mention}.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        welcome_message = await self.config.guild(guild).welcome_message()
        welcome_channel_id = await self.config.guild(guild).welcome_channel()
        
        if not welcome_message:
            return  # No welcome message set
    
        # Format placeholders (e.g., {user}, {mention})
        formatted_message = welcome_message.replace("{user}", member.name).replace("{mention}", member.mention)
    
        if welcome_channel_id:
            channel = guild.get_channel(welcome_channel_id)
        else:
            # Default to system channel or first text channel
            channel = guild.system_channel or discord.utils.get(guild.text_channels, permissions__send_messages=True)
    
        if channel:
            try:
                await channel.send(formatted_message)
            except discord.Forbidden:
                print(f"Missing permissions to send messages in {channel.id}")

    
    
    @commands.guild_only()
    @commands.admin()
    @commands.command(name="viewwelcome")
    async def view_welcome_message(self, ctx):
        """View the current welcome message."""
        message = await self.config.guild(ctx.guild).welcome_message()
        channel_id = await self.config.guild(ctx.guild).welcome_channel()
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
    
        if not message:
            await ctx.send("No welcome message set.")
            return
    
        await ctx.send(f"📜 Welcome Message:\n{message}\n\n📢 Channel: {channel.mention if channel else 'Default system/first available channel'}")

    @commands.guild_only()
    @commands.admin()
    @commands.command(name="dropnation")
    async def drop_nation(self, ctx, nation_name: str):
        """Admin command to remove a nation from all users' linked nations."""
        formatted_nation = nation_name.lower().replace(" ", "_")
        all_users = await self.config.all_users()
        dropped_count = 0
    
        for user_id, data in all_users.items():
            linked_nations = data.get("linked_nations", [])
            if formatted_nation in linked_nations:
                linked_nations.remove(formatted_nation)
                await self.config.user_from_id(user_id).linked_nations.set(linked_nations)
                dropped_count += 1
    
        await ctx.send(f"✅ Nation `{formatted_nation}` was removed from `{dropped_count}` user(s)' linked nations.")
    
    @commands.command()
    @commands.guild_only()
    async def xpleaderboard(self, ctx):
        """Show the top 10 users with the most XP."""
        all_users = await self.config.all_users()
        xp_data = []
    
        for user_id, data in all_users.items():
            xp = data.get("xp", 0)
            if xp > 0:
                xp_data.append((user_id, xp))
    
        if not xp_data:
            return await ctx.send("No XP data found!")
    
        # Sort by XP descending and grab top 10
        top_users = sorted(xp_data, key=lambda x: x[1], reverse=True)[:10]
    
        embed = discord.Embed(
            title="🏆 XP Leaderboard",
            description="Top 10 users with the most XP",
            color=discord.Color.gold()
        )
    
        for i, (user_id, xp) in enumerate(top_users, start=1):
            user = self.bot.get_user(int(user_id)) or f"<@{user_id}>"
            embed.add_field(name=f"#{i}", value=f"{user} — `{xp}` XP", inline=False)
    
        await ctx.send(embed=embed)







