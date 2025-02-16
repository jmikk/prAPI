import random
import discord
from redbot.core import commands, Config, checks
import asyncio


class Casino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, identifier=345678654456, force_registration=True)

    async def get_balance(self, user: discord.Member):
        return await self.config.user(user).master_balance()

    async def update_balance(self, user: discord.Member, amount: int):
        balance = await self.get_balance(user)
        new_balance = max(0, balance + amount)  # Prevent negative balance
        await self.config.user(user).master_balance.set(new_balance)
        return new_balance

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def coinflip(self, ctx, bet: int, call_it=None):
        """Flip a coin and win or lose your bet (House Edge: 52% loss, 48% win)"""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        outcome = random.choices(["win", "lose"], weights=[48, 52])[0]
        if outcome == "win":
            winnings = bet
            new_balance = await self.update_balance(ctx.author, winnings)
            await ctx.send(f"You won! Your new balance is {new_balance} WellCoins.")
        else:
            new_balance = await self.update_balance(ctx.author, -bet)
            await ctx.send(f"You lost! Your new balance is {new_balance} WellCoins.")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def dice(self, ctx, bet: int):
        """Roll a dice against the house (House rolls 1-6, Player rolls 1-5)"""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        player_roll = random.randint(1, 6)
        house_roll = random.choices([1, 2, 3, 4, 5, 6], weights=[5, 10, 15, 20, 25, 30])[0]
        
        if player_roll > house_roll:
            winnings = bet
            new_balance = await self.update_balance(ctx.author, winnings)
            await ctx.send(f"You rolled {player_roll}, house rolled {house_roll}. You win! New balance: {new_balance} WellCoins.")
        else:
            new_balance = await self.update_balance(ctx.author, -bet)
            await ctx.send(f"You rolled {player_roll}, house rolled {house_roll}. You lose! New balance: {new_balance} WellCoins.")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def slots(self, ctx, bet: int):
        """Play a slot machine with emojis and live message updates."""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        emojis = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎", "🌸"]
        message = await ctx.send("Spinning... 🎰")
        
        slots = []
        for _ in range(3):
            slots = [random.choice(emojis) for _ in range(3)]
            await message.edit(content=f"{' | '.join(slots)}\n{' | '.join(slots)}\n{' | '.join(slots)}")
            await asyncio.sleep(1)
        
        payout = 0
        if slots.count("🍒") == 2:
            payout = bet * 3
            result_text = "Two cherries! 🍒 You win 3x your bet!"
        elif len(set(slots)) == 1:
            payout = bet * 10
            result_text = "Three of a kind! 🎉 You win 10x your bet!"
        elif slots.count("🌸") == 3:
            payout = bet * 50
            result_text = "JACKPOT! 🌸🌸🌸 You hit the cherry blossoms jackpot!"
        else:
            payout = -bet
            result_text = "You lost! 😢"
        
        new_balance = await self.update_balance(ctx.author, payout)
        await message.edit(content=f"{' | '.join(slots)}\n{result_text} New balance: {new_balance} WellCoins.")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def roulette(self, ctx, bet: int, choice: str):
        """Play roulette (Red/Black = 2x, Number (0-36) = 35x)"""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        result = random.randint(0, 36)
        color = "red" if result % 2 == 0 else "black"
        payout = 0
        
        if choice.lower() in ["red", "black"]:
            if choice.lower() == color:
                payout = bet * 2
        elif choice.isdigit() and 0 <= int(choice) <= 36:
            if int(choice) == result:
                payout = bet * 35
        
        if payout > 0:
            new_balance = await self.update_balance(ctx.author, payout)
            await ctx.send(f"Roulette landed on {result} ({color}). You won {payout} WellCoins! New balance: {new_balance}")
        else:
            new_balance = await self.update_balance(ctx.author, -bet)
            await ctx.send(f"Roulette landed on {result} ({color}). You lost! New balance: {new_balance} WellCoins.")
