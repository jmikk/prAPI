import discord
from redbot.core import commands, Config
from discord.ext import tasks
import random
import matplotlib.pyplot as plt
import io
from discord import File

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

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="SM9003", force_registration=True)
        self.economy_config = Config.get_conf(None, identifier=345678654456, force_registration=False)
        self.config.register_user(stocks={}, avg_buy_prices={})
        self.config.register_global(
            stocks={},
            tags={}
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

            for stock_name, data in stocks.items():
                tag_bonus = 0
                for tag, weight in data.get("tags", {}).items():
                    flat_increase = tag_multipliers.get(tag, 0)
                    tag_bonus += flat_increase * weight

                volatility = data.get("volatility")
                if volatility and isinstance(volatility, (list, tuple)) and len(volatility) == 2:
                    change = random.randint(volatility[0], volatility[1])
                else:
                    change = random.randint(-2, 2)

                new_price = round(data["price"] + change + tag_bonus, 2)

                if data.get("commodity", False):
                    new_price = max(1.0, new_price)
                else:
                    if new_price <= 0:
                        if random.random() < 0.5:
                            del stocks[stock_name]
                            continue
                        else:
                            new_price = 1.0

                new_price = max(1.0, new_price)

                if "history" not in data:
                    data["history"] = []
                data["history"].append(new_price)
                if len(data["history"]) > 24 * 365 * 2:
                    data["history"] = data["history"][-24 * 365 * 2:]

                data["price"] = new_price
                data["buys"] = 0
                data["sells"] = 0

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def createstock(self, ctx, name: str, starting_price: float, min_volatility: int = None, max_volatility: int = None, commodity: bool = False):
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
        await ctx.send(f"Stock {name} created with starting price {starting_price:.2f} coins.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def liststocks(self, ctx):
        """List all available stocks and their prices."""
        stocks = await self.config.stocks()
        if not stocks:
            return await ctx.send("No stocks available.")

        embed = discord.Embed(title="📊 Available Stocks", color=discord.Color.green())
        for name, data in stocks.items():
            emoji = "🛂 " if data.get("commodity", False) else ""
            embed.add_field(name=f"{emoji}{name}", value=f"Price: {data['price']:.2f} coins", inline=False)

        await ctx.send(embed=embed)

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

        await ctx.send(f"Purchased {amount} shares of {name}.")

    @commands.command()
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

        await ctx.send(f"Sold {amount} shares of {name} for {earnings:.2f} coins.")

    @commands.command()
    async def viewstock(self, ctx, name: str):
        """View details about a specific stock."""
        stocks = await self.config.stocks()
        stock = stocks.get(name.upper())
        if not stock:
            return await ctx.send("Stock not found.")

        embed = discord.Embed(title=f"📈 {name.upper()} Stock Details", color=discord.Color.blue())
        embed.add_field(name="Price", value=f"{stock['price']:.2f} coins", inline=False)
        embed.add_field(name="Tags", value=", ".join(f"{t} ({w})" for t, w in stock["tags"].items()) or "None", inline=False)
        embed.add_field(name="Volatility", value=f"{stock.get('volatility', 'None')}", inline=False)
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
            current_price = all_stocks.get(stock, {}).get("price", 0)
            avg_price = avg_prices.get(stock, current_price)
            percent_change = ((current_price - avg_price) / avg_price) * 100 if avg_price else 0
            embed.add_field(
                name=stock,
                value=f"{amount} shares @ {current_price:.2f} coins (Δ {percent_change:+.2f}%)",
                inline=False
            )
            total_value += current_price * amount
            total_cost += avg_price * amount

        net_change = total_value - total_cost
        embed.set_footer(text=f"Net Portfolio Change: {net_change:+.2f} coins")
        await ctx.send(embed=embed)

    @commands.command()
    async def stockchart(self, ctx, name: str, range: str = "month"):
        """View a historical price chart of a stock."""
        name = name.upper()
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
        plt.xlabel("Hours")
        plt.ylabel("Price")
        plt.grid(True)

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        await ctx.send(file=File(buf, filename=f"{name}_chart.png"))
