from redbot.core import commands, Config
import random
import asyncio
from datetime import datetime, timedelta
import os
import discord

#clean up list
#Add custom lines for:
#Hunting
#Resting
#Looting
#Evenly matched Huntinga
#item names

#todo list

#More aggressive AI for NPCs
#kill count leaderboard


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
            day_counter=0, 
            random_events=True,  # Enable or disable random events
            feast_active=False,  # Track if a feast is active# Counter for days
            
        )

    async def load_npc_names(self):
        """Load NPC names from the NPC_names.txt file."""
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_path, "NPC_names.txt")
            with open(file_path, "r") as f:
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
        if district == 1:
            stats["Dex"] = stats["Dex"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 2:
            stats["Dex"] = stats["Dex"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"]
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 3:
            stats["Dex"] = stats["Dex"]
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 4:
            stats["Dex"] = stats["Dex"] + 1
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 10
        elif district == 5:
            stats["Dex"] = stats["Dex"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 6:
            stats["Dex"] = stats["Dex"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 5
        elif district == 7:
            stats["Dex"] = stats["Dex"] 
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 8:
            stats["Dex"] = stats["Dex"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 9:
            stats["Dex"] = stats["Dex"] 
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 5
        elif district == 10:
            stats["Dex"] = stats["Dex"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] 
        elif district == 11:
            stats["Dex"] = stats["Dex"]
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 12:
            stats["Dex"] = stats["Dex"] 
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"]
            
        

        players[str(ctx.author.id)] = {
            "name": ctx.author.display_name,
            "district": district,
            "stats": stats,
            "alive": True,
            "action": None,
            "items": [],
            "kill_list": [],  
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
            
        # Load and shuffle NPC names
        npc_names = await self.load_npc_names()
        random.shuffle(npc_names)

        # Track used NPC names and add NPCs
        used_names = set(player["name"] for player in players.values() if player.get("is_npc"))
        available_names = [name for name in npc_names if name not in used_names]

        if len(available_names) < npcs:
            await ctx.send("Not enough unique NPC names available for the requested number of NPCs.")
            return

        for i in range(npcs):
            npc_id = f"npc_{i+1}"
            players[npc_id] = {
                "kill_list" : [] ,
                "name": available_names.pop(0),  # Get and remove the first available name
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

        for player_id, player_data in players.items():
            if player_data.get("is_npc", False):
                # Bold NPC names
                player_data["name"] = f"**{player_data['name']}**"
            else:
                # Mention real players
                member = guild.get_member(int(player_id))
                if member:
                    player_data["name"] = member.mention  # Replace name with mention
                else:
                    player_data["name"] = player_data["name"]  # Fallback to original name
        


        await self.config.guild(guild).players.set(players)
        await self.config.guild(guild).game_active.set(True)
        await self.config.guild(guild).day_start.set(datetime.utcnow().isoformat())
        await self.config.guild(guild).day_counter.set(0)

        # Announce all participants with mentions for real players, sorted by district
        sorted_players = sorted(players.values(), key=lambda p: p["district"])
        participant_list = []
        for player in sorted_players:
            if player.get("is_npc"):
                participant_list.append(f"{player['name']} from District {player['district']}")
            else:
                member = guild.get_member(int(next((k for k, v in players.items() if v == player), None)))
                if member:
                    participant_list.append(f"{member.mention} from District {player['district']}")

        participant_announcement = "\n".join(participant_list)
        await ctx.send(f"The Hunger Games have begun with the following participants (sorted by District):\n{participant_announcement}")

        asyncio.create_task(self.run_game(ctx))

    async def run_game(self, ctx):
        """Handle the real-time simulation of the game."""
        try:
            guild = ctx.guild
            await self.announce_new_day(ctx, guild)
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
                    await self.process_day(ctx)
                    await self.announce_new_day(ctx, guild)
                    await self.config.guild(guild).day_start.set(datetime.utcnow().isoformat())
    
                await asyncio.sleep(10)  # Check every 10 seconds
        except Exception as e:
            await ctx.send(e)
            await ctx.send(traceback.format_exc())
            

    async def announce_new_day(self, ctx, guild):
        """Announce the start of a new day and ping alive players."""
        await ctx.send("https://i.imgur.com/gtCA6wO.png")
        config = await self.config.guild(guild).all()
        players = config["players"]

        # Reset all player actions to None
        for player_id, player_data in players.items():
            if player_data["alive"]:  # Only reset actions for alive players
                player_data["action"] = None

        # Increment day counter

        # Handle Feast Activation
        #await ctx.send(day_counter)
        if config["day_counter"] % 10 == 0:
            # Feast is active on Day 1 and every 10th day
            await self.config.guild(guild).feast_active.set(True)
            config = await self.config.guild(guild).all()

        else:
            # Ensure Feast is not active on other days
            await self.config.guild(guild).feast_active.set(False)
            config = await self.config.guild(guild).all()


        # Get alive players count
        alive_players = [player for player in players.values() if player["alive"]]
        alive_count = len(alive_players)

        feast_active = config.get("feast_active", False)
        feast_message = "A Feast has been announced! Attend by choosing `Feast` as your action today." if feast_active else ""

        alive_mentions = []
        for player_id, player_data in players.items():
            if player_data["alive"]:
                if player_data.get("is_npc"):
                    # NPC names are appended as text
                    alive_mentions.append(f"{player_data['name']}")
                else:
                    # Real players are pinged using mentions
                    member = guild.get_member(int(player_id))
                    if member:
                        alive_mentions.append(member.mention)

        # Send the announcement with all alive participant
        # Send the announcement
        await ctx.send(
            f"Day {config['day_counter']} begins in the Hunger Games! {alive_count} participants remain.\n"
            f"{feast_message}\n"
            f"Alive participants: {', '.join(alive_mentions)}"
        )

    async def isOneLeft(self, guild):
        """Check if only one player is alive."""
        players = await self.config.guild(guild).players()
        alive_players = [player for player in players.values() if player["alive"]]
        return len(alive_players) == 1

    async def endGame(self, ctx):
        """End the game and announce the winner."""
        guild = ctx.guild
        config = await self.config.guild(guild).all()
        players = config["players"]
        leaderboard = config.get("elimination_leaderboard", [])
    
        alive_players = [player for player in players.values() if player["alive"]]
    
        if alive_players:
            winner = alive_players[0]
            await ctx.send(f"The game is over! The winner is {winner['name']} from District {winner['district']}!")
        else:
            await ctx.send("The game is over! No one survived.")
    
        # Send elimination leaderboard
        if leaderboard:
            leaderboard.sort(key=lambda x: x["day"])  # Sort by elimination day
            leaderboard_message = "Elimination Leaderboard:\n" + "\n".join(
                [f"Day {entry['day']}: {entry['name']}" for entry in leaderboard]
            )
            await ctx.send(leaderboard_message)

            guild_data = await self.config.guild(ctx.guild).all()
      
        players = guild_data["players"]
        # Sort players by kill count (descending)
        sorted_players = sorted(players.values(), key=lambda p: len(p["kill_list"]), reverse=True)
    
        # Generate leaderboard message
        leaderboard = "🏆 **Kill Leaderboard** 🏆\n"
        for i, player in enumerate(sorted_players, start=1):
            leaderboard += f"**{i}. {player['name']}** - {len(player['kill_list'])} kills\n"
            if len(player["kill_list"]) > 0:
                leaderboard += f"    Killed: {', '.join(player['kill_list'])}\n"
    
        # Send the leaderboard
        await ctx.send(leaderboard)
    
        # Reset players
        await self.config.guild(guild).players.set({})
        await self.config.guild(guild).game_active.set(False)
        await self.config.guild(guild).elimination_leaderboard.set([])  # Reset leaderboard


    async def process_day(self, ctx):
        """Process daily events and actions."""
        guild = ctx.guild
        config = await self.config.guild(guild).all()  # Add this line to fetch config
        players = config["players"]
        event_outcomes = []
        hunted = set()
        hunters = []
        looters = []
        resters = []
        feast_participants = []  # Separate list for Feast participants
        eliminations = []
                
        day_counter = config.get("day_counter", 0) + 1
        await self.config.guild(guild).day_counter.set(day_counter)




        # Categorize players by action
        for player_id, player_data in players.items():
            if not player_data["alive"]:
                continue
            
            if config["feast_active"] and player_data.get("action") is None:
                player_data["action"] = random.choices(
                        ["Feast", "Hunt", "Rest", "Loot"], weights=[60, 20, 10, 10], k=1
                    )[0]
            elif player_data.get("action") is None:
                player_data["action"] = random.choices(
                        ["Hunt", "Rest", "Loot"], weights=[70, 15, 15], k=1
                    )[0]

            if player_data.get("is_npc"):
                if config["feast_active"]:
                    # 80% chance NPC attends the Feast, adjust weights as needed
                    player_data["action"] = random.choices(
                        ["Feast", "Hunt", "Rest", "Loot"], weights=[100, 0, 0, 0], k=1
                    )[0]
                else:
                    player_data["action"] = random.choices(["Hunt", "Rest", "Loot"], weights=[70, 15, 15], k=1)[0]
            
            action = player_data["action"]

            if action == "Hunt":
                hunters.append(player_id)
                #event_outcomes.append(f"{player_data['name']} went hunting!")
            elif action == "Rest":
                resters.append(player_id)
                threshold = 1 / (1 + player_data["stats"]["Con"] / 4)  # Scale slows the decrease
                if random.random() < threshold or not player_data["items"]: #take dmg
                    damage = random.randint(1,5)
                    player_data["stats"]["HP"]=player_data["stats"]["HP"] - damage
                    event_outcomes.append(f"{player_data['name']} has hunger pains and takes {damage} points of damage")
                    if player_data["stats"]["HP"] <= 0:
                        player_data["alive"] = False
                        event_outcomes.append(f"{player_data['name']} starved to death.")
                        player_data["items"] = []
                    
                else:
                    item = player_data["items"].pop()
                    stat, boost = item
                    player_data["stats"][stat] += boost
                    event_outcomes.append(f"{player_data['name']} rested and used a {stat} boost item (+{boost}).")
                    
            elif action == "Loot":
                looters.append(player_id)
                if random.random() < 0.5:  # 50% chance to find an item
                    stat = random.choice(["Dex", "Str", "Con", "Wis", "HP"])
                    if stat == "HP":
                        boost = random.randint(5,10)
                    else:
                        boost = random.randint(1, 3)
                    player_data["items"].append((stat, boost))
                    event_outcomes.append(f"{player_data['name']} looted and found a {stat} boost item (+{boost}).")
                else:
                    threshold = 1 / (1 + player_data["stats"]["Wis"] / 10)  # Scale slows the decrease
                    if random.random() < threshold:
                        damage = random.randint(1,5)
                        player_data["stats"]["HP"]=player_data["stats"]["HP"] - damage
                        event_outcomes.append(f"{player_data['name']} done gone looted and stubbed their toe and took {damage} points of damage.")
                        if player_data["stats"]["HP"] <= 0:
                            player_data["alive"] = False
                            event_outcomes.append(f"{player_data['name']} has been eliminated by themself?!")
                            player_data["kill_list"].append(player_data['name'])
                            player_data["items"] = []
                    else:
                        event_outcomes.append(f"{player_data['name']} looted but found nothing.")
            elif action == "Feast":
                feast_participants.append(player_id)

        # Shuffle hunters for randomness
        random.shuffle(hunters)

        # Create priority target lists
        targeted_hunters = hunters[:]
        targeted_looters = looters[:]
        targeted_resters = resters[:]

        # Resolve hunting events
        for hunter_id in hunters:
            if hunter_id in hunted:
                continue

            # Find a target in priority order, excluding the hunter themselves
            target_id = None
            for target_list in [targeted_hunters, targeted_looters, targeted_resters]:
                while target_list:
                    potential_target = target_list.pop(0)
                    if potential_target != hunter_id and potential_target not in hunted:
                        target_id = potential_target
                        break
                if target_id:
                    break

            if not target_id:
                continue

            hunter = players[hunter_id]
            target = players[target_id]

            target_defense = target["stats"]["Str"] + random.randint(1, 10)
            hunter_str = max(hunter["stats"]["Str"], hunter["stats"]["Dex"]) + random.randint(1, 10)
            damage = abs(hunter_str - target_defense)

            if damage < 2:
                damage1 = damage + random.randint(1,3)
                target["stats"]["HP"] -= damage1
                damage2 = damage + random.randint(1,3)
                hunter["stats"]["HP"] -= damage2
                event_outcomes.append(f"{hunter['name']} hunted {target['name']} but the two were evenly matched dealing {damage1} to {target['name']} and {damage2} to {hunter['name']}")
                if target["stats"]["HP"] <= 0:
                    target["alive"] = False
                    event_outcomes.append(f"{target['name']} has been eliminated by {hunter['name']}!")
                    hunter["kill_list"].append(target['name'])
                    if target["items"]:
                        hunter["items"].extend(target["items"])
                        event_outcomes.append(
                            f"{hunter['name']} looted {len(target['items'])} item(s) from {target['name']}."
                        )
                        target["items"] = [] 
                        
                if hunter["stats"]["HP"] <= 0:
                    hunter["alive"] = False
                    event_outcomes.append(f"{hunter['name']} has been eliminated by {target['name']}!")
                    target["kill_list"].append(hunter['name'])
                    if hunter["items"]:
                        target["items"].extend(hunter["items"])
                        event_outcomes.append(
                            f"{target['name']} looted {len(hunter['items'])} item(s) from {hunter['name']}."
                        )
                        hunter["items"] = []
            else:
                if hunter_str > target_defense:
                    target["stats"]["HP"] -= damage
                    event_outcomes.append(f"{hunter['name']} hunted {target['name']} and dealt {damage} damage!")
                    if target["stats"]["HP"] <= 0:
                        target["alive"] = False
                        event_outcomes.append(f"{target['name']} has been eliminated by {hunter['name']}!")
                        hunter["kill_list"].append(target['name'])
                        if target["items"]:
                            hunter["items"].extend(target["items"])
                            event_outcomes.append(
                                f"{hunter['name']} looted {len(target['items'])} item(s) from {target['name']}."
                            )
                            target["items"] = [] 
                else:
                    hunter["stats"]["HP"] -= damage
                    event_outcomes.append(f"{target['name']} defended against {hunter['name']} and dealt {damage} damage in return!")
                    if hunter["stats"]["HP"] <= 0:
                        hunter["alive"] = False
                        event_outcomes.append(f"{hunter['name']} has been eliminated by {target['name']}!")
                        target["kill_list"].append(hunter['name'])
                        if hunter["items"]:
                            target["items"].extend(hunter["items"])
                            event_outcomes.append(
                                f"{target['name']} looted {len(hunter['items'])} item(s) from {hunter['name']}."
                            )
                            hunter["items"] = []

            # Mark both the hunter and target as involved in an event
            hunted.add(target_id)
            hunted.add(hunter_id)


            # Resolve Feast after other actions
        if config["feast_active"] and feast_participants:
            if len(feast_participants) == 1:
                # Single participant gains +5 to all stats
                participant = players[feast_participants[0]]
                for stat in ["Dex", "Str", "Con", "Wis", "HP"]:
                    participant["stats"][stat] += 5
                event_outcomes.append(f"{participant['name']} attended the Feast alone and gained +5 to all stats!")
            else:
                # Multiple participants battle it out
                dead_players = []
                for _ in range(3):  # 3 battle rounds
                    if len(feast_participants) <= 1:
                        break
                    for participant_id in feast_participants[:]:
                        if participant_id in dead_players:
                            continue
                        valid_targets = [p for p in feast_participants if p != participant_id and p not in dead_players]
                        if not valid_targets:
                            break
                        target_id = random.choice(valid_targets)
                        participant = players[participant_id]
                        target = players[target_id]
                        participant_str = participant["stats"]["Str"] + random.randint(1, 10)
                        target_str = target["stats"]["Str"] + random.randint(1, 10)
    
                        if participant_str > target_str:
                            damage = participant_str - target_str
                            target["stats"]["HP"] -= damage
                            event_outcomes.append(f"{participant['name']} attacked {target['name']} and dealt {damage} damage!")
                            if target["stats"]["HP"] <= 0:
                                target["alive"] = False
                                dead_players.append(target_id)
                                feast_participants.remove(target_id)
                                participant["items"].extend(target["items"])
                                target["items"] = []
                                event_outcomes.append(f"{target['name']} was eliminated by {participant['name']}!")
                                participant["kill_list"].append(target['name'])
                        else:
                            damage = target_str - participant_str
                            participant["stats"]["HP"] -= damage
                            event_outcomes.append(f"{target['name']} attacked {participant['name']} and dealt {damage} damage!")
                            if participant["stats"]["HP"] <= 0:
                                participant["alive"] = False
                                dead_players.append(participant_id)
                                feast_participants.remove(participant_id)
                                target["items"].extend(participant["items"])
                                participant["items"] = []
                                event_outcomes.append(f"{participant['name']} was eliminated by {target['name']}!")
                                target["kill_list"].append(participant['name'])
    
                # Remaining participants split items and stats
                if feast_participants:
                    all_dropped_items = []
                    for dead_id in dead_players:
                        all_dropped_items.extend(players[dead_id]["items"])
                        players[dead_id]["items"] = []
    
                    # Distribute items
                    if all_dropped_items:
                        random.shuffle(all_dropped_items)
                        for item in all_dropped_items:
                            chosen_participant_id = random.choice(feast_participants)
                            players[chosen_participant_id]["items"].append(item)
                        event_outcomes.append("Feast participants split the items dropped by the eliminated players.")
                        
    
                    # Distribute +5 stat bonuses randomly
                    stat_bonus = 5
                    stats_to_distribute = ["Dex", "Str", "Con", "Wis", "HP"]
                    for _ in range(stat_bonus):
                        for stat in stats_to_distribute:
                            if feast_participants:
                                chosen_participant_id = random.choice(feast_participants)
                                players[chosen_participant_id]["stats"][stat] += 1
                    event_outcomes.append("Surviving Feast participants split the remaining items among themselves! Taking time to apply the boosts.")


        # Save the updated players' state
        await self.config.guild(guild).players.set(players)

        day_counter = config.get("day_counter", 0)
        
        # Elimination announcement and tracking
        for player_id, player_data in players.items():
            if player_data["alive"] is False and "eliminated_on" not in player_data:
                player_data["eliminated_on"] = day_counter  # Track day of elimination
                eliminations.append(player_data)

        await self.config.guild(guild).players.set(players)

        # Announce the day's events
        if event_outcomes:
            # Pings users and bolds NPCs
            for each in event_outcomes:
                await ctx.send(each)
            #await ctx.send("\n".join(event_outcomes))
        else:
           await ctx.send("The day passed quietly, with no significant events.")

    
        # Save elimination leaderboard
        if eliminations:
            leaderboard = config.get("elimination_leaderboard", [])
            for eliminated_player in eliminations:
                leaderboard.append(
                    {"name": eliminated_player["name"], "day": eliminated_player["eliminated_on"]}
                )
            await self.config.guild(guild).elimination_leaderboard.set(leaderboard)


    
    @hunger.command()
    async def action(self, ctx, choice: str):
        """Choose your daily action: Hunt, Rest, or Loot."""
        guild = ctx.guild
        config = await self.config.guild(guild).all()
        players = config["players"]
        
        if str(ctx.author.id) not in players or not players[str(ctx.author.id)]["alive"]:
            await ctx.send("You are not part of the game or are no longer alive.")
            return

        # Check if Feast is a valid action
        valid_actions = ["Hunt", "Rest", "Loot"]
        if config.get("feast_active", False):  # Ensure feast_active is checked correctly
            valid_actions.append("Feast")
    
        choice = choice.capitalize()  # Standardize input capitalization
        if choice not in valid_actions:
            available_actions = ", ".join(valid_actions)
            await ctx.send(f"Invalid action. Choose one of the following: {available_actions}.")
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
            "day_duration": 10,
            "day_start": None,
            "day_counter": 0,
        })
        await ctx.send("The Hunger Games have been stopped early by the admin. All settings and players have been reset.")

    @hunger.command()
    async def viewstats(self, ctx, member: commands.MemberConverter = None):
        """
        View your own stats or, if you're an admin, view another player's stats.
        """
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        
        # If no member is specified, show the stats of the command invoker
        if member is None:
            member_id = str(ctx.author.id)
            if member_id not in players:
                await ctx.send("You are not part of the Hunger Games.", ephemeral=True)
                return
            player = players[member_id]
            embed = discord.Embed(title="Your Stats", color=discord.Color.blue())
            embed.add_field(name="Name", value=player["name"], inline=False)
            embed.add_field(name="District", value=player["district"], inline=False)
            embed.add_field(name="Dex", value=player["stats"]["Dex"], inline=True)
            embed.add_field(name="Str", value=player["stats"]["Str"], inline=True)
            embed.add_field(name="Con", value=player["stats"]["Con"], inline=True)
            embed.add_field(name="Wis", value=player["stats"]["Wis"], inline=True)
            embed.add_field(name="HP", value=player["stats"]["HP"], inline=True)
            embed.add_field(name="Alive", value="Yes" if player["alive"] else "No", inline=False)
            await ctx.send(embed=embed, ephemeral=True)
        else:
            # Admins can view stats for any player
            if not await self.bot.is_admin(ctx.author):
                await ctx.send("You do not have permission to view other players' stats.", ephemeral=True)
                return
    
            member_id = str(member.id)
            if member_id not in players:
                await ctx.send(f"{member.display_name} is not part of the Hunger Games.", ephemeral=True)
                return
    
            player = players[member_id]
            embed = discord.Embed(title=f"{member.display_name}'s Stats", color=discord.Color.green())
            embed.add_field(name="Name", value=player["name"], inline=False)
            embed.add_field(name="District", value=player["district"], inline=False)
            embed.add_field(name="Dex", value=player["stats"]["Dex"], inline=True)
            embed.add_field(name="Str", value=player["stats"]["Str"], inline=True)
            embed.add_field(name="Con", value=player["stats"]["Con"], inline=True)
            embed.add_field(name="Wis", value=player["stats"]["Wis"], inline=True)
            embed.add_field(name="HP", value=player["stats"]["HP"], inline=True)
            embed.add_field(name="Alive", value="Yes" if player["alive"] else "No", inline=False)
            await ctx.send(embed=embed, ephemeral=True)



    
