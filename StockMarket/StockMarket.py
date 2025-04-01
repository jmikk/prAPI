import discord
from redbot.core import commands, Config, tasks
import random

class StockMarket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

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
                    market_change = random.randint(2, 5) if random.random() < 0.85 else random.randint(-1, 0)
                elif market_week == "good":
                    market_change = random.randint(1, 3) if random.random() < 0.7 else random.randint(-1, 0)
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
    async def liststocks(self, ctx):
        """List all available stocks and their prices."""
        stocks = await self.config.stocks()
        market_week = await self.config.market_week()
        if not stocks:
            return await ctx.send("No stocks available.")

        msg = f"**Market Condition: {market_week.title()} Week**\n\n**Available Stocks:**\n"
        for name, data in stocks.items():
            msg += f"`{name}` - {data['price']:.2f} coins\n"
        await ctx.send(msg)

    @commands.command()
    async def viewstock(self, ctx, name: str):
        """View a specific stock's details."""
        stocks = await self.config.stocks()
        stock = stocks.get(name.upper())
        if not stock:
            return await ctx.send("Stock not found.")

        tag_str = ", ".join(f"{t} ({w})" for t, w in stock["tags"].items())
        await ctx.send(f"**{name.upper()}**\nPrice: {stock['price']:.2f} coins\nTags: {tag_str}")

    @commands.command()
    async def buystock(self, ctx, name: str, amount: int):
        """Buy shares of a stock."""
        name = name.upper()
        user = ctx.author
        stocks = await self.config.stocks()
        stock = stocks.get(name)
        if not stock:
            return await ctx.send("Stock not found.")

        price = stock["price"] * amount
        bal = await self.config.user(user).master_balance()
        if bal < price:
            return await ctx.send("You don't have enough funds.")

        await self.config.user(user).master_balance.set(bal - price)
        async with self.config.user(user).stocks() as owned:
            previous_amount = owned.get(name, 0)
            owned[name] = previous_amount + amount

        async with self.config.user(user).avg_buy_prices() as prices:
            current_total = prices.get(name, 0) * previous_amount
            new_total = current_total + stock["price"] * amount
            prices[name] = round(new_total / (previous_amount + amount), 2) if (previous_amount + amount) > 0 else 0

        async with self.config.stocks() as s:
            s[name]["buys"] += amount

        await ctx.send(f"Bought {amount} shares of {name} for {price:.2f} coins.")

    @commands.command()
    async def sellstock(self, ctx, name: str, amount: int):
        """Sell shares of a stock."""
        name = name.upper()
        user = ctx.author
        stocks = await self.config.stocks()
        stock = stocks.get(name)
        if not stock:
            return await ctx.send("Stock not found.")

        async with self.config.user(user).stocks() as owned:
            if owned.get(name, 0) < amount:
                return await ctx.send("You don't own that many shares.")
            owned[name] -= amount

        earnings = stock["price"] * amount
        bal = await self.config.user(user).master_balance()
        await self.config.user(user).master_balance.set(bal + earnings)

        async with self.config.stocks() as s:
            s[name]["sells"] += amount

        await ctx.send(f"Sold {amount} shares of {name} for {earnings:.2f} coins.")

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
        await ctx.send(f"✅ Created stock `{name}` at {starting_price:.2f} coins.")

    @commands.command()
    async def myportfolio(self, ctx):
        """View your stock holdings and percent change."""
        user = ctx.author
        user_stocks = await self.config.user(user).stocks()
        all_stocks = await self.config.stocks()

        if not user_stocks:
            return await ctx.send("You don't own any stocks.")

        lines = [f"**{user.display_name}'s Portfolio**"]
        for stock, amount in user_stocks.items():
            if stock in all_stocks:
                current_price = all_stocks[stock]["price"]
                avg_prices = await self.config.user(user).avg_buy_prices()
                avg_price = avg_prices.get(stock, current_price)
                percent_change = ((current_price - avg_price) / avg_price) * 100 if avg_price else 0
                lines.append(f"`{stock}`: {amount} shares @ {current_price:.2f} coins (Δ {percent_change:+.2f}%)")
            else:
                lines.append(f"`{stock}`: {amount} shares (Delisted)")

        await ctx.send("".join(lines))

    @commands.command()
    async def stockchart(self, ctx, name: str, range: str = "month"):
        """View a chart of stock prices over time. Range: day, week, month, year"""
        import matplotlib.pyplot as plt
        import io
        from discord import File

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
    async def adjusttag(self, ctx, tag: str, value: int):
        """Admin: Adjust a tag's influence value."""
        tag = tag.lower()
        async with self.config.tags() as tags:
            tags[tag] = value
        await self.recalculate_all_stock_prices()
        await ctx.send(f"✅ Tag `{tag}` updated to {value:.2f}. All related stocks adjusted.")
