#!/usr/bin/env python3
"""fill_names - pilot: fill the name banks of the workspace from the glossary.

    python3 work/tools/fill_names.py [--ws work/translate/banks] [--force] [--dry-run]

Banks (v4 numbering, found by matching bank content against work/glossary/*.json):
    a027/0232 species (1439: national dex 1-1025, then form entries carrying the base name)
    a027/0739 moves (index = move id)          a027/0711 abilities (index = ability id, customs after 310)
    a027/0219 items (index = Gen 4 item index for <= 536, hack additions after)
    a027/0724 types (Gen 4 order with Fairy in the ??? slot 9)
    a027/0033 natures (Gen 4 order)

Resolution per string, first hit wins (origin field in the workspace):
    glossary       zh is a key of the category's glossary file (hack renames/custom names included)
    pokeapi-name   zh equals an official zh-Hans / zh-Hant(->Hans) PokéAPI name (work/glossary/src)
    rule           TM/HM/Data Card numbering, placeholders (？？？ -> ???)
    pokeapi-index  bank index -> official id, accepted only when the nearest name-matched neighbours on
                   both sides sit at their official index (local alignment check); the note records the
                   official zh name so a reviewer can spot repurposed slots
English longer than the QA limit is shortened with the glossary README abbreviations
(manual_overrides.ABBREV) or, failing that, LOCAL_ABBREV below (origin gets "+abbrev").
Everything is written with status "draft". Existing en values are never overwritten without --force
(entries with origin "copy" are treated as empty).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
GDIR = WORK / "glossary"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(GDIR))

import textmetrics as tm  # noqa: E402
import ws as wsmod  # noqa: E402

EN, HANS, HANT = "9", "12", "4"
FW = str.maketrans("０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ　：（）",
                   "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz :()")

BANKS = {  # narc/bank -> (category, csv, id column)
    ("a027", 232): ("species", "pokemon_species_names", "pokemon_species_id"),
    ("a027", 739): ("moves", "move_names", "move_id"),
    ("a027", 711): ("abilities", "ability_names", "ability_id"),
    ("a027", 219): ("items", "item_names", "item_id"),
    ("a027", 724): ("types", "type_names", "type_id"),
    ("a027", 33): ("natures", "nature_names", "nature_id"),
}

TYPE_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 18, 10, 11, 12, 13, 14, 15, 16, 17]   # bank index -> type id
NATURES = ["Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish", "Lax",
           "Timid", "Hasty", "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash",
           "Calm", "Gentle", "Sassy", "Careful", "Quirky"]

# Abbreviations for names over the limit that the glossary README does not cover yet.
# Style: Gen 4/5 in-game truncations (drop vowels / join words), kept readable.
LOCAL_ABBREV = {
    "Blacephalon": "Blacephaln",
    "Brute Bonnet": "BruteBonnt",
    "Corviknight": "Corvknight",
    "Corvisquire": "Corvsquire",
    "Fezandipiti": "Fezndipiti",
    "Flutter Mane": "FluttrMane",
    "Gouging Fire": "GougngFire",
    "Iron Boulder": "IronBouldr",
    "Iron Bundle": "IronBundle",
    "Iron Jugulis": "IronJuguls",
    "Iron Leaves": "IronLeaves",
    "Iron Thorns": "IronThorns",
    "Iron Treads": "IronTreads",
    "Iron Valiant": "IronValint",
    "Kilowattrel": "Kilowattrl",
    "Meowscarada": "Meowscrada",
    "Polteageist": "Poltegeist",
    "Raging Bolt": "RagingBolt",
    "Roaring Moon": "RoarngMoon",
    "Sandy Shocks": "SandyShcks",
    "Scream Tail": "ScreamTail",
    "Slither Wing": "SlithrWing",
    "Squawkabilly": "Squawkably",
    "Stonjourner": "Stonjournr",
    "Walking Wake": "WalkngWake",
    "10,000,000 Volt Thunderbolt": "10MVoltTBolt",
    "Acid Downpour": "AcidDownpour",
    "All-Out Pummeling": "AllOutPummel",
    "Alluring Voice": "AllurngVoice",
    "Aromatic Mist": "AromaticMist",
    "Astral Barrage": "AstrlBarrage",
    "Baneful Bunker": "BanefulBunkr",
    "Behemoth Bash": "BehemothBash",
    "Behemoth Blade": "BehemthBlade",
    "Bitter Malice": "BitterMalice",
    "Black Hole Eclipse": "BlkHoleEclps",
    "Blazing Torque": "BlazngTorque",
    "Bleakwind Storm": "BleakwndStrm",
    "Bouncy Bubble": "BouncyBubble",
    "Breaking Swipe": "BreakngSwipe",
    "Breakneck Blitz": "BrkneckBlitz",
    "Burning Bulwark": "BurnBulwark",
    "Burning Jealousy": "BurnJealousy",
    "Chilling Water": "ChillngWater",
    "Chilly Reception": "ChillyRecptn",
    "Clanging Scales": "ClangngScles",
    "Clangorous Soul": "ClangrusSoul",
    "Clangorous Soulblaze": "ClangSoulblz",
    "Collision Course": "CollisionCrs",
    "Combat Torque": "CombatTorque",
    "Continental Crush": "ContnntlCrsh",
    "Core Enforcer": "CoreEnforcer",
    "Corkscrew Crash": "CorkscrwCrsh",
    "Corrosive Gas": "CorrosiveGas",
    "Crafty Shield": "CraftyShield",
    "Darkest Lariat": "DarkstLariat",
    "Devastating Drake": "DevstatDrake",
    "Diamond Storm": "DiamondStorm",
    "Disarming Voice": "DisarmngVoic",
    "Double Iron Bash": "DblIronBash",
    "Dragon Ascent": "DragonAscent",
    "Dragon Energy": "DragonEnergy",
    "Dragon Hammer": "DragonHammer",
    "Dynamax Cannon": "DynamxCannon",
    "Electro Drift": "ElectroDrift",
    "Extreme Evoboost": "ExtrmEvboost",
    "False Surrender": "FalseSurrndr",
    "First Impression": "FirstImpresn",
    "Fishious Rend": "FishiousRend",
    "Floral Healing": "FloralHealng",
    "Flower Shield": "FlowerShield",
    "Forest’s Curse": "ForestsCurse",
    "Freezing Glare": "FreezngGlare",
    "Genesis Supernova": "GenesisNova",
    "Gigaton Hammer": "GigatonHammr",
    "Gigavolt Havoc": "GigavoltHavc",
    "Glacial Lance": "GlacialLance",
    "Guardian of Alola": "GuardnAlola",
    "Headlong Rush": "HeadlongRush",
    "Hyperspace Fury": "HyprspceFury",
    "Hyperspace Hole": "HyprspceHole",
    "Infernal Parade": "InfrnlParade",
    "Inferno Overdrive": "InfernoOvrdv",
    "Jungle Healing": "JungleHealng",
    "King’s Shield": "KingsShield",
    "Last Respects": "LastRespects",
    "Let’s Snuggle Forever": "SnuggleForvr",
    "Light That Burns the Sky": "LightBurnSky",
    "Light of Ruin": "LightOfRuin",
    "Lunar Blessing": "LunarBlessng",
    "Magical Torque": "MagiclTorque",
    "Magnetic Flux": "MagneticFlux",
    "Malicious Moonsault": "MalicMoonslt",
    "Malignant Chain": "MalignantChn",
    "Matcha Gotcha": "MatchaGotcha",
    "Max Airstream": "MaxAirstream",
    "Max Flutterby": "MaxFlutterby",
    "Max Hailstorm": "MaxHailstorm",
    "Max Lightning": "MaxLightning",
    "Max Mindstorm": "MaxMindstorm",
    "Max Overgrowth": "MaxOvergrwth",
    "Max Steelspike": "MaxSteelspke",
    "Menacing Moonraze Maelstrom": "MoonrazeMlst",
    "Meteor Assault": "MeteorAssalt",
    "Mighty Cleave": "MightyCleave",
    "Misty Explosion": "MistyExplosn",
    "Moongeist Beam": "MoongestBeam",
    "Mountain Gale": "MountainGale",
    "Mystical Power": "MysticalPowr",
    "Nature’s Madness": "NaturMadness",
    "Never-Ending Nightmare": "NvrEndNghtmr",
    "Noxious Torque": "NoxiousTorqu",
    "Oblivion Wing": "OblivionWing",
    "Oceanic Operetta": "OceanicOprta",
    "Petal Blizzard": "PetalBlizzrd",
    "Phantom Force": "PhantomForce",
    "Photon Geyser": "PhotonGeyser",
    "Population Bomb": "PopulatnBomb",
    "Precipice Blades": "PrcipceBlade",
    "Prismatic Laser": "PrismtcLaser",
    "Psychic Noise": "PsychicNoise",
    "Psyshield Bash": "PsyshieldBsh",
    "Pulverizing Pancake": "PulvrzPancke",
    "Revelation Dance": "RevelatnDnce",
    "Revival Blessing": "RevivlBlessg",
    "Rising Voltage": "RisngVoltage",
    "Sandsear Storm": "SandsearStrm",
    "Savage Spin-Out": "SavageSpnOut",
    "Searing Sunraze Smash": "SunrazeSmash",
    "Shattered Psyche": "ShattrdPsych",
    "Shell Side Arm": "ShellSideArm",
    "Sinister Arrow Raid": "SinArrowRaid",
    "Skitter Smack": "SkitterSmack",
    "Soul-Stealing 7-Star Strike": "7StarStrike",
    "Sparkling Aria": "SparklngAria",
    "Sparkly Swirl": "SparklySwirl",
    "Spectral Thief": "SpectrlThief",
    "Spicy Extract": "SpicyExtract",
    "Spirit Shackle": "SpiritShackl",
    "Splintered Stormshards": "Stormshards",
    "Splishy Splash": "SplishySplsh",
    "Springtide Storm": "SprngtdStorm",
    "Steam Eruption": "SteamEruptn",
    "Stoked Sparksurfer": "Sparksurfer",
    "Stomping Tantrum": "StompngTntrm",
    "Strange Steam": "StrangeSteam",
    "Subzero Slammer": "SubzeroSlmmr",
    "Sunsteel Strike": "SunsteelStrk",
    "Supercell Slam": "SupercellSlm",
    "Supersonic Skystrike": "SonicSkystrk",
    "Surging Strikes": "SurgngStrkes",
    "Tachyon Cutter": "TachyonCuttr",
    "Tectonic Rage": "TectonicRage",
    "Tera Starstorm": "TeraStarstrm",
    "Thousand Arrows": "ThousndArrws",
    "Thousand Waves": "ThousndWaves",
    "Thunderous Kick": "ThundrusKick",
    "Trick-or-Treat": "TrickOrTreat",
    "Triple Arrows": "TripleArrows",
    "Twinkle Tackle": "TwinklTackle",
    "Veevee Volley": "VeeveeVolley",
    "Victory Dance": "VictoryDance",
    "Water Shuriken": "WatrShuriken",
    "Wicked Torque": "WickedTorque",
    "Wildbolt Storm": "WildboltStrm",
    "Beads of Ruin": "BeadsOfRuin",
    "Chilling Neigh": "ChillngNeigh",
    "Curious Medicine": "CuriousMedcn",
    "Dauntless Shield": "DauntlssShld",
    "Electromorphosis": "Electromorph",
    "Full Metal Body": "FullMetalBdy",
    "Hadron Engine": "HadronEngine",
    "Hunger Switch": "HungerSwitch",
    "Intrepid Sword": "IntrepidSwrd",
    "Lingering Aroma": "LingerngArma",
    "Mycelium Might": "MyceliumMght",
    "Orichalcum Pulse": "OrichlcmPlse",
    "Poison Puppeteer": "PoisnPuppetr",
    "Power Construct": "PowrConstrct",
    "Power of Alchemy": "PowrOfAlchmy",
    "Protosynthesis": "Protosynthss",
    "Purifying Salt": "PurifyngSalt",
    "Screen Cleaner": "ScreenCleanr",
    "Shadow Shield": "ShadowShield",
    "Supersweet Syrup": "SuprswtSyrup",
    "Supreme Overlord": "SuprmOverlrd",
    "Sword of Ruin": "SwordOfRuin",
    "Tablets of Ruin": "TabletsRuin",
    "Tangling Hair": "TanglingHair",
    "Teraform Zero": "TeraformZero",
    "Vessel of Ruin": "VesselOfRuin",
    "Wandering Spirit": "WanderngSprt",
    "Well-Baked Body": "WellBakedBdy",
    "Embody Aspect": "EmbodyAspect",
    "Ability Capsule": "AbilityCapsl",
    "Ability Patch": "AbilityPatch",
    "Ability Shield": "AbilityShild",
    "Adamant Crystal": "AdamantCrstl",
    "Adrenaline Orb": "Adrenlin Orb",
    "Auspicious Armor": "AuspcsArmor",
    "Balm Mushroom": "BalmMushroom",
    "Black Augurite": "BlkAugurite",
    "Blunder Policy": "BlundrPolicy",
    "Booster Energy": "BoostrEnergy",
    "Catching Charm": "CatchngCharm",
    "Clever Feather": "CleverFeathr",
    "Cornerstone Mask": "CornrstnMask",
    "Dragon Memory": "DragonMemory",
    "Electric Memory": "ElecMemory",
    "Electric Seed": "ElectricSeed",
    "Exp. Candy XL": "Exp.CandyXL",
    "Exp. Candy XS": "Exp.CandyXS",
    "Fairy Feather": "FairyFeather",
    "Fighting Memory": "FightMemory",
    "Flying Memory": "FlyingMemory",
    "Fossilized Bird": "Fossil Bird",
    "Fossilized Dino": "Fossil Dino",
    "Fossilized Drake": "Fossil Drake",
    "Fossilized Fish": "Fossil Fish",
    "Galarica Cuff": "GalaricaCuff",
    "Galarica Twig": "GalaricaTwig",
    "Galarica Wreath": "GalaricaWrth",
    "Genius Feather": "GeniusFeathr",
    "Gimmighoul Coin": "GimmighlCoin",
    "Gold Bottle Cap": "GoldBottlCap",
    "Griseous Core": "GriseousCore",
    "Ground Memory": "GroundMemory",
    "Health Feather": "HealthFeathr",
    "Hearthflame Mask": "HrthflmeMask",
    "Heavy-Duty Boots": "HvyDutyBoots",
    "Iceroot Carrot": "IcerootCarrt",
    "Leader’s Crest": "LeadersCrest",
    "Luminous Moss": "LuminousMoss",
    "Lumiose Galette": "LumioseGltte",
    "Lustrous Globe": "LustrusGlobe",
    "Malicious Armor": "MalicusArmor",
    "Maranga Berry": "MarangaBerry",
    "Masterpiece Teacup": "MstrpcTeacup",
    "Moomoo Cheese": "MoomooCheese",
    "Muscle Feather": "MuscleFeathr",
    "Pewter Crunchies": "PewtrCrnchys",
    "Poison Memory": "PoisonMemory",
    "Pokémon Box Link": "Box Link",
    "Pretty Feather": "PrettyFeathr",
    "Prison Bottle": "PrisonBottle",
    "Protective Pads": "ProtectvPads",
    "Psychic Memory": "PsychcMemory",
    "Punching Glove": "PunchngGlove",
    "Purple Nectar": "PurpleNectar",
    "Reins of Unity": "ReinsOfUnity",
    "Resist Feather": "ResistFeathr",
    "Rotom Catalog": "RotomCatalog",
    "Rusted Shield": "RustedShield",
    "Safety Goggles": "SafetyGoggls",
    "Scroll of Darkness": "ScrollOfDark",
    "Shaderoot Carrot": "ShadrtCarrot",
    "Shalour Sable": "ShalourSable",
    "Strawberry Sweet": "StrwbrySweet",
    "Swift Feather": "SwiftFeather",
    "Terrain Extender": "TerrainExtdr",
    "Unremarkable Teacup": "UnrmrkTeacup",
    "Utility Umbrella": "UtilUmbrella",
    "Wellspring Mask": "WellsprgMask",
    "Whipped Dream": "WhippedDream",
    "Yellow Nectar": "YellowNectar",
}


# Hack-custom or repurposed slots no source resolves: (narc, bank, id) -> (en, note). origin "agent".
MANUAL = {
    ("a027", 739, 120): ("Selfdestruct", "slot #120 Self-Destruct (Gen 4 spelling); hack zh 玉石俱碎 differs from official 自爆"),
    ("a027", 739, 517): ("Inferno", "slot #517 Inferno; hack zh 烈火深渊 differs from official 炼狱"),
    ("a027", 739, 920): ("Rock Storm", "custom hack move (岩石风暴), literal name"),
    ("a027", 711, 301): ("EmbodyAspect", "Embody Aspect (Speed form); abbreviated"),
    ("a027", 711, 302): ("EmbodyAspect", "Embody Aspect (Attack form); abbreviated"),
    ("a027", 711, 303): ("EmbodyAspect", "Embody Aspect (Sp. Def form); abbreviated"),
    ("a027", 711, 304): ("EmbodyAspect", "Embody Aspect (Defense form); abbreviated"),
    ("a027", 219, 114): ("Steel Armor", "custom hold item for Armored Mewtwo (钢铁铠甲); literal, verify"),
    ("a027", 219, 438): ("Wetsuit", "hack item in the Works Key slot (防水服 = waterproof suit); verify"),
    ("a027", 219, 440): ("Badge Case", "hack item in the Galactic Key slot (装徽章的袋子 = bag for badges); verify"),
    ("a027", 219, 479): ("Spoils", "hack item in the Lost Item slot (战利品 = loot/spoils); verify"),
    ("a027", 219, 599): ("Snowball", "雪丸 = Snowball (official zh 雪球)"),
    ("a027", 219, 744): ("Chain Logger", "custom hack item (连锁记录仪 = chain recorder); verify function"),
    ("a027", 219, 745): ("EV Allocator", "custom hack item (能力分配器 = stat distributor); verify function"),
    ("a027", 219, 761): ("Ninja Scroll", "custom hack item (忍者卷轴)"),
}

ALIAS_RE = re.compile(r"^(.*?)[（(](?:已|预计)?(?:改名|改为|为)?(.+?)[）)]$")


def glossary_index(g: dict) -> dict:
    """zh -> entry, adding the renamed/alias form of keys like 'A（改名B）' or 'A(B）' under B."""
    out = dict(g)
    for k, v in g.items():
        mm = ALIAS_RE.match(k)
        if mm and not re.match(r"形态|[0-9０-９]", mm.group(2)):
            out.setdefault(mm.group(2).strip(), v)
            out.setdefault(mm.group(1).strip(), v)
    return out


def read_csv(name):
    with open(GDIR / "src" / (name + ".csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def learn_t2s():
    try:
        import build_glossary as bg  # type: ignore
        return bg.learn_t2s()
    except Exception:
        return {}


def names(csvname, idcol, t2s):
    en, zh = {}, {}
    zh_by_id = {}
    for r in read_csv(csvname):
        i, lang, n = int(r[idcol]), r["local_language_id"], (r["name"] or "").strip()
        if not n:
            continue
        if lang == EN:
            en[i] = n
        elif lang == HANS:
            zh.setdefault(n.translate(FW), i)
            zh_by_id.setdefault(i, n)
        elif lang == HANT:
            s = "".join(t2s.get(c, c) for c in n)
            zh.setdefault(s.translate(FW), i)
            zh.setdefault(n.translate(FW), i)
            zh_by_id.setdefault(i, s)
    return en, zh, zh_by_id


def gen4_items():
    m = {}
    for r in read_csv("item_game_indices"):
        if r["generation_id"] == "4":
            m.setdefault(int(r["game_index"]), int(r["item_id"]))
    return m


def rules(zh: str, cat: str):
    z = zh.translate(FW).strip()
    if re.fullmatch(r"[?？]+", z):
        return "???"
    if cat == "items":
        mm = re.fullmatch(r"(技能机|招式学习器)(\d+)", z)
        if mm:
            return "TM%02d" % int(mm.group(2))
        mm = re.fullmatch(r"(秘传机|秘传学习器)(\d+)", z)
        if mm:
            return "HM%02d" % int(mm.group(2))
        mm = re.fullmatch(r"资料卡(\d+)", z)
        if mm:
            return "Data Card %02d" % int(mm.group(1))
        if z in ("无", "无 "):
            return "None"
    return None


def shorten(en: str, limit: int, abbrev: dict):
    if len(en) <= limit:
        return en, False
    for table in (abbrev, LOCAL_ABBREV):
        v = table.get(en)
        if v:
            v = re.sub(r"\s*\(.*\)$", "", v)
            if len(v) <= limit:
                return v, True
    return en, False


def fix_quotes(en: str) -> str:
    return en.replace("'", "’")


def resolve_bank(bank: dict, cat: str, csvname: str, idcol: str, gloss: dict, abbrev: dict, t2s, limit: int):
    en_by_id, zh2id, zh_by_id = names(csvname, idcol, t2s)
    idmap = (lambda i: gen4_items().get(i)) if cat == "items" else (lambda i: i)
    if cat == "types":
        idmap = lambda i: TYPE_ORDER[i] if i < len(TYPE_ORDER) else None   # noqa: E731
    g = glossary_index(gloss.get(cat, {}))
    contained = sorted(((n, i) for n, i in zh2id.items() if len(n) >= 3), key=lambda x: -len(x[0]))
    res = {}
    anchors = {}   # index -> official id from name matches
    for e in bank["strings"]:
        zh = e["zh"]
        z = zh.translate(FW).strip()
        if cat == "natures" and e["id"] < len(NATURES):
            res[e["id"]] = (NATURES[e["id"]], "index", "Gen 4 nature order")
            continue
        if z in g and g[z].get("en"):
            res[e["id"]] = (g[z]["en"], "glossary", "")
            if g[z].get("id") is not None:
                anchors[e["id"]] = g[z]["id"]
            continue
        if z in zh2id:
            pid = zh2id[z]
            if pid in en_by_id:
                res[e["id"]] = (en_by_id[pid], "pokeapi-name", "")
                anchors[e["id"]] = pid
                continue
        r = rules(zh, cat)
        if r:
            res[e["id"]] = (r, "rule", "")
            continue
        if cat == "moves":   # Z-moves: '<species>Ｚ<official Z-move name>'
            for n, pid in contained:
                if n in z and z != n and pid in en_by_id:
                    res[e["id"]] = (en_by_id[pid], "pokeapi-name", "hack zh contains official name %s" % n)
                    break
    # index fallback with a local alignment check
    idx_sorted = sorted(anchors)
    import bisect
    for e in bank["strings"]:
        i = e["id"]
        if i in res or not tm.CJK_RE.search(e["zh"]):
            continue
        pid = idmap(i)
        if cat == "types" and pid is not None and pid in en_by_id:
            res[i] = (en_by_id[pid], "index", "Gen 4 type order (Fairy in slot 9); official zh %s" % zh_by_id.get(pid, "?"))
            continue
        if pid is None or pid not in en_by_id:
            continue
        k = bisect.bisect_left(idx_sorted, i)
        left = idx_sorted[k - 1] if k > 0 else None
        right = idx_sorted[k] if k < len(idx_sorted) else None
        ok_l = left is None or idmap(left) == anchors[left]
        ok_r = right is None or idmap(right) == anchors[right]
        oz = zh_by_id.get(pid, "")
        overlap = set(oz.translate(FW)) & set(e["zh"].translate(FW)) - set("0123456789 ")
        if (left is not None or right is not None) and ok_l and ok_r and overlap:
            res[i] = (en_by_id[pid], "pokeapi-index",
                      "by index; official zh-Hans is %s" % zh_by_id.get(pid, "?"))
    # same zh elsewhere in the bank (form entries repeat the base name) -> same English
    by_zh = {}
    for e in bank["strings"]:
        if e["id"] in res and res[e["id"]][1] != "index":
            by_zh.setdefault(e["zh"], res[e["id"]])
    for e in bank["strings"]:
        if e["id"] not in res and e["zh"] in by_zh:
            en, origin, note = by_zh[e["zh"]]
            res[e["id"]] = (en, origin, "same zh as another entry" + ("; " + note if note else ""))
    for e in bank["strings"]:
        k = (bank["narc"], bank["bank"], e["id"])
        if k in MANUAL and e["id"] not in res:
            res[e["id"]] = (MANUAL[k][0], "agent", MANUAL[k][1])
    out = {}
    for i, (en, origin, note) in res.items():
        en = fix_quotes(en)
        short, did = shorten(en, limit, abbrev)
        if did:
            note = (note + "; " if note else "") + "abbreviated from %s" % en
            origin += "+abbrev"
        out[i] = (short, origin, note)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws", default=str(wsmod.DEFAULT_WS))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    gloss = {c: json.loads((GDIR / f"{c}.json").read_text(encoding="utf-8"))
             for c in ("species", "moves", "abilities", "items", "types", "natures")}
    try:
        import manual_overrides as mo  # type: ignore
        abbrev = {fix_quotes(k): fix_quotes(v) for k, v in mo.ABBREV.items()}
    except Exception:
        abbrev = {}
    cfg = tm.load_config()
    t2s = learn_t2s()
    for (narc, bno), (cat, csvname, idcol) in BANKS.items():
        p = wsmod.ws_path(Path(a.ws), narc, bno)
        bank = wsmod.load_json(p)
        limit = cfg["categories"][cat].get("max_chars", 99)
        res = resolve_bank(bank, cat, csvname, idcol, gloss, abbrev, t2s, limit)
        c = Counter()
        for e in bank["strings"]:
            r = res.get(e["id"])
            if not r:
                if tm.CJK_RE.search(e["zh"]) and e.get("en") is None:
                    c["unresolved"] += 1
                continue
            if e.get("en") is not None and e.get("origin") != "copy" and not a.force:
                c["kept"] += 1
                continue
            en, origin, note = r
            e.update({"en": en, "status": "draft", "origin": origin, "notes": note})
            c[origin] += 1
        bank["category"] = cat
        if not a.dry_run:
            wsmod.save_json(p, bank)
        print(f"{narc}/{bno:04d} {cat:9s} {len(bank['strings']):5d} strings: {dict(c)}")


if __name__ == "__main__":
    main()
