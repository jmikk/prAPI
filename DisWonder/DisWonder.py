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
            user_data[recipe_result] = user_data.get(recipe_result, 0) + 1

            await self.view.cog.config.user(interaction.user).set(user_data)
            await interaction.response.send_message(f"Crafted {recipe_result}!")
        else:
            await interaction.response.send_message("Invalid recipe combination.")

class MyDropdownView(discord.ui.View):
    def __init__(self, cog, user_data):
        super().__init__()
        self.cog = cog
        self.add_item(Dropdown(cog.basic_items, user_data))


class DisWonder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="DisWonder", force_registration=True)
        default_user = {}
        self.config.register_user(**default_user)        

    @commands.command()
    async def buy_basic(self, ctx, tokens=1):
        tokens=1
        
        basic_items = [("Logistics","basic"), ("Knowledge","basic"), ("Chemicals","basic"), ("Textiles","basic"), ("Food","basic"),("Metal","basic"),("Wood","basic"),("Stone","basic")]
        chosen_item = random.choice(basic_items)
        user_data = await self.config.user(ctx.author).all()
        await ctx.send(user_data)

        #user_tokens = await self.get_user_tokens(ctx.author)
        #await ctx.send(user_tokens)
        #if user_tokens < tokens:
        #    await ctx.send("Go earn more tokens doing some recuritment!")
        #    return
            
        #self.use_tokens(ctx,tokens)
            
        # Example logic for modifying item quantities
        if tokens > 0:
            # Select a random item to increment
            chosen_item_key = str(chosen_item)  # Convert tuple to string
            user_data[chosen_item] = user_data.get(chosen_item_key, 0) + 1
            # Save the updated items back to the user's config
            await ctx.send(f"You spent {tokens} tokens and received {tokens} units of {chosen_item}.")
            await self.config.user(ctx.author).set(user_data)

        else:
            await ctx.send("You must spend at least 1 token.")


    
    @commands.command()
    async def build(self, ctx):
        user_data = await self.config.user(ctx.author).all()
        await ctx.send(user_data)
        view = MyDropdownView(self, user_data)

        
        await ctx.send("Select items to combine:", view=view)
        user_items = await self.config.user(ctx.author).default_items()
        await ctx.send(user_items)

    async def get_user_tokens(self, user):
        tokens_cog = self.bot.get_cog("Recruitomatic9003")
        if tokens_cog:
            return await tokens_cog.get_tokens(user)
        else:
            return 0  # or handle the absence of TokensCog appropriately





    




