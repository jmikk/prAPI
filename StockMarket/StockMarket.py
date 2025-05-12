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

class StockListView(View):
    def __init__(self, cog, stocks, per_page=10):
        super().__init__(timeout=120)
        self.cog = cog
        self.stocks = stocks
        self.per_page = per_page
        self.page = 0
        self.message = None
        self.last_day_trades=0

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
            embed.add_field(
                name=f"{emoji}{name}",
                value=f"Price: {data['price']:.2f} Wellcoins",
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
        return [
            app_commands.Choice(name=stock, value=stock)
            for stock, data in stocks.items()
            if not data.get("delisted", False) and current.lower() in stock.lower()
        ][:25]  # Limit to 25 results

    
        


    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="SM9003", force_registration=True)
        self.economy_config = Config.get_conf(None, identifier=345678654456, force_registration=False)
        self.config.register_user(stocks={}, avg_buy_prices={})
        self.config.register_global(
            stocks={},
            tags={},
        announcement_channel=None 
        )

        self.price_updater.start()

    def cog_unload(self):
        self.price_updater.cancel()

    @tasks.loop(hours=1)
    async def price_updater(self):
        await self.recalculate_all_stock_prices()
    
    async def recalculate_all_stock_prices(self):
        async with self.config.stocks() as stocks:
            tag_multipliers = await self.config.tags()
    
            to_delist = []
    
            # Now process all active stocks.
            for stock_name, data in stocks.items():
                if data.get("delisted", False):
                    continue  # Already handled above
    
                tag_bonus = 0
                old_price = data["price"]
                for tag, weight in data.get("tags", {}).items():
                    flat_increase = tag_multipliers.get(tag, 0)
                    tag_bonus += flat_increase * weight
    
                volatility = data.get("volatility")
                if volatility and isinstance(volatility, (list, tuple)) and len(volatility) == 2:
                    change = random.uniform(volatility[0], volatility[1])
                else:
                    change = random.uniform(-2, 2)
    
                new_price = round(data["price"] + change + tag_bonus, 2)

                market_change = .01 * (self.last_day_trades / 1000)
                if market_changes > 10000
                    market_change = .11
                if market_changes < -10000
                    market_change = -.1
                    
                new_price = new_price + market_change
 
    
                # Check for large positive price surge
                if old_price > 0:
                    percent_change = ((new_price - old_price) / old_price) * 100
                    if percent_change > 3:
                        channel_id = await self.config.announcement_channel()
                        if channel_id:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                await channel.send(f"🚀 **{stock_name}** surged by **{percent_change:.2f}%** this hour!")
    
                if data.get("commodity", False):
                    new_price = max(1.0, new_price)
                else:
                    if new_price <= 0:
                        if random.random() < 0.5:
                            new_price = 0.01
                            channel_id = await self.config.announcement_channel()
                            if channel_id:
                                channel = self.bot.get_channel(channel_id)
                                if channel:
                                    await channel.send(f"**{stock_name}** narrowly avoided bankruptcy and is now trading at **0.01 WC**!")
                        else:
                            to_delist.append(stock_name)
                            channel_id = await self.config.announcement_channel()
                            if channel_id:
                                channel = self.bot.get_channel(channel_id)
                                if channel:
                                    await channel.send(f"💀 **{stock_name}** has gone bankrupt and been delisted!")
                        continue
    
                new_price = max(1.0, new_price)
    
                if "history" not in data:
                    data["history"] = []
                data["history"].append(new_price)
                if len(data["history"]) > 24 * 365 * 2:
                    data["history"] = data["history"][-24 * 365 * 2:]
    
                data["price"] = new_price
                data["buys"] = 0
                data["sells"] = 0


            # First, force all previously delisted stocks' price to 0.
            for stock_name, data in stocks.items():
                if data.get("delisted", False):
                    data["price"] = 0.0
    
            # Handle new delistings
            for stock_name in to_delist:
                if stock_name in stocks:
                    stocks[stock_name]["delisted"] = True
                    stocks[stock_name]["price"] = 0.0
            self.last_day_trades = 0 



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
            embed.add_field(name=f"{emoji}{name}", value=f"Price: {data['price']:.2f} Wellcoins", inline=False)
    
        view.message = await ctx.send(embed=embed, view=view)

    
    @app_commands.command(name="buystock", description="Buy shares of a stock.")
    @app_commands.describe(name="The stock you want to buy", amount="Number of shares to buy")
    @app_commands.autocomplete(name=stock_name_autocomplete)
    async def buystock(self, interaction: discord.Interaction, name: str, amount: int):
        user = interaction.user
        name = name.upper()
        stocks = await self.config.stocks()
        stock = stocks.get(name)
    
        if not stock or stock.get("delisted", False):
            return await interaction.response.send_message("This stock is not available for purchase.", ephemeral=True)
    
        price = stock["price"] * amount
        bal = await self.economy_config.user(user).master_balance()
        if bal < price:
            return await interaction.response.send_message("You don't have enough funds.", ephemeral=True)
    
        await self.economy_config.user(user).master_balance.set(bal - price)
        async with self.config.user(user).stocks() as owned:
            previous_amount = owned.get(name, 0)
            owned[name] = previous_amount + amount
    
        async with self.config.user(user).avg_buy_prices() as prices:
            current_total = prices.get(name, 0) * previous_amount
            new_total = current_total + stock["price"] * amount
            prices[name] = round(new_total / (previous_amount + amount), 2) if (previous_amount + amount) > 0 else 0
        
        self.last_day_trades = self.last_day_trades + price
        await interaction.response.send_message(f"✅ Purchased {amount} shares of **{name}** for **{price:.2f} WC**.")


    @app_commands.command(name="sellstock", description="Sell shares of a stock.")
    @app_commands.describe(name="The stock you want to sell", amount="Number of shares to sell")
    @app_commands.autocomplete(name=stock_name_autocomplete)
    async def sellstock(self, interaction: discord.Interaction, name: str, amount: int):
        user = interaction.user
        name = name.upper()
        stocks = await self.config.stocks()
        stock = stocks.get(name)
    
        async with self.config.user(user).stocks() as owned:
            if owned.get(name, 0) < amount:
                return await interaction.response.send_message("You don't own that many shares.", ephemeral=True)
            owned[name] -= amount
            if owned[name] <= 0:
                del owned[name]
                async with self.config.user(user).avg_buy_prices() as prices:
                    if name in prices:
                        del prices[name]
    
        earnings = stock["price"] * amount if stock else 0
        bal = await self.economy_config.user(user).master_balance()
        await self.economy_config.user(user).master_balance.set(bal + earnings)

        self.last_day_trades = self.last_day_trades - earnings
        await interaction.response.send_message(f"💰 Sold {amount} shares of **{name}** for **{earnings:.2f} WC**.")


    @commands.hybrid_command(name="viewstock", with_app_command=True)
    @app_commands.autocomplete(name=stock_name_autocomplete)
    async def viewstock(self, ctx: commands.Context, name: str):
        """View details about a stock, including ownership percentages."""
        stocks = await self.config.stocks()
        stock = stocks.get(name.upper())
    
        if not stock:
            return await ctx.send("Stock not found.")
    
        tag_str = ", ".join(f"{t} ({w})" for t, w in stock.get("tags", {}).items()) or "None"
        vol_str = f"{stock.get('volatility', 'None')}"
    
        embed = discord.Embed(title=f"📈 {name.upper()} Stock Details", color=discord.Color.blue())
        embed.add_field(name="Price", value=f"{stock['price']:.2f} Wellcoins", inline=False)
        embed.add_field(name="Tags", value=tag_str, inline=False)
        embed.add_field(name="Volatility", value=vol_str, inline=False)
    
        if stock.get("delisted", False):
            embed.add_field(name="Status", value="❌ Delisted", inline=False)
    
        # Collect ownership
        ownership = {}
        for member in ctx.guild.members:
            if member.bot:
                continue  # Ignore bots
            user_stocks = await self.config.user(member).stocks()
            owned = user_stocks.get(name.upper(), 0)
            if owned > 0:
                ownership[member.display_name] = owned
    
        if ownership:
            # Sort owners by biggest holdings
            sorted_owners = sorted(ownership.items(), key=lambda x: x[1], reverse=True)
    
            total_shares = sum(ownership.values())
            labels = []
            sizes = []
    
            other_shares = 0
            max_sections = 8  # Adjust how many unique owners before lumping into 'Other'
    
            for idx, (owner, shares) in enumerate(sorted_owners):
                if idx < max_sections:
                    labels.append(owner)
                    sizes.append(shares / total_shares * 100)
                else:
                    other_shares += shares
    
            if other_shares > 0:
                labels.append("Other")
                sizes.append(other_shares / total_shares * 100)
    
            fig, ax = plt.subplots(figsize=(6, 6))
            ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
            ax.axis('equal')
            plt.title(f"Ownership of {name.upper()} (%)")
    
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close()
    
            await ctx.send(embed=embed, file=File(buf, filename=f"{name}_ownership.png"))
    
        else:
            embed.set_footer(text="No one owns this stock currently.")
            await ctx.send(embed=embed)



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
            embed.add_field(
                name=f"{stock}{status}",
                value=f"{amount} shares @ {current_price:.2f} Wellcoins (Δ {percent_change:+.2f}%)",
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
    async def adjustbytag(self, ctx, tag: str, amount: float):
        """Adjust price of all stocks with a given tag by a flat amount."""
        tag = tag.lower()
        affected = 0
        async with self.config.stocks() as stocks:
            for stock, data in stocks.items():
                if tag in data.get("tags", {}):
                    data["price"] = round(max(1.0, data["price"] + amount), 2)
                    affected += 1
    
        if affected == 0:
            await ctx.send(f"No stocks found with tag `{tag}`.")
        else:
            await ctx.send(f"📈 Adjusted {affected} stock(s) with tag `{tag}` by {amount:+.2f} Wellcoins.")

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

    
    
        
    
    
    
    
    
    
    
