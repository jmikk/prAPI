import random
import discord
from redbot.core import commands, Config, checks
import asyncio
from collections import Counter
from redbot.core.commands import cooldown, BucketType




class Casino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=True)
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
        
        new_balance = await self.update_balance(ctx.author, winnings)
        await message.edit(content=f"{final_flip}\n{result_text} New balance: {new_balance:.2f} WellCoins.")
        self.total_bets["coinflip"] += bet
        self.total_payouts["coinflip"] += max(0, winnings)

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
        
        new_balance = await self.update_balance(ctx.author, winnings)
        await message.edit(content=f"Player: {player_emoji} | House: {house_emoji}\n{result_text} New balance: {new_balance:.2f} WellCoins.")
        self.total_bets["dice"] += bet
        self.total_payouts["dice"] += max(0, winnings)


    @commands.command()
    @cooldown(1, 3, BucketType.guild)
    async def slots(self, ctx, bet: float):
        """Play a 3x3 slot machine with emojis and live message updates."""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        emojis = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎", "🌸"]
        weighted_emojis = ["🍒"] * 8 + ["🍋"] * 15 + ["🍊"] * 18 + ["🍉"] * 20 + ["⭐"] * 22 + ["💎"] * 22 + ["🌸"] * 3
        
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
        if any(row.count(row[0]) == 3 for row in grid) or any(col.count(col[0]) == 3 for col in zip(*grid)):
            payout = max(payout, bet * 4)
            result_text = "Three of a kind in a row or column! 🎉 You win 4x your bet!"
        if flat_grid.count("🌸") == 3:
            payout = bet * 20
            result_text = "JACKPOT! 🌸🌸🌸 You hit the cherry blossoms jackpot!"
        
        if payout == 0:
            payout = -bet  # House edge ensured
        
        new_balance = await self.update_balance(ctx.author, payout)
        await message.edit(content=f"{display}\n{result_text} New balance: {new_balance:.2f} WellCoins.")
       
        self.total_bets["slots"] += bet
        self.total_payouts["slots"] += max(0, payout)


    @commands.command()
    @cooldown(1, 3, BucketType.guild)
    @commands.admin_or_permissions(administrator=True)
    async def roulette(self, ctx, bet: float, call: str):
        """Play roulette. Bet on a number (0-36), red, black, even, or odd."""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        # Roulette wheel setup
        number = random.randint(0, 36)
        red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        black_numbers = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}
        color = "red" if number in red_numbers else "black" if number in black_numbers else "green"
        color2 = "🟥 Red" if number in red_numbers else "⬛ Black" if number in black_numbers else "🟩 Green"
        even_or_odd = "even" if number % 2 == 0 and number != 0 else "odd" if number != 0 else "neither"
        
        # Store result in history
        self.roulette_history.append(number)
        if len(self.roulette_history) > 20:
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
                payout = bet * 35
        elif call.lower() in ["red", "black"] and call.lower() == color:
            payout = bet * 2
        elif call.lower() in ["even", "odd"] and call.lower() == even_or_odd:
            payout = bet * 2
        
        result_text = f"Roulette landed on {color2} {number}."
        if payout > 0:
            result_text += " You win! 🎉"
        else:
            payout = -bet
            result_text += " You lost! 😢"
        
        new_balance = await self.update_balance(ctx.author, payout)
        await message.edit(content=f"🎡 {color2} {number}\n{result_text} New balance: {new_balance:.2f} WellCoins.")
        
        self.total_bets["roulette"] += bet
        self.total_payouts["roulette"] += max(0, payout)


    @commands.command()
    @commands.admin_or_permissions(administrator=True)
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
                    f"💰 **Total Bet**: {total_bet:.2}\n"
                    f"🏆 **Total Payout**: {total_payout:.2}\n"
                    f"📊 **Actual Payout %**: {actual_er:.2%}\n"
                    f"📉 **House Net**: {net:.2}"
                ),
                inline=False
            )
    
        embed.set_footer(text=f"🧮 Total House Profit: {total_net:.2} WellCoins")
        await ctx.send(embed=embed)
    
