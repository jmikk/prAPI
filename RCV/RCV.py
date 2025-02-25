from redbot.core import commands, Config
import discord
from collections import defaultdict

class RCV(commands.Cog):
    """A cog for running Ranked Choice Voting elections."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1983746508234, force_registration=True)
        self.config.register_guild(elections={})

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def start_election(self, ctx, election_name: str, *candidates: str):
        """Start a ranked choice voting election."""
        if not candidates:
            return await ctx.send("You must provide at least two candidates.")

        elections = await self.config.guild(ctx.guild).elections()
        election_name = election_name.lower()

        if election_name in elections:
            return await ctx.send(f"An election named '{election_name}' is already running.")

        candidates = [c.lower() for c in candidates]

        elections[election_name] = {
            "candidates": candidates,
            "votes": {},
            "status": "open"
        }
        await self.config.guild(ctx.guild).elections.set(elections)

        candidate_list = "\n".join(f"- {c.capitalize()}" for c in candidates)
        await ctx.send(f"Election '{election_name.capitalize()}' started! Candidates:\n{candidate_list}\nUse `!vote {election_name} <ranked choices>` to vote.")

    @commands.guild_only()
    @commands.command()
    async def vote(self, ctx, election_name: str, *choices: str):
        """Vote in a ranked choice election by listing candidates in order of preference."""
        elections = await self.config.guild(ctx.guild).elections()
        election_name = election_name.lower()

        if election_name not in elections:
            return await ctx.send("No such election exists.")

        election = elections[election_name]
        if election["status"] != "open":
            return await ctx.send("This election has ended.")

        candidates = set(election["candidates"])
        choices = [c.lower() for c in choices]

        if not set(choices).issubset(candidates):
            return await ctx.send("Invalid vote! Your choices must be from the listed candidates.")

        if len(choices) != len(set(choices)):
            return await ctx.send("Duplicate candidates detected! Ensure each choice is unique.")

        election["votes"][str(ctx.author.id)] = choices  # Overwrites previous vote
        await self.config.guild(ctx.guild).elections.set(elections)
        await ctx.send(f"Your vote for '{election_name.capitalize()}' has been recorded!")

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def tally(self, ctx, election_name: str):
        """Tally the votes for a ranked choice election and determine the winner."""
        elections = await self.config.guild(ctx.guild).elections()
        election_name = election_name.lower()

        if election_name not in elections:
            return await ctx.send("No such election exists.")

        election = elections[election_name]
        if election["status"] != "open":
            return await ctx.send("This election has already been tallied.")

        votes = list(election["votes"].values())
        candidates = election["candidates"]
        
        winner, rounds = self.run_ranked_choice_voting(candidates, votes)

        election["status"] = "closed"
        await self.config.guild(ctx.guild).elections.set(elections)

        result_msg = f"**Election '{election_name.capitalize()}' Results:**\n\n"
        for round_num, (tally, eliminated) in enumerate(rounds, 1):
            round_result = "\n".join(f"{c.capitalize()}: {t}" for c, t in tally.items())
            result_msg += f"**Round {round_num}**:\n{round_result}\nEliminated: {eliminated.capitalize()}\n\n"
        
        result_msg += f"🏆 **Winner: {winner.capitalize()}!**"
        await ctx.send(result_msg)

    @commands.guild_only()
    @commands.admin()
    @commands.command()
    async def cancel_election(self, ctx, election_name: str):
        """Cancel an ongoing election."""
        elections = await self.config.guild(ctx.guild).elections()
        election_name = election_name.lower()

        if election_name not in elections:
            return await ctx.send("No such election exists.")

        del elections[election_name]
        await self.config.guild(ctx.guild).elections.set(elections)
        await ctx.send(f"Election '{election_name.capitalize()}' has been canceled.")

    def run_ranked_choice_voting(self, candidates, votes):
        """Perform ranked choice voting (instant-runoff) and return the winner with rounds breakdown."""
        rounds = []
        candidate_votes = defaultdict(int)

        for vote in votes:
            if vote:
                candidate_votes[vote[0]] += 1  

        while True:
            total_votes = sum(candidate_votes.values())
            if not total_votes:
                return "No valid votes", rounds

            threshold = total_votes / 2
            sorted_candidates = sorted(candidate_votes.items(), key=lambda x: x[1])

            if sorted_candidates[-1][1] > threshold:
                return sorted_candidates[-1][0], rounds

            eliminated = sorted_candidates[0][0]
            rounds.append((dict(candidate_votes), eliminated))

            del candidate_votes[eliminated]

            for vote in votes:
                if vote and vote[0] == eliminated:
                    vote.pop(0)
                    if vote:
                        candidate_votes[vote[0]] += 1

        return "Error", rounds
