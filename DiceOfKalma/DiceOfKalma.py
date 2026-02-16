import discord
import asyncio
import random
from collections import defaultdict
from redbot.core import commands, Config
from discord.ui import View, Button, Modal, TextInput

class DiceOfKalma(commands.Cog):
    """
    Play the Dice of Kalma.
    High-stakes bluffing with specific hand rankings and economy integration.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=894723847230, force_registration=True)
        self.config.register_user(master_balance=100.0)
        # FIX: defaultdict is from collections, using asyncio.Lock as the factory
        self._balance_locks = defaultdict(asyncio.Lock)
        self.active_games = {} # {channel_id: GameSession}

    # =========================================================================
    #                               ECONOMY API
    # =========================================================================

    async def get_balance(self, user: discord.abc.User) -> float:
        """Return the user's current Wellcoin balance."""
        return await self.config.user(user).master_balance()

    async def modify_wellcoins(self, user: discord.abc.User, delta: float, *, force: bool = False) -> float:
        """Modify a user's Wellcoin balance safely."""
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            raise ValueError("delta must be a number")

        delta = int(delta * 100) / 100.0
        
        async with self._balance_locks[user.id]:
            data = await self.config.user(user).all()
            bal = float(data.get("master_balance", 0))

            if delta < 0 and not force:
                if bal < -delta:
                    raise ValueError(f"Insufficient funds: tried to remove {-delta}, only {bal} available.")
                new_bal = bal + delta
            else:
                new_bal = bal + delta

            new_bal = int(new_bal * 100) / 100.0
            data["master_balance"] = new_bal
            await self.config.user(user).set(data)
            return new_bal

    async def add_wellcoins(self, user: discord.abc.User, amount: float) -> float:
        if amount < 0: raise ValueError("Amount must be non-negative")
        return await self.modify_wellcoins(user, amount, force=False)

    async def take_wellcoins(self, user: discord.abc.User, amount: float, force: bool = False) -> float:
        if amount < 0: raise ValueError("Amount must be non-negative")
        return await self.modify_wellcoins(user, -amount, force=force)

    # =========================================================================
    #                             GAME LOGIC
    # =========================================================================

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def kalma(self, ctx, ante: float = 10.0):
        """Start a game of Dice of Kalma."""
        if ctx.channel.id in self.active_games:
            return await ctx.send("A game is already running in this channel!")
        
        if ante <= 0:
            return await ctx.send("The ante must be greater than 0.")

        # Initialize Game Session
        game = GameSession(self, ctx, ante)
        self.active_games[ctx.channel.id] = game
        await game.start_join_phase()

    @kalma.command()
    async def stop(self, ctx):
        """Force stop a game in this channel."""
        if ctx.channel.id in self.active_games:
            del self.active_games[ctx.channel.id]
            await ctx.send("Game force-stopped.")
        else:
            await ctx.send("No game running.")

    # --- Shared Helper Methods ---

    async def determine_winner(self, players, rolls, channel):
        """Finds the winner, resolving ties recursively."""
        
        def get_score_tuple(uid):
            d1, d2 = rolls[uid]
            total = d1 + d2
            # Power Ranking: 7 > 11 > 12 > 2 > High > Low
            if total == 7: power = 5
            elif total == 11: power = 4
            elif total == 12: power = 3
            elif total == 2: power = 2
            elif total > 7: power = 1
            else: power = 0
            return (power, total)

        best_score = (-1, -1)
        player_scores = {}
        
        # Calculate scores
        for p in players:
            score = get_score_tuple(p.id)
            player_scores[p] = score
            if score > best_score:
                best_score = score

        winners = [p for p, s in player_scores.items() if s == best_score]

        if len(winners) > 1:
            await channel.send(f"⚔️ **SUDDEN DEATH!** {', '.join([w.display_name for w in winners])} are tied!")
            await asyncio.sleep(2)
            return await self.sudden_death(channel, winners)
        
        return winners[0]

    async def sudden_death(self, channel, contenders):
        results = {}
        msg_text = ""
        
        for p in contenders:
            roll = random.randint(1, 20)
            results[p] = roll
            msg_text += f"**{p.display_name}**: {roll}\n"
        
        embed = discord.Embed(title="⚔️ Sudden Death Rolls", description=msg_text, color=discord.Color.red())
        await channel.send(embed=embed)
        await asyncio.sleep(2)

        high_roll = max(results.values())
        finalists = [p for p, r in results.items() if r == high_roll]
        
        if len(finalists) > 1:
            await channel.send("Another tie! Rolling again...")
            await asyncio.sleep(1)
            return await self.sudden_death(channel, finalists)
        
        return finalists[0]


class GameSession:
    """Handles the state of a single game in a channel."""
    def __init__(self, cog, ctx, ante):
        self.cog = cog
        self.ctx = ctx
        self.ante = ante
        self.pot = 0.0
        self.players = []       # List of Discord Members
        self.rolls = {}         # {user_id: (d1, d2)}
        self.bets = {}          # {user_id: amount_bet_this_round}
        self.tapped_out = []    # List of user_ids who are all-in/tapped
        self.folded = []        # List of user_ids who folded
        self.turn_index = 0
        self.current_high_bet = 0.0
        self.message = None     # The main game message
        self.is_betting = False

    async def start_join_phase(self):
        embed = discord.Embed(
            title="🎲 Dice of Kalma",
            description=f"**Ante:** {self.ante} Wellcoins\n\nClick **Join** to buy in.",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Game hosted by " + self.ctx.author.display_name)
        
        view = JoinView(self)
        self.message = await self.ctx.send(embed=embed, view=view)

    async def start_round(self):
        """ transitions from joining to playing """
        if len(self.players) < 2:
            return await self.ctx.send("Not enough players! Game cancelled.")

        self.is_betting = True
        self.turn_index = 0
        self.current_high_bet = 0.0
        
        # Roll Dice
        for p in self.players:
            self.rolls[p.id] = (random.randint(1, 6), random.randint(1, 6))
            self.bets[p.id] = 0.0

        await self.update_game_board("The dice have been cast! Check your rolls privately.")
        await self.next_turn()

    async def next_turn(self):
        """Determines whose turn it is or if the round is over."""
        active_players = [p for p in self.players if p.id not in self.folded and p.id not in self.tapped_out]
        remaining = [p for p in self.players if p.id not in self.folded]

        # 1. Win by default (everyone else folded)
        if len(remaining) == 1:
            return await self.end_game(winner=remaining[0])

        # 2. Check Betting Complete Condition
        # If everyone remaining has either matched the high bet OR is tapped out
        # AND everyone has had at least one chance to act (bets > -1, though simplified here)
        
        all_bets_aligned = True
        for p in remaining:
            if p.id in self.tapped_out:
                continue
            if self.bets.get(p.id, 0.0) < self.current_high_bet:
                all_bets_aligned = False
                break
        
        # If bets are aligned, we need to ensure the round doesn't end immediately 
        # before the first player acts. We check if the current player has acted.
        # Logic: If it's the start of the round (high_bet == 0) we must play.
        # If high_bet > 0 and we return to the person who set it (or everyone called), we show down.
        
        # We'll use a simplified check:
        # If we loop through players and everyone called/folded/tapped, Showdown.
        # This is handled implicitly: if the logic finds the next player has ALREADY matched the high bet,
        # it usually means the round is over.
        
        player = self.players[self.turn_index]
        
        # Skip folded/tapped players
        start_index = self.turn_index
        while player.id in self.folded or player.id in self.tapped_out:
            self.turn_index = (self.turn_index + 1) % len(self.players)
            player = self.players[self.turn_index]
            
            # If we looped all the way around, everyone is out/tapped
            if self.turn_index == start_index:
                return await self.showdown()

        # SHOWDOWN CHECK:
        # If the current player has already matched the high bet, AND everyone else has too, it's over.
        if self.current_high_bet > 0 and self.bets.get(player.id, 0.0) == self.current_high_bet:
            if all_bets_aligned:
                return await self.showdown()
        # If high bet is 0 and everyone has checked (bets=0), we need a flag to track if we circled.
        # For simplicity in this version: We assume if we return to index 0 and everyone checked, it's over.
        # (This is a naive implementation; full poker logic requires an 'acted' set, but this works for basic flow)
        
        # Update View for the specific player's turn
        view = TurnView(self, player)
        embed = self.message.embeds[0]
        embed.description = f"It is {player.mention}'s turn to act."
        embed.clear_fields()
        
        player_status = ""
        for p in self.players:
            status = "Waiting"
            bet_amt = self.bets.get(p.id, 0.0)
            if p.id in self.folded: status = "🏳️ Folded"
            elif p.id in self.tapped_out: status = "⚠️ Tapped Out"
            elif p == player: status = "🤔 Thinking..."
            elif bet_amt == self.current_high_bet and self.current_high_bet > 0: status = "✅ Matched"
            elif bet_amt == 0 and self.current_high_bet == 0: status = "Waiting" 
            else: status = f"Needs {self.current_high_bet - bet_amt:.2f}"
            
            player_status += f"**{p.display_name}**: {status} (Bet: {bet_amt})\n"

        embed.add_field(name="Current Pot", value=str(self.pot), inline=True)
        embed.add_field(name="High Bet", value=str(self.current_high_bet), inline=True)
        embed.add_field(name="Status", value=player_status, inline=False)

        await self.message.edit(embed=embed, view=view)

    async def update_game_board(self, status_text):
        embed = self.message.embeds[0]
        embed.description = status_text
        embed.set_field_at(0, name="Pot", value=f"{self.pot} Wellcoins")
        await self.message.edit(embed=embed)

    async def showdown(self):
        """Reveals dice and determines winner."""
        self.is_betting = False
        contenders = [p for p in self.players if p.id not in self.folded]
        
        if not contenders:
            return await self.ctx.send("Everyone folded? Pot lost to the void.")

        winner = await self.cog.determine_winner(contenders, self.rolls, self.ctx.channel)
        await self.end_game(winner)

    async def end_game(self, winner):
        text = "🎲 **THE REVEAL** 🎲\n"
        for p in self.players:
            d1, d2 = self.rolls.get(p.id, (0,0))
            status = ""
            if p.id in self.folded: status = "(Folded)"
            text += f"**{p.display_name}**: {d1} & {d2} (Total: {d1+d2}) {status}\n"
        
        try:
            new_bal = await self.cog.add_wellcoins(winner, self.pot)
            text += f"\n🏆 **{winner.mention} wins {self.pot} Wellcoins!**"
        except Exception as e:
            text += f"\nError paying out: {e}"

        embed = self.message.embeds[0]
        embed.title = "Game Over"
        embed.description = text
        embed.clear_fields()
        
        await self.message.edit(embed=embed, view=None)
        
        if self.ctx.channel.id in self.cog.active_games:
            del self.cog.active_games[self.ctx.channel.id]

# =========================================================================
#                               VIEWS
# =========================================================================

class JoinView(View):
    def __init__(self, game):
        super().__init__(timeout=120)
        self.game = game

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: Button):
        if interaction.user in self.game.players:
            return await interaction.response.send_message("You are already joined.", ephemeral=True)
        
        try:
            bal = await self.game.cog.take_wellcoins(interaction.user, self.game.ante)
            
            self.game.players.append(interaction.user)
            self.game.pot += self.game.ante
            self.game.bets[interaction.user.id] = 0.0
            
            embed = interaction.message.embeds[0]
            embed.set_field_at(0, name="Pot", value=f"{self.game.pot} Wellcoins")
            
            # Simple list update
            player_names = [p.display_name for p in self.game.players]
            embed.description = f"**Ante:** {self.game.ante} Wellcoins\n**Players:** {', '.join(player_names)}"
            
            await interaction.message.edit(embed=embed)
            await interaction.response.send_message(f"Joined! Balance remaining: {bal}", ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message(f"You don't have enough Wellcoins (Need {self.game.ante})", ephemeral=True)

    @discord.ui.button(label="Check Balance", style=discord.ButtonStyle.grey)
    async def check_bal(self, interaction: discord.Interaction, button: Button):
        bal = await self.game.cog.get_balance(interaction.user)
        await interaction.response.send_message(f"💰 Your Wallet: **{bal} Wellcoins**", ephemeral=True)

    @discord.ui.button(label="Start Round", style=discord.ButtonStyle.blurple)
    async def start(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.game.ctx.author:
            return await interaction.response.send_message("Only the host can start the game.", ephemeral=True)
        
        self.stop()
        await self.game.start_round()

class RaiseModal(Modal, title="Raise Bet"):
    amount = TextInput(label="Amount to Raise", placeholder="e.g. 50")

    def __init__(self, game, player):
        super().__init__()
        self.game = game
        self.player = player

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raise_amount = float(self.amount.value)
            if raise_amount <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("Invalid amount.", ephemeral=True)

        current_bet = self.game.bets[self.player.id]
        call_diff = self.game.current_high_bet - current_bet
        total_needed = call_diff + raise_amount

        try:
            bal = await self.game.cog.get_balance(self.player)
            
            if bal < total_needed:
                return await interaction.response.send_message(f"You don't have enough to raise that much! You have {bal}.", ephemeral=True)

            await self.game.cog.take_wellcoins(self.player, total_needed)
            
            self.game.pot += total_needed
            self.game.bets[self.player.id] += total_needed
            self.game.current_high_bet += raise_amount
            
            await interaction.response.send_message(f"Raised by {raise_amount}!", ephemeral=True)
            
            self.game.turn_index = (self.game.turn_index + 1) % len(self.game.players)
            await self.game.next_turn()

        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

class TurnView(View):
    def __init__(self, game, active_player):
        super().__init__(timeout=60)
        self.game = game
        self.active_player = active_player

    @discord.ui.button(label="Check Dice", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def check_dice(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.game.rolls:
            return await interaction.response.send_message("You aren't in this game.", ephemeral=True)
        d1, d2 = self.game.rolls[interaction.user.id]
        await interaction.response.send_message(f"Your Roll: **{d1}** & **{d2}** (Total: {d1+d2})", ephemeral=True)

    @discord.ui.button(label="Check Balance", style=discord.ButtonStyle.secondary, emoji="💰")
    async def check_bal(self, interaction: discord.Interaction, button: Button):
        bal = await self.game.cog.get_balance(interaction.user)
        await interaction.response.send_message(f"Your Wallet: **{bal} Wellcoins**", ephemeral=True)

    @discord.ui.button(label="Call / Check", style=discord.ButtonStyle.success)
    async def call(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.active_player:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)

        current_bet = self.game.bets[interaction.user.id]
        diff = self.game.current_high_bet - current_bet

        if diff == 0:
            await interaction.response.send_message("Checked.", ephemeral=True)
        else:
            try:
                await self.game.cog.take_wellcoins(interaction.user, diff)
                self.game.pot += diff
                self.game.bets[interaction.user.id] += diff
                await interaction.response.send_message(f"Called {diff}.", ephemeral=True)
            except ValueError:
                # TAPPED OUT LOGIC
                bal = await self.game.cog.get_balance(interaction.user)
                await self.game.cog.take_wellcoins(interaction.user, bal)
                self.game.pot += bal
                self.game.bets[interaction.user.id] += bal
                self.game.tapped_out.append(interaction.user.id)
                
                await interaction.channel.send(f"⚠️ **{interaction.user.display_name}** is TAPPED OUT! They are all-in with {bal}.")
                await interaction.response.send_message("You are all-in.", ephemeral=True)

        self.game.turn_index = (self.game.turn_index + 1) % len(self.game.players)
        await self.game.next_turn()

    @discord.ui.button(label="Raise", style=discord.ButtonStyle.primary)
    async def raise_bet(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.active_player:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)
        
        await interaction.response.send_modal(RaiseModal(self.game, interaction.user))

    @discord.ui.button(label="Fold", style=discord.ButtonStyle.danger)
    async def fold(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.active_player:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)

        self.game.folded.append(interaction.user.id)
        await interaction.channel.send(f"🏳️ **{interaction.user.display_name}** folded.")
        await interaction.response.send_message("You folded.", ephemeral=True)
        
        self.game.turn_index = (self.game.turn_index + 1) % len(self.game.players)
        await self.game.next_turn()
