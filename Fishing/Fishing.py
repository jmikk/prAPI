# File: fishing/fishing.py
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Protocol

import discord
from discord import ui
from redbot.core import commands, Config
from redbot.core.bot import Red

__all__ = ["Fishing"]

COOLDOWN_SECONDS = 0.5

# ---------- Data Models ----------
@dataclass(frozen=True)
class Rod:
    key: str
    name: str
    power: int            # affects chance for higher rarity
    durability: int       # max durability
    price: float

@dataclass(frozen=True)
class Bait:
    key: str
    name: str
    rarity_boost: float   # additive/multiplicative boost to non-common rarities
    price: float

@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    unlock_price: float
    sell_multiplier: float  # improves sell price of fish
    base_table: Dict[str, float]  # rarity -> weight override/boost

@dataclass(frozen=True)
class Catch:
    rarity: str
    species: str


# ---------- Static Data ----------
RARITY_PRICES: Dict[str, float] = {
    "common": 2.00,
    "uncommon": 4.50,
    "part": 10,
    "rare": 12.00,
    "epic": 30.00,
    "legendary": 100.00,
}

BASE_RARITY_TABLE: Dict[str, float] = {
    "common": 70.0,
    "part": 30.0,
    "uncommon": 22.0,
    "rare": 6.0,
    "epic": 1.8,
    "legendary": 0.2,
}

RODS: Dict[str, Rod] = {
    "twig":   Rod("twig",   "Twig Rod",        power=0, durability=30,  price=0.0),
    "oak":    Rod("oak",    "Oak Rod",         power=1, durability=60,  price=25.0),
    "steel":  Rod("steel",  "Steel Rod",       power=2, durability=120, price=120.0),
    "myth":   Rod("myth",   "Mythril Rod",     power=4, durability=240, price=500.0),
}

BAITS: Dict[str, Bait] = {
    "worm":    Bait("worm",    "Worm Bait",     rarity_boost=0.02,  price=0.5),
    "minnow":  Bait("minnow",  "Minnow Bait",   rarity_boost=0.04,  price=1.5),
    "shrimp":  Bait("shrimp",  "Shrimp Bait",   rarity_boost=0.06, price=4.0),
    "goldfly": Bait("goldfly", "Goldfly Bait",  rarity_boost=0.1,  price=8.0),
}

ZONES: Dict[str, Zone] = {
    "pond": Zone(
        "pond", "Quiet Pond", unlock_price=0.0, sell_multiplier=1.0,
        base_table={"common": +5.0}
    ),
    "river": Zone(
        "river", "Swift River", unlock_price=50.0, sell_multiplier=1.1,
        base_table={"uncommon": +3.0, "rare": +1.0}
    ),
    "coast": Zone(
        "coast", "Rocky Coast", unlock_price=200.0, sell_multiplier=1.25,
        base_table={"rare": +2.0, "epic": +0.5}
    ),
    "abyss": Zone(
        "abyss", "Midnight Abyss", unlock_price=1000.0, sell_multiplier=1.5,
        base_table={"epic": +0.8, "legendary": +0.2}
    ),
    "rift": Zone(
        "rift", "The Magic Rift", unlock_price=5000.0, sell_multiplier=3,
        base_table={"part": +3, "legendary": +1}
    ),
}

ZONE_IMAGES = {
    "pond": "https://i.imgur.com/RSOcl06.png",
    "river": "https://i.imgur.com/yntvP05.png",
    "coast": "https://i.imgur.com/PX4Nosp.png",
    "abyss": "https://i.imgur.com/AnBi2vR.png",
    "rift": "https://i.ibb.co/bRjyRMfm/8a256adc-f383-4569-835b-1389ad1eb5f6.png",
}

FISH_IMAGES_BY_SPECIES: Dict[str, str] = {
    "Bluegill": "https://i.etsystatic.com/49528872/r/il/e5e842/6121364885/il_570xN.6121364885_p01x.jpg",
    "Muddy Carp": "https://www.shutterstock.com/image-vector/side-view-example-vector-art-600nw-2359648865.jpg",
    "Lilypad Perch": "https://i.imgur.com/9xO4rZM.png",
    "Speckled Sunfish": "https://ih1.redbubble.net/image.1222662294.2458/flat,750x,075,f-pad,750x1000,f8f8f8.u3.jpg",
    "Dusk Minnow": "https://img.freepik.com/premium-vector/cartoon-vector-illustration-white-cloud-mountain-minnow-fish-icon-isolated-white-background_760559-2494.jpg",
    "Moonlit Koi": "https://thumbs.dreamstime.com/b/elegant-blue-koi-fish-swimming-under-moonlight-dreamy-fantasy-night-sky-scene-high-quality-photo-396767528.jpg",
    "Verdant Arowana": "https://thumbs.dreamstime.com/b/cartoon-illustration-green-teal-arowana-fish-cartoon-style-illustration-green-teal-arowana-fish-orange-392599416.jpg",
    "Pond Guardian": "https://i.imgur.com/qFLusNn.png",

    # Swift River
    "River Perch": "https://www.shutterstock.com/image-vector/perch-fish-isolated-on-white-260nw-2157228141.jpg",
    "Stone Shiner": "https://thumbs.dreamstime.com/b/cartoon-stonefish-illustration-vector-textured-brown-patterns-bold-fins-set-against-blue-background-perfect-394794606.jpg",
    "Silver Chub": "https://www.shutterstock.com/image-vector/silver-carp-color-icon-vector-260nw-2612774453.jpg",
    "Swift Darter": "https://www.shutterstock.com/image-vector/darter-fish-etheosomatidae-north-america-600nw-2127404258.jpg",
    "Bronze Trout": "https://static.wixstatic.com/media/ad2f54_3d6a80a453f6447a85a071a6b70fd69b~mv2.png",
    "Runebrook Salmon": "https://i.imgur.com/9F65Vk0.png",
    "King of Currents": "https://i.imgur.com/Ngk4Vsn.png",

    # Rocky Coast
    "Tide Sardine": "https://us.bordallopinheiro.com/on/demandware.static/-/Sites-bordallo-master-catalog/default/dw9b09adc6/images/large/65018846.jpg",
    "Pebble Mackerel": "https://static.vecteezy.com/system/resources/previews/055/111/980/non_2x/cartoon-mackerel-fish-icon-illustration-vector.jpg",
    "Sea Bream": "https://thumbs.dreamstime.com/b/cartoon-twobar-seabream-cute-isolated-white-background-76503113.jpg",
    "Glimmer Hake": "https://static.wikia.nocookie.net/characters/images/2/21/Glimmer_the_Anglerfish.jpg",
    "Opal Snapper": "https://img.freepik.com/premium-vector/vector-cute-snapper-cartoon-style_846317-918.jpg",
    "Storm Marlin": "https://media.istockphoto.com/id/165695537/vector/capn-marlin.jpg",
    "Leviathan Fry": "https://i.imgur.com/sq6ZZ45.png",

    # Midnight Abyss
    "Gloom Smelt": "https://thumbs.dreamstime.com/b/dynamic-smelt-fish-illustration-colorful-design-featuring-369690331.jpg",
    "Twilight Cod": "https://static.wikia.nocookie.net/fisch/images/5/51/Twilight_Tentaclefish.png",
    "Nightfang Eel": "https://i.imgur.com/JPXa10g.png",
    "Phantom Angler": "https://i.imgur.com/mOJgImO.png",
    "Abyssal Sovereign": "https://i.imgur.com/Qo9HmZz.png",

    # Parts
    "Fishing Map": "https://i.ibb.co/gFdC2Mgw/57d76c68-ab77-4363-839b-53e821344cd4.png",

    # A set
    "A1": "https://i.ibb.co/Gf0BB29Y/A1.png",
    "A2": "https://i.ibb.co/spHr8BrQ/A2.png",
    "A3": "https://i.ibb.co/C3cLmnGS/A3.png",
    "A4": "https://i.ibb.co/FqmpWf6S/A4.png",
    "A5": "https://i.ibb.co/XfmGkMmS/A5.png",
    "A6": "https://i.ibb.co/hQystd6/A6.png",
    "A7": "https://i.ibb.co/q316g7LG/A7.png",
    "A8": "https://i.ibb.co/VpzdY5qC/A8.png",

    # B set
    "B1": "https://i.ibb.co/XrnJmysD/B1.png",
    "B2": "https://i.ibb.co/pjMnq89w/B2.png",
    "B3": "https://i.ibb.co/3mkqM813/B3.png",
    "B4": "https://i.ibb.co/p9ZCM99/B4.png",
    "B5": "https://i.ibb.co/1FbJmh8/B5.png",
    "B6": "https://i.ibb.co/3mJCx64y/B6.png",
    "B7": "https://i.ibb.co/Ngy2P2WK/B7.png",
    "B8": "https://i.ibb.co/jk0nZMQZ/B8.png",

    # C set
    "C1": "https://i.ibb.co/MDjLjVfs/C1.png",
    "C2": "https://i.ibb.co/HDjrD7jy/C2.png",
    "C3": "https://i.ibb.co/1YMzYLcz/C3.png",
    "C4": "https://i.ibb.co/w84PYQ8/C4.png",
    "C5": "https://i.ibb.co/jv7jBsvw/C5.png",
    "C6": "https://i.ibb.co/wFkLV1WP/C6.png",
    "C7": "https://i.ibb.co/Rkz2PwJR/C7.png",
    "C8": "https://i.ibb.co/pNH6QXt/C8.png",

    # D set
    "D1": "https://i.ibb.co/Ggr08Qc/D1.png",
    "D2": "https://i.ibb.co/zTG7ZwRG/D2.png",
    "D3": "https://i.ibb.co/pjh7PMvZ/D3.png",
    "D4": "https://i.ibb.co/HTHWbXT5/D4.png",
    "D5": "https://i.ibb.co/yFXYSjxf/D5.png",
    "D6": "https://i.ibb.co/N62Vwtbx/D6.png",
    "D7": "https://i.ibb.co/GQW06yNs/D7.png",
    "D8": "https://i.ibb.co/v6nfH5mm/D8.png",

    # E set
    "E1": "https://i.ibb.co/N60FGfz4/E1.png",
    "E2": "https://i.ibb.co/rRL5dBJb/E2.png",
    "E3": "https://i.ibb.co/YTLp9yry/E3.png",
    "E4": "https://i.ibb.co/h12pfCV3/E4.png",
    "E5": "https://i.ibb.co/0R18wM6z/E5.png",
    "E6": "https://i.ibb.co/VWhtL1Hh/E6.png",
    "E7": "https://i.ibb.co/W4jgCvb7/E7.png",
    "E8": "https://i.ibb.co/TBTGDnmB/E8.png",

    # F set
    "F1": "https://i.ibb.co/Vpxf7DsG/F1.png",
    "F2": "https://i.ibb.co/b5ZLMmb4/F2.png",
    "F3": "https://i.ibb.co/9kStFxyX/F3.png",
    "F4": "https://i.ibb.co/SXg5JHP1/F4.png",
    "F5": "https://i.ibb.co/QjPPSs7v/F5.png",
    "F6": "https://i.ibb.co/0jzjSz4D/F6.png",
    "F7": "https://i.ibb.co/ZRKFJbQb/F7.png",
    "F8": "https://i.ibb.co/BVBF9RLj/F8.png",

    # G set
    "G1": "https://i.ibb.co/G4jyj2P4/G1.png",
    "G2": "https://i.ibb.co/WNNVmHvZ/G2.png",
    "G3": "https://i.ibb.co/C35cLntt/G3.png",
    "G4": "https://i.ibb.co/9HZB9gXB/G4.png",
    "G5": "https://i.ibb.co/HT5Yf89N/G5.png",
    "G6": "https://i.ibb.co/cKXC9JS7/G6.png",
    "G7": "https://i.ibb.co/9kk4VncX/G7.png",
    "G8": "https://i.ibb.co/DDKGDpSQ/G8.png",

    # H set
    "H1": "https://i.ibb.co/bgM5SshR/H1.png",
    "H2": "https://i.ibb.co/dJQFRBwV/H2.png",
    "H3": "https://i.ibb.co/6Jwpf9sg/H3.png",
    "H4": "https://i.ibb.co/7NLCRjxj/H4.png",
    "H5": "https://i.ibb.co/sd9QNQQH/H5.png",
    "H6": "https://i.ibb.co/Kk0yzDK/H6.png",
    "H7": "https://i.ibb.co/7x0t9x2G/H7.png",
    "H8": "https://i.ibb.co/1JPFYTBr/H8.png",
}


    


FISH_IMAGES_BY_ZONE_RARITY: Dict[str, Dict[str, str]] = {
    "pond": {
        "part": "https://i.ibb.co/gFdC2Mgw/57d76c68-ab77-4363-839b-53e821344cd4.png",
        "common": "https://thumbs.dreamstime.com/b/cartoon-gray-fish-illustration-digital-art-cartoon-gray-fish-illustration-digital-art-380198597.jpg",
        "uncommon": "https://i.pinimg.com/736x/82/0e/82/820e828e963939f2a91e940e55d61ad3.jpg",
        "rare": "https://ih1.redbubble.net/image.1197727643.6143/raf,360x360,075,t,fafafa:ca443f4786.jpg",
        "epic": "https://i.etsystatic.com/16060308/r/il/be76d1/6538996724/il_fullxfull.6538996724_7vek.jpg",
        "legendary": "https://ih1.redbubble.net/image.4938759497.5127/flat,750x,075,f-pad,750x1000,f8f8f8.jpg",
    },
    "river": {
        "part": "https://i.ibb.co/gFdC2Mgw/57d76c68-ab77-4363-839b-53e821344cd4.png",
        "common": "https://thumbs.dreamstime.com/b/cartoon-gray-fish-illustration-digital-art-cartoon-gray-fish-illustration-digital-art-380198597.jpg",
        "uncommon": "https://i.pinimg.com/736x/82/0e/82/820e828e963939f2a91e940e55d61ad3.jpg",
        "rare": "https://ih1.redbubble.net/image.1197727643.6143/raf,360x360,075,t,fafafa:ca443f4786.jpg",
        "epic": "https://i.etsystatic.com/16060308/r/il/be76d1/6538996724/il_fullxfull.6538996724_7vek.jpg",
        "legendary": "https://ih1.redbubble.net/image.4938759497.5127/flat,750x,075,f-pad,750x1000,f8f8f8.jpg",
    },
    "coast": {
        "part": "https://i.ibb.co/gFdC2Mgw/57d76c68-ab77-4363-839b-53e821344cd4.png",
        "common": "https://thumbs.dreamstime.com/b/cartoon-gray-fish-illustration-digital-art-cartoon-gray-fish-illustration-digital-art-380198597.jpg",
        "uncommon": "https://i.pinimg.com/736x/82/0e/82/820e828e963939f2a91e940e55d61ad3.jpg",
        "rare": "https://ih1.redbubble.net/image.1197727643.6143/raf,360x360,075,t,fafafa:ca443f4786.jpg",
        "epic": "https://i.etsystatic.com/16060308/r/il/be76d1/6538996724/il_fullxfull.6538996724_7vek.jpg",
        "legendary": "https://ih1.redbubble.net/image.4938759497.5127/flat,750x,075,f-pad,750x1000,f8f8f8.jpg",
    },
    "abyss": {
        "part": "https://i.ibb.co/gFdC2Mgw/57d76c68-ab77-4363-839b-53e821344cd4.png",
        "common": "https://thumbs.dreamstime.com/b/cartoon-gray-fish-illustration-digital-art-cartoon-gray-fish-illustration-digital-art-380198597.jpg",
        "uncommon": "https://i.pinimg.com/736x/82/0e/82/820e828e963939f2a91e940e55d61ad3.jpg",
        "rare": "https://ih1.redbubble.net/image.1197727643.6143/raf,360x360,075,t,fafafa:ca443f4786.jpg",
        "epic": "https://i.etsystatic.com/16060308/r/il/be76d1/6538996724/il_fullxfull.6538996724_7vek.jpg",
        "legendary": "https://ih1.redbubble.net/image.4938759497.5127/flat,750x,075,f-pad,750x1000,f8f8f8.jpg",
    },
}




# Zone-specific species names per rarity (flavor-only; does not affect pricing)
SPECIES: Dict[str, Dict[str, List[str]]] = {
    "pond": {
        "part": [
            "Fishing Map",
            "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8",
            "B1", "B2", "B3", "B4", "B5",
        ],
        "common":    ["Bluegill", "Muddy Carp", "Lilypad Perch"],
        "uncommon":  ["Speckled Sunfish", "Dusk Minnow"],
        "rare":      ["Moonlit Koi"],
        "epic":      ["Verdant Arowana"],
        "legendary": ["Pond Guardian"],
    },
    "river": {
        "part": [
            "Fishing Map",
            "B6", "B7", "B8",
            "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8",
            "D1", "D2",
        ],
        "common":    ["River Perch", "Stone Shiner"],
        "uncommon":  ["Silver Chub", "Swift Darter"],
        "rare":      ["Bronze Trout"],
        "epic":      ["Runebrook Salmon"],
        "legendary": ["King of Currents"],
    },
    "coast": {
        "part": [
            "Fishing Map",
            "D3", "D4", "D5", "D6", "D7", "D8",
            "E1", "E2", "E3", "E4", "E5", "E6", "E7",
        ],
        "common":    ["Tide Sardine", "Pebble Mackerel"],
        "uncommon":  ["Sea Bream", "Glimmer Hake"],
        "rare":      ["Opal Snapper"],
        "epic":      ["Storm Marlin"],
        "legendary": ["Leviathan Fry"],
    },
    "abyss": {
        "part": [
            "Fishing Map",
            "E8",
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8",
            "G1", "G2", "G3", "G4",
        ],
        "common":    ["Gloom Smelt"],
        "uncommon":  ["Twilight Cod"],
        "rare":      ["Nightfang Eel"],
        "epic":      ["Phantom Angler"],
        "legendary": ["Abyssal Sovereign"],
    },
    "rift": {
        "part": [
            "Fishing Map",
            "G5", "G6", "G7", "G8",
            "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8",
        ],
        "common": [
            "Bluegill",
            "Muddy Carp",
            "Lilypad Perch",
            "River Perch",
            "Stone Shiner",
            "Tide Sardine",
            "Pebble Mackerel",
            "Gloom Smelt",
        ],
        "uncommon": [
            "Speckled Sunfish",
            "Dusk Minnow",
            "Silver Chub",
            "Swift Darter",
            "Sea Bream",
            "Glimmer Hake",
            "Twilight Cod",
        ],
        "rare": [
            "Moonlit Koi",
            "Bronze Trout",
            "Opal Snapper",
            "Nightfang Eel",
        ],
        "epic": [
            "Verdant Arowana",
            "Runebrook Salmon",
            "Storm Marlin",
            "Phantom Angler",
        ],
        "legendary": [
            "Pond Guardian",
            "King of Currents",
            "Leviathan Fry",
            "Abyssal Sovereign",
        ],
    },
}

PART_RENAMES: Dict[str, str] = {
    # A set
    "A1": "Map Fragment: Lilybanks",
    "A2": "Map Fragment: Reed Hollow",
    "A3": "Map Fragment: Stillwater Bend",
    "A4": "Map Fragment: Frogfen",
    "A5": "Map Fragment: Sunken Roots",
    "A6": "Map Fragment: Mossmere",
    "A7": "Map Fragment: Quiet Cove",
    "A8": "Map Fragment: Greenveil",

    # B set
    "B1": "Map Fragment: Shallow Run",
    "B2": "Map Fragment: Stone Crossing",
    "B3": "Map Fragment: Silver Reach",
    "B4": "Map Fragment: Driftbank",
    "B5": "Map Fragment: Old Ford",
    "B6": "Map Fragment: Rapid Gate",
    "B7": "Map Fragment: Foamwake",
    "B8": "Map Fragment: Currentfall",

    # C set
    "C1": "Map Fragment: Saltpoint",
    "C2": "Map Fragment: Breaker Shoal",
    "C3": "Map Fragment: Gullrock",
    "C4": "Map Fragment: Tideglass Bay",
    "C5": "Map Fragment: Kelpstrand",
    "C6": "Map Fragment: Whitecap Edge",
    "C7": "Map Fragment: Opal Shoals",
    "C8": "Map Fragment: Mariner’s Reach",

    # D set
    "D1": "Map Fragment: Thunder Shoals",
    "D2": "Map Fragment: Blackwave",
    "D3": "Map Fragment: Barnacle Reach",
    "D4": "Map Fragment: Surfbreak",
    "D5": "Map Fragment: Marlin Deep",
    "D6": "Map Fragment: Whitewake",
    "D7": "Map Fragment: Riptide Pass",
    "D8": "Map Fragment: Seaflare Point",

    # E set
    "E1": "Map Fragment: Gloom Trench",
    "E2": "Map Fragment: Blackwater Rift",
    "E3": "Map Fragment: Lightless Shelf",
    "E4": "Map Fragment: Void Drop",
    "E5": "Map Fragment: Starless Reach",
    "E6": "Map Fragment: Eelway",
    "E7": "Map Fragment: Nightcoil",
    "E8": "Map Fragment: Trench Crown",

    # F set
    "F1": "Map Fragment: Prism Scar",
    "F2": "Map Fragment: Moonfold",
    "F3": "Map Fragment: Leybreak",
    "F4": "Map Fragment: Arc Split",
    "F5": "Map Fragment: Warped Crossing",
    "F6": "Map Fragment: Sigil Drift",
    "F7": "Map Fragment: Etherfall",
    "F8": "Map Fragment: Spectral Divide",

    # G set
    "G1": "Map Fragment: Mythreach",
    "G2": "Map Fragment: Chromatic Verge",
    "G3": "Map Fragment: Rune Lattice",
    "G4": "Map Fragment: Aurora Span",
    "G5": "Map Fragment: Core Fault",
    "G6": "Map Fragment: Glitterway",
    "G7": "Map Fragment: Prism Wake",
    "G8": "Map Fragment: Flux Edge",

    # H set
    "H1": "Map Fragment: Hollow Tide",
    "H2": "Map Fragment: Dawn Rift",
    "H3": "Map Fragment: Wyrmglass Way",
    "H4": "Map Fragment: Starcoil Path",
    "H5": "Map Fragment: Nebula Crossing",
    "H6": "Map Fragment: Astral Reach",
    "H7": "Map Fragment: Gilded Arc",
    "H8": "Map Fragment: Crown of Currents",
}
# Update image dictionary keys
FISH_IMAGES_BY_SPECIES = {
    PART_RENAMES.get(k, k): v
    for k, v in FISH_IMAGES_BY_SPECIES.items()
}

# Update SPECIES "part" lists
for zone_key, rarity_map in SPECIES.items():
    if "part" in rarity_map:
        rarity_map["part"] = [PART_RENAMES.get(x, x) for x in rarity_map["part"]]



# Snapshot of the original, built-in species (so we know what's override-only)
BASE_SPECIES_SNAPSHOT: Dict[str, Dict[str, List[str]]] = {
    zk: {rk: list(lst) for rk, lst in rmap.items()} for zk, rmap in SPECIES.items()
}

def _species_to_rarity_zones() -> Dict[str, List[Tuple[str, str]]]:
    """
    Build an index:
      species_name -> list[(zone_key, rarity)]
    Uses SPECIES (current runtime table, including overrides).
    """
    idx: Dict[str, List[Tuple[str, str]]] = {}
    for zk, rmap in SPECIES.items():
        for rarity, lst in rmap.items():
            for s in lst:
                idx.setdefault(s, []).append((zk, rarity))
    return idx


def _find_species_records(species_name: str) -> List[Tuple[str, str]]:
    """
    Return list[(zone_key, rarity)] where this species exists in SPECIES.
    Case-insensitive match with fallback to exact.
    """
    idx = _species_to_rarity_zones()
    if species_name in idx:
        return idx[species_name]

    # Case-insensitive fallback
    lower = species_name.lower()
    for k, v in idx.items():
        if k.lower() == lower:
            return v
    return []


def _canonical_species_name(species_name: str) -> str:
    """Return canonical species spelling from SPECIES if case-insensitive match exists."""
    idx = _species_to_rarity_zones()
    if species_name in idx:
        return species_name
    lower = species_name.lower()
    for k in idx.keys():
        if k.lower() == lower:
            return k
    return species_name



def _fish_image_for(zone_key: str, species: str, rarity: str) -> Optional[str]:
    # Try exact species first
    url = FISH_IMAGES_BY_SPECIES.get(species)
    if url:
        return url
    # Then (zone, rarity)
    return FISH_IMAGES_BY_ZONE_RARITY.get(zone_key, {}).get(rarity)

def _compute_zone_completion(zone_key: str, fishdex: Dict[str, List[str]]) -> tuple[int, int]:
    """Return (have, total) for a zone."""
    caught = set(fishdex.get(zone_key, []))
    total = sum(len(v) for v in SPECIES[zone_key].values())
    have = len(caught)
    return have, total

def _compute_global_completion(fishdex: Dict[str, List[str]]) -> tuple[int, int, float]:
    """Return (have, total, percent) across all zones."""
    have_sum = 0
    total_sum = 0
    for zk in SPECIES.keys():
        have, total = _compute_zone_completion(zk, fishdex)
        have_sum += have
        total_sum += total
    pct = (have_sum / total_sum * 100.0) if total_sum else 0.0
    return have_sum, total_sum, pct


class FishdexView(ui.View):
    def __init__(self, cog: "Fishing", user_id: int, start_zone_index: int = 0):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.zone_keys = list(SPECIES.keys())  # order of pages
        self.index = start_zone_index

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id

    def _current_embed(self, fishdex: Dict[str, List[str]]) -> discord.Embed:
        zone_key = self.zone_keys[self.index]
        return _fishdex_zone_embed(zone_key, fishdex)

    @ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button):
        data = await self.cog.config.user(interaction.user).all()
        self.index = (self.index - 1) % len(self.zone_keys)
        await interaction.response.edit_message(embed=self._current_embed(data["fishdex"]), view=self)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button):
        data = await self.cog.config.user(interaction.user).all()
        self.index = (self.index + 1) % len(self.zone_keys)
        await interaction.response.edit_message(embed=self._current_embed(data["fishdex"]), view=self)

    @ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="📖 Fishdex closed.", embed=None, view=None)
    
    @ui.button(label="Summary", style=discord.ButtonStyle.secondary, emoji="📊")
    async def summary_btn(self, interaction: discord.Interaction, button: ui.Button):
        data = await self.cog.config.user(interaction.user).all()
        embed = _fishdex_summary_embed(data["fishdex"])
        await interaction.response.edit_message(embed=embed, view=self)



# ---------- Loot Table Logic ----------
def _weighted_choice(table: Dict[str, float]) -> str:
    items = list(table.items())
    total = sum(w for _, w in items)
    pick = random.random() * total if total > 0 else 0.0
    upto = 0.0
    for rarity, w in items:
        if upto + w >= pick:
            return rarity
        upto += w
    return items[-1][0] if items else "common"

def _fishdex_embed(fishdex: Dict[str, List[str]]) -> discord.Embed:
    e = discord.Embed(title="🎣 Fishdex", colour=discord.Colour.blue())
    for zone_key, zone_species in SPECIES.items():
        caught = set(fishdex.get(zone_key, []))
        lines = []
        for rarity, species_list in zone_species.items():
            for s in species_list:
                mark = "✅" if s in caught else "❌"
                lines.append(f"{mark} {s} (*{rarity.title()}*)")
        zone = ZONES[zone_key]
        e.add_field(name=zone.name, value="\n".join(lines), inline=False)
    return e



def _compose_table(*, rod: Rod, bait: Optional[Bait], zone: Zone) -> Dict[str, float]:
    # Start with base table
    table = dict(BASE_RARITY_TABLE)

    # Zone tweaks (additive to weights)
    for r, delta in zone.base_table.items():
        table[r] = max(0.0, table.get(r, 0.0) + delta)

    # Rod power shifts weight upward
    for _ in range(rod.power):
        for (src, dst, frac) in [
            ("common", "uncommon", 0.02),
            ("uncommon", "rare", 0.01),
            ("rare", "epic", 0.005),
        ]:
            amt = table[src] * frac
            table[src] -= amt
            table[dst] += amt

    # Bait boosts non-common, then renormalize to original magnitude
    if bait:
        boost = bait.rarity_boost
        for r in ("uncommon", "rare", "epic", "legendary"):
            table[r] *= (1.0 + boost)
        scale = sum(BASE_RARITY_TABLE.values()) / max(sum(table.values()), 1e-9)
        for k in table:
            table[k] *= scale

    for k in list(table.keys()):
        table[k] = max(0.0, table[k])
    return table


def roll_catch(*, rod: Rod, bait: Optional[Bait], zone: Zone) -> Catch:
    table = _compose_table(rod=rod, bait=bait, zone=zone)
    rarity = _weighted_choice(table)
    species_pool = SPECIES.get(zone.key, {}).get(rarity, [rarity.title()])
    species = random.choice(species_pool)
    return Catch(rarity=rarity, species=species)


# ---------- Economy Protocol ----------
class Economy(Protocol):
    async def get_balance(self, user): ...
    async def add_wellcoins(self, user, amount: float): ...
    async def take_wellcoins(self, user, amount: float, force: bool = False): ...

def _fishdex_summary_embed(fishdex: Dict[str, List[str]]) -> discord.Embed:
    e = discord.Embed(
        title="📖 Fishdex — Summary",
        description="Per-zone completion and total progress",
        colour=discord.Colour.blurple(),
    )

    for zk in SPECIES.keys():
        zone = ZONES[zk]
        have, total = _compute_zone_completion(zk, fishdex)
        pct = (have / total * 100.0) if total else 0.0
        e.add_field(
            name=zone.name,
            value=f"**{have}/{total}** ({pct:.0f}%)",
            inline=True
        )

    g_have, g_total, g_pct = _compute_global_completion(fishdex)
    e.add_field(name="—", value="‎", inline=False)  # thin spacer
    e.add_field(name="TOTAL", value=f"**{g_have}/{g_total}** ({g_pct:.0f}%)", inline=False)
    return e



def _get_economy(bot: Red) -> Economy:
    econ = bot.get_cog("NexusExchange")
    if not econ:
        raise RuntimeError("NexusExchange cog not found. Please load it so Fishing can use Wellcoins.")
    for fn in ("get_balance", "add_wellcoins", "take_wellcoins"):
        if not hasattr(econ, fn):
            raise RuntimeError(f"NexusExchange is missing required method `{fn}`.")
    return econ  # type: ignore[return-value]


# ---------- Embeds ----------
RARITY_COLOR = {
    "part": discord.Colour.light_grey(),
    "common": discord.Colour.light_grey(),
    "uncommon": discord.Colour.green(),
    "rare": discord.Colour.blue(),
    "epic": discord.Colour.purple(),
    "legendary": discord.Colour.gold(),
}

def _fishdex_zone_embed(zone_key: str, fishdex: Dict[str, List[str]]) -> discord.Embed:
    zone = ZONES[zone_key]
    caught = set(fishdex.get(zone_key, []))
    total = sum(len(v) for v in SPECIES[zone_key].values())
    have = len(caught)
    pct = (have / total * 100.0) if total else 0.0

    e = discord.Embed(
        title=f"📖 Fishdex — {zone.name}",
        description=f"Completion: **{have}/{total}** ({pct:.0f}%)",
        colour=discord.Colour.blue(),
    )
    if zone.key in ZONE_IMAGES:
        e.set_thumbnail(url=ZONE_IMAGES[zone.key])

    for rarity in ("part", "common", "uncommon", "rare", "epic", "legendary"):
        species_list = SPECIES[zone_key].get(rarity, [])
        if not species_list:
            continue
        lines = []
        for s in species_list:
            mark = "✅" if s in caught else "❌"
            lines.append(f"{mark} {s}")
        e.add_field(name=rarity.title(), value="\n".join(lines), inline=False)

    # Global completion footer
    g_have, g_total, g_pct = _compute_global_completion(fishdex)
    e.set_footer(text=f"Total completion: {g_have}/{g_total} ({g_pct:.0f}%)")
    return e

class CatchView(ui.View):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id

    @ui.button(label="Fish Again", style=discord.ButtonStyle.primary, emoji="🎣")
    async def fish_again_btn(self, interaction: discord.Interaction, button: ui.Button):
        async with self.cog._lock_for(interaction.user.id):
            embed, delete_after = await self.cog._attempt_fish(interaction)
            if delete_after:
                await interaction.response.send_message(
                    embed=embed,
                    view=CatchView(self.cog, interaction.user.id),
                    delete_after=delete_after
                )
            else:
                await interaction.response.send_message(
                    embed=embed,
                    view=CatchView(self.cog, interaction.user.id)
                )





def _catch_embed(*, zone: Zone, rod: Rod, bait: Bait | None, catch: Catch, durability_now: int) -> discord.Embed:
    e = discord.Embed(
        title=f"You fished in {zone.name}!",
        description=f"**{catch.species}** (*{catch.rarity.title()}*)",
        colour=RARITY_COLOR.get(catch.rarity, discord.Colour.blurple()),
    )
    e.add_field(name="Rod", value=f"{rod.name} ({durability_now}/{rod.durability})", inline=True)
    e.add_field(name="Zone", value=zone.name, inline=True)
    e.add_field(name="Bait", value=bait.name if bait else "None", inline=True)

    # Thumbnail = zone image
    if zone.key in ZONE_IMAGES:
        e.set_thumbnail(url=ZONE_IMAGES[zone.key])

    # Main image = fish image (species first, then (zone, rarity) fallback)
    fish_url = _fish_image_for(zone.key, catch.species, catch.rarity)
    if fish_url:
        e.set_image(url=fish_url)

    return e




def _inventory_embed(*, rod: Rod, zone: Zone, inv: Dict[str, int], bait_inv: Dict[str, int], dur: int) -> discord.Embed:
    e = discord.Embed(
        title="Tackle Box",
        description=f"Rod: **{rod.name}** ({dur}/{rod.durability})\nZone: **{zone.name}**",
        colour=discord.Colour.teal(),
    )
    fish_lines = "\n".join(f"{r.title()}: **{inv.get(r,0)}**" for r in RARITY_PRICES)
    bait_lines = "\n".join(f"{k.title()}: **{v}**" for k, v in bait_inv.items()) or "None"
    e.add_field(name="Fish", value=fish_lines, inline=False)
    e.add_field(name="Bait", value=bait_lines, inline=False)
    return e

def _prices_embed(*, zone: Zone) -> discord.Embed:
    e = discord.Embed(title=f"Prices • {zone.name}", colour=discord.Colour.orange())
    for r, p in RARITY_PRICES.items():
        e.add_field(name=r.title(), value=f"{p:.2f} → {(p*zone.sell_multiplier):.2f} WC", inline=True)
    e.set_footer(text=f"Zone Multiplier ×{zone.sell_multiplier:.2f}")
    return e

def _sell_embed(*, zone: Zone, sold: List[Tuple[str, int, float]], total: float) -> discord.Embed:
    e = discord.Embed(title=f"Sold at {zone.name}", colour=discord.Colour.dark_gold())
    for rarity, qty, amt in sold:
        e.add_field(name=rarity.title(), value=f"× {qty} → {amt:.2f} WC", inline=False)
    e.add_field(name="Total", value=f"**{total:.2f} WC**", inline=False)
    e.set_footer(text=f"Zone Multiplier ×{zone.sell_multiplier:.2f}")
    return e


# ---------- Views (Buttons & Selects) ----------

class MainMenu(ui.View):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id

    @ui.button(label="Fish", style=discord.ButtonStyle.primary, emoji="🎣")
    async def fish_btn(self, interaction: discord.Interaction, button: ui.Button):
        async with self.cog._lock_for(interaction.user.id):
            embed, delete_after = await self.cog._attempt_fish(interaction)
            if delete_after:
                await interaction.response.send_message(
                    embed=embed,
                    view=CatchView(self.cog, interaction.user.id),
                    delete_after=delete_after
                )
            else:
                await interaction.response.send_message(
                    embed=embed,
                    view=CatchView(self.cog, interaction.user.id)
                )




    @ui.button(label="Sell", style=discord.ButtonStyle.success, emoji="💰")
    async def sell_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(view=SellMenu(self.cog, interaction.user.id), ephemeral=True)

    @ui.button(label="Zone", style=discord.ButtonStyle.secondary, emoji="🗺️")
    async def zone_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(view=ZoneMenu(self.cog, interaction.user.id), ephemeral=True)

    @ui.button(label="Shop", style=discord.ButtonStyle.secondary, emoji="🛒")
    async def shop_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(view=ShopMenu(self.cog, interaction.user.id), ephemeral=True)

    @ui.button(label="Repair", style=discord.ButtonStyle.danger, emoji="🔧")
    async def repair_btn(self, interaction: discord.Interaction, button: ui.Button):
        econ = _get_economy(self.cog.bot)
        data = await self.cog.config.user(interaction.user).all()
        rod = RODS.get(data["rod"], RODS["twig"])
        price = rod.price
        if price > 0:
            try:
                await econ.take_wellcoins(interaction.user, price, force=False)
            except ValueError:
                return await interaction.response.send_message(
                    f"Insufficient funds. Need {price:.2f} WC.", ephemeral=True
                )
        await self.cog.config.user(interaction.user).rod_durability.set(rod.durability)
        await interaction.response.send_message(
            f"🔧 Repaired **{rod.name}** to full durability ({rod.durability}).", ephemeral=True
        )
    
    @ui.button(label="Fishdex", style=discord.ButtonStyle.secondary, emoji="📖")
    async def fishdex_btn(self, interaction: discord.Interaction, button: ui.Button):
        data = await self.cog.config.user(interaction.user).all()
        view = FishdexView(self.cog, interaction.user.id, start_zone_index=0)
        # Start on the global Summary page instead of a zone page:
        embed = _fishdex_summary_embed(data["fishdex"])
        await interaction.response.send_message(embed=embed, view=view)

    



class SellMenu(ui.View):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

        self.add_item(SellAllButton(cog, user_id))
        self.add_item(SellSelect(cog, user_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id


class SellAllButton(ui.Button):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(label="Sell All", style=discord.ButtonStyle.success, emoji="🧺")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        econ = _get_economy(self.cog.bot)
        data = await self.cog.config.user(interaction.user).all()
        zone = ZONES.get(data["zone"], ZONES["pond"])
        inv = data["inventory"]

        def price_for(r: str, qty: int) -> float:
            return RARITY_PRICES.get(r, 0.0) * zone.sell_multiplier * qty

        total = 0.0
        sold_detail: List[Tuple[str, int, float]] = []
        for r, qty in list(inv.items()):
            qty = int(qty)
            if qty <= 0:
                continue
            p = price_for(r, qty)
            total += p
            sold_detail.append((r, qty, p))
            inv[r] = 0

        data["inventory"] = inv
        await self.cog.config.user(interaction.user).set(data)

        if total <= 0:
            return await interaction.response.send_message("No fish to sell.", ephemeral=True)
        await econ.add_wellcoins(interaction.user, float(total))
        await interaction.response.send_message(embed=_sell_embed(zone=zone, sold=sold_detail, total=total), ephemeral=True)


class SellSelect(ui.Select):
    def __init__(self, cog: "Fishing", user_id: int):
        options = [discord.SelectOption(label=r.title(), value=r) for r in RARITY_PRICES.keys()]
        super().__init__(placeholder="Sell by rarity (sell all of selected)", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        econ = _get_economy(self.cog.bot)
        choice = self.values[0]
        data = await self.cog.config.user(interaction.user).all()
        zone = ZONES.get(data["zone"], ZONES["pond"])
        inv = data["inventory"]

        have = int(inv.get(choice, 0))
        if have <= 0:
            return await interaction.response.send_message(f"You have no **{choice}** fish.", ephemeral=True)

        total = RARITY_PRICES.get(choice, 0.0) * zone.sell_multiplier * have
        inv[choice] = 0
        data["inventory"] = inv
        await self.cog.config.user(interaction.user).set(data)
        await econ.add_wellcoins(interaction.user, float(total))
        await interaction.response.send_message(
            embed=_sell_embed(zone=zone, sold=[(choice, have, total)], total=total),
            ephemeral=True
        )


class ZoneMenu(ui.View):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.add_item(ZoneSelect(cog, user_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id


class ZoneSelect(ui.Select):
    def __init__(self, cog: "Fishing", user_id: int):
        options = []
        for z in ZONES.values():
            options.append(
                discord.SelectOption(
                    label=z.name,
                    description=f"Sell ×{z.sell_multiplier:.2f} • Unlock {z.unlock_price:.2f} WC",
                    value=z.key,
                )
            )
        super().__init__(placeholder="Choose or unlock a zone", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        econ = _get_economy(self.cog.bot)
        zone_key = self.values[0]
        data = await self.cog.config.user(interaction.user).all()
        unlocked = set(data["unlocked_zones"])

        if zone_key not in ZONES:
            return await interaction.response.send_message("Unknown zone.", ephemeral=True)

        zone = ZONES[zone_key]
        if zone_key not in unlocked:
            price = zone.unlock_price
            if price > 0:
                try:
                    await econ.take_wellcoins(interaction.user, price, force=False)
                except ValueError:
                    return await interaction.response.send_message(
                        f"Insufficient funds to unlock **{zone.name}** (need {price:.2f} WC).",
                        ephemeral=True
                    )
            data["unlocked_zones"].append(zone_key)

        data["zone"] = zone_key
        await self.cog.config.user(interaction.user).set(data)
        await interaction.response.send_message(f"✅ Active zone set to **{zone.name}**.", ephemeral=True)


class ShopMenu(ui.View):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.add_item(BaitShopButton(cog, user_id))
        self.add_item(RodShopButton(cog, user_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id


class BaitShopButton(ui.Button):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(label="Bait Shop", style=discord.ButtonStyle.secondary, emoji="🪱")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=BaitShopView(self.cog, interaction.user.id), ephemeral=True)


class RodShopButton(ui.Button):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(label="Rod Shop", style=discord.ButtonStyle.secondary, emoji="🪝")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=RodShopView(self.cog, interaction.user.id), ephemeral=True)


class BaitShopView(ui.View):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.add_item(BaitSelect(cog, user_id))
        self.add_item(BaitQtySelect(cog, user_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id


class BaitSelect(ui.Select):
    def __init__(self, cog: "Fishing", user_id: int):
        options = [
            discord.SelectOption(label=f"{b.name}", description=f"{b.price:.2f} WC • +{int(b.rarity_boost*1000)/10}% rare boost", value=key)
            for key, b in BAITS.items()
        ]
        super().__init__(placeholder="Choose bait", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        # stash the choice in view state using custom_id on the parent
        self.view.selected_bait_key = self.values[0]  # type: ignore[attr-defined]
        await interaction.response.send_message(f"Selected **{BAITS[self.values[0]].name}**. Now choose quantity.", ephemeral=True)


class BaitQtySelect(ui.Select):
    def __init__(self, cog: "Fishing", user_id: int):
        options = [discord.SelectOption(label=str(n), value=str(n)) for n in (1, 5, 10, 25)]
        super().__init__(placeholder="Quantity", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        bait_key = getattr(self.view, "selected_bait_key", None)  # type: ignore[attr-defined]
        if not bait_key:
            return await interaction.response.send_message("Pick a bait first.", ephemeral=True)
        qty = int(self.values[0])
        bait = BAITS[bait_key]
        total_cost = bait.price * qty
        econ = _get_economy(self.cog.bot)
        try:
            await econ.take_wellcoins(interaction.user, total_cost, force=False)
        except ValueError:
            return await interaction.response.send_message(
                f"Insufficient funds. Need {total_cost:.2f} WC.", ephemeral=True
            )
        have = await self.cog.config.user(interaction.user).bait()
        have[bait_key] = int(have.get(bait_key, 0)) + qty
        await self.cog.config.user(interaction.user).bait.set(have)
        await interaction.response.send_message(
            f"🪱 Purchased **{qty}× {bait.name}** for {total_cost:.2f} WC.",
            ephemeral=True
        )


class RodShopView(ui.View):
    def __init__(self, cog: "Fishing", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.add_item(RodSelect(cog, user_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id


class RodSelect(ui.Select):
    def __init__(self, cog: "Fishing", user_id: int):
        options = []
        for key, r in RODS.items():
            options.append(discord.SelectOption(
                label=f"{r.name}",
                description=f"{r.price:.2f} WC • P{r.power} • Dur {r.durability}",
                value=key
            ))
        super().__init__(placeholder="Choose a rod to buy & equip", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        rod_key = self.values[0]
        rod = RODS[rod_key]
        econ = _get_economy(self.cog.bot)
        if rod.price > 0:
            try:
                await econ.take_wellcoins(interaction.user, rod.price, force=False)
            except ValueError:
                return await interaction.response.send_message(
                    f"Insufficient funds. Need {rod.price:.2f} WC.", ephemeral=True
                )
        data = await self.cog.config.user(interaction.user).all()
        data["rod"] = rod.key
        data["rod_durability"] = rod.durability
        await self.cog.config.user(interaction.user).set(data)
        await interaction.response.send_message(
            f"🪝 You bought and equipped **{rod.name}** (Durability {rod.durability}).",
            ephemeral=True
        )


# ---------- The Cog ----------
class Fishing(commands.Cog):
    """Catch fish, sell, shop, switch/unlock zones, and repair — via a button menu."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=324234324234, force_registration=True)

        default_user = {
            "rod": "twig",
            "rod_durability": RODS["twig"].durability,
            "bait": {k: 0 for k in BAITS.keys()},
            "zone": "pond",
            "unlocked_zones": ["pond"],
            "inventory": {r: 0 for r in RARITY_PRICES.keys()},
            "last_fished_ts": 0.0,
            "fishdex": {zone: [] for zone in SPECIES.keys()},  # per-zone caught species
        }
        self.config.register_user(**default_user)
        self._locks: Dict[int, asyncio.Lock] = {}

        default_global = {
            "species_overrides": {},   # { zone_key: { rarity: [species, ...], ... }, ... }
            "species_images": {},      # { species_name: image_url }
        }
        self.config.register_global(**default_global)

    async def cog_load(self):
        """Called by Red when the cog is loaded (or reloaded)."""
        await self._hydrate_runtime_tables()
    
    async def _hydrate_runtime_tables(self):
        overrides = await self.config.species_overrides() or {}
        images = await self.config.species_images() or {}
    
        # Merge species overrides into SPECIES
        for zone_key, rarities in overrides.items():
            if zone_key not in SPECIES:
                continue
            for rarity, species_list in (rarities or {}).items():
                if rarity not in SPECIES[zone_key]:
                    SPECIES[zone_key][rarity] = []
                for s in species_list or []:
                    if s not in SPECIES[zone_key][rarity]:
                        SPECIES[zone_key][rarity].append(s)
    
        # Merge images
        for species_name, url in images.items():
            if isinstance(species_name, str) and isinstance(url, str) and url.lower().startswith(("http://", "https://")):
                FISH_IMAGES_BY_SPECIES[species_name] = url



    def _lock_for(self, user_id: int) -> asyncio.Lock:
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
        return lock
    
    async def _attempt_fish(self, interaction: discord.Interaction) -> Tuple[discord.Embed, Optional[float]]:
        """
        Performs one fishing attempt, respecting cooldown/durability/bait,
        applying junk/nothing chances, updating inventory/fishdex, and returning:
          (embed, delete_after_seconds | None)
        """
        econ = _get_economy(self.bot)
        user_conf = self.config.user(interaction.user)
        data = await user_conf.all()
    
        # Cooldown
        now = time.time()
        last = float(data.get("last_fished_ts", 0.0))
        remaining = COOLDOWN_SECONDS - (now - last)
        if remaining > 0:
            next_ts = int(last + COOLDOWN_SECONDS)
            e = discord.Embed(
                title="⏳ On cooldown",
                description=f"Try again <t:{next_ts}:R> (at <t:{next_ts}:t>).",
                colour=discord.Colour.orange(),
            )
            # auto-delete when cooldown is up (at least 1s so it doesn't insta-vanish)
            return e, max(1.0, remaining)
       
        quest_cog = self.bot.get_cog("FantasyJobBoard")
        if quest_cog:
          await quest_cog.record_progress(
          member=interaction.user,
          game="Fishing",
          objective="attempt",
          amount=1,
        )
            
        # Ensure fishdex exists
        fishdex = await self._ensure_fishdex(interaction.user)
    
        # Validate rod
        rod: Rod = RODS.get(data["rod"], RODS["twig"])
        if int(data.get("rod_durability", 0)) <= 0:
            e = discord.Embed(
                title="⛔ Broken Rod",
                description=f"Your **{rod.name}** is broken. Use **Repair**.",
                colour=discord.Colour.red(),
            )
            return e, None
    
        # Auto-consume best bait (if any)
        bait: Optional[Bait] = None
        if any(qty > 0 for qty in data["bait"].values()):
            owned = [(BAITS[k], q) for k, q in data["bait"].items() if q > 0 and k in BAITS]
            owned.sort(key=lambda t: BAITS[t[0].key].rarity_boost, reverse=True)
            bait = owned[0][0]
            data["bait"][bait.key] -= 1
    
        zone: Zone = ZONES.get(data["zone"], ZONES["pond"])
    
        # 25% junk, 25% nothing, 50% normal
        roll = random.random()
        caught_junk = roll < 0.25
        caught_nothing = (0.25 <= roll < 0.50)
    
        # Always consume durability and set cooldown on an attempt
        data["rod_durability"] = max(0, int(data["rod_durability"]) - 1)
        data["last_fished_ts"] = now
    
        if caught_junk:
            await econ.add_wellcoins(interaction.user, 1.0)
            e = discord.Embed(
                title=f"You fished in {zone.name}!",
                description=f"🗑️ You reeled in **junk** and found **1 WC**.",
                colour=discord.Colour.dark_grey(),
            )
            if zone.key in ZONE_IMAGES:
                e.set_thumbnail(url=ZONE_IMAGES[zone.key])
            e.add_field(name="Rod", value=f"{rod.name} ({data['rod_durability']}/{rod.durability})", inline=True)
            e.add_field(name="Zone", value=zone.name, inline=True)
            e.add_field(name="Bait", value=bait.name if bait else "None", inline=True)
    
        elif caught_nothing:
            e = discord.Embed(
                title=f"You fished in {zone.name}!",
                description="…and **caught nothing**.",
                colour=discord.Colour.light_grey(),
            )
            if zone.key in ZONE_IMAGES:
                e.set_thumbnail(url=ZONE_IMAGES[zone.key])
            e.add_field(name="Rod", value=f"{rod.name} ({data['rod_durability']}/{rod.durability})", inline=True)
            e.add_field(name="Zone", value=zone.name, inline=True)
            e.add_field(name="Bait", value=bait.name if bait else "None", inline=True)
    
        else:
            catch: Catch = roll_catch(rod=rod, bait=bait, zone=zone)
            data["inventory"][catch.rarity] = int(data["inventory"].get(catch.rarity, 0)) + 1
    
            zkey = zone.key
            lst = fishdex.get(zkey) or []
            if catch.species not in lst:
                lst.append(catch.species)
                fishdex[zkey] = lst
            data["fishdex"] = fishdex
    
            e = _catch_embed(zone=zone, rod=rod, bait=bait, catch=catch, durability_now=data["rod_durability"])
    
        await user_conf.set(data)
        return e, None

    @commands.hybrid_command(name="fish_info")
    async def fish_info(self, ctx: commands.Context, *, species_name: str):
        """
        Show info for a fish you have caught:
        image, rarity, zones it exists in, and base price.
        """
        data = await self.config.user(ctx.author).all()
        fishdex = data.get("fishdex") or {}
        if not isinstance(fishdex, dict):
            fishdex = {}
    
        # Build a set of all caught fish across all zones
        caught_all = set()
        for zk, lst in fishdex.items():
            if isinstance(lst, list):
                caught_all.update(lst)
    
        canonical = _canonical_species_name(species_name)
    
        if canonical not in caught_all:
            return await ctx.reply(
                f"📖 You have not caught **{canonical}** yet. Catch it first to view its details."
            )
    
        records = _find_species_records(canonical)
        if not records:
            # Fish exists in fishdex but not in SPECIES anymore (removed/renamed)
            e = discord.Embed(
                title=f"🐟 {canonical}",
                description="You have caught this fish, but it no longer exists in the current species table.",
                colour=discord.Colour.orange(),
            )
            img = FISH_IMAGES_BY_SPECIES.get(canonical)
            if img:
                e.set_image(url=img)
            return await ctx.reply(embed=e)
    
        # Prefer a record that matches where they actually caught it (if possible)
        caught_zone_key = None
        for zk, lst in fishdex.items():
            if isinstance(lst, list) and canonical in lst:
                caught_zone_key = zk
                break
    
        zone_key, rarity = records[0]
        if caught_zone_key:
            for zk, r in records:
                if zk == caught_zone_key:
                    zone_key, rarity = zk, r
                    break
    
        zone = ZONES.get(zone_key)
        zone_name = zone.name if zone else zone_key
    
        e = discord.Embed(
            title=f"🐟 {canonical}",
            description=f"Rarity: **{rarity.title()}**\nPrimary Zone: **{zone_name}**",
            colour=RARITY_COLOR.get(rarity, discord.Colour.blurple()),
        )
    
        # Image
        img = _fish_image_for(zone_key, canonical, rarity)
        if img:
            e.set_image(url=img)
    
            # Zones list (some fish can exist in multiple zones—rift case)
        zone_lines = []
        for zk, r in records:
            z = ZONES.get(zk)
            zone_lines.append(f"• {z.name if z else zk} (*{r.title()}*)")
        e.add_field(name="Appears In", value="\n".join(zone_lines), inline=False)
    
            # Pricing info
        base = float(RARITY_PRICES.get(rarity, 0.0))
        e.add_field(name="Base Sell Value", value=f"{base:.2f} WC", inline=True)
        if zone:
            e.add_field(name="Sell Value (in primary zone)", value=f"{base * zone.sell_multiplier:.2f} WC", inline=True)
    
        await ctx.reply(embed=e)
    
    
    @commands.hybrid_command(name="fish_caught")
    async def fish_caught(self, ctx: commands.Context):
        """
        Browse every fish you have caught across all zones (from fishdex),
        with images and details.
        """
        data = await self.config.user(ctx.author).all()
        fishdex = data.get("fishdex") or {}
        if not isinstance(fishdex, dict):
            fishdex = {}
    
        # Build entries: one per caught fish per zone.
        # (If you catch the same fish in multiple zones, you'll see multiple entries.)
        entries: List[Dict[str, str]] = []
        idx = _species_to_rarity_zones()
    
        for zone_key, caught_list in fishdex.items():
            if not isinstance(caught_list, list):
                continue
            for species in caught_list:
                if not isinstance(species, str):
                    continue
    
                # Determine rarity (prefer this zone's rarity if known)
                rarity = None
                for zk, r in idx.get(species, []):
                    if zk == zone_key:
                        rarity = r
                        break
                if rarity is None:
                        # fallback: first known rarity, else "common"
                    rarity = idx.get(species, [(zone_key, "common")])[0][1] if idx.get(species) else "common"
    
                entries.append({"species": species, "zone_key": zone_key, "rarity": rarity})
    
            # Stable ordering: by zone order in SPECIES, then rarity tier, then name
        rarity_order = {"part": 0, "common": 1, "uncommon": 2, "rare": 3, "epic": 4, "legendary": 5}
        zone_order = {zk: i for i, zk in enumerate(SPECIES.keys())}
    
        entries.sort(
            key=lambda d: (
                zone_order.get(d["zone_key"], 999),
                rarity_order.get(d["rarity"], 999),
                d["species"].lower()
            )
        )
    
        view = CaughtFishView(self, ctx.author.id, entries)
        await ctx.reply(embed=view._embed(), view=view)


    @commands.hybrid_command(name="fish")
    async def fish_root(self, ctx: commands.Context):
        """
        Open the Fishing menu with buttons:
        🎣 Fish • 💰 Sell • 🗺️ Zone • 🛒 Shop • 🔧 Repair
        """
        async with self._lock_for(ctx.author.id):
            data = await self.config.user(ctx.author).all()
            rod = RODS.get(data["rod"], RODS["twig"])
            zone = ZONES.get(data["zone"], ZONES["pond"])
            inv = dict(data["inventory"])
            bait_inv = data["bait"]

            quest_cog = self.bot.get_cog("FantasyJobBoard")
            if quest_cog:
                await quest_cog.record_progress(
                    member=ctx.author,
                    game="Fishing",
                    objective="open_menu",
                    amount=1,
                )

            emb = _inventory_embed(rod=rod, zone=zone, inv=inv, bait_inv=bait_inv, dur=data["rod_durability"])
            await ctx.reply(embed=emb, view=MainMenu(self, ctx.author.id))

    async def _ensure_fishdex(self, user) -> Dict[str, List[str]]:
        data = await self.config.user(user).all()
        fishdex = data.get("fishdex")
        if not isinstance(fishdex, dict):
            fishdex = {zone: [] for zone in SPECIES.keys()}
            await self.config.user(user).fishdex.set(fishdex)
        else:
            # Backfill any new zones that might be added later
            changed = False
            for zone in SPECIES.keys():
                if zone not in fishdex:
                    fishdex[zone] = []
                    changed = True
            if changed:
                await self.config.user(user).fishdex.set(fishdex)
        return fishdex

    @commands.hybrid_command(name="fish_addspecies")
    @commands.admin_or_permissions(administrator=True)
    async def fish_addspecies(self, ctx: commands.Context, zone_key: str, rarity: str, *, species_and_img: str):
        """
        Admin: Add a new fish species to a given zone/rarity, with optional image URL (persisted).
        Usage (prefix):
          [p]fish_addspecies river epic Runeblade Pike
          [p]fish_addspecies river epic "Runeblade Pike" https://example.com/pike.png
          [p]fish_addspecies river epic Runeblade Pike | https://example.com/pike.png
          [p]fish_addspecies river epic Runeblade Pike ; https://example.com/pike.png

        Usage (slash):
          /fish_addspecies zone_key:river rarity:epic species_and_img:"Runeblade Pike https://example.com/pike.png"
          (You can also use a pipe: "Runeblade Pike | https://example.com/pike.png")
        """
        zone_key = zone_key.lower().strip()
        rarity = rarity.lower().strip()

        if zone_key not in SPECIES:
            return await ctx.reply(f"Unknown zone key. Valid: {', '.join(SPECIES.keys())}")
        if rarity not in ("part", "common", "uncommon", "rare", "epic", "legendary"):
            return await ctx.reply("Rarity must be one of: common, uncommon, rare, epic, legendary.")

        text = species_and_img.strip()
        img_url = None
        species_name = None

        # Accept separators like "|" or ";" for clarity
        for sep in ("|", "||", ";"):
            if sep in text:
                name_part, url_part = text.split(sep, 1)
                species_name = name_part.strip()
                candidate = url_part.strip().strip("<>")  # allow <https://...>
                if candidate.lower().startswith(("http://", "https://")):
                    img_url = candidate
                break

        # If no explicit separator, treat a trailing URL as the image
        if species_name is None:
            parts = text.split()
            if parts and parts[-1].lower().startswith(("http://", "https://")):
                img_url = parts[-1].strip("<>")
                species_name = " ".join(parts[:-1]).strip()
            else:
                species_name = text

        if not species_name:
            return await ctx.reply("Please provide a species name (and optional image URL).")

        # ---- Update in-memory SPECIES table (for immediate use) ----
        existing = SPECIES[zone_key].setdefault(rarity, [])
        already_present = species_name in existing
        if not already_present:
            existing.append(species_name)

        # ---- Persist species override ----
        overrides = await self.config.species_overrides()
        zmap = overrides.get(zone_key) or {}
        rlist = zmap.get(rarity) or []
        if species_name not in rlist:
            rlist.append(species_name)
            zmap[rarity] = rlist
            overrides[zone_key] = zmap
            await self.config.species_overrides.set(overrides)

        # ---- Optional: store/update image (in memory + persistent) ----
        if img_url:
            if len(img_url) > 512 or not img_url.lower().startswith(("http://", "https://")):
                return await ctx.reply("Image URL looks invalid. Please provide a valid http(s) URL.")
            FISH_IMAGES_BY_SPECIES[species_name] = img_url

            images = await self.config.species_images()
            images[species_name] = img_url
            await self.config.species_images.set(images)

        zone_name = ZONES[zone_key].name
        if already_present and img_url:
            await ctx.reply(f"🔁 **{species_name}** already existed in **{zone_name}** ({rarity}). Image saved/updated.")
        elif already_present:
            await ctx.reply(f"ℹ️ **{species_name}** already exists in **{zone_name}** ({rarity}). Saved to overrides.")
        elif img_url:
            await ctx.reply(f"✅ Added **{species_name}** to **{zone_name}** as **{rarity.title()}**, with image (persisted).")
        else:
            await ctx.reply(f"✅ Added **{species_name}** to **{zone_name}** as **{rarity.title()}** (persisted).")

    @commands.hybrid_command(name="fish_removespecies")
    @commands.admin_or_permissions(administrator=True)
    async def fish_removespecies(self, ctx: commands.Context, zone_key: str, rarity: str, *, species_name: str):
        """
        Admin: Remove a species from overrides and purge it from every user's Fishdex.
        This does NOT delete built-in species; only those added via overrides.
        
        Usage:
          [p]fish_removespecies river epic Runeblade Pike
          /fish_removespecies zone_key:river rarity:epic species_name:"Runeblade Pike"
        """
        zone_key = zone_key.lower().strip()
        rarity = rarity.lower().strip()
        species_name = species_name.strip()
    
        # Validate
        if zone_key not in SPECIES:
            return await ctx.reply(f"Unknown zone key. Valid: {', '.join(SPECIES.keys())}")
        if rarity not in ("part","common", "uncommon", "rare", "epic", "legendary"):
            return await ctx.reply("Rarity must be one of: common, uncommon, rare, epic, legendary.")
    
        # --- Remove from persistent overrides ---
        overrides = await self.config.species_overrides()
        zmap = overrides.get(zone_key) or {}
        rlist = list(zmap.get(rarity) or [])
    
        override_removed = False
        if species_name in rlist:
            rlist = [s for s in rlist if s != species_name]
            override_removed = True
            if rlist:
                zmap[rarity] = rlist
            else:
                zmap.pop(rarity, None)
    
            if zmap:
                overrides[zone_key] = zmap
            else:
                overrides.pop(zone_key, None)
    
            await self.config.species_overrides.set(overrides)
    
        # --- Update in-memory SPECIES immediately if this was override-only ---
        base_list = BASE_SPECIES_SNAPSHOT.get(zone_key, {}).get(rarity, [])
        if species_name not in base_list:
            current_list = SPECIES[zone_key].get(rarity, [])
            if species_name in current_list:
                SPECIES[zone_key][rarity] = [s for s in current_list if s != species_name]
    
        # --- Purge from all users' Fishdex ---
        users = await self.config.all_users()
        purged_users = 0
        for uid_str, udata in users.items():
            fishdex = udata.get("fishdex")
            if not isinstance(fishdex, dict):
                continue
            if zone_key not in fishdex:
                continue
            zlist = list(fishdex.get(zone_key) or [])
            if species_name in zlist:
                zlist = [s for s in zlist if s != species_name]
                fishdex[zone_key] = zlist
                await self.config.user_from_id(int(uid_str)).fishdex.set(fishdex)
                purged_users += 1
    
        # --- Reply summary ---
        if override_removed:
            await ctx.reply(f"🗑️ Removed **{species_name}** from overrides in **{ZONES[zone_key].name}** ({rarity}). "
                            f"Purged from **{purged_users}** Fishdex(es).")
        else:
            await ctx.reply(f"ℹ️ **{species_name}** was not in overrides for **{ZONES[zone_key].name}** ({rarity}). "
                            f"Still purged from **{purged_users}** Fishdex(es).")


class CaughtFishView(ui.View):
    def __init__(self, cog: "Fishing", user_id: int, entries: List[Dict[str, str]], start: int = 0):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.entries = entries
        self.index = max(0, min(start, len(entries) - 1)) if entries else 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.user_id

    def _embed(self) -> discord.Embed:
        if not self.entries:
            return discord.Embed(
                title="🎣 Caught Fish",
                description="You have not caught any fish yet.",
                colour=discord.Colour.light_grey(),
            )

        item = self.entries[self.index]
        species = item["species"]
        zone_key = item["zone_key"]
        rarity = item["rarity"]

        zone = ZONES.get(zone_key)
        zone_name = zone.name if zone else zone_key

        e = discord.Embed(
            title=f"🐟 {species}",
            description=f"Rarity: **{rarity.title()}**\nCaught in: **{zone_name}**",
            colour=RARITY_COLOR.get(rarity, discord.Colour.blurple()),
        )

        # Show best image we can
        img = _fish_image_for(zone_key, species, rarity)
        if img:
            e.set_image(url=img)

        # Helpful pricing info
        base = float(RARITY_PRICES.get(rarity, 0.0))
        if zone:
            e.add_field(name="Sell Value (here)", value=f"{base * zone.sell_multiplier:.2f} WC", inline=True)
            e.add_field(name="Zone Multiplier", value=f"×{zone.sell_multiplier:.2f}", inline=True)
        else:
            e.add_field(name="Base Sell Value", value=f"{base:.2f} WC", inline=True)

        e.set_footer(text=f"{self.index+1}/{len(self.entries)} • Use buttons to browse")
        return e

    @ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.entries:
            return await interaction.response.edit_message(embed=self._embed(), view=self)
        self.index = (self.index - 1) % len(self.entries)
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.entries:
            return await interaction.response.edit_message(embed=self._embed(), view=self)
        self.index = (self.index + 1) % len(self.entries)
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Closed.", embed=None, view=None)




async def setup(bot: Red):
    await bot.add_cog(Fishing(bot))
