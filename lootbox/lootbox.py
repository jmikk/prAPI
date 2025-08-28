import aiohttp
import random
import xml.etree.ElementTree as ET
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from discord import Embed
import time
import csv
import os
from datetime import datetime
from discord.ext.commands import BucketType
import discord


tsv_file = "report.tsv"

class lootbox(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)

        # guild-scoped policy
        default_guild = {
            "cooldown_policy": {
                "default": {"rate": 1, "per": 3600},
                "roles": {},
            }
        }
        default_global = {
            "season": 4,
            "categories": ["common", "uncommon", "rare", "ultra-rare", "epic"],
            "useragent": "",
            "nationName": "",
            "password": "",
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.config.register_user()

        # local in-memory cache: {guild_id: policy_dict}
        self._policy_cache = {}

    async def cog_load(self):
        # Preload policies for all guilds the bot is in
        for guild in self.bot.guilds:
            pol = await self.config.guild(guild).cooldown_policy()
            self._policy_cache[guild.id] = pol

    # helper: PURE SYNC function for dynamic_cooldown
    def _cooldown_for_ctx_sync(self, ctx: commands.Context) -> commands.Cooldown:
        # fallback if DMs or missing policy
        if not ctx.guild:
            return commands.Cooldown(1, 3600)

        policy = self._policy_cache.get(ctx.guild.id)
        if not policy:
            return commands.Cooldown(1, 3600)

        default_rate = policy["default"]["rate"]
        default_per = policy["default"]["per"]
        best_rate, best_per = default_rate, default_per

        roles_policy = policy.get("roles", {})
        member = ctx.guild.get_member(ctx.author.id)
        if member:
            for r in member.roles:
                rp = roles_policy.get(str(r.id))
                if rp:
                    rate, per = rp.get("rate", default_rate), rp.get("per", default_per)
                    if rate / per > best_rate / best_per:
                        best_rate, best_per = rate, per

        if best_per > 86400:
            best_per = 86400
        return commands.Cooldown(best_rate, best_per)



    @commands.group()
    async def cardset(self, ctx):
        """Group of commands to set season, categories, user-agent, nationName, and cooldown."""
        pass

    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def season(self, ctx, season: int):
        """Set the season to filter cards."""
        await self.config.season.set(season)
        await ctx.send(f"Season set to {season}")

    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def categories(self, ctx, *categories: str):
        """Set the categories to filter cards."""
        categories = [category for category in categories]
        await self.config.categories.set(categories)
        await ctx.send(f"Categories set to {', '.join(categories)}")

        
    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def view_c(self, ctx):
        """Set the categories to filter cards."""
        
        await ctx.send(await self.config.categories())



    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def useragent(self, ctx, *, useragent: str):
        """Set the User-Agent header for the requests."""
        await self.config.useragent.set(useragent)
        await ctx.send(f"User-Agent set to {useragent}")
    
    @cardset.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def nationname(self, ctx, *, nationname: str):
        """Set the nationName for the loot box prizes."""
        nationname = nationname.replace(" ","_").lower()
        await self.config.nationName.set(nationname)
        await ctx.send(f"Nation Name set to {nationname}")

    @commands.dm_only()
    @cardset.command()
    async def password(self, ctx, *, password: str):
        """Set the password for the loot box prizes in DM."""
        await self.config.password.set(password)
        await ctx.send(f"Password set to {password}")

    @commands.dynamic_cooldown(lambda ctx: ctx.cog._cooldown_for_ctx_sync(ctx), BucketType.user)
    @commands.command()    
    async def openlootbox(self, ctx, *recipient: str):
        """Open a loot box and fetch a random card for the specified nation."""
        await ctx.send("HERE")
        if len(recipient) < 1:
            await ctx.send("Make sure to put your nation in after openlootbox")
            return
        recipient =  "_".join(recipient)
        #await ctx.send(recipient)
        season = await self.config.season()
        nationname = await self.config.nationName()
        #await ctx.send(nationname)
        categories = await self.config.categories()
        useragent = await self.config.useragent()

        headers = {"User-Agent": useragent}
        password = await self.config.password()

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"https://www.nationstates.net/cgi-bin/api.cgi?q=cards+deck;nationname={nationname}"
            ) as response:
                if response.status != 200:
                    await ctx.send("Failed to fetch data from NationStates API.")
                    return

                data = await response.text()
                #await ctx.send(data[:1000])

                cards = self.parse_cards(data, season, categories)

                if not cards:
                    await ctx.send(
                        f"No cards found for season {season} in categories {', '.join(categories)}"
                    )
                    return

                random_card = random.choice(cards)

                # Fetch card details
                async with session.get(
                    f"https://www.nationstates.net/cgi-bin/api.cgi?q=card+info;cardid={random_card['id']};season={random_card['season']}"
                ) as card_info_response:
                    if card_info_response.status != 200:
                        await ctx.send("Failed to fetch card details from NationStates API.")
                        return

                    card_info_data = await card_info_response.text()
                    card_info = self.parse_card_info(card_info_data)

                    embed_color = self.get_embed_color(random_card['category'])
                    embed = Embed(title="Loot Box Opened!", description="You received a card!", color=embed_color)
                    embed.add_field(name="Card Name", value=card_info['name'], inline=True)
                    embed.add_field(name="Card ID", value=random_card['id'], inline=True)
                    embed.add_field(name="Season", value=random_card['season'], inline=True)
                    embed.add_field(name="Market Value", value=card_info['market_value'], inline=True)
                    await ctx.send(embed=embed)

                # Prepare the gift
                prepare_data = {
                    "nation": nationname,
                    "c": "giftcard",
                    "cardid": random_card['id'],
                    "season": random_card['season'],
                    "to": recipient,
                    "mode": "prepare"
                }
                prepare_headers = {
                    "User-Agent": useragent,
                    "X-Password": password
                }

                async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=prepare_data, headers=prepare_headers) as prepare_response:
                    if prepare_response.status != 200:
                        if prepare_response.status in (409 or 403):
                            await ctx.send("No loot boxes ready! Give me a minute or so to wrap one up for you.")
                            return

                            
                        await ctx.send(prepare_response.text)
                        await ctx.send("Failed to prepare the gift.")
                        return

                    prepare_response_data = await prepare_response.text()
                    token = self.parse_token(prepare_response_data)
                    x_pin = prepare_response.headers.get("X-Pin")

                    if not token or not x_pin:
                        await ctx.send(prepare_response_data)
                        await ctx.send("Failed to retrieve the token or X-Pin for gift execution.")
                        return

                    # Execute the gift
                    execute_data = {
                        "nation": nationname,
                        "c": "giftcard",
                        "cardid": random_card['id'],
                        "season": random_card['season'],
                        "to": recipient,
                        "mode": "execute",
                        "token": token
                    }
                    execute_headers = {
                        "User-Agent": useragent,
                        "X-Pin": x_pin
                    }

                    async with session.post("https://www.nationstates.net/cgi-bin/api.cgi", data=execute_data, headers=execute_headers) as execute_response:
                        if execute_response.status == 200:
                            await ctx.send(f"Successfully gifted the card to {recipient}!")
                        else:
                            await ctx.send("Failed to execute the gift.")
                            
    def parse_cards(self, xml_data, season, categories):
        root = ET.fromstring(xml_data)
        cards = []
        for card in root.findall(".//CARD"):
            card_season = int(card.find("SEASON").text)
            card_category = card.find("CATEGORY").text
            if card_season == season and card_category in categories:
                card_id = card.find("CARDID").text
                cards.append(
                    {"id": card_id, "season": card_season, "category": card_category}
                )
        return cards

    def parse_card_info(self, xml_data):
        root = ET.fromstring(xml_data)
        return {
            "name": root.find("NAME").text,
            "market_value": root.find("MARKET_VALUE").text
        }

    def parse_token(self, xml_data):
        root = ET.fromstring(xml_data)
        token = root.find("SUCCESS")
        return token.text if token is not None else None

    def get_embed_color(self, category):
        colors = {
            "COMMON": 0x808080,       # Grey
            "UNCOMMON": 0x00FF00,     # Green
            "RARE": 0x0000FF,         # Blue
            "ULTRA-RARE": 0x800080,   # Purple
            "EPIC": 0xFFA500,         # Orange
            "LEGENDARY": 0xFFFF00     # Yellow
        }
        return colors.get(category.upper(), 0xFFFFFF)  # Default to white if not found
        
    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def cooldownset(self, ctx):
        """Configure lootbox cooldowns."""
        pass
    
    @cooldownset.command()
    async def default(self, ctx, rate: int, per: int):
        pol = await self.config.guild(ctx.guild).cooldown_policy()
        pol["default"] = {"rate": rate, "per": per}
        await self.config.guild(ctx.guild).cooldown_policy.set(pol)
        self._policy_cache[ctx.guild.id] = pol  # keep cache in sync
        await ctx.send(f"Default cooldown set to {rate} uses per {per}s.")
    
    @cooldownset.command()
    async def role(self, ctx, role: discord.Role, rate: int, per: int):
        pol = await self.config.guild(ctx.guild).cooldown_policy()
        pol.setdefault("roles", {})[str(role.id)] = {"rate": rate, "per": per}
        await self.config.guild(ctx.guild).cooldown_policy.set(pol)
        self._policy_cache[ctx.guild.id] = pol  # keep cache in sync
        await ctx.send(f"Cooldown for {role.name}: {rate} uses per {per}s.")



def setup(bot):
    bot.add_cog(lootbox(bot))
