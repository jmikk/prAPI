from redbot.core import commands, Config
import discord
import random
from math import ceil
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
        self.config = Config.get_conf(self, identifier="DnD_Table", force_registration=True)

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

        # Construct the table ID using the command invoker's ID
        table_id = f"{ctx.author.id}_{table_name}"
    
        async with self.config.guild(ctx.guild).tables() as tables:
            if table_id in tables:
                await ctx.send(f"You already have a table with the name '{table_name}'.")
                return
    
            tables[table_id] = {"type": table_type, "items": parsed_items}
    
        await ctx.send(f"Table '{table_name}' uploaded successfully.")

   
    @table_group.command(name="roll")
    async def roll_table(self, ctx, *args,depth=0):
        """Rolls on a specified table and handles table triggers.
    
        Usage: [p]table roll [user_mention|user_id] <table_name>
        If no user is specified, defaults to the command invoker's tables.
        """
        MAX_RECURSION_DEPTH = 10  # Example limit
       
        if not args:
            await ctx.send("You must specify a table name.")
            return
    
        # Attempt to resolve the first argument as a table name under the command invoker's tables
        table_name = args[0]
        user = ctx.author
        table_id = f"{user.id}_{table_name}"
    
        if depth > MAX_RECURSION_DEPTH:
            await ctx.send("Maximum table roll depth exceeded.")
            return
    
        tables = await self.config.guild(ctx.guild).tables()
        if table_id not in tables:
            await ctx.send(f"No table found with the name '{table_name}' created by {user.display_name}.")
            return
    
        table = tables[table_id]
        result = self.roll_on_table(table)
        await ctx.send(f"Rolling on '{table_name}' by {user.display_name}: {result}")
        
    def roll_on_table(self, table):
        """Rolls on a given table."""
        if table["type"] == "standard":
            return random.choice(table["items"])
        elif table["type"] == "weighted":
            items, weights = zip(*table["items"])
            return random.choices(items, weights=weights, k=1)[0]


    @table_group.command(name="list")
    async def list_tables(self, ctx, user: discord.User = None, page: int = 1, edit: bool = False):
        """Lists all tables or tables belonging to a specified user, with pagination."""
        tables = await self.config.guild(ctx.guild).tables()
        if user:
            user_tables = {k: v for k, v in tables.items() if str(user.id) in k}
            tables_to_list = user_tables
        else:
            tables_to_list = tables
    
        items_per_page = 10
        pages = list(tables_to_list.items())
        start = (page - 1) * items_per_page
        end = start + items_per_page
        current_page = pages[start:end]
    
        if not current_page:
            await ctx.send("No tables found.")
            return
    
        embed = discord.Embed(title=f"Tables Page {page}", colour=discord.Colour.blue())
        for table_id, table in current_page:
            embed.add_field(name=table_id, value=f"Type: {table['type']}", inline=False)
    
        # Check if we are editing an existing message or sending a new one
        if edit:
            await ctx.message.edit(embed=embed)
        else:
            sent_message = await ctx.send(embed=embed)
    
            if len(pages) > items_per_page:
                await sent_message.add_reaction("◀")
                await sent_message.add_reaction("▶")
                self.bot.loop.create_task(self.handle_reactions(ctx, sent_message, user, page, len(pages) // items_per_page + (len(pages) % items_per_page > 0)))
    
    async def handle_reactions(self, ctx, message, user, page, max_page):
        def check(reaction, user_reacted):
            return user_reacted == ctx.author and str(reaction.emoji) in ["◀", "▶"] and reaction.message.id == message.id
    
        while True:
            try:
                reaction, user_reacted = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
    
                if str(reaction.emoji) == "▶" and page < max_page:
                    page += 1
                elif str(reaction.emoji) == "◀" and page > 1:
                    page -= 1
                else:
                    continue
    
                await message.remove_reaction(reaction, user_reacted)
                await self.list_tables(ctx, user, page, edit=True)
                break
    
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

