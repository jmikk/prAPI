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
            day_duration=10,  # Default: 1 hour in seconds
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
            "action": None,
            "items": []
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
                "is_npc": True,
                "items": []
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
        hunted = set()
        hunters = []
        looters = []
        resters = []

        for player_id, player_data in players.items():
            if not player_data["alive"]:
                continue

            if player_data.get("is_npc"):
                player_data["action"] = random.choice(["Hunt", "Rest", "Loot"])

            action = player_data["action"]
            if action == "Hunt":
                hunters.append(player_id)
                event_outcomes.append(f"{player_data['name']} went hunting!")
            elif action == "Rest":
                resters.append(player_id)
                if player_data["items"]:
                    item = player_data["items"].pop()
                    stat, boost = item
                    player_data["stats"][stat] += boost
                    event_outcomes.append(f"{player_data['name']} rested and used a {stat} boost item (+{boost}).")
                else:
                    event_outcomes.append(f"{player_data['name']} rested but had no items to use.")
            elif action == "Loot":
                looters.append(player_id)
                if random.random() < 0.5:  # 50% chance to find an item
                    stat = random.choice(["Dex", "Str", "Con", "Wis", "HP","HP","HP"])
                    boost = random.randint(1, 3)
                    player_data["items"].append((stat, boost))
                    event_outcomes.append(f"{player_data['name']} looted and found a {stat} boost item (+{boost}).")
                else:
                    event_outcomes.append(f"{player_data['name']} looted but found nothing.")

        # Shuffle hunters for randomness
        random.shuffle(hunters)

        # Resolve hunting events
        targeted_hunters = hunters[:]
        targeted_looters = looters[:]
        targeted_resters = resters[:]

        for hunter_id in hunters:
            if hunter_id in hunted:
                continue

            # Prioritize hunters first
            if targeted_hunters:
                target_id = targeted_hunters.pop(0)
            elif targeted_looters:
                target_id = targeted_looters.pop(0)
            elif targeted_resters:
                target_id = targeted_resters.pop(0)
            else:
                continue

            if target_id in hunted:
                continue

            hunter = players[hunter_id]
            target = players[target_id]

            hunter_str = hunter["stats"]["Str"]
            target_defense = max(target["stats"]["Str"], target["stats"]["Dex"])
            damage = abs(hunter_str - target_defense)

            if hunter_str > target_defense:
                target["stats"]["HP"] -= damage
                event_outcomes.append(f"{hunter['name']} hunted {target['name']} and dealt {damage} damage!")
                if target["stats"]["HP"] <= 0:
                    target["alive"] = False
                    event_outcomes.append(f"{target['name']} has been eliminated by {hunter['name']}!")
            else:
                hunter["stats"]["HP"] -= damage
                event_outcomes.append(f"{target['name']} defended against {hunter['name']} and dealt {damage} damage in return!")
                               if hunter["stats"]["HP"] <= 0:
                    hunter["alive"] = False
                    event_outcomes.append(f"{hunter['name']} has been eliminated by {target['name']}!")

            # Mark both the hunter and target as involved in an event
            hunted.add(target_id)
            hunted.add(hunter_id)

        # Save the updated players' state
        await self.config.guild(guild).players.set(players)

        # Announce the day's events
        if event_outcomes:
            await ctx.send("\n".join(event_outcomes))
        else:
            await ctx.send("The day passed quietly, with no significant events.")

    @hunger.command()
    async def action(self, ctx, choice: str):
        """Choose your daily action: Hunt, Rest, or Loot."""
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        if str(ctx.author.id) not in players or not players[str(ctx.author.id)]["alive"]:
            await ctx.send("You are not part of the game or are no longer alive.")
            return

        if choice not in ["Hunt", "Rest", "Loot"]:
            await ctx.send("Invalid action. Choose Hunt, Rest, or Loot.")
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

