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
  "house": {
    "cost": 100.0,
    "inputs": {},
    "upkeep": 0,
    "tier": 0
  },

  # ----- Tier 1 -----
  "Farm": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"food": 1},
    "upkeep": 0,
    "tier": 1
  },
  "Mine": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"ore": 1},
    "upkeep": 0,
    "tier": 1
  },
  "Lumberyard": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"wood": 1},
    "upkeep": 0,
    "tier": 1
  },
  "Mana fountain": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"Mana": 1},
    "upkeep": 0,
    "tier": 1
  },
  "Cow": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"milk": 1},
    "upkeep": 0,
    "tier": 1
  },
  "Goblin Camp": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"Goblin teeth": 1},
    "upkeep": 0,
    "tier": 1
  },
  "Fairy Grove": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"Fairy dust": 1},
    "upkeep": 0,
    "tier": 1
  },
  "oil well": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"oil": 1},
    "upkeep": 0,
    "tier": 1
  },
  "Sheep Pasture": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"wool": 1},
    "upkeep": 0,
    "tier": 1
  },
  "garden": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"herb": 1},
    "upkeep": 0,
    "tier": 1
  },
  "salt flats": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"salt": 1},
    "upkeep": 0,
    "tier": 1
  },
  "Fishery": {
    "cost": 100.0,
    "inputs": {},
    "produces": {"fish": 1},
    "upkeep": 0,
    "tier": 1
  },

  # ----- Tier 2 -----
  "smokehouse": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "food": 1, "fish": 1 },
    "produces": { "dried meat": 1 },
    "tier": 2
  },
  "forge kitchen": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "ore": 1, "food": 1 },
    "produces": { "iron rations": 1 },
    "tier": 2
  },
  "blacksmiths forge": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "wood": 1, "ore": 1 },
    "produces": { "weapons": 1 },
    "tier": 2
  },
  "Enchanter’s Workshop": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "Mana": 1, "wood": 1 },
    "produces": { "magic staff": 1 },
    "tier": 2
  },
  "Altar of Purity": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "milk": 1, "Mana": 1 },
    "produces": { "Blessed cheese": 1 },
    "tier": 2
  },
  "Witch’s Cauldron": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "Goblin teeth": 1, "milk": 1 },
    "produces": { "cursed brew": 1 },
    "tier": 2
  },
  "Fey Altar": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "Fairy dust": 1, "Goblin teeth": 1 },
    "produces": { "Charm Amulet": 1 },
    "tier": 2
  },
  "Arcane Lampworks": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "oil": 1, "Fairy dust": 1 },
    "produces": { "Enchanted Lantern": 1 },
    "tier": 2
  },
  "Oil Weaver’s Hall": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "wool": 1, "oil": 1 },
    "produces": { "Oily Rags": 1 },
    "tier": 2
  },
  "Druid’s Hut": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "herb": 1, "wool": 1 },
    "produces": { "Healing Poultice": 1 },
    "tier": 2
  },
  "Apothecary": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "salt": 1, "herb": 1 },
    "produces": { "Preservation Tonic": 1 },
    "tier": 2
  },
  "Sea Shrine": {
    "cost": 300.0,
    "upkeep": 10,
    "inputs": { "fish": 1, "salt": 1 },
    "produces": { "Dreid Kraken Jerky": 1 },
    "tier": 2
  },

  # ----- Tier 3 -----
  "Hunter’s Lodge": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "dried meat": 1, "Dreid Kraken Jerky": 1 },
    "produces": { "Beast Provisions": 1 },
    "tier": 3
  },
  "War Camp": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "iron rations": 1, "dried meat": 1 },
    "produces": { "Soldier Supplies": 1 },
    "tier": 3
  },
  "Armory Barracks": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "weapons": 1, "iron rations": 1 },
    "produces": { "Armed Troops": 1 },
    "tier": 3
  },
  "Wizard Forge": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "magic staff": 1, "weapons": 1 },
    "produces": { "Arcane Weaponry": 1 },
    "tier": 3
  },
  "Cathedral Armory": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "Blessed cheese": 1, "magic staff": 1 },
    "produces": { "Holy Relic": 1 },
    "tier": 3
  },
  "Blighted Chapel": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "cursed brew": 1, "Blessed cheese": 1 },
    "produces": { "Corrupted Icon": 1 },
    "tier": 3
  },
  "Dark Shrine": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "Charm Amulet": 1, "cursed brew": 1 },
    "produces": { "Hexed Relic": 1 },
    "tier": 3
  },
  "Oracle’s Tower": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "Enchanted Lantern": 1, "Charm Amulet": 1 },
    "produces": { "Vision Crystal": 1 },
    "tier": 3
  },
  "Pyromancer’s Lab": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "Oily Rags": 1, "Enchanted Lantern": 1 },
    "produces": { "Firebomb": 1 },
    "tier": 3
  },
  "Battlefield Tent": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "Healing Poultice": 1, "Oily Rags": 1 },
    "produces": { "First Aid Pack": 1 },
    "tier": 3
  },
  "Alchemical Lab": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "Preservation Tonic": 1, "Healing Poultice": 1 },
    "produces": { "Elixir of Life": 1 },
    "tier": 3
  },
  "Temple of the Deep": {
    "cost": 400.0,
    "upkeep": 15,
    "inputs": { "Dreid Kraken Jerky": 1, "Preservation Tonic": 1 },
    "produces": { "Tear of the Kraken": 1 },
    "tier": 3
  },

  # ----- Tier 4 -----
  "Grand Market": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Beast Provisions": 1, "Tear of the Kraken": 1 },
    "produces": { "Wealth": 1 },
    "tier": 4
  },
  "Bloodforge": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Soldier Supplies": 1, "Beast Provisions": 1 },
    "produces": { "Warspawn": 1 },
    "tier": 4
  },
  "War Academy": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Armed Troops": 1, "Soldier Supplies": 1 },
    "produces": { "Elite Army": 1 },
    "tier": 4
  },
  "Battle Mage Citadel": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Arcane Weaponry": 1, "Armed Troops": 1 },
    "produces": { "War Mages": 1 },
    "tier": 4
  },
  "Sacred Armory": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Holy Relic": 1, "Arcane Weaponry": 1 },
    "produces": { "Divine Crusaders": 1 },
    "tier": 4
  },
  "Desecrated Cathedral": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Corrupted Icon": 1, "Holy Relic": 1 },
    "produces": { "Fallen Paladins": 1 },
    "tier": 4
  },
  "Cabal Sanctum": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Hexed Relic": 1, "Corrupted Icon": 1 },
    "produces": { "Dark Cultists": 1 },
    "tier": 4
  },
  "Oracle Spire": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Vision Crystal": 1, "Hexed Relic": 1 },
    "produces": { "Prophecy Scrolls": 1 },
    "tier": 4
  },
  "Siege Workshop": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Firebomb": 1, "Vision Crystal": 1 },
    "produces": { "Demolition Squad": 1 },
    "tier": 4
  },
  "Field Hospital": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "First Aid Pack": 1, "Firebomb": 1 },
    "produces": { "War Medics": 1 },
    "tier": 4
  },
  "Alchemical Sanctuary": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Elixir of Life": 1, "First Aid Pack": 1 },
    "produces": { "Immortal Guard": 1 },
    "tier": 4
  },
  "Temple of the Abyss": {
    "cost": 1000.0,
    "upkeep": 40,
    "inputs": { "Tear of the Kraken": 1, "Elixir of Life": 1 },
    "produces": { "Kraken-Blessed Chosen": 1 },
    "tier": 4
  },

  # ----- Tier 5 -----
  "Abyssal Throne": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Wealth": 1, "Kraken-Blessed Chosen": 1 },
    "produces": { "Kraken Dominion": 1 },
    "tier": 5
  },
  "Blood Market": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Warspawn": 1, "Wealth": 1 },
    "produces": { "Mercenary Legion": 1 },
    "tier": 5
  },
  "Grand Fortress": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Elite Army": 1, "Warspawn": 1 },
    "produces": { "Conqueror Host": 1 },
    "tier": 5
  },
  "Arcane War College": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "War Mages": 1, "Elite Army": 1 },
    "produces": { "Spellbound Battalion": 1 },
    "tier": 5
  },
  "Sanctified Citadel": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Divine Crusaders": 1, "War Mages": 1 },
    "produces": { "Holy Inquisition": 1 },
    "tier": 5
  },
  "Twilight Abbey": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Fallen Paladins": 1, "Divine Crusaders": 1 },
    "produces": { "Oathbreakers": 1 },
    "tier": 5
  },
  "Obsidian Pyramid": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Dark Cultists": 1, "Fallen Paladins": 1 },
    "produces": { "Shadow Hierarchy": 1 },
    "tier": 5
  },
  "Temple of Oracles": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Prophecy Scrolls": 1, "Dark Cultists": 1 },
    "produces": { "Fateweavers": 1 },
    "tier": 5
  },
  "Siege Foundry": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Demolition Squad": 1, "Prophecy Scrolls": 1 },
    "produces": { "War Machines": 1 },
    "tier": 5
  },
  "Sanctum of Mercy": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "War Medics": 1, "Demolition Squad": 1 },
    "produces": { "Battle Chaplains": 1 },
    "tier": 5
  },
  "Hall of Eternity": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Immortal Guard": 1, "War Medics": 1 },
    "produces": { "Eternal Vanguard": 1 },
    "tier": 5
  },
  "Abyssal Monastery": {
    "cost": 1200.0,
    "upkeep": 50,
    "inputs": { "Kraken-Blessed Chosen": 1, "Immortal Guard": 1 },
    "produces": { "Heralds of the Deep": 1 },
    "tier": 5
  },

  # ----- Tier 6 -----
  "Empire of the Deep": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Abyssal Throne": 1, "Abyssal Monastery": 1 },
    "produces": { "Kraken Imperium": 1 },
    "tier": 6
  },
  "Council of Chains": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Blood Market": 1, "Abyssal Throne": 1 },
    "produces": { "Slaver Dynasties": 1 },
    "tier": 6
  },
  "Iron Dominion": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Grand Fortress": 1, "Blood Market": 1 },
    "produces": { "Warlord Kingdoms": 1 },
    "tier": 6
  },
  "Mage Conclave": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Arcane War College": 1, "Grand Fortress": 1 },
    "produces": { "Arcane Dominion": 1 },
    "tier": 6
  },
  "High Theocracy": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Sanctified Citadel": 1, "Arcane War College": 1 },
    "produces": { "Eternal Church": 1 },
    "tier": 6
  },
  "Order of Twilight": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Twilight Abbey": 1, "Sanctified Citadel": 1 },
    "produces": { "Dusk Crusaders": 1 },
    "tier": 6
  },
  "Night Court": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Obsidian Pyramid": 1, "Twilight Abbey": 1 },
    "produces": { "Shadow Empire": 1 },
    "tier": 6
  },
  "Council of Prophets": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Temple of Oracles": 1, "Obsidian Pyramid": 1 },
    "produces": { "Fate Dominion": 1 },
    "tier": 6
  },
  "Engineer's Guildhall": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Siege Foundry": 1, "Temple of Oracles": 1 },
    "produces": { "Colossus Engines": 1 },
    "tier": 6
  },
  "Order of Mercy": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Sanctum of Mercy": 1, "Siege Foundry": 1 },
    "produces": { "Holy Hospitallers": 1 },
    "tier": 6
  },
  "Pantheon’s Vault": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Hall of Eternity": 1, "Sanctum of Mercy": 1 },
    "produces": { "Demi-Gods": 1 },
    "tier": 6
  },
  "Rite of Abyss": {
    "cost": 18000.0,
    "upkeep": 90,
    "inputs": { "Abyssal Monastery": 1, "Hall of Eternity": 1 },
    "produces": { "Deep Ascendants": 1 },
    "tier": 6
  },

  # ----- Tier 7 -----
  "Abyssal Convergence": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Kraken Imperium": 1, "Deep Ascendants": 1 },
    "produces": { "World-Eater Cult": 1 },
    "tier": 7
  },
  "Throne of Chains": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Slaver Dynasties": 1, "Kraken Imperium": 1 },
    "produces": { "Tyrant Overlords": 1 },
    "tier": 7
  },
  "Bloodforged Empire": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Warlord Kingdoms": 1, "Slaver Dynasties": 1 },
    "produces": { "Eternal Conquerors": 1 },
    "tier": 7
  },
  "Grand Arcanum": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Arcane Dominion": 1, "Warlord Kingdoms": 1 },
    "produces": { "Spellforged Empire": 1 },
    "tier": 7
  },
  "Celestial Synod": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Eternal Church": 1, "Arcane Dominion": 1 },
    "produces": { "Divine Hierarchs": 1 },
    "tier": 7
  },
  "Crimson Cathedral": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Dusk Crusaders": 1, "Eternal Church": 1 },
    "produces": { "Twilight Zealots": 1 },
    "tier": 7
  },
  "Crown of Midnight": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Shadow Empire": 1, "Dusk Crusaders": 1 },
    "produces": { "Umbral Sovereigns": 1 },
    "tier": 7
  },
  "Prophet-King’s Court": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Fate Dominion": 1, "Shadow Empire": 1 },
    "produces": { "Destiny Weavers": 1 },
    "tier": 7
  },
  "Titan Forge": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Colossus Engines": 1, "Fate Dominion": 1 },
    "produces": { "Living War Machines": 1 },
    "tier": 7
  },
  "Sanctum of Steel": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Holy Hospitallers": 1, "Colossus Engines": 1 },
    "produces": { "Paladins of Iron": 1 },
    "tier": 7
  },
  "Celestial Ascent": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Demi-Gods": 1, "Holy Hospitallers": 1 },
    "produces": { "Minor Deities": 1 },
    "tier": 7
  },
  "Abyssal Apotheosis": {
    "cost": 24500.0,
    "upkeep": 105,
    "inputs": { "Deep Ascendants": 1, "Demi-Gods": 1 },
    "produces": { "Eldritch Gods": 1 },
    "tier": 7
  },

  # ----- Tier 8 -----
  "The Abyss Awakens": {
    "cost": 65000.0,
    "upkeep": 160,
    "inputs": {
      "World-Eater Cult": 1,
      "Eldritch Gods": 1,
      "Umbral Sovereigns": 1,
      "Twilight Zealots": 1
    },
    "produces": { "Team Drowned World tokens": 1 },
    "tier": 8
  },
  "The Eternal Dominion": {
    "cost": 65000.0,
    "upkeep": 160,
    "inputs": {
      "Tyrant Overlords": 1,
      "Eternal Conquerors": 1,
      "Spellforged Empire": 1,
      "Living War Machines": 1
    },
    "produces": { "Team Iron Empire tokens": 1 },
    "tier": 8
  },
  "The Ascended Pantheon": {
    "cost": 65000.0,
    "upkeep": 160,
    "inputs": {
      "Divine Hierarchs": 1,
      "Destiny Weavers": 1,
      "Paladins of Iron": 1,
      "Minor Deities": 1
    },
    "produces": { "Team Celestial Nexus tokens": 1 },
    "tier": 8
  }
}


# Per-worker wage (in WC) per tick; user pays in local currency at their rate
WORKER_WAGE_WC = 5.0


TICK_SECONDS = 3600  # hourly ticks

# ====== NationStates config ======
NS_USER_AGENT = "9005"
NS_BASE = "https://www.nationstates.net/cgi-bin/api.cgi"

# Default composite: 46 + a few companions (tweak freely)
DEFAULT_SCALES = [46, 1, 10, 39]

class ResourceRecycleBtn(ui.Button):
    def __init__(self, resource: str):
        super().__init__(label=f"♻️ {resource}", style=discord.ButtonStyle.secondary)
        self.resource = resource

    async def callback(self, interaction: discord.Interaction):
        view: ResourcesTierDetailView = self.view  # type: ignore
        await interaction.response.send_modal(RecycleResourceQtyModal(view.cog, self.resource))


class RecycleResourceQtyModal(discord.ui.Modal, title="♻️ Recycle Resources → Scrap"):
    def __init__(self, cog: "CityBuilder", resource_name: str):
        super().__init__()
        self.cog = cog
        self.resource_name = resource_name
        self.qty = discord.ui.TextInput(label=f"How many **{resource_name}** to recycle?", placeholder="e.g., 10", required=True)
        self.add_item(self.qty)

    async def on_submit(self, interaction: discord.Interaction):
        res = self.resource_name.strip().lower()
        if res == "ore":
            res = "metal"
        try:
            qty = int(str(self.qty.value))
            if qty <= 0:
                raise ValueError
        except Exception:
            return await interaction.response.send_message("❌ Quantity must be a positive integer.", ephemeral=True)

        d = await self.cog.config.user(interaction.user).all()
        inv = {k: int(v) for k, v in (d.get("resources") or {}).items()}
        have = int(inv.get(res, 0))
        if have < qty:
            return await interaction.response.send_message(
                f"❌ You only have **{have} {res}**.", ephemeral=True
            )

        scrap_gain = self.cog._scrap_from_resource(res, qty)
        await self.cog._adjust_resources(interaction.user, {res: -qty, "scrap": scrap_gain})

        e = await self.cog.make_city_embed(
            interaction.user,
            header=f"♻️ Recycled **{qty} {res}** → **{scrap_gain} scrap**."
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

class ResourcesTierDetailView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, tier: int, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.tier = int(tier)
        self.show_admin = show_admin

        # Add a recycle button for every resource mapped to this tier
        r2t = self.cog._resource_tier_map()
        tier_resources = [r for r, t in r2t.items() if int(t) == self.tier]
        for r in sorted(tier_resources):
            self.add_item(ResourceRecycleBtn(r))

        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True



class WorkersTiersMenuView(discord.ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.show_admin = show_admin

        # TIER BUTTONS (above)
        for t in self.cog._all_tiers():
            btn = WorkersTierButton(t)
            # leave rows for auto-placement so they sit above the bottom row
            self.add_item(btn)

        # ACTION ROW (bottom)
        hire_btn = HireWorkerBtn()
        fire_btn = FireWorkerBtn()
        back_btn = BackBtn(show_admin)

        # Pin these to the bottom row so tiers stay above them
        hire_btn.row = 4
        fire_btn.row = 4
        back_btn.row = 4

        self.add_item(hire_btn)
        self.add_item(fire_btn)
        self.add_item(back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True


class WorkersBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Workers", style=discord.ButtonStyle.secondary, custom_id="city:workers")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        embed = await view.cog.workers_overview_by_tier_embed(interaction.user)
        await interaction.response.edit_message(
            embed=embed,
            view=WorkersTiersMenuView(view.cog, view.author, show_admin=view.show_admin),
        )


class WorkersTierButton(ui.Button):
    def __init__(self, tier: int):
        super().__init__(label=f"Tier {tier}", style=discord.ButtonStyle.primary, custom_id=f"city:workers:tier:{tier}")
        self.tier = int(tier)

    async def callback(self, interaction: discord.Interaction):
        menu: WorkersTiersMenuView = self.view  # type: ignore
        e = await menu.cog.workers_tier_detail_embed(interaction.user, self.tier)
        await interaction.response.edit_message(
            embed=e,
            view=WorkersTierView(menu.cog, menu.author, self.tier, menu.show_admin),  # 👈 pass tier!
        )




class BuildingsTierActionsView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, tier: int, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.tier = int(tier)
        self.show_admin = show_admin

        # Collect names for this tier
        build_names = []
        recycle_names = []

        for name, meta in BUILDINGS.items():
            if int(meta.get("tier", 0)) == self.tier:
                build_names.append(name)
                if name.lower() != "house":  # usually you don't "recycle" housing
                    recycle_names.append(name)

        # Add Build buttons first
        for name in build_names:
            self.add_item(BuildInTierBtn(name))

        # Then add Recycle buttons
        for name in recycle_names:
            self.add_item(RecycleBuildingInTierBtn(name))

        # Finally, add the back button
        self.add_item(BackToTiersBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "This panel isn’t yours. Use `$city` to open your own.", ephemeral=True
            )
            return False
        return True



class WorkersTierView(discord.ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, tier: int, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.tier = tier
        self.show_admin = show_admin

        # Dynamically add one assign + one unassign button per building in this tier
        for name, meta in sorted(BUILDINGS.items()):
            if int(meta.get("tier", 0)) == int(tier) and name != "house":
                self.add_item(AssignWorkerToBuildingBtn(name))
                self.add_item(UnassignWorkerFromBuildingBtn(name))

        self.add_item(BackToWorkersTiersBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True

class AssignWorkerToBuildingBtn(discord.ui.Button):
    def __init__(self, building: str):
        super().__init__(label=f"+ {building}", style=discord.ButtonStyle.success)
        self.building = building

    async def callback(self, interaction: discord.Interaction):
        view: WorkersTierView = self.view  # type: ignore
        cog = view.cog
        user = interaction.user

        d = await cog.config.user(user).all()
        st = await cog._get_staffing(user)
        owned = int((d.get("buildings") or {}).get(self.building, {}).get("count", 0))
        if owned <= 0:
            return await interaction.response.send_message(f"❌ You don’t own any {self.building}.", ephemeral=True)

        if int(d.get("workers_unassigned") or 0) <= 0:
            return await interaction.response.send_message("❌ No unassigned workers available.", ephemeral=True)

        if st.get(self.building, 0) >= owned:
            return await interaction.response.send_message(f"❌ All {self.building} are already staffed.", ephemeral=True)

        st[self.building] = st.get(self.building, 0) + 1
        await cog._set_staffing(user, st)
        await cog.config.user(user).workers_unassigned.set(int(d.get("workers_unassigned") or 0) - 1)

        e = await cog.workers_tier_detail_embed(user, view.tier)
        await interaction.response.edit_message(embed=e, view=view)


class UnassignWorkerFromBuildingBtn(discord.ui.Button):
    def __init__(self, building: str):
        super().__init__(label=f"– {building}", style=discord.ButtonStyle.danger)  # red
        self.building = building

    async def callback(self, interaction: discord.Interaction):
        view: WorkersTierView = self.view  # type: ignore
        cog = view.cog
        user = interaction.user

        st = await cog._get_staffing(user)
        if st.get(self.building, 0) <= 0:
            return await interaction.response.send_message(f"❌ No workers assigned to {self.building}.", ephemeral=True)

        st[self.building] -= 1
        await cog._set_staffing(user, st)
        un = int((await cog.config.user(user).workers_unassigned()) or 0) + 1
        await cog.config.user(user).workers_unassigned.set(un)

        e = await cog.workers_tier_detail_embed(user, view.tier)
        await interaction.response.edit_message(embed=e, view=view)


class BackToWorkersTiersBtn(ui.Button):
    def __init__(self, show_admin: bool):
        super().__init__(label="Back to Tiers", style=discord.ButtonStyle.secondary, custom_id="city:workers:tiers:back")
        self.show_admin = show_admin

    async def callback(self, interaction: discord.Interaction):
        detail: WorkersTierActionsView | WorkersTierView = self.view  # type: ignore
        e = await detail.cog.workers_overview_by_tier_embed(interaction.user)
        await interaction.response.edit_message(
            embed=e,
            view=WorkersTiersMenuView(detail.cog, detail.author, show_admin=self.show_admin),
        )





class BuildInTierBtn(ui.Button):
    def __init__(self, bname: str):
        # label shows the building name; we’ll show local price in the ephemeral error/confirm text
        super().__init__(label=f"Build {bname}", style=discord.ButtonStyle.success, custom_id=f"city:build:tier:{bname}")
        self.bname = bname

    async def callback(self, interaction: discord.Interaction):
        view: BuildingsTierActionsView = self.view  # type: ignore
        cog = view.cog
        user = interaction.user

        if self.bname not in BUILDINGS:
            return await interaction.response.send_message("⚠️ Unknown building.", ephemeral=True)

        # Compute current local price from WC cost
        wc_cost = trunc2(float(BUILDINGS[self.bname].get("cost", 0.0)))
        rate, cur = await cog._get_rate_currency(user)
        local_cost = trunc2(wc_cost * rate)

        # Check bank balance
        bank_local = trunc2(float(await cog.config.user(user).bank()))
        if bank_local + 1e-9 < local_cost:
            return await interaction.response.send_message(
                f"❌ Not enough in bank for **{self.bname}**. Need **{local_cost:,.2f} {cur}**.",
                ephemeral=True
            )

        # Deduct local, add building
        await cog.config.user(user).bank.set(trunc2(bank_local - local_cost))
        bld = await cog.config.user(user).buildings()
        curcnt = int((bld.get(self.bname) or {}).get("count", 0))
        bld[self.bname] = {"count": curcnt + 1}
        await cog.config.user(user).buildings.set(bld)

        # Refresh the tier details (so the new owned count shows), keep the action buttons
        header = f"🏗️ Built **{self.bname}** for **{local_cost:,.2f} {cur}**."
        e = await cog.buildings_tier_embed(user, view.tier)
        if e.description:
            e.description = f"{header}\n\n{e.description}"
        else:
            e.description = header

        await interaction.response.edit_message(embed=e, view=view)


class BackToTiersBtn(ui.Button):
    def __init__(self, show_admin: bool):
        super().__init__(label="Back to Tiers", style=discord.ButtonStyle.secondary, custom_id="city:buildings:tiers:back")
        self.show_admin = show_admin

    async def callback(self, interaction: discord.Interaction):
        view: BuildingsTierActionsView = self.view  # type: ignore
        tier_view = BuildingsTierView(view.cog, view.author, show_admin=self.show_admin)
        e = await view.cog.buildings_overview_embed(interaction.user)
        await interaction.response.edit_message(embed=e, view=tier_view)


class RecycleBuildingSelect(ui.Select):
    def __init__(self, cog: "CityBuilder"):
        self.cog = cog
        # List only buildings the user owns (>0)
        options = []
        # We'll fill options at refresh-time in callback if needed,
        # but building an initial generic list keeps UI responsive.
        for name in BUILDINGS.keys():
            options.append(discord.SelectOption(label=name))
        super().__init__(placeholder="Choose a building to recycle", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        bname = self.values[0]
        # Ask for quantity in a modal
        await interaction.response.send_modal(RecycleBuildingQtyModal(self.cog, bname))

class RecycleBuildingInTierBtn(ui.Button):
    def __init__(self, bname: str):
        super().__init__(label=f"Recycle {bname}", style=discord.ButtonStyle.danger, custom_id=f"city:recycle:tier:{bname}")
        self.bname = bname

    async def callback(self, interaction: discord.Interaction):
        view: BuildingsTierActionsView = self.view  # type: ignore
        await interaction.response.send_modal(RecycleBuildingQtyModal(view.cog, self.bname))



class LeaderboardBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Leaderboard", style=discord.ButtonStyle.secondary, custom_id="city:lb")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        e = await view.cog.leaderboard_embed(interaction.user)
        await interaction.response.edit_message(
            embed=e,
            view=LeaderboardView(view.cog, view.author, show_admin=view.show_admin)
        )

class LeaderboardView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True


class ViewResourcesBtn(ui.Button):
    def __init__(self):
        super().__init__(label="View Resources", style=discord.ButtonStyle.secondary, custom_id="city:resources:view")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        e = await view.cog.resources_overview_embed(interaction.user)
        tier_view = ResourcesTierView(view.cog, view.author, show_admin=view.show_admin)
        await interaction.response.edit_message(embed=e, view=tier_view)

class ResourcesTierView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.show_admin = show_admin
        for t in self.cog._all_tiers():
            self.add_item(ResourceTierButton(t))
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True

class ResourceTierButton(ui.Button):
    def __init__(self, tier: int):
        super().__init__(label=f"Tier {tier}", style=discord.ButtonStyle.primary, custom_id=f"city:resources:tier:{tier}")
        self.tier = int(tier)

    async def callback(self, interaction: discord.Interaction):
        view: ResourcesTierView = self.view  # type: ignore
        e = await view.cog.resources_tier_embed(interaction.user, self.tier)
        await interaction.response.edit_message(
            embed=e,
            view=ResourcesTierDetailView(view.cog, view.author, self.tier, show_admin=view.show_admin)
        )



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
        view: BuildingsTierView = self.view  # <-- get the parent view
        e = await view.cog.buildings_tier_embed(interaction.user, self.tier)
        actions = BuildingsTierActionsView(view.cog, view.author, self.tier, show_admin=view.show_admin)
        await interaction.response.edit_message(embed=e, view=actions)





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
        label = f"Amount to deposit (max {self.max_wc:,.2f} WC)" if max_wc is not None else "Amount to deposit (in WC)"
        placeholder = f"{self.max_wc:,.2f}" if max_wc is not None else "e.g. 100.50"

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
            f"✅ Deposited {amt_wc:,.2f} WC → **{local_credit:,.2f} {cur}**. New treasury: **{bank_local:,.2f} {cur}**",
            ephemeral=True
        )



class WithdrawModal(discord.ui.Modal, title="🏦 Withdraw Wellcoins"):
    def __init__(self, cog: "CityBuilder", max_local: Optional[float] = None, currency: Optional[str] = None):
        super().__init__()
        self.cog = cog
        self.max_local = trunc2(max_local or 0.0)
        self.currency = currency or "Local"

        label = f"Amount to withdraw (max {self.max_local:,.2f} {self.currency})"
        placeholder = f"{self.max_local:,.2f}" if max_local is not None else "e.g. 50.00"

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
                f"❌ Not enough in the treasury. You have **{bank_local:,.2f} {self.currency}**.",
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
            f"✅ Withdrew **{amt_local:,.2f} {cur}** → **{amt_wc:,.2f} WC**.\n"
            f"New treasury balance: **{new_bank:,.2f} {cur}**",
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
        
        Reliability = random.choice(["⭐","⭐⭐","⭐⭐⭐","⭐⭐⭐⭐","⭐⭐⭐⭐⭐"])
        Safety = random.choice(["⭐","⭐⭐","⭐⭐⭐","⭐⭐⭐⭐","⭐⭐⭐⭐⭐"])

        e = discord.Embed(
            title="👤 Candidate: General Worker",
            description=(
                "Hard-working, adaptable, and ready to operate your facilities.\n"
                f"• Reliability: {Reliability}\n"
                f"• Safety: {Safety}\n"
                "• Salary: "
                f"**{wage_local:,.2f} {cur}** per tick"
            )
        )
        e.set_image(url=img)

        await interaction.response.edit_message(
            embed=e,
            view=ConfirmHireView(cog, view.author, show_admin=any(isinstance(i, NextDayBtn) for i in view.children))
        )

class FireWorkerBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Fire Worker", style=discord.ButtonStyle.danger, custom_id="city:workers:fire")

    async def callback(self, interaction: discord.Interaction):
        view = self.view  # can be WorkersView or WorkersTiersMenuView
        cog: CityBuilder = view.cog  # type: ignore

        d = await cog.config.user(interaction.user).all()
        hired = int(d.get("workers_hired") or 0)
        if hired <= 0:
            return await interaction.response.send_message("❌ You don’t have any workers to fire.", ephemeral=True)

        # figure out unassigned count
        st = await cog._get_staffing(interaction.user)
        assigned = sum(int(v) for v in st.values())
        unassigned = max(0, hired - assigned)
        if unassigned <= 0:
            return await interaction.response.send_message(
                "❌ All workers are assigned right now. Unassign one before firing.",
                ephemeral=True
            )

        # fire: -1 hired and -1 unassigned
        await cog.config.user(interaction.user).workers_hired.set(hired - 1)
        await cog.config.user(interaction.user).workers_unassigned.set(unassigned - 1)

        # If we’re on the tier overview, refresh that; otherwise fall back to generic workers panel
        if isinstance(view, WorkersTiersMenuView):
            e = await cog.workers_overview_by_tier_embed(interaction.user)
            await interaction.response.edit_message(
                embed=e,
                view=WorkersTiersMenuView(cog, view.author, show_admin=view.show_admin)  # type: ignore
            )
        else:
            e = await cog.workers_embed(interaction.user)
            await interaction.response.edit_message(
                embed=e,
                view=WorkersView(cog, interaction.user, show_admin=any(isinstance(i, NextDayBtn) for i in view.children))  # type: ignore
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
                f"❌ Not enough funds. Need **{view.buyer_price_local:,.2f}** (incl. 10% fee).",
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
            header=f"🛒 Purchased **{view.listing_name}** for **{view.buyer_price_local:,.2f}** (incl. fee)."
        )
        await interaction.response.edit_message(
            embed=e,
            view=CityMenuView(cog, view.buyer, show_admin=view.show_admin)
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

    async def cog_load(self):
    # Start background tick after the bot is ready to load cogs
    # (safer than doing it in __init__)
        self.task = asyncio.create_task(self.resource_tick())

    def cog_unload(self):
        # Cancel the background task cleanly
        task = getattr(self, "task", None)
        if task:
            task.cancel()

    def _staffing_totals_by_tier(self, user_data: dict) -> dict[int, tuple[int, int]]:
        """
        Returns {tier: (assigned_in_tier, max_staffable_in_tier)}.
        max_staffable = owned count (1 worker per building unit).
        """
        by_tier: dict[int, tuple[int, int]] = {}
        bld = user_data.get("buildings") or {}
        st = {k: int(v) for k, v in (user_data.get("staffing") or {}).items()}
    
        for name, meta in BUILDINGS.items():
            t = int(meta.get("tier", 0))
            owned = int((bld.get(name) or {}).get("count", 0))
            if owned <= 0 or name == "house":
                # houses don’t take staffing
                continue
            assigned = min(int(st.get(name, 0)), owned)
            a, m = by_tier.get(t, (0, 0))
            by_tier[t] = (a + assigned, m + owned)
        return by_tier

    async def workers_overview_by_tier_embed(self, user: discord.abc.User) -> discord.Embed:
        d = await self.config.user(user).all()
        hired = int(d.get("workers_hired") or 0)
        st = await self._get_staffing(user)
        assigned_total = sum(int(v) for v in st.values())
        unassigned = max(0, hired - assigned_total)
    
        by_tier = self._staffing_totals_by_tier(d)
        lines = []
        for t in self._all_tiers():
            a, m = by_tier.get(t, (0, 0))
            lines.append(f"**Tier {t}** — {a}/{m} staffed")
    
        e = discord.Embed(title="👷 Workers by Tier",
                          description="Pick a tier to assign workers to buildings.")
        e.add_field(name="Tiers", value="\n".join(lines) or "—", inline=False)
        e.add_field(name="Totals", value=f"Hired **{hired}** · Assigned **{assigned_total}** · Unassigned **{unassigned}**", inline=False)
        e.set_footer(text=f"Unassigned: {unassigned}")
        return e


    async def workers_tier_detail_embed(self, user: discord.abc.User, tier: int) -> discord.Embed:
        d = await self.config.user(user).all()
        st = await self._get_staffing(user)
        lines = []
        for name, meta in sorted(BUILDINGS.items()):
            if int(meta.get("tier", 0)) != int(tier) or name == "house":
                continue
            owned = int((d.get("buildings") or {}).get(name, {}).get("count", 0))
            if owned <= 0:
                continue
            staffed = int(st.get(name, 0))
            lines.append(f"• **{name}** — {staffed}/{owned} staffed")
        if not lines:
            lines = ["—"]
    
        # totals for footer
        hired = int(d.get("workers_hired") or 0)
        assigned_total = sum(int(v) for v in st.values())
        unassigned = max(0, hired - assigned_total)
    
        e = discord.Embed(title=f"👷 Tier {tier} — Staffing", description="\n".join(lines))
        e.set_footer(text=f"Total workers: {hired} | Unassigned: {unassigned}")
        return e




    async def how_to_play_embed(self, user: discord.abc.User) -> discord.Embed:
        e = discord.Embed(
            title="📖 How to Play CityBuilder",
            description=(
                "Welcome to **CityBuilder**! Here’s the basics:\n\n"
                "🏗️ **Buildings** — Buy farms, mines, factories, and houses. "
                "Houses increase worker capacity, other buildings produce resources.\n\n"
                "👷 **Workers** — Hire and assign workers to staffed buildings so they actually produce.\n\n"
                "📦 **Resources** — Produced each tick (1h). Resources can be recycled into scrap or sold.\n\n"
                "🏦 **Treasury** — Pays upkeep and wages every tick. If empty, production halts.\n\n"
                "🛒 **Store** — Trade resources with other players. Buyers pay +10% fee, sellers lose −10% on payout.\n\n"
                "♻️ **Recycle** — Convert unwanted resources/buildings into scrap (Tier 0).\n\n"
                "🏆 **Leaderboard** — Score is based on your buildings (mainly) and resources."
            )
        )
        e.set_footer(text="Tip: Use `$city` anytime to return to your main city panel.")
        return e


    def _bundle_mul(self, per_unit: Dict[str, int], units: int) -> Dict[str, int]:
        return {k: int(v) * int(units) for k, v in (per_unit or {}).items()}

    def _wage_multiplier(self, hired: int, cap: int) -> float:
        if hired <= cap:
            return 1.0
        overflow = hired - cap
        if cap <= 0:
            return 1.0 + float(overflow)  # no housing at all → harsh penalty
        return 1.0 + (float(overflow) / float(cap))
    
    def _compute_wages_wc_from_numbers(self, hired: int, cap: int) -> float:
        base = trunc2(hired * WORKER_WAGE_WC)
        mult = self._wage_multiplier(hired, cap)
        return trunc2(base * mult)




    # --- Scoring params (tweak to taste) ---
    def _score_params(self) -> dict:
        """
        Building score dominates; each tier is exponentially more valuable.
        - Buildings:   b_score = b_base * (b_growth ** tier) * count
        - Resources:   r_score = r_base * (r_growth ** tier) * qty
        """
        return {
            "b_base": 100.0,  # base points per T0 building
            "b_growth": 3.0,  # exponential growth per tier for buildings
            "r_base": 1.0,    # base points per unit of T0 resource
            "r_growth": 2.0,  # exponential growth per tier for resources
            "top_n": 10,      # leaderboard size
        }
    
    def _building_tier_totals(self, user_data: dict) -> dict[int, int]:
        """
        Returns {tier: total_count_of_buildings_at_that_tier}.
        """
        by_tier: dict[int, int] = {}
        owned = (user_data.get("buildings") or {})
        for name, meta in BUILDINGS.items():
            t = int(meta.get("tier", 0))
            cnt = int((owned.get(name) or {}).get("count", 0))
            if cnt > 0:
                by_tier[t] = by_tier.get(t, 0) + cnt
        return by_tier

    
    def _resource_tier_totals(self, user_data: dict) -> dict[int, int]:
        """
        Returns {tier: total_qty_of_resources_at_that_tier}.
        Resources with no producer mapping are ignored.
        """
        inv = {k: int(v) for k, v in (user_data.get("resources") or {}).items()}
        r2t = self._resource_tier_map()
        out: dict[int, int] = {}
        for r, qty in inv.items():
            if qty <= 0 or r not in r2t:
                continue
            t = int(r2t[r])
            out[t] = out.get(t, 0) + qty
        return out
    
    def _compute_user_score_from_data(self, user_data: dict) -> float:
        """
        Pure function version (uses user_data) so we can score everyone quickly.
        """
        p = self._score_params()
        b_totals = self._building_tier_totals(user_data)
        r_totals = self._resource_tier_totals(user_data)
    
        score = 0.0
        # Buildings dominate
        for t, cnt in b_totals.items():
            score += p["b_base"] * (p["b_growth"] ** int(t)) * float(cnt)
        # Resources contribute less
        for t, qty in r_totals.items():
            score += p["r_base"] * (p["r_growth"] ** int(t)) * float(qty)
        return float(int(score))  # keep it neat (integer points)
    
    
    async def leaderboard_embed(self, requester: discord.abc.User) -> discord.Embed:
        """
        Computes all users' scores, shows Top N and the requester's rank.
        """
        params = self._score_params()
        top_n = int(params.get("top_n", 10))
    
        all_users = await self.config.all_users()
    
        # Build (user_id, score) pairs
        scored: list[tuple[int, float]] = []
        for uid, udata in all_users.items():
            try:
                s = self._compute_user_score_from_data(udata or {})
            except Exception:
                s = 0.0
            scored.append((int(uid), s))
    
        # Sort desc by score, then asc by user id for stability
        scored.sort(key=lambda tup: (-tup[1], tup[0]))
    
        # Find requester rank
        req_id = int(getattr(requester, "id", 0))
        rank_map = {uid: i + 1 for i, (uid, _) in enumerate(scored)}
        my_rank = rank_map.get(req_id, None)
        my_score = next((s for (uid, s) in scored if uid == req_id), 0.0)
    
        # Build Top N lines
        lines = []
        for i, (uid, score) in enumerate(scored[:top_n], start=1):
            u = self.bot.get_user(uid)
            name = u.display_name if u else f"User {uid}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            lines.append(f"{medal} **{name}** — **{score:,.0f}** pts")  # 👈 commas
    
        if not lines:
            lines = ["—"]
    
        footer = (
            f"Your rank: #{my_rank} — {my_score:,.0f} pts"
            if my_rank else "You’re not ranked yet."
        )
    
        e = discord.Embed(
            title="🏆 City Leaderboard",
            description="\n".join(lines)
        )
        e.set_footer(text=footer)
        return e

    def _resource_tier_map(self) -> Dict[str, int]:
        """
        Map each resource to the *lowest* tier of any building that produces it.
        Example: if farm (t1) and factory (t2) both produce 'food', tier is 1.
        """
        m: Dict[str, int] = {}
        for bname, meta in BUILDINGS.items():
            tier = int(meta.get("tier", 0))
            for res in (meta.get("produces") or {}).keys():
                if res not in m:
                    m[res] = tier
                else:
                    m[res] = min(m[res], tier)
    
        # Ensure 'scrap' is visible as a T0 resource (even if no building produces it)
        m.setdefault("scrap", 0)
    
        return m
    
    def _scrap_from_resource(self, res: str, qty: int) -> int:
        """Scrap gained from recycling 'qty' units of resource 'res', based on resource score."""
        p = self._score_params()
        r_tier = self._resource_tier_map().get(res, 0)
        per_unit = int(p["r_base"] * (p["r_growth"] ** int(r_tier)))
        return max(0, per_unit * max(0, int(qty)))
    
    def _scrap_from_building(self, bname: str, qty: int) -> int:
        """Scrap gained from recycling 'qty' buildings, based on building score."""
        if bname not in BUILDINGS:
            return 0
        p = self._score_params()
        b_tier = int(BUILDINGS[bname].get("tier", 0))
        per_unit = int(p["b_base"] * (p["b_growth"] ** int(b_tier)))
        return max(0, per_unit * max(0, int(qty)))


    
    def _group_resources_by_tier(self, user_data: dict) -> Dict[int, list]:
        """
        Returns {tier: [(resource, qty), ...]} for current inventory.
        Resources with no producer mapping are ignored.
        """
        inv = {k: int(v) for k, v in (user_data.get("resources") or {}).items()}
        r2t = self._resource_tier_map()
        by_tier: Dict[int, list] = {}
        for r, qty in inv.items():
            if qty <= 0:
                continue
            if r not in r2t:
                # skip unknown/unmapped resources
                continue
            t = int(r2t[r])
            by_tier.setdefault(t, []).append((r, qty))
        for t in by_tier:
            by_tier[t].sort(key=lambda p: p[0])
        return by_tier
    
    async def resources_overview_embed(self, user: discord.abc.User) -> discord.Embed:
        """
        Overview of user's resources grouped by tier (totals per tier).
        Shows tiers even if empty as '—'.
        """
        d = await self.config.user(user).all()
        grouped = self._group_resources_by_tier(d)
        lines = []
        for t in self._all_tiers():
            entries = grouped.get(t, [])
            total = sum(q for _, q in entries)
            lines.append(f"**Tier {t}** — {total if total > 0 else '—'}")
        e = discord.Embed(title="📦 Resources by Tier", description="\n".join(lines) or "—")
        e.set_footer(text="Select a tier below to view details.")
        return e
    
    async def resources_tier_embed(self, user: discord.abc.User, tier: int) -> discord.Embed:
        """
        Detail view for a resource tier: shows each resource, qty, and which buildings (at this tier)
        can produce it, with per-building output rate.
        """
        d = await self.config.user(user).all()
        inv = {k: int(v) for k, v in (d.get("resources") or {}).items()}
        lines = []
    
        # collect all resources that *map* to this tier
        r2t = self._resource_tier_map()
        tier_resources = [r for r, t in r2t.items() if int(t) == int(tier)]
    
        # for each resource at this tier, show qty and producers (at this tier)
        for res in sorted(tier_resources):
            qty = int(inv.get(res, 0))
            producers = []
            for bname, meta in sorted(BUILDINGS.items()):
                if int(meta.get("tier", 0)) != int(tier):
                    continue
                out = meta.get("produces") or {}
                if res in out:
                    producers.append(f"{bname}(+{int(out[res])}/t)")
            prod_txt = ", ".join(producers) if producers else "—"
            lines.append(f"• **{res}** — qty **{qty}** · produced by: {prod_txt}")
    
        if not lines:
            lines = ["—"]
    
        return discord.Embed(title=f"📦 Tier {tier} Resources", description="\n".join(lines))


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
        Shows the TOTAL count per tier (0 if empty).
        """
        d = await self.config.user(user).all()
        grouped = self._group_owned_by_tier(d)
    
        lines = []
        for t in self._all_tiers():
            entries = grouped.get(t, [])
            total = sum(cnt for _, cnt in entries)
            lines.append(f"**Tier {t}** — {total}")
    
        e = discord.Embed(
            title="🏗️ Buildings by Tier",
            description="\n".join(lines) or "—"
        )
        e.set_footer(text="Select a tier below to view details.")
        return e

    
    async def buildings_tier_embed(self, user: discord.abc.User, tier: int) -> discord.Embed:
        """
        Detailed view for a single tier: local cost, upkeep (/t), and clear multi-input/output lines.
        """
        d = await self.config.user(user).all()
        rate, cur = await self._get_rate_currency(user)
    
        def fmt_io(io: Dict[str, int], *, per_tick: bool = True) -> str:
            if not io:
                return "—"
            suf = "/t" if per_tick else ""
            # Example: "metal+2/t, food+1/t, scrap+5/t"
            return ", ".join(f"{k}+{int(v)}{suf}" for k, v in io.items())
    
        lines = []
        for name, meta in sorted(BUILDINGS.items()):
            if int(meta.get("tier", 0)) != int(tier):
                continue
    
            cnt = int((d.get("buildings") or {}).get(name, {}).get("count", 0))
            cost_wc = trunc2(float(meta.get("cost", 0.0)))
            upkeep_wc = trunc2(float(meta.get("upkeep", 0.0)))
            cost_local = trunc2(cost_wc * rate)
            upkeep_local = trunc2(upkeep_wc * rate)
    
            inputs = meta.get("inputs") or {}
            outputs = meta.get("produces") or {}
    
            # Optional note for houses
            cap_note = ""
            if name == "house":
                cap = int(meta.get("capacity", 0))
                if cap:
                    cap_note = f" · Capacity +{cap}"
    
            # Build the block for this building
            lines.append(
                f"• **{name}** (owned {cnt})\n"
                f"  Cost **{cost_local:,.2f} {cur}** · Upkeep **{upkeep_local:,.2f} {cur}/t**{cap_note}\n"
                f"  **Inputs:**  {fmt_io(inputs)}\n"
                f"  **Outputs:** {fmt_io(outputs)}"
            )
    
        if not lines:
            lines = ["—"]
    
        e = discord.Embed(title=f"🏗️ Tier {tier} — Details", description="\n".join(lines))
        return e

    

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
                              f"Price **{p_local:,.2f} {cur}** | Stock {int(it.get('stock') or 0)}")
        buy_lines = []
        for o in orders:
            p_local = trunc2(float(o.get("price_wc") or 0.0) * rate)
            buy_lines.append(f"• **{o.get('id')}** — {o.get('resource')} ×{int(o.get('qty') or 0)} @ **{p_local:,.2f} {cur}** /u")
        desc = (header + "\n\n" if header else "") + "**Your Sell Listings**\n" + ("\n".join(sell_lines) or "—")
        e = discord.Embed(title="🧾 My Store", description=desc)
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
                    f"**{price_local:,.2f} {cur}** (incl. fee) · Stock {effective_stock}"
                )
    
        e = discord.Embed(
            title="🛍️ Browse Listings",
            description="\n".join(lines) or "No listings available."
        )
        return e
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
                    value=(f"Hired **{hired}** · Capacity **{cap}** · Assigned **{assigned}** · Unassigned **{unassigned}**"),
                    inline=False)
        e.add_field(name="Wage",
                    value=f"**{wage_local:,.2f} {cur}** per worker per tick",
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
        d = await self.config.user(user).all()
        bld = d.get("buildings", {})
        _, cur = await self._get_rate_currency(user)
    
        # compute upkeep + wages (in local), same as main panel
        wc_upkeep = 0.0
        for b, info in bld.items():
            if b in BUILDINGS:
                wc_upkeep += BUILDINGS[b]["upkeep"] * int(info.get("count", 0))
        wc_upkeep = trunc2(wc_upkeep)
        local_upkeep = await self._wc_to_local(user, wc_upkeep)
        wages_local = await self._wc_to_local(user, trunc2(int(d.get("workers_hired") or 0) * WORKER_WAGE_WC))
        per_tick_local = trunc2(local_upkeep + wages_local)
    
        if per_tick_local > 0:
            ticks_left = int(bank_local // per_tick_local)
            seconds_left = ticks_left * TICK_SECONDS
            end_ts = int(time.time()) + seconds_left
            runway_txt = f"About {ticks_left} ticks — runs out <t:{end_ts}:R> (<t:{end_ts}:T>)"
        else:
            runway_txt = "∞ (no upkeep/wages)"

    
        e = discord.Embed(
            title="🏦 Treasury",
            description="Your **Bank** pays wages/upkeep each tick in your **local currency**. "
                        "If the bank can’t cover upkeep, **production halts**."
        )
        e.add_field(name="Current Balance", value=f"**{bank_local:,.2f} {cur}**", inline=False)
        e.add_field(name="Per-Tick Need", value=f"**{per_tick_local:,.2f} {cur}/t**", inline=True)
        e.add_field(name="Runway", value=runway_txt, inline=True)
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
            content=f"📄 XML for **{target_nation}** · recalculated: `1 WC = {float(rate):,.2f} {currency}`",
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
                lines.append(f"• Scale {sid}: **missing** → norm `—` × w `{w:,.2f}` = contrib `0.00`")
                continue
            norm = transforms[sid](raw)
            contrib = w * norm
            num += contrib
            den += abs(w)
            # format raw compactly (handles scientific)
            raw_str = f"{raw:.4g}"
            lines.append(f"• Scale {sid}: raw `{raw_str}` → norm `{norm:,.2f}` × w `{w:,.2f}` = contrib `{contrib:,.2f}`")
    
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
            e.add_field(name="Current Rate", value=f"1 WC = **{float(rate):,.2f} {currency}**", inline=False)
        else:
            e.add_field(name="Current Rate", value="(not set)", inline=False)
    
        e.add_field(name="Per-Scale Contributions", value="\n".join(lines) or "—", inline=False)
        e.add_field(name="Composite Index → Rate", value=f"Index `{idx:.3f}` → Mapped Rate `{mapped:,.2f}`", inline=False)
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
        """
        Pay-as-you-go production:
        - Sort staffed building *units* by descending tier.
        - For each unit, compute marginal WC cost (its upkeep + 1 worker's marginal wage incl. housing overflow).
        - Convert that marginal WC to local; if treasury can cover it and inputs exist, run the unit:
            * Deduct local funds
            * Consume inputs
            * Add outputs
            * Count that worker as 'used' (affects next unit's marginal wage via overflow)
        - Stop when funds or inputs run out.
        """
        d = await self.config.user(user).all()
        bld = d.get("buildings", {})
        if not bld:
            return
    
        # Ensure staffing consistency
        await self._reconcile_staffing(user)
        st = await self._get_staffing(user)
    
        # Snapshot inventory + treasury (local)
        new_resources = dict(d.get("resources", {}))
        bank_local = trunc2(float(d.get("bank", 0.0)))
    
        # Quick exit: nothing staffed
        any_staffed = any(min(int((bld.get(b) or {}).get("count", 0)), int(st.get(b, 0))) > 0 for b in bld.keys())
        if not any_staffed:
            return
    
        # Capacity affects wage overflow
        cap = await self._worker_capacity(user)
    
        # --- Build a flat list of staffed building *units* with their tier/name ---
        # Each element is (tier:int, name:str)
        units: list[tuple[int, str]] = []
        for bname, info in bld.items():
            if bname not in BUILDINGS:
                continue
            cnt = int(info.get("count", 0))
            staffed = min(cnt, int(st.get(bname, 0)))
            if staffed <= 0:
                continue
            tier = int(BUILDINGS[bname].get("tier", 0))
            units.extend((tier, bname) for _ in range(staffed))
    
        # Highest tier first
        units.sort(key=lambda t: (-t[0], t[1]))
    
        # Helper to get marginal wage (WC) of adding the Nth paid worker
        def _marginal_wage_wc(n_workers_before: int) -> float:
            # total(n) - total(n-1), using the same overflow schedule as your global wage function
            before = self._compute_wages_wc_from_numbers(n_workers_before, cap)
            after = self._compute_wages_wc_from_numbers(n_workers_before + 1, cap)
            return trunc2(after - before)
    
        used_workers = 0  # number of workers we actually fund this tick
    
        # For each staffed unit in priority order, attempt to fund and run it
        for tier, bname in units:
            meta = BUILDINGS[bname]
            # Per-unit upkeep in WC
            upkeep_wc = trunc2(float(meta.get("upkeep", 0.0)))
    
            # Marginal wage (WC) for adding this worker
            wage_wc = _marginal_wage_wc(used_workers)
    
            # Total marginal WC for this unit
            unit_wc = trunc2(upkeep_wc + wage_wc)
    
            # Convert to local to compare against treasury
            unit_local = await self._wc_to_local(user, unit_wc)
            if bank_local + 1e-9 < unit_local:
                # Not enough funds to run more units; stop early
                break
    
            # Check if we have inputs to run ONE unit
            inputs = {k: int(v) for k, v in (meta.get("inputs") or {}).items()}
            can_run = True
            for res, need in inputs.items():
                if need <= 0:
                    continue
                if int(new_resources.get(res, 0)) < need:
                    can_run = False
                    break
            if not can_run:
                # Skip this unit; maybe lower-tier units can still run
                continue
    
            # PAY for this unit
            bank_local = trunc2(bank_local - unit_local)
    
            # CONSUME inputs
            for res, need in inputs.items():
                if need <= 0:
                    continue
                new_resources[res] = int(new_resources.get(res, 0)) - need
                if new_resources[res] < 0:
                    new_resources[res] = 0  # safety
    
            # PRODUCE outputs
            for res, amt in (meta.get("produces") or {}).items():
                if amt <= 0:
                    continue
                new_resources[res] = int(new_resources.get(res, 0)) + int(amt)
    
            # Count this worker as funded/used
            used_workers += 1
    
        # Save final inventory and treasury
        await self.config.user(user).resources.set(new_resources)
        await self.config.user(user).bank.set(bank_local)




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
        cap = await self._worker_capacity(user)
        wages_wc = self._compute_wages_wc_from_numbers(hired, cap)
        wages_local = await self._wc_to_local(user, wages_wc)
        per_tick_local = trunc2(local_upkeep + wages_local)

       
        if per_tick_local > 0:
            ticks_left = int(bank_local // per_tick_local)
            seconds_left = ticks_left * TICK_SECONDS
            end_ts = int(time.time()) + seconds_left
            runway_txt = f"About {ticks_left} ticks — runs out <t:{end_ts}:R> (<t:{end_ts}:T>)"
        else:
            runway_txt = "∞ (no upkeep/wages)"

        desc = "Use the buttons below to manage your city."
        if header:
            desc = f"{header}\n\n{desc}"
    
        # ✅ CREATE THE EMBED BEFORE ADDING FIELDS
        e = discord.Embed(
            title=f"🌆 {getattr(user, 'display_name', 'Your')} City",
            description=desc
        )
    
        grouped_owned = self._group_owned_by_tier(d)  # {tier: [(name, count), ...]} (only >0)
        tier_lines = []
        for t in self._all_tiers():  # tiers derived from BUILDINGS, so includes empty tiers
            total = sum(cnt for _, cnt in grouped_owned.get(t, []))
            tier_lines.append(f"**Tier {t}** — {total}")
        btxt = "\n".join(tier_lines) or "None"
    
        # 📦 Resources: counts by tier (always show every tier)
        grouped_res = self._group_resources_by_tier(d)  # {tier: [(res, qty), ...]}
        res_tier_lines = []
        for t in self._all_tiers():
            total = sum(q for _, q in grouped_res.get(t, []))
            res_tier_lines.append(f"**Tier {t}** — {total}")
        rtxt = "\n".join(res_tier_lines) or "None"
    
        # Add fields after embed is defined
        e.add_field(name="🏗️ Buildings", value=btxt, inline=False)
        e.add_field(name="📦 Resources", value=rtxt, inline=False)
        e.add_field(
            name="👷 Workers",
            value=(
                f"Hired **{hired}** · Capacity **{cap}** · Assigned **{assigned}** · Unassigned **{unassigned}**\n"
                f"Wages per tick: **{wages_local:,.2f} {cur}** "
            ),
            inline=False,
        )
        e.add_field(name="🏦 Treasury", value=f"**{bank_local:,.2f} {cur}**", inline=True)
        e.add_field(name="⏳ Total Upkeep per Tick", value=f"**{per_tick_local:,.2f} {cur}/t**", inline=True)
        e.add_field(name="📉 Runway", value=runway_txt, inline=False)
        e.add_field(name="🌍 Exchange", value=f"1 WC = **{rate:,.2f} {cur}**", inline=False)
    
        next_ts = self._next_tick_ts()
        e.add_field(
            name="🕒 Next Tick",
            value=f"<t:{next_ts}:R>  —  <t:{next_ts}:T>",
            inline=False
        )
    
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

        # ── NEW: pull balances ─────────────────────────────────────────────
        bank_local = trunc2(float(await view.cog.config.user(interaction.user).bank()))
        wallet_wc = await view.cog._get_wallet_wc(interaction.user)
        rate, cur = await view.cog._get_rate_currency(interaction.user)
        wallet_local = await view.cog._wc_to_local(interaction.user, wallet_wc)
        total_local = trunc2(bank_local + wallet_local)
        # ───────────────────────────────────────────────────────────────────

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

        # ── NEW: show balances ─────────────────────────────────────────────
        e.add_field(
            name="💰 Your Balance",
            value=(
                f"Treasury: **{bank_local:,.2f} {cur}**\n"
                f"Wallet: **{wallet_wc:,.2f} WC** (≈ **{wallet_local:,.2f} {cur}**)\n"
                f"Total: **{total_local:,.2f} {cur}**"
            ),
            inline=False
        )
        # ───────────────────────────────────────────────────────────────────

        try:
            await interaction.response.edit_message(
                embed=e,
                view=StoreMenuView(view.cog, view.author, show_admin=view.show_admin),  # type: ignore
            )
        except NameError:
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
#menu buttons
        self.add_item(ViewBtn())
        #self.add_item(BuildBtn())
        self.add_item(BankBtn())
        self.add_item(WorkersBtn())
        self.add_item(StoreBtn())
        self.add_item(ViewBuildingsBtn())  
        self.add_item(ViewResourcesBtn())
        self.add_item(LeaderboardBtn())
        self.add_item(HowToPlayBtn())
        if show_admin:
            self.add_item(NextDayBtn())
            self.add_item(RateBtn()) 

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

class HowToPlayBtn(ui.Button):
    def __init__(self):
        super().__init__(label="How to Play", style=discord.ButtonStyle.primary, custom_id="city:howtoplay")

    async def callback(self, interaction: discord.Interaction):
        view: CityMenuView = self.view  # type: ignore
        e = await view.cog.how_to_play_embed(interaction.user)
        await interaction.response.edit_message(
            embed=e,
            view=HowToPlayView(view.cog, view.author, show_admin=view.show_admin),
        )

class HowToPlayView(ui.View):
    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This panel isn’t yours. Use `$city` to open your own.", ephemeral=True)
            return False
        return True


class BankBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Bank", style=discord.ButtonStyle.success, custom_id="city:bank")

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
            desc = f"Cost {local_cost:,.2f} {self.currency} · Upkeep {local_upkeep:,.2f} {self.currency}/t"
            if len(desc) > 96:
                desc = f"Cost {local_cost:,.2f} · Upkeep {local_upkeep:,.2f}/t"
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
                f"Need **{local_cost:,.2f} {self.currency}**.",
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

        header = f"🏗️ Built **{building}** for **{local_cost:,.2f} {self.currency}**."
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
        #self.add_item(RemoveBuyOrderBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id


class AddSellListingBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Add Sell Listing", style=discord.ButtonStyle.success, custom_id="store:addsell")

    async def callback(self, interaction: discord.Interaction):
        view: StoreMenuView = self.view  # type: ignore
        await interaction.response.send_modal(AddSellListingModal(view.cog))


class BrowseStoresBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Browse Stores", style=discord.ButtonStyle.primary, custom_id="store:browse")

    async def callback(self, interaction: discord.Interaction):
        view: StoreMenuView = self.view  # type: ignore
        e = await view.cog.store_browse_embed(interaction.user)

        buyview = StoreBuyView(view.cog, view.author, view.children[-1].show_admin)
        await buyview.refresh(interaction.user)  # build first page
        await interaction.response.edit_message(embed=e, view=buyview)



class RemoveListingBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Remove Sell Listing", style=discord.ButtonStyle.danger, custom_id="store:removesell")

    async def callback(self, interaction: discord.Interaction):
        view: StoreManageMyView = self.view  # type: ignore
        await interaction.response.send_modal(RemoveSellListingModal(view.cog))


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
            header=f"✅ Added listing **{self.name.value}** at {price_local:,.2f} (your currency). "
                   f"Escrowed stock: {final_stock}."
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

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


class StoreBuyView(ui.View):
    PAGE_SIZE = 25  # Discord select limit

    def __init__(self, cog: "CityBuilder", author: discord.abc.User, show_admin: bool, page: int = 0):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.show_admin = show_admin
        self.page = max(0, int(page))
        self.total_pages = 1  # will be set on refresh
        self._all_items: list[tuple[int, dict]] = []  # [(owner_id, listing_dict)]

        self.select = PurchaseListingSelect(cog, self)
        self.add_item(self.select)
        self.add_item(PrevPageBtn())
        self.add_item(NextPageBtn())
        self.add_item(BackBtn(show_admin))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    async def load_all_items(self, viewer: discord.abc.User):
        """Build the full list of (owner_id, listing) across all users, filtered & sorted."""
        self._all_items.clear()
        all_users = await self.cog.config.all_users()

        for owner_id, udata in all_users.items():
            if int(owner_id) == viewer.id:
                continue
            for it in (udata.get("store_sell_listings") or []):
                # Compute effective (escrow-backed) stock
                effective_stock = (
                    self.cog._effective_stock_from_escrow(it)
                    if hasattr(self.cog, "_effective_stock_from_escrow")
                    else int(it.get("stock") or 0)
                )
                if effective_stock <= 0:
                    continue
                self._all_items.append((int(owner_id), it))

        # optional stable sort by name then id
        self._all_items.sort(key=lambda p: (str(p[1].get("name") or ""), str(p[1].get("id") or "")))

        # compute total pages
        n = len(self._all_items)
        self.total_pages = max(1, (n + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page = min(self.page, self.total_pages - 1)  # clamp

    def slice_for_page(self) -> list[tuple[int, dict]]:
        start = self.page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        return self._all_items[start:end]

    async def refresh(self, viewer: discord.abc.User):
        """Rebuild options for the current page."""
        await self.load_all_items(viewer)
        await self.select.refresh(viewer)

class PurchaseListingSelect(ui.Select):
    def __init__(self, cog: "CityBuilder", view: "StoreBuyView"):
        self.cog = cog
        self._view = view
        super().__init__(placeholder="Loading listings…", min_values=1, max_values=1, options=[])

    async def refresh(self, viewer: discord.abc.User):
        # Ensure the view has data (in case refresh() on the view wasn't called)
        if not self._view._all_items:
            await self._view.load_all_items(viewer)
    
        opts: list[discord.SelectOption] = []
        page_items = self._view.slice_for_page()
        for owner_id, item in page_items:
            price_wc = float(item.get("price_wc") or 0.0)
            price_local_fee = trunc2((await self.cog._wc_to_local(viewer, price_wc)) * 1.10)
    
            effective_stock = (
                self.cog._effective_stock_from_escrow(item)
                if hasattr(self.cog, "_effective_stock_from_escrow")
                else int(item.get("stock") or 0)
            )
            if effective_stock <= 0:
                continue
    
            label = f'{item.get("name")} [Stock {effective_stock}]'
            desc = f'Price {price_local_fee:,.2f} in your currency (incl. fee)'
            value = f'{owner_id}|{item.get("id")}'
            opts.append(discord.SelectOption(label=label[:100], description=desc[:100], value=value))
    
        if not opts:
            opts = [discord.SelectOption(label="No available listings on this page", description="—", value="none")]
    
        self.options = opts
        self.placeholder = f"Buy 1 unit — Page {self._view.page+1}/{self._view.total_pages}"


    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "none":
            return await interaction.response.send_message("Nothing to buy on this page.", ephemeral=True)

        owner_s, lid = value.split("|", 1)
        owner_id = int(owner_s)
        if owner_id == interaction.user.id:
            return await interaction.response.send_message("You can’t buy your own listing.", ephemeral=True)

        # Fetch listing fresh (race-safe)
        owner_conf = self.cog.config.user_from_id(owner_id)
        owner_data = await owner_conf.all()
        listings = list(owner_data.get("store_sell_listings") or [])
        listing = next((x for x in listings if x.get("id") == lid), None)
        if not listing:
            return await interaction.response.send_message("Listing unavailable.", ephemeral=True)

        eff_stock = (
            self.cog._effective_stock_from_escrow(listing)
            if hasattr(self.cog, "_effective_stock_from_escrow")
            else int(listing.get("stock", 0) or 0)
        )
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
                f"Price: **{buyer_price_local:,.2f} {buyer_cur}** (incl. 10% fee)\n\n"
                "Do you want to proceed?"
            )
        )

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

# ------ NEW: pager buttons ------
class PrevPageBtn(ui.Button):
    def __init__(self):
        super().__init__(label="◀ Prev", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: StoreBuyView = self.view  # type: ignore
        if view.page > 0:
            view.page -= 1
            await view.select.refresh(interaction.user)
            await interaction.response.edit_message(view=view)
        else:
            await interaction.response.send_message("Already at the first page.", ephemeral=True)

class NextPageBtn(ui.Button):
    def __init__(self):
        super().__init__(label="Next ▶", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: StoreBuyView = self.view  # type: ignore
        if view.page + 1 < view.total_pages:
            view.page += 1
            await view.select.refresh(interaction.user)
            await interaction.response.edit_message(view=view)
        else:
            await interaction.response.send_message("Already at the last page.", ephemeral=True)

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
