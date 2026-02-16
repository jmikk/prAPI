import discord
import asyncio
import random
import time
from collections import defaultdict
from redbot.core import commands
from discord.ui import View, Button, Modal, TextInput

class DiceOfKalma(commands.Cog):
    """
    Play the Dice of Kalma.
    High-stakes bluffing with specific hand rankings.
    Currency is handled by the NexusExchange cog.
    """

    def __init__(self, bot):
        self.bot = bot
        self.active_games = {} # {channel_id: GameSession}

    # =========================================================================
    #                        EXTERNAL ECONOMY WRAPPERS
    # =========================================================================

    @property
    def nexus(self):
        return self.bot.get_cog("NexusExchange")

    def _check_nexus(self):
        if not self.nexus:
            raise RuntimeError("NexusExchange cog is not loaded. Please load it to play.")

    async def get_balance(self, user: discord.abc.User) -> float:
        """Return the user's current Wellcoin balance via NexusExchange."""
        self._check_nexus()
        return await self.nexus.get_balance(user)

    async def add_wellcoins(self, user: discord.abc.User, amount: float) -> float:
        """Add coins via NexusExchange."""
        self._check_nexus()
        return await self.nexus.add_wellcoins(user, amount)

    async def take_wellcoins(self, user: discord.abc.User, amount: float, force: bool = False) -> float:
        """Remove coins via NexusExchange. Raises ValueError if insufficient."""
        self._check_nexus()
        return await self.nexus.take_wellcoins(user, amount, force=force)

    # =========================================================================
    #                                  GAME LOGIC
    # =========================================================================

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def kalma(self, ctx, ante: float = 10.0):
        """Start a game of Dice of Kalma."""
        if ctx.channel.id in self.active_games:
            return await ctx.send("A game is already running in this channel!")
        
        if ante <= 0:
            return await ctx.send("The ante must be greater than 0.")

        # Check if Nexus is loaded before starting
        if not self.nexus:
            return await ctx.send("Error: The `NexusExchange` cog is required for currency but is not loaded.")

        # Initialize Game Session
        game = GameSession(self, ctx, ante)
        self.active_games[ctx.channel.id] = game
        await game.start_join_phase()

    @kalma.command()
    async def stop(self, ctx):
        """Force stop a game in this channel."""
        if ctx.channel.id in self.active_games:
            # Try to stop any running view to prevent timeouts firing after stop
            game = self.active_games[ctx.channel.id]
            if game.current_view:
                game.current_view.stop()
            
            # Refund ante if game hasn't started yet
            if not game.started:
                for p in game.players:
                    try:
                        await self.add_wellcoins(p, game.ante)
                    except:
                        pass
                await ctx.send("Game cancelled and antes refunded.")
            else:
                await ctx.send("Game force-stopped. Pot remains in the void (no refund logic for mid-game stop).")

            del self.active_games[ctx.channel.id]
            
            # Disable view
            if game.message:
                try:
                    await game.message.edit(view=None)
                except:
                    pass
        else:
            await ctx.send("No game running.")

    @kalma.command()
    @commands.is_owner()
    async def stopall(self, ctx):
        """
        Force stops ALL active Dice of Kalma games across all channels.
        Refunding logic:
        - If in Lobby: Refunds Ante.
        - If In-Game: Splits the pot evenly among active (non-folded) players.
        """
        if not self.active_games:
            return await ctx.send("No active games found.")

        count = 0
        for channel_id, game in list(self.active_games.items()):
            if game.current_view:
                game.current_view.stop()
            
            # Refund Logic
            if not game.started:
                # Refund Ante
                for p in game.players:
                    try:
                        await self.add_wellcoins(p, game.ante)
                    except:
                        pass
            else:
                # Split pot among remaining players
                remaining = [p for p in game.players if p.id not in game.folded]
                if remaining and game.pot > 0:
                    share = game.pot / len(remaining)
                    for p in remaining:
                        try:
                            await self.add_wellcoins(p, share)
                        except:
                            pass
            
            # Notify channel
            try:
                # We need to fetch the channel or use the stored message
                if game.message:
                    await game.message.channel.send("⚠️ **Admin has force-stopped all active games.** Funds have been returned/split.")
                    await game.message.edit(view=None)
            except:
                pass

            count += 1
        
        self.active_games.clear()
        await ctx.send(f"✅ Force stopped {count} games.")

    # --- Shared Helper Methods ---

    def get_hand_details(self, total: int) -> tuple:
        """Returns (Hand Name, Rank Description) based on total."""
        if total == 7: return ("The Kalma", "Rank 1 - Unbeatable")
        elif total == 11: return ("Merchant's Boon", "Rank 2 - Very Strong")
        elif total == 12: return ("Midnight Twelve", "Rank 3 - Strong")
        elif total == 2: return ("Snake Eyes", "Rank 4 - Tricky")
        elif total > 7: return ("High Standard", "Rank 5 - Average")
        else: return ("Low Dregs", "Rank 6 - Weak")

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
        self.checks = set()     # List of user_ids who have checked (for 0 bet rounds)
        self.turn_index = 0
        self.current_high_bet = 0.0
        self.message = None     # The main game message
        self.is_betting = False
        self.started = False    # Prevents race conditions with timeouts
        self.current_view = None # Tracks active view to stop it properly

    async def start_join_phase(self):
        embed = discord.Embed(
            title="🎲 Dice of Kalma",
            description=f"**Ante:** {self.ante} Wellcoins\n\nClick **Join** to buy in.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Pot", value="0.0 Wellcoins", inline=True)
        embed.set_footer(text="Game hosted by " + self.ctx.author.display_name)
        
        view = JoinView(self)
        self.current_view = view
        self.message = await self.ctx.send(embed=embed, view=view)

    async def start_round(self):
        """ transitions from joining to playing """
        self.started = True
        if self.current_view:
            self.current_view.stop()
            
        if len(self.players) < 2:
            # REFUND & CANCEL LOGIC
            for p in self.players:
                try:
                    await self.cog.add_wellcoins(p, self.ante)
                except:
                    pass
            
            await self.ctx.send("⚠️ **Not enough players to start!** Game cancelled and antes refunded.")
            
            if self.ctx.channel.id in self.cog.active_games:
                del self.cog.active_games[self.ctx.channel.id]
            
            # Disable buttons
            try:
                await self.message.edit(view=None)
            except:
                pass
            return

        self.is_betting = True
        self.turn_index = 0
        self.current_high_bet = 0.0
        self.checks = set()
        
        # Roll Dice
        for p in self.players:
            self.rolls[p.id] = (random.randint(1, 6), random.randint(1, 6))
            self.bets[p.id] = 0.0

        await self.update_game_board("The dice have been cast! Check your rolls privately.")
        await self.next_turn()

    async def next_turn(self):
        """Determines whose turn it is or if the round is over."""
        # Clean up previous view to prevent timeout listeners from lingering
        if self.current_view:
            self.current_view.stop()

        # 1. Check Win by default (everyone else folded)
        remaining = [p for p in self.players if p.id not in self.folded]
        if len(remaining) == 1:
            return await self.end_game(winner=remaining[0])

        # 2. Check Betting Complete Condition
        all_bets_aligned = True
        for p in remaining:
            if p.id in self.tapped_out:
                continue
            if self.bets.get(p.id, 0.0) < self.current_high_bet:
                all_bets_aligned = False
                break
        
        player = self.players[self.turn_index]
        
        # Skip folded/tapped players
        start_index = self.turn_index
        while player.id in self.folded or player.id in self.tapped_out:
            self.turn_index = (self.turn_index + 1) % len(self.players)
            player = self.players[self.turn_index]
            
            # If we looped all the way around, everyone is out/tapped -> Showdown
            if self.turn_index == start_index:
                return await self.showdown()

        # SHOWDOWN CHECK:
        # Determine if we should end the game (Showdown)
        
        # Case A: Pot has been raised (>0), current player matches, and everyone else is aligned.
        pot_matched_end = (self.current_high_bet > 0 and self.bets.get(player.id, 0.0) == self.current_high_bet)
        
        # Case B: Pot is 0 (Check-Check situation), and everyone remaining has checked.
        # We check if self.checks (set of IDs) contains all IDs in remaining players.
        active_ids = {p.id for p in remaining}
        zero_bet_end = (self.current_high_bet == 0 and self.checks.issuperset(active_ids))

        if (pot_matched_end or zero_bet_end):
            if all_bets_aligned:
                return await self.showdown()

        # Update View for the specific player's turn
        view = TurnView(self, player)
        self.current_view = view
        
        # Calculate expiry for relative timestamp (60s timeout matching TurnView)
        expiry = int(time.time() + 60)
        
        # Reuse existing embed style or create new one
        if self.message and self.message.embeds:
            embed = self.message.embeds[0]
        else:
            embed = discord.Embed(title="🎲 Dice of Kalma", color=discord.Color.gold())

        embed.description = f"It is {player.mention}'s turn to act.\nAuto-fold <t:{expiry}:R>."
        embed.clear_fields()
        
        player_status = ""
        for p in self.players:
            status = "Waiting"
            bet_amt = self.bets.get(p.id, 0.0)
            if p.id in self.folded: status = "🏳️ Folded"
            elif p.id in self.tapped_out: status = "⚠️ Tapped Out"
            elif p == player: status = "🤔 Thinking..."
            elif bet_amt == self.current_high_bet and self.current_high_bet > 0: status = "✅ Matched"
            elif bet_amt == 0 and self.current_high_bet == 0: 
                # Differentiate between "Waiting to act" and "Checked"
                if p.id in self.checks: status = "Checked"
                else: status = "Waiting"
            else: status = f"Needs {self.current_high_bet - bet_amt:.2f}"
            
            player_status += f"**{p.display_name}**: {status} (Bet: {bet_amt})\n"

        embed.add_field(name="Current Pot", value=str(self.pot), inline=True)
        embed.add_field(name="High Bet", value=str(self.current_high_bet), inline=True)
        embed.add_field(name="Status", value=player_status, inline=False)

        # RESEND LOGIC: Delete old message, send new one to be at the bottom
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        self.message = await self.ctx.send(embed=embed, view=view)
        
        # PING logic: Ping player, delete after 10s
        try:
            await self.ctx.send(f"🔔 {player.mention}, it's your turn!", delete_after=10)
        except:
            pass # Ignore permission errors

    async def update_game_board(self, status_text):
        embed = self.message.embeds[0]
        embed.description = status_text
        if len(embed.fields) > 0:
            embed.set_field_at(0, name="Pot", value=f"{self.pot} Wellcoins")
        else:
            embed.add_field(name="Pot", value=f"{self.pot} Wellcoins")
            
        await self.message.edit(embed=embed)

    async def showdown(self):
        """Reveals dice and determines winner."""
        self.is_betting = False
        if self.current_view:
            self.current_view.stop()
            
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
            
            # Show the hand name in the reveal too
            if p.id not in self.folded:
                h_name, h_rank = self.cog.get_hand_details(d1 + d2)
                text += f"**{p.display_name}**: {d1} & {d2} - *{h_name}* (Total: {d1+d2})\n"
            else:
                text += f"**{p.display_name}**: (Folded)\n"
        
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
#                                VIEWS
# =========================================================================

class JoinView(View):
    def __init__(self, game):
        super().__init__(timeout=120)
        self.game = game

    async def on_timeout(self):
        # If game already started manually, do nothing
        if self.game.started:
            return

        if len(self.game.players) >= 2:
            await self.game.ctx.send("⏳ **Join time expired!** Auto-starting the game...")
            await self.game.start_round()
        else:
            # Not enough players, refund everyone
            for p in self.game.players:
                try:
                    await self.game.cog.add_wellcoins(p, self.game.ante)
                except:
                    pass # Ignore errors during cleanup
            
            await self.game.ctx.send("⏳ **Join time expired!** Not enough players. Game cancelled and antes refunded.")
            if self.game.ctx.channel.id in self.game.cog.active_games:
                del self.game.cog.active_games[self.game.ctx.channel.id]
            
            # Disable buttons
            try:
                await self.game.message.edit(view=None)
            except:
                pass

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        if interaction.user in self.game.players:
            return await interaction.followup.send("You are already joined.", ephemeral=True)
        
        try:
            bal = await self.game.cog.take_wellcoins(interaction.user, self.game.ante)
            
            self.game.players.append(interaction.user)
            self.game.pot += self.game.ante
            self.game.bets[interaction.user.id] = 0.0
            
            embed = interaction.message.embeds[0]
            player_names = [p.display_name for p in self.game.players]
            
            embed.description = f"**Ante:** {self.game.ante} Wellcoins\n\n**Players Joined:**\n{', '.join(player_names)}\n\nClick **Join** to buy in."
            embed.set_field_at(0, name="Pot", value=f"{self.game.pot} Wellcoins")
            
            await interaction.message.edit(embed=embed)
            await interaction.followup.send(f"🎲 **{interaction.user.display_name}** has joined the table!", ephemeral=False)
            
        except ValueError:
            await interaction.followup.send(f"You don't have enough Wellcoins to join! (Need {self.game.ante})", ephemeral=True)
        except RuntimeError:
             await interaction.followup.send("The Economy system (NexusExchange) is offline.", ephemeral=True)

    @discord.ui.button(label="How to Play", style=discord.ButtonStyle.secondary, row=1)
    async def how_to_play(self, interaction: discord.Interaction, button: Button):
        rules = (
            "**Dice of Kalma Rules**\n"
            "1. Everyone rolls 2 dice (hidden).\n"
            "2. Betting happens in rounds. You can Call, Raise, or Fold.\n"
            "3. **Hand Rankings (Best to Worst):**\n"
            "   - **7** : *The Kalma* (Unbeatable)\n"
            "   - **11**: *Merchant's Boon*\n"
            "   - **12**: *Midnight Twelve*\n"
            "   - **2** : *Snake Eyes*\n"
            "   - **8, 9, 10**: *High Standard*\n"
            "   - **3, 4, 5, 6**: *Low Dregs*\n"
            "4. Winner takes the pot!"
        )
        await interaction.response.send_message(rules, ephemeral=True)

    @discord.ui.button(label="Check Balance", style=discord.ButtonStyle.grey, row=1)
    async def check_bal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        try:
            bal = await self.game.cog.get_balance(interaction.user)
            await interaction.followup.send(f"💰 Your Wallet: **{bal} Wellcoins**", ephemeral=True)
        except RuntimeError:
            await interaction.followup.send("The Economy system (NexusExchange) is offline.", ephemeral=True)

    @discord.ui.button(label="Start Round", style=discord.ButtonStyle.blurple, row=0)
    async def start(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.game.ctx.author:
            return await interaction.response.send_message("Only the host can start the game.", ephemeral=True)
        
        await interaction.response.defer()
        # Manually triggering start needs to handle stopping this view, which start_round does.
        await self.game.start_round()

class RaiseModal(Modal, title="Raise Bet"):
    amount = TextInput(label="Amount to Raise", placeholder="e.g. 50")

    def __init__(self, game, player):
        super().__init__()
        self.game = game
        self.player = player

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            raise_amount = float(self.amount.value)
            if raise_amount <= 0: raise ValueError
        except ValueError:
            return await interaction.followup.send("Invalid amount.", ephemeral=True)

        current_bet = self.game.bets[self.player.id]
        call_diff = self.game.current_high_bet - current_bet
        total_needed = call_diff + raise_amount

        try:
            bal = await self.game.cog.get_balance(self.player)
            
            if bal < total_needed:
                return await interaction.followup.send(f"You don't have enough to raise that much! You have {bal}.", ephemeral=True)

            await self.game.cog.take_wellcoins(self.player, total_needed)
            
            self.game.pot += total_needed
            self.game.bets[self.player.id] += total_needed
            self.game.current_high_bet += raise_amount
            # Clear checks because a raise resets the "everyone checked" condition
            self.game.checks.clear()
            
            await interaction.followup.send(f"Raised by {raise_amount}!", ephemeral=True)
            
            self.game.turn_index = (self.game.turn_index + 1) % len(self.game.players)
            await self.game.next_turn()

        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

class TurnView(View):
    def __init__(self, game, active_player):
        super().__init__(timeout=60)
        self.game = game
        self.active_player = active_player

    async def on_timeout(self):
        # Auto-fold logic if timeout is reached
        if self.game.ctx.channel.id not in self.game.cog.active_games:
            return # Game already deleted

        if self.active_player.id not in self.game.folded and self.active_player.id not in self.game.tapped_out:
            self.game.folded.append(self.active_player.id)
            await self.game.ctx.send(f"⏰ **{self.active_player.display_name}** ran out of time and folded automatically.")
            
            self.game.turn_index = (self.game.turn_index + 1) % len(self.game.players)
            await self.game.next_turn()

    @discord.ui.button(label="Check Dice", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def check_dice(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.game.rolls:
            return await interaction.response.send_message("You aren't in this game.", ephemeral=True)
        d1, d2 = self.game.rolls[interaction.user.id]
        total = d1 + d2
        name, rank = self.game.cog.get_hand_details(total)
        await interaction.response.send_message(f"Your Roll: **{d1}** & **{d2}**\nTotal: **{total}**\nHand: **{name}** ({rank})", ephemeral=True)

    @discord.ui.button(label="Check Balance", style=discord.ButtonStyle.secondary, emoji="💰")
    async def check_bal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        try:
            bal = await self.game.cog.get_balance(interaction.user)
            await interaction.followup.send(f"Your Wallet: **{bal} Wellcoins**", ephemeral=True)
        except RuntimeError:
             await interaction.followup.send("Economy system offline.", ephemeral=True)

    @discord.ui.button(label="Call / Check", style=discord.ButtonStyle.success)
    async def call(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.active_player:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)

        await interaction.response.defer(ephemeral=True) 

        current_bet = self.game.bets[interaction.user.id]
        diff = self.game.current_high_bet - current_bet

        if diff == 0:
            # Player is checking
            self.game.checks.add(interaction.user.id)
            await interaction.followup.send("Checked.", ephemeral=True)
        else:
            try:
                await self.game.cog.take_wellcoins(interaction.user, diff)
                self.game.pot += diff
                self.game.bets[interaction.user.id] += diff
                await interaction.followup.send(f"Called {diff}.", ephemeral=True)
            except ValueError:
                # TAPPED OUT LOGIC
                try:
                    bal = await self.game.cog.get_balance(interaction.user)
                    await self.game.cog.take_wellcoins(interaction.user, bal)
                    self.game.pot += bal
                    self.game.bets[interaction.user.id] += bal
                    self.game.tapped_out.append(interaction.user.id)
                    
                    await interaction.channel.send(f"⚠️ **{interaction.user.display_name}** is TAPPED OUT! They are all-in with {bal}.")
                    await interaction.followup.send("You are all-in.", ephemeral=True)
                except Exception as e:
                     await interaction.followup.send(f"Error processing tap out: {e}", ephemeral=True)

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
        
        await interaction.response.defer(ephemeral=True)
        self.game.folded.append(interaction.user.id)
        await interaction.channel.send(f"🏳️ **{interaction.user.display_name}** folded.")
        await interaction.followup.send("You folded.", ephemeral=True)
        
        self.game.turn_index = (self.game.turn_index + 1) % len(self.game.players)
        await self.game.next_turn()
