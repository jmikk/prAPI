# battle_tower.py
import copy
import random
from typing import Dict, List, Optional, Tuple, Union

import discord
from redbot.core import commands, Config

HP_BAR_LEN = 20


def _hp_bar(cur: int, maxhp: int, length: int = HP_BAR_LEN) -> str:
    cur = max(0, min(cur, maxhp))
    fill = int(round((cur / maxhp) * length)) if maxhp > 0 else 0
    return "▰" * fill + "▱" * (length - fill)


def _init_hp(mon: Dict) -> int:
    """Readable in-embed HP scale (not your stored base)."""
    base_hp = int(mon.get("stats", {}).get("hp", 1))
    return max(10, base_hp * 5)


def _bst(mon: Dict) -> int:
    s = mon.get("stats", {})
    return int(
        s.get("hp", 0)
        + s.get("attack", 0)
        + s.get("defense", 0)
        + s.get("special-attack", 0)
        + s.get("special-defense", 0)
        + s.get("speed", 0)
    )


def _parse_move(move_str: str) -> Tuple[str, str, str, Optional[int]]:
    """
    Supports your custom move format:
      'thunderbolt {electric,special attack.,90}'
    and plain names (fallback):
      'nightmare' -> ('nightmare', mon.types[0] (later), 'special', 60)
    NOTE: Type fallback is handled in _coerce_move.
    """
    if "{" not in move_str or "}" not in move_str:
        return move_str.strip(), "", "special", None
    name, rest = move_str.split("{", 1)
    name = name.strip()
    inside = rest.strip().rstrip("}")
    parts = [p.strip() for p in inside.split(",")]
    mtype = parts[0] if parts else ""
    style_phrase = parts[1].lower() if len(parts) > 1 else "status"
    style = "physical" if "physical" in style_phrase else ("special" if "special" in style_phrase else "status")
    power = None
    if len(parts) > 2:
        try:
            power = int(parts[2])
        except Exception:
            power = None
    return name, mtype, style, power


def _coerce_move(mon: Dict, s: str) -> Tuple[str, str, str, int]:
    """Make sure we always have (name, type, style, power) for damage calc."""
    name, mtype, style, power = _parse_move(s)
    if not mtype:
        mtype = (mon.get("types") or ["normal"])[0]
    if style not in ("physical", "special", "status"):
        style = "special"
    if power is None:
        # Reasonable default if user team moves are names only
        power = 60 if style in ("physical", "special") else 0
    return name, mtype, style, int(power)


def _pick_damage_move(mon: Dict) -> Optional[Tuple[str, str, str, int]]:
    moves = list(mon.get("moves", []))
    random.shuffle(moves)
    for s in moves:
        name, mtype, style, power = _coerce_move(mon, s)
        if style in ("physical", "special") and power > 0:
            return (name, mtype, style, power)
    return None


def _calc_damage(attacker: Dict, defender: Dict, move: Tuple[str, str, str, int]) -> int:
    """Simple, fast damage model with STAB + RNG."""
    _name, mtype, style, power = move
    a = attacker.get("stats", {})
    d = defender.get("stats", {})
    atk = a.get("attack", 1)
    dfc = d.get("defense", 1)
    if style == "special":
        atk = a.get("special-attack", 1)
        dfc = d.get("special-defense", 1)

    stab = 1.5 if mtype in (attacker.get("types") or []) else 1.0
    rand = random.uniform(0.85, 1.0)
    spd_bonus = 1.05 if a.get("speed", 0) >= d.get("speed", 0) else 1.0
    dmg = (power * (atk / max(1, dfc)) * stab * rand * spd_bonus)
    return max(1, int(dmg))


def _battle_embed(
    title: str,
    player: Dict,
    p_cur: int,
    p_max: int,
    foe: Dict,
    f_cur: int,
    f_max: int,
    footer: Optional[str] = None,
) -> discord.Embed:
    e = discord.Embed(title=title, color=discord.Color.blurple())
    e.description = (
        f"**Duel —** {player['name'].title()} (Lv {player.get('level','?')}) vs {foe['name'].title()} (Lv {foe.get('level','?')})\n\n"
        f"**{player['name'].title()} HP:** {_hp_bar(p_cur, p_max)}  {p_cur}/{p_max}\n"
        f"**{foe['name'].title()} HP:** {_hp_bar(f_cur, f_max)}  {f_cur}/{f_max}\n"
    )
    ps = player.get("sprite")
    if ps:
        e.set_author(name=player["name"].title(), icon_url=ps)
    fs = foe.get("sprite")
    if fs:
        e.set_thumbnail(url=fs)
    if footer:
        e.set_footer(text=footer)
    return e


class BattleTowerView(discord.ui.View):
    """Interactive Battle Tower fight loop."""

    def __init__(self, ctx: commands.Context, player_team: List[Dict], foe: Dict, level_step: int = 5, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.cog: BattleTower = ctx.cog
        self.user_id = ctx.author.id
        self.level_step = level_step

        self.team: List[Dict] = copy.deepcopy(player_team)
        self.pi: int = 0  # party index
        self.player: Dict = self.team[self.pi]

        # Opponent
        self.foe = copy.deepcopy(foe)

        # Pools
        self.p_max = _init_hp(self.player)
        self.f_max = _init_hp(self.foe)
        self.p_cur = self.p_max
        self.f_cur = self.f_max

        self._arm_player_buttons()




    # --- inside BattleTowerView ---
    def _advance_next_player(self) -> bool:
        """
        Move to next party member if any remain. Returns True if switched,
        False if no more mons (team wiped).
        """
        self.pi += 1
        if self.pi >= len(self.team):
            return False
        self.player = self.team[self.pi]
        self.p_max = _init_hp(self.player)
        self.p_cur = self.p_max
        self._arm_player_buttons()
        return True


    def _arm_player_buttons(self):
        self.clear_items()

        # Add up to 4 damage moves (fallback to first 4 if needed)
        candidates = []
        for m in self.player.get("moves", [])[:4]:
            mv = _coerce_move(self.player, m)
            if mv[2] in ("physical", "special") and mv[3] > 0:
                candidates.append(mv)
        if not candidates:
            for m in self.player.get("moves", [])[:4]:
                candidates.append(_coerce_move(self.player, m))

        for idx, mv in enumerate(candidates[:4]):
            label = f"{mv[0].title()} ({mv[3]})"
            self.add_item(self.MoveButton(tower=self, label=label, move=mv, row=0 if idx < 3 else 1))

        self.add_item(self.AutoSimButton(tower=self))
        self.add_item(self.GiveUpButton(tower=self))

    class MoveButton(discord.ui.Button):
        def __init__(self, tower: "BattleTowerView", label: str, move: Tuple[str, str, str, int], row: int = 0):
            super().__init__(style=discord.ButtonStyle.primary, label=label, row=row)
            self.tower = tower
            self.move = move

        async def callback(self, interaction: discord.Interaction):
            await self.tower._turn(interaction, self.move, autosim=False)

    class AutoSimButton(discord.ui.Button):
        def __init__(self, tower: "BattleTowerView"):
            super().__init__(style=discord.ButtonStyle.secondary, label="⏩ Auto-Sim")
            self.tower = tower

        async def callback(self, interaction: discord.Interaction):
            mv = _pick_damage_move(self.tower.player) or _coerce_move(self.tower.player, (self.tower.player.get("moves") or ["tackle"])[0])
            await self.tower._turn(interaction, mv, autosim=True)

    class GiveUpButton(discord.ui.Button):
        def __init__(self, tower: "BattleTowerView"):
            super().__init__(style=discord.ButtonStyle.danger, label="Give Up")
            self.tower = tower

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.tower.user_id:
                return await interaction.response.send_message("This isn't your battle.", ephemeral=True)
            self.tower.clear_items()
            await self.tower.cog._reset_streak(self.tower.user_id)
            self.tower.add_item(self.tower.CloseButton())
            emb = _battle_embed(
                "You Gave Up — Battle Tower",
                self.tower.player, self.tower.p_cur, self.tower.p_max,
                self.tower.foe, self.tower.f_cur, self.tower.f_max,
                footer="Battle ended by player.",
            )
            await interaction.response.edit_message(embed=emb, view=self.tower)

    class RematchSame(discord.ui.Button):
        def __init__(self, tower: "BattleTowerView"):
            super().__init__(style=discord.ButtonStyle.success, label="🔁 Rematch (Same Level)")
            self.tower = tower

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.tower.user_id:
                return await interaction.response.send_message("This isn't your battle.", ephemeral=True)
            self.tower.f_cur = self.tower.f_max = _init_hp(self.tower.foe)
            self.tower._arm_player_buttons()
            emb = _battle_embed(
                "Team Battle — Battle Tower",
                self.tower.player, self.tower.p_cur, self.tower.p_max,
                self.tower.foe, self.tower.f_cur, self.tower.f_max,
                footer="Rematch started at the same level.",
            )
            await interaction.response.edit_message(embed=emb, view=self.tower)

    class RematchHigher(discord.ui.Button):
        def __init__(self, tower: "BattleTowerView"):
            super().__init__(style=discord.ButtonStyle.primary, label="⬆️ Challenge Higher Level")
            self.tower = tower

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.tower.user_id:
                return await interaction.response.send_message("This isn't your battle.", ephemeral=True)

            # Use the *cog's* scaler
            cog = self.tower.ctx.cog
            if hasattr(cog, "_tower_scale"):
                self.tower.foe = cog._tower_scale(self.tower.foe, self.tower.level_step)
            else:
                # Fallback growth
                s = self.tower.foe.get("stats", {})
                for _ in range(self.tower.level_step):
                    for k in s:
                        s[k] += random.choice([0, 1, 1, 2, 2, 3])
                self.tower.foe["stats"] = s
                self.tower.foe["level"] = self.tower.foe.get("level", 1) + self.tower.level_step

            self.tower.f_cur = self.tower.f_max = _init_hp(self.tower.foe)
            self.tower._arm_player_buttons()
            emb = _battle_embed(
                "Team Battle — Battle Tower",
                self.tower.player, self.tower.p_cur, self.tower.p_max,
                self.tower.foe, self.tower.f_cur, self.tower.f_max,
                footer=f"Challenging higher level foe (Lv {self.tower.foe.get('level','?')}).",
            )
            await interaction.response.edit_message(embed=emb, view=self.tower)

    class CloseButton(discord.ui.Button):
        def __init__(self):
            super().__init__(style=discord.ButtonStyle.secondary, label="Close")

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.edit_message(view=None)


    # ---------- Turn engine ----------
    async def _turn(self, interaction: discord.Interaction, move: Tuple[str, str, str, int], autosim: bool):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your battle.", ephemeral=True)

        # Player hits
        p_dmg = _calc_damage(self.player, self.foe, move)
        self.f_cur = max(0, self.f_cur - p_dmg)
        if self.f_cur <= 0:
            return await self._victory(interaction, move[0], p_dmg)

        # Foe counters
        foe_move = _pick_damage_move(self.foe) or ("tackle", "normal", "physical", 40)
        f_dmg = _calc_damage(self.foe, self.player, foe_move)
        self.p_cur = max(0, self.p_cur - f_dmg)

        if self.p_cur <= 0:
            # Try to send next party mon
            if self._advance_next_player():
                # Switched successfully: announce and continue
                footer = (
                    f"Your previous mon fainted. You sent out **{self.player['name'].title()}**!\n"
                    f"(Foe used {foe_move[0]} for {f_dmg} damage.)"
                )
                emb = _battle_embed(
                    "Team Battle — Battle Tower",
                    self.player, self.p_cur, self.p_max,
                    self.foe, self.f_cur, self.f_max,
                    footer,
                )
                return await interaction.response.edit_message(embed=emb, view=self)
            else:
                # No more team members: defeat
                return await self._defeat(interaction, foe_move[0], f_dmg)

        footer = f"You used {move[0]} ({p_dmg}). Foe used {foe_move[0]} ({f_dmg})."
        emb = _battle_embed("Team Battle — Battle Tower", self.player, self.p_cur, self.p_max, self.foe, self.f_cur, self.f_max, footer)
        await interaction.response.edit_message(embed=emb, view=self)

        if autosim:
            # Continue autosim with a random damaging move
            nmv = _pick_damage_move(self.player)
            if nmv:
                # Use followup to acknowledge, then immediately continue
                await interaction.followup.send("⏩ Auto-sim continues…", ephemeral=True)
                await self._turn(interaction, nmv, autosim=True)

    async def _victory(self, interaction: discord.Interaction, used: str, dealt: int):
        gcog = interaction.client.get_cog("GachaCatchEmAll")
        exp_txt = ""

        # Base EXP by BST diff + level factor
        player_bst = _bst(self.player)
        foe_bst = _bst(self.foe)
        lvl = int(self.foe.get("level", 1))
        diff = max(0, foe_bst - player_bst)
        base_exp = max(10, diff // 4 + lvl * 2)

        # --- Streak bonus ---
        # +10% per current streak, capped at +50%
        current_streak = await self.cog._get_streak(self.user_id)
        bonus_mult = min(1.0 + 0.10 * current_streak, 1.50)
        final_exp = int(round(base_exp * bonus_mult))
        # Increment streak for next battle
        new_streak = await self.cog._inc_streak(self.user_id)

        if gcog and hasattr(gcog, "_add_xp_to_entry") and hasattr(gcog, "_xp_bar"):
            before_lvl = int(self.player.get("level", 1))
            before_xp = int(self.player.get("xp", 0))
            new_lvl, new_xp, _ = gcog._add_xp_to_entry(self.player, final_exp)
            exp_txt = (
                f"**+{final_exp} EXP** (base {base_exp}, streak x{bonus_mult:.2f}; streak **{new_streak}**)"
                f" — Lv {before_lvl}→{new_lvl}  {_safe_xpbar(gcog, new_lvl, new_xp)}"
            )
        else:
            exp_txt = f"EXP awarded: {final_exp} (base {base_exp}, streak x{bonus_mult:.2f}; streak {new_streak})."

        # Swap to rematch controls
        self.clear_items()
        self.add_item(self.RematchSame(self))
        self.add_item(self.RematchHigher(self))
        self.add_item(self.CloseButton())
        footer = f"✅ Victory! Used {used} for {dealt} damage. {exp_txt}"
        emb = _battle_embed("Victory — Battle Tower", self.player, self.p_cur, self.p_max, self.foe, self.f_cur, self.f_max, footer)
        await interaction.response.edit_message(embed=emb, view=self)


    async def _defeat(self, interaction: discord.Interaction, foe_used: str, dealt: int):
        self.clear_items()
        self.add_item(self.CloseButton())
        await self.cog._reset_streak(self.user_id)
        footer = f"💀 Defeat. Foe used {foe_used} for {dealt} damage."
        emb = _battle_embed("Defeat — Battle Tower", self.player, self.p_cur, self.p_max, self.foe, self.f_cur, self.f_max, footer)
        await interaction.response.edit_message(embed=emb, view=self)


def _safe_xpbar(gcog, level: int, xp: int) -> str:
    try:
        return gcog._xp_bar(level, xp)
    except Exception:
        need = 100
        filled = int(round(10 * (xp / need))) if need else 0
        filled = max(0, min(10, filled))
        return "▰" * filled + "▱" * (10 - filled) + f"  {xp}/{need}"


class BattleTower(commands.Cog):
    """Endless Battle Tower that depends on GachaCatchEmAll helpers."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier="0xBATTLETOWER", force_registration=True)
        # per-user streak
        self.config.register_user(bt_streak=0)

    async def _get_streak(self, user_id: int) -> int:
        return await self.config.user_from_id(user_id).bt_streak()

    async def _set_streak(self, user_id: int, value: int) -> None:
        await self.config.user_from_id(user_id).bt_streak.set(value)

    async def _inc_streak(self, user_id: int) -> int:
        streak = await self._get_streak(user_id)
        streak += 1
        await self._set_streak(user_id, streak)
        return streak

    async def _reset_streak(self, user_id: int) -> None:
        await self._set_streak(user_id, 0)


    @commands.hybrid_command(name="battletower")
    async def battletower(self, ctx: commands.Context, level: int = 1, level_step: int = 5):
        """Fight an endlessly scaling NPC at the given level. Buttons = your moves."""
        await ctx.defer()

        gcog = self.bot.get_cog("GachaCatchEmAll")
        if not gcog:
            return await ctx.reply("GachaCatchEmAll cog not found. Please load it first.")

        # 1) Get full player team
        team = await gcog._get_user_team(ctx.author)
        if not team:
            return await ctx.reply("You don't have a team set up.")

        # Deep-copy + ensure required keys exist for EVERY mon in the party
        player_team = copy.deepcopy(team)
        for mon in player_team:
            mon.setdefault("level", mon.get("level", 1))
            mon.setdefault("xp", mon.get("xp", 0))
            mon.setdefault("moves", mon.get("moves", ["tackle"]))
            mon.setdefault("types", mon.get("types", ["normal"]))

        # 2) Get/scale single NPC
        npc_list = await gcog._generate_npc_team(1, 1)
        foe = copy.deepcopy(npc_list[0] if isinstance(npc_list, list) else npc_list)
        foe.setdefault("level", foe.get("level", 1))
        start_lv = int(foe["level"])
        if level > start_lv:
            foe = self._tower_scale(foe, level - start_lv)

        # 3) Send interactive view (pass the WHOLE party)
        view = BattleTowerView(ctx, player_team=player_team, foe=foe, level_step=level_step)

        pmax = _init_hp(player_team[0])  # first active mon
        fmax = _init_hp(foe)
        emb = _battle_embed(
            "Team Battle — Battle Tower",
            player_team[0], pmax, pmax,
            foe, fmax, fmax,
            footer="Choose a move, ⏩ Auto-Sim, or Give Up.",
        )
        await ctx.send(embed=emb, view=view)

    
    @staticmethod
    def _recalc_bst(stats: Dict[str, int]) -> int:
        """Recalculate BST from standard keys (missing keys count as 0)."""
        keys = ("hp", "attack", "defense", "special-attack", "special-defense", "speed")
        return sum(int(stats.get(k, 0)) for k in keys)

    def _tower_scale(
        self,
        target: Union[Dict, List[Dict]],
        levels: int,
        *,
        copy_input: bool = True,
        seed: Optional[int] = None,
        update_bst: bool = True,
    ) -> Union[Dict, List[Dict]]:
        """
        Scale a mon (or list of mons) upward by `levels`.
        - Each level adds a random choice from [0,1,1,2,2,3] to EACH stat.
        - Increments 'level' by `levels`.
        - If update_bst=True and a 'bst' field exists, it will be refreshed.

        Returns: same shape (dict or list) as provided.
        """
        if seed is not None:
            random.seed(seed)

        if levels <= 0:
            return copy.deepcopy(target) if copy_input else target

        growth_choices = [0, 1, 1, 2, 2, 3]

        def scale_one(mon: Dict) -> Dict:
            b = copy.deepcopy(mon) if copy_input else mon
            stats = b.get("stats")
            if not isinstance(stats, dict):
                # Nothing to scale if stats are missing/invalid
                b["level"] = int(b.get("level", 1)) + levels
                return b

            # Add weighted growth to each stat for each level
            for _ in range(levels):
                for k, v in list(stats.items()):
                    try:
                        stats[k] = int(v) + random.choice(growth_choices)
                    except Exception:
                        # If a stat isn't numeric, leave it as-is
                        pass

            b["stats"] = stats
            b["level"] = int(b.get("level", 1)) + levels

            if update_bst and "bst" in b:
                b["bst"] = self._recalc_bst(stats)

            return b

        if isinstance(target, list):
            return [scale_one(m) for m in target]
        if isinstance(target, dict):
            return scale_one(target)
        raise TypeError(f"_tower_scale expected dict or list[dict], got {type(target)!r}")


async def setup(bot):
    await bot.add_cog(BattleTower(bot))
