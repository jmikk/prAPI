import random
import discord
from redbot.core import commands, Config, checks

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
    async def coinflip(self, ctx, bet: int):
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
        
        player_roll = random.randint(1, 5)
        house_roll = random.randint(1, 6)
        
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
        """Play a slot machine (Jackpot = 10x, small win = 3x, mostly losses)"""
        balance = await self.get_balance(ctx.author)
        if bet <= 0 or bet > balance:
            return await ctx.send("Invalid bet amount.")
        
        outcome = random.choices(["jackpot", "win", "lose"], weights=[5, 20, 75])[0]
        
        if outcome == "jackpot":
            winnings = bet * 10
            new_balance = await self.update_balance(ctx.author, winnings)
            await ctx.send(f"JACKPOT! You won {winnings} WellCoins. New balance: {new_balance}")
        elif outcome == "win":
            winnings = bet * 3
            new_balance = await self.update_balance(ctx.author, winnings)
            await ctx.send(f"You won {winnings} WellCoins! New balance: {new_balance}")
        else:
            new_balance = await self.update_balance(ctx.author, -bet)
            await ctx.send(f"You lost! New balance: {new_balance} WellCoins.")

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
