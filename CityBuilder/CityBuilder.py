# citybuilder_buttons.py
import asyncio
import math
from typing import Dict, Optional, Tuple, Callable
import io
import aiohttp
import discord
from discord import ui
from redbot.core import commands, Config

# ====== Balance knobs ======
BUILDINGS: Dict[str, Dict] = {
    "farm":    {"cost": 100.0, "upkeep": 2.0, "produces": {"food": 5}},   # per building per tick (WC)
    "mine":    {"cost": 200.0, "upkeep": 3.0, "produces": {"metal": 2}},
    "factory": {"cost": 500.0, "upkeep": 5.0, "produces": {"goods": 1}},
}

TICK_SECONDS = 3600  # hourly ticks

# ====== NationStates config ======
NS_USER_AGENT = "9005"
NS_BASE = "https://www.nationstates.net/cgi-bin/api.cgi"

# Default composite: 46 + a few companions (tweak freely)
DEFAULT_SCALES = [46, 1, 10, 39]

# ====== Utility ======
def trunc2(x: float) -> float:
    """Truncate (not round) to 2 decimals to match wallet behavior."""
    return math.trunc(float(x) * 100) / 100.0

def normalize_nation(n: str) -> str:
    return n.strip().lower().replace(" ", "_")

def _xml_get_tag(txt: str, tag: str) -> Optional[str]:
    start = txt.find(f"<{tag}>")
    if start == -1:
        return None
    end = txt.find(f"</{tag}>", start)
    if end == -1:
        return None
    return txt[start + len(tag) + 2 : end].strip()

def _xml_has_nation_block(xml: str) -> bool:
    """Very light validation that the response actually contains a <NATION>…</NATION> block and no <ERROR>."""
    if not isinstance(xml, str) or not xml:
        return False
    up = xml.upper()
    return ("<NATION" in up and "</NATION>" in up) and ("<ERROR>" not in up)


def _xml_get_scales_scores(xml: str) -> dict:
    """
    Extract all <SCALE id="X"><SCORE>Y</SCORE>… and return {id: float(score)}.
    Handles scientific notation.
    """
    out = {}
    pos = 0
    while True:
        sid = xml.find("<SCALE", pos)
        if sid == -1:
            break
        e = xml.find(">", sid)
        if e == -1:
            break
        head = xml[sid : e + 1]  # e.g., <SCALE id="76">
        # id="..."
        scale_id = None
        idpos = head.find('id="')
        if idpos != -1:
            idend = head.find('"', idpos + 4)
            if idend != -1:
                try:
                    scale_id = int(head[idpos + 4 : idend])
                except Exception:
                    scale_id = None

        # SCORE
        sc_start = xml.find("<SCORE>", e)
        sc_end = xml.find("</SCORE>", sc_start)
        if sc_start != -1 and sc_end != -1:
            raw = xml[sc_start + 7 : sc_end].strip()
            try:
                score = float(raw)
            except Exception:
                score = None
            if scale_id is not None and score is not None:
                out[scale_id] = score

        pos = sc_end if sc_end != -1 else e + 1
    return out


async def ns_fetch_currency_and_scales(nation_name: str, scales: Optional[list] = None) -> Tuple[str, dict, str]:
    """
    Robust fetch:
      1) q=currency+census with mode/scale as separate params
      2) q=currency+census;mode=score;scale=...
      3) Fallback: q=currency  AND  q=census;mode=score;scale=... (two requests)
    Returns: (currency_text, {scale_id: score, ...}, xml_text)
    """
    nation = normalize_nation(nation_name)
    scales = scales or DEFAULT_SCALES
    scale_str = "+".join(str(s) for s in scales)
    headers = {"User-Agent": NS_USER_AGENT}

    async def fetch(params: dict) -> str:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(NS_BASE, params=params) as resp:
                # gentle pacing
                remaining = resp.headers.get("Ratelimit-Remaining")
                reset_time = resp.headers.get("Ratelimit-Reset")
                if remaining is not None and reset_time is not None:
                    try:
                        remaining_i = max(1, int(remaining) - 10)
                        reset_i = int(reset_time)
                        wait = reset_i / remaining_i if remaining_i > 0 else reset_i
                        await asyncio.sleep(wait)
                    except Exception:
                        pass
                return await resp.text()

    # --- Try #1: separate params for mode/scale ---
    params1 = {"nation": nation, "q": "currency+census", "mode": "score", "scale": scale_str}
    text1 = await fetch(params1)
    currency1 = _xml_get_tag(text1, "CURRENCY") or "Credits"
    scores1 = _xml_get_scales_scores(text1)
    if scores1:  # got census
        return currency1, scores1, text1

    # --- Try #2: combined in q= string (your original format) ---
    params2 = {"nation": nation, "q": f"currency+census;mode=score;scale={scale_str}"}
    text2 = await fetch(params2)
    currency2 = _xml_get_tag(text2, "CURRENCY") or currency1
    scores2 = _xml_get_scales_scores(text2)
    if scores2:
        return currency2, scores2, text2

    # --- Try #3: split requests (currency, then census only) ---
    text_cur = await fetch({"nation": nation, "q": "currency"})
    text_cen = await fetch({"nation": nation, "q": "census", "mode": "score", "scale": scale_str})
    currency3 = _xml_get_tag(text_cur, "CURRENCY") or "Credits"
    scores3 = _xml_get_scales_scores(text_cen)

    # Build a combined debug blob so you can see both raw payloads
    combined_xml = f"<!-- CURRENCY -->\n{text_cur}\n\n<!-- CENSUS -->\n{text_cen}"
    return currency3, scores3, combined_xml



# ====== Currency strength composite → exchange rate ======
def _softlog(x: float) -> float:
    return math.log10(max(0.0, float(x)) + 1.0)

def _norm(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.5
    v = max(lo, min(hi, v))
    return (v - lo) / (hi - lo)

def _invert(p: float) -> float:
    return 1.0 - p

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _make_transforms() -> dict:
    return {
        46: lambda x: _norm(_softlog(x), 0.0, 6.0),   # huge ranges → log then 0..6
        1:  lambda x: _norm(x, 0.0, 100.0),           # Economy
        10: lambda x: _norm(x, 0.0, 100.0),           # Industry
        39: lambda x: _invert(_norm(x, 0.0, 20.0)),   # Unemployment (invert)
    }

def _make_weights() -> dict:
    return {46: 0.5, 1: 0.3, 10: 0.15, 39: 0.5}

def _weighted_avg(scores: dict, weights: dict, transforms: dict) -> float:
    num = 0.0
    den = 0.0
    for k, w in weights.items():
        if k in scores:
            v = scores[k]
            t = transforms.get(k)
            if t:
                v = t(v)
            num += w * v
            den += abs(w)
    return num / den if den else 0.5

def _map_index_to_rate(idx: float) -> float:
    """
    idx in [0,1] → rate range [0.25, 2.00] with 0.5 ≈ 1.0x.
    """
    centered = (idx - 0.5) * 2.0  # [-1, 1]
    factor = 1.0 + 0.75 * centered  # 0.25..1.75
    return _clamp(trunc2(factor), 0.25, 10.00)

def compute_currency_rate(scores: dict) -> Tuple[float, dict]:
    scores_cast = {}
    for k, v in (scores or {}).items():
        try:
            scores_cast[int(k)] = float(v)
        except (TypeError, ValueError):
            continue

    transforms = _make_transforms()
    weights = _make_weights()
    idx = _weighted_avg(scores_cast, weights, transforms)
    rate = _map_index_to_rate(idx)
    contribs = {str(k): (transforms[k](scores_cast[k]) if k in scores_cast else None) for k in transforms}
    debug = {
        "scores": {str(k): scores_cast[k] for k in scores_cast},
        "contribs": contribs,
        "index": idx,
        "rate": rate,
        "weights": {str(k): float(weights[k]) for k in weights},
    }
    return rate, debug


# ====== Modals: Bank deposit/withdraw (wallet WC <-> bank WC here) ======
class DepositModal(discord.ui.Modal, title="🏦 Deposit Wellcoins"):
    def __init__(self, cog: "CityBuilder", max_wc: Optional[float] = None):
        super().__init__()
        self.cog = cog
        self.max_wc = trunc2(max_wc or 0.0)

        # Build the input dynamically so we can customize label/placeholder
        label = f"Amount to deposit (max {self.max_wc:.2f} WC)" if max_wc is not None else "Amount to deposit (in WC)"
        placeholder = f"{self.max_wc:.2f}" if max_wc is not None else "e.g. 100.50"

        self.amount = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt_wc = trunc2(float(self.amount.value))
        except ValueError:
            return await interaction.response.send_message("❌ That’s not a number.", ephemeral=True)
        if amt_wc <= 0:
            return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)

        nexus = self.cog.bot.get_cog("NexusExchange")
        if not nexus:
            return await interaction.response.send_message("⚠️ NexusExchange not loaded.", ephemeral=True)

        # Take WC from wallet (this will error if over max; we still show max for UX)
        try:
            await nexus.take_wellcoins(interaction.user, amt_wc, force=False)
        except ValueError:
            return await interaction.response.send_message("❌ Not enough Wellcoins in your wallet.", ephemeral=True)

        # Credit bank in local currency
        local_credit = await self.cog._wc_to_local(interaction.user, amt_wc)
        bank_local = trunc2(float(await self.cog.config.user(interaction.user).bank()) + local_credit)
        await self.cog.config.user(interaction.user).bank.set(bank_local)

        _, cur = await self.cog._get_rate_currency(interaction.user)
        await interaction.response.send_message(
            f"✅ Deposited {amt_wc:.2f} WC → **{local_credit:.2f} {cur}**. New bank: **{bank_local:.2f} {cur}**",
            ephemeral=True
        )



class WithdrawModal(discord.ui.Modal, title="🏦 Withdraw Wellcoins"):
    amount = discord.ui.TextInput(label="Wellcoins to withdraw (WC)", placeholder="e.g. 50", required=True)

    def __init__(self, cog: "CityBuilder"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt_wc = trunc2(float(self.amount.value))
        except ValueError:
            return await interaction.response.send_message("❌ That’s not a number.", ephemeral=True)
        if amt_wc <= 0:
            return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
    
        # Local required for this many WC
        local_needed = await self.cog._wc_to_local(interaction.user, amt_wc)
        bank_local = trunc2(float(await self.cog.config.user(interaction.user).bank()))
        if bank_local + 1e-9 < local_needed:
            _, cur = await self.cog._get_rate_currency(interaction.user)
            return await interaction.response.send_message(
                f"❌ Not enough in bank. Need **{local_needed:.2f} {cur}**.",
                ephemeral=True
            )
    
        # Deduct local from bank
        bank_local = trunc2(bank_local - local_needed)
        await self.cog.config.user(interaction.user).bank.set(bank_local)
    
        # Credit wallet WC
        nexus = self.cog.bot.get_cog("NexusExchange")
        if not nexus:
            return await interaction.response.send_message("⚠️ NexusExchange not loaded.", ephemeral=True)
    
        await nexus.add_wellcoins(interaction.user, amt_wc)
        _, cur = await self.cog._get_rate_currency(interaction.user)
        await interaction.response.send_message(
            f"✅ Withdrew **{local_needed:.2f} {cur}** → {amt_wc:.2f} WC. New bank: **{bank_local:.2f} {cur}**",
            ephemeral=True
        )


# ====== Setup: Prompt+Modal ======
class SetupPromptView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User):
        super().__init__(timeout=120)
        self.cog = cog
        self.author = author
        self.add_item(OpenSetupBtn())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This setup isn’t for you. Use `$city` to open your own.", ephemeral=True)
            return False
        return True

class OpenSetupBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Start City Setup", style=discord.ButtonStyle.primary, custom_id="city:setup")

    async def callback(self, interaction: discord.Interaction):
        view: SetupPromptView = self.view  # type: ignore
        await interaction.response.send_modal(SetupNationModal(view.cog))

class SetupNationModal(discord.ui.Modal, title="🌍 Link Your NationStates Nation"):
    nation = discord.ui.TextInput(label="Main nation name", placeholder="e.g., testlandia", required=True)

    def __init__(self, cog: "CityBuilder"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        nation_input = str(self.nation.value).strip()

        # Fetch currency + census (returns raw XML as 3rd value)
        try:
            currency, scores, xml_text = await ns_fetch_currency_and_scales(nation_input, DEFAULT_SCALES)
        except Exception as e:
            return await interaction.response.send_message(
                f"❌ Failed to reach NationStates API.\n`{e}`", ephemeral=True
            )

        # ===== NEW: existence check =====
        if not _xml_has_nation_block(xml_text):
            return await interaction.response.send_message(
                "❌ I couldn’t find that nation. Double-check the spelling (use your nation’s **main** name, "
                "no BBCode/links) and try again.",
                ephemeral=True,
            )
        # =================================

        # Compute & save
        rate, details = compute_currency_rate(scores)

        await self.cog.config.user(interaction.user).ns_nation.set(normalize_nation(nation_input))
        await self.cog.config.user(interaction.user).ns_currency.set(currency)
        await self.cog.config.user(interaction.user).set_raw("ns_scores", value={str(k): float(v) for k, v in scores.items()})
        await self.cog.config.user(interaction.user).wc_to_local_rate.set(rate)
        await self.cog.config.user(interaction.user).set_raw("rate_debug", value=details)
        await self.cog.config.user(interaction.user).set_raw("ns_last_xml", value=xml_text)  # keep for debugging

        # Show main panel
        embed = await self.cog.make_city_embed(interaction.user, header=f"✅ Linked to **{nation_input}**.")
        view = CityMenuView(self.cog, interaction.user, show_admin=self.cog._is_adminish(interaction.user))
        await interaction.response.send_message(embed=embed, view=view)


# ====== Cog ======
class CityBuilder(commands.Cog):
    """
    City planning mini-game using embeds + buttons.
    Entry: traditional Red command: $city
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        self.config.register_user(
            resources={},      # {"food": 0, "metal": 0, ...}
            buildings={},      # {"farm": {"count": int}, ...}
            bank=0.0,          # Wellcoins reserved for upkeep/wages (WC)
            ns_nation=None,    # normalized nation
            ns_currency=None,  # e.g. "Kro-bro-ünze"
            ns_scores={},      # {scale_id: score}
            wc_to_local_rate=None,  # float (optional if you later use local currency banking)
            rate_debug={},     # optional for debugging
        )
        self.task = bot.loop.create_task(self.resource_tick())

    async def _get_wallet_wc(self, user: discord.abc.User) -> float:
        """Best-effort to read user's wallet WellCoins from NexusExchange."""
        nexus = self.bot.get_cog("NexusExchange")
        if not nexus:
            return 0.0
    
        # Try common method names first
        for name in ("get_wellcoins", "get_balance", "balance_of", "get_wallet"):
            fn = getattr(nexus, name, None)
            if fn:
                try:
                    val = await fn(user)  # async method
                except TypeError:
                    try:
                        val = fn(user)      # sync method
                    except Exception:
                        continue
                try:
                    return trunc2(float(val))
                except Exception:
                    return 0.0
    
        # Last-ditch: read from a likely config path if it exists
        try:
            return trunc2(float(await nexus.config.user(user).wallet()))
        except Exception:
            return 0.0

    async def bank_help_embed(self, user: discord.abc.User) -> discord.Embed:
        bank_local = trunc2(float(await self.config.user(user).bank()))
        _, cur = await self._get_rate_currency(user)
        e = discord.Embed(
            title="🏦 Bank",
            description="Your **Bank** pays wages/upkeep each tick in your **local currency**. "
                        "If the bank can’t cover upkeep, **production halts**."
        )
        e.add_field(name="Current Balance", value=f"**{bank_local:.2f} {cur}**", inline=False)
        e.add_field(
            name="Tips",
            value="• Deposit: wallet **WC → local** bank\n"
                  "• Withdraw: bank **local → WC** wallet\n",
            inline=False,
        )
        return e


    # --- FX helpers ---
    async def _get_rate_currency(self, user: discord.abc.User) -> tuple[float, str]:
        d = await self.config.user(user).all()
        rate = float(d.get("wc_to_local_rate") or 1.0)
        currency = d.get("ns_currency") or "Local"
        return rate, currency
    
    async def _wc_to_local(self, user: discord.abc.User, wc_amount: float) -> float:
        rate, _ = await self._get_rate_currency(user)
        return trunc2(trunc2(wc_amount) * rate)


    @commands.guild_only()
    @commands.command(name="cityfxresync")
    async def city_fx_resync(self, ctx: commands.Context, nation: Optional[str] = None):
        """
        Re-fetch your NationStates currency & census scales, recompute the FX rate,
        cache the raw XML, and POST the XML here as a file. You can optionally override the nation name.
        """
        user = ctx.author
        d = await self.config.user(user).all()
        target_nation = nation or d.get("ns_nation")
        if not target_nation:
            return await ctx.send("❌ No nation linked yet. Run `$city` and complete setup first.")
    
        try:
            currency, scores, xml_text = await ns_fetch_currency_and_scales(target_nation, DEFAULT_SCALES)
            rate, details = compute_currency_rate(scores)
        except Exception as e:
            return await ctx.send(f"❌ Failed to fetch from NationStates.\n`{e}`")
    
        # Save everything
        await self.config.user(user).ns_currency.set(currency)
        await self.config.user(user).set_raw("ns_scores", value={str(k): float(v) for k, v in scores.items()})
        await self.config.user(user).wc_to_local_rate.set(rate)
        await self.config.user(user).set_raw("rate_debug", value=details)
        await self.config.user(user).set_raw("ns_last_xml", value=xml_text)
    
        # Send XML file in-channel
        filename = f"ns_{normalize_nation(target_nation)}_census.xml"
        filebuf = io.BytesIO(xml_text.encode("utf-8"))
        file = discord.File(filebuf, filename=filename)
        await ctx.send(
            content=f"📄 XML for **{target_nation}** · recalculated: `1 WC = {float(rate):.2f} {currency}`",
            file=file
        )



    # ---- helpers ----
    async def _reset_user(self, user: discord.abc.User, *, hard: bool):
        # Game progress
        await self.config.user(user).resources.set({})
        await self.config.user(user).buildings.set({})
        await self.config.user(user).bank.set(0.0)
    
        if hard:
            # NS linkage & FX
            await self.config.user(user).ns_nation.set(None)
            await self.config.user(user).ns_currency.set(None)
            await self.config.user(user).set_raw("ns_scores", value={})
            await self.config.user(user).wc_to_local_rate.set(None)
            await self.config.user(user).set_raw("rate_debug", value={})
    
    @commands.guild_only()
    @commands.command(name="cityreset")
    async def city_reset(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """
        Soft reset a city (keeps NationStates link & exchange rate).
        Use with no member to reset yourself; Manage Server needed to reset others.
        """
        target = member or ctx.author
        if target.id != ctx.author.id and not self._is_adminish(ctx.author):
            return await ctx.send("❌ You need **Manage Server** to reset other players.")
        await self._reset_user(target, hard=False)
        who = "your" if target.id == ctx.author.id else f"{target.display_name}'s"
        await ctx.send(f"🔄 Soft reset complete — {who} city progress was cleared (NS link kept).")
    
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(name="cityresethard")
    async def city_reset_hard(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """
        HARD reset a city (also clears NationStates link & exchange rate).
        Manage Server or Admin required.
        """
        target = member or ctx.author
        await self._reset_user(target, hard=True)
        who = "your" if target.id == ctx.author.id else f"{target.display_name}'s"
        await ctx.send(
            f"🧨 Hard reset complete — {who} city was wiped **and NS link removed**.\n"
            f"They’ll be prompted to re-link NationStates on next `$city`."
        )


    async def rate_details_embed(self, user: discord.abc.User, header: Optional[str] = None) -> discord.Embed:
        d = await self.config.user(user).all()
        currency = d.get("ns_currency") or "Local Credits"
        rate = d.get("wc_to_local_rate")
        scores_raw = d.get("ns_scores") or {}
        # keys may be strings; normalize to ints
        scores = {}
        for k, v in scores_raw.items():
            try:
                scores[int(k)] = float(v)
            except Exception:
                pass
    
        transforms = _make_transforms()
        weights = _make_weights()
    
        lines = []
        num = 0.0
        den = 0.0
        for sid in sorted(weights.keys(), key=lambda x: -weights[x]):  # show heavier weights first
            w = weights[sid]
            raw = scores.get(sid)
            if raw is None:
                lines.append(f"• Scale {sid}: **missing** → norm `—` × w `{w:.2f}` = contrib `0.00`")
                continue
            norm = transforms[sid](raw)
            contrib = w * norm
            num += contrib
            den += abs(w)
            # format raw compactly (handles scientific)
            raw_str = f"{raw:.4g}"
            lines.append(f"• Scale {sid}: raw `{raw_str}` → norm `{norm:.2f}` × w `{w:.2f}` = contrib `{contrib:.2f}`")
    
        idx = (num / den) if den else 0.5
        mapped = _map_index_to_rate(idx)
    
        desc = (
            "We normalize several NS stats, weight them, average to an **index** (0..1), "
            "then map to your exchange rate with 0.5 → **1.00×** (clamped 0.25..2.00)."
        )
        if header:
            desc = f"{header}\n\n{desc}"
    
        e = discord.Embed(title="💱 FX Rate Details", description=desc)
        if rate is not None:
            e.add_field(name="Current Rate", value=f"1 WC = **{float(rate):.2f} {currency}**", inline=False)
        else:
            e.add_field(name="Current Rate", value="(not set)", inline=False)
    
        e.add_field(name="Per-Scale Contributions", value="\n".join(lines) or "—", inline=False)
        e.add_field(name="Composite Index → Rate", value=f"Index `{idx:.3f}` → Mapped Rate `{mapped:.2f}`", inline=False)
        e.add_field(
            name="Weights & Transforms",
            value=(
                "Weights: 46=`0.50`, 1=`0.30`, 10=`0.15`, 39=`0.05`\n"
                "Transforms: 46=`log10(x+1)→[0..6]`, 1/10=`[0..100]`, 39=`Unemployment inverted [0..20]%`"
            ),
            inline=False
        )
        return e


    # Traditional Red command to open the panel
    @commands.command(name="city")
    async def city_cmd(self, ctx: commands.Context):
        """Open your city panel (first time shows NS setup)."""
        if await self._needs_ns_setup(ctx.author):
            # First-time: show a setup button that opens the modal
            prompt = discord.Embed(
                title="🌍 Set up your City",
                description="Before you start, link your **NationStates** main nation.\n"
                            "Click the button below to open the setup form."
            )
            return await ctx.send(embed=prompt, view=SetupPromptView(self, ctx.author))

        embed = await self.make_city_embed(ctx.author)
        view = CityMenuView(self, ctx.author, show_admin=self._is_adminish(ctx.author))
        await ctx.send(embed=embed, view=view)

    async def _needs_ns_setup(self, user: discord.abc.User) -> bool:
        d = await self.config.user(user).all()
        return not (d.get("ns_nation") and d.get("ns_currency") and (d.get("wc_to_local_rate") is not None))

    # -------------- lifecycle --------------
    async def cog_unload(self):
        self.task.cancel()

    def _is_adminish(self, member: discord.Member) -> bool:
        p = member.guild_permissions if isinstance(member, discord.Member) else None
        return bool(p and (p.administrator or p.manage_guild))

    # -------------- tick engine --------------
    async def resource_tick(self):
        """Automatic background tick."""
        await self.bot.wait_until_ready()
        while True:
            await self.process_all_ticks()
            await asyncio.sleep(TICK_SECONDS)

    async def process_all_ticks(self):
        all_users = await self.config.all_users()
        for user_id in all_users:
            user = self.bot.get_user(user_id)
            if user:
                await self.process_tick(user)

    async def process_tick(self, user: discord.abc.User):
        data = await self.config.user(user).all()
        buildings = data.get("buildings", {})
        if not buildings:
            return
    
        # total upkeep in WC (fixed underlying)
        total_wc = 0.0
        for b, info in buildings.items():
            if b in BUILDINGS:
                total_wc += BUILDINGS[b]["upkeep"] * int(info.get("count", 0))
        total_wc = trunc2(total_wc)
    
        # convert to local and charge from bank
        local_upkeep = await self._wc_to_local(user, total_wc)
        bank_local = trunc2(float(data.get("bank", 0.0)))
        if bank_local + 1e-9 < local_upkeep:
            return  # insufficient → halt production
    
        bank_local = trunc2(bank_local - local_upkeep)
    
        # produce resources
        new_resources = dict(data.get("resources", {}))
        for b, info in buildings.items():
            if b not in BUILDINGS:
                continue
            cnt = int(info.get("count", 0))
            if cnt <= 0:
                continue
            for res, amt in BUILDINGS[b]["produces"].items():
                new_resources[res] = int(new_resources.get(res, 0)) + int(amt * cnt)
    
        await self.config.user(user).resources.set(new_resources)
        await self.config.user(user).bank.set(bank_local)

    # -------------- embeds & helpers --------------
    async def make_city_embed(self, user: discord.abc.User, header: Optional[str] = None) -> discord.Embed:
        d = await self.config.user(user).all()
        res = d.get("resources", {})
        bld = d.get("buildings", {})
        bank_local = trunc2(float(d.get("bank", 0.0)))
        rate, cur = await self._get_rate_currency(user)
    
        # upkeep (wc + local)
        wc_upkeep = 0.0
        for b, info in bld.items():
            if b in BUILDINGS:
                wc_upkeep += BUILDINGS[b]["upkeep"] * int(info.get("count", 0))
        wc_upkeep = trunc2(wc_upkeep)
        local_upkeep = await self._wc_to_local(user, wc_upkeep)
    
        desc = "Use the buttons below to manage your city."
        if header:
            desc = f"{header}\n\n{desc}"
    
        e = discord.Embed(title=f"🌆 {getattr(user, 'display_name', 'Your')} City", description=desc)
        btxt = "\n".join(f"• **{b}** × {info.get('count', 0)}" for b, info in bld.items()) or "None"
        rtxt = "\n".join(f"• **{k}**: {v}" for k, v in res.items()) or "None"
    
        e.add_field(name="🏗️ Buildings", value=btxt, inline=False)
        e.add_field(name="📦 Resources", value=rtxt, inline=False)
        e.add_field(name="🏦 Bank", value=f"**{bank_local:.2f} {cur}**", inline=True)
        e.add_field(name="⏳ Upkeep per Tick",
                    value=f"**{local_upkeep:.2f} {cur}/t**", inline=True)
        e.add_field(name="🌍 Exchange", value=f"1 WC = **{rate:.2f} {cur}**", inline=False)
        return e

    
    async def build_help_embed(self, user: discord.abc.User) -> discord.Embed:
        e = discord.Embed(
            title="🏗️ Build",
            description="Pick a building to buy **1 unit** (costs your **local currency**; prices shown below)."
        )
        lines = []
        for name in BUILDINGS.keys():
            wc_cost = BUILDINGS[name]["cost"]
            wc_upkeep = BUILDINGS[name]["upkeep"]
            local_cost = await self._wc_to_local(user, wc_cost)
            local_upkeep = await self._wc_to_local(user, wc_upkeep)
            _, cur = await self._get_rate_currency(user)
            produces = ", ".join(f"{r}+{a}/tick" for r, a in BUILDINGS[name]["produces"].items())
            lines.append(
                f"**{name}** — Cost **{local_cost:.2f} {cur}** (={wc_cost:.2f} WC) | "
                f"Upkeep **{local_upkeep:.2f} {cur}/t** (={wc_upkeep:.2f} WC/t) | Produces {produces}"
            )
        e.add_field(name="Catalog", value="\n".join(lines) or "—", inline=False)
        return e



# ====== UI: Main Menu ======

class RateBtn(ui.Button):
    def __init__(self):
        super().__init__(label="FX Rate", style=discord.ButtonStyle.secondary, custom_id="city:rate")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        embed = await view.cog.rate_details_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=RateView(view.cog, view.author, show_admin=view.show_admin),
        )


class RateView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(RecalcRateBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True


class RecalcRateBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Recalculate from NS", style=discord.ButtonStyle.primary, custom_id="city:rate:recalc")

    async def callback(self, interaction: discord.Interaction):
        view: RateView = self.view  # type: ignore
        cog = view.cog
        d = await cog.config.user(interaction.user).all()
        nation = d.get("ns_nation")
        if not nation:
            return await interaction.response.send_message("You need to link a Nation first. Use `$city` and run setup.", ephemeral=True)

        try:
            currency, scores, xml_text = await ns_fetch_currency_and_scales(nation)
            rate, details = compute_currency_rate(scores)
            # save
            await cog.config.user(interaction.user).ns_currency.set(currency)
            await cog.config.user(interaction.user).set_raw("ns_scores", value={str(k): float(v) for k, v in scores.items()})
            await cog.config.user(interaction.user).wc_to_local_rate.set(rate)
            await cog.config.user(interaction.user).set_raw("rate_debug", value=details)
            await cog.config.user(interaction.user).set_raw("ns_last_xml", value=xml_text)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Failed to fetch from NationStates.\n`{e}`", ephemeral=True)

        embed = await cog.rate_details_embed(interaction.user, header="🔄 Recalculated from NationStates.")
        await interaction.response.edit_message(embed=embed, view=view)

class CityMenuView(ui.View):
    def __init__(self, cog: CityBuilder, author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.show_admin = show_admin

        self.add_item(ViewBtn())
        self.add_item(BuildBtn())
        self.add_item(BankBtn())
        if show_admin:
            self.add_item(NextDayBtn())
            self.add_item(RateBtn())  # add after BankBtn

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
        return interaction.user.id == self.author.id

class ViewBtn(ui.Button):
    def __init__(self):
        super().__init__(label="View", style=discord.ButtonStyle.primary, custom_id="city:view")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        embed = await view.cog.make_city_embed(interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)

class BankBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Bank", style=discord.ButtonStyle.secondary, custom_id="city:bank")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        embed = await view.cog.bank_help_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=BankView(view.cog, view.author, show_admin=view.show_admin),
        )


class BuildBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Build", style=discord.ButtonStyle.success, custom_id="city:build")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        embed = await view.cog.build_help_embed(view.author)
        await interaction.response.edit_message(
            embed=embed,
            view=BuildView(view.cog, view.author, show_admin=view.show_admin),
        )


class NextDayBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Next Day (All)", style=discord.ButtonStyle.danger, custom_id="city:nextday")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        await view.cog.process_all_ticks()
        await interaction.response.send_message("⏩ Advanced the world by one tick for everyone.", ephemeral=True)

# ====== UI: Build flow ======
class BuildSelect(ui.Select):
    def __init__(self, cog: CityBuilder):
        options = [
            discord.SelectOption(
                label=name,
                description=f"Cost {BUILDINGS[name]['cost']:.2f} WC | Upkeep {BUILDINGS[name]['upkeep']:.2f} WC/t"
            )
            for name in BUILDINGS.keys()
        ]
        super().__init__(
            placeholder="Choose a building to construct (costs wallet Wellcoins)",
            min_values=1, max_values=1, options=options, custom_id="city:build:select"
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        building = self.values[0].lower()
        if building not in BUILDINGS:
            return await interaction.response.send_message("⚠️ Unknown building.", ephemeral=True)
    
        wc_cost = trunc2(BUILDINGS[building]["cost"])
        local_cost = await self.cog._wc_to_local(interaction.user, wc_cost)
    
        bank_local = trunc2(float(await self.cog.config.user(interaction.user).bank()))
        if bank_local + 1e-9 < local_cost:
            _, cur = await self.cog._get_rate_currency(interaction.user)
            return await interaction.response.send_message(
                f"❌ Not enough in bank for **{building}**. Need **{local_cost:.2f} {cur}** (={wc_cost:.2f} WC).",
                ephemeral=True
            )
    
        # Deduct local from bank
        bank_local = trunc2(bank_local - local_cost)
        await self.cog.config.user(interaction.user).bank.set(bank_local)
    
        # Add building
        bld = await self.cog.config.user(interaction.user).buildings()
        curcnt = int(bld.get(building, {}).get("count", 0))
        bld[building] = {"count": curcnt + 1}
        await self.cog.config.user(interaction.user).buildings.set(bld)
    
        _, cur = await self.cog._get_rate_currency(interaction.user)
        header = f"🏗️ Built **{building}** for **{local_cost:.2f} {cur}** (={wc_cost:.2f} WC)."
        embed = await self.cog.make_city_embed(interaction.user, header=header)
        await interaction.response.edit_message(
            embed=embed,
            view=CityMenuView(self.cog, interaction.user, show_admin=self.cog._is_adminish(interaction.user))
        )


class BuildView(ui.View):
    def __init__(self, cog: CityBuilder, author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(BuildSelect(cog))
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True

# ====== UI: Bank flow (modals) ======
class BankView(ui.View):
    def __init__(self, cog: CityBuilder, author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(BankDepositBtn())
        self.add_item(BankWithdrawBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True

class BankDepositBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Deposit", style=discord.ButtonStyle.success, custom_id="city:bank:dep")

    async def callback(self, interaction: discord.Interaction):
        view: BankView = self.view  # type: ignore
        max_wc = await view.cog._get_wallet_wc(interaction.user)
        await interaction.response.send_modal(DepositModal(view.cog, max_wc=max_wc))


class BankWithdrawBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Withdraw", style=discord.ButtonStyle.danger, custom_id="city:bank:wit")

    async def callback(self, interaction: discord.Interaction):
        view: BankView = self.view  # type: ignore
        await interaction.response.send_modal(WithdrawModal(view.cog))

# ====== Shared Back button ======
class BackBtn(ui.Button):
    def __init__(self, show_admin: bool):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, custom_id="city:back")
        self.show_admin = show_admin

    async def callback(self, interaction: discord.Interaction):
        view: ui.View = self.view  # type: ignore
        cog: CityBuilder = view.cog  # type: ignore
        embed = await cog.make_city_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=CityMenuView(cog, interaction.user, show_admin=self.show_admin)
        )

# ====== Helpers ======
async def setup(bot: commands.Bot):
    await bot.add_cog(CityBuilder(bot))
