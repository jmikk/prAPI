import discord
from redbot.core import commands, Config
from discord.ext import tasks  
import random
import matplotlib.pyplot as plt
import io
from discord import File



class StockMarket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="SM9003", force_registration=True)
        self.economy_config = Config.get_conf(None, identifier=345678654456, force_registration=False)
        self.config.register_user(stocks={},avg_buy_prices={})  # {"STOCK_NAME": amount_owned}
        

        self.config.register_global(
            stocks={},  # {"STOCK_NAME": {"price": 100, "tags": {"tech": 2}, "volatility": [-3, 3], ...}}
            tags={},
            market_week="good"
        )

        self.price_updater.start()
        self.week_changer.start()

    def cog_unload(self):
        self.price_updater.cancel()
        self.week_changer.cancel()

    @tasks.loop(hours=1)
    async def price_updater(self):
        await self.recalculate_all_stock_prices()

    @tasks.loop(hours=168)  # once a week
    async def week_changer(self):
        new_week = random.choices(
            ["good", "bad", "great", "ugly"],
            weights=[3, 3, 2, 2],
            k=1
        )[0]
        await self.config.market_week.set(new_week)

    async def recalculate_all_stock_prices(self):
        async with self.config.stocks() as stocks:
            tag_multipliers = await self.config.tags()
            market_week = await self.config.market_week()

            for stock_name, data in stocks.items():
                # Calculate tag influence
                tag_bonus = 0
                for tag, weight in data.get("tags", {}).items():
                    flat_increase = tag_multipliers.get(tag, 0)
                    tag_bonus += flat_increase * weight

                # Flat change based on market week
                if market_week == "great":
                    market_change = random.randint(3, 6) if random.random() < 0.85 else random.randint(-1, 0)
                elif market_week == "good":
                    market_change = random.randint(2, 4) if random.random() < 0.7 else random.randint(-1, 0)
                elif market_week == "bad":
                    market_change = random.randint(-3, -1) if random.random() < 0.7 else random.randint(0, 1)
                elif market_week == "ugly":
                    market_change = random.randint(-5, -2) if random.random() < 0.85 else random.randint(1, 2)
                else:
                    market_change = 0

                volatility = data.get("volatility")
                if volatility and isinstance(volatility, (list, tuple)) and len(volatility) == 2:
                    change = random.randint(volatility[0], volatility[1])
                else:
                    change = market_change

                new_price = round(data["price"] + change + tag_bonus, 2)

                if new_price <= 0:
                    del stocks[stock_name]
                    continue

                new_price = max(1.0, new_price)

                if "history" not in data:
                    data["history"] = []
                data["history"].append(new_price)
                if len(data["history"]) > 24 * 365 * 2:  # keep 2 years of hourly data
                    data["history"] = data["history"][-24 * 365 * 2:]

                data["price"] = new_price
                data["buys"] = 0
                data["sells"] = 0

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def liststocks(self, ctx):
        """List all available stocks and their prices."""
        stocks = await self.config.stocks()
        market_week = await self.config.market_week()
        if not stocks:
            return await ctx.send("No stocks available.")

        embed = discord.Embed(
            title="📊 Available Stocks",
            description=f"**Market Condition:** {market_week.title()} Week",
            color=discord.Color.green()
        )

        for name, data in stocks.items():
            embed.add_field(name=name, value=f"Price: {data['price']:.2f} coins", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def viewstock(self, ctx, name: str):
        """View a specific stock's details."""
        stocks = await self.config.stocks()
        stock = stocks.get(name.upper())
        if not stock:
            return await ctx.send("Stock not found.")

        tag_str = ", ".join(f"{t} ({w})" for t, w in stock["tags"].items()) or "None"
        vol_str = f"{stock['volatility']}" if "volatility" in stock else "None"

        embed = discord.Embed(title=f"📈 {name.upper()} Stock Details", color=discord.Color.blue())
        embed.add_field(name="Price", value=f"{stock['price']:.2f} coins", inline=False)
        embed.add_field(name="Tags", value=tag_str, inline=False)
        embed.add_field(name="Volatility", value=vol_str, inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def buystock(self, ctx, name: str, amount: int):
        """Buy shares of a stock."""
        name = name.upper()
        user = ctx.author
        stocks = await self.config.stocks()
        stock = stocks.get(name)
        if not stock:
            return await ctx.send("Stock not found.")

        price = stock["price"] * amount
        bal = await self.economy_config.user(user).master_balance()
        if bal < price:
            return await ctx.send("You don't have enough funds.")

        await self.economy_config.user(user).master_balance.set(bal - price)       
        async with self.config.user(user).stocks() as owned:
            previous_amount = owned.get(name, 0)
            owned[name] = previous_amount + amount

        async with self.config.user(user).avg_buy_prices() as prices:
            current_total = prices.get(name, 0) * previous_amount
            new_total = current_total + stock["price"] * amount
            prices[name] = round(new_total / (previous_amount + amount), 2) if (previous_amount + amount) > 0 else 0

        async with self.config.stocks() as s:
            s[name]["buys"] += amount

        embed = discord.Embed(title="✅ Stock Purchase", color=discord.Color.green())
        embed.add_field(name="Stock", value=name, inline=True)
        embed.add_field(name="Amount", value=str(amount), inline=True)
        embed.add_field(name="Total Cost", value=f"{price:.2f} coins", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def sellstock(self, ctx, name: str, amount: int):
        """Sell shares of a stock."""
        name = name.upper()
        user = ctx.author
        stocks = await self.config.stocks()
        stock = stocks.get(name)

        async with self.config.user(user).stocks() as owned:
            if owned.get(name, 0) < amount:
                return await ctx.send("You don't own that many shares.")
            owned[name] -= amount
            if owned[name] <= 0:
                del owned[name]
                async with self.config.user(user).avg_buy_prices() as prices:
                    if name in prices:
                        del prices[name]

        earnings = stock["price"] * amount if stock else 0
        bal = await self.economy_config.user(user).master_balance()
        await self.economy_config.user(user).master_balance.set(bal + earnings)

        if stock:
            async with self.config.stocks() as s:
                s[name]["sells"] += amount

        embed = discord.Embed(title="💰 Stock Sale", color=discord.Color.gold())
        embed.add_field(name="Stock", value=name, inline=True)
        embed.add_field(name="Amount", value=str(amount), inline=True)
        embed.add_field(name="Total Earned", value=f"{earnings:.2f} coins", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setvolatility(self, ctx, name: str, min_change: int, max_change: int):
        """Set the volatility range for a stock."""
        name = name.upper()
        async with self.config.stocks() as stocks:
            if name not in stocks:
                return await ctx.send("Stock not found.")
            stocks[name]["volatility"] = [min_change, max_change]
        await ctx.send(f"📉 Volatility for `{name}` set to [{min_change}, {max_change}].")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def createstock(self, ctx, name: str, starting_price: float, min_volatility: int = None, max_volatility: int = None):
        """Create a new stock. Optionally include volatility range."""
        name = name.upper()
        async with self.config.stocks() as stocks:
            if name in stocks:
                return await ctx.send("Stock already exists.")
            stocks[name] = {
                "price": round(starting_price, 2),
                "tags": {},
                "buys": 0,
                "sells": 0
            }
            if min_volatility is not None and max_volatility is not None:
                stocks[name]["volatility"] = [min_volatility, max_volatility]
        embed = discord.Embed(title="🆕 Stock Created", color=discord.Color.blurple())
        embed.add_field(name="Name", value=name, inline=True)
        embed.add_field(name="Starting Price", value=f"{starting_price:.2f} coins", inline=True)
        if min_volatility is not None and max_volatility is not None:
            embed.add_field(name="Volatility", value=f"[{min_volatility}, {max_volatility}]", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def myportfolio(self, ctx):
        """View your stock holdings and percent change."""
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
            if stock in all_stocks:
                current_price = all_stocks[stock]["price"]
            else:
                current_price = 0
            avg_price = avg_prices.get(stock, current_price)
            percent_change = ((current_price - avg_price) / avg_price) * 100 if avg_price else 0
            status = " (Delisted)" if stock not in all_stocks else ""
            embed.add_field(
                name=stock,
                value=f"{amount} shares @ {current_price:.2f} coins (Δ {percent_change:+.2f}%)" + status,
                inline=False
            )
            total_value += current_price * amount
            total_cost += avg_price * amount

        net_change = total_value - total_cost
        if net_change > 0:
            embed.color = discord.Color.green()
        elif net_change < 0:
            embed.color = discord.Color.red()
        else:
            embed.color = discord.Color.purple()

        embed.set_footer(text=f"Net Portfolio Change: {net_change:+.2f} coins")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def stockchart(self, ctx, name: str, range: str = "month"):
        """View a chart of stock prices over time. Range: day, week, month, year"""
        await ctx.send("This takes a moment or two")
        name = name.upper()
        stock_data = await self.config.stocks()
        stock = stock_data.get(name)

        if not stock:
            return await ctx.send("Stock not found.")

        if "history" not in stock or not stock["history"]:
            return await ctx.send("No historical data for this stock.")

        history = stock["history"]

        range_map = {
            "day": 24,
            "week": 24 * 7,
            "month": 24 * 30,
            "year": 24 * 365
        }

        if range not in range_map:
            return await ctx.send("Invalid range. Choose from: day, week, month, year")

        points = range_map[range]
        data = history[-points:] if len(history) > points else history

        plt.figure(figsize=(10, 4))
        plt.plot(data)
        plt.title(f"{name} Price History ({range})")
        plt.xlabel("Hours")
        plt.ylabel("Price")
        plt.grid(True)

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        await ctx.send(file=File(buf, filename=f"{name}_chart.png"))

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def simulatetime(self, ctx, hours: int):
        """Simulate X hours of stock market activity, including weekly changes."""
        for i in range(hours):
            await self.recalculate_all_stock_prices()
            if (i + 1) % 168 == 0:
                await self.week_changer()
        await ctx.send(f"🕒 Simulated {hours} hour(s) of market activity (including week changes).")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def adjusttag(self, ctx, tag: str, value: int):
        """Admin: Adjust a tag's influence value."""
        tag = tag.lower()
        async with self.config.tags() as tags:
            tags[tag] = value
        await self.recalculate_all_stock_prices()
        await ctx.send(f"✅ Tag `{tag}` updated to {value:.2f}. All related stocks adjusted.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def deletestock(self, ctx, name: str):
        """Delete a stock and remove it from all user portfolios."""
        name = name.upper()
        async with self.config.stocks() as stocks:
            if name not in stocks:
                return await ctx.send("Stock not found.")
            del stocks[name]

        all_users = await self.config.all_users()
        for user_id, user_data in all_users.items():
            if "stocks" in user_data and name in user_data["stocks"]:
                del user_data["stocks"][name]
            if "avg_buy_prices" in user_data and name in user_data["avg_buy_prices"]:
                del user_data["avg_buy_prices"][name]

        await ctx.send(f"🗑️ Stock `{name}` has been deleted and removed from all users.")
