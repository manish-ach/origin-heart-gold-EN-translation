"""Run one damage-parity scenario on the untouched Chinese ROM (D-1002). Usage:
    scen.py SPEC.json OUTDIR        run it: OUTDIR/<name>.json (raw rows) and <name>.records.json (calc inputs)
    scen.py rebuild OUTDIR/<name>.json ...   rebuild the records from a run (after editing a spec's tags/fields)

Spec (see specs/*.json and work/notes/damage_calc_parity.md):
  name; player: [{species, level, moves, item?, status? (brn/par/psn/tox/slp/frz)}]  (slot 0 leads; built with
  the game's own generator); bpp: [{species, ability?, item?}]  (ability/item of the player's or a wild Pokemon,
  written into its record before the battle); then either wild/trainer/turns for one battle or
  battles: [{wild: {species, level, moves, bpp?} | trainer: id, trainer2?: id (same id = double battle),
             tmEdit?: {species: {moves?, ability?}}, playerEdit?: {ability?, item?, moves?}, noTrainerRef?,
             turns: [{slot, slot2? (doubles: partner), target?/target2? (touch points), tag, crit? (force
             the crit flag), roll? (force the roll), field? (CalcField for the calc), fieldFoe?, set?:
             {species: {hp?, spe?}} (battle-struct writes before the turn), atkItem?/defItem?, atkStatus?/
             defStatus?, atkBoosts?/defBoosts?}]}]
Stat stages, weather ratio and the Glaive Rush flag are read from the game; see calc_cmp.mjs."""
import sys, os, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plib import *
ROOT = Path(__file__).resolve().parents[3]
TRAINERS = {t['id']: t for t in json.load(open(ROOT / 'site/src/data/trainers.json'))}

STATUS_BITS = {'slp': 1, 'psn': 0x08, 'brn': 0x10, 'frz': 0x20, 'par': 0x40, 'tox': 0x80}
TRAINER_MON_DONE = 0x0207291A   # trainer loader: finished Pokemon at r4 (damage_calc_data.md)
BPP_WEIGHT_CLAMP = 0x022164D8   # r0 = battle Pokemon; runs while the battle sets up (data agent's hook)


def to_set(m, ovr=None):
    ivs = m['ivs']; evs = m['evs']     # order hp, atk, def, spe, spa, spd
    st = m.get('party', {}) or {}
    s = dict(speciesId=m['species'], level=m['level'], nature=m['nature'], abilityId=m['ability'] or None,
             itemId=m['item'] or None, moveIds=[],
             ivs=dict(hp=ivs[0], atk=ivs[1], def_=ivs[2], spe=ivs[3], spa=ivs[4], spd=ivs[5]),
             evs=dict(hp=evs[0], atk=evs[1], def_=evs[2], spe=evs[3], spa=evs[4], spd=evs[5]))
    for d in (s['ivs'], s['evs']):
        d['def'] = d.pop('def_')
    if ovr:
        if 'ability' in ovr: s['abilityId'] = ovr['ability']
        if 'item' in ovr: s['itemId'] = ovr['item'] or None
    return s


def main(spec_path, out):
    spec = json.load(open(spec_path))
    name = spec['name']
    os.makedirs(out, exist_ok=True)
    res = dict(spec=spec, mons={}, rows=[], trainer_mons=[])
    ovr = {o['species']: o for o in spec.get('bpp', [])}
    cur = {'turn': -1}
    bpps = {}
    bpp_all = {}

    def hooks(h):
        def tm(h):
            edits = (cur.get('tmEdit') or {}).get(str(decode_pokemon(h.read(h.reg.r4, 236))['species']))
            if edits:
                fields = dict(edits)
                if 'moves' in fields:
                    fields.update(E.moveset(fields.pop('moves'), [30] * 4))
                h.write(h.reg.r4, E.encode_pokemon(h.read(h.reg.r4, 236), **fields))
            m = decode_pokemon(h.read(h.reg.r4, 236))
            res['trainer_mons'].append({k: v for k, v in m.items() if isinstance(v, (int, str, bool, type(None), list, dict))})
        h.on_exec(TRAINER_MON_DONE, tm)
        def clamp(h):
            bpps[h.u16(h.reg.r0)] = h.reg.r0
            bpp_all.setdefault(h.u16(h.reg.r0), set()).add(h.reg.r0)
        h.on_exec(BPP_WEIGHT_CLAMP, clamp)

    with E.start_at(None, sav=SAV, out=out, verbose=False, clock=CLOCK, hooks=hooks) as h:
        for i, p in enumerate(reversed(spec['player'])):
            # build from the last to the first so the first ends in slot 0
            slot = len(spec['player']) - 1 - i
            m = setup_attacker(h, p['species'], p['level'], p['moves'], item=p.get('item', 0),
                               status=STATUS_BITS.get(p.get('status')) if p.get('status') else None, slot_to=slot,
                               ability=ovr.get(p['species'], {}).get('ability'))
            res['mons'][f"p{slot}"] = m
        # Only the scenario's Pokemon stay in the party (no Exp. Share level-ups, evolutions or move prompts).
        h.w32(h.array(E.ARR_PARTY) + 4, len(spec['player']))
        dl = DamageLog(h)
        battles = spec.get('battles') or [dict(wild=spec.get('wild'), trainer=spec.get('trainer'), turns=spec['turns'])]
        cur['battle'] = 0
        def turn_spec():
            b = battles[cur['battle']]
            return b['turns'][cur['turn']] if 0 <= cur['turn'] < len(b['turns']) else {}
        orig_entry = dl.entry
        def entry(h):
            dl.force_crit = turn_spec().get('crit')
            dl.force_roll = turn_spec().get('roll')
            orig_entry(h)
            dl.cur['turn'] = cur['turn']; dl.cur['battle'] = cur['battle']
        h.on_exec(DMG_ENTRY, entry, replace=True)
        res['snap'] = []
        def snap(tag):
            res['snap'].append(dict(battle=cur['battle'], turn=cur['turn'], tag=tag,
                                    hp={str(sp): [h.u16(a + 0x1e), h.u16(a + 0x1c)] for sp, a in bpps.items()}))
        res['battle_info'] = []
        for bi, b in enumerate(battles):
            cur['battle'] = bi; cur['turn'] = -1
            bpps.clear(); bpp_all.clear()
            info = {}
            if not b.get('playerEdit'):
                res['mons'][f'p0b{bi}'] = party_mon(h, 0)     # EVs gained in earlier battles change stats
            if b.get('playerEdit'):
                pe = dict(b['playerEdit'])
                if 'moves' in pe:
                    pe.update(E.moveset(pe.pop('moves'), [30] * 4))
                h.edit_party_mon(0, **pe)
                res['mons'][f'p0b{bi}'] = party_mon(h, 0)
            if b.get('wild'):
                w = b['wild']
                o = {**ovr.get(w['species'], {}), **(w.get('bpp') or {})}
                wb = wild_battle2(h, w['species'], w['level'], item=o.get('item', w.get('item')), moves=w.get('moves', [150]),
                                  ability=o.get('ability'))
                info['wild'] = wb
                info['mon'] = wild_mon_info(h, wb['pid'])
                res['mons'][f'wild{bi}'] = info['mon']
            else:
                cur['tmEdit'] = b.get('tmEdit')
                t2 = b.get('trainer2', 0)
                for attempt in range(12):
                    try:
                        h.run_script(program=E.script_bytes(("LockAll",), ("TrainerBattle", b['trainer'], t2, 1, 0),
                                                            ("ReleaseAll",), ("End",)))
                        break
                    except RuntimeError as e:      # a message after the last battle may still be open
                        res.setdefault('errors', []).append(f"b{bi} start attempt {attempt}: {e}")
                        h.press("B", after=60)
                        h.step(120)
            res['battle_info'].append(info)
            for t, turn in enumerate(b['turns']):
                cur['turn'] = t
                if not h.wait_screen("battle_menu", 1500):
                    res.setdefault('errors', []).append(f"b{bi} t{t}: no menu")
                    break
                for sp, fields in (turn.get('set') or {}).items():
                    for a in bpp_all.get(int(sp), ()):
                        if 'hp' in fields:
                            h.w16(a + 0x1e, fields['hp'])
                        if 'spe' in fields:
                            h.w16(a + 0x234, fields['spe'])
                snap('start')
                try:
                    if 'slot2' in turn:
                        shots = []
                        choose(h, turn['slot'], turn.get('target', TARGET_TL), shots, f'b{bi}t{t}a')
                        choose(h, turn['slot2'], tuple(turn['target2']) if turn.get('target2') else None, shots, f'b{bi}t{t}b')
                        st = finish_turn(h)
                    else:
                        st = h.battle_turn(turn['slot'])
                except RuntimeError as e:
                    res.setdefault('errors', []).append(f"b{bi} t{t}: {e}")
                    break
                snap('end')
                if st == 'field':
                    info['ended'] = t
                    break
            else:
                if bi < len(battles) - 1:
                    info['fled'] = h.flee(battle_menu_wait=30)
            h.screenshot(f'{name}_b{bi}_end')
        res['rows'] = dl.rows
    for r in res['rows']:
        r['attacker'].pop('raw', None); r['defender'].pop('raw', None)
    dump(res, f'{out}/{name}.json')
    recs = build_records(spec, res, ovr)
    dump(recs, f'{out}/{name}.records.json')
    print('done', name, len(res['rows']), 'hits', res.get('errors', ''))


def build_records(spec, res, ovr):
    name = spec['name']
    # records for the calc
    recs = []
    hit_count = {}
    by_species = {}
    for k, m in res['mons'].items():
        if m and k.startswith('p') and 'b' not in k:
            by_species.setdefault(m['species'], m)
    for m in res['trainer_mons']:
        by_species.setdefault(m['species'], m)
    pstat = {p['species']: p.get('status') for p in spec['player'] if p.get('status')}
    for r in res['rows']:
        a, d = r['attacker'], r['defender']
        look = dict(by_species)
        pm = res['mons'].get(f"p0b{r.get('battle', 0)}")
        if pm:
            look[pm['species']] = pm
        wm = res['mons'].get(f"wild{r.get('battle', 0)}")
        if wm:
            look[wm['species']] = wm
        ma, md = look.get(a['species']), look.get(d['species'])
        if not ma or not md:
            continue
        bt = (spec.get('battles') or [dict(turns=spec['turns'])])[r.get('battle', 0)]['turns']
        turn = bt[r['turn']] if 0 <= r.get('turn', -1) < len(bt) else {}
        sa, sd = to_set(ma, ovr.get(a['species'])), to_set(md, ovr.get(d['species']))
        hpa = a['hp2'] * 100 / a['hp'] if a['hp'] else 100
        hpd = d['hp2'] * 100 / d['hp'] if d['hp'] else 100
        sa['curHPPercent'] = hpa; sd['curHPPercent'] = hpd
        for st_, x in ((sa, a), (sd, d)):
            b_ = {k: v - 6 for k, v in zip(('atk', 'def', 'spa', 'spd', 'spe'), x['stages'][:5]) if v != 6}
            if b_:
                st_['boosts'] = b_
            if st_.get('abilityId') == 22:      # Intimidate: its drop is already in the observed stages
                st_['abilityOn'] = False
        if pstat.get(a['species']): sa['status'] = pstat[a['species']]
        if pstat.get(d['species']): sd['status'] = pstat[d['species']]
        if 'atkItem' in turn: sa['itemId'] = turn['atkItem']      # e.g. a Gem consumed by an earlier hit
        if 'defItem' in turn: sd['itemId'] = turn['defItem']
        if turn.get('atkStatus'): sa['status'] = turn['atkStatus']
        if turn.get('defStatus'): sd['status'] = turn['defStatus']
        if turn.get('atkBoosts'): sa['boosts'] = turn['atkBoosts']
        if turn.get('defBoosts'): sd['boosts'] = turn['defBoosts']
        player_species = {p['species'] for p in spec['player']}
        fld = turn.get('field', {})
        if a['species'] not in player_species:
            fld = turn.get('fieldFoe', {**fld, 'attackerSide': fld.get('defenderSide', {}), 'defenderSide': fld.get('attackerSide', {})})
        key = (r.get('battle'), r.get('turn'), a['addr'], d['addr'], r['move'], r.get('lr'))
        hit_count[key] = hit_count.get(key, -1) + 1
        b = (spec.get('battles') or [spec])[r.get('battle', 0)]
        tref = {}
        if b.get('trainer') and not b.get('noTrainerRef'):
            team = TRAINERS[b['trainer']]['team']
            for role, x in (('attacker', a), ('defender', d)):
                idx = [i for i, m in enumerate(team) if m['id'] == x['species']]
                if idx and x['species'] not in player_species:
                    tref[role] = [b['trainer'], idx[0]]
        recs.append(dict(case=f"{name}/b{r.get('battle')}t{r.get('turn')}/{turn.get('tag', '')}", attacker=sa, defender=sd,
                         moveId=r['move'], field=fld, hitIndex=hit_count[key], trainerRef=tref,
                         obs=dict(roll=r.get('roll'), crit=r['crit'], damage=r['damage'], atkStats=a['stats'],
                                  defStats=d['stats'], eff=r['eff'], power=r.get('power'), atk=r.get('atk'),
                                  def_=r.get('def'), base=r.get('base'), weatherRatio=r.get('weatherRatio'),
                                  glaive=r.get('glaive'), stab=r.get('stabRatio'), finalMod=r.get('finalMod'),
                                  preFinal=r.get('preFinal'), hpBefore=[a['hp2'], d['hp2']],
                                  maxHP=[a['hp'], d['hp']], targetRatio=r['targetRatio'],
                                  stages=[a['stages'], d['stages']], lr=r.get('lr'))))
    return recs


def rebuild(res_path):
    res = json.load(open(res_path))
    spec = res['spec']
    sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'specs', spec['name'] + '.json')
    if os.path.exists(sp):          # tags and calc fields may be corrected after the run
        spec = json.load(open(sp))
    ovr = {o['species']: o for o in spec.get('bpp', [])}
    recs = build_records(spec, res, ovr)
    dump(recs, res_path.replace('.json', '.records.json'))


if __name__ == '__main__':
    if sys.argv[1] == 'rebuild':
        for p in sys.argv[2:]:
            rebuild(p)
    else:
        main(sys.argv[1], sys.argv[2])
