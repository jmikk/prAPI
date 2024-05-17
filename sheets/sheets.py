from redbot.core import commands
from redbot.core.commands import BucketType, Cooldown, CommandOnCooldown
import discord
import time

def dynamic_cooldown(ctx):
    user_roles = [role.id for role in ctx.author.roles]

    # Default cooldown: 1 use per week (7 days)
    cooldown_period = 7 * 24 * 3600  # 7 days in seconds
    rate = 1

    # Adjust cooldown based on roles
    if 1098646004250726420 in user_roles:  # Role A
        rate = 2
    if 1098673767858843648 in user_roles:  # Role B
        rate = 3

    return Cooldown(rate=rate, per=cooldown_period)

class sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.dynamic_cooldown(dynamic_cooldown, type=BucketType.user)
    @commands.command()
    async def my_command(self, ctx, card_id):
        await ctx.send("Here")
               # Fetch card info from the NationStates API
        url = f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={card_id};season=3"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    await ctx.send("Failed to fetch card info.")
                    return
                xml_content = await response.text()
                card_info = self.parse_card_info(xml_content)
                if card_info:
                    await ctx.send(embed=card_info)
                else:
                    await ctx.send("Failed to parse card info.")

    def parse_card_info(self, xml_content):
        root = ET.fromstring(xml_content)
        card = root.find('CARD')
        if card is None:
            return None
        
        # Extract card details
        card_id = card.find('CARDID').text
        category = card.find('CATEGORY').text
        flag = card.find('FLAG').text
        govt = card.find('GOVT').text
        market_value = card.find('MARKET_VALUE').text
        name = card.find('NAME').text
        region = card.find('REGION').text
        season = card.find('SEASON').text
        slogan = card.find('SLOGAN').text
        card_type = card.find('TYPE').text

        # Create an embed with the card details
        embed = discord.Embed(title=f"Card Info: {name}", color=discord.Color.blue())
        embed.add_field(name="Card ID", value=card_id, inline=True)
        embed.add_field(name="Category", value=category, inline=True)
        embed.add_field(name="Government", value=govt, inline=True)
        embed.add_field(name="Market Value", value=market_value, inline=True)
        embed.add_field(name="Region", value=region, inline=True)
        embed.add_field(name="Season", value=season, inline=True)
        embed.add_field(name="Slogan", value=slogan, inline=True)
        embed.add_field(name="Type", value=card_type, inline=True)
        embed.set_thumbnail(url=f"https://www.nationstates.net/{flag}")

        return embed

    @my_command.error
    async def my_command_error(self, ctx, error):
        if isinstance(error, CommandOnCooldown):
            retry_after = int(error.retry_after)
            timestamp = int(time.time() + retry_after)
            cooldown_message = f"You can use this command again <t:{timestamp}:R>."
            await ctx.send(cooldown_message)
        else:
            raise error

def setup(bot):
    bot.add_cog(sheets(bot))

