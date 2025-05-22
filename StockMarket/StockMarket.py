import discord
from redbot.core import commands, Config
from discord.ext import tasks
import random
import matplotlib.pyplot as plt
import io
from discord import File
from discord import app_commands
from discord.ui import View, Button
from discord import Interaction
import aiohttp
import xml.etree.ElementTree as ET
import datetime


class StockListView(View):
    def __init__(self, cog, stocks, per_page=10):
        super().__init__(timeout=120)
        self.cog = cog
        self.stocks = stocks
        self.per_page = per_page
        self.page = 0
        self.message = None

    async def update_embed(self):
        embed = discord.Embed(
            title="📊 Available Stocks",
            description=f"Page {self.page + 1}/{(len(self.stocks) - 1) // self.per_page + 1}",
            color=discord.Color.green()
        )

        start = self.page * self.per_page
        end = start + self.per_page
        for name, data in self.stocks[start:end]:
            emoji = "🛂 " if data.get("commodity", False) else ""
            buys = data.get("buys", 0)
            sells = data.get("sells", 0)
            buy_remaining = 100 - (buys % 100)
            sell_remaining = 100 - (sells % 100)
            embed.add_field(
                name=f"{emoji}{name}",
                value=(
                    f"Price: {data['price']:.2f} Wellcoins\n"
                    f"🟢 {buy_remaining} shares until next price **increase**\n"
                    f"🔴 {sell_remaining} shares until next price **decrease**"
                ),
                inline=False
            )   

        await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_embed()
            await interaction.response.defer()

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (self.page + 1) * self.per_page < len(self.stocks):
            self.page += 1
            await self.update_embed()
            await interaction.response.defer()

    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=None)



class StockMarket(commands.Cog):
    """
    StockMarket Commands:
    - createstock: Create a new stock (optionally mark as a commodity)
    - liststocks: List all available stocks with their prices
    - buystock: Buy shares of a stock
    - sellstock: Sell shares of a stock
    - viewstock: View details about a specific stock
    - myportfolio: View your stock holdings and net change
    - stockchart: View a historical price chart of a stock
    """

    async def cog_unload(self):
        self.bot.tree.remove_command(self.buystock.name)
        self.bot.tree.remove_command(self.sellstock.name)
    
    async def stock_name_autocomplete(self, interaction: discord.Interaction, current: str):
        stocks = await self.config.stocks()
        choices = []
    
        for name, data in stocks.items():
            if data.get("delisted"):
                continue  # ✅ Skip delisted stocks
            if current.lower() not in name.lower():
                continue
            label = f"{name} - {data['price']:.2f} WC"
            if data.get("commodity"):
                label += " [Commodity]"
            choices.append(app_commands.Choice(name=label, value=name.upper()))
    
        return choices[:25]



    
        


    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="SM9003", force_registration=True)
        self.economy_config = Config.get_conf(None, identifier=345678654456, force_registration=False)
        self.config.register_user(stocks={}, avg_buy_prices={})
        self.config.register_global(
            stocks={},
            tags={},
            announcement_channel=None,
            last_commodity_update=None
        )
        self.last_day_trades = 0.0  # ✅ Add this line

        self.price_updater.start()

    def cog_unload(self):
        self.price_updater.cancel()

    @tasks.loop(hours=1)
    async def price_updater(self):
        self._hourly_start_prices = {}
        async with self.config.stocks() as stocks:
            for name, data in stocks.items():
                if data.get("delisted", False):
                    continue
                self._hourly_start_prices[name] = data["price"]  # 🟢 FIXED: Now inside the loop
    
        await self.recalculate_all_stock_prices()
        await self.apply_daily_commodity_price_update()
    
        # Build gainers list based on start-of-hour prices
        gainers = []
        stocks = await self.config.stocks()
        for name, data in stocks.items():
            if data.get("delisted", False):
                continue
            start_price = self._hourly_start_prices.get(name)
            end_price = data["price"]
            if start_price and start_price > 0:
                change = ((end_price - start_price) / start_price) * 100
                gainers.append((name, change))
    
        # Sort and announce
        if gainers:
            top_3 = sorted(gainers, key=lambda x: x[1], reverse=True)[:3]
            message = "**📈 Top 3 Gainers This Hour:**\n" + "\n".join(
                f"**{name}**: + {change:.2f}%" for name, change in top_3
            )
            channel_id = await self.config.announcement_channel()
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(message)



    async def apply_daily_commodity_price_update(self):
        last_run_timestamp = await self.config.last_commodity_update()
        now = datetime.datetime.utcnow()
    
        if last_run_timestamp:
            last_run = datetime.datetime.fromisoformat(last_run_timestamp)
            if (now - last_run).total_seconds() < 86400:
                return
    
        if not hasattr(self, "_today_target_hour"):
            self._today_target_hour = random.randint(0, 23)
    
        if now.hour != self._today_target_hour:
            return
    
        # --- Fetch Census Scale History ---
        scales = [
            10, 13, 17, 19, 20, 24, 25, 26, 28, 29, 33,
            48, 51, 52, 55, 56, 57, 59, 60, 61, 62, 63,
            70, 79, 85, 86, 87, 88, 7
        ]
        scale_param = "+".join(map(str, scales))
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?region=the_wellspring&q=census&mode=history&scale={scale_param}"
        headers = {"User-Agent": "9005 StockBot (Contact: NSwa9002@gmail.com)"}
    
        percent_changes = {}
    
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
                root = ET.fromstring(text)
    
                for scale in root.findall("CENSUS/SCALE"):
                    scale_id = scale.attrib["id"]
                    points = scale.findall("POINT")
                    if len(points) >= 8:
                        old_score = float(points[-8].find("SCORE").text)
                        new_score = float(points[-1].find("SCORE").text)
                        if old_score != 0:
                            percent_change = ((new_score - old_score) / old_score) * 100
                            percent_changes[scale_id] = percent_change
    
        commodity_influence = {
            "crude_oil": {"20": 0.4, "26": 0.3, "10": 0.2, "59": 0.1, "7": -0.5},
            "gold": {"51": 0.5, "70": 0.2, "86": 0.3, "79": 0.3, "52": -0.4, "33": -0.2, "28": -0.1},
            "silver": {"70": 0.4, "13": 0.3, "24": 0.2, "86": 0.2, "33": -0.2},
            "platinum": {"70": 0.3, "10": 0.3, "13": 0.2, "88": 0.1, "33": -0.2},
            "copper": {"13": 0.3, "26": 0.3, "20": 0.3, "57": 0.2, "7": -0.4},
            "corn": {"17": 0.5, "88": 0.3, "60": 0.2, "63": 0.1, "61": -0.2, "29": -0.3},
            "wheat": {"17": 0.4, "88": 0.3, "28": 0.2, "61": -0.3, "29": -0.2},
            "coffee_beans": {"13": 0.2, "56": 0.2, "55": 0.3, "88": 0.2, "87": 0.1, "7": -0.2},
            "sugar": {"60": 0.4, "61": 0.3, "88": 0.2, "25": 0.2, "29": -0.3, "28": -0.2},
            "wandwood": {"19": 0.4, "63": 0.3, "55": 0.3, "86": 0.3, "62": -0.3, "52": -0.1}
        }
    
        async with self.config.stocks() as stocks:
            for stock_name, data in stocks.items():
                if not data.get("commodity", False):
                    continue
    
                name_key = stock_name.lower().replace(" ", "_")
                influences = commodity_influence.get(name_key)
                if not influences:
                    continue
    
                # Calculate percent delta
                percent_delta = sum(
                    percent_changes.get(scale_id, 0) * weight for scale_id, weight in influences.items()
                )
    
                # Clamp percent change between -5% and +5%
                percent_delta = max(-5.0, min(percent_delta, 5.0))
    
                old_price = data["price"]
                new_price = round(old_price * (1 + percent_delta / 100), 2)
                new_price = max(1.0, new_price)
    
                percent_change = ((new_price - old_price) / old_price) * 100 if old_price > 0 else 0
                if percent_change > 3:
                    channel_id = await self.config.announcement_channel()
                    if channel_id:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(f"🌾 **{stock_name}** commodity surged by **{percent_change:.2f}%** today!")
    
                if "history" not in data:
                    data["history"] = []
                data["history"].append(new_price)
                if len(data["history"]) > 24 * 365 * 2:
                    data["history"] = data["history"][-24 * 365 * 2:]
    
                data["price"] = new_price
    
        await self.config.last_commodity_update.set(now.isoformat())

    
    async def recalculate_all_stock_prices(self):
        async with self.config.stocks() as stocks:
            tag_multipliers = await self.config.tags()
            to_delist = []
            gainers = []
    
            for stock_name, data in stocks.items():
                if data.get("delisted", False):
                    continue
    
                old_price = data["price"]
                tag_bonus = 0
    
                for tag, weight in data.get("tags", {}).items():
                    flat_increase = tag_multipliers.get(tag, 0)
                    tag_bonus += flat_increase * weight
    
                # Base percent change
                if isinstance(data.get("volatility"), (list, tuple)) and len(data["volatility"]) == 2:
                    base_percent = random.uniform(data["volatility"][0], data["volatility"][1])
                else:
                    base_percent = random.uniform(-2, 2)
    
                # Market activity influence
                market_change = 0.01 * (self.last_day_trades / 1000)
                market_change = max(-0.1, min(market_change, 0.11))  # Clamp between -10% and +11%
    
                # Final percent change calculation
                total_percent_change = base_percent + tag_bonus + (market_change * 100)
                new_price = round(old_price * (1 + total_percent_change / 100), 2)
    
                # Bankruptcy/delist logic
                if data.get("commodity", False):
                    new_price = max(1.0, new_price)
                else:
                    if new_price <= 0:
                        if random.random() < 0.5:
                            new_price = 0.01
                            await self._announce_recovery(stock_name)
                        else:
                            to_delist.append(stock_name)
                            await self._announce_bankruptcy(stock_name)
                        continue
    
                new_price = max(0.01, new_price)
    
                # History tracking
                if "history" not in data:
                    data["history"] = []
                data["history"].append(new_price)
                if len(data["history"]) > 24 * 365 * 2:
                    data["history"] = data["history"][-24 * 365 * 2:]
    
                # Save new price
                data["price"] = new_price
                data["buys"] = random.randint(1, 99)
                data["sells"] = random.randint(1, 99)
    
                # Track for top gainers
                if old_price > 0:
                    percent_change = ((new_price - old_price) / old_price) * 100
                    if percent_change > 3:
                        await self._announce_surge(stock_name, percent_change)
                    gainers.append((stock_name, percent_change))
    
            # Finalize delistings
            for stock_name, data in stocks.items():
                if data.get("delisted", False):
                    data["price"] = 0.0
    
            for stock_name in to_delist:
                if stock_name in stocks:
                    stocks[stock_name]["delisted"] = True
                    stocks[stock_name]["price"] = 0.0
    
            self.last_day_trades = 0
            
    # Helper announcement methods
    async def _announce_surge(self, stock_name, percent_change):
        channel_id = await self.config.announcement_channel()
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"🚀 **{stock_name}** surged by **{percent_change:.2f}%** this hour!")
    
    async def _announce_recovery(self, stock_name):
        channel_id = await self.config.announcement_channel()
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"**{stock_name}** narrowly avoided bankruptcy and is now trading at **0.01 WC**!")
    
    async def _announce_bankruptcy(self, stock_name):
        channel_id = await self.config.announcement_channel()
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"💀 **{stock_name}** has gone bankrupt and been delisted!")




    @commands.command()
    @commands.has_permissions(administrator=True)
    async def createstock(self, ctx, name: str, starting_price: float, min_volatility: int = -2, max_volatility: int = 2, commodity: bool = False):
        """Create a new stock. Optionally set volatility and mark as a commodity."""
        name = name.upper()
        async with self.config.stocks() as stocks:
            if name in stocks:
                return await ctx.send("Stock already exists.")
            stocks[name] = {
                "price": round(starting_price, 2),
                "tags": {},
                "buys": 0,
                "sells": 0,
                "commodity": commodity
            }
            if min_volatility is not None and max_volatility is not None:
                stocks[name]["volatility"] = [min_volatility, max_volatility]
        await ctx.send(f"Stock {name} created with starting price {starting_price:.2f} Wellcoins.")

    @app_commands.command(name="viewstock", description="View details about a specific stock.")
    @app_commands.autocomplete(name=stock_name_autocomplete)
    async def viewstock(self, interaction: discord.Interaction, name: str):
        name = name.upper()
        stocks = await self.config.stocks()
        stock = stocks.get(name)
    
        if not stock or stock.get("delisted", False):
            return await interaction.response.send_message("❌ That stock does not exist or is delisted.", ephemeral=True)
    
        price = stock["price"]
        buys = stock.get("buys", 0)
        sells = stock.get("sells", 0)
        buy_remaining = 100 - (buys % 100)
        sell_remaining = 100 - (sells % 100)
    
        embed = discord.Embed(title=f"📄 Stock Info: {name}", color=discord.Color.blue())
        embed.add_field(name="💰 Price", value=f"{price:.2f} Wellcoins", inline=True)
        embed.add_field(name="📈 Shares to Next Increase", value=f"{buy_remaining}", inline=True)
        embed.add_field(name="📉 Shares to Next Decrease", value=f"{sell_remaining}", inline=True)
        # Display tags if any
        tags = stock.get("tags", {})
        if tags:
            tag_str = "\n".join(f"`{tag}` (weight {weight})" for tag, weight in tags.items())
            embed.add_field(name="🏷️ Tags", value=tag_str, inline=False)

        history = stock.get("history", [])
        if history and len(history) > 1 and history[-2] > 0:
            change = ((history[-1] - history[-2]) / history[-2]) * 100
            embed.add_field(name="Last Hour Change", value=f"{change:+.2f}%", inline=True)
    
        # Gather stock ownership data
        owners_data = await self.config.all_users()
        owners = {}
        total_held = 0
        for user_id, user_data in owners_data.items():
            user_stocks = user_data.get("stocks", {})
            if user_stocks.get(name, 0) > 0:
                amount = user_stocks[name]
                owners[user_id] = amount
                total_held += amount
    
        if total_held == 0:
            embed.add_field(name="📦 Total Shares Held", value="0 (No current holders)", inline=False)
            return await interaction.response.send_message(embed=embed)
    
        embed.add_field(name="📦 Total Shares Held", value=f"{total_held}", inline=False)
        await interaction.response.send_message(embed=embed)
    
        # Format data for pie chart
        labels = []
        sizes = []
        for user_id, amount in owners.items():
            user = interaction.guild.get_member(int(user_id))
            label = user.display_name if user else f"User {user_id}"
            labels.append(label)
            sizes.append(amount)
    
        # Sort and combine into Top N
        top_n = 10
        sorted_data = sorted(zip(labels, sizes), key=lambda x: x[1], reverse=True)
        top_labels = []
        top_sizes = []
        other_total = 0
    
        for i, (label, size) in enumerate(sorted_data):
            if i < top_n:
                top_labels.append(f"{label} ({size})")
                top_sizes.append(size)
            else:
                other_total += size
    
        if other_total > 0:
            top_labels.append(f"Other ({other_total})")
            top_sizes.append(other_total)
    
        # Generate the pie chart
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(top_sizes, labels=top_labels, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        plt.title(f"{name} Ownership Distribution\n(Total: {total_held} shares)")
    
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
    
        await interaction.followup.send(file=discord.File(buf, filename=f"{name}_owners.png"))




    @commands.command()
    async def liststocks(self, ctx):
        """List all available stocks with pagination."""
        stocks = await self.config.stocks()
        available_stocks = [(name, data) for name, data in stocks.items() if not data.get("delisted", False)]
    
        if not available_stocks:
            return await ctx.send("No stocks available.")
    
        view = StockListView(self, available_stocks)
        embed = discord.Embed(
            title="📊 Available Stocks",
            description="Page 1",
            color=discord.Color.green()
        )
    
        for name, data in available_stocks[:10]:
            emoji = "🛂 " if data.get("commodity", False) else ""
                # Calculate shares until price shift
                # Calculate shares until price shift
            buys = data.get("buys", 0)
            sells = data.get("sells", 0)
            buy_remaining = 100 - (buys % 100)
            sell_remaining = 100 - (sells % 100)
            embed.add_field(
                name=f"{emoji}{name}",
                value=(
                    f"Price: {data['price']:.2f} Wellcoins\n"
                    f"🟢 {buy_remaining} shares until next price **increase**\n"
                    f"🔴 {sell_remaining} shares until next price **decrease**"
                ),
                inline=False
            )    
        view.message = await ctx.send(embed=embed, view=view)
    
    def calculate_total_cost_for_buy(self,start_price: float, shares: int, buys: int, price_increase: float = .1):
        total_cost = 0.0
        current_price = start_price
        simulated_buys = buys
        shares = int(shares)
        for _ in range(shares):
            if simulated_buys % 100 == 0 and simulated_buys != 0:
                current_price += price_increase
            total_cost += current_price
            simulated_buys += 1
    
        return total_cost, current_price, simulated_buys
    
    
    def calculate_earnings_and_final_price(self, start_price: float, shares: int, sells: int, price_decrease: float = 0.1):
        total_earnings = 0.0
        current_price = start_price
        simulated_sells = sells
        shares = int(shares)
    
        for _ in range(shares):
            # ↓ Apply price drop before the threshold, matching buy behavior
            if simulated_sells % 100 == 0 and simulated_sells != 0:
                current_price = max(0.01, current_price - price_decrease)
    
            total_earnings += current_price
            simulated_sells += 1
    
        return total_earnings, current_price, simulated_sells





     
    @app_commands.command(name="buystock", description="Buy shares of a stock.")
    @app_commands.describe(
        name="The stock you want to buy",
        shares="Number of shares to buy (optional)",
        wc_spend="Amount of WC to spend instead of share count (optional)"
    )
    @app_commands.autocomplete(name=stock_name_autocomplete)
    async def buystock(self, interaction: discord.Interaction, name: str, shares: int = None, wc_spend: float = None):
        user = interaction.user
        name = name.upper()
        stocks = await self.config.stocks()
        stock = stocks.get(name)
    
        if not stock or stock.get("delisted", False):
            return await interaction.response.send_message("❌ This stock is not available for purchase.", ephemeral=True)
    
        price = stock["price"]
        balance = await self.economy_config.user(user).master_balance()
        price_increase = 1.0
        shares_bought = 0
        total_cost = 0.0
    
        # Buy by amount of WC
        if wc_spend is not None:
            test_price = price
            test_buys = stock["buys"]
            while True:
                if test_buys % 100 == 0 and test_buys != 0:
                    test_price += price_increase
                if total_cost + test_price > wc_spend:
                    break
                total_cost += test_price
                test_buys += 1
                shares_bought += 1
    
            total_cost, new_price, updated_buys = self.calculate_total_cost_for_buy(price, shares_bought, stock["buys"])
            stock["buys"] = updated_buys
    
        elif shares is not None:
            shares_bought = shares
            simulated_total_cost, new_price, updated_buys = self.calculate_total_cost_for_buy(price, shares_bought, stock["buys"])
        
            if simulated_total_cost > balance:
                return await interaction.response.send_message(
                    f"💸 You need {simulated_total_cost:.2f} WC but only have {balance:.2f} WC.",
                    ephemeral=True
                )
        
            total_cost = simulated_total_cost
            stock["buys"] = updated_buys
    
        else:
            return await interaction.response.send_message("❗ Please provide either `shares` or `wc_spend`.", ephemeral=True)
    
        if total_cost > balance:
            return await interaction.response.send_message(f"💸 You need {total_cost:.2f} WC but only have {balance:.2f} WC.", ephemeral=True)
    
        # Update user balance and portfolio
        await self.economy_config.user(user).master_balance.set(balance - total_cost)
    
        async with self.config.user(user).stocks() as owned:
            prev = owned.get(name, 0)
            owned[name] = prev + shares_bought
    
        async with self.config.user(user).avg_buy_prices() as prices:
            total_old = prices.get(name, 0) * prev
            total_new = total_old + total_cost
            prices[name] = round(total_new / (prev + shares_bought), 2)
    
        stock["price"] = new_price
        await self.config.stocks.set_raw(name, value=stock)
    
        self.last_day_trades += total_cost
        await interaction.response.send_message(
            f"✅ Bought {shares_bought} shares of **{name}** for **{total_cost:.2f} WC**."
        )


    
    @app_commands.command(name="sellstock", description="Sell shares of a stock.")
    @app_commands.describe(name="The stock you want to sell", amount="Number of shares to sell")
    @app_commands.autocomplete(name=stock_name_autocomplete)
    async def sellstock(self, interaction: discord.Interaction, name: str, amount: int):
        user = interaction.user
        name = name.upper()
        stocks = await self.config.stocks()
        stock = stocks.get(name)
    
        if not stock:
            return await interaction.response.send_message("❌ This stock does not exist.", ephemeral=True)
    
        async with self.config.user(user).stocks() as owned:
            if owned.get(name, 0) < amount:
                return await interaction.response.send_message("❌ You don't own that many shares.", ephemeral=True)
            owned[name] -= amount
            if owned[name] <= 0:
                del owned[name]
                async with self.config.user(user).avg_buy_prices() as prices:
                    prices.pop(name, None)
    
        # Handle delisted stocks
        if stock.get("delisted", False):
            await self.economy_config.user(user).master_balance.set(
                (await self.economy_config.user(user).master_balance())
            )
            return await interaction.response.send_message(
                f"📉 **{name}** is delisted. You sold {amount} shares for **0 WC**.", ephemeral=True
            )
    
        # Apply price drop + earnings
        current_price = stock["price"] - .01
        sells_so_far = stock.get("sells", 0)
        earnings, new_price, updated_sells = self.calculate_earnings_and_final_price(
            current_price, amount, sells_so_far
        )
    
        # Update stock state
        stock["price"] = new_price
        stock["sells"] = updated_sells
    
        # Bankruptcy logic
        if stock["price"] <= 0 and not stock.get("commodity", False):
            if random.random() < 0.5:
                stock["price"] = 0.01
                await self._announce_recovery(name)
            else:
                stock["price"] = 0.0
                stock["delisted"] = True
                await self._announce_bankruptcy(name)
    
        # Save stock changes
        await self.config.stocks.set_raw(name, value=stock)
    
        # Apply earnings
        balance = await self.economy_config.user(user).master_balance()
        await self.economy_config.user(user).master_balance.set(balance + earnings)
    
        self.last_day_trades -= earnings
        await interaction.response.send_message(
            f"💰 Sold {amount} shares of **{name}** for **{earnings:.2f} WC**."
        )




    @commands.command()
    async def myportfolio(self, ctx):
        """View your stock holdings and net change."""
        user = ctx.author
        user_stocks = await self.config.user(user).stocks()
        all_stocks = await self.config.stocks()
        avg_prices = await self.config.user(user).avg_buy_prices()
    
        if not user_stocks:
            return await ctx.send("You don't own any stocks.")
     
        total_value = 0
        total_cost = 0
        embed = discord.Embed(title=f"📁 {user.display_name}'s Portfolio")
    
        for stock, amount in user_stocks.items():
            stock_data = all_stocks.get(stock, {})
            current_price = stock_data.get("price", 0)
            avg_price = avg_prices.get(stock, current_price)
            percent_change = ((current_price - avg_price) / avg_price) * 100 if avg_price else 0
            status = " (Delisted)" if stock_data.get("delisted", False) else ""
            # Shares to next price shift
            buys = stock_data.get("buys", 0)
            sells = stock_data.get("sells", 0)
            buy_remaining = 100 - (buys % 100)
            sell_remaining = 100 - (sells % 100)
            
            # Construct value
            value = (
                f"{amount} shares @ {current_price:.2f} Wellcoins (Δ {percent_change:+.2f}%)\n"
                f"🟢 {buy_remaining} shares until next price **increase**\n"
                f"🔴 {sell_remaining} shares until next price **decrease**"
            )
            
            embed.add_field(
                name=f"{stock}{status}",
                value=value,
                inline=False
            )

            total_value += current_price * amount
            total_cost += avg_price * amount
    
        net_change = total_value - total_cost
        embed.set_footer(text=f"Net Portfolio Change: {net_change:+.2f} Wellcoins")
        await ctx.send(embed=embed)




    @commands.hybrid_command(name="stockchart", with_app_command=True)
    async def stockchart(
        self,
        ctx: commands.Context,
        name: str,
        range: str = "month"
    ):
        """View a historical price chart of a stock."""
        name = name.upper()  # Smash spaces out
        stock_data = await self.config.stocks()
        stock = stock_data.get(name)

        if not stock:
            return await ctx.send("Stock not found.")

        history = stock.get("history", [])

        range_map = {
            "day": 24,
            "week": 24 * 7,
            "month": 24 * 30,
            "year": 24 * 365
        }

        if range not in range_map:
            return await ctx.send("Invalid range. Choose from: day, week, month, year.")

        points = range_map[range]
        data = history[-points:] if len(history) > points else history

        plt.figure(figsize=(10, 4))
        plt.plot(data)
        plt.title(f"{name} Price History ({range})")
        plt.xlabel("Hours Since Creation")
        plt.ylabel("Price")
        plt.grid(True)

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        await ctx.send(file=File(buf, filename=f"{name}_chart.png"))

    @stockchart.autocomplete("name")
    async def stockchart_name_autocomplete(self, interaction: Interaction, current: str):
        return await self.stock_name_autocomplete(interaction, current)
    
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def tagstock(self, ctx, name: str, tag: str, weight: int = 1):
        """Add a tag to a stock with an optional weight (default 1)."""
        name = name.upper()
        tag = tag.lower()
        async with self.config.stocks() as stocks:
            if name not in stocks:
                return await ctx.send("Stock not found.")
            stocks[name].setdefault("tags", {})
            stocks[name]["tags"][tag] = weight
        await ctx.send(f"🏷️ Tag `{tag}` added to `{name}` with weight {weight}.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def removetag(self, ctx, name: str, tag: str):
        """Remove a tag from a stock."""
        name = name.upper()
        tag = tag.lower()
        async with self.config.stocks() as stocks:
            if name not in stocks:
                return await ctx.send("Stock not found.")
            if tag in stocks[name].get("tags", {}):
                del stocks[name]["tags"][tag]
                await ctx.send(f"❌ Tag `{tag}` removed from `{name}`.")
            else:
                await ctx.send(f"Tag `{tag}` not found on `{name}`.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def adjustbytag(self, ctx, tag: str, percent: float):
        """Adjust price of all stocks with a given tag by a percentage."""
        tag = tag.lower()
        affected = 0
        async with self.config.stocks() as stocks:
            for stock, data in stocks.items():
                if tag in data.get("tags", {}):
                    old_price = data["price"]
                    new_price = old_price * (1 + percent / 100)
                    data["price"] = round(max(1.0, new_price), 2)
                    affected += 1
    
        if affected == 0:
            await ctx.send(f"No stocks found with tag `{tag}`.")
        else:
            await ctx.send(f"📈 Adjusted {affected} stock(s) with tag `{tag}` by {percent:+.2f}%.")



    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setannouncechannel(self, ctx, channel: discord.TextChannel = None):
        """Set or clear the announcement channel for stock market events."""
        if channel:
            await self.config.announcement_channel.set(channel.id)
            await ctx.send(f"✅ Announcements will now be sent to {channel.mention}.")
        else:
            await self.config.announcement_channel.set(None)
            await ctx.send("🛑 Announcements have been disabled.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setvolatility(self, ctx, name: str, min_volatility: float, max_volatility: float):
        """Set the volatility range for a specific stock."""
        name = name.upper()
        async with self.config.stocks() as stocks:
            if name not in stocks:
                return await ctx.send("Stock not found.")
            stocks[name]["volatility"] = [min_volatility, max_volatility]
        await ctx.send(f"📉 Volatility for `{name}` set to range [{min_volatility}, {max_volatility}].")
    
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setallvolatility(self, ctx, min_volatility: float, max_volatility: float):
        """Set the same volatility range for all stocks."""
        async with self.config.stocks() as stocks:
            for stock in stocks.values():
                stock["volatility"] = [min_volatility, max_volatility]
        await ctx.send(f"🌐 Set volatility of **all stocks** to range [{min_volatility}, {max_volatility}].")


    @commands.command()
    async def marketchart(self, ctx):
        """View a pie chart of the current stock market distribution."""
        stocks = await self.config.stocks()
        available_stocks = {name: data for name, data in stocks.items() if not data.get("delisted", False)}
    
        if not available_stocks:
            return await ctx.send("📉 No active stocks to display.")
    
        labels = []
        sizes = []
    
        for name, data in available_stocks.items():
            value = data.get("price", 0)
            if value > 0:
                labels.append(name)
                sizes.append(value)
    
        if not sizes:
            return await ctx.send("📉 All stocks are currently valued at 0.")
    
        # Sort the top N and lump the rest into "Other" for readability
        sorted_data = sorted(zip(labels, sizes), key=lambda x: x[1], reverse=True)
        top_n = 10
        top_labels = []
        top_sizes = []
        other_total = 0
    
        for idx, (label, size) in enumerate(sorted_data):
            if idx < top_n:
                top_labels.append(label)
                top_sizes.append(size)
            else:
                other_total += size
    
        if other_total > 0:
            top_labels.append("Other")
            top_sizes.append(other_total)
    
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.pie(top_sizes, labels=top_labels, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        plt.title("📊 Market Capitalization Distribution")
    
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
    
        await ctx.send(file=discord.File(buf, filename="market_chart.png"))

    @commands.command()
    async def markettrend(self, ctx, time_range: str = "month"):
        """Show the market-wide average stock price trend over time."""
        stocks = await self.config.stocks()
        available_stocks = [data for data in stocks.values() if not data.get("delisted", False)]
    
        if not available_stocks:
            return await ctx.send("📉 No active stocks to display.")
    
        range_map = {
            "day": 24,
            "week": 24 * 7,
            "month": 24 * 30,
            "year": 24 * 365
        }
    
        if time_range not in range_map:
            return await ctx.send("❌ Invalid range. Choose from: day, week, month, year.")
    
        points = range_map[time_range]
        
        # Build the average history
        averaged_history = []
        for i in range(points):
            total = 0
            count = 0
            for stock in available_stocks:
                history = stock.get("history", [])
                if len(history) >= points - i:
                    total += history[-(points - i)]
                    count += 1
            averaged_history.append(round(total / count, 2) if count else 0)
    
        if not any(averaged_history):
            return await ctx.send("⚠️ Not enough price history to generate market trend.")
    
        plt.figure(figsize=(10, 4))
        plt.plot(averaged_history, color='green')
        plt.title(f"📈 Market-Wide Average Price Trend ({time_range.capitalize()})")
        plt.xlabel("Hours Since Opening")
        plt.ylabel("Average Price")
        plt.grid(True)
    
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
    
        await ctx.send(file=discord.File(buf, filename=f"markettrend_{time_range}.png"))

    @commands.command()
    async def listtags(self, ctx):
        """List all unique tags used across stocks and how many stocks use each."""
        stocks = await self.config.stocks()
        tag_counts = {}
    
        for data in stocks.values():
            for tag in data.get("tags", {}).keys():
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
        if not tag_counts:
            return await ctx.send("📭 No tags have been assigned to any stocks.")
    
        # Sort by frequency
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        Message = "🏷️ Stock Tags Summary"
        for tag, count in sorted_tags:
            Message = Message + f"`{tag}` Used by {count} stock(s)\n"
    
        await ctx.send(Message)


    
    
        
    
    
    
    
    
    
    
