    @commands.guild_only()
    @commands.command()
    async def tally(self, ctx, election_name: str):
        """Tally votes and determine the winner using Ranked Choice Voting."""
        elections = await self.config.guild(ctx.guild).elections()
        election_name = election_name.lower()

        if election_name not in elections:
            return await ctx.send("No such election exists.")
        
        election = elections.get(election_name, {})
        if election.get("status") != "open":
            return await ctx.send("This election has already been tallied.")

        votes = election.get("votes", {})
        if not votes:
            return await ctx.send("No votes have been cast in this election.")

        election["status"] = "closed"
        await self.config.guild(ctx.guild).elections.set(elections)

        candidates = set(election.get("candidates", []))
        first_round_votes = Counter(v[0] for v in votes.values() if v)
        
        # Remove candidates with 0 votes in the first round, but ensure 'ney' is not eliminated
        candidates -= {cand for cand in candidates if first_round_votes[cand] == 0 and cand != "ney"}

        rounds = []
        last_round = None
        
        while True:
            round_results = Counter()
            
            for ballot in votes.values():
                for choice in ballot:
                    if choice in candidates:
                        round_results[choice] += 1
                        break  # Only count the highest-ranked valid candidate
            
            total_votes = sum(round_results.values())
            rounds.append(dict(round_results))
            
            # Check if the last round is identical to the previous round, if so, trigger tiebreaker
            if last_round and last_round == round_results:
                break
            last_round = round_results.copy()
            
            # Announce current round results
            result_text = "\n".join(f"{cand.capitalize()}: {count}" for cand, count in round_results.items())
            await ctx.send(f"**Round {len(rounds)} Results:**\n{result_text}")
            
            # Check if a candidate has a majority
            for candidate, count in round_results.items():
                if count > total_votes / 2:
                    elections.pop(election_name, None)  # Remove election safely
                    await self.config.guild(ctx.guild).elections.set(elections)
                    return await ctx.send(f"🏆 **{candidate.capitalize()} wins with a majority!**")
            
            # Find the lowest vote-getters, but ensure 'ney' is not eliminated
            min_votes = min(round_results.values())
            lowest_candidates = {cand for cand, count in round_results.items() if count == min_votes and cand != "ney"}
            
            # Eliminate lowest-ranked candidates
            candidates -= lowest_candidates
            
            # If no candidates remain, backtrack to first-round results
            if not candidates:
                break
        
        # Initiate tiebreaker
        remaining_candidates = sorted(first_round_votes.items(), key=lambda x: x[1], reverse=True)
        top_votes = remaining_candidates[0][1]
        top_candidates = [cand for cand, count in remaining_candidates if count == top_votes]
        
        if len(top_candidates) == 1:
            elections.pop(election_name, None)  # Remove election safely
            await self.config.guild(ctx.guild).elections.set(elections)
            return await ctx.send(f"🏆 **{top_candidates[0].capitalize()} wins based on first-round votes!**")
        
        for round_number, round_result in enumerate(rounds[1:], start=2):
            for candidate in top_candidates:
                if candidate in round_result:
                    top_votes = round_result[candidate]
                    break
            
            if top_votes:
                top_candidates = [cand for cand in top_candidates if round_result.get(cand, 0) == top_votes]
            
            if len(top_candidates) == 1:
                elections.pop(election_name, None)  # Remove election safely
                await self.config.guild(ctx.guild).elections.set(elections)
                return await ctx.send(f"🏆 **{top_candidates[0].capitalize()} wins based on tiebreaker!**")
        
        elections.pop(election_name, None)  # Remove election safely
        await self.config.guild(ctx.guild).elections.set(elections)
        return await ctx.send("⚠️ **Election remains tied after all rounds. No winner determined.**")
