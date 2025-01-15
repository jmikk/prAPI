from redbot.core import commands, Config
import random
import asyncio
from datetime import datetime, timedelta
import os
import discord
from discord.ext.commands import CheckFailure

#todo list

def is_gamemaster():
    """Check if the user has the GameMaster role."""
    async def predicate(ctx):
        gamemaster_role = discord.utils.get(ctx.guild.roles, name="GameMaster")
        if not gamemaster_role:
            raise CheckFailure("The 'GameMaster' role does not exist in this server.")
        if gamemaster_role not in ctx.author.roles:
            raise CheckFailure("You do not have the 'GameMaster' role.")
        return True
    return commands.check(predicate)

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
        self.config.register_user(
            gold=0,
            bets={},
            kill_count=0,  # Track total kills
        )


    
    async def load_file(self,fileName,name1="Name1 Filler",name2="Name2 Filler",dmg="DMG Filler",dmg2="DMG2 Filler", item_name="Item name filler"):
        """Load file names from the fileName.txt file."""
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_path, fileName)
            with open(file_path, "r") as f:
                line =  [line.strip() for line in f.readlines() if line.strip()]
                line = random.choice(line)
                line = line.replace("{name1}",str(name1)).replace("{name2}",str(name2)).replace("{dmg}",str(dmg)).replace("{item}",str(item_name)).replace("{dmg2}",str(dmg2))
                return line
        except FileNotFoundError:
            return f"ERROR {fileName} not found"  # Fallback if file is missing

    
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
       
        # Award 100 gold to the player in user config
        user_gold = await self.config.user(ctx.author).gold()
        user_gold += 100
        await self.config.user(ctx.author).gold.set(user_gold)
        
        if str(ctx.author.id) in players:
            await ctx.send("You are already signed up!")
            return

        # Assign random district and stats
        district = random.randint(1, 12)  # Assume 12 districts
        stats = {
            "Def": random.randint(1, 10),
            "Str": random.randint(1, 10),
            "Con": random.randint(1, 10),
            "Wis": random.randint(1, 10),
            "HP": random.randint(15, 25)
        }
        if district == 1:
            stats["Def"] = stats["Def"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 2:
            stats["Def"] = stats["Def"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"]
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 3:
            stats["Def"] = stats["Def"]
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 4:
            stats["Def"] = stats["Def"] + 1
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 10
        elif district == 5:
            stats["Def"] = stats["Def"] + 1
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] + 1
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 6:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 5
        elif district == 7:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 10
        elif district == 8:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 9:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] + 1
            stats["HP"] = stats["HP"] + 5
        elif district == 10:
            stats["Def"] = stats["Def"] 
            stats["Str"] = stats["Str"] + 1
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] 
        elif district == 11:
            stats["Def"] = stats["Def"]
            stats["Str"] = stats["Str"] 
            stats["Con"] = stats["Con"] 
            stats["Wis"] = stats["Wis"] 
            stats["HP"] = stats["HP"] + 5
        elif district == 12:
            stats["Def"] = stats["Def"] 
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
    @is_gamemaster()
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
    @is_gamemaster()
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
        if len(players)>25: 
            await ctx.send("Sorry only 25 people can play (this includes NPCs)")
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
                    "Def": random.randint(1, 10),
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
    
                day_start = datetime.fromisoformat(config["day_start"])
                day_duration = timedelta(seconds=config["day_duration"])
                if datetime.utcnow() - day_start >= day_duration:
                    await self.process_day(ctx)
                    if await self.isOneLeft(guild):
                        await self.endGame(ctx)
                        break
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

        await self.config.guild(guild).players.set(players)

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
        return len(alive_players) <= 1

    async def endGame(self, ctx):
        """End the game and announce the winner."""
        guild = ctx.guild
        config = await self.config.guild(guild).all()
        players = config["players"]
        leaderboard = config.get("elimination_leaderboard", [])
        all_users = await self.config.all_users()  # Fetch all users
    
        alive_players = [player for player in players.values() if player["alive"]]
    
        if alive_players:
            winner = alive_players[0]
            winner_id = next((pid for pid, pdata in players.items() if pdata == winner), None)
            await ctx.send(f"The game is over! The winner is {winner['name']} from District {winner['district']}!")
        else:
            await ctx.send("The game is over! No one survived.")
    
        # Send elimination leaderboard
        if leaderboard:
            leaderboard.sort(key=lambda x: x["day"])  # Sort by elimination day
            
            # Create the elimination leaderboard embed
            elim_embed = discord.Embed(
                title="🏅 Elimination Leaderboard 🏅",
                description="Here are the players eliminated so far:",
                color=discord.Color.red(),
            )
            for entry in leaderboard:
                elim_embed.add_field(
                    name=f"Day {entry['day']}",
                    value=f"{entry['name']}",
                    inline=False
                )
            await ctx.send(embed=elim_embed)
    
            # Fetch player data and sort by kill count
            guild_data = await self.config.guild(ctx.guild).all()
            players = guild_data["players"]
            sorted_players = sorted(players.values(), key=lambda p: len(p["kill_list"]), reverse=True)
            
            # Create the kill leaderboard embed
            kill_embed = discord.Embed(
                title="🏆 Kill Leaderboard 🏆",
                description="Here are the top killers:",
                color=discord.Color.gold(),
            )
            for i, player in enumerate(sorted_players, start=1):
                kills = len(player["kill_list"])
                if kills == 1:
                    kill_embed.add_field(
                        name="",
                        value=f"**{i}.** {player['name']}: {kills} kill\nKilled: {', '.join(player['kill_list'])}",
                        inline=False)
                else:
                    kill_embed.add_field(
                        name="",
                        value=f"**{i}.** {player['name']}: {kills} kills\nKilled: {', '.join(player['kill_list'])}",
                        inline=False)
            await ctx.send(embed=kill_embed)


            # Distribute winnings
        for user_id, user_data in all_users.items():
            bets = user_data.get("bets", {})
            user_gold = user_data.get("gold", 0)
    
            for tribute_id, bet_data in bets.items():
                if tribute_id == winner_id:
                    # Pay double the bet amount + daily earnings for the winner
                    user_gold += bet_data["amount"] * 2


            # Update total kill counts for each player
        for player_id, player_data in players.items():
            if not player_data.get("is_npc") and player_data["kill_list"]:
                user_id = int(player_id)
                total_kills = len(player_data["kill_list"])
                current_kill_count = await self.config.user_from_id(user_id).kill_count()
                await self.config.user_from_id(user_id).kill_count.set(current_kill_count + total_kills)

        # Clear bets after game ends
        await self.config.user_from_id(user_id).gold.set(user_gold)
        await self.config.user_from_id(user_id).bets.set({})

    
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

        if day_counter > 5:
            reduction = ((day_counter - 5) // 5) + 1     
            
            event_outcomes.append("A mysterious mist has descended upon the arena, sapping the abilites of all participants!")

            for player_id, player_data in players.items():
                if not player_data["alive"]:
                    continue
    
                # Choose a random stat to reduce
                stats = ["Def", "Str", "Con", "Wis", "HP"]
                stat_to_reduce = random.choice(stats)
                player_data["stats"][stat_to_reduce] -= reduction

                # Check if the player dies
                if player_data["stats"][stat_to_reduce] <= 0:
                    player_data["alive"] = False
                    event_outcomes.append(f"{player_data['name']} succumbed to the mist and perished.")
                    player_data["items"] = []  # Drop all items



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
                        ["Hunt", "Rest", "Loot"], weights=[player_data["stats"]["Str"], player_data["stats"]["Con"]+len(player_data["items"])*3, player_data["stats"]["Wis"]], k=1
                    )[0]

            if player_data.get("is_npc"):
                if config["feast_active"]:
                    # 80% chance NPC attends the Feast, adjust weights as needed
                    player_data["action"] = random.choices(
                        ["Feast", "Hunt", "Rest", "Loot"], weights=[60, 20, 10, 10], k=1
                    )[0]
                else:
                    player_data["action"] = random.choices(["Hunt", "Rest", "Loot"], weights=[player_data["stats"]["Str"], player_data["stats"]["Con"]+len(player_data["items"])*3, player_data["stats"]["Wis"]], k=1)[0]
            
            action = player_data["action"]

            if action == "Hunt":
                hunters.append(player_id)
                #event_outcomes.append(f"{player_data['name']} went hunting!")
            elif action == "Rest":
                resters.append(player_id)
                threshold = 1 / (1 + player_data["stats"]["Con"] / 3)  # Scale slows the decrease
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
                    stat = random.choice(["Def", "Str", "Con", "Wis", "HP"])
                    if stat == "HP":
                        boost = random.randint(5,10)
                    else:
                        boost = random.randint(1, 3)
                    player_data["items"].append((stat, boost))

                    
                    effect = await self.load_file(
                        f"loot_good_{stat}.txt",
                        name1=player_data['name'],
                        dmg=boost,
                        )

                    event_outcomes.append(effect)
                else:
                    threshold = 1 / (1 + player_data["stats"]["Wis"] / 10)  # Scale slows the decrease
                    if random.random() < threshold:
                        damage = random.randint(1,5)
                        player_data["stats"]["HP"]=player_data["stats"]["HP"] - damage

                        effect = await self.load_file(
                            f"loot_real_bad.txt",
                            name1=player_data['name'],
                            dmg=damage,
                            )
                        event_outcomes.append(effect)
                        
                        if player_data["stats"]["HP"] <= 0:
                            player_data["alive"] = False
                            event_outcomes.append(f"{player_data['name']} has been eliminated by themselves?!")
                            player_data["kill_list"].append(player_data['name'])
                            player_data["items"] = []
                    else:
                        effect = await self.load_file("loot_bad.txt",name1=player_data['name'])
                        event_outcomes.append(effect)
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

            target_defense = target["stats"]["Def"] + random.randint(1, 10)
            hunter_str = hunter["stats"]["Str"] + random.randint(1, 10)
            damage = abs(hunter_str - target_defense)

            if damage < 2:
                damage1 = damage + random.randint(1,3)
                target["stats"]["HP"] -= damage1
                damage2 = damage + random.randint(1,3)
                hunter["stats"]["HP"] -= damage2

                effect = await self.load_file(
                    "tie_attack.txt",
                    name1=hunter['name'],
                    name2=target['name'],
                    dmg=damage1,
                    dmg2=damage2
                    )
                
                event_outcomes.append(effect)
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
                    
                    effect = await self.load_file(
                        "feast_attack.txt",
                        name1=hunter['name'],
                        name2=target['name'],
                        dmg=damage,
                        )
                    
                    event_outcomes.append(effect)
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

                    effect = await self.load_file(
                        "feast_attack.txt",
                        name1=target['name'],
                        name2=hunter['name'],
                        dmg=damage,
                        )
                    
                    event_outcomes.append(effect)
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
                for stat in ["Def", "Str", "Con", "Wis", "HP"]:
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
                        target_str = target["stats"]["Def"] + random.randint(1, 10)
    
                        if participant_str > target_str:
                            damage = participant_str - target_str
                            target["stats"]["HP"] -= damage
                          
                            effect = await self.load_file(
                                "feast_attack.txt",
                                name1=participant['name'],
                                name2=target['name'],
                                dmg=damage
                            )
                            
                            event_outcomes.append(effect)
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
                            effect = await self.load_file(
                                "feast_attack.txt",
                                name1=target['name'],
                                name2=participant['name'],
                                dmg=damage
                            )
                            event_outcomes.append(effect)
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
                    stats_to_distribute = ["Def", "Str", "Con", "Wis", "HP"]
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
        
        # Process daily bet earnings
        players = await self.config.guild(guild).players()
        all_users = await self.config.all_users()
        
        for user_id, user_data in all_users.items():
            bets = user_data.get("bets", {})
            user_gold = user_data.get("gold", 0)
        
            for tribute_id, bet_data in bets.items():
                if tribute_id in players and players[tribute_id]["alive"]:
                    daily_return = int(bet_data["amount"] * 0.1)  # 10% daily return
                    bet_data["daily_earnings"] += daily_return
                    user_gold += daily_return
        
            await self.config.user_from_id(user_id).gold.set(user_gold)
            await self.config.user_from_id(user_id).bets.set(bets)

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
    @is_gamemaster()
    async def setdaylength(self, ctx, seconds: int):
        """Set the real-time length of a day in seconds (Admin only)."""
        guild = ctx.guild
        await self.config.guild(guild).day_duration.set(seconds)
        await ctx.send(f"Day length has been set to {seconds} seconds.")

    @hunger.command()
    @is_gamemaster()
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
        
        all_users = await self.config.all_users()
        for user_id, user_data in all_users.items():
            await self.config.user_from_id(user_id).bets.set({})
        
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
            embed.add_field(name="Def", value=player["stats"]["Def"], inline=True)
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
            embed.add_field(name="Def", value=player["stats"]["Def"], inline=True)
            embed.add_field(name="Str", value=player["stats"]["Str"], inline=True)
            embed.add_field(name="Con", value=player["stats"]["Con"], inline=True)
            embed.add_field(name="Wis", value=player["stats"]["Wis"], inline=True)
            embed.add_field(name="HP", value=player["stats"]["HP"], inline=True)
            embed.add_field(name="Alive", value="Yes" if player["alive"] else "No", inline=False)
            await ctx.send(embed=embed, ephemeral=True)

    @hunger.command()
    async def place_bet(self, ctx, amount: int, *, tribute: str):
        """Place a bet on a tribute."""

        if not ("<" in tribute):
            tribute = f"**{tribute}**"

        tribute = tribute.strip()  # Clean up any extra spaces        
        
        if amount <= 0:
            await ctx.send("Bet amount must be greater than zero.")
            return
    
        user_gold = await self.config.user(ctx.author).gold()
        if amount > user_gold:
            await ctx.send("You don't have enough gold to place that bet. You can always play in the games to earn money.")
            return
    
        guild = ctx.guild
        players = await self.config.guild(guild).players()
        tribute = tribute.lower()

        config = await self.config.guild(guild).all()
        
        day_counter = config.get("day_counter", 0)

        # Restrict betting to days 1 and 2
        if day_counter > 1:
            await ctx.send("Betting is only allowed on Day 0 and Day 1.")
            return
    
        # Validate tribute
        tribute_id = next((pid for pid, pdata in players.items() if pdata["name"].lower() == tribute), None)
        if not tribute_id:
            await ctx.send("Tribute not found. Please check the name and try again.")
            return
    
        # Save the bet
        user_bets = await self.config.user(ctx.author).bets()
        if tribute_id in user_bets:
            await ctx.send("You have already placed a bet on this tribute.")
            return
    
        user_bets[tribute_id] = {
            "amount": amount,
            "daily_earnings": 0
        }
        await self.config.user(ctx.author).bets.set(user_bets)
    
        # Deduct gold
        await self.config.user(ctx.author).gold.set(user_gold - amount)
    
        tribute_name = players[tribute_id]["name"]
        await ctx.send(f"{ctx.author.mention} has placed a bet of {amount} gold on {tribute_name}. Good luck!")
    
    @hunger.command()
    async def check_gold(self, ctx):
        """Check your current gold."""
        user_gold = await self.config.user(ctx.author).gold()
        await ctx.send(f"{ctx.author.mention}, you currently have {user_gold} gold.")

    @hunger.command()
    async def leaderboard(self, ctx):
        """Display leaderboards for total kills and gold."""
        all_users = await self.config.all_users()
        
        # Gather and sort kill counts
        kill_leaderboard = sorted(
            all_users.items(),
            key=lambda x: x[1].get("kill_count", 0),
            reverse=True
        )
        
        # Gather and sort gold counts
        gold_leaderboard = sorted(
            all_users.items(),
            key=lambda x: x[1].get("gold", 0),
            reverse=True
        )
        
        # Build the embed
        embed = discord.Embed(title="🏆 Hunger Games Leaderboard 🏆", color=discord.Color.gold())
    
        # Add top players by kills
        if kill_leaderboard:
            kills_text = "\n".join(
                f"**{ctx.guild.get_member(int(user_id)).mention}**: {data['kill_count']} kills"
                for user_id, data in kill_leaderboard[:10]
                if ctx.guild.get_member(int(user_id))  # Ensure the user exists in the guild
            )
            embed.add_field(name="Top Killers", value=kills_text or "No data", inline=False)
    
        # Add top players by gold
        if gold_leaderboard:
            gold_text = "\n".join(
                f"**{ctx.guild.get_member(int(user_id)).mention}**: {data['gold']} gold"
                for user_id, data in gold_leaderboard[:10]
                if ctx.guild.get_member(int(user_id))  # Ensure the user exists in the guild
            )
            embed.add_field(name="Top Richest Players", value=gold_text or "No data", inline=False)
    
        await ctx.send(embed=embed)
    
    @hunger.command()
    @commands.admin()
    async def reset_leaderboard(self, ctx):
        """Reset all user kill counts and gold."""
        all_users = await self.config.all_users()
        for user_id in all_users:
            await self.config.user_from_id(int(user_id)).kill_count.set(0)
            await self.config.user_from_id(int(user_id)).gold.set(0)
        await ctx.send("Leaderboards have been reset.")


    
    
    

    
