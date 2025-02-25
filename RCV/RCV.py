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
        await ctx.send(f"Election '{election_name.capitalize()}' started! Candidates:\n{candidate_list}\nUse `$vote {election_name} <ranked choices>` to vote.")

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
        
        winner, rounds, exhausted_votes = self.run_ranked_choice_voting(candidates, votes)

        # Mark election as closed
        del elections[election_name]
        await self.config.guild(ctx.guild).elections.set(elections)

        result_msg = f"**Election '{election_name.capitalize()}' Results:**\n\n"
        for round_num, (tally, eliminated, exhausted) in enumerate(rounds, 1):
            round_result = "\n".join(f"{c.capitalize()}: {t}" for c, t in tally.items())
            result_msg += f"**Round {round_num}**:\n{round_result}\nEliminated: {eliminated.capitalize()}\nExhausted Ballots: {exhausted}\n\n"
        
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
        """Perform ranked choice voting (instant-runoff) with direct list modification."""
        rounds = []
        exhausted_votes = 0
    
        while True:
            # Count only first-choice votes
            vote_counts = defaultdict(int)
            total_valid_votes = 0
            current_exhausted = 0  # Count exhausted ballots in this round only
    
            for vote in votes:
                while vote:  # Ensure we are only counting valid votes
                    first_choice = vote[0]
                    if first_choice in candidates:  # Make sure it's still a valid candidate
                        vote_counts[first_choice] += 1
                        total_valid_votes += 1
                        break  # Move to the next voter's ballot
                    else:
                        vote.pop(0)  # Remove invalid/removed candidates
    
                if not vote:  # Ballot has no remaining valid choices
                    current_exhausted += 1  # Count this ballot as exhausted
    
            exhausted_votes += current_exhausted  # Keep track of total exhausted votes
    
            # Check if a candidate has a majority (>50% of total valid votes)
            for candidate, count in vote_counts.items():
                if count > total_valid_votes / 2:
                    return candidate, rounds, exhausted_votes  # Winner found!
    
            # If no winner, find the lowest-ranked candidate and remove them
            if not vote_counts:
                return "No valid votes", rounds, exhausted_votes  # No one left
    
            lowest_candidate = min(vote_counts, key=vote_counts.get)  # Candidate with fewest votes
            rounds.append((dict(vote_counts), lowest_candidate, exhausted_votes))
    
            # Remove the eliminated candidate from all votes
            for vote in votes:
                if vote and vote[0] == lowest_candidate:
                    vote.pop(0)
    
            candidates.remove(lowest_candidate)  # Remove from valid candidates list
