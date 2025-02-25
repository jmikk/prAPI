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
        
        winner, rounds, exhausted_votes = self.run_ranked_choice_voting(candidates, votes, votes)

        # Mark election as closed
        del elections[election_name]
        await self.config.guild(ctx.guild).elections.set(elections)

        result_msg = f"**📊 Election '{election_name.capitalize()}' Results:**\n\n"

        for round_num, (tally, eliminated, exhausted) in enumerate(rounds, 1):
            total_votes = sum(tally.values()) + exhausted  # Active votes + exhausted ballots
            round_result = "\n".join(f"🗳 **{c.capitalize()}**: {t} votes" for c, t in tally.items())
            result_msg += (
                f"**🔄 Round {round_num}** (Total Votes: {total_votes}):\n"
                f"{round_result}\n"
                f"❌ **Eliminated:** {eliminated.capitalize()}\n"
                f"💨 **Exhausted Ballots:** {exhausted}\n\n"
            )

        # Ensure the final round is displayed if it wasn't added before
        if rounds:
            final_tally = rounds[-1][0]  # Last round's tally
            total_final_votes = sum(final_tally.values()) + exhausted_votes
            final_round_display = "\n".join(f"🗳 **{c.capitalize()}**: {t} votes" for c, t in final_tally.items())

            result_msg += (
                f"**🏁 Final Round (Total Votes: {total_final_votes}):**\n"
                f"{final_round_display}\n\n"
            )

        result_msg += f"🏆 **Winner: {winner.capitalize()}!** 🎉"
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
    
    def run_ranked_choice_voting(self, candidates, votes, original_votes, admin_id=None):
        """Perform ranked choice voting (instant-runoff) with tie-breaking rules using original votes."""
        rounds = []
        exhausted_votes = 0
    
        while True:
            # Count only first-choice votes in the current round
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
    
            # If only one candidate remains, they are the winner
            if len(vote_counts) == 1:
                rounds.append((dict(vote_counts), "None (Final Round)", exhausted_votes))
                return list(vote_counts.keys())[0], rounds, exhausted_votes  # Last candidate wins

            # Check if a candidate has a majority (>50% of total valid votes)
            for candidate, count in vote_counts.items():
                if count > total_valid_votes / 2:
                    rounds.append((dict(vote_counts), "None (Majority Reached)", exhausted_votes))
                    return candidate, rounds, exhausted_votes  # Winner found!
    
            # Find the lowest-ranked candidate in the current round
            if not vote_counts:
                return "No valid votes", rounds, exhausted_votes  # No one left

            lowest_candidates = self.find_lowest_ranked_candidate(vote_counts, votes, original_votes)

            if len(lowest_candidates) == 1:
                eliminated_candidate = lowest_candidates[0]
            else:
                if admin_id:
                    # Admin must cast the deciding vote
                    eliminated_candidate = lowest_candidates[0]  # Placeholder for admin decision
                else:
                    eliminated_candidate = lowest_candidates[0]  # Default to first in tie list
            
            rounds.append((dict(vote_counts), eliminated_candidate, exhausted_votes))

            # Remove the eliminated candidate from all votes
            for vote in votes:
                if vote and vote[0] == eliminated_candidate:
                    vote.pop(0)

            candidates.remove(eliminated_candidate)  # Remove from valid candidates list

    def find_lowest_ranked_candidate(self, vote_counts, votes, original_votes):
        """Finds the lowest-ranked candidate using original votes for tie-breaking."""
        min_votes = min(vote_counts.values())
        tied_candidates = [c for c in vote_counts if vote_counts[c] == min_votes]

        if len(tied_candidates) == 1:
            return tied_candidates  # Only one candidate is the lowest

        # If tied, use the original first-choice votes
        original_first_counts = defaultdict(int)
        for vote in original_votes:
            if vote and vote[0] in tied_candidates:
                original_first_counts[vote[0]] += 1

        min_first_votes = min(original_first_counts.values(), default=0)
        tied_candidates = [c for c in original_first_counts if original_first_counts[c] == min_first_votes]

        if len(tied_candidates) == 1:
            return tied_candidates  # Found a unique lowest-ranked candidate

        # Tie-break by checking second-choice votes from original ballots
        for rank in range(1, max(len(v) for v in original_votes if v) + 1):
            ranked_counts = defaultdict(int)
            for vote in original_votes:
                if len(vote) > rank and vote[rank] in tied_candidates:
                    ranked_counts[vote[rank]] += 1
            
            if ranked_counts:
                min_secondary_votes = min(ranked_counts.values())
                tied_candidates = [c for c in ranked_counts if ranked_counts[c] == min_secondary_votes]

                if len(tied_candidates) == 1:
                    return tied_candidates  # Found a unique lowest-ranked candidate

        return tied_candidates  # Still tied (admin must decide)




