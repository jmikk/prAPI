from redbot.core import commands, Config
import discord
import random


class Dropdown(discord.ui.Select):
    def __init__(self, items, user_data):
        # Ensure that options are based on items the user has at least one of
        options = [discord.SelectOption(label=item, description=f"You have {user_data[item]} of these") for item in items if user_data[item] > 0]

        super().__init__(placeholder="Choose two items to combine...", min_values=2, max_values=2, options=options)

    async def callback(self, interaction: discord.Interaction):
        # Example recipe check (this would be more complex in practice)
        recipes = {
            ("Logistics", "Knowledge"): "Common Item 1",
            ("Chemicals", "Textiles"): "Common Item 2",
            # Add more recipes as needed
        }

        # Deduct the used items from user data and add the new item if the recipe matches
        user_data = await self.view.cog.config.user(interaction.user).all()
        chosen_items = tuple(sorted(self.values))  # Sort to ensure consistent tuple order
        recipe_result = recipes.get(chosen_items)

        if recipe_result:
            for item in chosen_items:
                if user_data[item] > 0:
                    user_data[item] -= 1
                else:
                    await interaction.response.send_message("You don't have enough items to craft this.", ephemeral=True)
                    return
            
            # Add the new common item here
            # user_data[recipe_result] += 1  # Assuming you add common items to the config

            await self.view.cog.config.user(interaction.user).set(user_data)
            await interaction.response.send_message(f"Crafted {recipe_result}!", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid recipe combination.", ephemeral=True)

class MyDropdownView(discord.ui.View):
    def __init__(self, cog, user_data):
        super().__init__()
        self.cog = cog
        self.add_item(Dropdown(cog.basic_items, user_data))


class DisWonder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_user = {"Logistics": 0, "Knowledge": 0, "Chemicals": 0, "Textiles": 0, "Food": 0, "Metal": 0, "Wood": 0, "Stone": 0}
        self.config.register_user(**default_user)

    @commands.command()
    async def buy_basic(self, ctx):
        basic_items = ["Logistics", "Knowledge", "Chemicals", "Textiles", "Food", "Metal", "Wood", "Stone"]
        chosen_item = random.choice(basic_items)
        await ctx.send(self.config.user(ctx.author).all())

        
        # Example logic for modifying item quantities
        if tokens > 0:
            # Select a random item to increment
            user_items[chosen_item] += tokens  # Increment by the number of tokens spent
            # Save the updated items back to the user's config
            await ctx.send(f"You spent {tokens} tokens and received {tokens} units of {random_item}.")
        else:
            await ctx.send("You must spend at least 1 token.")

        
        async with self.config.user(ctx.author).all() as user_data:
            user_data[chosen_item] += 1
            await ctx.send(f"{ctx.author.mention}, you have acquired 1 {chosen_item}!")

        # Assuming 1 point per basic item, update points
        points = sum(value for key, value in user_data.items())
        await ctx.send(f"Your total points are now: {points}")
    
    @commands.command()
    async def build(self, ctx):
        user_data = await self.config.user(ctx.author).all()
        view = MyDropdownView(self, user_data)

        
        await ctx.send("Select items to combine:", view=view)
        user_items = await self.config.user(ctx.author).default_items()
        await ctx.send(user_items)






