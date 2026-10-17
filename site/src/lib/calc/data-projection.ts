// Builds the compact calc-data payload (served at /team-builder/calc-data.json) from the site's game data.
// Build time only: the endpoint passes species/moves/abilities/items/trainers from src/data/*.json.
// Only fields the damage engine needs are kept. Shapes (arrays keep the payload small):
//   species:   [id, name, baseId, types, [hp,atk,def,spa,spd,spe], abilityIds, hiddenAbilityId, flags, gender]
//              flags bit0 = can evolve (Eviolite); gender 'M'|'F'|'N'|'' (either). No weight: battles in this
//              hack always use the minimum weight (work/notes/damage_calc_data.md §1).
//   moves:     [id, name, type, cat, power, priority, target, flags, critStage, hits, drain, extra]
//              cat 'P'|'S'|'X'; power null = "var."; target 0 single, 1 all adjacent, 2 all adjacent foes, 3 self/side/field;
//              flags bit0 contact, 1 punch, 2 sound, 3 bite, 4 slicing, 5 ballistic; hits 0 or [min,max];
//              drain % (negative = recoil); extra bit0 = secondary effect (Sheer Force), bits1-3 = own Atk/SpA drop stages
//   abilities: [id, name]          items: [id, name]
//   forms:     [baseId, resultId, itemId, onlyNatures|null, exceptNatures|null]
//   defaultMoves: {"speciesId:level": moveIds} for trainer Pokémon whose moves come from their level-up set

export const CALC_DATA_VERSION = 1;

type Json = any;

const FLAG_BITS: Array<[number, number]> = [[0, 0], [7, 1], [8, 2], [29, 3], [34, 4], [30, 5]];
const TARGETS: Record<number, number> = {4: 1, 5: 2, 1: 3, 2: 3, 6: 3, 7: 3, 8: 3, 10: 3, 11: 3, 12: 3, 13: 0};

/** Straighten curly apostrophes so names match the names the mechanics code tests against. */
export function calcName(name: string) {
  return name.replace(/[‘’]/g, '\'');
}

export function moveSecondaries(effects: Json) {
  const q = effects?.quality ?? 0;
  const changes: Json[] = effects?.stat_changes ?? [];
  return (effects?.flinch_chance ?? 0) > 0 || q === 4 || q === 6 ||
    (q === 7 && changes.some(c => c.chance > 0 && c.chance < 100));
}

/** Stages the user's own Atk (category P) or SpA (S) drops after the move (Draco Meteor, Superpower…). */
export function moveDropsStats(move: Json) {
  const effects = move.effects ?? {};
  if (effects.quality !== 7) return 0;
  const stat = move.cat === 'Special' ? 3 : 1;
  const change = (effects.stat_changes ?? []).find((c: Json) => c.stat === stat && c.stages < 0 && c.chance >= 100);
  return change ? -change.stages : 0;
}

function genderCode(text: string | null | undefined) {
  if (text === 'genderless') return 'N';
  if (text === 'always female') return 'F';
  if (text === 'always male') return 'M';
  return '';
}

/** Gen 4 default moveset: the last four distinct level-up moves learnt at or below the level. */
export function defaultLevelUpMoves(levelup: Array<[number, number]>, level: number) {
  const moves: number[] = [];
  for (const [lv, id] of levelup ?? []) {
    if (lv > level) continue;
    if (moves.includes(id)) continue;
    if (moves.length === 4) moves.shift();
    moves.push(id);
  }
  return moves;
}

function formNatures(condition: string): [string[] | null, string[] | null] {
  const list = (s: string) => s.split(/,\s*|\s+or\s+/).map(x => x.trim()).filter(Boolean);
  const except = /Any nature except ([A-Za-z ,]+?)\./.exec(condition);
  if (except) return [null, list(except[1])];
  const only = /^([A-Za-z ,]+?) nature\./.exec(condition);
  if (only) return [list(only[1]), null];
  return [null, null];
}

export function buildCalcData({species, moves, abilities, items, trainers = [], formChanges = []}: {
  species: Json[]; moves: Json[]; abilities: Json[]; items: Json[]; trainers?: Json[]; formChanges?: Json[];
}) {
  const byId = new Map(species.map(s => [s.id, s]));
  const defaultMoves: Record<string, number[]> = {};
  for (const trainer of trainers) {
    for (const mon of trainer.team ?? []) {
      if (mon.moveIds?.length) continue;
      const key = `${mon.id}:${mon.level}`;
      if (!defaultMoves[key]) defaultMoves[key] = defaultLevelUpMoves(byId.get(mon.id)?.levelup ?? [], mon.level);
    }
  }
  return {
    v: CALC_DATA_VERSION,
    species: species.map(s => {
      const abilityIds = [...new Set<number>((s.abilityIds ?? []).filter((id: number) => id > 0))];
      return [s.id, s.name, s.baseSpeciesId ?? s.id, s.types, s.stats, abilityIds, s.hiddenAbilityId || 0,
        (s.evoTo?.length ? 1 : 0), genderCode(s.gender)];
    }),
    moves: moves.map(m => {
      const bits = new Set<number>(m.flagBits ?? []);
      const flags = FLAG_BITS.reduce((acc, [bit, shift]) => acc | (bits.has(bit) ? (1 << shift) : 0), 0);
      const power = m.power === 'var.' ? null : /^\d+$/.test(m.power) ? Number(m.power) : 0;
      const hits = m.effects?.hits && m.effects.hits[0] > 0 ? m.effects.hits : 0;
      const extra = (moveSecondaries(m.effects) ? 1 : 0) | (moveDropsStats(m) << 1);
      return [m.id, calcName(m.name), m.type, m.cat === 'Physical' ? 'P' : m.cat === 'Special' ? 'S' : 'X',
        power, m.priority ?? 0, TARGETS[m.targetId] ?? 0, flags, m.effects?.crit_stage ?? 0, hits,
        m.effects?.drain ?? 0, extra];
    }),
    abilities: abilities.map(a => [a.id, a.name]),
    items: items.filter(i => i.pocket !== 'Key Items' && i.pocket !== 'TMs & HMs').map(i => [i.id, i.name]),
    forms: formChanges.map(f => [f.base, f.result, f.item, ...formNatures(f.condition ?? '')]),
    defaultMoves,
  };
}

export type CalcData = ReturnType<typeof buildCalcData>;
