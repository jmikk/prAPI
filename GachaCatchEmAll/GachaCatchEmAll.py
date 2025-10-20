# PokeAutoBattler: Prefix Command Edition
# Converts all slash commands to standard Redbot prefix commands for easier use.

import asyncio
import json
import random
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import humanize_timedelta, pagify

RARITIES = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]

@dataclass
class Move:
    name: str
    power: int
    accuracy: int = 95
    crit: float = 0.05

@dataclass
class Species:
    name: str
    rarity: str
    base_hp: int
    base_atk: int
    base_def: int
    base_spd: int
    moves: List[str]

@dataclass
class Mon:
    id: str
    species: str
    rarity: str
    level: int
    xp: int
    max_hp: int
    hp: int
    atk: int
    defn: int
    spd: int
    moves: List[str]
    fainted: bool = False

    @classmethod
    def from_species(cls, sp: Species, level: int):
        def scale(base, lvl, mult=1.0):
            return int(base + (lvl ** 1.2) * mult)
        rarity_mult = {"COMMON": 1, "UNCOMMON": 1.05, "RARE": 1.1, "EPIC": 1.18, "LEGENDARY": 1.28}[sp.rarity]
        return cls(
            id=str(uuid.uuid4())[:8],
            species=sp.name,
            rarity=sp.rarity,
            level=level,
            xp=0,
            max_hp=int(scale(sp.base_hp, level, 2.0)),
            hp=int(scale(sp.base_hp, level, 2.0)),
            atk=int(scale(sp.base_atk, level) * rarity_mult),
            defn=int(scale(sp.base_def, level) * rarity_mult),
            spd=int(scale(sp.base_spd, level, 0.8) * rarity_mult),
            moves=sp.moves[:2]
        )

class EconomyAdapter:
    def __init__(self, bot: Red, config: Config):
        self.bot = bot
        self.config = config

    async def wc_get(self, user: discord.User):
        econ = self.bot.get_cog("NexusExchange")
        if econ and hasattr(econ, "get_balance"):
            return await econ.get_balance(user)
        return await self.config.user(user).wallet()

    async def wc_add(self, user: discord.User, amt: float):
        econ = self.bot.get_cog("NexusExchange")
        if econ and hasattr(econ, "add_wellcoins"):
            return await econ.add_wellcoins(user, amt)
        async with self.config.user(user).wallet() as w:
            w += amt
            return w

    async def wc_take(self, user: discord.User, amt: float):
        econ = self.bot.get_cog("NexusExchange")
        if econ and hasattr(econ, "take_wellcoins"):
            try:
                await econ.take_wellcoins(user, amt)
                return True
            except Exception:
                return False
        async with self.config.user(user).wallet() as w:
            if w < amt:
                return False
            w -= amt
                return True
        async with self.config.user(user).wallet() as w:
            if w < amt:
                return False
            w -= amt
            return True

class PokeAutoBattler(commands.Cog):
    """GachaCatchEmAll main cog using prefix commands under [p]pokemon."""

    @commands.group(name="pokemon", invoke_without_command=True)
    async def pokemon(self, ctx):
        """Pokémon Gacha Main Menu"""
        embed = discord.Embed(title="Pokémon Gacha", description="Use subcommands like `pokemon roll`, `pokemon mons`, or `pokemon balls`.", color=0x2b2d31)
        await ctx.send(embed=embed)

    @pokemon.command(name="balls")
    async def pokemon_balls(self, ctx):
        """View all gacha ball types and prices."""
        if not self.balls:
            return await ctx.send("No Pokéballs configured yet.")

        embed = discord.Embed(title="🎯 Available Pokéballs", color=0x3498db)
        emoji_map = {"pokeball": "⚪", "greatball": "🔵", "ultraball": "🟡", "masterball": "🟣"}

        for name, data in self.balls.items():
            emoji = emoji_map.get(name.lower(), "🔘")
            price = data.get("price", 0)
            lvmin, lvmax = data.get("level_range", [1, 1])
            embed.add_field(name=f"{emoji} {name.title()}", value=f"**Price:** {price} WC
**Lv Range:** {lvmin}–{lvmax}", inline=False)

        await ctx.send(embed=embed)

    # --- ROLL COMMAND WITH BUTTONS ---
    @pokemon.command(name="roll")
    async def pokemon_roll(self, ctx):
        """Open the Pokéball roll menu."""
        emoji_map = {"pokeball": "⚪", "greatball": "🔵", "ultraball": "🟡", "masterball": "🟣"}

        # Build button view to select Pokéball
        class BallSelectView(discord.ui.View):
            def __init__(self, parent):
                super().__init__(timeout=30)
                self.parent = parent
                self.selected_ball = None

                for name in parent.balls.keys():
                    label = name.title()
                    emoji = emoji_map.get(name.lower(), "🔘")
                    self.add_item(self.BallButton(label, name, emoji, parent))

            class BallButton(discord.ui.Button):
                def __init__(self, label, ball_key, emoji, parent):
                    super().__init__(label=label, style=discord.ButtonStyle.primary, emoji=emoji)
                    self.ball_key = ball_key
                    self.parent = parent

                async def callback(self, interaction: discord.Interaction):
                    if interaction.user != ctx.author:
                        return await interaction.response.send_message("This menu isn't for you.", ephemeral=True)

                    # After selecting the ball, show roll options
                    view = RollAmountView(self.ball_key, self.parent, ctx)
                    embed = discord.Embed(
                        title=f"{self.emoji} {self.ball_key.title()} Selected",
                        description="Choose how many rolls you want:",
                        color=0x2ecc71
                    )
                    await interaction.response.edit_message(embed=embed, view=view)

        class RollAmountView(discord.ui.View):
            def __init__(self, ball_key, parent, ctx):
                super().__init__(timeout=30)
                self.ball_key = ball_key
                self.parent = parent
                self.ctx = ctx
                for amount in [1, 5, 10, 25, 100]:
                    self.add_item(self.RollButton(amount, ball_key, parent, ctx))

            class RollButton(discord.ui.Button):
                def __init__(self, amount, ball_key, parent, ctx):
                    super().__init__(label=f"{amount}x", style=discord.ButtonStyle.secondary)
                    self.amount = amount
                    self.ball_key = ball_key
                    self.parent = parent
                    self.ctx = ctx

                async def callback(self, interaction: discord.Interaction):
                    if interaction.user != ctx.author:
                        return await interaction.response.send_message("This menu isn't for you.", ephemeral=True)

                    cost = self.parent.balls[self.ball_key]["price"] * self.amount
                    has_money = await self.parent.econ.wc_take(self.ctx.author, cost)
                    if not has_money:
                        balance = await self.parent.econ.wc_get(self.ctx.author)
                        return await interaction.response.send_message(
                            f"❌ Not enough Wellcoins. Cost: {cost} WC | You have: {balance}", ephemeral=True)

                    results = []
                    for _ in range(self.amount):
                        mon = await self.parent._roll_one(self.ball_key)
                        await self.parent._save_mon(self.ctx.author, mon)
                        results.append(f"Lv{mon.level} {mon.species} [{mon.rarity}]")

                    embed = discord.Embed(title=f"✅ Rolled {self.amount}x {self.ball_key.title()}", color=0x00ff99)
                    embed.description = "
".join(results[:10]) + ("
...and more!" if len(results) > 10 else "")
                    await interaction.response.edit_message(embed=embed, view=None)

        embed = discord.Embed(title="🎯 Choose a Pokéball", description="Select a Pokéball to roll:", color=0x7289da)
        view = BallSelectView(self)
        await ctx.send(embed=embed, view=view)

    # --- existing code below will be migrated under pokemon group next ---
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        self.config.register_user(mons={}, team=[], wallet=500)
        self.data_path = cog_data_path(raw_name=self.__class__.__name__)
        self.moves = self._load_json("moves.json")
        self.species = self._load_json("species.json")
        self.balls = self._load_json("balls.json")
        self.econ = EconomyAdapter(bot, self.config)

    def _load_json(self, name):
        path = self.data_path / name
        if not path.exists():
            path.write_text(json.dumps({}, indent=2))
        return json.loads(path.read_text())

    async def _save_mon(self, user, mon):
        async with self.config.user(user).mons() as mons:
            mons[mon.id] = asdict(mon)

    @commands.command()
    async def balls(self, ctx):
        """View all gacha ball types and prices."""
        msg = []
        for k, v in self.balls.items():
            msg.append(f"**{k.title()}** — {v['price']} WC, Lv{v['level_range'][0]}–{v['level_range'][1]}")
        await ctx.send("\n".join(msg) or "No balls configured.")

    @commands.command()
    async def roll(self, ctx, ball: str, count: int = 1):
        """Spend Wellcoins to roll a gacha ball."""
        ball = ball.lower()
        if ball not in self.balls:
            return await ctx.send("Unknown ball.")
        total = self.balls[ball]["price"] * count
        if not await self.econ.wc_take(ctx.author, total):
            bal = await self.econ.wc_get(ctx.author)
            return await ctx.send(f"Not enough Wellcoins. Need {total}, you have {bal}.")
        obtained = []
        for _ in range(count):
            m = await self._roll_one(ball)
            await self._save_mon(ctx.author, m)
            obtained.append(m)
        lines = [f"Spent **{total} WC** and got:"]
        for m in obtained:
            lines.append(f"\nLv{m.level} {m.species} [{m.rarity}] HP {m.hp}/{m.max_hp}")
        await ctx.send("".join(lines))

    async def _roll_one(self, ball):
        info = self.balls[ball]
        rarity = self._pick_rarity(info["rates"])
        candidates = [Species(**v) for v in self.species.values() if v["rarity"] == rarity]
        if not candidates:
            candidates = [Species(**v) for v in self.species.values()]
        sp = random.choice(candidates)
        lvl = random.randint(*info["level_range"])
        return Mon.from_species(sp, lvl)

    def _pick_rarity(self, rates):
        r = random.random()
        s = 0
        for rarity, chance in rates.items():
            s += chance
            if r <= s:
                return rarity
        return "COMMON"

    @commands.command()
    async def mons(self, ctx):
        mons = await self.config.user(ctx.author).mons()
        if not mons:
            return await ctx.send("You have no monsters.")
        msg = []
        for m in mons.values():
            msg.append(f"`{m['id']}` Lv{m['level']} {m['species']} [{m['rarity']}] HP {m['hp']}/{m['max_hp']}")
        pages = list(pagify("\n".join(msg)))
        for p in pages:
            await ctx.send(p)

async def setup(bot):
    await bot.add_cog(PokeAutoBattler(bot))
