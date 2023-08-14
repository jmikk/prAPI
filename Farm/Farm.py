from redbot.core import commands,data_manager
import discord
import datetime

class Farm(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot

    # Store user data and their crops
    user_data = {}
    
    # Crop growth time (in days)
    crop_growth_time = {
        "POTATO": 2,
        "CARROT": 3,
        "MUSHROOM": 4,
        "CORN": 5,
        "TACO": 6,
        "AVOCADO": 7
    }
    
    @commands.command()
    def update_growths(user_id):
        now = datetime.datetime.now()
        for crop_name, data in user_data[user_id].items():
            last_action_time = data["last_action_time"]
            days_since_last_action = (now - last_action_time).days
            if days_since_last_action > 0:
                data["growth_progress"] += days_since_last_action
                data["last_action_time"] = now
    
                if data["growth_progress"] >= crop_growth_time[crop_name]:
                    data["growth_progress"] = 0
                    data["ready_to_harvest"] = True

    @commands.command()
    async def plant(ctx, crop_name):
        user_id = str(ctx.author.id)
        if user_id not in user_data:
            user_data[user_id] = {}
    
        if crop_name in crop_growth_time:
            if crop_name not in user_data[user_id]:
                user_data[user_id][crop_name] = {
                    "growth_progress": 0,
                    "ready_to_harvest": False,
                    "last_action_time": datetime.datetime.now()
                }
            await ctx.send(f"You planted {crop_name}!")
            update_growths(user_id)
        else:
            await ctx.send("Invalid crop name.")
    
    @commands.command()
    async def harvest(ctx, crop_name):
        user_id = str(ctx.author.id)
        if user_id in user_data and crop_name in user_data[user_id]:
            if user_data[user_id][crop_name]["ready_to_harvest"]:
                user_data[user_id][crop_name]["ready_to_harvest"] = False
                await ctx.send(f"You harvested {crop_name}!")
            else:
                await ctx.send(f"{crop_name} is not ready for harvest.")
        else:
            await ctx.send("You don't have any of that crop to harvest.")
    
    @commands.command()
    async def status(ctx):
        user_id = str(ctx.author.id)
        if user_id in user_data:
            status_message = "Your farm status:\n"
            for crop_name, data in user_data[user_id].items():
                growth_progress = data["growth_progress"]
                ready_to_harvest = "Ready to harvest" if data["ready_to_harvest"] else f"Growth: {growth_progress}/{crop_growth_time[crop_name]}"
                status_message += f":{crop_name}: {ready_to_harvest}\n"
            await ctx.send(status_message)
        else:
            await ctx.send("You haven't started farming yet.")
