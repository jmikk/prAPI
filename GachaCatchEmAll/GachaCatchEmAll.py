from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List, Optional, Tuple

import discord
from redbot.core import commands, Config, checks
import aiohttp


__red_end_user_data_statement__ = (
    "This cog stores a list of Pokémon you've caught (name, count) and your last rolls."
)


POKEAPI_BASE = "https://pokeapi.co/api/v2"

# Reasonable defaults; you can adjust with [p]gacha setcosts
DEFAULT_COSTS = {
    "pokeball": 5.0,
    "greatball": 15.0,
    "ultraball": 50.0,
    "masterball": 200.0,
}

# Catch tuning parameters per ball
BALL_TUNING = {
    # weight_bias: how we bias encounter weights (higher favors strong mons)
    # bonus_catch: added to base catch chance
    "pokeball": {"weight_bias": -1, "bonus_catch": 0.00},
    "greatball": {"weight_bias": 0, "bonus_catch": 0.15},
    "ultraball": {"weight_bias": 1, "bonus_catch": 0.30},
    "masterball": {"weight_bias": 2, "bonus_catch": 999.0},  # auto-catch
}


class GachaCatchEmAll(commands.Cog):
    """Pokémon gacha using Wellcoins + PokéAPI"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: Config = Config.get_conf(self, identifier=0xC0FFEE55, force_registration=True)
        self.config.register_user(pokebox={}, last_roll=None, active_encounter=None)
        self.config.register_global(costs=DEFAULT_COSTS)

        self._session: Optional[aiohttp.ClientSession] = None
        self._pokemon_list: Optional[List[Dict[str, Any]]] = None  # list of {name, url}
        self._pokemon_cache: Dict[int, Dict[str, Any]] = {}  # id -> pokemon data
        self._list_lock = asyncio.Lock()

    # --------- Red utilities ---------

    async def red_delete_data_for_user(self, **kwargs):  # GDPR
        user = kwargs.get("user")
        if user:
            await self.config.user(user).clear()

    def cog_unload(self):
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # --------- Economy helpers (NexusExchange) ---------

    def _nexus(self):
        cog = self.bot.get_cog("NexusExchange")
        if not cog:
            raise RuntimeError(
                "NexusExchange cog not found. Please load it so PokéGacha can charge Wellcoins."
            )
        return cog

    async def _get_balance(self, user: discord.abc.User) -> float:
        return float(await self._nexus().get_balance(user))

    async def _charge(self, user: discord.abc.User, amount: float):
        # Raises ValueError if insufficient (as per NexusExchange API)
        await self._nexus().take_wellcoins(user, amount, force=False)

    async def _refund(self, user: discord.abc.User, amount: float):
        await self._nexus().add_wellcoins(user, amount)

    # --------- PokéAPI helpers ---------

    async def _fetch_json(self, url: str) -> Any:
        session = await self._get_session()
        async with session.get(url, timeout=8) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _ensure_pokemon_list(self):
        async with self._list_lock:
            if self._pokemon_list is not None:
                return
            data = await self._fetch_json(f"{POKEAPI_BASE}/pokemon?limit=20000")
            # keep only Pokémon that have an id (by parsing from URL) and a default sprite later
            self._pokemon_list = data.get("results", [])

    @staticmethod
    def _extract_id_from_url(url: str) -> Optional[int]:
        # URLs look like https://pokeapi.co/api/v2/pokemon/25/
        try:
            parts = url.rstrip("/").split("/")
            return int(parts[-1])
        except Exception:
            return None

    async def _get_pokemon(self, poke_id: int) -> Dict[str, Any]:
        if poke_id in self._pokemon_cache:
            return self._pokemon_cache[poke_id]
        data = await self._fetch_json(f"{POKEAPI_BASE}/pokemon/{poke_id}")
        self._pokemon_cache[poke_id] = data
        return data

    async def _random_encounter(self, ball_key: str) -> Tuple[Dict[str, Any], int, int]:
        """Roll a random Pokémon, biased by base stat totals depending on ball.
        Designed to be **fast** — fetches only a small concurrent batch and uses cache.
        Returns (pokemon_data, poke_id, bst)
        """
        await self._ensure_pokemon_list()
        assert self._pokemon_list is not None

        # Small, tiered batch sizes to keep the interaction snappy
        sample_sizes = {"pokeball": 8, "greatball": 10, "ultraball": 12, "masterball": 14}
        sample_n = sample_sizes.get(ball_key, 10)

        population = random.sample(self._pokemon_list, k=min(sample_n, len(self._pokemon_list)))
        ids: List[int] = []
        for entry in population:
            pid = self._extract_id_from_url(entry["url"])  # type: ignore
            if pid:
                ids.append(pid)

        if not ids:
            pdata = await self._get_pokemon(1)
            return pdata, 1, sum(s["base_stat"] for s in pdata.get("stats", []))

        async def fetch(pid: int) -> Optional[Tuple[int, Dict[str, Any], int]]:
            try:
                pdata = await self._get_pokemon(pid)
                bst = sum(s["base_stat"] for s in pdata.get("stats", []))
                sprite = (
                    pdata.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default")
                    or pdata.get("sprites", {}).get("front_default")
                )
                if not sprite:
                    return None
                return (pid, pdata, bst)
            except Exception:
                return None

        # Fetch concurrently (bounded by aiohttp connector limit implicitly). Time-box to 5s.
        tasks = [fetch(pid) for pid in ids]
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
        except asyncio.TimeoutError:
            # Try any finished tasks; if none, fallback
            results = []
        triples: List[Tuple[int, Dict[str, Any], int]] = [t for t in results if t]
        if not triples:
            # Fallback to a quick single fetch of a popular mon
            for pid in (1, 4, 7, 25):
                try:
                    pdata = await self._get_pokemon(pid)
                    bst = sum(s["base_stat"] for s in pdata.get("stats", []))
                    return pdata, pid, bst
                except Exception:
                    continue
            pdata = await self._get_pokemon(1)
            return pdata, 1, sum(s["base_stat"] for s in pdata.get("stats", []))

        # Weighting
        bias = BALL_TUNING[ball_key]["weight_bias"]
        weights: List[int] = []
        for _, pdata, bst in triples:
            if bias < 0:
                w = max(1, 800 - bst)
            elif bias == 0:
                w = max(1, 100 + abs(500 - bst) // 5)
            elif bias == 1:
                w = max(1, bst)
            else:
                w = max(1, bst * bst // 50)
            weights.append(w)

        choice_idx = random.choices(range(len(triples)), weights=weights, k=1)[0]
        pid, pdata, bst = triples[choice_idx]
        return pdata, pid, bst

    @staticmethod
    def _compute_catch_chance(ball_key: str, bst: int) -> float:
        if ball_key == "masterball":
            return 1.0
        difficulty = min(1.2, bst / 700.0)
        base = 0.40
        bonus = BALL_TUNING[ball_key]["bonus_catch"]
        chance = base + bonus - (0.50 * difficulty)
        return max(0.05, min(0.95, chance))

    # --------- Views / Buttons ---------

    def _encounter_embed(self, user: discord.abc.User, enc: Dict[str, Any], costs: Dict[str, float]) -> discord.Embed:
        title = f"🌿 A wild {enc['name']} appeared!"
        desc = (
            f"""Base Stat Total: **{enc['bst']}** Misses so far: **{enc.get('fails', 0)}** 
            **Choose a ball:**
            ⚪ Poké Ball — **{costs['pokeball']:.2f}** WC
            🔵 Great Ball — **{costs['greatball']:.2f}** WC
            🟡 Ultra Ball — **{costs['ultraball']:.2f}** WC
            🟣 Master Ball — **{costs['masterball']:.2f}** WC"""
        )
        embed = discord.Embed(title=title, description=desc, color=discord.Color.green())
        if enc.get('sprite'):
            embed.set_thumbnail(url=enc['sprite'])
        return embed

    class EncounterView(discord.ui.View):
        def __init__(self, cog: "GachaCatchEmAll", author: discord.abc.User, timeout: int = 120):
            super().__init__(timeout=timeout)
            self.cog = cog
            self.author = author

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.author.id:
                await interaction.response.send_message("This encounter isn't yours — run /gacha to start your own.", ephemeral=True)
                return False
            return True

        async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
            try:
                msg = f"⚠️ Error: {type(error).__name__}: {error}"
                if interaction.response.is_done():
                    await interaction.followup.send(msg)
                else:
                    await interaction.response.send_message(msg)
            except Exception:
                pass

        async def _throw(self, interaction: discord.Interaction, ball_key: str, label: str):
            # Try to load the current encounter
            uconf = self.cog.config.user(interaction.user)
            enc = await uconf.active_encounter()
            if not enc:
                if not interaction.response.is_done():
                    await interaction.response.send_message("There is no active encounter. Use /gacha again.")
                else:
                    await interaction.followup.send("There is no active encounter. Use /gacha again.")
                return

            costs = await self.cog.config.costs()
            cost = float(costs[ball_key])

            # Always defer first to avoid timeouts, then send a visible loading message
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            try:
                loading_msg = await interaction.followup.send(
                    f"{interaction.user.display_name} threw a {label}..."
                )
            except Exception:
                loading_msg = None

            # Charge
            try:
                await self.cog._charge(interaction.user, cost)
            except Exception as e:
                text = f"❌ {e}"
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(text)
                    elif loading_msg:
                        await loading_msg.edit(content=text)
                    else:
                        await interaction.channel.send(text)
                except Exception:
                    pass
                return

            try:
                # compute catch chance
                bst = int(enc['bst'])
                chance = self.cog._compute_catch_chance(ball_key, bst)
                caught = (ball_key == 'masterball') or (random.random() <= chance)

                if caught:
                    # save and end encounter
                    name = enc['name']
                    sprite = enc.get('sprite')
                    box = await uconf.pokebox()
                    box[name] = int(box.get(name, 0)) + 1
                    await uconf.pokebox.set(box)
                    await uconf.active_encounter.clear()

                    embed = discord.Embed(
                        title=f"🎉 Caught {name}!",
                        description=f"Added to your PokéBox.",
                        color=discord.Color.gold()
                    )
                    if sprite:
                        embed.set_thumbnail(url=sprite)
                    bal = await self.cog._get_balance(interaction.user)
                    embed.set_footer(text=f"New balance: {bal:.2f} WC")

                    if loading_msg:
                        await loading_msg.edit(content=None, embed=embed, view=None)
                    else:
                        await interaction.edit_original_response(embed=embed, view=None)
                    return

                # not caught — roll flee chance
                fails = int(enc.get('fails', 0)) + 1
                enc['fails'] = fails
                flee_base = float(enc.get('flee_base', 0.08))
                flee_chance = min(0.85, flee_base + 0.12 * fails)
                fled = random.random() < flee_chance

                if fled:
                    await uconf.active_encounter.clear()
                    embed = discord.Embed(
                        title=f"💨 {enc['name']} fled!",
                        description="Better luck next time.",
                        color=discord.Color.red()
                    )
                    if enc.get('sprite'):
                        embed.set_thumbnail(url=enc['sprite'])
                    bal = await self.cog._get_balance(interaction.user)
                    embed.set_footer(text=f"New balance: {bal:.2f} WC")
                    if loading_msg:
                        await loading_msg.edit(content=None, embed=embed, view=None)
                    else:
                        await interaction.edit_original_response(embed=embed, view=None)
                    return

                # still here — update encounter UI with incremented fails
                await uconf.active_encounter.set(enc)
                costs = await self.cog.config.costs()
                embed = self.cog._encounter_embed(interaction.user, enc, costs)
                embed.title = f"❌ It broke free! Wild {enc['name']} is still here!"
                bal = await self.cog._get_balance(interaction.user)
                embed.set_footer(text=f"Catch chance now ~ {int(self.cog._compute_catch_chance(ball_key, bst)*100)}% • Balance: {bal:.2f} WC")
                if loading_msg:
                    await loading_msg.edit(content=None, embed=embed, view=self)
                else:
                    await interaction.edit_original_response(embed=embed, view=self)

                # save last roll
                await uconf.last_roll.set({
                    "pokemon": enc['name'],
                    "id": enc['id'],
                    "bst": enc['bst'],
                    "ball": ball_key,
                    "caught": False,
                })

            except Exception as e:
                # refund on error
                try:
                    await self.cog._refund(interaction.user, cost)
                except Exception:
                    pass
                msg = f"⚠️ Something went wrong: {e}"
                if loading_msg:
                    try:
                        await loading_msg.edit(content=msg)
                    except Exception:
                        pass
                else:
                    try:
                        if interaction.response.is_done():
                            await interaction.followup.send(msg)
                        else:
                            await interaction.response.send_message(msg)
                    except Exception:
                        pass

        @discord.ui.button(label="Poké Ball", style=discord.ButtonStyle.secondary, emoji="⚪")
        async def pokeball(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._throw(interaction, "pokeball", "Poké Ball")

        @discord.ui.button(label="Great Ball", style=discord.ButtonStyle.primary, emoji="🔵")
        async def greatball(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._throw(interaction, "greatball", "Great Ball")

        @discord.ui.button(label="Ultra Ball", style=discord.ButtonStyle.success, emoji="🟡")
        async def ultraball(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._throw(interaction, "ultraball", "Ultra Ball")

        @discord.ui.button(label="Master Ball", style=discord.ButtonStyle.danger, emoji="🟣")
        async def masterball(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._throw(interaction, "masterball", "Master Ball")

        @discord.ui.button(label="Run", style=discord.ButtonStyle.secondary, emoji="🏃")
        async def run(self, interaction: discord.Interaction, button: discord.ui.Button):
            uconf = self.cog.config.user(interaction.user)
            enc = await uconf.active_encounter()
            await uconf.active_encounter.clear()
            if enc:
                embed = discord.Embed(title=f"You ran away from {enc['name']}.", color=discord.Color.dark_grey())
                if enc.get('sprite'):
                    embed.set_thumbnail(url=enc['sprite'])
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                await interaction.response.send_message("No active encounter.")

    # --------- Commands ---------


    @commands.hybrid_command(name="gacha")
    async def gacha(self, ctx: commands.Context):
        """Start (or resume) a wild encounter. Multi-throw enabled until catch or flee."""
        try:
            _ = await self._get_balance(ctx.author)
        except Exception as e:
            await ctx.reply(f"Economy unavailable: {e} Make sure the NexusExchange cog is loaded.")
            return

        uconf = self.config.user(ctx.author)
        enc = await uconf.active_encounter()

        # If no active encounter, roll a new one
        if not enc:
            pdata, pid, bst = await self._random_encounter("greatball")  # neutral bias for encounter only
            name = pdata.get("name", "unknown").title()
            sprite = (
                pdata.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default")
                or pdata.get("sprites", {}).get("front_default")
            )
            # compute a base flee rate from BST (stronger mons slightly braver)
            flee_base = max(0.05, min(0.25, 0.10 + (bst - 400) / 800.0))
            enc = {"id": int(pid), "name": name, "bst": int(bst), "sprite": sprite, "fails": 0, "flee_base": float(flee_base)}
            await uconf.active_encounter.set(enc)

        costs = await self.config.costs()
        embed = self._encounter_embed(ctx.author, enc, costs)
        view = self.EncounterView(self, ctx.author)
        await ctx.reply(embed=embed, view=view)

    @commands.hybrid_command(name="pokebox")
    async def pokebox(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Show your (or another member's) caught Pokémon."""
        member = member or ctx.author
        box = await self.config.user(member).pokebox()
        if not box:
            await ctx.reply(f"{member.display_name} has no Pokémon yet. Go roll the gacha!")
            return

        # Sort by count desc, then name
        entries = sorted(box.items(), key=lambda kv: (-int(kv[1]), kv[0]))
        chunks: List[str] = []
        line = []
        total = 0
        for name, count in entries:
            total += int(count)
            line.append(f"**{name}** ×{int(count)}")
            if sum(len(x) for x in line) > 800:
                chunks.append(" • ".join(line))
                line = []
        if line:
            chunks.append(" • ".join(line))

        for i, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=(f"{member.display_name}'s PokéBox (page {i}/{len(chunks)})"),
                description=chunk,
                color=discord.Color.teal(),
            )
            if i == 1:
                embed.set_footer(text=f"Total caught: {total}")
            await ctx.send(embed=embed)

    @checks.admin()
    @commands.hybrid_group(name="gachaadmin")
    async def gachaadmin(self, ctx: commands.Context):
        """Admin settings for PokéGacha."""
        pass

    @gachaadmin.command(name="setcosts")
    async def gacha_setcosts(
        self,
        ctx: commands.Context,
        pokeball: Optional[float] = None,
        greatball: Optional[float] = None,
        ultraball: Optional[float] = None,
        masterball: Optional[float] = None,
    ):
        """Set custom Wellcoin costs for balls. Omit a value to leave it unchanged.
        Example: `[p]gachaadmin setcosts 10 25 60 250`"""
        costs = await self.config.costs()
        if pokeball is not None:
            costs["pokeball"] = float(pokeball)
        if greatball is not None:
            costs["greatball"] = float(greatball)
        if ultraball is not None:
            costs["ultraball"] = float(ultraball)
        if masterball is not None:
            costs["masterball"] = float(masterball)
        await self.config.costs.set(costs)
        await ctx.reply(
            "Updated costs: "
            f"Poké {costs['pokeball']:.2f}, Great {costs['greatball']:.2f}, "
            f"Ultra {costs['ultraball']:.2f}, Master {costs['masterball']:.2f}"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCatchEmAll(bot))
