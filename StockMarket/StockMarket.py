import discord
from redbot.core import commands, Config
from discord.ext import tasks
import random

class StockMarket(commands.Cog):
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
        embed = discord.Embed(title="🎕️ Stock Created", color=discord.Color.blurple())
        embed.add_field(name="Name", value=name, inline=True)
        embed.add_field(name="Starting Price", value=f"{starting_price:.2f} coins", inline=True)
        embed.add_field(name="Commodity", value="Yes" if commodity else "No", inline=True)
        if min_volatility is not None and max_volatility is not None:
            embed.add_field(name="Volatility", value=f"[{min_volatility}, {max_volatility}]", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def liststocks(self, ctx):
        """List all available stocks and their prices."""
        stocks = await self.config.stocks()
        if not stocks:
            return await ctx.send("No stocks available.")

        embed = discord.Embed(
            title="📊 Available Stocks",
            color=discord.Color.green()
        )

        for name, data in stocks.items():
            emoji = "🛂 " if data.get("commodity", False) else ""
            embed.add_field(name=f"{emoji}{name}", value=f"Price: {data['price']:.2f} coins", inline=False)

        await ctx.send(embed=embed)
