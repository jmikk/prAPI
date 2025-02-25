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
        await ctx.send(votes)

        # ✅ Fix: Await the async function
        winner, rounds, exhausted_votes = await self.run_ranked_choice_voting(
            candidates, votes, votes, admin_id=ctx.author.id, ctx=ctx
        )

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
                f"❌ **Eliminated:** {', '.join(eliminated).capitalize() if isinstance(eliminated, list) else eliminated.capitalize()}\n"
                f"💨 **Exhausted Ballots:** {exhausted}\n\n"
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
    
    async def run_ranked_choice_voting(self, candidates, votes, original_votes, admin_id=None, ctx=None):
        """Perform ranked choice voting (instant-runoff) with bulk tie elimination."""
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

            # Find the lowest-ranked candidates in the current round
            if not vote_counts:
                return "No valid votes", rounds, exhausted_votes  # No one left

            min_votes = min(vote_counts.values())
            lowest_candidates = [c for c in vote_counts if vote_counts[c] == min_votes]

            # **Fix: If all remaining candidates are tied, admin must decide**
            if len(lowest_candidates) == len(vote_counts):
                if admin_id and ctx:
                    return await self.admin_tiebreaker(ctx, admin_id, original_votes, rounds, exhausted_votes)
                else:
                    return "Admin decision required", rounds, exhausted_votes  # Should not happen without admin

            # Otherwise, eliminate all tied lowest candidates
            for eliminated_candidate in lowest_candidates:
                candidates.remove(eliminated_candidate)

            rounds.append((dict(vote_counts), lowest_candidates, exhausted_votes))  # Ensure rounds are recorded

            # Remove eliminated candidates from votes
            for vote in votes:
                while vote and vote[0] in lowest_candidates:
                    vote.pop(0)  # Remove all tied lowest candidates


    async def admin_tiebreaker(self, ctx, admin_id, original_votes, rounds, exhausted_votes):
        """Prompts the admin to break a full tie by reviewing original votes."""
        admin = ctx.guild.get_member(admin_id)
        if not admin:
            return "Admin decision required", rounds, exhausted_votes  # Admin not found

        if not rounds:
            return "No rounds available to reference for tiebreaking.", rounds, exhausted_votes

        # Generate a tally of original votes for admin review
        original_first_counts = defaultdict(int)
        remaining_candidates = list(rounds[-1][0].keys()) if rounds else []

        for vote in original_votes:
            if vote and vote[0] in remaining_candidates:  # Only include remaining candidates
                original_first_counts[vote[0]] += 1

        # If no candidates are found, return an error message
        if not original_first_counts:
            return "No valid candidates remaining for tiebreaking.", rounds, exhausted_votes

        result_msg = "**🏁 Tiebreaker Required: All remaining candidates are tied!**\n"
        result_msg += "Admin, please choose which candidate to eliminate based on original votes:\n\n"
        for candidate, count in original_first_counts.items():
            result_msg += f"🗳 **{candidate.capitalize()}**: {count} original first-choice votes\n"

        # Send admin a DM to pick the eliminated candidate
        try:
            dm_message = await admin.send(result_msg)
        except discord.Forbidden:
            return "Admin decision required, but DM failed.", rounds, exhausted_votes

        return "Admin decision pending", rounds, exhausted_votes  # Wait for admin input


