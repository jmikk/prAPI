from redbot.core import commands, Config
import asyncio
import random
from datetime import datetime
import discord


class HOTW(commands.Cog):
    """Holder of the Water - Server Competition Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "HOTWname": None,
            "timestamp": None,
            "user_data": {}  # Format: {user_id: {"name": name, "total_time": x, "current_streak": y, "longest_streak": z}}
        }
        self.config.register_guild(**default_guild)

    @commands.command()
    async def leaderboard(self, ctx):
        data = await self.config.guild(ctx.guild).all()
        user_data = data["user_data"]

        if not user_data:
            await ctx.send("No HOTW data available yet.")
            return

        # Sort users
        sorted_users_by_time = sorted(user_data.values(), key=lambda x: x["total_time"], reverse=True)
        sorted_users_by_streak = sorted(user_data.values(), key=lambda x: x["longest_streak"], reverse=True)

        # Create leaderboard strings
        time_lb = "**Top 3 by Total Time:**\n"
        streak_lb = "**Top 3 by Longest Streak:**\n"

        for i, u in enumerate(sorted_users_by_time[:3]):
            time_lb += f"{i+1}. {u['name']} - {int(u['total_time'])} seconds\n"

        for i, u in enumerate(sorted_users_by_streak[:3]):
            streak_lb += f"{i+1}. {u['name']} - {int(u['longest_streak'])} seconds\n"

        await ctx.send(time_lb)
        await ctx.send(streak_lb)

    @commands.command()
    async def HOTW(self, ctx):
        guild = ctx.guild
        author = ctx.author

        data = await self.config.guild(guild).all()
        old_holder = data["HOTWname"]
        old_timestamp = data["timestamp"]
        user_data = data["user_data"]

        # Pick random message
        ways_to_take_water = [
            "Bob dives into Joe's bag and emerges with Fancy Water.",
            "Bob distracts Joe with a joke and grabs the Fancy Water.",
            "Bob teleports in, nabs Fancy Water, and vanishes.",
            "Bob trades a fake bottle and keeps the real Fancy Water.",
            "Bob charms Joe out of the Fancy Water with compliments.",
            "Bob picks Joe’s pocket for Fancy Water like a pro.",
            "Bob flips over Joe’s table and runs with Fancy Water.",
            "Bob bets Joe in a game and wins the Fancy Water.",
            "Bob casts a spell to levitate Fancy Water into his hands.",
            "Bob uses a fishing rod to hook Fancy Water from Joe.",
            "Bob sneezes, and Joe looks away — boom, Fancy Water's gone.",
            "Bob drops glitter, grabs Fancy Water in the distraction.",
            "Bob fakes a hug, pockets Fancy Water mid-embrace.",
            "Bob opens a portal, reaches in, and takes Fancy Water from Joe’s world.",
            "Bob writes “IOU” and leaves it where Fancy Water was.",
            "Bob paints a replica, switches it with Joe’s Fancy Water.",
            "Bob bribes Joe’s pet to knock over the Fancy Water.",
            "Bob juggles fire to distract Joe and swipes the bottle.",
            "Bob plays dead, waits for Joe to leave, and claims the water.",
            "Bob pays off Joe’s butler to “lose” the Fancy Water.",
            "Bob poses as a health inspector and “confiscates” the Fancy Water.",
            "Bob leaves a trail of snacks leading Joe away from the water.",
            "Bob hacks Joe’s smart fridge and has Fancy Water delivered.",
            "Bob pretends to be Joe’s future self and claims the water.",
            "Bob convinces Joe that the water is haunted.",
            "Bob sends Joe a fake letter demanding he give up the water.",
            "Bob trains a raccoon to steal Fancy Water on command.",
            "Bob hides in a bush and strikes when Joe blinks.",
            "Bob creates an illusion of Fancy Water — and keeps the real one.",
            "Bob fakes an earthquake to snatch the bottle mid-shake.",
            "Bob leaves a decoy in place of the real Fancy Water.",
            "Bob challenges Joe to a duel and steals it mid-bow.",
            "Bob places a banana peel — Joe slips, and Bob swoops in.",
            "Bob whispers secrets in Joe’s ear, then lifts the bottle.",
            "Bob puts on a mustache and “borrows” the Fancy Water.",
            "Bob time-travels to take the water before Joe even got it.",
            "Bob tricks Joe into thinking it was never his.",
            "Bob sings a siren song that lulls Joe into giving it up.",
            "Bob casts *Confusion* — and Joe hands over the water willingly.",
            "Bob sends Joe a cursed relic — while he’s distracted, Bob grabs it.",
            "Bob swaps the water into a thermos and walks off.",
            "Bob calls dibs louder than Joe ever could.",
            "Bob fakes a prophecy — and says he’s the Chosen Sipper.",
            "Bob wears a cloak of invisibility — poof, water gone.",
            "Bob rewrites the rules to say he’s the rightful holder.",
            "Bob distracts Joe with memes until the water disappears.",
            "Bob turns the lights off — when they return, he’s holding the water.",
            "Bob pirouettes into Joe’s space, twirls out with water.",
            "Bob performs a magic trick — the water vanishes into his hand.",
            "Bob knocks on Joe’s door claiming to be “Water Services.”",
            "Bob drops a “limited edition” bottle — Joe trades his.",
            "Bob gives Joe a riddle — while thinking, Joe loses the water.",
            "Bob just smiles and Joe... hands it over willingly.",
            "Bob wins Fancy Water in a staring contest.",
            "Bob says “trust fall” and runs with the water.",
            "Bob blows bubbles, Joe is hypnotized, and water is gone.",
            "Bob challenges Joe to rock-paper-scissors — winner takes water.",
            "Bob files a claim: “Water acquired illegally.” It’s his now.",
            "Bob spins a wheel — it lands on “steal water.”",
            "Bob says “Look! A distraction!” — and the water’s gone.",
            "Bob offers a sock, freeing Joe like a house-elf — and snags the water.",
            "Bob snaps his fingers, and the water appears in his hands.",
            "Bob calls it “community property” and walks away.",
            "Bob rewrites the deed to Joe’s house — and the water.",
            "Bob hosts a fake trivia show — water is the prize.",
            "Bob teaches Joe a TikTok dance — and dances away with the bottle.",
            "Bob uses a grappling hook to pull the water in.",
            "Bob tosses glitter and yells “WATER HEIST!” before disappearing.",
            "Bob plays the Uno Reverse card — now he has the water.",
            "Bob replaces it with a balloon full of sparkle juice.",
            "Bob runs a scam called “The Great Water Exchange.”",
            "Bob shouts “FREE WATER CHECK!” and pretends it’s a routine procedure.",
            "Bob challenges Joe to a pun-off — winner hydrates.",
            "Bob dresses as the water delivery man and “replaces” it.",
            "Bob claims diplomatic immunity and seizes the bottle.",
            "Bob raises a toast — with Joe’s own Fancy Water.",
            "Bob summons a seagull — it flies away with the bottle.",
            "Bob teaches a parrot to say “That’s Bob’s!” — Joe believes it.",
            "Bob builds a LEGO clone and steals the water during the switch.",
            "Bob impersonates Joe’s sibling and claims it as a gift.",
            "Bob folds a paper crane — and it walks off with the water.",
            "Bob puts on a monocle and says, “I believe this is mine.”",
            "Bob fakes a wedding — water is the bouquet he catches.",
            "Bob wears a crown and says “This is royal property now.”",
            "Bob makes a cardboard tank — and rolls over Joe’s defenses.",
            "Bob recites the *Water Bill of Rights* — and takes what’s his.",
            "Bob plays smooth jazz — the water slides into his pocket.",
            "Bob wears sunglasses — and looks cool enough to own it.",
            "Bob makes a friendship bracelet — water comes as a gift.",
            "Bob says “Tag, you’re it!” and takes the water while Joe’s frozen.",
            "Bob airlifts the bottle out with a drone.",
            "Bob adds it to his inventory — and Joe can’t find it anymore.",
            "Bob fakes a map to 'better water' and trades for this one.",
            "Bob files a police report claiming the water was his first.",
            "Bob wins it in a raffle only he entered.",
            "Bob sets up a fake HOTW event and claims the prize.",
            "Bob eats an imaginary spicy pepper and drinks Joe’s water.",
            "Bob rides in on a llama and grabs it with flair.",
            "Bob makes a cardboard decoy and runs with the real one.",
            "Bob builds a Minecraft redstone trap — and claims the water.",
            "Bob says 'hydration tax' and demands payment.",
            "Bob sells Joe a bottle of 'improved' water, swaps the real one.",
            "Bob slaps a 'REPO' sticker on it and takes the water.",
            "Bob legally changes his name to 'Joe' and says it's his.",
        ]

        action = random.choice(ways_to_take_water)

        if old_holder is None:
            old_holder = author.mention
            old_timestamp = datetime.now().timestamp()
            await self.config.guild(guild).timestamp.set(old_timestamp)
            await self.config.guild(guild).HOTWname.set(old_holder)
            await ctx.send(f"{author.mention} is the first to claim The Magic Wellwater!")
            return

        # Calculate how long old_holder held it
        now = datetime.now().timestamp()
        duration = now - old_timestamp

        # Format output message
        action = action.replace("Bob", author.mention).replace("Joe", old_holder).replace("Fancy Water", "The Magic Wellwater")
        await ctx.send(action)
        await ctx.send(f"{old_holder} had the water for {int(duration)} seconds.")

        # Update user_data
        if old_holder not in user_data:
            user_data[old_holder] = {
                "name": old_holder,
                "total_time": 0,
                "current_streak": 0,
                "longest_streak": 0
            }

        # Update previous holder's stats
        user_data[old_holder]["total_time"] += duration
        user_data[old_holder]["current_streak"] += duration
        if user_data[old_holder]["current_streak"] > user_data[old_holder]["longest_streak"]:
            user_data[old_holder]["longest_streak"] = user_data[old_holder]["current_streak"]

        # Reset streaks for everyone else
        for uid in user_data:
            if uid != old_holder:
                user_data[uid]["current_streak"] = 0

        # Save new HOTW state
        await self.config.guild(guild).HOTWname.set(author.mention)
        await self.config.guild(guild).timestamp.set(now)
        await self.config.guild(guild).user_data.set(user_data)
