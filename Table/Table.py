from redbot.core import commands, Config
import discord
import random
import asyncio



def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False

    return commands.permissions_check(predicate)


class Table(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        # Define a default guild setting structure
        default_guild = {
            "tables": {}
        }

        self.config.register_guild(**default_guild)

    @commands.guild_only()
    @commands.group(name="table")
    async def table_group(self, ctx):
        """Commands for managing D&D tables."""
        pass

    @table_group.command(name="upload")
    async def upload_table(self, ctx, table_name: str, table_type: str, *items):
        """Uploads a new table.

        Usage: [p]table upload <table_name> <type: standard|weighted> <item1> <item2> ...
        For weighted tables, use <item,weight> pairs.
        """
        if table_type not in ["standard", "weighted"]:
            await ctx.send("Table type must be 'standard' or 'weighted'.")
            return

        # Parse items for weighted tables
        parsed_items = []
        if table_type == "weighted":
            for item in items:
                try:
                    name, weight = item.split(",")
                    parsed_items.append((name.strip(), int(weight)))
                except ValueError:
                    await ctx.send(f"Error parsing item: {item}. Ensure it's in the format 'itemName,weight'.")
                    return
        else:
            parsed_items = list(items)

        # Save the table
        async with self.config.guild(ctx.guild).tables() as tables:
            if table_name in tables:
                await ctx.send(f"A table with the name '{table_name}' already exists.")
                return
            tables[table_name] = {"type": table_type, "items": parsed_items}

        await ctx.send(f"Table '{table_name}' uploaded successfully.")
   
    @table_group.command(name="roll")
    async def roll_table(self, ctx, table_name: str):
        """Rolls on a specified table.

        Usage: [p]table roll <table_name>
        """
        tables = await self.config.guild(ctx.guild).tables()
        if table_name not in tables:
            await ctx.send(f"No table found with the name '{table_name}'.")
            return

        table = tables[table_name]
        result = self.roll_on_table(table)

        await ctx.send(f"Rolling on '{table_name}': {result}")

        # Check if the result triggers another table roll
        if result in tables:
            await ctx.send(f"'{result}' triggers another table roll!")
            triggered_result = self.roll_on_table(tables[result])
            await ctx.send(f"Rolling on '{result}': {triggered_result}")

    def roll_on_table(self, table):
        """Rolls on a given table."""
        if table["type"] == "standard":
            return random.choice(table["items"])
        elif table["type"] == "weighted":
            items, weights = zip(*table["items"])
            return random.choices(items, weights=weights, k=1)[0]

