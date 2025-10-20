import random
import discord
from redbot.core import commands, Config, checks
import asyncio
from collections import Counter
from redbot.core.commands import cooldown, BucketType

from datetime import datetime, timedelta


class Casino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=False)
        self.roulette_history = []  # Store last 100 rolls

        self.total_bets = {
        "coinflip": 0,
        "dice": 0,
        "slots": 0,
        "roulette": 0,
    }
    
        self.total_payouts = {
        "coinflip": 0,
        "dice": 0,
        "slots": 0,
        "roulette": 0,
    }

        default_user = {
        "history": []
    }
    
        self.config.register_user(**default_user)
        
        self.config.register_global(spent_tax=0)
        self.config.register_global(
            monthly_net={},        # {"YYYY-MM": float house_net}
            regional_debt_shadow=0.0
        )


    async def get_balance(self, user: discord.Member):
        return await self.config.user(user).master_balance()

    async def update_balance(self, user: discord.Member, amount: int):
        balance = await self.get_balance(user)
        new_balance = max(0, balance + amount)  # Prevent negative balance
        await self.config.user(user).master_balance.set(new_balance)
        return new_balance



    @commands.command()
    @cooldown(1, 3, BucketType.guild)
    async def coinflip(self, ctx, bet: float, call: str = None):
        """Flip a coin with animated message updates. You can call Heads or Tails, but it does not affect the odds."""
        bet2 = bet
        balance = await self.get_balance(ctx.author)
        if not call:
            call = random.choices(["heads", "tails"], weights=[48, 52])[0]

        if call.lower() == "head":
            call = "heads"
        if call.lower() == "tail":
            call = "tails"

        if not call == "heads" and not call == "tails":
            await ctx.send("Sorry bad call please use ``heads`` or ``tails``")
            return
        
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")

        coin_faces = ["🪙 Heads", "🪙 Tails"]
        message = await ctx.send("Flipping the coin... 🪙")
        
        outcome = random.choices(["win", "lose"], weights=[48, 52])[0]
        if outcome == "win":
            if call == "heads":
                final_flip = "🪙 Heads"
            if call == "tails":
                final_flip = "🪙 Tails"
        else:
            if call == "heads":
                final_flip = "🪙 Tails"
            if call == "tails":
                final_flip = "🪙 Heads"
                    
        if call and call.lower() in ["heads", "tails"]:
            user_call = call.capitalize()
            result_text = f"You called {user_call}. "
        else:
            result_text = ""
        
        if outcome == "win":
            winnings = bet
            result_text += "You win! 🎉"
        else:
            winnings = -bet
            result_text += "You lost! 😢"
            
        await self._record_house_net(bet, max(0, winnings))
        new_balance = await self.update_balance(ctx.author, winnings)
        await message.edit(content=f"{final_flip}\n{result_text} New balance: {new_balance:,.2f} WellCoins.")
        self.total_bets["coinflip"] += bet
        self.total_payouts["coinflip"] += max(0, winnings)
        user = ctx.author
        user_history = await self.config.user(user).history()
        user_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "game": "coinflip",
            "bet": bet,
            "payout": max(0, winnings)
        })
        await self.config.user(user).history.set(user_history)



    @commands.command()
    @cooldown(1, 3, BucketType.guild)
    async def dice(self, ctx, bet: float):
        """Roll dice against the house with animated graphics."""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        dice_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
        message = await ctx.send("🎲 Rolling dice... 🎲")
        
        for _ in range(3):
            temp_player_roll = random.choice(dice_emojis)
            temp_house_roll = random.choice(dice_emojis)
            await message.edit(content=f"Player: {temp_player_roll} | House: {temp_house_roll}\nRolling... 🎲")
            await asyncio.sleep(0.5)
        
        player_roll = random.randint(1, 6)
        house_roll = random.choices([1, 2, 3, 4, 5, 6], weights=[5, 10, 15, 20, 25, 30])[0]
        player_emoji = dice_emojis[player_roll - 1]
        house_emoji = dice_emojis[house_roll - 1]
        
        if player_roll > house_roll:
            winnings = bet * 2
            result_text = "You win! 🎉"
        else:
            winnings = -bet
            result_text = "You lost! 😢"

        await self._record_house_net(bet, max(0, winnings))
        new_balance = await self.update_balance(ctx.author, winnings)
        await message.edit(content=f"Player: {player_emoji} | House: {house_emoji}\n{result_text} New balance: {new_balance:,.2f} WellCoins.")
        self.total_bets["dice"] += bet
        self.total_payouts["dice"] += max(0, winnings)
        user = ctx.author
        user_history = await self.config.user(user).history()
        user_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "game": "dice",
            "bet": bet,
            "payout": max(0, winnings)
        })
        await self.config.user(user).history.set(user_history)


    @commands.command()
    @cooldown(1, 3, BucketType.guild)
    async def slots(self, ctx, bet: float):
        """Play a 3x3 slot machine with emojis and live message updates."""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        emojis = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎", "🌸"]
        weighted_emojis = ["🍒"] * 8 + ["🍋"] * 15 + ["🍊"] * 18 + ["🍉"] * 20 + ["⭐"] * 22 + ["💎"] * 22 + ["🌸"] * 3 + ["🍍"] * 10
        
        message = await ctx.send("🎰 Rolling the slots... 🎰")
        
        # Generate the initial 3x3 grid
        grid = [[random.choice(weighted_emojis) for _ in range(3)] for _ in range(3)]
        
        # Simulate rolling effect by editing the message
        for _ in range(3):
            temp_grid = [[random.choice(emojis) for _ in range(3)] for _ in range(3)]
            display = "\n".join([" | ".join(row) for row in temp_grid])
            await message.edit(content=f"{display}\n🎰 Rolling... 🎰")
            await asyncio.sleep(0.3)
        
        display = "\n".join([" | ".join(row) for row in grid])
        payout = 0
        flat_grid = [emoji for row in grid for emoji in row]
        result_text = "You lost! 😢"
        
        if flat_grid.count("🍒") >= 2:
            payout = bet * 1.5
            result_text = "Two or more cherries! 🍒 You win 1.5x your bet!"
            
        elif any(row.count(row[0]) == 3 for row in grid) or any(col.count(col[0]) == 3 for col in zip(*grid)):
            payout = max(payout, bet * 4)
            result_text = "Three of a kind in a row or column! 🎉 You win 4x your bet!"
        
        elif flat_grid.count("🌸") == 3:
            payout = bet * 20
            result_text = "JACKPOT! 🌸🌸🌸 You hit the cherry blossoms jackpot!"
        
        if payout == 0:
            payout = -bet  # House edge ensured

        await self._record_house_net(bet, max(0, payout))
        new_balance = await self.update_balance(ctx.author, payout)
        await message.edit(content=f"{display}\n{result_text} New balance: {new_balance:,.2f} WellCoins.")
       
        self.total_bets["slots"] += bet
        self.total_payouts["slots"] += max(0, payout)
        
        user = ctx.author
        user_history = await self.config.user(user).history()
        user_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "game": "slots",
            "bet": bet,
            "payout": max(0, payout)
        })
        await self.config.user(user).history.set(user_history)


    @commands.command()
    @cooldown(1, 3, BucketType.guild)
    async def roulette(self, ctx, bet: float, call: str):
        """Play roulette. Bet on a number (0-36), red, black, even, or odd."""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        valid_calls = {
            "black": "x2",
            "red": "x2",
            "green": "x35",
            "odd": "x2",
            "even": "x2",
            "high": "x3",
            "mid": "x3",
            "low": "x3"
        }
        
        if call.lower() not in valid_calls:
            embed = discord.Embed(
                title="🎲 Invalid Bet Type",
                description="That bet type isn't recognized. Here's a list of valid roulette calls and their payouts:",
                color=discord.Color.red()
            )
            
            for bet, payout in valid_calls.items():
                embed.add_field(name=bet.capitalize(), value=f"Payout: {payout}", inline=True)
        
            embed.set_footer(text="Please choose a valid call to play roulette.")
            return await ctx.send(embed=embed)
        
        # Roulette wheel setup
        number = random.randint(0, 36)
        red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        black_numbers = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}
        color = "red" if number in red_numbers else "black" if number in black_numbers else "green"
        color2 = "🟥 Red" if number in red_numbers else "⬛ Black" if number in black_numbers else "🟩 Green"
        even_or_odd = "even" if number % 2 == 0 and number != 0 else "odd" if number != 0 else "neither"
        if number == -1:
            even_or_odd = "neither"
        
        # Store result in history
        self.roulette_history.append(number)
        if len(self.roulette_history) > 200:
            self.roulette_history.pop(0)
        
        # Simulate rolling effect
        message = await ctx.send("Roulette wheel spinning... 🎡")
        for _ in range(3):
            temp_number = random.randint(0, 36)
            temp_color = "🟥 Red" if temp_number in red_numbers else "⬛ Black" if temp_number in black_numbers else "🟩 Green"
            await message.edit(content=f"🎡 {temp_color} {temp_number}\nSpinning...")
            await asyncio.sleep(0.5)
        
        # Determine winnings
        payout = 0
        if call.isdigit() and 0 <= int(call) <= 36:
            if int(call) == number:
                payout = bet * 17.5

        elif call.lower() in ["red", "black"] and call.lower() == color:
            payout = bet
        elif call.lower() in ["even", "odd"] and call.lower() == even_or_odd:
            payout = bet

        elif call.lower() in ["green"] and call.lower() == color:
            payout = bet * 17.5

        elif call in ["low"] and 1 <= number <= 12:
            payout = bet * 1.5

        elif call in ["mid"] and 13 <= number <= 24:
            payout = bet * 1.5

        elif call in ["high"] and 25 <= number <= 36:
            payout = bet * 1.5

        
        result_text = f"Roulette landed on {color2} {number}."
        if payout > 0:
            result_text += " You win! 🎉"
        else:
            payout = -bet
            result_text += " You lost! 😢"

        await self._record_house_net(bet, max(0, payout))
        new_balance = await self.update_balance(ctx.author, payout)
        await message.edit(content=f"🎡 {color2} {number}\n{result_text} New balance: {new_balance:,.2f} WellCoins.")
        
        self.total_bets["roulette"] += bet
        self.total_payouts["roulette"] += max(0, payout)

        user = ctx.author
        user_history = await self.config.user(user).history()
        user_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "game": "roulette",
            "bet": bet,
            "payout": max(0, payout)
        })
        await self.config.user(user).history.set(user_history)


    @commands.command()
    async def roulette_history(self, ctx):
        """Display statistics of the last 20 roulette rolls."""
        if not self.roulette_history:
            return await ctx.send("No rolls recorded yet.")

        
        red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        black_numbers = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}
        
        count_numbers = Counter(self.roulette_history)
        total_reds = sum(1 for num in self.roulette_history if num in red_numbers)
        total_blacks = sum(1 for num in self.roulette_history if num in black_numbers)
        total_evens = sum(1 for num in self.roulette_history if num % 2 == 0 and num != 0)
        total_odds = sum(1 for num in self.roulette_history if num % 2 == 1)
        
        embed = discord.Embed(title="Roulette Roll History", color=discord.Color.gold())
        embed.add_field(name="Most Common Numbers", value="\n".join(f"{num}: {count}" for num, count in count_numbers.most_common(5)), inline=False)
        embed.add_field(name="Total Reds 🟥", value=str(total_reds), inline=True)
        embed.add_field(name="Total Blacks ⬛", value=str(total_blacks), inline=True)
        embed.add_field(name="Total Evens", value=str(total_evens), inline=True)
        embed.add_field(name="Total Odds", value=str(total_odds), inline=True)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def casinostats(self, ctx):
        """Display casino stats: total bets, payouts, expected return, and hot/cold status."""
        
        # Expected ER (i.e., house payout rate, can be adjusted)
        expected_returns = {
            "coinflip": 0.48,  # Expected ER = 48%
            "dice": 0.416,     # Expected ER = 41.6%
            "slots": 0.85,     # Estimated ER = 85%
            "roulette": 0.473  # Expected ER = 47.3%
        }
    
        embed = discord.Embed(title="🎰 Casino Stats Report", color=discord.Color.purple())
        total_net = 0
    
        for game in self.total_bets:
            total_bet = self.total_bets[game]
            total_payout = self.total_payouts[game]
    
            if total_bet == 0:
                actual_er = 0.0
            else:
                actual_er = total_payout / total_bet  # Real return percentage
            
            expected_er = expected_returns[game]
            net = total_bet - total_payout
            total_net += net
    
            # Status based on comparison
            status = "🔥 Hot" if actual_er + 30 > expected_er else "❄️ Cold"
    
            embed.add_field(
                name=f"{game.capitalize()} {status}",
                value=(
                    f"💰 **Total Bet**: {total_bet:,.2f}\n"
                    f"🏆 **Total Payout**: {total_payout:,.2f}\n"
                    f"📊 **Actual Payout %**: {actual_er:.2%}\n"
                    f"📉 **House Net**: {net:,.2f}"
                ),
                inline=False
            )
    
        embed.set_footer(text=f"🧮 Total House Profit: {total_net:,.2f} WellCoins")
        await ctx.send(embed=embed)
    
    @commands.command()
    async def gamblingreport(self, ctx, timeframe: str = "all"):
        """DM you your gambling report: daily, weekly, monthly, or all."""
        user = ctx.author
        now = datetime.utcnow()
        timeframe = timeframe.lower()
    
        # Load & prune to 30 days
        history = await self.config.user(user).history()
        cutoff_date = now - timedelta(days=30)
        history = [e for e in history if datetime.fromisoformat(e["timestamp"]) >= cutoff_date]
        await self.config.user(user).history.set(history)
    
        # Time window
        if timeframe == "daily":
            time_limit = now - timedelta(days=1)
        elif timeframe == "weekly":
            time_limit = now - timedelta(weeks=1)
        elif timeframe == "monthly":
            time_limit = now - timedelta(days=30)
        else:
            time_limit = None
    
        # Aggregate: bet (all bets), payout (sum of positive credits), lost (sum of losing bets),
        # and net = payout - lost.
        games = ["coinflip", "dice", "slots", "roulette"]
        stats = {g: {"bet": 0.0, "payout": 0.0, "lost": 0.0, "net": 0.0} for g in games}
    
        for entry in history:
            ts = datetime.fromisoformat(entry["timestamp"])
            if time_limit and ts < time_limit:
                continue
    
            game = entry["game"]
            bet = float(entry.get("bet", 0.0))
            payout = float(entry.get("payout", 0.0))  # this is your net-positive credit only
    
            # Always record the wagered amount so "Total Bet" remains intuitive.
            stats[game]["bet"] += bet
    
            if payout > 0:
                # Win: your code credits balance directly by 'payout' (already net positive change)
                stats[game]["payout"] += payout
                stats[game]["net"] += payout
            else:
                # Loss: your code debits balance by 'bet'
                stats[game]["lost"] += bet
                stats[game]["net"] -= bet
    
        # Optional: add the 5 WC regional debt side-effect (unchanged)
        regional_debt = await self.config.spent_tax()
        await self.config.spent_tax.set(regional_debt + 5)
    
        # Build the embed
        title_scope = timeframe.capitalize() if timeframe in {"daily","weekly","monthly"} else "All"
        embed = discord.Embed(title=f"📊 Your Gambling Report ({title_scope})", color=discord.Color.green())
        net_total = 0.0
    
        for game in games:
            g = stats[game]
            net_total += g["net"]
            embed.add_field(
                name=f"{game.capitalize()}",
                value=(
                    f"💰 **Total Bet**: {g['bet']:,.2f}\n"
                    f"🏆 **Total Payouts (wins only)**: {g['payout']:,.2f}\n"
                    f"💥 **Total Lost (losing bets)**: {g['lost']:,.2f}\n"
                    f"📉 **Net Gain/Loss**: {g['net']:,.2f}"
                ),
                inline=False
            )
    
        embed.set_footer(text=f"Total Net: {net_total:,.2f} WellCoins | 5 WC Debt Added to Region")
    
        # DM it
        try:
            await user.send(embed=embed)
            await ctx.send(f"{user.mention} Your report has been DM'd to you.")
        except discord.Forbidden:
            await ctx.send("Unable to DM you your report. Please enable DMs.")
    
    def _month_key(self, dt: datetime = None) -> str:
        dt = dt or datetime.utcnow()
        return dt.strftime("%Y-%m")
    
    def _prev_month_key(self) -> str:
        today = datetime.utcnow().replace(day=1)
        prev = today - timedelta(days=1)
        return prev.strftime("%Y-%m")
    
    async def _record_house_net(self, bet: float, payout_pos_only: float, when: datetime = None):
        """
        Record house net for the month:
        - bet is the wagered amount
        - payout_pos_only is your stored, wins-only positive credit to user (0 on losses)
        House net = bet - payout_pos_only
        """
        mk = self._month_key(when)
        monthly = await self.config.monthly_net()
        house_net = bet - max(0.0, float(payout_pos_only))
        monthly[mk] = monthly.get(mk, 0.0) + house_net
        await self.config.monthly_net.set(monthly)
    
    async def _get_regional_debt(self) -> float:
        """
        Prefer StockMarket cog's debt (if available). Fallback to our shadow.
        """
        sm = self.bot.get_cog("StockMarket")
        if sm and hasattr(sm, "get_regional_debt"):
            try:
                return float(await sm.get_regional_debt())
            except Exception:
                pass
        return float(await self.config.regional_debt_shadow())
    
    async def _set_regional_debt(self, value: float):
        """
        Try to set via StockMarket. If not possible, store in shadow.
        """
        sm = self.bot.get_cog("StockMarket")
        if sm and hasattr(sm, "set_regional_debt"):
            try:
                await sm.set_regional_debt(max(0.0, float(value)))
                return
            except Exception:
                pass
        await self.config.regional_debt_shadow.set(max(0.0, float(value)))
    
    async def _increase_regional_debt(self, amount: float):
        """
        Increase total regional debt by amount.
        """
        if amount <= 0:
            return
        current = await self._get_regional_debt()
        await self._set_regional_debt(current + amount)
    
    async def _decrease_regional_debt(self, amount: float):
        """ 
        Pay down regional debt by amount (clamped to zero).
        """
        if amount <= 0:
            return
        current = await self._get_regional_debt()
        new_val = max(0.0, current - amount)
        await self._set_regional_debt(new_val)

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def casino_monthly_report(self, ctx, month: str = None):
        """
        Close and post the monthly casino report and settle finances.
        Usage:
          [p]casino_monthly_report           -> closes previous month
          [p]casino_monthly_report 2025-09  -> closes that specific month (YYYY-MM)
        """
        # Determine which month to close
        target_month = month or self._prev_month_key()
    
        monthly = await self.config.monthly_net()
        house_net = float(monthly.get(target_month, 0.0))  # positive = profit for casino, negative = loss
        starting_debt = await self._get_regional_debt()
    
        actions = []
        distribution_total = 0.0
        distributed_each = 0.0
        eligible_count = 0
    
        if house_net < 0:
            # Casino lost money => add to regional debt
            loss = -house_net
            await self._increase_regional_debt(loss)
            actions.append(f"📈 Increased regional debt by **{loss:,.2f}** WC.")
        elif house_net > 0:
            # Casino profited: pay down debt first
            profit = house_net
            if starting_debt > 0:
                paydown = min(profit, starting_debt)
                await self._decrease_regional_debt(paydown)
                actions.append(f"💳 Paid down regional debt by **{paydown:,.2f}** WC.")
                profit -= paydown
    
            if profit > 0:
                # No debt left => pay 50% to role 1098673767858843648 evenly
                role = ctx.guild.get_role(1098673767858843648)
                if role:
                    recipients = [m for m in role.members if not m.bot]
                    eligible_count = len(recipients)
                    pool = profit * 0.50
                    distribution_total = pool
                    if eligible_count > 0 and pool > 0:
                        distributed_each = pool / eligible_count
                        # Credit each eligible member
                        for m in recipients:
                            await self.update_balance(m, distributed_each)
                        actions.append(
                            f"🎁 Distributed **{pool:,.2f}** WC (50% of profit) "
                            f"evenly to **{eligible_count}** members ({distributed_each:,.2f} each)."
                        )
                    else:
                        actions.append("ℹ️ No eligible members found for distribution.")
                else:
                    actions.append("⚠️ Role 1098673767858843648 not found; skipped profit distribution.")
        else:
            actions.append("ℹ️ House net was exactly 0. No changes applied.")
    
        # Snapshot debts after action
        ending_debt = await self._get_regional_debt()
    
        # Zero-out that month so it won't be applied twice
        monthly[target_month] = 0.0
        await self.config.monthly_net.set(monthly)
    
        # Build and post the report
        embed = discord.Embed(
            title=f"🏦 Casino Monthly Report — {target_month}",
            color=discord.Color.gold()
        )
        embed.add_field(name="House Net (month)", value=f"{house_net:,.2f} WC", inline=True)
        embed.add_field(name="Debt (start → end)", value=f"{starting_debt:,.2f} → {ending_debt:,.2f} WC", inline=True)
    
        if distribution_total > 0:
            embed.add_field(
                name="Profit Distribution",
                value=f"Total: {distribution_total:,.2f} WC\nRecipients: {eligible_count}\nEach: {distributed_each:,.2f} WC",
                inline=False
            )
    
        embed.add_field(
            name="Applied Actions",
            value="\n".join(actions) if actions else "None",
            inline=False
        )
    
        embed.set_footer(text="Monthly ledger has been settled and reset for this period.")
        await ctx.send(embed=embed)
    

    

    
