// In-game parity fixtures for the damage engine (site/src/lib/calc).
//
// Every fixture is one real hit observed in the emulator on the untouched Chinese ROM (D-1002): the damage
// routine ov14 0x0220876C was hooked and the game's own random roll (85–100), critical-hit flag, final damage
// and the battle Pokémon's stats were read from memory. Sets are the Pokémon the game actually built (decoded
// from RAM), or, for trainer Pokémon, `{trainer: [trainerId, teamIndex]}`, i.e. calc.fromTrainerMon on the
// exported trainers.json entry, so these also check the trainer export against what the game spawns.
// Method, cases and findings: work/notes/damage_calc_parity.md. Regenerate with the parity harness there.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { loadCalc, buildCalcData } from '../src/lib/calc/index.ts';

const read = name => JSON.parse(readFileSync(new URL(`../src/data/${name}.json`, import.meta.url), 'utf8'));
const species = read('species'), moves = read('moves'), abilities = read('abilities'), items = read('items'), trainers = read('trainers');
const formChanges = [
  { base: 6, result: 1027, item: 325, condition: 'Any nature except Timid or Modest.' },
  { base: 6, result: 1028, item: 325, condition: 'Timid or Modest nature.' },
  { base: 150, result: 1440, item: 114, condition: 'No nature requirement.' },
];
const calc = loadCalc(JSON.parse(JSON.stringify(buildCalcData({ species, moves, abilities, items, trainers, formChanges }))));
const TRAINERS = Object.fromEntries(trainers.map(t => [t.id, t]));
const fixtures = JSON.parse(readFileSync(new URL('./damage-calc-parity.fixtures.json', import.meta.url), 'utf8'));

function toSet(s) {
  if (!s.trainer) return s;
  const [id, index] = s.trainer;
  return { ...calc.fromTrainerMon(TRAINERS[id].team[index]), curHPPercent: s.curHPPercent, boosts: s.boosts };
}

/** The calc's number for the game's roll (or its single value for fixed damage). */
function predicted(f) {
  const out = calc.calculateMatchup({ ...toSet(f.attacker), moveIds: [f.moveId] }, toSet(f.defender), { ...f.field, crit: f.crit });
  const m = out.moves[0];
  const stats = p => [p.stats.atk, p.stats.def, p.stats.spa, p.stats.spd];
  let value;
  if (m.hitRolls && f.roll) value = m.hitRolls[f.hitIndex ?? 0][f.roll - 85];
  else if (m.rolls.length === 16 && f.roll) value = m.rolls[f.roll - 85];
  else value = m.rolls[0];
  return { value, attackerStats: stats(out.attacker), defenderStats: stats(out.defender), move: m };
}

test('parity fixtures are present and cover the planned mechanics', () => {
  assert.ok(fixtures.length >= 200, `${fixtures.length} fixtures`);
  const groups = new Set(fixtures.map(f => f.case.split('/')[0]));
  for (const g of ['base1', 'types', 'types2', 'burn', 'weather', 'sandhail', 'screens', 'doubles1', 'doubles2', 'doubles3', 'glaive',
    'fixed', 'pbond', 'abil_att', 'abil_def', 'items', 'souldew', 'trainers1', 'trainers2']) {
    assert.ok(groups.has(g), `fixture group ${g}`);
  }
});

const byGroup = {};
for (const f of fixtures) (byGroup[f.case.split('/')[0]] ??= []).push(f);
for (const [group, list] of Object.entries(byGroup)) {
  test(`in-game damage matches the calc: ${group} (${list.length} hits)`, () => {
    for (const f of list) {
      const p = predicted(f);
      const label = `${f.case} ${f.move} roll ${f.roll} crit ${f.crit}`;
      assert.deepEqual(p.attackerStats, f.attackerStats, `${label}: attacker stats`);
      assert.deepEqual(p.defenderStats, f.defenderStats, `${label}: defender stats`);
      assert.equal(p.value, f.damage, `${label}: damage (rolls ${p.move.rolls.join(',')})`);
    }
  });
}

// Behaviour checked in game without a damage number (HP before/after, move order). See the parity note.
test('emulator-verified: paralysis halves Speed (100 → 50 moves before 49, after 51)', () => {
  const fast = { speciesId: 68, level: 100, nature: 'Serious', abilityId: 99, itemId: null, moveIds: [], status: 'par' };
  const r = calc.speedOrder(fast, { speciesId: 143, level: 30, nature: 'Serious', abilityId: 50, itemId: null, moveIds: [] });
  const unpar = calc.speedOrder({ ...fast, status: '' }, { speciesId: 143, level: 30, nature: 'Serious', abilityId: 50, itemId: null, moveIds: [] });
  assert.equal(r.aSpeed, Math.floor(unpar.aSpeed / 2));
  assert.ok(!r.caveats.some(c => c.startsWith('Paralysis')));
});

test('emulator-verified: no caveat for Glaive Rush, Parental Bond, hail, or the two inert duplicate items checked', () => {
  const machamp = { speciesId: 68, level: 50, nature: 'Serious', abilityId: 99, itemId: null, moveIds: [33] };
  const snorlax = { speciesId: 143, level: 50, nature: 'Serious', abilityId: 50, itemId: null, moveIds: [] };
  const all = [
    calc.calculateMatchup(machamp, snorlax, { defenderSide: { glaiveRush: true } }),
    calc.calculateMatchup({ ...machamp, abilityId: abilities.find(a => a.name === 'Parental Bond').id }, snorlax),
    calc.calculateMatchup(machamp, { ...snorlax, speciesId: 362 }, { weather: 'Hail' }),
    calc.calculateMatchup(machamp, { ...snorlax, itemId: 324 }),
  ];
  const caveats = all.flatMap(r => r.moves[0].caveats);
  assert.ok(!caveats.some(c => /Glaive Rush|Parental Bond|hail chip|not confirmed in game/.test(c)), caveats.join(' | '));
  assert.ok(all[3].moves[0].caveats.some(c => c.includes('This Rocky Helmet') && c.includes('checked in game')));
});

test('emulator-verified: Corrosion leaves Steel types immune to Poison moves', () => {
  const corr = { speciesId: 68, level: 50, nature: 'Serious', abilityId: abilities.find(a => a.name === 'Corrosion').id,
    itemId: null, moveIds: [moves.find(m => m.name === 'Poison Jab').id] };
  const r = calc.calculateMatchup(corr, { speciesId: 379, level: 100, nature: 'Serious', abilityId: 50, itemId: null, moveIds: [] });
  assert.equal(r.moves[0].maxDamage, 0);
  assert.ok(r.notes.some(n => n.startsWith('Corrosion does not')));
});
