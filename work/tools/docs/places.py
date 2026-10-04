"""Player-readable names for maps that share a location name.

The game only names locations (Celadon City), not rooms, and the hack reuses vanilla map
layouts for other purposes (its Pokémon League uses the Radio Tower 3F layout), so the vanilla
map constant alone can't be trusted. A room is named from two signals:

1. a room *type* that the layout keeps whatever the hack does with it (Pokémon Center, Poké Mart,
   Gym, Department Store floor, gatehouse, cave floor), and
2. where its door is in the hack's own maps: a building entered from the town map gets a compass
   position ("north-west house"); an upstairs room is named after the room you reach it from.

A vanilla map name is used when the map's constant belongs to the same location (MAP_CELADON_GAME_CORNER
under Celadon City) and is not one of the vanilla "unused" slots. Anything still ambiguous gets a running
number ("Celadon City, building 2") instead of a map id. Corrections go in work/docs/place_names.json.
"""
import collections
import re
import unicodedata

FLOOR = re.compile(r'^B?\d+F$')
OUTDOOR = ('town', 'route')


def _floor(const):
    for w in const.split('_'):
        if FLOOR.match(w):
            return w
    return None


def _short(area):
    return re.sub(r' (City|Town)$', '', area)


def room_type(const, area):
    """Room kind that survives layout reuse, or None."""
    c = const.upper()
    fl = _floor(c)
    flr = '' if fl in (None, '1F') else ' ' + fl
    if 'POKECENTER' in c:
        return 'Pokémon Center' + flr
    if c.endswith('_MART') or 'POKEMART' in c or c.endswith('_MART_1F'):
        return 'Poké Mart'
    if 'DEPARTMENT_STORE' in c:
        if 'ELEVATOR' in c:
            return 'Department Store elevator'
        return 'Department Store' + (' ' + fl if fl else '') if 'ROOF' not in c else 'Department Store roof'
    if c.endswith('_GYM') or '_GYM_' in c:
        return 'Gym' + flr
    if 'GATEHOUSE' in c or c.endswith('_GATE'):
        return 'gatehouse'
    return None


WORDS = {'POKECENTER': 'Pokémon Center', 'POKEMART': 'Poké Mart', 'MART': 'Poké Mart', 'GYM': 'Gym', 'SS': 'S.S.',
         'POKEMON': 'Pokémon', 'POKE': 'Poké', 'OAKS': "Oak's", 'ELMS': "Elm's", 'BILLS': "Bill's", 'BLUES': "Blue's",
         'MR': 'Mr.', 'MRS': 'Mrs.', 'MT': 'Mt.', 'MOUNT': 'Mt.', 'JP': '', 'INTERIOR': '', 'EXTERIOR': 'outside',
         'FISHING': 'Fishing', 'DUDE': 'Guru’s', 'GUIDE': 'Guide', 'GENT': 'Gent’s', 'CO': 'Co.', 'HQ': 'HQ', 'MOOMOO': 'MooMoo'}
NOISE = re.compile(r'UNUSED|DUMMY|WIFI|_\d+$')
LEAGUE_ROOMS = {'WILL_ROOM': 'Elite Four room 1', 'KOGA_ROOM': 'Elite Four room 2', 'BRUNO_ROOM': 'Elite Four room 3',
                'KAREN_ROOM': 'Elite Four room 4', 'LANCE_ROOM': 'Champion’s room', 'HALL_OF_FAME': 'Hall of Fame'}
ALIASES = {'S.S. Anne': ['SS_AQUA', 'SS_ANNE']}


def humanize(words):
    out = []
    for w in words:
        if FLOOR.match(w):
            out.append(w)
        elif w in WORDS:
            if WORDS[w]:
                out.append(WORDS[w])
        else:
            out.append(w.capitalize())
    s = ' '.join(out)
    return s.replace('Guru’s House', 'Guru’s house').replace(' House', ' house').replace(' Room', ' room')


def _norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', s.lower().replace('mt.', 'mount'))


def vanilla_name(const, area):
    """The vanilla map name minus the location, when the constant belongs to this location; else None."""
    c = const[4:] if const.startswith('MAP_') else const
    if NOISE.search(c):
        return None
    for k, v in LEAGUE_ROOMS.items():
        if area == 'Pokémon League' and c.endswith(k):
            return v
    w = c.split('_')
    keys = [area, _short(area)] + [a.replace('_', ' ') for a in ALIASES.get(area, [])]
    for key in keys:
        nk = _norm(key)
        for i in (0, 1):            # MAP_GOLDENROD_RADIO_TOWER_2F under "Radio Tower"
            for j in range(i + 1, len(w) + 1):
                if _norm(''.join(w[i:j])) == nk:
                    return humanize(w[j:])
    return None


class PlaceNamer:
    def __init__(self, zones, events, base_name, overrides=None):
        """zones: bank_maps _zones; events: {events_bank: parse_events()}; base_name(z) -> location name;
        overrides: {"zone id": "name"} hand corrections (work/docs/place_names.json)."""
        self.overrides = overrides or {}
        self.Z = zones
        self.ev = events
        self.base = base_name
        self.by_area = collections.defaultdict(list)
        for z in zones:
            self.by_area[base_name(z)].append(z['zone_id'])
        self._labels = {}
        for area, zids in self.by_area.items():
            if len(zids) > 1:
                self._name_area(area, zids)

    # -------------------------------------------------------------- helpers
    def _main(self, area, zids):
        """The area's own map: the one whose layout is the location itself, else the first outdoor map."""
        for z in zids:
            if vanilla_name(self.Z[z].get('vanilla_const') or '', area) == '':
                return z
        out = [z for z in zids if self.Z[z]['map_type'] in OUTDOOR]
        return out[0] if out else zids[0]

    def _doors(self, zid):
        """[(x, z, dest zone)] warps of a zone."""
        z = self.Z[zid]
        e = self.ev.get(z['events_bank']) or {}
        return [(w['x'], w['z'], w['dest']) for w in e.get('warp', [])]

    def _compass(self, outdoor, target):
        doors = self._doors(outdoor)
        pts = [(x, y) for x, y, _ in doors]
        e = self.ev.get(self.Z[outdoor]['events_bank']) or {}
        pts += [(o['x'], o['z']) for o in e.get('obj', [])]
        mine = [(x, y) for x, y, d in doors if d == target]
        if not mine or len(pts) < 3:
            return None
        x, y = mine[0]
        xs = sorted(p[0] for p in pts)
        ys = sorted(p[1] for p in pts)
        x0, x1, y0, y1 = xs[0], xs[-1], ys[0], ys[-1]
        def third(v, lo, hi):
            if hi - lo < 6:
                return 1
            f = (v - lo) / (hi - lo)
            return 0 if f < 1 / 3 else (2 if f > 2 / 3 else 1)
        ns = ['north', '', 'south'][third(y, y0, y1)]
        we = ['west', '', 'east'][third(x, x0, x1)]
        if ns and we:
            return '%s-%s' % (ns, we)
        return ns or we or 'central'

    # -------------------------------------------------------------- naming
    def _name_area(self, area, zids):
        main = self._main(area, zids)
        labels = {main: area}
        short = _short(area)
        cave = self.Z[main]['map_type'] == 'cave'
        # pass 1: typed rooms, cave floors and buildings entered from the outdoor map
        for zid in zids:
            if zid == main:
                continue
            z = self.Z[zid]
            const = z.get('vanilla_const') or ''
            t = room_type(const, area)
            fl = _floor(const)
            vn = vanilla_name(const, area)
            if t:
                labels[zid] = '%s %s' % (short, t)
            elif vn:
                labels[zid] = '%s %s' % (short if area.endswith((' City', ' Town')) else area, vn)
            elif z['map_type'] in OUTDOOR:
                d = self._compass_any(zids, zid)
                labels[zid] = '%s, %s part' % (area, d) if d else None
            elif (z['map_type'] == 'cave' or cave) and fl:
                labels[zid] = '%s %s' % (area, fl)
            else:
                outdoors = [o for o in zids if self.Z[o]['map_type'] in OUTDOOR and any(d == zid for _, _, d in self._doors(o))]
                if outdoors:
                    pos = self._compass(outdoors[0], zid)
                    kind = 'house' if 'HOUSE' in const.upper() else 'building'
                    labels[zid] = '%s, %s %s' % (area, pos, kind) if pos else None
                else:
                    labels[zid] = None
        # pass 2: rooms reached from a named room (upstairs, back rooms)
        for _ in range(4):
            for zid in zids:
                if labels.get(zid) is not None:
                    continue
                const = self.Z[zid].get('vanilla_const') or ''
                for n in zids:
                    if n == zid or labels.get(n) is None or n == main:
                        continue
                    if any(d == zid for _, _, d in self._doors(n)) or any(d == n for _, _, d in self._doors(zid)):
                        fl = _floor(const)
                        base = re.sub(r' (B?\d+F)$', '', labels[n])
                        if fl and fl != _floor(self.Z[n].get('vanilla_const') or ''):
                            labels[zid] = '%s %s' % (base, fl)
                        elif ', inner room' not in base:
                            labels[zid] = '%s, inner room' % base
                        else:
                            continue
                        break
        # pass 3: whatever is left, and duplicates
        n = 0
        for zid in zids:
            if labels.get(zid) is None:
                n += 1
                labels[zid] = '%s, building %d' % (area, n) if self.Z[zid]['map_type'] == 'interior' else '%s, area %d' % (area, n)
        seen = collections.Counter()
        total = collections.Counter(labels.values())
        for zid in zids:
            lab = labels[zid]
            if total[lab] > 1:
                seen[lab] += 1
                if seen[lab] > 1:
                    lab = '%s (%d)' % (lab, seen[lab])
            self._labels[zid] = lab

    def _compass_any(self, zids, zid):
        """Second outdoor map of a location: its side relative to the main map on the region map."""
        ref = [z for z in zids if z != zid and self.Z[z]['map_type'] in OUTDOOR]
        if not ref:
            return None
        (x0, y0), (x1, y1) = self.Z[ref[0]].get('world_map_xy') or (0, 0), self.Z[zid].get('world_map_xy') or (0, 0)
        ns = 'north' if y1 < y0 else ('south' if y1 > y0 else '')
        we = 'west' if x1 < x0 else ('east' if x1 > x0 else '')
        return '-'.join(x for x in (ns, we) if x) or None

    def label(self, zid):
        o = self.overrides.get(str(zid))
        if o:
            return o
        return self._labels.get(zid) or self.base(self.Z[zid])
