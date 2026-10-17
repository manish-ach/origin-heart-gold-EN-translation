"""Official base stats and types to compare Origin HeartGold's species with (the site's
"Base stat changes" and "Type changes" pages and the Total note on each Pokémon page).

`site/src/data/official_species.json` holds the official values ("the current official games")
for every species or form whose stats or types in the hack differ from them. The site computes
the change pages from it and from species.json at build time, so the tables can't drift from the
game data. Normal site builds read only that JSON: no ROM or game text is bundled.

Generation I-IV species and the HeartGold forms come from the user's untouched US HeartGold ROM
plus the official changes made since (LATER_CHANGES, FAIRY). Refresh or check that part with

    python3 work/tools/site/species_comparisons.py --check-us-rom  "work/rom/Pokemon - HeartGold Version (USA).nds"
    python3 work/tools/site/species_comparisons.py --import-us-rom "work/rom/Pokemon - HeartGold Version (USA).nds"

Entries for later species and forms are curated by hand (`"source": "official"`); a custom form
of the hack is compared with its ordinary species (`"comparedWith": "<slug>"`).
"""
import argparse
import json
from pathlib import Path
import sys
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OFFICIAL = REPO / 'site' / 'src' / 'data' / 'official_species.json'
SPECIES = REPO / 'site' / 'src' / 'data' / 'species.json'
STATS = ['HP', 'Attack', 'Defense', 'Sp. Atk', 'Sp. Def', 'Speed']
TYPES = ['Normal', 'Fighting', 'Flying', 'Poison', 'Ground', 'Rock', 'Bug', 'Ghost', 'Steel', '???',
         'Fire', 'Water', 'Grass', 'Electric', 'Psychic', 'Ice', 'Dragon', 'Dark']

# Official base stat changes since HeartGold for Generation I-IV species: slug -> (generation, {stat: new value}).
LATER_CHANGES = {
    'butterfree': (6, {'Sp. Atk': 90}), 'beedrill': (6, {'Attack': 90}), 'pidgeot': (6, {'Speed': 101}),
    'pikachu': (6, {'Defense': 40, 'Sp. Def': 50}), 'raichu': (6, {'Speed': 110}),
    'nidoqueen': (6, {'Attack': 92}), 'nidoking': (6, {'Attack': 102}), 'clefable': (6, {'Sp. Atk': 95}),
    'wigglytuff': (6, {'Sp. Atk': 85}), 'vileplume': (6, {'Sp. Atk': 110}), 'poliwrath': (6, {'Attack': 95}),
    'alakazam': (6, {'Sp. Def': 95}), 'victreebel': (6, {'Sp. Def': 70}), 'golem': (6, {'Attack': 120}),
    'ampharos': (6, {'Defense': 85}), 'bellossom': (6, {'Defense': 95}), 'azumarill': (6, {'Sp. Atk': 60}),
    'jumpluff': (6, {'Sp. Def': 95}), 'beautifly': (6, {'Sp. Atk': 100}), 'exploud': (6, {'Sp. Def': 73}),
    'staraptor': (6, {'Sp. Def': 60}), 'roserade': (6, {'Defense': 65}),
    'arbok': (7, {'Attack': 95}), 'dugtrio': (7, {'Attack': 100}), 'farfetchd': (7, {'Attack': 90}),
    'dodrio': (7, {'Speed': 110}), 'electrode': (7, {'Speed': 150}), 'exeggutor': (7, {'Sp. Def': 75}),
    'noctowl': (7, {'Sp. Atk': 86}), 'ariados': (7, {'Sp. Def': 70}), 'qwilfish': (7, {'Defense': 85}),
    'magcargo': (7, {'HP': 60, 'Sp. Atk': 90}), 'corsola': (7, {'HP': 65, 'Defense': 95, 'Sp. Def': 95}),
    'mantine': (7, {'HP': 85}), 'swellow': (7, {'Sp. Atk': 75}), 'pelipper': (7, {'Sp. Atk': 95}),
    'masquerain': (7, {'Sp. Atk': 100, 'Speed': 80}), 'delcatty': (7, {'Speed': 90}),
    'volbeat': (7, {'Defense': 75, 'Sp. Def': 85}), 'illumise': (7, {'Defense': 75, 'Sp. Def': 85}),
    'lunatone': (7, {'HP': 90}), 'solrock': (7, {'HP': 90}),
    'chimecho': (7, {'HP': 75, 'Defense': 80, 'Sp. Def': 90}),
    'cresselia': (9, {'Defense': 110, 'Sp. Def': 120}),
}
# Generation VI retyped these to Fairy; Generation V gave the Rotom appliance forms their second type.
FAIRY = {
    'clefairy': ['Fairy'], 'clefable': ['Fairy'], 'cleffa': ['Fairy'], 'togepi': ['Fairy'],
    'togetic': ['Fairy', 'Flying'], 'togekiss': ['Fairy', 'Flying'], 'snubbull': ['Fairy'], 'granbull': ['Fairy'],
    'jigglypuff': ['Normal', 'Fairy'], 'wigglytuff': ['Normal', 'Fairy'], 'igglybuff': ['Normal', 'Fairy'],
    'azurill': ['Normal', 'Fairy'], 'marill': ['Water', 'Fairy'], 'azumarill': ['Water', 'Fairy'],
    'mr-mime': ['Psychic', 'Fairy'], 'mime-jr': ['Psychic', 'Fairy'], 'ralts': ['Psychic', 'Fairy'],
    'kirlia': ['Psychic', 'Fairy'], 'gardevoir': ['Psychic', 'Fairy'], 'mawile': ['Steel', 'Fairy'],
    'heat-rotom': ['Electric', 'Fire'], 'wash-rotom': ['Electric', 'Water'], 'frost-rotom': ['Electric', 'Ice'],
    'fan-rotom': ['Electric', 'Flying'], 'mow-rotom': ['Electric', 'Grass'],
}
# HeartGold's personal records after #493: record index -> the hack's slug for that form.
US_FORMS = {496: 'deoxys-attack-forme', 497: 'deoxys-defense-forme', 498: 'deoxys-speed-forme',
            499: 'wormadam-sandy-cloak', 500: 'wormadam-trash-cloak', 501: 'giratina-origin-forme',
            502: 'shaymin-sky-forme', 503: 'heat-rotom', 504: 'wash-rotom', 505: 'frost-rotom',
            506: 'fan-rotom', 507: 'mow-rotom'}
ROM_SOURCE = 'Pokémon HeartGold (USA) ROM'


def parse_personal(raw):
    """HeartGold personal record: stats in HP/Atk/Def/Spe/SpA/SpD order, then two type bytes."""
    if len(raw) < 8:
        raise ValueError('personal record too short')
    hp, at, df, sp, sa, sd = raw[0:6]
    types = [TYPES[raw[6]], TYPES[raw[7]]]
    return [hp, at, df, sa, sd, sp], types[:1] if types[0] == types[1] else types


def official_from_rom(slug, stats, types):
    """Apply the official changes since HeartGold. Returns (stats, types, source)."""
    stats, source = list(stats), ROM_SOURCE
    if slug in LATER_CHANGES:
        gen, changes = LATER_CHANGES[slug]
        for name, value in changes.items():
            stats[STATS.index(name)] = value
        source += ', Generation %s base stat change' % {6: 'VI', 7: 'VII', 9: 'IX'}[gen]
    if slug in FAIRY:
        types = FAIRY[slug]
        source += ', Generation %s typing' % ('V' if slug.endswith('rotom') else 'VI')
    return stats, types, source


def differs(entry, hack):
    return entry['stats'] != hack['stats'] or sorted(entry['types']) != sorted(hack['types'])


def rom_entries(rom_path, species):
    import ndspy.narc
    import ndspy.rom
    raw = Path(rom_path).read_bytes()
    if zlib.crc32(raw) != 0xC180A0E9:
        raise ValueError('expected untouched Pokémon HeartGold (USA), CRC32 C180A0E9')
    narc = ndspy.narc.NARC(ndspy.rom.NintendoDSRom(raw).getFileByName('a/0/0/2'))
    by_id = {s['id']: s for s in species if s['formId'] == 0}
    by_slug = {s['slug']: s for s in species}
    wanted = [(i, by_id[i]['slug']) for i in range(1, 494)] + sorted(US_FORMS.items())
    out = {}
    for index, slug in wanted:
        stats, types, source = official_from_rom(slug, *parse_personal(narc.files[index]))
        entry = dict(stats=stats, types=types, source=source)
        if differs(entry, by_slug[slug]):
            out[slug] = entry
    return out


def dump(data):
    """One species per line, so diffs stay readable."""
    rows = [' %s: %s,' % (json.dumps(k), json.dumps(data[k], ensure_ascii=False)) for k in data if k != 'species']
    items = ['  %s: %s' % (json.dumps(k), json.dumps(v, ensure_ascii=False)) for k, v in data['species'].items()]
    return '{\n%s\n "species": {\n%s\n }\n}\n' % ('\n'.join(rows), ',\n'.join(items))


def load():
    return (json.loads(OFFICIAL.read_text(encoding='utf-8')),
            json.loads(SPECIES.read_text(encoding='utf-8')))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check-us-rom', metavar='ROM', help='compare the ROM-based entries with the ROM')
    group.add_argument('--import-us-rom', metavar='ROM', help='rewrite the ROM-based entries from the ROM')
    a = ap.parse_args(argv)
    data, species = load()
    fresh = rom_entries(a.check_us_rom or a.import_us_rom, species)
    current = {k: v for k, v in data['species'].items() if v.get('source', '').startswith(ROM_SOURCE)}
    if a.check_us_rom:
        bad = sorted(k for k in set(fresh) | set(current) if fresh.get(k) != current.get(k))
        for k in bad:
            print('%-24s file %s\n%-24s rom  %s' % (k, current.get(k), '', fresh.get(k)))
        print('%d ROM-based entries, %d differ' % (len(fresh), len(bad)))
        return 1 if bad else 0
    rest = {k: v for k, v in data['species'].items() if k not in current}
    order = {s['slug']: n for n, s in enumerate(species)}
    data['species'] = dict(sorted({**rest, **fresh}.items(), key=lambda kv: order[kv[0]]))
    tmp = OFFICIAL.with_suffix('.tmp')
    tmp.write_text(dump(data), encoding='utf-8')
    tmp.replace(OFFICIAL)
    print('wrote %s: %d ROM-based, %d curated entries' % (OFFICIAL.relative_to(REPO), len(fresh), len(rest)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
