from redbot.core import commands, Config
import xml.etree.ElementTree as ET
from discord import Embed, ButtonStyle
from discord.ui import View, Button
import asyncio
import aiohttp
from datetime import datetime
from datetime import datetime, timedelta
import discord
import os

nations_tged=[]

class BatchButton(Button):
    def __init__(self, label: str, url: str):
        super().__init__(style=ButtonStyle.url, label=label, url=url)

class TimerButton(Button):
    def __init__(self, label: str, custom_id: str, cog_instance, ctx):
        super().__init__(style=ButtonStyle.secondary, label=label, custom_id=custom_id)
        self.cog_instance = cog_instance
        self.ctx = ctx

    async def callback(self, interaction):
        # Fetch the user's timer value
        timer_seconds = await self.cog_instance.config.user(self.ctx.author).timer_seconds()

        # Calculate the future time
        future_time = datetime.now() + timedelta(seconds=timer_seconds)
        future_timestamp = int(future_time.timestamp())

        # Send an ephemeral message with the countdown
        await interaction.response.send_message(f"Your timer is set! It will end <t:{future_timestamp}:R>.", ephemeral=True)


class ApproveButton(Button):
    def __init__(self, label: str, custom_id: str, cog_instance, ctx, nations_count,nations):
        super().__init__(style=ButtonStyle.success, label=label, custom_id=custom_id)
        self.cog_instance = cog_instance
        self.ctx = ctx
        self.nations_count = nations_count  # Number of processed nations
        self.invoker_id = ctx.author.id  # Store the ID of the user who invoked the command
        self.nations_list = nations
        

    async def callback(self, interaction):
        self.start_time = datetime.utcnow()
        Recruitomatic9006.last_interaction = datetime.utcnow()


        # Check if the user who interacted is the invoker
        if interaction.user.id == self.invoker_id:
            # Disable all buttons
            for item in self.view.children:
                item.disabled = True
            # Acknowledge the interaction and update the message with disabled buttons
            await interaction.response.edit_message(view=self.view)

            # Fetch current user settings
            user_settings = await self.cog_instance.config.user(self.ctx.author).all()
            # Calculate new token count
            new_token_count = user_settings.get('tokens', 0) + self.nations_count
            # Update user settings with new token count
            await self.cog_instance.config.user(self.ctx.author).tokens.set(new_token_count)
            # Continue with running the next cycle
            view = View()
             # Feedback embed

            embed = discord.Embed(title="Action Approved", description="Choose your next action:", color=0x00ff00)
            # Creating a new view for the feedback message        
            view.add_item(TimerButton("Start Timer", "start_timer", self, ctx))
            view.add_item(DoneButton("All Done", "done", self, ctx))

            # Send the feedback embed with the new view as a follow-up
            for each in self.nations_list:
                nations_tged.append(each)
            await interaction.followup.send("here")
            await ctx.send(nations_tged)
            await ctx.send(embed=embed)

        else:
            # If the user is not the invoker, send an error message
            await interaction.response.send_message("You are not allowed to use this button.", ephemeral=True)




class DoneButton(Button):
    def __init__(self, label: str, custom_id: str, cog_instance, ctx):
        super().__init__(style=ButtonStyle.danger, label=label, custom_id=custom_id)
        self.cog_instance = cog_instance
        self.ctx = ctx
        self.invoker_id = ctx.author.id  # Store the ID of the user who invoked the command

    async def callback(self, interaction):
        # Check if the user who interacted is the invoker
        if interaction.user.id == self.invoker_id:
            # Disable all buttons
            for item in self.view.children:
                item.disabled = True
            # Acknowledge the interaction and update the message with disabled buttons
            await interaction.response.edit_message(view=self.view)

            # Stop the recruitment loop
            self.cog_instance.loop_running = False
            self.cog_instance.processed_nations.clear()  # Clear processed nations
            await Recruitomatic9006.send_nations_file(self.ctx)

            # Fetch the total tokens and send a follow-up message with the embed
        else:
            # If the user is not the invoker, send an error message
            await interaction.response.send_message("You are not allowed to use this button.", ephemeral=True)



class Recruitomatic9006(commands.Cog):
    def __init__(self, bot):
        self.cycle_count = 0  # Initialize the cycle counter
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_user_settings = {
            "template": None,
            "user_agent": f"Recruitomatic9006 written by 9003, nswa9002@gmail.com (discord: 9003)     V 2"
        }
        self.last_interaction = datetime.utcnow()
        self.config.register_user(**default_user_settings)
        self.loop_running = False
        self.processed_nations = set()  # Track already processed nations

        default_guild_settings = {
            "excluded_regions": ["the_wellspring"],
        }
        self.config.register_guild(**default_guild_settings)
        self.start_time = 0
        

    async def fetch_nation_details(self, user_agent):
        async with aiohttp.ClientSession() as session:
            headers = {'User-Agent': user_agent}
            url = "https://www.nationstates.net/cgi-bin/api.cgi?q=newnationdetails"
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.text()

    async def run_cycle(self, ctx, user_settings, view):
        excluded_regions = await self.config.guild(ctx.guild).excluded_regions()       
        user_agent = user_settings['user_agent']

        if not user_settings['template']:
            await ctx.send("Make sure to set a template first with [p]set_user_template %template-1234%")
            return 
        template = user_settings['template'].replace("%","%25")

        data = await self.fetch_nation_details(user_agent)
        if data is None:
            embed = Embed(title="Error", description="Failed to fetch nation details.", color=0xff0000)
            await ctx.send(embed=embed)
            return False

        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            embed = Embed(title="Error", description=f"Error parsing XML: {e}", color=0xff0000)
            await ctx.send(embed=embed)
            return False

        nations = []
        for new_nation in root.findall('./NEWNATIONDETAILS/NEWNATION'):
            nation_name = new_nation.get('name')
            region = new_nation.find('REGION').text
            if region not in excluded_regions and nation_name not in self.processed_nations:
                nations.append(nation_name)
                self.processed_nations.add(nation_name)  # Add to the set of already processed nations

        view.clear_items()
        embed = Embed(title="Recruitment Cycle", color=0x00ff00)
        if not nations:
            embed.description = "No new nations found in this cycle.\nI'll keep looking for you based on the number of minutes you put in before.  If you want to check for more earlier, you can always approve this message!"
        else:

            if self.cycle_count == 0:
                nations = nations[:8]
            
            for i, group in enumerate([nations[i:i + 8] for i in range(0, len(nations), 8)]):
                nations_str = ",".join(group)
                url = f"https://www.nationstates.net/page=compose_telegram?tgto={nations_str}&message={template}"
                view.add_item(BatchButton(label=f"Batch {i+1}", url=url))
            embed.description = "Please click each batch, then the approve button, to get credit and get the next set.\nWhen you are all done recruiting for the day, click \'All done\'.  \nFor your convenience, I have a timer function you can use.  Just set it up by doing [p]set_timer {Num of Seconds}."
        nations_count = len(nations)
        
        view.add_item(TimerButton("Start Timer", "start_timer", self, ctx))
        view.add_item(ApproveButton("Approve", "approve", self, ctx, nations_count,nations))
        view.add_item(DoneButton("All Done", "done", self, ctx))


        current_time = datetime.utcnow()
        # Subtract 5 hours
        new_time = current_time - timedelta(hours=5)
        
        # Convert the new time to a Unix timestamp
        new_unix_timestamp = int(new_time.timestamp())
        
        # Now you can format this for Discord
        fancy_timestamp = f"<t:{new_unix_timestamp}:R>"
   
        if embed.description == "No new nations found in this cycle.\nI'll keep looking for you based on the number of minutes you put in before.  If you want to check for more earlier, you can always approve this message!":
            await ctx.send(content=fancy_timestamp,embed=embed, view=view)
        else:
            await ctx.send(content=ctx.author.mention+" "+fancy_timestamp,embed=embed, view=view)

        return True

    @commands.command()
    async def recruit2(self, ctx, timer: int):
        if self.loop_running:
            await ctx.send("A recruitment loop is already running.")
            return

        self.loop_running = True
        timer = max(40, timer * 60)
        cycles = 0
        self.last_interaction = datetime.utcnow()

        user_settings = await self.config.user(ctx.author).all()

        while self.loop_running and datetime.utcnow() - self.last_interaction < timedelta(minutes=10):
            view = View()

            success = await self.run_cycle(ctx, user_settings, view)
            if not success:
                break
            
            await asyncio.sleep(timer)
            cycles += 1

        self.loop_running = False
        # Fetch the total tokens and send a follow-up message with the embed
        embed = Embed(title="Tokens Earned", description=f"I'll clean up thanks for recruiting! check out the recruit_leaderboard to see your ranking!", color=0x00ff00)
        await ctx.send(embed=embed)
        await self.send_nations_file(ctx)


    @commands.command()
    async def set_user_template2(self, ctx, *, template: str):
        """Sets the user's recruitment message template."""
        # Ensure the template meets your requirements, e.g., starts and ends with %%
        if template.startswith("%") and template.endswith("%"):
            await self.config.user(ctx.author).template.set(template)
            await ctx.send("Your recruitment template has been updated.")
        else:
            await ctx.send("Error: The template must start and end with %.")

    @commands.command()
    async def recruit_leaderboard2(self, ctx):
        guild = ctx.guild
        members = guild.members
    
        data = []
        for member in members:
            member_data = await self.config.user(member).all()
            data.append((member.display_name, member_data.get("tokens", 0)))
        data.sort(key=lambda x: x[1], reverse=True)

        
        page = 0

        msg = await ctx.send(embed=self.get_leaderboard_embed(data, page))
        await msg.add_reaction("⬅️")
        await msg.add_reaction("➡️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"] and reaction.message.id == msg.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

                if str(reaction.emoji) == "➡️" and page < len(data) // 10:
                    page += 1
                    await msg.edit(embed=self.get_leaderboard_embed(data, page))
                    await msg.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "⬅️" and page > 0:
                    page -= 1
                    await msg.edit(embed=self.get_leaderboard_embed(data, page))
                    await msg.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                await msg.clear_reactions()
                break

    def get_leaderboard_embed(self, data, page):
        embed = Embed(title="Token Leaderboard")
        start_index = page * 10
        end_index = min(start_index + 10, len(data))  # Ensure end_index does not exceed data length
    
        for i, (user_id, tokens) in enumerate(data[start_index:end_index], start=start_index):
            user = self.bot.get_user(user_id)
            # Use mention if the user is found, otherwise fallback to "User ID: user_id"
            username = user.mention if user else f'User ID: {user_id}'
            embed.add_field(name=f"{i + 1}. {username}", value=f"Tokens: {tokens}", inline=False)
    
        return embed
    
    @commands.command()
    @commands.has_permissions(manage_guild=True)  # Ensure only users with manage guild permissions can modify the list
    async def add_excluded_region2(self, ctx, *, region: str):
        region = region.replace(" ","_").lower()
        async with self.config.guild(ctx.guild).excluded_regions() as regions:
            if region not in regions:
                regions.append(region)
                await ctx.send(f"Region '{region}' has been added to the excluded regions list.")
            else:
                await ctx.send(f"Region '{region}' is already in the excluded regions list.")
    
    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def remove_excluded_region2(self, ctx, *, region: str):
        region = region.replace(" ","_").lower()
        async with self.config.guild(ctx.guild).excluded_regions() as regions:
            if region in regions:
                regions.remove(region)
                await ctx.send(f"Region '{region}' has been removed from the excluded regions list.")
            else:
                await ctx.send(f"Region '{region}' is not in the excluded regions list.")

    @commands.command()
    async def view_excluded_regions2(self, ctx):
        # Fetch the excluded regions list from the guild's config
        excluded_regions = await self.config.guild(ctx.guild).excluded_regions()
    
        if excluded_regions:
            # If there are excluded regions, format them as a string and send
            regions_str = ", ".join(excluded_regions)
            message = f"Excluded regions for this server: {regions_str}"
        else:
            # If the list is empty, inform the user
            message = "There are no excluded regions for this server."
    
        # Send the message to the context channel
        await ctx.send(message)

    @commands.command()
    async def Thanks_9006(self, ctx):
        await ctx.send("Your appreciation is appreciated! If this has been a useful tool, please let 9003/9006 know by sending them a TG or a discord message. The wellspring starts on the excluded region list, another way you can say thanks is by leaving it on there!")




    @commands.command()
    async def set_timer2(self, ctx, seconds: int):
        """Sets your personal timer in seconds."""
        if seconds <= 0:
            await ctx.send("Please enter a positive number of seconds.")
            return
    
        # Save the timer value in the user's config
        await self.config.user(ctx.author).timer_seconds.set(seconds)
        await ctx.send(f"Your personal timer has been set to {seconds} seconds.")\

    @commands.command()
    async def end_loop2(self, ctx):
        self.loop_running = False
        await ctx.send("ending loop")
        await self.send_nations_file(ctx)

    async def send_nations_file(self, ctx):
        # Specify the filename
        filename = "nations_list.txt"

        # Write the nations to the file
        with open(filename, "w") as file:
            for nation in nations_tged:
                file.write(f"{nation}\n")

        # Send the file in a Discord message
        with open(filename, "rb") as file:
            await ctx.send("Here's the list of all nations that earned tokens:", file=discord.File(file, filename))

        # Clean up by deleting the file after sending it
        os.remove(filename)
