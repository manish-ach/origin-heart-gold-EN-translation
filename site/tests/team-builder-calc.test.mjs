import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { STORAGE_KEY } from '../src/lib/team-builder.mjs';
import {
  STORAGE_KEY_V2, loadStoredState, saveStoredState, parseStateHash, stateHash, encodeSet, decodeSet, sanitizeSet,
  replaceMember, removeMember, opponentHash,
} from '../src/lib/team-builder-state.mjs';
import { createDex, resolveSet, suggestedMoves, learnableMoves, exportShowdown, importShowdown, compactSet, showdownAliases, evolutionLevel, applyFoeEdit, cleanFoeEdit } from '../src/lib/battle-sets.mjs';
import { CAVEATS } from '../src/lib/calc/caveats.ts';
import { buildBattleData, playOrder, trainerMon, LATER, levelMargin } from '../src/lib/battle-check-data.mjs';
import { buildCalcData, loadCalc } from '../src/lib/calc/index.ts';

const read = name => JSON.parse(readFileSync(new URL(`../src/data/${name}.json`, import.meta.url), 'utf8'));
const species = read('species'), moves = read('moves'), abilities = read('abilities'), items = read('items');
const trainers = read('trainers'), areas = read('areas'), guide = read('trainer_guide'), tms = read('tms');
const calcData = JSON.parse(JSON.stringify(buildCalcData({ species, moves, abilities, items, trainers })));
const battleData = JSON.parse(JSON.stringify(buildBattleData({ species, areas, trainers, guide, tms })));
const dex = createDex(calcData, battleData);
const known = new Set(species.map(mon => mon.id));
const MOVE = Object.fromEntries(moves.map(m => [m.name, m.id]));
const ITEM = Object.fromEntries(items.map(i => [i.name, i.id]));
const ABILITY = Object.fromEntries(abilities.map(a => [a.name, a.id]));

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return { getItem: key => data.has(key) ? data.get(key) : null, setItem: (key, value) => data.set(key, String(value)), data };
}

test('state v2 migrates the v1 key, keeps v1 in sync and rejects malformed saves', () => {
  const v1 = memoryStorage({ [STORAGE_KEY]: JSON.stringify([3, 94, 3, 'x', 99999]) });
  assert.deepEqual(loadStoredState(v1, known), { team: [3, 94], sets: {}, opponent: null });
  const storage = memoryStorage();
  saveStoredState(storage, { team: [3, 94], sets: { 3: { level: 40, nature: 'Modest', moves: [22] }, 25: { level: 9 } }, opponent: { trainer: 253 } });
  assert.deepEqual(JSON.parse(storage.getItem(STORAGE_KEY)), [3, 94], 'v1 key still written for older pages');
  assert.deepEqual(loadStoredState(storage, known), { team: [3, 94], sets: { 3: { level: 40, nature: 'Modest', moves: [22] } }, opponent: { trainer: 253 } });
  const broken = memoryStorage({ [STORAGE_KEY_V2]: '{not json', [STORAGE_KEY]: '[25]' });
  assert.deepEqual(loadStoredState(broken, known).team, [25], 'a corrupt v2 entry falls back to v1');
  assert.deepEqual(sanitizeSet({ level: 0, nature: 'Hardy', ivs: { hp: 31, atk: 0 }, evs: { spe: 300 }, hp: 100, status: 'bad', boosts: { atk: 7, spe: -1 } }),
    { ivs: { atk: 0 }, boosts: { spe: -1 } }, 'defaults and out-of-range values are dropped');
  assert.equal(sanitizeSet({ nature: 'Xyzzy' }), null, 'only the 25 natures');
  assert.deepEqual(sanitizeSet({ nature: 'Modest' }), { nature: 'Modest' });
});

test('share links round-trip sets compactly and old #team links still load', () => {
  const state = {
    team: [3, 94, 1027], opponent: { trainer: 253 },
    sets: { 3: { level: 50, nature: 'Modest', ability: 34, item: 239, moves: [22, 73, 79, 33], ivs: { atk: 0 }, evs: { hp: 252, spa: 252, spe: 4 }, hp: 50, status: 'par', boosts: { spa: 2, spe: -1 } }, 94: { item: 270 } },
  };
  const hash = stateHash(state, { battle: true });
  assert.equal(hash, '#team=3,94,1027&sets=3.L50.NModest.A34.I239.M22-73-79-33.V31-0-31-31-31-31.E252-0-0-252-0-4.H50.Spar.Bggigf_94.I270&battle=253');
  assert.deepEqual(parseStateHash(hash, known), { team: state.team, sets: state.sets, battle: true, opponent: { trainer: 253 } });
  assert.equal(stateHash({ team: [720, 1243], sets: {} }), '#team=720,1243', 'no sets: the v1 link shape');
  assert.deepEqual(parseStateHash('#team=3,94', known), { team: [3, 94], sets: {}, battle: false, opponent: undefined });
  assert.deepEqual(parseStateHash('#battle=253', known), { team: null, sets: null, battle: true, opponent: { trainer: 253 } }, 'trainer deep link keeps the saved team');
  const free = stateHash({ team: [25], sets: {}, opponent: { species: 6, set: { level: 30 } } }, { battle: true });
  assert.equal(free, '#team=25&battle=free&foe=6.L30');
  assert.deepEqual(parseStateHash(free, known).opponent, { species: 6, set: { level: 30 } });
  assert.deepEqual(decodeSet(encodeSet({ boosts: { atk: 6, def: -6 } })), { boosts: { atk: 6, def: -6 } });
  assert.deepEqual(parseStateHash('#team=3&sets=3.Lnope.Mx-1.Bzz_99.L5', known).sets, { 3: { moves: [1] } }, 'garbage fields are ignored');
  assert.equal(parseStateHash('#team=%E0%A4%A', known).team, null, 'a damaged team link keeps the saved team');
  assert.equal(parseStateHash('#team=3.NXyzzy', known).team, null);
  assert.deepEqual(parseStateHash('#team=', known).team, [], 'an explicitly empty team is still a team');
  assert.deepEqual(parseStateHash('#team=3&sets=3.NXyzzy', known).sets, {}, 'unknown nature dropped');
});

test('default sets: opponent level, neutral nature, first ability, suggested level-up moves', () => {
  const venusaur = resolveSet(dex, 3, null, { level: 14 });
  assert.equal(venusaur.calc.level, 14);
  assert.equal(venusaur.calc.nature, null);
  assert.equal(venusaur.calc.abilityId, species.find(s => s.id === 3).abilityIds[0]);
  assert.equal(venusaur.calc.itemId, null);
  assert.deepEqual(venusaur.calc.ivs, { hp: 31, atk: 31, def: 31, spa: 31, spd: 31, spe: 31 });
  assert.deepEqual(venusaur.calc.evs, { hp: 0, atk: 0, def: 0, spa: 0, spd: 0, spe: 0 });
  assert.ok(venusaur.autoLevel && venusaur.suggestedMoves);
  assert.deepEqual(suggestedMoves(dex, 3, 14), venusaur.calc.moveIds);
  assert.ok(venusaur.calc.moveIds.every(id => learnableMoves(dex, 3).includes(id)));
  const custom = resolveSet(dex, 3, { level: 60, moves: [MOVE['Giga Drain']], ability: 999 }, { level: 14 });
  assert.equal(custom.calc.level, 60);
  assert.deepEqual(custom.calc.moveIds, [MOVE['Giga Drain']]);
  assert.equal(custom.calc.abilityId, species.find(s => s.id === 3).abilityIds[0], 'an ability the species cannot have falls back');
  assert.equal(compactSet(dex, 3, { ability: species.find(s => s.id === 3).abilityIds[0], nature: 'Hardy' }), null);
  // Every species with a learnset gets a suggestion; the engine accepts the default set.
  const calc = loadCalc(calcData);
  for (const mon of species.slice(0, 200)) {
    const set = resolveSet(dex, mon.id, null, { level: 50 }).calc;
    if (learnableMoves(dex, mon.id).length) assert.ok(set.moveIds.length > 0, mon.name);
    calc.calculateMatchup(set, calc.fromTrainerMon(trainers[0].team[0]));
  }
});

test('suggested moves: evolution moves, pre-evolution moves, strongest attacks first, fallbacks', () => {
  const names = (name, level) => suggestedMoves(dex, species.find(s => s.name === name).id, level).map(id => dex.moves.get(id).name);
  const damaging = ids => ids.filter(id => dex.moves.get(id).cat !== 'Status');
  // Moves learnt on evolving (level 0) are kept.
  assert.ok(names('Venusaur', 30).includes('Petal Blizzard'));
  assert.ok(names('Charizard', 36).includes('Air Slash'));
  assert.ok(names('Nidoking', 30).includes('Megahorn'));
  assert.ok(names('Nidoqueen', 30).includes('Superpower'));
  assert.ok(names('Alolan Raichu', 20).includes('Psychic'));
  // Espeon keeps Confusion (its evolution move) and Eevee's attacks instead of Growl / Tail Whip.
  const espeon = names('Espeon', 12);
  assert.ok(espeon.includes('Confusion'));
  assert.ok(!espeon.includes('Growl') && !espeon.includes('Tail Whip'));
  // Pre-evolution moves count: Metapod keeps Caterpie's Tackle.
  assert.ok(names('Metapod', 8).includes('Tackle'));
  // The strongest same-type attack comes first, and types are not repeated while others are available.
  const charizard = suggestedMoves(dex, 6, 36).map(id => dex.moves.get(id));
  assert.ok(charizard[0].type === 'Fire' || charizard[0].type === 'Flying', charizard[0].name);
  assert.equal(new Set(charizard.map(m => m.type)).size, charizard.length);
  // Fewer than two attacks from levelling up: TM / tutor moves fill in (Abra, Smeargle). Ditto keeps Transform.
  assert.ok(damaging(suggestedMoves(dex, 63, 10)).length >= 2, 'Abra');
  assert.ok(damaging(suggestedMoves(dex, 235, 30)).length >= 1, 'Smeargle');
  assert.deepEqual(names('Ditto', 30), ['Transform']);
  // Every species gets at least one attack, except Ditto.
  const none = species.filter(mon => !damaging(suggestedMoves(dex, mon.id, 30)).length).map(mon => mon.name);
  assert.deepEqual(none, ['Ditto']);
  // Evolution level hint.
  assert.deepEqual(evolutionLevel(dex, 3), { level: 32, exact: true });
  assert.deepEqual(evolutionLevel(dex, 94), { level: 25, exact: false }, 'Gengar: Haunter at 25, then a non-level step');
  assert.equal(evolutionLevel(dex, 1), null);
});

test('Showdown export and import round-trip with the hack’s names', () => {
  const set = { level: 52, nature: 'Modest', ability: species.find(s => s.id === 3).hiddenAbilityId, item: ITEM['Miracle Seed'],
    moves: [MOVE['Giga Drain'], MOVE['Sludge Bomb']], ivs: { atk: 0 }, evs: { hp: 252, spa: 252, spe: 4 } };
  const text = exportShowdown(dex, 3, resolveSet(dex, 3, set, { level: 14 }));
  assert.equal(text, 'Venusaur @ Miracle Seed\nAbility: Thick Fat\nLevel: 52\nEVs: 252 HP / 252 SpA / 4 Spe\nModest Nature\nIVs: 0 Atk\n- Giga Drain\n- Sludge Bomb');
  const back = importShowdown(dex, text);
  assert.deepEqual(back.errors, []);
  assert.deepEqual(back.sets, [{ speciesId: 3, name: 'Venusaur', set }]);
  const team = importShowdown(dex, `Sparky (Raichu-Alola) (F) @ Life Orb\nAbility: Surge Surfer\nTimid Nature\n- Thunderbolt\n- Psychic\n\nCharizard-Mega-X\n- Flare Blitz\n\nRotom-Wash\n- Hydro Pump`);
  assert.deepEqual(team.errors, []);
  assert.deepEqual(team.sets.map(s => s.name), ['Alolan Raichu', 'Mega Charizard X', 'Wash Rotom']);
  assert.equal(team.sets[0].set.level, undefined, 'no Level line keeps the automatic level');
  assert.equal(team.sets[0].set.ability, ABILITY['Surge Surfer']);
  const bad = importShowdown(dex, 'Pikachoo @ Leftovers\n- Thunderbolt\n\nPikachu @ Mystery Thing\nAbility: Drizzle\n- Not A Move\n- Thunderbolt');
  assert.deepEqual(bad.errors, [
    'Unknown Pokémon “Pikachoo”. Use the name shown in this guide’s Pokédex.',
    'Pikachu: unknown item “Mystery Thing”.',
    'Pikachu can’t have the Ability Drizzle in this game.',
    'Pikachu: unknown move “Not A Move”.',
  ]);
  assert.deepEqual(importShowdown(dex, '  ').errors, ['Paste a set in Showdown format first.']);
  const hp = importShowdown(dex, 'Pikachu\n- Hidden Power [Fire]\n- Thunderbolt');
  assert.deepEqual(hp.errors, []);
  assert.ok(hp.warnings.some(w => w.includes('Hidden Power’s type comes from the IVs')));
  assert.equal(hp.sets[0].set.moves[0], MOVE['Hidden Power']);
  assert.deepEqual(importShowdown(dex, 'Pikachu\nEVs: 252 Atk / 252 Spe / 252 HP\n- Thunderbolt').errors,
    ['Pikachu: EVs add up to 756; the most a Pokémon can have is 510.']);
  assert.ok(showdownAliases('Heat Rotom', new Set(['Rotom'])).includes('Rotom-Heat'));
});

test('battle data: play order, trainer conversion and learnsets', () => {
  const order = playOrder({ trainers, areas, guide }).map(entry => entry.t.id);
  const at = id => order.indexOf(id);
  // Kanto Gym challenges in the guide's order: Brock, Misty, Lt. Surge, Erika, Koga, Blaine.
  for (const [a, b] of [[253, 254], [254, 255], [255, 256], [256, 257], [257, 259]]) assert.ok(at(a) < at(b), `${a} before ${b}`);
  assert.ok(at(253) < at(720), 'Brock’s challenge before his rematch');
  // The first places hold early teams only; rematches and post-game teams form a later group sorted by level.
  const entries = playOrder({ trainers, areas, guide });
  const normal = entries.filter(e => !(e.f & (3 | LATER)) && e.area);
  const firstArea = normal[0].area;
  assert.equal(firstArea, 'pallet-town');
  assert.ok(normal.filter(e => e.area === firstArea).every(e => e.l <= 10), 'Pallet Town opens with low-level teams');
  const pewter = normal.filter(e => e.area === 'pewter-city');
  assert.equal(pewter.find(e => /Brock/.test(e.t.name))?.t.id, 253, 'Brock’s first team (Lv. 12) is the one under Pewter City');
  assert.ok(pewter.every(e => e.l <= 20));
  for (const id of [720, 721, 491, 753]) assert.ok(entries.find(e => e.t.id === id).f & LATER, `${id} is a rematch or later battle`);
  const later = entries.filter(e => e.f & LATER && !(e.f & 3)).map(e => e.l);
  assert.deepEqual(later, [...later].sort((a, b) => a - b), 'later battles by level');
  assert.ok(entries.findIndex(e => e.f & LATER) > entries.findLastIndex(e => !(e.f & (3 | LATER)) && e.area), 'later battles after the route');
  // Gym challenges stay at their Gym, even far above the place's usual level (Whitney Lv. 88 in Goldenrod).
  for (const id of [20, 21, 30, 253, 254, 255]) assert.equal(entries.find(e => e.t.id === id).f & LATER, 0, `${id} challenge`);
  // Each place forms one group.
  const groups = normal.map(e => e.area).filter((a, i, all) => a !== all[i - 1]);
  assert.equal(new Set(groups).size, groups.length, 'no place appears twice');
  assert.equal(levelMargin(12), 10);
  assert.equal(levelMargin(65), 23);
  assert.ok(battleData.trainers.every(t => t[7].length > 0), 'only teams with Pokémon');
  const brock = battleData.trainers.find(t => t[0] === 253);
  const original = trainers.find(t => t.id === 253);
  assert.equal(brock[5], 'pewter-city');
  assert.equal(battleData.areaNames['pewter-city'], 'Pewter City');
  const mon = trainerMon(brock[7][0]);
  for (const key of ['id', 'level', 'abilityId', 'itemId', 'moveIds', 'nature', 'ivs', 'hpIvs', 'evs', 'gender', 'friendship']) assert.deepEqual(mon[key], original.team[0][key], key);
  const learnable = learnableMoves(dex, 151);
  assert.ok(tms.every(tm => learnable.includes(tm.moveId)), 'Mew learns every TM');
});

test('production build ships the damage engine’s MIT notice', { skip: process.env.GUIDE_TEST_DIST !== '1' }, async () => {
  const { readdirSync } = await import('node:fs');
  const dist = new URL('../dist/', import.meta.url);
  const chunk = readdirSync(new URL('_astro/', dist)).find(name => /^battle-check\..*\.js$/.test(name));
  assert.ok(chunk, 'damage calculator chunk built');
  const code = readFileSync(new URL(`_astro/${chunk}`, dist), 'utf8');
  assert.match(code, /\/\*! @license MIT[\s\S]*Honko and other contributors/);
  const licence = readFileSync(new URL('licenses/smogon-damage-calc.txt', dist), 'utf8');
  assert.equal(licence, readFileSync(new URL('../src/lib/calc/LICENSE', import.meta.url), 'utf8'));
  assert.match(readFileSync(new URL('team-builder/index.html', dist), 'utf8'), /href="[^"]*licenses\/smogon-damage-calc\.txt"/);
});

test('swapping or adding a member from the calculator keeps the opponent and the other sets', () => {
  const state = { team: [3, 12, 196], sets: { 3: { level: 40 }, 12: { item: ITEM['Silver Powder'] } }, opponent: { trainer: 20 }, active: 3 };
  const swapped = replaceMember(state, 12, 6, known);
  assert.deepEqual(swapped, { team: [3, 6, 196], sets: { 3: { level: 40 } }, active: 6 }, 'same slot, the old set dropped, the new member selected');
  assert.deepEqual(state.opponent, { trainer: 20 }, 'the opponent is not touched');
  assert.equal(stateHash({ ...swapped, opponent: state.opponent }, { battle: true }), '#team=3,6,196&sets=3.L40&battle=20', 'the link keeps the fight');
  assert.deepEqual(replaceMember(swapped, null, 25, known).team, [3, 6, 196, 25], 'a free slot is filled at the end');
  assert.equal(replaceMember(swapped, null, 3, known).reason, 'duplicate');
  assert.equal(replaceMember({ team: [1, 4, 7, 25, 3, 6], sets: {} }, null, 9, known).reason, 'full');
  assert.deepEqual(replaceMember({ team: [1, 4, 7, 25, 3, 6], sets: {} }, 25, 9, known).team, [1, 4, 7, 9, 3, 6], 'a full team can still swap');
  assert.equal(replaceMember(swapped, null, 99999, known).reason, 'unknown');
  assert.deepEqual(removeMember({ team: [3, 6, 196], sets: { 3: { level: 40 } }, active: 6 }, 6), { team: [3, 196], sets: { 3: { level: 40 } }, active: 196 });
  assert.deepEqual(removeMember({ team: [3], sets: {}, active: 3 }, 3), { team: [], sets: {}, active: null });
});

test('edits to a trainer’s Pokémon change its numbers, and resetting restores the game data', () => {
  const calc = loadCalc(calcData);
  const falkner = battleData.trainers.find(t => t[0] === 20);
  const staraptor = trainerMon(falkner[7][0]);
  assert.equal(staraptor.id, 398);
  const base = calc.fromTrainerMon(staraptor);
  const obsolete = { nature: CAVEATS.natureGenerated, moves: CAVEATS.levelUpMovesMissing };
  const me = resolveSet(dex, 3, { level: 80 }, { level: 80 }).calc;
  const damage = (set, move) => calc.calculateMatchup(set, me, { gameType: 'Singles' }).moves.find(m => m.name === move);
  const banded = damage(applyFoeEdit(base, null, obsolete), 'Brave Bird');
  assert.equal(base.itemId, ITEM['Choice Band']);
  // No item: Brave Bird does less.
  const plain = damage(applyFoeEdit(base, { item: 0 }, obsolete), 'Brave Bird');
  assert.ok(plain.maxDamage < banded.maxDamage, `${plain.maxDamage} < ${banded.maxDamage}`);
  // Other moves: the matchup lists them.
  const moved = applyFoeEdit(base, { moves: [MOVE['Earthquake'], MOVE['Brave Bird']] }, obsolete);
  assert.deepEqual(calc.calculateMatchup(moved, me, {}).moves.map(m => m.name), ['Earthquake', 'Brave Bird']);
  // Condition and level are edits too; the base set itself never changes.
  const hurt = applyFoeEdit(base, { level: 50, hp: 40, status: 'brn', boosts: { atk: 2 } }, obsolete);
  assert.deepEqual([hurt.level, hurt.curHPPercent, hurt.status, hurt.boosts], [50, 40, 'brn', { atk: 2 }]);
  assert.equal(base.level, 80);
  // Reset (no edit) gives the game data back, with a healthy, unboosted Pokémon.
  const reset = applyFoeEdit(base, null, obsolete);
  assert.deepEqual({ ...reset, curHPPercent: undefined, status: undefined, boosts: undefined }, { ...base, curHPPercent: undefined, status: undefined, boosts: undefined });
  assert.equal(damage(reset, 'Brave Bird').maxDamage, banded.maxDamage);
  // An edited nature is no longer "generated by the game".
  const generated = calc.fromTrainerMon({ ...staraptor, nature: null });
  assert.ok(generated.caveats.includes(CAVEATS.natureGenerated));
  assert.ok(!applyFoeEdit(generated, { nature: 'Adamant' }, obsolete).caveats.includes(CAVEATS.natureGenerated));
  // Fields set back to the game's value are dropped; nothing left means no edit.
  assert.equal(cleanFoeEdit(base, { item: base.itemId, level: 80, moves: [...base.moveIds], evs: { hp: base.evs.hp }, hp: 100, status: '', boosts: { atk: 0 } }), null);
  assert.deepEqual(cleanFoeEdit(base, { item: 0, level: 80, evs: { atk: base.evs.atk + 4, hp: base.evs.hp } }), { item: 0, evs: { atk: base.evs.atk + 4 } });
});

test('links between the two calculator pages carry only the opponent', () => {
  assert.equal(opponentHash(null), '#battle=');
  assert.equal(opponentHash({ trainer: 20 }), '#battle=20');
  assert.equal(opponentHash({ species: 6, set: { level: 30 } }), '#battle=free&foe=6.L30');
  assert.deepEqual(parseStateHash(opponentHash({ trainer: 20 }), known), { team: null, sets: null, battle: true, opponent: { trainer: 20 } }, 'no team: the saved one is used');
});
