# gachacatchemall/gachacatchemall.py
from __future__ import annotations

import asyncio
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import discord
from redbot.core import commands, Config, checks
import aiohttp


__red_end_user_data_statement__ = (
    "This cog stores Pokémon you catch (per-catch entries with UID, species id/name, types, stats, "
    "sprite, optional nickname) and your last roll and active encounter."
)

POKEAPI_BASE = "https://pokeapi.co/api/v2"

# Reasonable defaults; adjust with [p]gachaadmin setcosts
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

NICKNAME_RE = re.compile(r"^[A-Za-z]{1,20}$")  # “letters only, max 20”

class GachaCatchEmAll(commands.Cog):
    """Pokémon encounter & multi-throw gacha using Wellcoins + PokéAPI."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: Config = Config.get_conf(self, identifier="pokemon", force_registration=True)
        # pokebox now stores a LIST of individual entries (each with uid)
        self.config.register_user(pokebox=[], last_roll=None, active_encounter=None)
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
        Designed to be fast: small concurrent batch + cache.
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
                    pdata.get("sprites", {})
                    .get("other", {})
                    .get("official-artwork", {})
                    .get("front_default")
                    or pdata.get("sprites", {}).get("front_default")
                )
                if not sprite:
                    return None
                return (pid, pdata, bst)
            except Exception:
                return None

        # Fetch concurrently; time-box to 5s.
        tasks = [fetch(pid) for pid in ids]
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
        except asyncio.TimeoutError:
            results = []
        triples: List[Tuple[int, Dict[str, Any], int]] = [t for t in results if t]
        if not triples:
            # Fallback to popular starters + Pikachu, then Bulbasaur
            for pid in (1, 4, 7, 25):
                try:
                    pdata = await self._get_pokemon(pid)
                    bst = sum(s["base_stat"] for s in pdata.get("stats", []))
                    return pdata, pid, bst
                except Exception:
                    continue
            pdata = await self._get_pokemon(1)
            return pdata, 1, sum(s["base_stat"] for s in pdata.get("stats", []))

        # Weighting by ball
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

    # --------- UI helpers ---------

    def _encounter_embed(
        self, user: discord.abc.User, enc: Dict[str, Any], costs: Dict[str, float]
    ) -> discord.Embed:
        title = f"🌿 A wild {enc['name']} appeared!"
        desc = (
            f"""Base Stat Total: **{enc['bst']}**\n
            Misses so far: **{enc.get('fails', 0)}**\n\n
            **Choose a ball:**\n
            ⚪ Poké Ball — **{costs['pokeball']:.2f}** WC\n
            🔵 Great Ball — **{costs['greatball']:.2f}** WC\n
            🟡 Ultra Ball — **{costs['ultraball']:.2f}** WC\n
            🟣 Master Ball — **{costs['masterball']:.2f}** WC"""
        )
        embed = discord.Embed(title=title, description=desc, color=discord.Color.green())
        if enc.get("sprite"):
            embed.set_thumbnail(url=enc["sprite"])
        return embed

    # --------- View / Buttons ---------

    class EncounterView(discord.ui.View):
        def __init__(self, cog: "GachaCatchEmAll", author: discord.abc.User, timeout: int = 120):
            super().__init__(timeout=timeout)
            self.cog = cog
            self.author = author
            self.message: Optional[discord.Message] = None

        # --- utilities ---
        def _disable_all(self):
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

        async def on_timeout(self):
            # Lock buttons when time runs out
            self._disable_all()
            try:
                if self.message:
                    await self.message.edit(view=self)
            except Exception:
                pass

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.author.id:
                await interaction.response.send_message(
                    "This encounter isn't yours — run /gacha to start your own.", ephemeral=True
                )
                return False
            return True

        async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except Exception:
                pass
            target_msg = self.message or interaction.message
            try:
                await target_msg.edit(content=f"⚠️ Error: {type(error).__name__}: {error}", view=self)
            except Exception:
                pass

        # --- throw logic ---
        async def _throw(self, interaction: discord.Interaction, ball_key: str, label: str):
            # ACK quickly (no new message)
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass

            # Load active encounter
            uconf = self.cog.config.user(interaction.user)
            enc = await uconf.active_encounter()
            target_msg = self.message or interaction.message
            if not enc:
                try:
                    await target_msg.edit(content="There is no active encounter. Use /gacha again.", embed=None, view=None)
                except Exception:
                    pass
                return

            # Charge
            costs = await self.cog.config.costs()
            cost = float(costs[ball_key])
            try:
                await self.cog._charge(interaction.user, cost)
            except Exception as e:
                try:
                    await target_msg.edit(content=f"❌ {e}", view=self)
                except Exception:
                    pass
                return

            try:
                # compute catch chance
                bst = int(enc["bst"])
                chance = self.cog._compute_catch_chance(ball_key, bst)
                caught = (ball_key == "masterball") or (random.random() <= chance)

                if caught:
                    # save per-catch entry and end encounter
                    pdata = await self.cog._get_pokemon(enc["id"])
                    types = [t["type"]["name"] for t in pdata.get("types", [])]
                    stats_map = {s["stat"]["name"]: int(s["base_stat"]) for s in pdata.get("stats", [])}
                    uid = uuid.uuid4().hex[:12]  # short UID
                    entry = {
                        "uid": uid,
                        "pokedex_id": int(enc["id"]),
                        "name": enc["name"],
                        "types": types,
                        "stats": stats_map,
                        "bst": int(enc["bst"]),
                        "sprite": enc.get("sprite"),
                        "nickname": None,
                        "caught_at": datetime.now(timezone.utc).isoformat(),
                    }
                    box = await uconf.pokebox()
                    if not isinstance(box, list):
                        box = []
                    box.append(entry)
                    await uconf.pokebox.set(box)
                    await uconf.active_encounter.clear()

                    embed = discord.Embed(
                        title=f"🎉 Caught {enc['name']}!",
                        description=f"UID: `{uid}` — use `$nickname {uid} <Name>` to nickname it.",
                        color=discord.Color.gold(),
                    )
                    if enc.get("sprite"):
                        embed.set_thumbnail(url=enc["sprite"])
                    bal = await self.cog._get_balance(interaction.user)
                    embed.set_footer(text=f"New balance: {bal:.2f} WC")

                    self._disable_all()
                    await target_msg.edit(content=None, embed=embed, view=self)
                    self.stop()
                    return

                # not caught — roll flee chance
                fails = int(enc.get("fails", 0)) + 1
                enc["fails"] = fails
                flee_base = float(enc.get("flee_base", 0.08))
                flee_chance = min(0.85, flee_base + 0.12 * fails)
                fled = random.random() < flee_chance

                if fled:
                    await uconf.active_encounter.clear()
                    embed = discord.Embed(
                        title=f"💨 {enc['name']} fled!",
                        description="Better luck next time.",
                        color=discord.Color.red(),
                    )
                    if enc.get("sprite"):
                        embed.set_thumbnail(url=enc["sprite"])
                    bal = await self.cog._get_balance(interaction.user)
                    embed.set_footer(text=f"New balance: {bal:.2f} WC")

                    self._disable_all()
                    await target_msg.edit(content=None, embed=embed, view=self)
                    self.stop()
                    return

                # still here — update encounter UI with incremented fails
                await uconf.active_encounter.set(enc)
                embed = self.cog._encounter_embed(interaction.user, enc, costs)
                embed.title = f"❌ It broke free! Wild {enc['name']} is still here!"
                bal = await self.cog._get_balance(interaction.user)
                embed.set_footer(
                    text=f"Catch chance now ~ {int(self.cog._compute_catch_chance(ball_key, bst)*100)}% • Balance: {bal:.2f} WC"
                )
                await target_msg.edit(content=None, embed=embed, view=self)

                # save last roll
                await uconf.last_roll.set(
                    {"pokemon": enc["name"], "id": enc["id"], "bst": enc["bst"], "ball": ball_key, "caught": False}
                )

            except Exception as e:
                # refund on error
                try:
                    await self.cog._refund(interaction.user, cost)
                except Exception:
                    pass
                try:
                    await target_msg.edit(content=f"⚠️ Something went wrong: {e}", view=self)
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
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass

            uconf = self.cog.config.user(interaction.user)
            enc = await uconf.active_encounter()
            await uconf.active_encounter.clear()
            target_msg = self.message or interaction.message

            self._disable_all()
            if enc:
                embed = discord.Embed(title=f"You ran away from {enc['name']}.", color=discord.Color.dark_grey())
                if enc.get("sprite"):
                    embed.set_thumbnail(url=enc["sprite"])
                await target_msg.edit(embed=embed, view=self)
            else:
                await target_msg.edit(content="No active encounter.", embed=None, view=self)
            self.stop()

    # --------- Commands ---------

    @commands.hybrid_command(name="gacha")
    async def gacha(self, ctx: commands.Context):
        """Start (or resume) a wild encounter. Multi-throw enabled until catch or flee."""
        try:
            _ = await self._get_balance(ctx.author)
        except Exception as e:
            await ctx.reply(f"Economy unavailable: {e}\nMake sure the NexusExchange cog is loaded.")
            return

        uconf = self.config.user(ctx.author)
        enc = await uconf.active_encounter()

        # If no active encounter, roll a new one (neutral bias for encounter only)
        if not enc:
            pdata, pid, bst = await self._random_encounter("greatball")
            name = pdata.get("name", "unknown").title()
            sprite = (
                pdata.get("sprites", {})
                .get("other", {})
                .get("official-artwork", {})
                .get("front_default")
                or pdata.get("sprites", {}).get("front_default")
            )
            # compute a base flee rate from BST (stronger mons slightly braver)
            flee_base = max(0.05, min(0.25, 0.10 + (bst - 400) / 800.0))
            enc = {
                "id": int(pid),
                "name": name,
                "bst": int(bst),
                "sprite": sprite,
                "fails": 0,
                "flee_base": float(flee_base),
            }
            await uconf.active_encounter.set(enc)

        costs = await self.config.costs()
        embed = self._encounter_embed(ctx.author, enc, costs)
        view = self.EncounterView(self, ctx.author)
        msg = await ctx.reply(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(name="pokebox")
    async def pokebox(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Show your (or another member's) caught Pokémon summary by species."""
        member = member or ctx.author
        box = await self.config.user(member).pokebox()
        if not box:
            await ctx.reply(f"{member.display_name} has no Pokémon yet. Go roll the gacha!")
            return

        # Summarize by species
        counts: Dict[str, int] = {}
        for entry in box:
            key = entry.get("name", "Unknown")
            counts[key] = counts.get(key, 0) + 1

        entries = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        chunks: List[str] = []
        line = []
        total = 0
        for name, count in entries:
            total += count
            line.append(f"**{name}** ×{count}")
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

    @commands.hybrid_command(name="pokeinv")
    async def pokeinv(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """List your (or another member's) individual Pokémon with UID & nickname."""
        member = member or ctx.author
        box: List[Dict[str, Any]] = await self.config.user(member).pokebox()
        if not box:
            await ctx.reply(f"{member.display_name} has no Pokémon yet.")
            return

        # sort newest first
        box_sorted = sorted(box, key=lambda e: e.get("caught_at", ""), reverse=True)
        page_size = 8
        pages = [box_sorted[i : i + page_size] for i in range(0, len(box_sorted), page_size)]
        for i, page in enumerate(pages, start=1):
            lines = []
            for e in page:
                nick = e.get("nickname")
                label = f"{e['name']} (#{e['pokedex_id']})"
                if nick:
                    label += f" — **{nick}**"
                lines.append(f"`{e['uid']}` • {label}")
            embed = discord.Embed(
                title=f"{member.display_name}'s Pokémon (page {i}/{len(pages)})",
                description="\n".join(lines),
                color=discord.Color.blue(),
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="nickname")
    async def nickname(self, ctx: commands.Context, uid: str, nickname: Optional[str] = None):
        """Set or clear a nickname for a caught Pokémon by UID.
        Nicknames must be LETTERS ONLY (A-Z) and at most 20 characters.
        Omit the nickname to CLEAR it.
        """
        box: List[Dict[str, Any]] = await self.config.user(ctx.author).pokebox()
        if not box:
            await ctx.reply("You have no Pokémon.")
            return

        # find entry
        target = None
        for e in box:
            if e.get("uid") == uid:
                target = e
                break
        if not target:
            await ctx.reply("UID not found in your PokéBox.")
            return

        if nickname is None:
            target["nickname"] = None
            await self.config.user(ctx.author).pokebox.set(box)
            await ctx.reply(f"Cleared nickname for `{uid}` ({target['name']}).")
            return

        if not NICKNAME_RE.match(nickname):
            await ctx.reply("Nickname must be LETTERS ONLY (A–Z/a–z), 1–20 chars.")
            return

        target["nickname"] = nickname
        await self.config.user(ctx.author).pokebox.set(box)
        await ctx.reply(f"Set nickname for `{uid}` to **{nickname}**.")

    @checks.admin()
    @commands.hybrid_group(name="gachaadmin")
    async def gachaadmin(self, ctx: commands.Context):
        """Admin settings for PokéGacha."""
        pass

    @gachaadmin.command(name="resetpokedata")
    @checks.admin()
    async def gacha_resetpokedata(self, ctx: commands.Context, confirm: Optional[bool] = False):
        """WIPE ALL users' PokéBoxes and active encounters. Use with care!
        Example: `[p]gachaadmin resetpokedata true`
        """
        if not confirm:
            await ctx.reply("⚠️ This will wipe ALL users' PokéBoxes and encounters. Re-run with `true` to confirm.")
            return

        # Get all user data and wipe the fields we own
        all_users = await self.config.all_users()
        wiped = 0
        for user_id, data in all_users.items():
            # reset to defaults we registered
            data["pokebox"] = []
            data["active_encounter"] = None
            # keep last_roll if you like, or clear:
            data["last_roll"] = None
            await self.config.user_from_id(int(user_id)).set(data)
            wiped += 1

        await ctx.reply(f"🧹 Reset Poké data for {wiped} users.")

    @gachaadmin.command(name="setcosts")
    @checks.admin()
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
