/**
 * Battle check sets: the game-data index ("dex"), default sets and Showdown text import/export.
 * Loaded with Battle check only. Saved sets hold only the fields a player changed (team-builder-state.mjs);
 * `resolveSet` fills in the defaults:
 *   level: the opponent's highest level (50 without an opponent) · nature: Hardy (neutral) · ability: the
 *   species' first · item: none · IVs 31 · EVs 0 · moves: "suggested moves" (see suggestedMoves).
 */
import { STATS, BOOST_STATS, STATUSES, NATURES, NATURE_NAMES, sanitizeSet } from './team-builder-state.mjs';

export { NATURES, NATURE_NAMES };
export const STAT_LABELS = { hp: 'HP', atk: 'Atk', def: 'Def', spa: 'SpA', spd: 'SpD', spe: 'Spe' };
export const DEFAULT_LEVEL = 50;

/** Lower-case letters and digits only: "Farfetch’d", "farfetchd" and "Farfetch'd" match. */
export const normalizeName = text => String(text ?? '').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^a-z0-9]/g, '');

const REGIONAL = { Alolan: 'Alola', Galarian: 'Galar', Hisuian: 'Hisui', Paldean: 'Paldea' };
/** Showdown spellings of the hack's form names ("Alolan Raichu" → "Raichu-Alola", "Mega Charizard X" → "Charizard-Mega-X"). */
export function showdownAliases(name, baseNames) {
  const out = new Set([name]);
  let m;
  if ((m = /^(Alolan|Galarian|Hisuian|Paldean) (.+)$/.exec(name))) out.add(`${m[2]}-${REGIONAL[m[1]]}`);
  if ((m = /^Mega (.+?)(?: ([XY]))?$/.exec(name))) out.add(`${m[1]}-Mega${m[2] ? `-${m[2]}` : ''}`);
  if ((m = /^Primal (.+)$/.exec(name))) out.add(`${m[1]}-Primal`);
  if ((m = /^(.+?) \((.+?)\)$/.exec(name))) {
    const words = m[2].replace(/\b(Forme?|Mode|Cloak|Pattern|Flower|Trim|Style|Core|Color|type)\b/g, '').trim();
    out.add(`${m[1]}-${words}`);
  }
  if ((m = /^(\S+) (\S+)$/.exec(name)) && baseNames.has(m[2]) && !REGIONAL[m[1]]) out.add(`${m[2]}-${m[1]}`);
  if ((m = /^(\S+) (\S+)$/.exec(name)) && baseNames.has(m[1])) out.add(`${m[1]}-${m[2]}`);
  return [...out];
}

/** Indexes the lazily loaded calc-data.json and battle-data.json. */
export function createDex(calcData, battleData) {
  const species = new Map(calcData.species.map(([id, name, baseId, types, stats, abilityIds, hiddenAbilityId]) =>
    [id, { id, name, baseId, types, stats, abilityIds, hiddenAbilityId }]));
  const moves = new Map(calcData.moves.map(([id, name, type, cat, power, priority, , , , hits]) =>
    [id, { id, name, type, cat: cat === 'P' ? 'Physical' : cat === 'S' ? 'Special' : 'Status', power, priority, hits: hits || null }]));
  const abilities = new Map(calcData.abilities.map(([id, name]) => [id, { id, name }]));
  const items = new Map(calcData.items.filter(([, name]) => name && !/^\?+$/.test(name)).map(([id, name]) => [id, { id, name }]));
  const learnsets = battleData?.learnsets ?? {};
  const baseNames = new Set([...species.values()].filter(s => s.id === s.baseId).map(s => s.name));
  const index = (map, aliases = record => [record.name], all = false) => {
    const out = new Map();
    for (const record of map.values()) for (const alias of aliases(record)) {
      const key = normalizeName(alias);
      if (!key) continue;
      if (all) out.set(key, [...(out.get(key) ?? []), record.id]);
      else if (!out.has(key)) out.set(key, record.id);
    }
    return out;
  };
  return {
    species, moves, abilities, items, learnsets, evolutions: battleData?.evolutions ?? {},
    speciesByName: index(species, record => showdownAliases(record.name, baseNames), true),
    moveByName: index(moves), abilityByName: index(abilities), itemByName: index(items),
  };
}

/** Level-up moves ([level, moveId] pairs) and other learnable moves; forms without a list use their base species'. */
export function learnset(dex, speciesId) {
  const own = dex.learnsets[speciesId];
  const base = dex.species.get(speciesId)?.baseId;
  const entry = own ?? (base != null ? dex.learnsets[base] : null);
  if (!entry) return { levelUp: [], other: [] };
  const levelUp = [];
  for (let i = 0; i + 1 < entry[0].length; i += 2) levelUp.push([entry[0][i], entry[0][i + 1]]);
  return { levelUp, other: entry[1] };
}

export function learnableMoves(dex, speciesId) {
  const { levelUp, other } = learnset(dex, speciesId);
  return [...new Set([...levelUp.map(([, id]) => id), ...other])].filter(id => dex.moves.has(id));
}

/** The species and its pre-evolutions, nearest first (from battle-data's `evolutions`). */
export function evolutionChain(dex, speciesId) {
  const chain = [];
  for (let id = speciesId; id != null && !chain.includes(id); id = dex.evolutions[id]?.[0]) chain.push(id);
  return chain;
}

/**
 * The lowest level at which a species can normally be reached by evolving: the highest level step on its chain
 * ({level, exact: false} when a step has no level, e.g. a trade or an item). Null for a species that does not
 * evolve from anything, or when no step has a level.
 */
export function evolutionLevel(dex, speciesId) {
  let level = 0, exact = true, evolved = false;
  for (const id of evolutionChain(dex, speciesId).slice(0, -1)) {
    const step = dex.evolutions[id];
    evolved = true;
    if (step[1] > 0) level = Math.max(level, step[1]); else exact = false;
  }
  return evolved && level > 0 ? { level, exact } : null;
}

// Moves with a big drawback (recharge, charge turn, fainting, only on the first turn, needing a condition):
// suggested only when nothing comparable is available.
const DRAWBACK = new Set(['Hyper Beam', 'Giga Impact', 'Blast Burn', 'Frenzy Plant', 'Hydro Cannon', 'Rock Wrecker',
  'Roar of Time', 'Prismatic Laser', 'Eternabeam', 'Meteor Assault', 'Explosion', 'Self-Destruct', 'Misty Explosion',
  'Final Gambit', 'Solar Beam', 'Solar Blade', 'Sky Attack', 'Skull Bash', 'Razor Wind', 'Freeze Shock', 'Ice Burn',
  'Meteor Beam', 'Future Sight', 'Doom Desire', 'Fake Out', 'First Impression', 'Dream Eater', 'Focus Punch',
  'Shell Trap', 'Snore', 'Belch', 'Last Resort', 'Synchronoise', 'Steel Beam', 'Mind Blown', 'Burn Up',
  'Double Shock', 'Struggle', 'Hyperspace Fury', 'Head Smash']);
// Variable-power moves with a predictable value: Return at maximum friendship.
const FIXED_POWER = { Return: 102 };

const movePower = move => FIXED_POWER[move.name] ?? (move.power > 0 ? move.power : 0);
function moveScore(move, types) {
  const hits = Array.isArray(move.hits) ? (move.hits[0] === move.hits[1] ? move.hits[0] : 3) : 1;
  return movePower(move) * hits * (types.includes(move.type) ? 1.5 : 1) * (DRAWBACK.has(move.name) ? 0.5 : 1);
}
/** Up to `max` damaging moves, strongest first (same-type moves get ×1.5), one per type before any repeats. */
function strongest(dex, ids, types, max) {
  const ranked = [...new Set(ids)].map(id => dex.moves.get(id)).filter(move => move && move.cat !== 'Status' && movePower(move) > 0)
    .sort((a, b) => moveScore(b, types) - moveScore(a, types) || a.id - b.id);
  const picked = [];
  for (const move of ranked) if (picked.length < max && !picked.some(p => p.type === move.type)) picked.push(move);
  for (const move of ranked) if (picked.length < max && !picked.includes(move)) picked.push(move);
  return picked.map(move => move.id);
}

/**
 * "Suggested moves" for a player's Pokémon at a level: the strongest damaging moves it can know by then, from
 * its own level-up moves at or below the level (moves learnt on evolving included) and those its
 * pre-evolutions learnt by that level. Same-type moves count ×1.5, and different types are preferred. With
 * fewer than two such attacks, the strongest moves it can learn otherwise (TM, tutor, egg) fill the free slots.
 * A species without any damaging move keeps its most recent level-up moves; Ditto keeps Transform.
 */
export function suggestedMoves(dex, speciesId, level) {
  const types = dex.species.get(speciesId)?.types ?? [];
  const levelUp = [];
  for (const id of evolutionChain(dex, speciesId)) {
    for (const [lv, move] of learnset(dex, id).levelUp) if (lv <= level && dex.moves.has(move)) levelUp.push(move);
  }
  // Ditto: Transform is the whole point; a TM attack would misrepresent it.
  if (levelUp.length && levelUp.every(id => dex.moves.get(id).name === 'Transform')) return [levelUp[0]];
  let moves = strongest(dex, levelUp, types, 4);
  if (moves.length < 2) moves = [...moves, ...strongest(dex, learnableMoves(dex, speciesId).filter(id => !moves.includes(id)), types, 4 - moves.length)];
  if (moves.length) return moves;
  return [...new Set(learnset(dex, speciesId).levelUp.filter(([lv]) => lv <= level).map(([, id]) => id).reverse())]
    .filter(id => dex.moves.has(id)).slice(0, 4);
}

/**
 * The full set used for a calculation, plus what was filled in by default.
 * `context.level`: the default level (the opponent's highest), `context.levelSource`: text for the UI.
 */
export function resolveSet(dex, speciesId, saved, { level: contextLevel = DEFAULT_LEVEL } = {}) {
  const set = sanitizeSet(saved) ?? {};
  const mon = dex.species.get(speciesId);
  const level = set.level ?? contextLevel;
  const abilityIds = mon?.abilityIds ?? [];
  const abilityChoices = [...new Set([...abilityIds, mon?.hiddenAbilityId].filter(id => id > 0))];
  const ability = set.ability && abilityChoices.includes(set.ability) ? set.ability : abilityIds[0] ?? null;
  const moves = set.moves?.filter(id => dex.moves.has(id));
  const suggested = !moves?.length;
  return {
    calc: {
      speciesId, level, nature: set.nature ?? null, abilityId: ability,
      itemId: set.item && dex.items.has(set.item) ? set.item : null,
      moveIds: suggested ? suggestedMoves(dex, speciesId, level) : moves,
      ivs: Object.fromEntries(STATS.map(stat => [stat, set.ivs?.[stat] ?? 31])),
      evs: Object.fromEntries(STATS.map(stat => [stat, set.evs?.[stat] ?? 0])),
      boosts: Object.fromEntries(BOOST_STATS.map(stat => [stat, set.boosts?.[stat] ?? 0])),
      status: set.status ?? '',
      curHPPercent: set.hp ?? 100,
    },
    autoLevel: set.level == null,
    suggestedMoves: suggested,
    abilityChoices,
  };
}

/** Drops fields equal to the defaults so saved sets and links stay small. */
export function compactSet(dex, speciesId, set) {
  const s = sanitizeSet(set);
  if (!s) return null;
  const mon = dex.species.get(speciesId);
  if (s.ability && s.ability === mon?.abilityIds?.[0]) delete s.ability;
  if (s.moves && !s.moves.length) delete s.moves;
  return Object.keys(s).length ? s : null;
}

// ---------------------------------------------------------------- Showdown text
/** One set as Showdown text, using the hack's English names. */
export function exportShowdown(dex, speciesId, resolved) {
  const set = resolved.calc;
  const name = dex.species.get(speciesId)?.name ?? `Pokémon #${speciesId}`;
  const item = set.itemId ? dex.items.get(set.itemId)?.name : null;
  const lines = [`${name}${item ? ` @ ${item}` : ''}`];
  if (set.abilityId) lines.push(`Ability: ${dex.abilities.get(set.abilityId)?.name ?? ''}`);
  lines.push(`Level: ${set.level}`);
  const evs = STATS.filter(stat => set.evs[stat]).map(stat => `${set.evs[stat]} ${STAT_LABELS[stat]}`);
  if (evs.length) lines.push(`EVs: ${evs.join(' / ')}`);
  lines.push(`${set.nature ?? 'Hardy'} Nature`);
  const ivs = STATS.filter(stat => set.ivs[stat] !== 31).map(stat => `${set.ivs[stat]} ${STAT_LABELS[stat]}`);
  if (ivs.length) lines.push(`IVs: ${ivs.join(' / ')}`);
  for (const id of set.moveIds) lines.push(`- ${dex.moves.get(id)?.name ?? `Move #${id}`}`);
  return lines.join('\n');
}

const STAT_BY_LABEL = { hp: 'hp', atk: 'atk', attack: 'atk', def: 'def', defense: 'def', spa: 'spa', spatk: 'spa', spd: 'spd', spdef: 'spd', spe: 'spe', speed: 'spe' };
export const EV_TOTAL = 510;
function parseSpread(text, max, errors, label) {
  const out = {};
  for (const part of text.split('/')) {
    const m = /^\s*(\d+)\s+(.+?)\s*$/.exec(part);
    const stat = m && STAT_BY_LABEL[normalizeName(m[2])];
    if (!m || !stat || Number(m[1]) > max) { errors.push(`${label}: couldn’t read “${part.trim()}”.`); continue; }
    out[stat] = Number(m[1]);
  }
  return out;
}

/**
 * Parses Showdown text (one or more sets separated by blank lines). `canUse(id)` picks between records that
 * share a name (e.g. a form listed twice). Returns {sets: [{speciesId, set, name}],
 * errors, warnings}. Unknown names are errors, never skipped silently. A set without "Level:" keeps the
 * automatic level (the opponent's highest).
 */
export function importShowdown(dex, text, { canUse = () => true } = {}) {
  const errors = [], warnings = [], sets = [];
  const blocks = String(text ?? '').replace(/\r/g, '').split(/\n\s*\n/).map(block => block.trim()).filter(Boolean);
  if (!blocks.length) errors.push('Paste a set in Showdown format first.');
  for (const block of blocks) {
    const lines = block.split('\n').map(line => line.trim()).filter(Boolean);
    let head = lines[0];
    let itemName = null;
    const at = head.lastIndexOf(' @ ');
    if (at >= 0) { itemName = head.slice(at + 3).trim(); head = head.slice(0, at).trim(); }
    head = head.replace(/\s*\((M|F)\)\s*$/, '');
    const nick = /^(.*?)\s*\(([^()]+)\)\s*$/.exec(head);
    const speciesName = nick ? nick[2] : head;
    const ids = dex.speciesByName.get(normalizeName(speciesName)) ?? [];
    const speciesId = ids.find(canUse) ?? ids[0];
    if (!speciesId) { errors.push(`Unknown Pokémon “${speciesName}”. Use the name shown in this guide’s Pokédex.`); continue; }
    const name = dex.species.get(speciesId).name;
    const set = {};
    if (itemName) {
      const item = dex.itemByName.get(normalizeName(itemName));
      if (item) set.item = item; else errors.push(`${name}: unknown item “${itemName}”.`);
    }
    const moves = [];
    for (const line of lines.slice(1)) {
      let m;
      if ((m = /^Ability:\s*(.+)$/i.exec(line))) {
        const ability = dex.abilityByName.get(normalizeName(m[1]));
        const mon = dex.species.get(speciesId);
        if (!ability) errors.push(`${name}: unknown Ability “${m[1]}”.`);
        else if (![...mon.abilityIds, mon.hiddenAbilityId].includes(ability)) errors.push(`${name} can’t have the Ability ${dex.abilities.get(ability).name} in this game.`);
        else set.ability = ability;
      } else if ((m = /^Level:\s*(\d+)$/i.exec(line))) {
        const level = Number(m[1]);
        if (level >= 1 && level <= 100) set.level = level; else errors.push(`${name}: level must be 1–100.`);
      } else if ((m = /^EVs:\s*(.+)$/i.exec(line))) {
        set.evs = parseSpread(m[1], 255, errors, `${name} EVs`);
        const total = Object.values(set.evs).reduce((sum, v) => sum + v, 0);
        if (total > EV_TOTAL) errors.push(`${name}: EVs add up to ${total}; the most a Pokémon can have is ${EV_TOTAL}.`);
      }
      else if ((m = /^IVs:\s*(.+)$/i.exec(line))) set.ivs = parseSpread(m[1], 31, errors, `${name} IVs`);
      else if ((m = /^(\w+)\s+Nature$/i.exec(line))) {
        const nature = NATURE_NAMES.find(n => n.toLowerCase() === m[1].toLowerCase());
        if (nature) set.nature = nature; else errors.push(`${name}: unknown nature “${m[1]}”.`);
      } else if ((m = /^[-~]\s*(.+)$/.exec(line))) {
        const moveName = m[1].replace(/\s*\[.*\]\s*$/, '').replace(/^Hidden Power\s+\w+$/i, 'Hidden Power');
        const move = dex.moveByName.get(normalizeName(moveName));
        if (move && moveName === 'Hidden Power' && moveName !== m[1].trim()) {
          warnings.push(`${name}: Hidden Power’s type comes from the IVs, so “${m[1].trim()}” is read as plain Hidden Power. Set the IVs to choose its type.`);
        }
        if (!move) { errors.push(`${name}: unknown move “${m[1]}”.`); continue; }
        if (moves.length === 4) { errors.push(`${name}: more than four moves.`); continue; }
        if (!moves.includes(move)) moves.push(move);
        const learnable = learnableMoves(dex, speciesId);
        if (learnable.length && !learnable.includes(move)) warnings.push(`${name} can’t learn ${dex.moves.get(move).name} in this game; kept for the calculation.`);
      } else if (/^(Shiny|Happiness|Tera Type|Gigantamax|Dynamax Level|Hidden Power|Pokeball|Gender):/i.test(line)) {
        warnings.push(`${name}: “${line}” is not used here.`);
      } else errors.push(`${name}: couldn’t read “${line}”.`);
    }
    if (moves.length) set.moves = moves;
    sets.push({ speciesId, name, set: compactSet(dex, speciesId, set) ?? {} });
  }
  return { sets, errors, warnings };
}

export { STATS, BOOST_STATS, STATUSES };
