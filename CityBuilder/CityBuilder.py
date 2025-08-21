# citybuilder_buttons.py
import asyncio
import math
from typing import Dict, Optional

import discord
from discord import ui
from redbot.core import commands, Config

# ====== Balance knobs ======
BUILDINGS: Dict[str, Dict] = {
    "farm":    {"cost": 100.0, "upkeep": 2.0, "produces": {"food": 5}},   # per building per tick
    "mine":    {"cost": 200.0, "upkeep": 3.0, "produces": {"metal": 2}},
    "factory": {"cost": 500.0, "upkeep": 5.0, "produces": {"goods": 1}},
}

TICK_SECONDS = 3600  # hourly ticks
NS_USER_AGENT = "9003"  
NS_BASE = "https://www.nationstates.net/cgi-bin/api.cgi"

DEFAULT_SCALES = [46, 1, 10, 39]  # 46 + a few sensible companions; tweak as you like

def normalize_nation(n: str) -> str:
    # NationStates API expects underscores instead of spaces, lowercase
    return n.strip().lower().replace(" ", "_")

def _xml_get_tag(txt: str, tag: str) -> Optional[str]:
    start = txt.find(f"<{tag}>")
    if start == -1:
        return None
    end = txt.find(f"</{tag}>", start)
    if end == -1:
        return None
    return txt[start + len(tag) + 2 : end].strip()

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
        head = xml[sid:e+1]  # e.g., <SCALE id="76">
        # find id="…"
        idpos = head.find('id="')
        if idpos != -1:
            idend = head.find('"', idpos + 4)
            if idend != -1:
                try:
                    scale_id = int(head[idpos + 4:idend])
                except Exception:
                    scale_id = None
            else:
                scale_id = None
        else:
            scale_id = None

        # find SCORE inside this SCALE block
        sc_start = xml.find("<SCORE>", e)
        sc_end = xml.find("</SCORE>", sc_start)
        if sc_start != -1 and sc_end != -1:
            raw = xml[sc_start + 7:sc_end].strip()
            try:
                score = float(raw)
            except Exception:
                score = None
            if scale_id is not None and score is not None:
                out[scale_id] = score

        pos = sc_end if sc_end != -1 else e + 1
    return out

async def _ns_fetch_profile(self, nation_name: str, scales: Optional[list] = None) -> tuple[str, dict]:
    """
    Returns (currency_text, {scale_id: score, ...})
    Using your format: q="currency+census;mode=score;scale=46(+more)"
    """
    nation = _ns_norm_nation(nation_name)
    scales = scales or DEFAULT_SCALES
    # Build the exact q you asked for
    scale_str = "+".join(str(s) for s in scales)
    q = f"currency+census;mode=score;scale={scale_str}"

    headers = {"User-Agent": NS_USER_AGENT}
    params = {"nation": nation, "q": q}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(NS_BASE, params=params) as resp:
            # your pacing pattern
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
            text = await resp.text()

    currency = _xml_get_tag(text, "CURRENCY") or "Credits"
    scores = _xml_get_scales_scores(text)  # e.g., {46: 123.45, 76: 3.2e+15, ...}
    return currency, scores

def trunc2(x: float) -> float:
    """Truncate (not round) to 2 decimals to match Nexus behavior."""
    return math.trunc(float(x) * 100) / 100.0

class DepositModal(discord.ui.Modal, title="🏦 Deposit Wellcoins"):
    amount = discord.ui.TextInput(label="Amount to deposit", placeholder="e.g. 100.50", required=True)

    def __init__(self, cog: "CityBuilder"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = trunc2(float(self.amount.value))
        except ValueError:
            return await interaction.response.send_message("❌ That’s not a number.", ephemeral=True)

        if amt <= 0:
            return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)

        nexus = self.cog.bot.get_cog("NexusExchange")
        if not nexus:
            return await interaction.response.send_message("⚠️ NexusExchange not loaded.", ephemeral=True)

        try:
            await nexus.take_wellcoins(interaction.user, amt, force=False)
        except ValueError:
            return await interaction.response.send_message("❌ Not enough Wellcoins in your wallet.", ephemeral=True)

        bank = trunc2(float(await self.cog.config.user(interaction.user).bank()) + amt)
        await self.cog.config.user(interaction.user).bank.set(bank)

        await interaction.response.send_message(f"✅ Deposited {amt:.2f}. New bank: {bank:.2f}", ephemeral=True)


class WithdrawModal(discord.ui.Modal, title="🏦 Withdraw Wellcoins"):
    amount = discord.ui.TextInput(label="Amount to withdraw", placeholder="e.g. 50", required=True)

    def __init__(self, cog: "CityBuilder"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = trunc2(float(self.amount.value))
        except ValueError:
            return await interaction.response.send_message("❌ That’s not a number.", ephemeral=True)

        if amt <= 0:
            return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)

        bank = trunc2(float(await self.cog.config.user(interaction.user).bank()))
        if bank + 1e-9 < amt:
            return await interaction.response.send_message("❌ Not enough in bank to withdraw that much.", ephemeral=True)

        # deduct from bank
        bank = trunc2(bank - amt)
        await self.cog.config.user(interaction.user).bank.set(bank)

        # credit wallet
        nexus = self.cog.bot.get_cog("NexusExchange")
        if not nexus:
            return await interaction.response.send_message("⚠️ NexusExchange not loaded.", ephemeral=True)

        await nexus.add_wellcoins(interaction.user, amt)
        await interaction.response.send_message(f"✅ Withdrew {amt:.2f}. New bank: {bank:.2f}", ephemeral=True)



class CityBuilder(commands.Cog):
    """
    City planning mini-game using embeds + buttons only.

    Entry trigger: users type `$city` (or '<prefix>city'). We listen in on_message,
    delete their message, and post the interactive panel.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        self.config.register_user(
            resources={},     # {"food": 0, "metal": 0, ...}
            buildings={},     # {"farm": {"count": int}, ...}
            bank=0.0          # Wellcoins reserved for upkeep/wages
        )
        self.task = bot.loop.create_task(self.resource_tick())

    # -------------- lifecycle --------------
    async def cog_unload(self):
        self.task.cancel()

    # -------------- message entry (no text commands needed) --------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Light-weight listener: if a normal user says '<prefix>city' (e.g. '$city'),
        open their city panel. Works for any prefix, and won't trigger on bots.
        """
        if message.author.bot:
            return
        # match common patterns quickly, case-insensitive
        content = message.content.strip().lower()
        if content.endswith("city") and (content.startswith("$"):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass

            embed = await self.make_city_embed(message.author)
            view = CityMenuView(self, message.author, show_admin=self._is_adminish(message.author, message.guild))
            await message.channel.send(embed=embed, view=view)

    def _is_adminish(self, user: discord.abc.User, guild: Optional[discord.Guild]) -> bool:
        if not isinstance(user, discord.Member) or guild is None:
            return False
        p = user.guild_permissions
        return p.administrator or p.manage_guild

        async def _needs_ns_setup(self, user: discord.abc.User) -> bool:
        data = await self.config.user(user).all()
        return not (data.get("ns_nation") and data.get("ns_currency") and data.get("wc_to_local_rate"))

    # ---------- NationStates API ----------
    async def _ns_fetch_profile(self, nation_name: str) -> Tuple[str, str, float]:
        """
        Returns (currency_text, economy_text, econ_score) for the nation.
        Uses shards: currency, economy, census(id=48, mode=score).
        """
        nation = normalize_nation(nation_name)
        params = {
            "nation": nation,
            "q": "currency+census;mode=score;scale=46",
        }
        headers = {"User-Agent": NS_USER_AGENT}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(NS_BASE, params=params) as resp:
                # --- Rate limiting backoff per your strategy ---
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

                text = await resp.text()

        # Very small XML parse (no external deps). Light extraction:
        def _tag(txt, tag):
            start = txt.find(f"<{tag}>")
            if start == -1:
                return None
            end = txt.find(f"</{tag}>", start)
            if end == -1:
                return None
            return txt[start + len(tag) + 2 : end].strip()

        currency = _tag(text, "CURRENCY") or "Credits"
        # Census score for id 48 appears under <CENSUS>...<SCALE id="48"><SCORE>...</SCORE>...
        # Quick extraction:
        score = None
        cpos = text.find('id="48"')
        if cpos != -1:
            s_start = text.find("<SCORE>", cpos)
            s_end = text.find("</SCORE>", s_start)
            if s_start != -1 and s_end != -1:
                try:
                    score = float(text[s_start + 7 : s_end].strip())
                except Exception:
                    score = None

        if score is None:
            score = 50.0  # neutral fallback

        return currency, economy_text, score

    async def _ensure_ns_profile(self, user: discord.abc.User, nation_input: str) -> Optional[str]:
        try:
            currency, scores = await self._ns_fetch_profile(nation_input, scales=DEFAULT_SCALES)
        except Exception as e:
            return f"❌ Failed to reach NationStates API. Try again later.\n`{e}`"
    
        rate, details = self._compute_currency_rate(scores)
    
        await self.config.user(user).ns_nation.set(_ns_norm_nation(nation_input))
        await self.config.user(user).ns_currency.set(currency)
        await self.config.user(user).set_raw("ns_scores", value={str(k): float(v) for k, v in scores.items()})
        await self.config.user(user).wc_to_local_rate.set(rate)
        await self.config.user(user).set_raw("rate_debug", value=details)  # optional: store breakdown for debugging
        return None


    def _softlog(x: float) -> float:
    # smooth log that works from x≈0 upward; shift by 1 to avoid log(0)
        return math.log10(max(0.0, float(x)) + 1.0)

    def _norm(v: float, lo: float, hi: float) -> float:
        # clamp & scale to [0,1]
        if hi <= lo:
            return 0.5
        v = max(lo, min(hi, v))
        return (v - lo) / (hi - lo)
    
    def _invert(p: float) -> float:
        return 1.0 - p
    
    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))
    
    def _weighted_avg(d: dict[int, float], weights: dict[int, float], transforms: dict[int, callable]) -> float:
        num = 0.0
        den = 0.0
        for k, w in weights.items():
            if k in d:
                v = d[k]
                t = transforms.get(k)
                if t:
                    v = t(v)
                num += w * v
                den += abs(w)
        return num / den if den else 0.5
    
    def _make_transforms() -> dict[int, callable]:
        # Per-scale transforms → normalized 0..1
        # Use softlog for very large ranges and pick anchor ranges empirically.
        return {
            46: lambda x: _norm(_softlog(x), 0.0, 6.0),   # if 46 can be huge (e.g., e+15), log it; 0..6 is ~1..10^6
            1:  lambda x: _norm(x, 0.0, 100.0),           # Economy score usually ~0..100
            10: lambda x: _norm(x, 0.0, 100.0),           # Industry score ~0..100
            39: lambda x: _invert(_norm(x, 0.0, 20.0)),   # If 39 = Unemployment (%), invert; tweak hi if your world differs
        }
    
    def _make_weights() -> dict[int, float]:
        # Heavier weight on the primary currency/ER stat, then economy, then others
        return {46: 0.5, 1: 0.3, 10: 0.15, 39: 0.05}
    
    def _map_index_to_rate(idx: float) -> float:
        """
        idx in [0,1] → rate range [0.25, 2.00] with 0.5 ≈ 1.0x.
        Smooth S-curve to avoid wild swings near ends.
        """
        # center at 0.5
        centered = (idx - 0.5) * 2.0  # [-1, 1]
        # gentle curve
        factor = 1.0 + 0.75 * centered  # 0.25..1.75
        return _clamp(trunc2(factor), 0.25, 2.00)


    def _compute_currency_rate(self, scores: dict[int, float]) -> tuple[float, dict]:
        transforms = _make_transforms()
        weights = _make_weights()
    
        # Apply per-scale transforms to 0..1, then weighted average
        contribs = {}
        for sid, fn in transforms.items():
            raw = scores.get(sid)
            if raw is None:
                continue
            contribs[sid] = fn(raw)  # 0..1 per scale
    
        idx = _weighted_avg(scores, weights, transforms)  # 0..1
        rate = _map_index_to_rate(idx)  # 1 WC = rate × Local
    
        debug = {
            "scores": {str(k): scores[k] for k in scores},
            "contribs": {str(k): contribs.get(k) for k in transforms},
            "index": idx,
            "rate": rate,
            "weights": {str(k): weights[k] for k in weights},
        }
        return rate, debug



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
        """
        Upkeep comes ONLY from the user's Bank. If fully paid, produce resources.
        If bank can't cover full upkeep, skip production for this tick.
        """
        nexus = self.bot.get_cog("NexusExchange")
        if not nexus:
            return

        data = await self.config.user(user).all()
        buildings = data.get("buildings", {})
        if not buildings:
            return

        # compute upkeep
        total_upkeep = 0.0
        for b, info in buildings.items():
            if b in BUILDINGS:
                total_upkeep += BUILDINGS[b]["upkeep"] * int(info.get("count", 0))
        total_upkeep = trunc2(total_upkeep)

        # pay from bank only
        bank = trunc2(float(data.get("bank", 0.0)))
        if bank + 1e-9 < total_upkeep:
            return  # insufficient → halt production

        bank = trunc2(bank - total_upkeep)

        # produce
        new_resources = dict(data.get("resources", {}))
        for b, info in buildings.items():
            if b not in BUILDINGS:
                continue
            cnt = int(info.get("count", 0))
            if cnt <= 0:
                continue
            for res, amt in BUILDINGS[b]["produces"].items():
                new_resources[res] = int(new_resources.get(res, 0)) + int(amt * cnt)

        # persist
        await self.config.user(user).resources.set(new_resources)
        await self.config.user(user).bank.set(bank)

    # -------------- embeds & helpers --------------
    async def make_city_embed(self, user: discord.abc.User, header: Optional[str] = None) -> discord.Embed:
        data = await self.config.user(user).all()
        res = data.get("resources", {})
        bld = data.get("buildings", {})
        bank = trunc2(float(data.get("bank", 0.0)))

        upkeep = 0.0
        for b, info in bld.items():
            if b in BUILDINGS:
                upkeep += BUILDINGS[b]["upkeep"] * int(info.get("count", 0))
        upkeep = trunc2(upkeep)

        desc = "Use the buttons below to manage your city."
        if header:
            desc = f"{header}\n\n{desc}"

        e = discord.Embed(title=f"🌆 {getattr(user, 'display_name', 'Your')} City", description=desc)
        if bld:
            btxt = "\n".join(f"• **{b}** × {info.get('count', 0)}" for b, info in bld.items())
        else:
            btxt = "None"
        if res:
            rtxt = "\n".join(f"• **{k}**: {v}" for k, v in res.items())
        else:
            rtxt = "None"

        e.add_field(name="🏗️ Buildings", value=btxt, inline=False)
        e.add_field(name="📦 Resources", value=rtxt, inline=False)
        e.add_field(name="🏦 Bank", value=f"{bank:.2f} Wellcoins", inline=True)
        e.add_field(name="⏳ Upkeep per Tick", value=f"{upkeep:.2f} Wellcoins", inline=True)

        # When building the city embed:
        d = await self.config.user(user).all()
        rate = float(d.get("wc_to_local_rate") or 1.0)
        currency = d.get("ns_currency") or "Local Credits"
        e.add_field(
            name="🌍 Exchange",
            value=f"1 WC = **{rate:.2f} {currency}** (personalized to your nation)",
            inline=False
        )

        return e

    def build_help_embed(self) -> discord.Embed:
        e = discord.Embed(
            title="🏗️ Build",
            description="Pick a building below to buy **1 unit** (costs your **wallet** Wellcoins)."
        )
        lines = []
        for k, v in BUILDINGS.items():
            produces = ", ".join(f"{r}+{a}/tick" for r, a in v["produces"].items())
            lines.append(f"**{k}** — Cost `{v['cost']:.2f}` | Upkeep `{v['upkeep']:.2f}` | Produces {produces}")
        e.add_field(name="Catalog", value="\n".join(lines), inline=False)
        return e
    
    async def bank_help_embed(self, user: discord.abc.User) -> discord.Embed:
        bank = trunc2(float(await self.config.user(user).bank()))
        e = discord.Embed(
            title="🏦 Bank",
            description="Your **Bank** pays wages/upkeep each tick. "
                        "If the bank can’t cover upkeep, **production halts**."
        )
        e.add_field(name="Current Balance", value=f"{bank:.2f} Wellcoins", inline=False)
        e.add_field(
            name="Tips",
            value="• Deposit from wallet → bank\n"
                  "• Withdraw bank → wallet\n"
                  "• Balance is shown above",
            inline=False,
        )
        return e


    async def wait_for_amount(self, channel_id: int, author: discord.abc.User) -> Optional[float]:
        """Prompted numeric input helper (30s timeout)."""
        def check(m: discord.Message):
            return m.author.id == author.id and m.channel and m.channel.id == channel_id
        try:
            msg = await self.bot.wait_for("message", timeout=30.0, check=check)
            amt = float(msg.content.strip().replace(",", ""))
            return trunc2(amt)
        except asyncio.TimeoutError:
            return None
        except ValueError:
            return None


# ====== UI: Main Menu ======
class CityMenuView(ui.View):
    def __init__(self, cog: CityBuilder, author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author

        # Buttons
        self.add_item(ViewBtn())
        self.add_item(BuildBtn())
        self.add_item(BankBtn())
        if show_admin:
            self.add_item(NextDayBtn())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Type `$city` to open your own.", ephemeral=True)
            return False
        return True


class ViewBtn(ui.Button):
    def __init__(self):
        super().__init__(label="View", style=discord.ButtonStyle.primary, custom_id="city:view")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        embed = await view.cog.make_city_embed(interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)


class BuildBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Build", style=discord.ButtonStyle.success, custom_id="city:build")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        await interaction.response.edit_message(
            embed=view.cog.build_help_embed(),
            view=BuildView(view.cog, view.author, show_admin=any(isinstance(i, NextDayBtn) for i in view.children)),
        )


class BankBtn(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Bank", style=discord.ButtonStyle.secondary, custom_id="city:bank")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        embed = await view.cog.bank_help_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=BankView(view.cog, view.author, show_admin=any(isinstance(i, NextDayBtn) for i in view.children)),
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
                description=f"Cost {cog_cost(cog, name):.2f}, Upkeep {BUILDINGS[name]['upkeep']:.2f}"
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
        nexus = self.cog.bot.get_cog("NexusExchange")
        if not nexus:
            return await interaction.response.send_message("⚠️ NexusExchange not loaded.", ephemeral=True)

        cost = trunc2(BUILDINGS[building]["cost"])
        try:
            await nexus.take_wellcoins(interaction.user, cost, force=False)
        except ValueError:
            return await interaction.response.send_message(
                f"❌ Not enough Wellcoins in your wallet for **{building}**. Cost: {cost:.2f}",
                ephemeral=True
            )

        # add building
        bld = await self.cog.config.user(interaction.user).buildings()
        cur = int(bld.get(building, {}).get("count", 0))
        bld[building] = {"count": cur + 1}
        await self.cog.config.user(interaction.user).buildings.set(bld)

        embed = await self.cog.make_city_embed(interaction.user, header=f"🏗️ Built **{building}** for {cost:.2f} Wellcoins!")
        await interaction.response.edit_message(
            embed=embed,
            view=CityMenuView(self.cog, interaction.user, show_admin=self.cog._is_adminish(interaction.user, interaction.guild))
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
            await interaction.response.send_message("This panel isn’t yours. Type `$city` to open your own.", ephemeral=True)
            return False
        return True


# ====== UI: Bank flow ======
class BankView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(BankDepositBtn())
        self.add_item(BankWithdrawBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Type `$city` to open your own.", ephemeral=True)
            return False
        return True



class BankBalanceBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Balance", style=discord.ButtonStyle.primary, custom_id="city:bank:bal")

    async def callback(self, interaction: discord.Interaction):
        view: BankView = self.view  # type: ignore
        bank = trunc2(float(await view.cog.config.user(interaction.user).bank()))
        await interaction.response.send_message(f"🏦 Bank balance: {bank:.2f} Wellcoins", ephemeral=True)


class BankDepositBtn(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Deposit", style=discord.ButtonStyle.success, custom_id="city:bank:dep")

    async def callback(self, interaction: discord.Interaction):
        view: BankView = self.view  # type: ignore
        await interaction.response.send_modal(DepositModal(view.cog))


class BankWithdrawBtn(discord.ui.Button):
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
def cog_cost(cog: CityBuilder, name: str) -> float:
    return trunc2(BUILDINGS[name]["cost"])
