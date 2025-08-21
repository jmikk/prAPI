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
        if content.endswith("city") and (content.startswith("$") or content.startswith("!")
                                         or content.startswith("?") or content.startswith(".")):
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


async def setup(bot: commands.Bot):
    await bot.add_cog(CityBuilder(bot))
