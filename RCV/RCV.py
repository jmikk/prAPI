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

        # ✅ Display the original votes first
        formatted_votes = "\n".join(f"Voter {idx + 1}: {', '.join(vote) if vote else 'No Vote'}"
                                    for idx, vote in enumerate(votes))

        await ctx.send(f"📜 **Original Votes:**\n```{formatted_votes}```")

        # ✅ Fix: Await the async function
        winner, rounds, exhausted_votes = await self.run_ranked_choice_voting(
            candidates, votes, votes, admin_id=ctx.author.id, ctx=ctx
        )

        # Mark election as closed
        del elections[election_name]
        await self.config.guild(ctx.guild).elections.set(elections)

        # ✅ Display the rounds and results separately
        result_msg = f"**📊 Election '{election_name.capitalize()}' Results:**\n\n"

        for round_num, (tally, eliminated, exhausted) in enumerate(rounds, 1):
            total_votes = sum(tally.values()) + exhausted  # Active votes + exhausted ballots
            round_result = "\n".join(f"🗳 **{c.capitalize()}**: {t} votes" for c, t in tally.items())
            result_msg += (
                f"**🔄 Round {round_num}** (Total Votes: {total_votes}):\n"
                f"{round_result}\n"
                f"❌ **Eliminated:** {', '.join(eliminated).capitalize() if isinstance(eliminated, list) else eliminated.capitalize()}\n"
                f"💨 **Exhausted Ballots:** {exhausted}\n\n"
            )

        result_msg += f"🏆 **Winner: {winner.capitalize()}!** 🎉"
        await ctx.send(result_msg)


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
    
    async def run_ranked_choice_voting(self, candidates, votes, original_votes, admin_id=None, ctx=None):
        """Perform ranked choice voting (instant-runoff) with specific handling for 'nay' and tie scenarios."""
        rounds = []
        exhausted_votes = 0
    
        while True:
            # Count first-choice votes in the current round
            vote_counts = defaultdict(int)
            total_valid_votes = 0
            current_exhausted = 0
    
            for vote in votes:
                while vote:
                    first_choice = vote[0]
                    if first_choice in candidates:
                        vote_counts[first_choice] += 1
                        total_valid_votes += 1
                        break
                    else:
                        vote.pop(0)  # Remove invalid/removed candidates
    
                if not vote:
                    current_exhausted += 1  # Ballot has no remaining valid choices
    
            exhausted_votes += current_exhausted
    
            # Check for a majority winner
            for candidate, count in vote_counts.items():
                if count > total_valid_votes / 2:
                    rounds.append((dict(vote_counts), "None (Majority Reached)", exhausted_votes))
                    return candidate, rounds, exhausted_votes  # Winner found!
    
            # Identify the lowest and highest vote counts
            if not vote_counts:
                return "No valid votes", rounds, exhausted_votes  # No candidates left
    
            min_votes = min(vote_counts.values())
            max_votes = max(vote_counts.values())
            lowest_candidates = [c for c in vote_counts if vote_counts[c] == min_votes]
            highest_candidates = [c for c in vote_counts if vote_counts[c] == max_votes]
    
            # Special handling when 'nay' is the lowest-voted candidate
            if "nay" in lowest_candidates:
                if len(lowest_candidates) == 1:
                    # If 'nay' is the sole lowest, check if the next lowest is tied for the most votes
                    next_min_votes = min(v for c, v in vote_counts.items() if c != "nay")
                    next_lowest_candidates = [c for c in vote_counts if vote_counts[c] == next_min_votes]
    
                    if next_min_votes == max_votes:
                        # Next lowest is tied for the most votes; trigger admin tiebreaker
                        if admin_id and ctx:
                            return await self.admin_tiebreaker(ctx, admin_id, original_votes, rounds, exhausted_votes)
                        else:
                            return await self.admin_tiebreaker(ctx, admin_id, original_votes, rounds, exhausted_votes)
                    else:
                        # Eliminate 'nay' and continue
                        candidates.remove("nay")
                        rounds.append((dict(vote_counts), ["nay"], exhausted_votes))
                        continue
                else:
                    # Multiple candidates tied for lowest, including 'nay'
                    lowest_candidates.remove("nay")  # Preserve 'nay' for now
    
            # If all remaining candidates are tied, trigger admin tiebreaker
            if len(lowest_candidates) == len(vote_counts):
                if admin_id and ctx:
                    return await self.admin_tiebreaker(ctx, admin_id, original_votes, rounds, exhausted_votes)
                else:
                    return await self.admin_tiebreaker(ctx, admin_id, original_votes, rounds, exhausted_votes)
    
            # Eliminate all candidates with the lowest votes (excluding 'nay' if preserved)
            for eliminated_candidate in lowest_candidates:
                candidates.remove(eliminated_candidate)
    
            rounds.append((dict(vote_counts), lowest_candidates, exhausted_votes))
    
            # Remove eliminated candidates from votes
            for vote in votes:
                while vote and vote[0] in lowest_candidates:
                    vote.pop(0)
    




    async def admin_tiebreaker(self, ctx, admin_id, original_votes, rounds, exhausted_votes):
        """Break ties by checking original votes round-by-round until a candidate with the lowest votes is found."""
        admin = ctx.guild.get_member(admin_id)
        if not admin:
            return "Admin decision required", rounds, exhausted_votes  # Admin not found

        remaining_candidates = list(rounds[-1][0].keys()) if rounds else []

        # Cycle through the original votes, checking round by round to break the tie
        for round_index in range(len(original_votes[0])):  # Iterate through ballot ranks
            tied_counts = defaultdict(int)

            for vote in original_votes:
                if len(vote) > round_index and vote[round_index] in remaining_candidates:
                    tied_counts[vote[round_index]] += 1

            # Only keep the tied candidates in the count
            tied_counts = {k: v for k, v in tied_counts.items() if k in remaining_candidates}

            if tied_counts:
                min_votes = min(tied_counts.values())
                lowest_candidates = [c for c in tied_counts if tied_counts[c] == min_votes]

                # If a single lowest candidate is found, eliminate them
                if len(lowest_candidates) == 1:
                    return lowest_candidates[0], rounds, exhausted_votes

        # If we exhausted all rounds and still have a tie, admin must decide
        result_msg = "**🏁 Tiebreaker Required: All remaining candidates are still tied!**\n"
        result_msg += "Admin, please choose which candidate to eliminate based on original votes:\n\n"

        # Generate a final tally from original votes for admin review
        final_counts = defaultdict(int)
        for vote in original_votes:
            for choice in vote:
                if choice in remaining_candidates:
                    final_counts[choice] += 1

        for candidate, count in final_counts.items():
            result_msg += f"🗳 **{candidate.capitalize()}**: {count} total votes across all rounds\n"

        # Format the original votes for readability
        formatted_votes = "\n".join(f"Voter {idx + 1}: {', '.join(vote) if vote else 'No Vote'}"
                                    for idx, vote in enumerate(original_votes))

        # Append the formatted votes to the admin message
        result_msg += f"\n\n**📜 Original Votes Across Rounds:**\n```{formatted_votes}```"

        # Send admin a DM to pick the eliminated candidate
        try:
            await admin.send(result_msg)
        except discord.Forbidden:
            return "Admin decision required, but DM failed.", rounds, exhausted_votes

        return "Admin decision pending", rounds, exhausted_votes  # Wait for admin input




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



