from redbot.core import commands, Config
import discord
from collections import defaultdict, Counter

class RCV(commands.Cog):
    """A cog for running Ranked Choice Voting elections."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1983746508234, force_registration=True)
        self.config.register_guild(elections={})

    @commands.guild_only()
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

    @commands.guild_only()
    @commands.command()
    async def add_test_ballot(self, ctx, election_name: str, *choices: str):
        """Add a test ballot manually to an election."""
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
            return await ctx.send("Invalid ballot! Your choices must be from the listed candidates.")

        if len(choices) != len(set(choices)):
            return await ctx.send("Duplicate candidates detected! Ensure each choice is unique.")

        # Use a special ID for test ballots to avoid conflicts with real voters
        test_voter_id = f"test_{len(election['votes']) + 1}"
        election["votes"][test_voter_id] = choices  # Adds test ballot

        await self.config.guild(ctx.guild).elections.set(elections)
        await ctx.send(f"✅ Test ballot added for '{election_name.capitalize()}': {', '.join(choices)}")

    @commands.guild_only()
    @commands.command()
    async def tally(self, ctx, election_name: str):
        """Tally votes and determine the winner using Ranked Choice Voting."""
        elections = await self.config.guild(ctx.guild).elections()
        election_name = election_name.lower()

        if election_name not in elections:
            return await ctx.send("No such election exists.")
        
        election = elections[election_name]
        if election["status"] != "open":
            return await ctx.send("This election has already been tallied.")

        votes = election["votes"]
        if not votes:
            return await ctx.send("No votes have been cast in this election.")

        election["status"] = "closed"
        await self.config.guild(ctx.guild).elections.set(elections)

        candidates = set(election["candidates"])
        rounds = []
        first_round_votes = Counter(v[0] for v in votes.values() if v)

                # Remove candidates with 0 votes in the first round
        candidates -= {cand for cand in candidates if first_round_votes[cand] == 0}
        
        while True:
            round_results = Counter()
            
            for ballot in votes.values():
                for choice in ballot:
                    if choice in candidates:
                        round_results[choice] += 1
                        break  # Only count the highest-ranked valid candidate
            
            total_votes = sum(round_results.values())
            rounds.append(dict(round_results))
            
            # Announce current round results
            result_text = "\n".join(f"{cand.capitalize()}: {count}" for cand, count in round_results.items())
            await ctx.send(f"**Round {len(rounds)} Results:**\n{result_text}")
            
            # Check if a candidate has a majority
            for candidate, count in round_results.items():
                if count > total_votes / 2:
                    return await ctx.send(f"🏆 **{candidate.capitalize()} wins with a majority!**")
            
            # Find the lowest vote-getters
            min_votes = min(round_results.values())
            lowest_candidates = {cand for cand, count in round_results.items() if count == min_votes}
            
            # Eliminate lowest-ranked candidates
            candidates -= lowest_candidates
            
            # If no candidates remain, backtrack to first-round results
            if not candidates:
                remaining_candidates = sorted(first_round_votes.items(), key=lambda x: x[1], reverse=True)
                top_votes = remaining_candidates[0][1]
                top_candidates = [cand for cand, count in remaining_candidates if count == top_votes]
                
                if len(top_candidates) == 1:
                    return await ctx.send(f"🏆 **{top_candidates[0].capitalize()} wins based on first-round votes!**")
                
                for round_number, round_result in enumerate(rounds[1:], start=2):
                    for candidate in top_candidates:
                        if candidate in round_result:
                            top_votes = round_result[candidate]
                            break
                    
                    if top_votes:
                        top_candidates = [cand for cand in top_candidates if round_result.get(cand, 0) == top_votes]
                    
                    if len(top_candidates) == 1:
                        return await ctx.send(f"🏆 **{top_candidates[0].capitalize()} wins based on tiebreaker!**")
                
                return await ctx.send("⚠️ **Election remains tied after all rounds. No winner determined.**")




