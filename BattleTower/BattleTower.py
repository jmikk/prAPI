# battle_tower.py
import copy
import random
from typing import Dict, List, Optional, Tuple, Union

import discord
from redbot.core import commands, Config

import asyncio  # top of file

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

        # run/session stats
        self.current_floor: int = getattr(self, "current_floor", 1)  # will be set by command
        self.wins_since_floor_up: int = getattr(self, "wins_since_floor_up", 0)
        self.total_wins: int = getattr(self, "total_wins", 0)
        self.turns: int = 0
        self.total_damage_dealt: int = 0
        self.total_damage_taken: int = 0
        self.moves_used: Dict[str, int] = {}

        self.autosim_running = False




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

    def _green_xp_bar(self, gcog, level: int, xp: int) -> str:
        """🟩/⬛ 10-slot bar with numeric xp/need, using the main cog's _xp_needed if available."""
        need = 0
        if hasattr(gcog, "_xp_needed"):
            try:
                need = int(gcog._xp_needed(level))
            except Exception:
                need = 100
        else:
            need = 100

        need = max(1, need)
        filled = int(round(10 * (xp / need)))
        filled = max(0, min(10, filled))
        return "▰" * filled + "▱" * (10 - filled) + f"  {xp}/{need}"



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
            if interaction.user.id != self.tower.user_id:
                return await interaction.response.defer(ephemeral=True)  # silent reject

            # Toggle autosim without sending messages
            self.tower.autosim_running = not self.tower.autosim_running
            await interaction.response.defer()  # ACK with no new message

            if self.tower.autosim_running:
                await self.tower._autosim_loop(interaction)


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

            desired = int(self.tower.foe.get("level", 1))
            self.tower.foe = await self.tower._fetch_new_foe(desired)

            # Reset foe HP and refresh UI
            self.tower.f_cur = self.tower.f_max = _init_hp(self.tower.foe)
            self.tower._arm_player_buttons()
            emb = _battle_embed(
                "Team Battle — Battle Tower",
                self.tower.player, self.tower.p_cur, self.tower.p_max,
                self.tower.foe, self.tower.f_cur, self.tower.f_max,
                footer=f"Rematch at Lv {desired} — new opponent!",
            )
            await interaction.response.edit_message(embed=emb, view=self.tower)


    class CloseButton(discord.ui.Button):
        def __init__(self):
            super().__init__(style=discord.ButtonStyle.secondary, label="Close")

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.edit_message(view=None)

    async def _fetch_new_foe(self, desired_level: int) -> Dict:
        """
        Ask the main cog for a fresh NPC, ensure it's a different species than the current foe,
        and scale it up to desired_level.
        """
        gcog = self.ctx.bot.get_cog("GachaCatchEmAll")
        if not gcog:
            return self.foe  # fallback

        old_id = self.foe.get("pokedex_id") or self.foe.get("name")
        candidate = None

        # Try a few times to get a different species
        for _ in range(10):
            npc_list = await gcog._generate_npc_team(1, 1)
            cand = copy.deepcopy(npc_list[0] if isinstance(npc_list, list) else npc_list)
            new_id = cand.get("pokedex_id") or cand.get("name")
            if new_id != old_id:
                candidate = cand
                break
            candidate = cand  # keep last as fallback

        # Scale to desired level
        base_lv = int(candidate.get("level", 1))
        diff = max(0, desired_level - base_lv)
        if diff and hasattr(self.cog, "_tower_scale"):
            candidate = self.cog._tower_scale(candidate, diff)
        candidate.setdefault("level", desired_level)
        return candidate

    async def _autosim_loop(self, interaction: discord.Interaction):
        while self.autosim_running and self.f_cur > 0 and self.p_cur > 0:
            mv = _pick_damage_move(self.player) or _coerce_move(self.player, (self.player.get("moves") or ["tackle"])[0])
            await self._turn(interaction, mv, autosim=True)
            await asyncio.sleep(2)
            # If foe fainted, _victory will prep next foe; just continue loop naturally
        # No end message — we quietly stop





    async def _turn(self, interaction: discord.Interaction, move: Tuple[str, str, str, int], autosim: bool):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your battle.", ephemeral=True)

        # Ensure run counters exist (in case they weren't set in __init__)
        self.total_damage_dealt = getattr(self, "total_damage_dealt", 0)
        self.total_damage_taken = getattr(self, "total_damage_taken", 0)
        self.turns = getattr(self, "turns", 0)
        self.moves_used = getattr(self, "moves_used", {})

        # --- Player hits ---
        p_dmg = _calc_damage(self.player, self.foe, move)
        self.f_cur = max(0, self.f_cur - p_dmg)
        # record immediately to avoid UnboundLocalError on early returns
        self.total_damage_dealt += p_dmg
        self.moves_used[move[0]] = self.moves_used.get(move[0], 0) + 1

        if self.f_cur <= 0:
            # Count the turn when the foe is KO'd before their action
            self.turns += 1
            return await self._victory(interaction, move[0], p_dmg)

        # --- Foe counters ---
        foe_move = _pick_damage_move(self.foe) or ("tackle", "normal", "physical", 40)
        f_dmg = _calc_damage(self.foe, self.player, foe_move)
        self.p_cur = max(0, self.p_cur - f_dmg)
        self.total_damage_taken += f_dmg

        # Full round completed
        self.turns += 1

        if self.p_cur <= 0:
            # Try to send next party mon
            if self._advance_next_player():
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
                return await self._safe_edit(interaction, embed=emb, view=self)
            else:
                return await self._defeat(interaction, foe_used=foe_move[0], dealt=f_dmg)

        footer = f"You used {move[0]} ({p_dmg}). Foe used {foe_move[0]} ({f_dmg})."
        emb = _battle_embed(
            "Team Battle — Battle Tower",
            self.player, self.p_cur, self.p_max,
            self.foe, self.f_cur, self.f_max,
            footer,
        )
        await self._safe_edit(interaction, embed=emb, view=self)

        if autosim:
            nmv = _pick_damage_move(self.player) or move
            await self._turn(interaction, nmv, autosim=True)


        footer = f"You used {move[0]} ({p_dmg}). Foe used {foe_move[0]} ({f_dmg})."
        emb = _battle_embed("Team Battle — Battle Tower", self.player, self.p_cur, self.p_max, self.foe, self.f_cur, self.f_max, footer)
        await self._safe_edit(interaction, embed=emb, view=self)

        if autosim:
            # Continue autosim with a random damaging move
            nmv = _pick_damage_move(self.player)
            if nmv:
                # Use followup to acknowledge, then immediately continue
                await self._turn(interaction, nmv, autosim=True)

    async def _victory(self, interaction: discord.Interaction, used: str, dealt: int):
        gcog = interaction.client.get_cog("GachaCatchEmAll")

        # Base EXP by BST diff + level factor
        player_bst = _bst(self.player)
        foe_bst = _bst(self.foe)
        lvl = int(self.foe.get("level", 1))
        diff = max(0, foe_bst - player_bst)
        base_exp = max(10, diff // 4 + lvl * 2)

        # Streak bonus
        current_streak = await self.cog._get_streak(self.user_id)
        bonus_mult = min(1.0 + 0.10 * current_streak, 1.50)
        final_exp = int(round(base_exp * bonus_mult))
        new_streak = await self.cog._inc_streak(self.user_id)

        # Grant EXP to entire party
        lines = []
        if gcog and hasattr(gcog, "_add_xp_to_entry") and hasattr(gcog, "_xp_bar"):
            for mon in self.team:
                before_lvl = int(mon.get("level", 1))
                before_xp = int(mon.get("xp", 0))
                new_lvl, new_xp, _ = gcog._add_xp_to_entry(mon, final_exp)
                # green bar + “arrow only if leveled up”
                lvl_text = f"Lv {before_lvl} → {new_lvl}" if new_lvl > before_lvl else f"Lv {new_lvl}"
                bar = self._green_xp_bar(gcog, new_lvl, new_xp)
                lines.append(f"**{mon['name'].title()}** — {lvl_text}  {bar}")
            # persist back to user’s box by UID (see previous message for helper)
            if hasattr(gcog, "_apply_exp_bulk"):
                updates = [(mon["uid"], mon["level"], mon["xp"]) for mon in self.team if "uid" in mon]
                await gcog._apply_exp_bulk(self.ctx.author, updates)
        else:
            for mon in self.team:
                lines.append(f"**{mon.get('name','?').title()}** +{final_exp} EXP")

        self.total_wins += 1
        self.wins_since_floor_up += 1
        floor_msg = ""
        if self.wins_since_floor_up >= 10:
            self.wins_since_floor_up = 0
            self.current_floor += 1

            # New foe at higher level (different species)
            desired = int(self.foe.get("level", 1)) + self.level_step
            self.foe = await self._fetch_new_foe(desired)

            # reset foe HP for next fight
            self.f_cur = self.f_max = _init_hp(self.foe)
            floor_msg = f"\n\n⬆️ **Floor Up!** You’ve reached **Floor {self.current_floor}**."

            # update highest floor in storage
            await self.cog._set_highest_floor(self.user_id, self.current_floor)

        # Summary embed (victory)
        self.clear_items()
        self.add_item(self.RematchSame(self))
        self.add_item(self.CloseButton())

        summary = discord.Embed(title=f"🏆 Victory — Team EXP (Floor {self.current_floor})", color=discord.Color.green())
        summary.description = (
            f"Used **{used}** for **{dealt}** damage."
            f"{floor_msg}\n\n" +
            "\n".join(lines)
        )
        summary.set_footer(text=f"+{final_exp} EXP to each (base {base_exp}, streak x{bonus_mult:.2f}; current streak {new_streak})")
        
        # First, show the victory summary on the SAME message
        await self._safe_edit(interaction, embed=summary, view=self)

        # If autosim is running, wait a moment then replace the SAME message with next battle
        if self.autosim_running:
            await asyncio.sleep(1.5)
            desired = int(self.foe.get("level", 1))
            self.foe = await self._fetch_new_foe(desired)
            self.f_cur = self.f_max = _init_hp(self.foe)
            emb = _battle_embed(
                "Team Battle — Battle Tower (AutoSim)",
                self.player, self.p_cur, self.p_max,
                self.foe, self.f_cur, self.f_max,
                footer=f"AutoSim continues... Lv {desired} opponent.",
            )
            await self._safe_edit(interaction, embed=emb, view=self)
            # Resume loop
            await self._autosim_loop(interaction)
            return

        await self._safe_edit(interaction, embed=summary, view=self)

    async def _safe_edit(self, interaction: discord.Interaction, *, embed: discord.Embed, view: Optional[discord.ui.View] = None):
        """
        Edit the one original message for this view. Never sends new messages.
        """
        # Best: we stored the original message in the command
        if getattr(self, "message", None):
            await self.message.edit(embed=embed, view=view)
            return

        # Fallbacks if message wasn't stored for some reason
        try:
            if interaction.response.is_done():
                # For component interactions, edit the message the component belongs to
                if hasattr(interaction, "message") and interaction.message:
                    await interaction.message.edit(embed=embed, view=view)
                else:
                    await interaction.edit_original_response(embed=embed, view=view)
            else:
                await interaction.response.edit_message(embed=embed, view=view)
        except Exception:
            # Final fallback: try editing the component's message
            if hasattr(interaction, "message") and interaction.message:
                await interaction.message.edit(embed=embed, view=view)







    async def _defeat(self, interaction: discord.Interaction, foe_used: str, dealt: int):
        # reset streak
        await self.cog._reset_streak(self.user_id)

        # defeat summary
        mlist = ", ".join(f"{k}×{v}" for k, v in self.moves_used.items()) or "—"
        desc = (
            f"**Floor Reached:** {self.current_floor}\n"
            f"**Foes Defeated This Run:** {self.total_wins}\n"
            f"**Turns Taken:** {self.turns}\n"
            f"**Total Damage Dealt:** {self.total_damage_dealt}\n"
            f"**Total Damage Taken:** {self.total_damage_taken}\n"
            f"**Last Blow:** Foe used **{foe_used}** ({dealt})\n"
            f"**Moves Used:** {mlist}"
        )

        self.clear_items()
        self.add_item(self.CloseButton())

        emb = discord.Embed(title="💀 Defeat — Run Summary", description=desc, color=discord.Color.red())
        await self._safe_edit(interaction, embed=emb, view=self)



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
        self.config.register_user(bt_streak=0, bt_highest_floor=1)  # add bt_highest_floor

        # add helpers in BattleTower class
    async def _get_highest_floor(self, user_id: int) -> int:
        return await self.config.user_from_id(user_id).bt_highest_floor()

    async def _set_highest_floor(self, user_id: int, floor: int) -> None:
        cur = await self._get_highest_floor(user_id)
        if floor > cur:
            await self.config.user_from_id(user_id).bt_highest_floor.set(int(floor))

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
    async def battletower(self, ctx: commands.Context, floor: int = 1):
        """Fight an endlessly scaling NPC at the given level. Buttons = your moves."""
        level = floor
        level_step: int = 1
        await ctx.defer()

        await self._reset_streak(ctx.author.id)


        # Highest floor gate
        highest = await self._get_highest_floor(ctx.author.id)  # default 1
        start_floor = highest if floor is None else min(highest, max(1, int(floor)))
        if floor is not None and start_floor != floor:
            await ctx.send(f"You can only start on your highest unlocked floor. Your highest **Floor {start_floor}**.", ephemeral=True)
            return
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
        msg = await ctx.send(embed=emb, view=view)
        view.message = msg  # <— IMPORTANT: store original message

    
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
