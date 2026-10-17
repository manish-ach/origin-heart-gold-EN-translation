// Compare emulator damage records with the calc. Usage: node calc_cmp.mjs records.json [more.json ...]
// Each record: {case, attacker: CalcSet-ish (nature as game index), defender, moveId, field, obs: {roll, crit, damage,
//   atkStats, defStats, eff, power, atk, def, base}}
import { readFileSync } from 'node:fs';
const SITE = new URL('../../../site', import.meta.url).pathname;
const { loadCalc, buildCalcData } = await import(`${SITE}/src/lib/calc/index.ts`);
const read = n => JSON.parse(readFileSync(`${SITE}/src/data/${n}.json`, 'utf8'));
const formChanges = [
  { base: 6, result: 1027, item: 325, condition: 'Any nature except Timid or Modest.' },
  { base: 6, result: 1028, item: 325, condition: 'Timid or Modest nature.' },
  { base: 150, result: 1440, item: 114, condition: 'No nature requirement.' },
];
const data = buildCalcData({ species: read('species'), moves: read('moves'), abilities: read('abilities'), items: read('items'),
  trainers: read('trainers'), formChanges });
const calc = loadCalc(JSON.parse(JSON.stringify(data)));
const GAME_NATURES = ['Hardy', 'Lonely', 'Brave', 'Adamant', 'Naughty', 'Bold', 'Docile', 'Relaxed', 'Impish', 'Lax', 'Timid',
  'Hasty', 'Serious', 'Jolly', 'Naive', 'Modest', 'Mild', 'Quiet', 'Bashful', 'Rash', 'Calm', 'Gentle', 'Sassy', 'Careful', 'Quirky'];
const toSet = s => ({ ...s, nature: typeof s.nature === 'number' ? GAME_NATURES[s.nature] : s.nature });
const out = [];
for (const file of process.argv.slice(2)) {
  for (const r of JSON.parse(readFileSync(file, 'utf8'))) {
    const field = { ...(r.field || {}), crit: !!r.obs.crit };
    // Weather is game state: when the field does not name it, infer rain/sun from the observed weather ratio.
    if (!field.weather && r.obs.weatherRatio && r.obs.weatherRatio !== 4096) {
      const mt = calc.generation.moves.get(r.moveId)?.type;
      const up = r.obs.weatherRatio > 4096;
      if (mt === 'Water') field.weather = up ? 'Rain' : 'Sun';
      if (mt === 'Fire') field.weather = up ? 'Sun' : 'Rain';
    }
    // Glaive Rush: the vulnerability flag is read from the game (timing is reported separately).
    if (r.obs.glaive) field.defenderSide = { ...(field.defenderSide || {}), glaiveRush: true };
    const TR = globalThis.TR ??= Object.fromEntries(read('trainers').map(t => [t.id, t]));
    const fromRef = (ref, decoded) => {
      if (!ref) return toSet(decoded);
      const set = calc.fromTrainerMon(TR[ref[0]].team[ref[1]]);
      return { ...set, curHPPercent: decoded.curHPPercent, status: decoded.status, boosts: decoded.boosts, abilityOn: decoded.abilityOn };
    };
    const useRef = !!process.env.TRAINER_REF;
    const A = useRef ? fromRef(r.trainerRef?.attacker, r.attacker) : toSet(r.attacker);
    const D = useRef ? fromRef(r.trainerRef?.defender, r.defender) : toSet(r.defender);
    const res = calc.calculateMatchup({ ...A, moveIds: [r.moveId] }, D, field);
    const m = res.moves[0];
    const s = res.attacker.stats, t = res.defender.stats;
    const calcAtk = [s.atk, s.def, s.spa, s.spd, s.spe], calcDef = [t.atk, t.def, t.spa, t.spd, t.spe];
    // Speed is excluded: some scenarios overwrite the battle speed stat to force the move order.
    const same = (x, y) => JSON.stringify(x.slice(0, 4)) === JSON.stringify(y.slice(0, 4));
    const statsOk = (!r.obs.atkStats || same(calcAtk, r.obs.atkStats)) && (!r.obs.defStats || same(calcDef, r.obs.defStats));
    let expected = null;
    if (m && m.rolls.length === 16 && r.obs.roll) expected = m.rolls[r.obs.roll - 85];
    else if (m && m.rolls.length === 1) expected = m.rolls[0];
    if (m && m.hitRolls && r.hitIndex != null && r.obs.roll) expected = m.hitRolls[r.hitIndex]?.[r.obs.roll - 85];
    const verdict = expected == null ? 'N/A' : expected === r.obs.damage && statsOk ? 'PASS' : 'FAIL';
    out.push({ case: r.case, move: m?.name, verdict, obs: r.obs.damage, roll: r.obs.roll, crit: r.obs.crit, expected,
      statsOk, calcAtk, calcDef, rolls: m?.rolls, desc: m?.description, caveats: m?.caveats, note: r.note, lr: r.obs.lr, hitIndex: r.hitIndex, trainerRef: useRef ? r.trainerRef : undefined, setA: A, setD: D, fieldUsed: field, moveId: r.moveId, obsAtk: r.obs.atkStats, obsDef: r.obs.defStats, obsLr: r.obs.lr, eff: r.obs.eff,
      calcHP: [res.attacker.maxHP, res.defender.maxHP] });
  }
}
console.log(JSON.stringify(out, null, 1));
