# citybuilder_buttons.py
import asyncio
import math
from typing import Dict, Optional, Tuple, Callable
import io
import aiohttp
import discord
from discord import ui
from redbot.core import commands, Config
import random
import time


# ====== Balance knobs ======
BUILDINGS: Dict[str, Dict] = {
    "house":   {"cost": 50.0,  "upkeep": 0, "produces": {},"capacity": 1, "tier": 0},  # +1 worker capacity
    "farm":    {"cost": 100.0, "upkeep": 0, "produces": {"food": 5}, "tier": 1},
    "mine":    {"cost": 200.0, "upkeep": 0, "produces": {"metal": 2}, "tier": 1},
    "factory": {"cost": 500.0, "upkeep": 5, "produces": {"goods": 1}, "tier": 1},
}

# Per-worker wage (in WC) per tick; user pays in local currency at their rate
WORKER_WAGE_WC = 1.0


TICK_SECONDS = 3600  # hourly ticks

# ====== NationStates config ======
NS_USER_AGENT = "9005"
NS_BASE = "https://www.nationstates.net/cgi-bin/api.cgi"

# Default composite: 46 + a few companions (tweak freely)
DEFAULT_SCALES = [46, 1, 10, 39]


class ViewBuildingsBtn(ui.Button):
    def __init__(self):
        super().__init__(label="View Buildings", style=discord.ButtonStyle.secondary, custom_id="city:buildings:view")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        e = await view.cog.buildings_overview_embed(interaction.user)
        tier_view = BuildingsTierView(view.cog, view.author, show_admin=view.show_admin)
        await interaction.response.edit_message(embed=e, view=tier_view)


class BuildingsTierView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.show_admin = show_admin

        # Add a button per tier dynamically
        for t in self.cog._all_tiers():
            self.add_item(TierButton(t))

        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True


class TierButton(ui.Button):
    def __init__(self, tier: int):
        super().__init__(label=f"Tier {tier}", style=discord.ButtonStyle.primary, custom_id=f"city:buildings:tier:{tier}")
        self.tier = int(tier)

    async def callback(self, interaction: discord.Interaction):
        view: BuildingsTierView = self.view  # type: ignore
        e = await view.cog.buildings_tier_embed(interaction.user, self.tier)
        # Reuse the same view so user can pick other tiers or go Back
        await interaction.response.edit_message(embed=e, view=view)


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
    def __init__(self, cog: "CityBuilder", max_local: Optional[float] = None, currency: Optional[str] = None):
        super().__init__()
        self.cog = cog
        self.max_local = trunc2(max_local or 0.0)
        self.currency = currency or "Local"

        label = f"Amount to withdraw (max {self.max_local:.2f} {self.currency})"
        placeholder = f"{self.max_local:.2f}" if max_local is not None else "e.g. 50.00"

        self.amount = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        # Parse local amount
        try:
            amt_local = trunc2(float(self.amount.value))
        except ValueError:
            return await interaction.response.send_message("❌ That’s not a number.", ephemeral=True)
        if amt_local <= 0:
            return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)

        # Check bank balance in local
        bank_local = trunc2(float(await self.cog.config.user(interaction.user).bank()))
        if bank_local + 1e-9 < amt_local:
            return await interaction.response.send_message(
                f"❌ Not enough in bank. You have **{bank_local:.2f} {self.currency}**.",
                ephemeral=True
            )

        # Convert local → WC
        amt_wc = await self.cog._local_to_wc(interaction.user, amt_local)
        if amt_wc <= 0:
            return await interaction.response.send_message(
                "❌ Amount too small to convert to at least **0.01 WC** at the current rate.",
                ephemeral=True
            )

        # Deduct local from bank
        new_bank = trunc2(bank_local - amt_local)
        await self.cog.config.user(interaction.user).bank.set(new_bank)

        # Credit WC to wallet
        nexus = self.cog.bot.get_cog("NexusExchange")
        if not nexus:
            # Undo deduction if Nexus is missing
            await self.cog.config.user(interaction.user).bank.set(bank_local)
            return await interaction.response.send_message("⚠️ NexusExchange not loaded.", ephemeral=True)

        await nexus.add_wellcoins(interaction.user, amt_wc)

        # Confirm
        _, cur = await self.cog._get_rate_currency(interaction.user)
        await interaction.response.send_message(
            f"✅ Withdrew **{amt_local:.2f} {cur}** → **{amt_wc:.2f} WC**.\n"
            f"New bank: **{new_bank:.2f} {cur}**",
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

class WorkersView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(HireWorkerBtn())
        self.add_item(AssignWorkerBtn())
        self.add_item(UnassignWorkerBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True
        
class HireWorkerBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Hire Worker", style=discord.ButtonStyle.success, custom_id="city:workers:hire")

    async def callback(self, interaction: discord.Interaction):
        view: WorkersView = self.view  # type: ignore
        cog = view.cog

        # simple “candidate”
        seed = random.randint(1, 70)
        img = f"https://i.pravatar.cc/150?img={seed}"
        wage_local = await cog._wc_to_local(interaction.user, WORKER_WAGE_WC)
        _, cur = await cog._get_rate_currency(interaction.user)

        e = discord.Embed(
            title="👤 Candidate: General Worker",
            description=(
                "Hard-working, adaptable, and ready to operate your facilities.\n"
                "• Reliability: ⭐⭐⭐\n"
                "• Safety: ⭐⭐⭐⭐\n"
                "• Salary: "
                f"**{wage_local:.2f} {cur}** per tick"
            )
        )
        e.set_image(url=img)

        await interaction.response.edit_message(
            embed=e,
            view=ConfirmHireView(cog, view.author, show_admin=any(isinstance(i, NextDayBtn) for i in view.children))
        )

class ConfirmHireView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=120)
        self.cog = cog
        self.author = author
        self.add_item(ConfirmHireNowBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

class ConfirmHireNowBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Confirm Hire", style=discord.ButtonStyle.primary, custom_id="city:workers:confirmhire")

    async def callback(self, interaction: discord.Interaction):
        view: ConfirmHireView = self.view  # type: ignore
        cog = view.cog
        d = await cog.config.user(interaction.user).all()
        cap = await cog._worker_capacity(interaction.user)
        hired = int(d.get("workers_hired") or 0)

        if hired >= cap:
            return await interaction.response.send_message("❌ No housing capacity. Build more **houses**.", ephemeral=True)

        # hire: +1 hired and +1 unassigned
        await cog.config.user(interaction.user).workers_hired.set(hired + 1)
        un = int(d.get("workers_unassigned") or 0) + 1
        await cog.config.user(interaction.user).workers_unassigned.set(un)

        embed = await cog.workers_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=WorkersView(cog, view.author, show_admin=any(isinstance(i, NextDayBtn) for i in view.children))
        )


class AssignWorkerBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Assign Worker", style=discord.ButtonStyle.secondary, custom_id="city:workers:assign")

    async def callback(self, interaction: discord.Interaction):
        view: WorkersView = self.view  # type: ignore
        await interaction.response.edit_message(
            embed=await view.cog.workers_embed(interaction.user),
            view=AssignView(view.cog, view.author, show_admin=any(isinstance(i, NextDayBtn) for i in view.children)),
        )

class AssignView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=120)
        self.cog = cog
        self.author = author
        self.add_item(AssignSelect(cog))
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

class AssignSelect(ui.Select):
    def __init__(self, cog: "CityBuilder"):
        self.cog = cog
        options = [discord.SelectOption(label=b) for b in BUILDINGS.keys() if b != "house"]
        super().__init__(placeholder="Assign 1 worker to a building", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        b = self.values[0]
        d = await self.cog.config.user(interaction.user).all()
        await self.cog._reconcile_staffing(interaction.user)
        st = await self.cog._get_staffing(interaction.user)

        # capacity on building
        cnt = int((d.get("buildings") or {}).get(b, {}).get("count", 0))
        if cnt <= 0:
            return await interaction.response.send_message(f"❌ You have no **{b}**.", ephemeral=True)

        assigned = int(st.get(b, 0))
        unassigned = int(d.get("workers_unassigned") or 0)
        if unassigned <= 0:
            return await interaction.response.send_message("❌ No unassigned workers available.", ephemeral=True)
        if assigned >= cnt:
            return await interaction.response.send_message(f"❌ All **{b}** are already staffed.", ephemeral=True)

        st[b] = assigned + 1
        await self.cog._set_staffing(interaction.user, st)
        await self.cog.config.user(interaction.user).workers_unassigned.set(unassigned - 1)

        embed = await self.cog.workers_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=WorkersView(self.cog, interaction.user, show_admin=True if self.view and any(isinstance(i, NextDayBtn) for i in self.view.children) else False)  # type: ignore
        )

class UnassignWorkerBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Unassign Worker", style=discord.ButtonStyle.secondary, custom_id="city:workers:unassign")

    async def callback(self, interaction: discord.Interaction):
        view: WorkersView = self.view  # type: ignore
        await interaction.response.edit_message(
            embed=await view.cog.workers_embed(interaction.user),
            view=UnassignView(view.cog, view.author, show_admin=any(isinstance(i, NextDayBtn) for i in view.children)),
        )

class UnassignView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=120)
        self.cog = cog
        self.author = author
        self.add_item(UnassignSelect(cog))
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

class UnassignSelect(ui.Select):
    def __init__(self, cog: "CityBuilder"):
        self.cog = cog
        options = [discord.SelectOption(label=b) for b in BUILDINGS.keys() if b != "house"]
        super().__init__(placeholder="Unassign 1 worker from a building", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        b = self.values[0]
        await self.cog._reconcile_staffing(interaction.user)
        st = await self.cog._get_staffing(interaction.user)
        if st.get(b, 0) <= 0:
            return await interaction.response.send_message(f"❌ No workers assigned to **{b}**.", ephemeral=True)

        st[b] -= 1
        await self.cog._set_staffing(interaction.user, st)
        un = int((await self.cog.config.user(interaction.user).workers_unassigned()) or 0) + 1
        await self.cog.config.user(interaction.user).workers_unassigned.set(un)

        embed = await self.cog.workers_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=WorkersView(self.cog, interaction.user, show_admin=True if self.view and any(isinstance(i, NextDayBtn) for i in self.view.children) else False)  # type: ignore
        )


# ====== Store confirmations ======
class ConfirmPurchaseView(ui.View):
    def __init__(
        self,
        cog: "CityBuilder",
        buyer: discord.abc.User,
        owner_id: int,
        listing_id: str,
        listing_name: str,
        bundle: Dict[str, int],
        price_wc: float,
        buyer_price_local: float,
        show_admin: bool,
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.buyer = buyer
        self.owner_id = int(owner_id)
        self.listing_id = listing_id
        self.listing_name = listing_name
        self.bundle = dict(bundle)
        self.price_wc = float(price_wc)
        self.buyer_price_local = float(buyer_price_local)
        self.show_admin = show_admin
        self.add_item(ConfirmPurchaseBtn())
        self.add_item(CancelConfirmBtn())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.buyer.id


class ConfirmPurchaseBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Confirm Purchase", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        view: ConfirmPurchaseView = self.view  # type: ignore
        cog = view.cog

        # Re-load seller listing (to avoid race conditions)
        owner_conf = cog.config.user_from_id(view.owner_id)
        owner_data = await owner_conf.all()
        listings = list(owner_data.get("store_sell_listings") or [])
        listing = next((x for x in listings if x.get("id") == view.listing_id), None)
        if not listing:
            return await interaction.response.send_message("Listing unavailable.", ephemeral=True)

        # Check effective stock again
        eff_stock = cog._effective_stock_from_escrow(listing) if hasattr(cog, "_effective_stock_from_escrow") else int(listing.get("stock", 0) or 0)
        if eff_stock <= 0:
            listing["stock"] = 0
            for i, it in enumerate(listings):
                if it.get("id") == view.listing_id:
                    listings[i] = listing
                    break
            await owner_conf.store_sell_listings.set(listings)
            return await interaction.response.send_message("⚠️ This listing is currently out of stock.", ephemeral=True)

        # Charge buyer (uses price calculated earlier)
        ok = await cog._charge_bank_local(view.buyer, trunc2(view.buyer_price_local))
        if not ok:
            return await interaction.response.send_message(
                f"❌ Not enough funds. Need **{view.buyer_price_local:.2f}** (incl. 10% fee).",
                ephemeral=True
            )

        # Transfer one unit from escrow → buyer
        bundle = {k: int(v) for k, v in (listing.get("bundle") or {}).items()}
        escrow = {k: int(v) for k, v in (listing.get("escrow") or {}).items()}
        for r, need in bundle.items():
            escrow[r] = max(0, int(escrow.get(r, 0)) - int(need))
        listing["escrow"] = escrow
        listing["stock"] = max(0, int(listing.get("stock", 0)) - 1)

        # Save seller listing
        for i, it in enumerate(listings):
            if it.get("id") == view.listing_id:
                listings[i] = listing
                break
        await owner_conf.store_sell_listings.set(listings)

        # Give items to buyer
        await cog._adjust_resources(view.buyer, bundle)

        # Credit seller (after fee)
        seller_user = cog.bot.get_user(view.owner_id)
        if seller_user:
            seller_payout_local = trunc2((await cog._wc_to_local(seller_user, float(listing.get("price_wc") or view.price_wc))) * 0.90)
            await cog._credit_bank_local(seller_user, seller_payout_local)

        # Feedback + return to main menu
        e = await cog.make_city_embed(
            view.buyer,
            header=f"🛒 Purchased **{view.listing_name}** for **{view.buyer_price_local:.2f}** (incl. fee)."
        )
        await interaction.response.edit_message(
            embed=e,
            view=CityMenuView(cog, view.buyer, show_admin=view.show_admin)
        )


class ConfirmSellToOrderView(ui.View):
    def __init__(
        self,
        cog: "CityBuilder",
        seller: discord.abc.User,
        buyer_id: int,
        order_id: str,
        resource: str,
        price_wc: float,
        seller_payout_local: float,
        show_admin: bool,
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.seller = seller
        self.buyer_id = int(buyer_id)
        self.order_id = order_id
        self.resource = resource
        self.price_wc = float(price_wc)
        self.seller_payout_local = float(seller_payout_local)
        self.show_admin = show_admin
        self.add_item(ConfirmSellBtn())
        self.add_item(CancelConfirmBtn())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.seller.id


class ConfirmSellBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Confirm Sale", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        view: ConfirmSellToOrderView = self.view  # type: ignore
        cog = view.cog

        # Reload buyer order
        buyer_conf = cog.config.user_from_id(view.buyer_id)
        buyer_data = await buyer_conf.all()
        orders = list(buyer_data.get("store_buy_orders") or [])
        order = next((x for x in orders if x.get("id") == view.order_id), None)
        if not order or int(order.get("qty", 0)) <= 0:
            return await interaction.response.send_message("Order unavailable.", ephemeral=True)

        res = str(order.get("resource") or "").lower()
        if res == "ore":
            res = "metal"

        # Ensure seller still has the item
        d = await cog.config.user(view.seller).all()
        if int((d.get("resources") or {}).get(res, 0)) <= 0:
            return await interaction.response.send_message(f"❌ You no longer have **{res}**.", ephemeral=True)

        price_wc = float(order.get("price_wc") or view.price_wc)

        # Charge buyer (+10%)
        buyer_user = cog.bot.get_user(view.buyer_id)
        if not buyer_user:
            return await interaction.response.send_message("Buyer not present; try later.", ephemeral=True)
        buyer_charge_local = trunc2((await cog._wc_to_local(buyer_user, price_wc)) * 1.10)
        ok = await cog._charge_bank_local(buyer_user, buyer_charge_local)
        if not ok:
            return await interaction.response.send_message("❌ Buyer lacks funds to complete this order.", ephemeral=True)

        # Transfer resource
        await cog._adjust_resources(view.seller, {res: -1})
        await cog._adjust_resources(buyer_user, {res: +1})

        # Decrement order
        for o in orders:
            if o.get("id") == view.order_id:
                o["qty"] = int(o.get("qty", 0)) - 1
                break
        await buyer_conf.store_buy_orders.set(orders)

        # Credit seller (−10%)
        seller_payout_local = trunc2((await cog._wc_to_local(view.seller, price_wc)) * 0.90)
        await cog._credit_bank_local(view.seller, seller_payout_local)

        e = await cog.make_city_embed(
            view.seller,
            header=f"✅ Sold **1 {res}** for **{seller_payout_local:.2f}** (after fee)."
        )
        await interaction.response.edit_message(
            embed=e,
            view=CityMenuView(cog, view.seller, show_admin=view.show_admin)
        )


class CancelConfirmBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        # Just close the ephemeral confirmation
        await interaction.response.send_message("❎ Cancelled.", ephemeral=True)


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
            rate_debug={},
            workers_hired=0,            # total hired workers
            workers_unassigned=0,       # idle workers
            staffing={},                # {"farm": 0, "mine": 0, ...}# optional for debugging

            store_sell_listings=[],  # [{id:str, name:str, bundle:{res:int}, price_wc: float, stock:int}]
            store_buy_orders=[],     # [{id:str, resource:str, qty:int, price_wc:float}]
        )
        self.next_tick_at: Optional[int] = None
        self.task = bot.loop.create_task(self.resource_tick())

    def _next_tick_ts(self) -> int:
        if getattr(self, "next_tick_at", None):
            return int(self.next_tick_at)
        return int((time.time() // TICK_SECONDS + 1) * TICK_SECONDS)

    def _all_tiers(self) -> list:
        """Sorted unique tiers from BUILDINGS."""
        tiers = sorted({int(data.get("tier", 0)) for data in BUILDINGS.values()})
        return tiers

    def _group_owned_by_tier(self, user_data: dict) -> Dict[int, list]:
        """
        Returns {tier: [(name, count), ...]} containing only buildings the user owns (>0).
        """
        by_tier: Dict[int, list] = {}
        owned = (user_data.get("buildings") or {})
        for name, meta in BUILDINGS.items():
            tier = int(meta.get("tier", 0))
            cnt = int((owned.get(name) or {}).get("count", 0))
            if cnt > 0:
                by_tier.setdefault(tier, []).append((name, cnt))
        # sort names within each tier
        for t in by_tier:
            by_tier[t].sort(key=lambda p: p[0])
        return by_tier
    
    async def buildings_overview_embed(self, user: discord.abc.User) -> discord.Embed:
        """
        Overview of user's buildings grouped by tier.
        Shows tiers even if empty (as  — ).
        """
        d = await self.config.user(user).all()
        grouped = self._group_owned_by_tier(d)
        lines = []
        for t in self._all_tiers():
            entries = grouped.get(t, [])
            if not entries:
                lines.append(f"**Tier {t}** — —")
            else:
                count = name * cnt for name, cnt in entries
                lines.append(f"**Tier {t}** — {row}")
        e = discord.Embed(title="🏗️ Buildings by Tier", description="\n".join(lines) or "—")
        e.set_footer(text="Select a tier below to view details.")
        return e
    
    async def buildings_tier_embed(self, user: discord.abc.User, tier: int) -> discord.Embed:
        """
        Detailed view for a single tier: cost, upkeep, inputs/outputs.
        Inputs are shown if you later add them to BUILDINGS (uses key 'inputs').
        """
        d = await self.config.user(user).all()
        rate, cur = await self._get_rate_currency(user)
        lines = []
        for name, meta in sorted(BUILDINGS.items()):
            if int(meta.get("tier", 0)) != int(tier):
                continue
            cnt = int((d.get("buildings") or {}).get(name, {}).get("count", 0))
            cost_wc = float(meta.get("cost", 0.0))
            upkeep_wc = float(meta.get("upkeep", 0.0))
            cost_local = trunc2(cost_wc * rate)
            upkeep_local = trunc2(upkeep_wc * rate)
            inputs = meta.get("inputs") or {}
            outputs = meta.get("produces") or {}
    
            def fmt_io(io: Dict[str, int]) -> str:
                return ", ".join(f"{k}+{v}" for k, v in io.items()) if io else "—"
    
            cap_note = ""
            if name == "house":
                cap = int(meta.get("capacity", 0))
                if cap:
                    cap_note = f" · Capacity +{cap}"
    
            lines.append(
                f"• **{name}** "
                f"(owned {cnt})\n"
                f"  Cost **{cost_local:.2f} {cur}** · Upkeep **{upkeep_local:.2f} {cur}/t**{cap_note}\n"
                f"  Inputs: {fmt_io(inputs)}\n"
                f"  Outputs: {fmt_io(outputs)}"
            )
        if not lines:
            lines = ["—"]
        e = discord.Embed(title=f"🏗️ Tier {tier} — Details", description="\n".join(lines))
        return e



    # ====== Store helpers & embeds ======
    async def store_home_embed(self, user: discord.abc.User) -> discord.Embed:
        e = discord.Embed(
            title="🛒 Player Store",
            description="Create sell listings for **bundles**, post **buy orders** for resources, "
                        "and trade across currencies.\n\n"
                        "Fees: Buyer +10% on conversion · Seller −10% on payout."
        )
        e.add_field(name="What you can sell", value="Any bundle of: **food, metal, goods**", inline=False)
        e.add_field(name="What you can buy",  value="Any produced resource: **food, metal, goods**", inline=False)
        return e

    def _bundle_mul(self, bundle: Dict[str, int], n: int) -> Dict[str, int]:
        return {k: int(v) * int(n) for k, v in (bundle or {}).items()}

    def _bundle_sub(self, a: Dict[str, int], b: Dict[str, int]) -> Dict[str, int]:
        out = dict(a or {})
        for k, v in (b or {}).items():
            out[k] = int(out.get(k, 0)) - int(v)
            if out[k] <= 0:
                out[k] = 0
        return out
    
    def _bundle_add(self, a: Dict[str, int], b: Dict[str, int]) -> Dict[str, int]:
        out = dict(a or {})
        for k, v in (b or {}).items():
            out[k] = int(out.get(k, 0)) + int(v)
        return out
    
    def _effective_stock_from_escrow(self, listing: Dict) -> int:
        """
        Derive usable stock from escrow vs per-unit bundle.
        If 'escrow' missing (legacy), fall back to listing['stock'] (best effort).
        """
        bundle = {k: int(v) for k, v in (listing.get("bundle") or {}).items()}
        escrow = {k: int(v) for k, v in (listing.get("escrow") or {}).items()}
        if not bundle:
            return 0
        # Units possible with current escrow
        possible = min((escrow.get(k, 0) // max(1, bundle[k])) for k in bundle.keys())
        return min(int(listing.get("stock", 0)), possible)

    
    async def store_my_listings_embed(self, user: discord.abc.User, header: Optional[str] = None) -> discord.Embed:
        d = await self.config.user(user).all()
        lst = list(d.get("store_sell_listings") or [])
        orders = list(d.get("store_buy_orders") or [])
        rate, cur = await self._get_rate_currency(user)
        def fmt_bundle(b: Dict[str, int]) -> str:
            if not b: return "—"
            return ", ".join([f"{k}+{v}" for k, v in b.items()])
        sell_lines = []
        for it in lst:
            p_local = trunc2(float(it.get("price_wc") or 0.0) * rate)
            sell_lines.append(f"• **{it.get('id')}** — {it.get('name')} | {fmt_bundle(it.get('bundle') or {})} | "
                              f"Price **{p_local:.2f} {cur}** | Stock {int(it.get('stock') or 0)}")
        buy_lines = []
        for o in orders:
            p_local = trunc2(float(o.get("price_wc") or 0.0) * rate)
            buy_lines.append(f"• **{o.get('id')}** — {o.get('resource')} ×{int(o.get('qty') or 0)} @ **{p_local:.2f} {cur}** /u")
        desc = (header + "\n\n" if header else "") + "**Your Sell Listings**\n" + ("\n".join(sell_lines) or "—")
        e = discord.Embed(title="🧾 My Store", description=desc)
        e.add_field(name="Your Buy Orders", value=("\n".join(buy_lines) or "—"), inline=False)
        return e
    
    async def store_browse_embed(self, viewer: discord.abc.User) -> discord.Embed:
        all_users = await self.config.all_users()
        rate, cur = await self._get_rate_currency(viewer)
        lines = []
        for owner_id, udata in all_users.items():
            if int(owner_id) == viewer.id:
                continue
            for it in (udata.get("store_sell_listings") or []):
                # Compute effective (escrow-backed) stock FIRST
                effective_stock = (
                    self._effective_stock_from_escrow(it)
                    if hasattr(self, "_effective_stock_from_escrow")
                    else int(it.get("stock") or 0)
                )
                if effective_stock <= 0:
                    continue
    
                price_wc = float(it.get("price_wc") or 0.0)
                price_local = trunc2(price_wc * rate * 1.10)  # include buyer fee
                owner = self.bot.get_user(int(owner_id))
                owner_name = owner.display_name if owner else f"User {owner_id}"
                bundle = ", ".join([f"{k}+{v}" for k, v in (it.get("bundle") or {}).items()]) or "—"
    
                lines.append(
                    f"• **{it.get('id')}** — {it.get('name')} by *{owner_name}* · {bundle} · "
                    f"**{price_local:.2f} {cur}** (incl. fee) · Stock {effective_stock}"
                )
    
        e = discord.Embed(
            title="🛍️ Browse Listings",
            description="\n".join(lines) or "No listings available."
        )
        return e

    
    async def store_fulfill_embed(self, seller: discord.abc.User) -> discord.Embed:
        """
        Show buy orders another player posted that the seller can likely fulfill *now*.
        - Filters to orders where the seller has at least 1 unit of the resource.
        - Computes seller payout (after 10% fee) in seller's currency.
        - Best-effort flag if buyer appears short on funds (bank < price_in_buyer_currency + 10%).
        """
        all_users = await self.config.all_users()
        seller_rate, seller_cur = await self._get_rate_currency(seller)
    
        # Seller inventory snapshot
        d = await self.config.user(seller).all()
        inv = {k: int(v) for k, v in (d.get("resources") or {}).items()}
    
        lines = []
    
        for owner_id, udata in all_users.items():
            buyer_id = int(owner_id)
            if buyer_id == seller.id:
                continue
    
            # Pull buyer info we might need
            try:
                buyer_user = self.bot.get_user(buyer_id)
                buyer_rate, _buyer_cur = await self._get_rate_currency(buyer_user) if buyer_user else (1.0, "Local")
                buyer_bank_local = float((udata or {}).get("bank", 0.0))
            except Exception:
                buyer_user = None
                buyer_rate, _buyer_cur, buyer_bank_local = (1.0, "Local", 0.0)
    
            for o in (udata.get("store_buy_orders") or []):
                qty = int(o.get("qty", 0) or 0)
                if qty <= 0:
                    continue
    
                res = str(o.get("resource") or "").lower()
                if res == "ore":
                    res = "metal"
    
                # Only show if seller has the resource *now*
                if int(inv.get(res, 0)) <= 0:
                    continue
    
                price_wc = float(o.get("price_wc") or 0.0)
                if price_wc <= 0:
                    continue
    
                # Seller payout (after fee), shown in seller currency
                payout_local = trunc2(price_wc * seller_rate * 0.90)
    
                # Quick check whether buyer likely has the funds (buyer pays +10% in their currency)
                buyer_charge_local = trunc2(price_wc * buyer_rate * 1.10)
                buyer_ok = (buyer_bank_local + 1e-9) >= buyer_charge_local
    
                owner = self.bot.get_user(buyer_id)
                owner_name = owner.display_name if owner else f"User {buyer_id}"
    
                warn_txt = "" if buyer_ok else " _(buyer may be short on funds)_"
                lines.append(
                    f"• **{o.get('id')}** — {res} ×{qty} from *{owner_name}* "
                    f"@ **{payout_local:.2f} {seller_cur}** (after fee){warn_txt}"
                )
    
        return discord.Embed(
            title="📦 Fulfill Buy Orders",
            description="\n".join(lines) or "No open buy orders you can fulfill right now."
        )




    async def _adjust_resources(self, user: discord.abc.User, delta: Dict[str, int]) -> None:
        d = await self.config.user(user).all()
        res = dict(d.get("resources") or {})
        for k, v in delta.items():
            res[k] = int(res.get(k, 0)) + int(v)
            if res[k] < 0:
                res[k] = 0
        await self.config.user(user).resources.set(res)
    
    async def _charge_bank_local(self, user: discord.abc.User, amount_local: float) -> bool:
        amt = trunc2(amount_local)
        bank_local = trunc2(float(await self.config.user(user).bank()))
        if bank_local + 1e-9 < amt:
            return False
        await self.config.user(user).bank.set(trunc2(bank_local - amt))
        return True
    
    async def _credit_bank_local(self, user: discord.abc.User, amount_local: float) -> None:
        bank_local = trunc2(float(await self.config.user(user).bank()))
        await self.config.user(user).bank.set(trunc2(bank_local + trunc2(amount_local)))


    async def _local_to_wc(self, user: discord.abc.User, local_amount: float) -> float:
        """Convert local currency → WC using the user's current rate, truncating to 2 decimals."""
        rate, _ = await self._get_rate_currency(user)
        rate = float(rate) if rate else 1.0
        return trunc2(trunc2(local_amount) / rate)


    async def workers_embed(self, user: discord.abc.User) -> discord.Embed:
        d = await self.config.user(user).all()
        hired = int(d.get("workers_hired") or 0)
        st = await self._get_staffing(user)
        assigned = sum(st.values())
        unassigned = max(0, hired - assigned)
        cap = await self._worker_capacity(user)
        rate, cur = await self._get_rate_currency(user)
        wage_local = await self._wc_to_local(user, WORKER_WAGE_WC)
    
        lines = [
            f"• **{b}** staffed: {st.get(b, 0)}"
            for b in (d.get("buildings") or {}).keys()
            if b != "house"          # don't list houses
        ]
        staffed_txt = "\n".join(lines) or "None"
            
        e = discord.Embed(title="👷 Workers", description="Hire and assign workers to buildings to enable production.")
        e.add_field(name="Status",
                    value=(f"Hired **{hired}** · Capacity **{cap}** · Assigned **{assigned}** · Unassigned **{unassigned}** · "),
                    inline=False)
        e.add_field(name="Wage",
                    value=f"**{wage_local:.2f} {cur}** per worker per tick",
                    inline=False)
        e.add_field(name="Staffing by Building", value=staffed_txt, inline=False)
        return e


    def _get_building_count_sync(self, data: dict, name: str) -> int:
        return int((data.get("buildings") or {}).get(name, {}).get("count", 0))
    
    async def _worker_capacity(self, user: discord.abc.User) -> int:
        d = await self.config.user(user).all()
        houses = self._get_building_count_sync(d, "house")
        cap_per = int(BUILDINGS["house"].get("capacity", 1))
        return houses * cap_per
    
    async def _get_staffing(self, user: discord.abc.User) -> Dict[str, int]:
        d = await self.config.user(user).all()
        st: Dict[str, int] = {k: int(v) for k, v in (d.get("staffing") or {}).items()}
        # ensure keys for all buildings
        bld = d.get("buildings") or {}
        for b in bld.keys():
            st.setdefault(b, 0)
        return st
    
    async def _set_staffing(self, user: discord.abc.User, st: Dict[str, int]) -> None:
        # sanitize negative values
        clean = {k: max(0, int(v)) for k, v in st.items()}
        await self.config.user(user).staffing.set(clean)
    
    async def _reconcile_staffing(self, user: discord.abc.User) -> None:
        """Clamp assignments to existing buildings, capacity, and worker counts."""
        d = await self.config.user(user).all()
        st = await self._get_staffing(user)
        bld = d.get("buildings") or {}
    
        # Remove staffing for buildings the user no longer owns
        st = {k: v for k, v in st.items() if k in bld}
    
        # Clamp per-building to its count
        for b, info in (bld or {}).items():
            cnt = int(info.get("count", 0))
            st[b] = min(int(st.get(b, 0)), cnt)
    
        # Sum assigned, clamp to workers_hired and capacity
        assigned = sum(st.values())
        hired = int(d.get("workers_hired") or 0)
        cap = await self._worker_capacity(user)
        max_assignable = min(hired, cap)
        if assigned > max_assignable:
            # Unassign extras in arbitrary order
            overflow = assigned - max_assignable
            for b in list(st.keys()):
                if overflow <= 0: break
                take = min(st[b], overflow)
                st[b] -= take
                overflow -= take
    
        # Fix workers_unassigned accordingly
        assigned = sum(st.values())
        unassigned = max(0, hired - assigned)
        await self._set_staffing(user, st)
        await self.config.user(user).workers_unassigned.set(unassigned)


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
            self.next_tick_at = int(time.time()) + TICK_SECONDS
            await asyncio.sleep(TICK_SECONDS)

    async def process_all_ticks(self):
        all_users = await self.config.all_users()
        for user_id in all_users:
            user = self.bot.get_user(user_id)
            if user:
                await self.process_tick(user)

    async def process_tick(self, user: discord.abc.User):
        d = await self.config.user(user).all()
        bld = d.get("buildings", {})
        if not bld:
            return
    
        await self._reconcile_staffing(user)
        st = await self._get_staffing(user)
    
        # Buildings upkeep (WC)
        total_upkeep_wc = 0.0
        for b, info in bld.items():
            if b in BUILDINGS:
                total_upkeep_wc += BUILDINGS[b]["upkeep"] * int(info.get("count", 0))
        total_upkeep_wc = trunc2(total_upkeep_wc)
    
        # Wages (WC)
        hired = int(d.get("workers_hired") or 0)
        wages_wc = trunc2(hired * WORKER_WAGE_WC)
    
        # Total WC → Local
        need_local = await self._wc_to_local(user, trunc2(total_upkeep_wc + wages_wc))
        bank_local = trunc2(float(d.get("bank", 0.0)))
    
        # If we can't pay **everything**, halt production and don't charge
        if bank_local + 1e-9 < need_local:
            return
    
        # Deduct funds
        bank_local = trunc2(bank_local - need_local)
    
        # Production only from staffed units
        new_resources = dict(d.get("resources", {}))
        for b, info in bld.items():
            if b not in BUILDINGS:
                continue
            cnt = int(info.get("count", 0))
            staffed = min(cnt, int(st.get(b, 0)))
            if staffed <= 0:
                continue
            for res, amt in BUILDINGS[b]["produces"].items():
                new_resources[res] = int(new_resources.get(res, 0)) + int(amt * staffed)
    
        await self.config.user(user).resources.set(new_resources)
        await self.config.user(user).bank.set(bank_local)


    # -------------- embeds & helpers --------------
    async def make_city_embed(self, user: discord.abc.User, header: Optional[str] = None) -> discord.Embed:
        d = await self.config.user(user).all()
        res = d.get("resources", {})
        bld = d.get("buildings", {})
        bank_local = trunc2(float(d.get("bank", 0.0)))
        rate, cur = await self._get_rate_currency(user)
    
        # upkeep (WC→local)
        wc_upkeep = 0.0
        for b, info in bld.items():
            if b in BUILDINGS:
                wc_upkeep += BUILDINGS[b]["upkeep"] * int(info.get("count", 0))
        wc_upkeep = trunc2(wc_upkeep)
        local_upkeep = await self._wc_to_local(user, wc_upkeep)
    
        # workers
        await self._reconcile_staffing(user)
        hired = int(d.get("workers_hired") or 0)
        st = await self._get_staffing(user)
        assigned = sum(st.values())
        unassigned = max(0, hired - assigned)
        cap = await self._worker_capacity(user)
        wages_local = await self._wc_to_local(user, trunc2(hired * WORKER_WAGE_WC))
    
        desc = "Use the buttons below to manage your city."
        if header:
            desc = f"{header}\n\n{desc}"
    
        e = discord.Embed(title=f"🌆 {getattr(user, 'display_name', 'Your')} City", description=desc)
            
        grouped = self._group_owned_by_tier(d)
        tier_lines = []
        for t in self._all_tiers():
            entries = grouped.get(t, [])
            if not entries:
                continue  # hide empty tiers on the main card; they’ll appear in the browser
            row = " | ".join(f"{name}×{cnt}" for name, cnt in entries)
            tier_lines.append(f"**Tier {t}** — {row}")
        btxt = "\n".join(tier_lines) or "None"      
        
        rtxt = "\n".join(f"• **{k}**: {v}" for k, v in res.items()) or "None"
    
        e.add_field(name="🏗️ Buildings", value=btxt, inline=False)
        e.add_field(name="📦 Resources", value=rtxt, inline=False)
        e.add_field(
            name="👷 Workers",
            value=(
                f"Hired **{hired}** · Assigned **{assigned}** · Unassigned **{unassigned}** · "
                f"Capacity **{cap}**\n"
                f"Wages per tick: **{wages_local:.2f} {cur}** "
                f"(= {trunc2(hired * WORKER_WAGE_WC):.2f} WC)"
            ),
            inline=False,
        )
        e.add_field(name="🏦 Bank", value=f"**{bank_local:.2f} {cur}**", inline=True)
        e.add_field(name="⏳ Upkeep per Tick", value=f"**{local_upkeep:.2f} {cur}/t**", inline=True)
        e.add_field(name="🌍 Exchange", value=f"1 WC = **{rate:.2f} {cur}**", inline=False)
        next_ts = self._next_tick_ts()
        e.add_field(
            name="🕒 Next Tick",
            value=f"<t:{next_ts}:R>  —  <t:{next_ts}:T>",
            inline=False
        )

        return e



    
    async def build_help_embed(self, user: discord.abc.User) -> discord.Embed:
        e = discord.Embed(
            title="🏗️ Build",
            description="Pick a building to buy **1 unit** (costs your **local currency**; prices shown below)."
        )
    
        lines = []
        for name, data in BUILDINGS.items():
            wc_cost = float(data["cost"])
            wc_upkeep = float(data["upkeep"])
            local_cost = await self._wc_to_local(user, wc_cost)
            local_upkeep = await self._wc_to_local(user, wc_upkeep)
            produces_str = ", ".join(f"{r}+{a}/tick" for r, a in data["produces"].items()) or "—"
            _, cur = await self._get_rate_currency(user)
            note = " (+1 worker capacity)" if name == "house" else ""
    
            lines.append(
                f"**{name}** — Cost **{local_cost:.2f} {cur}** | "
                f"Upkeep **{local_upkeep:.2f} {cur}/t** | Produces {produces_str} {note}"
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

class StoreBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Store", style=discord.ButtonStyle.secondary, custom_id="city:store")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore

        # Build the intro embed inline so we don't require cog.store_home_embed()
        e = discord.Embed(
            title="🛒 Player Store",
            description=(
                "Create sell listings for **bundles**, post **buy orders** for resources, "
                "and trade across currencies.\n\n"
                "Fees: Buyer **+10%** on conversion · Seller **−10%** on payout."
            ),
        )
        e.add_field(name="What you can sell", value="Any bundle of: **food, metal, goods**", inline=False)
        e.add_field(name="What you can buy",  value="Any produced resource: **food, metal, goods**", inline=False)

        # If you already have StoreMenuView defined, show it; otherwise just show the embed.
        try:
            await interaction.response.edit_message(
                embed=e,
                view=StoreMenuView(view.cog, view.author, show_admin=view.show_admin),  # type: ignore
            )
        except NameError:
            # Fallback if StoreMenuView isn't defined yet
            await interaction.response.edit_message(embed=e, view=view)


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
        self.add_item(WorkersBtn())
        self.add_item(StoreBtn())
        self.add_item(ViewBuildingsBtn())  
        if show_admin:
            self.add_item(NextDayBtn())
            self.add_item(RateBtn()) 

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
        return interaction.user.id == self.author.id

class WorkersBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Workers", style=discord.ButtonStyle.secondary, custom_id="city:workers")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        embed = await view.cog.workers_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=WorkersView(view.cog, view.author, show_admin=view.show_admin),
        )


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
        # NEW: get user FX
        rate, cur = await view.cog._get_rate_currency(interaction.user)

        embed = await view.cog.build_help_embed(view.author)
        await interaction.response.edit_message(
            embed=embed,
            # NEW: pass rate & currency into BuildView
            view=BuildView(view.cog, view.author, rate, cur, show_admin=view.show_admin),
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
    def __init__(self, cog: CityBuilder, rate: float, currency: str):
        self.cog = cog
        self.rate = float(rate)
        self.currency = currency

        options = []
        for name in BUILDINGS.keys():
            wc_cost = trunc2(BUILDINGS[name]["cost"])
            wc_upkeep = trunc2(BUILDINGS[name]["upkeep"])
            local_cost = trunc2(wc_cost * self.rate)
            local_upkeep = trunc2(wc_upkeep * self.rate)
            desc = f"Cost {local_cost:.2f} {self.currency} · Upkeep {local_upkeep:.2f} {self.currency}/t"
            if len(desc) > 96:
                desc = f"Cost {local_cost:.2f} · Upkeep {local_upkeep:.2f}/t"
            options.append(discord.SelectOption(label=name, description=desc))


        super().__init__(
            placeholder="Choose a building (local prices shown)",
            min_values=1, max_values=1, options=options, custom_id="city:build:select"
        )

    async def callback(self, interaction: discord.Interaction):
        building = self.values[0].lower()
        if building not in BUILDINGS:
            return await interaction.response.send_message("⚠️ Unknown building.", ephemeral=True)

        # Use the same rate we displayed for consistency:
        wc_cost = trunc2(BUILDINGS[building]["cost"])
        local_cost = trunc2(wc_cost * self.rate)

        bank_local = trunc2(float(await self.cog.config.user(interaction.user).bank()))
        if bank_local + 1e-9 < local_cost:
            return await interaction.response.send_message(
                f"❌ Not enough in bank for **{building}**. "
                f"Need **{local_cost:.2f} {self.currency}**.",
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

        header = f"🏗️ Built **{building}** for **{local_cost:.2f} {self.currency}**."
        embed = await self.cog.make_city_embed(interaction.user, header=header)
        await interaction.response.edit_message(
            embed=embed,
            view=CityMenuView(self.cog, interaction.user, show_admin=self.cog._is_adminish(interaction.user))
        )



class BuildView(ui.View):
    def __init__(self, cog: CityBuilder, author: discord.abc.User, rate: float, currency: str, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.rate = rate
        self.currency = currency
        self.add_item(BuildSelect(cog, rate, currency))
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
        bank_local = trunc2(float(await view.cog.config.user(interaction.user).bank()))
        _, cur = await view.cog._get_rate_currency(interaction.user)
        await interaction.response.send_modal(WithdrawModal(view.cog, max_local=bank_local, currency=cur))

# ====== Store UI ======
class StoreMenuView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(MyListingsBtn())
        self.add_item(AddSellListingBtn())
        #self.add_item(AddBuyOrderBtn())
        self.add_item(BrowseStoresBtn())
        #self.add_item(FulfillBuyOrdersBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True


class MyListingsBtn(ui.Button):
    def __init__(self):
        super().__init__(label="My Listings", style=discord.ButtonStyle.secondary, custom_id="store:mine")

    async def callback(self, interaction: discord.Interaction):
        view: StoreMenuView = self.view  # type: ignore
        e = await view.cog.store_my_listings_embed(interaction.user)
        await interaction.response.edit_message(embed=e, view=StoreManageMyView(view.cog, view.author, view.children[-1].show_admin))  # BackBtn is last


class StoreManageMyView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(RemoveListingBtn())
        self.add_item(RemoveBuyOrderBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id


class AddSellListingBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Add Sell Listing", style=discord.ButtonStyle.success, custom_id="store:addsell")

    async def callback(self, interaction: discord.Interaction):
        view: StoreMenuView = self.view  # type: ignore
        await interaction.response.send_modal(AddSellListingModal(view.cog))


class AddBuyOrderBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Add Buy Order", style=discord.ButtonStyle.success, custom_id="store:addbuy")

    async def callback(self, interaction: discord.Interaction):
        view: StoreMenuView = self.view  # type: ignore
        await interaction.response.send_modal(AddBuyOrderModal(view.cog))


class BrowseStoresBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Browse Stores", style=discord.ButtonStyle.primary, custom_id="store:browse")

    async def callback(self, interaction: discord.Interaction):
        view: StoreMenuView = self.view  # type: ignore
        e = await view.cog.store_browse_embed(interaction.user)
        buyview = StoreBuyView(view.cog, view.author, view.children[-1].show_admin)
        await buyview.select.refresh(interaction.user)
        await interaction.response.edit_message(embed=e, view=buyview)


class FulfillBuyOrdersBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Fulfill Buy Orders", style=discord.ButtonStyle.primary, custom_id="store:fulfill")

    async def callback(self, interaction: discord.Interaction):
        view: StoreMenuView = self.view  # type: ignore
        e = await view.cog.store_fulfill_embed(interaction.user)
        sellview = StoreSellToOrdersView(view.cog, view.author, view.children[-1].show_admin)
        await sellview.select.refresh(interaction.user)
        await interaction.response.edit_message(embed=e, view=sellview)


class RemoveListingBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Remove Sell Listing", style=discord.ButtonStyle.danger, custom_id="store:removesell")

    async def callback(self, interaction: discord.Interaction):
        view: StoreManageMyView = self.view  # type: ignore
        await interaction.response.send_modal(RemoveSellListingModal(view.cog))


class RemoveBuyOrderBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Remove Buy Order", style=discord.ButtonStyle.danger, custom_id="store:removebuy")

    async def callback(self, interaction: discord.Interaction):
        view: StoreManageMyView = self.view  # type: ignore
        await interaction.response.send_modal(RemoveBuyOrderModal(view.cog))


# --------- Modals ----------
class AddSellListingModal(discord.ui.Modal, title="➕ New Sell Listing"):
    name = discord.ui.TextInput(label="Listing name", placeholder="e.g., 9003's Rock Stew", required=True, max_length=60)
    bundle = discord.ui.TextInput(
        label="Bundle (comma list)",
        placeholder="food:1, metal:1",
        required=True
    )
    price = discord.ui.TextInput(
        label="Price (shown in your currency; saved in WC)",
        placeholder="e.g., 25.00",
        required=True
    )
    stock = discord.ui.TextInput(label="Stock units", placeholder="e.g., 10", required=True)

    def __init__(self, cog: "CityBuilder"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        # Parse bundle
        def parse_bundle(s: str) -> Dict[str, int]:
            out: Dict[str, int] = {}
            for part in s.split(","):
                if not part.strip():
                    continue
                if ":" not in part:
                    raise ValueError("Use key:value like food:1")
                k, v = [x.strip().lower() for x in part.split(":", 1)]
                if k == "ore":
                    k = "metal"
                if k not in ("food", "metal", "goods"):
                    raise ValueError(f"Unknown resource '{k}'. Use food, metal, goods.")
                amt = int(v)
                if amt <= 0:
                    raise ValueError("Amounts must be positive integers.")
                out[k] = out.get(k, 0) + amt
            return out
    
        try:
            bundle = parse_bundle(str(self.bundle.value))
            price_local = float(str(self.price.value))
            requested_stock = int(str(self.stock.value))
            if price_local <= 0 or requested_stock <= 0:
                raise ValueError
        except Exception as e:
            return await interaction.response.send_message(f"❌ Invalid input: {e}", ephemeral=True)
    
        # Convert local -> WC (store pure WC)
        price_wc = await self.cog._local_to_wc(interaction.user, price_local)
    
        # Check seller resources and compute craftable stock
        d = await self.cog.config.user(interaction.user).all()
        inv = {k: int(v) for k, v in (d.get("resources") or {}).items()}
    
        def max_units_from_inventory(inv: Dict[str, int], per_unit: Dict[str, int]) -> int:
            if not per_unit:
                return 0
            vals = []
            for r, need in per_unit.items():
                have = int(inv.get(r, 0))
                if need <= 0:
                    return 0
                vals.append(have // need)
            return min(vals) if vals else 0
    
        craftable = max_units_from_inventory(inv, bundle)
        final_stock = min(requested_stock, craftable)
    
        if final_stock <= 0:
            return await interaction.response.send_message(
                "❌ You don’t currently have the resources to back that listing (stock would be 0).",
                ephemeral=True
            )
    
        # ESCROW: remove resources upfront from seller and store on the listing
        escrow_total = self.cog._bundle_mul(bundle, final_stock)
        # Deduct from seller inventory
        await self.cog._adjust_resources(interaction.user, {k: -v for k, v in escrow_total.items()})
    
        # Save listing with escrow
        d = await self.cog.config.user(interaction.user).all()
        lst = list(d.get("store_sell_listings") or [])
        new_id = f"S{random.randint(10_000, 99_999)}"
        lst.append({
            "id": new_id,
            "name": str(self.name.value).strip(),
            "bundle": bundle,
            "price_wc": float(price_wc),
            "stock": int(final_stock),
            "escrow": escrow_total,  # total reserved resources
        })
        await self.cog.config.user(interaction.user).store_sell_listings.set(lst)
    
        e = await self.cog.store_my_listings_embed(
            interaction.user,
            header=f"✅ Added listing **{self.name.value}** at {price_local:.2f} (your currency). "
                   f"Escrowed stock: {final_stock}."
        )
        await interaction.response.send_message(embed=e, ephemeral=True)



class AddBuyOrderModal(discord.ui.Modal, title="➕ New Buy Order"):
    resource = discord.ui.TextInput(label="Resource (food / metal / goods)", required=True)
    qty = discord.ui.TextInput(label="Quantity wanted", required=True)
    price = discord.ui.TextInput(label="Offered price per unit (your currency; saved in WC)", required=True)

    def __init__(self, cog: "CityBuilder"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        r = str(self.resource.value).strip().lower()
        if r == "ore":
            r = "metal"
        if r not in ("food", "metal", "goods"):
            return await interaction.response.send_message("❌ Resource must be food, metal, or goods.", ephemeral=True)
        try:
            qty = int(str(self.qty.value))
            price_local = float(str(self.price.value))
            if qty <= 0 or price_local <= 0:
                raise ValueError
        except Exception:
            return await interaction.response.send_message("❌ Quantity and price must be positive numbers.", ephemeral=True)

        price_wc = await self.cog._local_to_wc(interaction.user, price_local)
        d = await self.cog.config.user(interaction.user).all()
        lst = list(d.get("store_buy_orders") or [])
        new_id = f"B{random.randint(10_000, 99_999)}"
        lst.append({"id": new_id, "resource": r, "qty": qty, "price_wc": float(price_wc)})
        await self.cog.config.user(interaction.user).store_buy_orders.set(lst)
        await interaction.response.send_message(f"✅ Buy order **{new_id}** created: {qty} {r} at {price_local:.2f} (your currency).", ephemeral=True)


class RemoveSellListingModal(discord.ui.Modal, title="🗑️ Remove Sell Listing"):
    listing_id = discord.ui.TextInput(label="Listing ID", placeholder="e.g., S12345", required=True)

    def __init__(self, cog: "CityBuilder"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        lid = str(self.listing_id.value).strip()
        lst = list(await self.cog.config.user(interaction.user).store_sell_listings())
        new = [x for x in lst if x.get("id") != lid]
        if len(new) == len(lst):
            return await interaction.response.send_message("❌ Listing not found.", ephemeral=True)
        await self.cog.config.user(interaction.user).store_sell_listings.set(new)
        await interaction.response.send_message(f"✅ Removed listing **{lid}**.", ephemeral=True)


class RemoveBuyOrderModal(discord.ui.Modal, title="🗑️ Remove Buy Order"):
    order_id = discord.ui.TextInput(label="Order ID", placeholder="e.g., B54321", required=True)

    def __init__(self, cog: "CityBuilder"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        oid = str(self.order_id.value).strip()
        lst = list(await self.cog.config.user(interaction.user).store_buy_orders())
        new = [x for x in lst if x.get("id") != oid]
        if len(new) == len(lst):
            return await interaction.response.send_message("❌ Order not found.", ephemeral=True)
        await self.cog.config.user(interaction.user).store_buy_orders.set(new)
        await interaction.response.send_message(f"✅ Removed order **{oid}**.", ephemeral=True)


# --------- Buyer view (purchase listings) ----------
class StoreBuyView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.select = PurchaseListingSelect(cog)
        self.add_item(self.select)
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id


class PurchaseListingSelect(ui.Select):
    def __init__(self, cog: "CityBuilder"):
        self.cog = cog
        options = []
        # Build options across all users
        options = []  # [(owner_id, listing)]
        # We'll store owner_id in the option value as "ownerId|listingId"
        # Render below in callback
        super().__init__(placeholder="Buy 1 unit from a listing", min_values=1, max_values=1, options=[])
   
    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "none":
            return await interaction.response.send_message("Nothing to buy right now.", ephemeral=True)
        owner_s, lid = value.split("|", 1)
        owner_id = int(owner_s)
        if owner_id == interaction.user.id:
            return await interaction.response.send_message("You can’t buy your own listing.", ephemeral=True)
    
        owner_conf = self.cog.config.user_from_id(owner_id)
        owner_data = await owner_conf.all()
        listings = list(owner_data.get("store_sell_listings") or [])
        listing = next((x for x in listings if x.get("id") == lid), None)
        if not listing:
            return await interaction.response.send_message("Listing unavailable.", ephemeral=True)
    
        eff_stock = self.cog._effective_stock_from_escrow(listing) if hasattr(self.cog, "_effective_stock_from_escrow") else int(listing.get("stock", 0) or 0)
        if eff_stock <= 0:
            # reflect 0 stock for visibility
            listing["stock"] = 0
            for i, it in enumerate(listings):
                if it.get("id") == lid:
                    listings[i] = listing
                    break
            await owner_conf.store_sell_listings.set(listings)
            return await interaction.response.send_message("⚠️ This listing is currently out of stock.", ephemeral=True)
    
        price_wc = float(listing.get("price_wc") or 0.0)
        buyer_price_local = trunc2((await self.cog._wc_to_local(interaction.user, price_wc)) * 1.10)
    
        bundle = {k: int(v) for k, v in (listing.get("bundle") or {}).items()}
        _, buyer_cur = await self.cog._get_rate_currency(interaction.user)
        bundle_txt = ", ".join([f"{k}+{v}" for k, v in bundle.items()]) or "—"
    
        confirm_embed = discord.Embed(
            title="Confirm Purchase",
            description=(
                f"**{listing.get('name')}**\n"
                f"Bundle: {bundle_txt}\n"
                f"Price: **{buyer_price_local:.2f} {buyer_cur}** (incl. 10% fee)\n\n"
                "Do you want to proceed?"
            )
        )
    
        # Send ephemeral confirmation popup
        await interaction.response.send_message(
            embed=confirm_embed,
            view=ConfirmPurchaseView(
                self.cog,
                interaction.user,
                owner_id,
                lid,
                str(listing.get("name") or "Item"),
                bundle,
                price_wc,
                buyer_price_local,
                show_admin=self.cog._is_adminish(interaction.user),
            ),
            ephemeral=True
        )

    async def refresh(self, viewer: discord.abc.User):
        # Build dynamic options with viewer price
        opts: list[discord.SelectOption] = []
        all_users = await self.cog.config.all_users()
        for owner_id, udata in all_users.items():
            if str(owner_id) == str(viewer.id):
                continue  # don't buy from self
            for item in (udata.get("store_sell_listings") or []):
                if int(item.get("stock", 0)) <= 0:
                    continue
                price_wc = float(item.get("price_wc") or 0.0)
                price_local = await self.cog._wc_to_local(viewer, price_wc)
                price_local_fee = trunc2(price_local * 1.10)  # buyer pays 10% fee
                effective_stock = self.cog._effective_stock_from_escrow(item)
                if effective_stock <= 0:
                    continue
                label = f'{item.get("name")} [Stock {effective_stock}]'
                desc = f'Price {price_local_fee:.2f} in your currency (incl. 10% fee)'
                value = f'{owner_id}|{item.get("id")}'
                opts.append(discord.SelectOption(label=label[:100], description=desc[:100], value=value))
        if not opts:
            opts = [discord.SelectOption(label="No available listings", description="—", value="none")]
        self.options = opts


class StoreSellToOrdersView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.select = FulfillOrderSelect(cog)
        self.add_item(self.select)
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id



class FulfillOrderSelect(ui.Select):
    def __init__(self, cog: "CityBuilder"):
        self.cog = cog
        super().__init__(placeholder="Sell 1 unit into a buy order", min_values=1, max_values=1, options=[])

    async def refresh(self, seller: discord.abc.User):
        opts = []
        all_users = await self.cog.config.all_users()
        for owner_id, udata in all_users.items():
            if int(owner_id) == seller.id:
                continue
            for o in (udata.get("store_buy_orders") or []):
                if int(o.get("qty", 0)) <= 0:
                    continue
                res = o.get("resource")
                price_wc = float(o.get("price_wc") or 0.0)
                # Show seller payout in seller currency (w/ 10% fee)
                payout_local = await self.cog._wc_to_local(seller, price_wc)
                payout_local_fee = trunc2(payout_local * 0.90)
                label = f'Order {o.get("id")} · {res} x{int(o.get("qty"))}'
                desc = f'Payout {payout_local_fee:.2f} (your currency, after 10% fee)'
                value = f'{owner_id}|{o.get("id")}'
                opts.append(discord.SelectOption(label=label[:100], description=desc[:100], value=value))
        if not opts:
            opts = [discord.SelectOption(label="No open buy orders", description="—", value="none")]
        self.options = opts
   
    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "none":
            return await interaction.response.send_message("No orders to fulfill.", ephemeral=True)
        buyer_s, oid = value.split("|", 1)
        buyer_id = int(buyer_s)
    
        buyer_conf = self.cog.config.user_from_id(buyer_id)
        buyer_data = await buyer_conf.all()
        orders = list(buyer_data.get("store_buy_orders") or [])
        order = next((x for x in orders if x.get("id") == oid), None)
        if not order or int(order.get("qty", 0)) <= 0:
            return await interaction.response.send_message("Order unavailable.", ephemeral=True)
    
        res = str(order.get("resource") or "").lower()
        if res == "ore":
            res = "metal"
    
        # Seller must have at least 1 unit
        d = await self.cog.config.user(interaction.user).all()
        if int((d.get("resources") or {}).get(res, 0)) <= 0:
            return await interaction.response.send_message(f"❌ You don’t have any **{res}** to sell.", ephemeral=True)
    
        price_wc = float(order.get("price_wc") or 0.0)
        seller_payout_local = trunc2((await self.cog._wc_to_local(interaction.user, price_wc)) * 0.90)
        _, seller_cur = await self.cog._get_rate_currency(interaction.user)
    
        confirm_embed = discord.Embed(
            title="Confirm Sale",
            description=(
                f"Sell **1 {res}** into order **{oid}**\n"
                f"Payout: **{seller_payout_local:.2f} {seller_cur}** (after 10% fee)\n\n"
                "Do you want to proceed?"
            )
        )
    
        await interaction.response.send_message(
            embed=confirm_embed,
            view=ConfirmSellToOrderView(
                self.cog,
                interaction.user,
                buyer_id,
                oid,
                res,
                price_wc,
                seller_payout_local,
                show_admin=self.cog._is_adminish(interaction.user),
            ),
            ephemeral=True
        )





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
