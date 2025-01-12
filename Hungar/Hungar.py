from redbot.core import commands, Config
import random
import asyncio
from datetime import datetime, timedelta

class Hungar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            districts={},
            players={},
            game_active=False,
            day_duration=3600,  # Default: 1 hour in seconds
            day_start=None,
        )

    async def load_npc_names(self):
        """Load NPC names from the NPC_names.txt file."""
        try:
            with open("NPC_names.txt", "r") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except FileNotFoundError:
            return [f"NPC {i+1}" for i in range(100)]  # Fallback if file is missing

    @commands.guild_only()
    @commands.group()
    async def hunger(self, ctx):
        """Commands for managing the Hunger Games."""
        pass

    @hunger.command()
    async def signup(self, ctx):
        """Sign up for the Hunger Games."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        if str(ctx.author.id) in players:
            await ctx.send("You are already signed up!")
            return

        # Assign random district and stats
        district = random.randint(1, 12)  # Assume 12 districts
        stats = {
            "Dex": random.randint(1, 10),
            "Str": random.randint(1, 10),
            "Con": random.randint(1, 10),
            "Wis": random.randint(1, 10),
            "HP": random.randint(15, 25)
        }

        players[str(ctx.author.id)] = {
            "name": ctx.author.display_name,
            "district": district,
            "stats": stats,
            "alive": True,
            "action": None
        }

        await self.config.guild(guild).players.set(players)
        await ctx.send(f"{ctx.author.mention} has joined the Hunger Games from District {district}!")

    @hunger.command()
    @commands.admin()
    async def setdistrict(self, ctx, member: commands.MemberConverter, district: int):
        """Set a player's district manually (Admin only)."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        if str(member.id) not in players:
            await ctx.send(f"{member.display_name} is not signed up.")
            return

        players[str(member.id)]["district"] = district
        await self.config.guild(guild).players.set(players)
        await ctx.send(f"{member.display_name}'s district has been set to {district}.")

    @hunger.command()
    @commands.admin()
    async def startgame(self, ctx, npcs: int = 0):
        """Start the Hunger Games (Admin only). Optionally, add NPCs."""
        guild = ctx.guild
        config = await self.config.guild(guild).all()
        if config["game_active"]:
            await ctx.send("The Hunger Games are already active!")
            return

        players = config["players"]
        if not players:
            await ctx.send("No players are signed up yet.")
            return

        # Add NPCs if specified
        npc_names = await self.load_npc_names()
        for i in range(npcs):
            npc_id = f"npc_{i+1}"
            players[npc_id] = {
                "name": npc_names[i % len(npc_names)],
                "district": random.randint(1, 12),
                "stats": {
                    "Dex": random.randint(1, 10),
                    "Str": random.randint(1, 10),
                    "Con": random.randint(1, 10),
                    "Wis": random.randint(1, 10),
                    "HP": random.randint(15, 25)
                },
                "alive": True,
                "action": None,
                "is_npc": True
            }

        await self.config.guild(guild).players.set(players)
        await self.config.guild(guild).game_active.set(True)
        await self.config.guild(guild).day_start.set(datetime.utcnow().isoformat())
        await ctx.send(f"The Hunger Games have begun with {npcs} NPCs added! Day 1 starts now.")

        asyncio.create_task(self.run_game(ctx))

    async def run_game(self, ctx):
        """Handle the real-time simulation of the game."""
        guild = ctx.guild

        while True:
            config = await self.config.guild(guild).all()
            if not config["game_active"]:
                break

            if await self.isOneLeft(guild):
                await self.endGame(ctx)
                break

            day_start = datetime.fromisoformat(config["day_start"])
            day_duration = timedelta(seconds=config["day_duration"])
            if datetime.utcnow() - day_start >= day_duration:
                await self.announce_new_day(ctx, guild)
                await self.process_day(ctx)
                await self.config.guild(guild).day_start.set(datetime.utcnow().isoformat())

            await asyncio.sleep(10)  # Check every 10 seconds

    async def announce_new_day(self, ctx, guild):
        """Announce the start of a new day and ping alive players."""
        players = await self.config.guild(guild).players()
        alive_mentions = []
        for player_id, player_data in players.items():
            if player_data["alive"]:
                if player_data.get("is_npc"):
                    alive_mentions.append(player_data["name"])
                else:
                    member = guild.get_member(int(player_id))
                    if member:
                        alive_mentions.append(member.mention)

        await ctx.send(f"A new day dawns in the Hunger Games! Participants still alive: {', '.join(alive_mentions)}")

    async def isOneLeft(self, guild):
        """Check if only one player is alive."""
        players = await self.config.guild(guild).players()
        alive_players = [player for player in players.values() if player["alive"]]
        return len(alive_players) == 1

    async def endGame(self, ctx):
        """End the game and announce the winner."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        alive_players = [player for player in players.values() if player["alive"]]

        if alive_players:
            winner = alive_players[0]
            await ctx.send(f"The game is over! The winner is {winner['name']} from District {winner['district']}!")
        else:
            await ctx.send("The game is over! No one survived.")

        # Reset players
        await self.config.guild(guild).players.set({})
        await self.config.guild(guild).game_active.set(False)

    async def process_day(self, ctx):
        """Process daily events and actions."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        event_outcomes = []
        for player_id, player_data in players.items():
            if not player_data["alive"]:
                continue

            if player_data.get("is_npc"):
                player_data["action"] = random.choice(["Hunt", "Hunker Down", "Loot"])

            action = player_data["action"]
            if action == "Hunt":
                event_outcomes.append(f"{player_data['name']} went hunting!")
            elif action == "Hunker Down":
                event_outcomes.append(f"{player_data['name']} hunkered down for safety.")
            elif action == "Loot":
                event_outcomes.append(f"{player_data['name']} searched for resources.")
            elif action == None:
                event_outcomes.append(f"{player_data['name']} decided to do absolutely nothing")

            # Reset action for the next day
            player_data["action"] = None

        # Random daily event
        event_roll = random.randint(1, 100)
        if event_roll <= 30:
            event_outcomes.append("A deadly storm swept through the arena!")
            for player_id, player_data in players.items():
                if player_data["alive"]:
                    damage = random.randint(1, 5)
                    player_data["stats"]["HP"] -= damage
                    if player_data["stats"]["HP"] <= 0:
                        player_data["alive"] = False
                        event_outcomes.append(f"{player_data['name']} was killed by the storm!")

        await self.config.guild(guild).players.set(players)
        await ctx.send("\n".join(event_outcomes))

    @hunger.command()
    async def action(self, ctx, choice: str):
        """Choose your daily action: Hunt, Hunker Down, or Loot."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        if str(ctx.author.id) not in players or not players[str(ctx.author.id)]["alive"]:
            await ctx.send("You are not part of the game or are no longer alive.")
            return

        if choice not in ["Hunt", "Hunker Down", "Loot"]:
            await ctx.send("Invalid action. Choose Hunt, Hunker Down, or Loot.")
            return

        players[str(ctx.author.id)]["action"] = choice
        await self.config.guild(guild).players.set(players)
        await ctx.send(f"{ctx.author.mention} has chosen to {choice}.")

    @hunger.command()
    @commands.admin()
    async def setdaylength(self, ctx, seconds: int):
        """Set the real-time length of a day in seconds (Admin only)."""
        guild = ctx.guild
        await self.config.guild(guild).day_duration.set(seconds)
        await ctx.send(f"Day length has been set to {seconds} seconds.")

    @hunger.command()
    @commands.admin()
    async def stopgame(self, ctx):
        """Stop the Hunger Games early (Admin only). Reset everything."""
        guild = ctx.guild
        await self.config.guild(guild).clear()
        await self.config.guild(guild).set({
            "districts": {},
            "players": {},
            "game_active": False,
            "day_duration": 3600,
            "day_start": None,
        })
        await ctx.send("The Hunger Games have been stopped early by the admin. All settings and players have been reset.")
        self.endGame(ctx)
