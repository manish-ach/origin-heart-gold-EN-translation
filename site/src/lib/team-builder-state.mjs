/**
 * Planner state v2: the team (record IDs), an optional battle set per member and the opponent chosen in
 * Battle check. Loaded on every visit, so it only checks the shape of saved values; the Battle check
 * module validates ids against the game data when it opens.
 *
 * Storage: `ohg-team-builder-v2` = {v: 2, team, sets, opponent}. The v1 key (a bare id array) is still read
 * when no v2 state exists and is kept up to date, so older pages keep working.
 * Link: `#team=3,94&sets=3.L50.NModest_94.I239&battle=253` (`battle=free&foe=25.L30` for a custom opponent).
 * Old `#team=` links load unchanged.
 */
import { TEAM_SIZE, STORAGE_KEY, sanitizeTeam } from './team-builder.mjs';

export const STORAGE_KEY_V2 = 'ohg-team-builder-v2';
export const STATS = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
export const BOOST_STATS = ['atk', 'def', 'spa', 'spd', 'spe'];
export const STATUSES = ['brn', 'par', 'psn', 'tox', 'slp', 'frz'];
export const NATURES = [
  ['Adamant', 'atk', 'spa'], ['Bashful'], ['Bold', 'def', 'atk'], ['Brave', 'atk', 'spe'], ['Calm', 'spd', 'atk'],
  ['Careful', 'spd', 'spa'], ['Docile'], ['Gentle', 'spd', 'def'], ['Hardy'], ['Hasty', 'spe', 'def'],
  ['Impish', 'def', 'spa'], ['Jolly', 'spe', 'spa'], ['Lax', 'def', 'spd'], ['Lonely', 'atk', 'def'], ['Mild', 'spa', 'def'],
  ['Modest', 'spa', 'atk'], ['Naive', 'spe', 'spd'], ['Naughty', 'atk', 'spd'], ['Quiet', 'spa', 'spe'], ['Quirky'],
  ['Rash', 'spa', 'spd'], ['Relaxed', 'def', 'spe'], ['Sassy', 'spd', 'spe'], ['Serious'], ['Timid', 'spe', 'atk'],
];
export const NATURE_NAMES = NATURES.map(n => n[0]);
const int = (value, min, max) => Number.isInteger(value) && value >= min && value <= max;

/** Keeps only well-formed, non-default fields. Returns null for an empty set. */
export function sanitizeSet(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const set = {};
  if (int(value.level, 1, 100)) set.level = value.level;
  if (NATURE_NAMES.includes(value.nature) && value.nature !== 'Hardy') set.nature = value.nature;
  if (int(value.ability, 1, 9999)) set.ability = value.ability;
  if (int(value.item, 1, 9999)) set.item = value.item;
  if (Array.isArray(value.moves)) {
    const moves = value.moves.filter(id => int(id, 1, 9999)).slice(0, 4);
    if (moves.length) set.moves = moves;
  }
  for (const [key, max, fallback] of [['ivs', 31, 31], ['evs', 255, 0]]) {
    if (!value[key] || typeof value[key] !== 'object') continue;
    const stats = {};
    for (const stat of STATS) if (int(value[key][stat], 0, max) && value[key][stat] !== fallback) stats[stat] = value[key][stat];
    if (Object.keys(stats).length) set[key] = stats;
  }
  if (int(value.hp, 1, 99)) set.hp = value.hp;
  if (STATUSES.includes(value.status)) set.status = value.status;
  if (value.boosts && typeof value.boosts === 'object') {
    const boosts = {};
    for (const stat of BOOST_STATS) if (int(value.boosts[stat], -6, 6) && value.boosts[stat] !== 0) boosts[stat] = value.boosts[stat];
    if (Object.keys(boosts).length) set.boosts = boosts;
  }
  return Object.keys(set).length ? set : null;
}

export function sanitizeSets(value, team) {
  const sets = {};
  if (!value || typeof value !== 'object') return sets;
  for (const id of team) {
    const set = sanitizeSet(value[id]);
    if (set) sets[id] = set;
  }
  return sets;
}

export function sanitizeOpponent(value) {
  if (!value || typeof value !== 'object') return null;
  if (int(value.trainer, 0, 99999)) return { trainer: value.trainer };
  if (int(value.species, 1, 99999)) {
    const set = sanitizeSet(value.set);
    return set ? { species: value.species, set } : { species: value.species };
  }
  return null;
}

/** Reads v2, else migrates v1. Throws when storage itself is unavailable. */
export function loadStoredState(storage, knownIds) {
  const raw = storage.getItem(STORAGE_KEY_V2);
  if (raw != null) {
    try {
      const value = JSON.parse(raw);
      if (value && value.v === 2) {
        const team = sanitizeTeam(value.team, knownIds);
        return { team, sets: sanitizeSets(value.sets, team), opponent: sanitizeOpponent(value.opponent) };
      }
    } catch { /* fall back to v1 */ }
  }
  let team = [];
  try { team = sanitizeTeam(JSON.parse(storage.getItem(STORAGE_KEY) ?? '[]'), knownIds); } catch { team = []; }
  return { team, sets: {}, opponent: null };
}

export function saveStoredState(storage, { team, sets, opponent }) {
  storage.setItem(STORAGE_KEY_V2, JSON.stringify({ v: 2, team, sets: sanitizeSets(sets, team), opponent: sanitizeOpponent(opponent) }));
  storage.setItem(STORAGE_KEY, JSON.stringify(team));
}

// ------------------------------------------------------------------ compact link encoding
const boostChar = n => String.fromCharCode(103 + n); // a = -6, g = 0, m = +6
const charBoost = c => c.charCodeAt(0) - 103;

/** One set as dot-separated fields; only fields that differ from the defaults are written. */
export function encodeSet(set) {
  const s = sanitizeSet(set);
  if (!s) return '';
  const out = [];
  if (s.level) out.push(`L${s.level}`);
  if (s.nature) out.push(`N${s.nature}`);
  if (s.ability) out.push(`A${s.ability}`);
  if (s.item) out.push(`I${s.item}`);
  if (s.moves) out.push(`M${s.moves.join('-')}`);
  if (s.ivs) out.push(`V${STATS.map(stat => s.ivs[stat] ?? 31).join('-')}`);
  if (s.evs) out.push(`E${STATS.map(stat => s.evs[stat] ?? 0).join('-')}`);
  if (s.hp != null) out.push(`H${s.hp}`);
  if (s.status) out.push(`S${s.status}`);
  if (s.boosts) out.push(`B${BOOST_STATS.map(stat => boostChar(s.boosts[stat] ?? 0)).join('')}`);
  return out.join('.');
}

export function decodeSet(text) {
  const set = {};
  for (const field of String(text ?? '').split('.')) {
    const key = field[0], value = field.slice(1);
    const nums = () => value.split('-').map(Number);
    if (key === 'L') set.level = Number(value);
    else if (key === 'N') set.nature = value;
    else if (key === 'A') set.ability = Number(value);
    else if (key === 'I') set.item = Number(value);
    else if (key === 'M') set.moves = nums();
    else if (key === 'V' || key === 'E') {
      const list = nums();
      if (list.length === 6) set[key === 'V' ? 'ivs' : 'evs'] = Object.fromEntries(STATS.map((stat, i) => [stat, list[i]]));
    } else if (key === 'H') set.hp = Number(value);
    else if (key === 'S') set.status = value;
    else if (key === 'B' && value.length === 5) set.boosts = Object.fromEntries(BOOST_STATS.map((stat, i) => [stat, charBoost(value[i])]));
  }
  return sanitizeSet(set);
}

export function encodeSets(team, sets) {
  return team.map(id => {
    const text = encodeSet(sets?.[id]);
    return text ? `${id}.${text}` : '';
  }).filter(Boolean).join('_');
}

export function decodeSets(text, team) {
  const sets = {};
  for (const entry of String(text ?? '').split('_')) {
    const dot = entry.indexOf('.');
    if (dot < 1) continue;
    const id = Number(entry.slice(0, dot));
    if (!team.includes(id)) continue;
    const set = decodeSet(entry.slice(dot + 1));
    if (set) sets[id] = set;
  }
  return sets;
}

/** Hash for the current state. `battle` adds the opponent (used while Battle check is open and for sharing). */
export function stateHash({ team, sets = {}, opponent = null }, { battle = false } = {}) {
  let hash = `#team=${team.join(',')}`;
  const encoded = encodeSets(team, sets);
  if (encoded) hash += `&sets=${encoded}`;
  if (battle) {
    const foe = sanitizeOpponent(opponent);
    if (foe?.trainer != null) hash += `&battle=${foe.trainer}`;
    else if (foe?.species) {
      const set = encodeSet(foe.set);
      hash += `&battle=free&foe=${foe.species}${set ? `.${set}` : ''}`;
    } else hash += '&battle=';
  }
  return hash;
}

/**
 * Parses a link. `team` is null when the link has no team (keep the saved one); `battle` is true when the
 * link asks for Battle check, and `opponent` is the opponent it names (undefined = keep the saved one).
 */
export function parseStateHash(hash, knownIds) {
  const params = new URLSearchParams(String(hash ?? '').replace(/^#/, ''));
  let team = null, sets = null;
  if (params.has('team')) {
    const raw = params.get('team');
    team = sanitizeTeam(raw.split(',').filter(id => /^\d+$/.test(id)).map(Number), knownIds);
    // A damaged link (nothing readable in a non-empty team) keeps the saved team instead of emptying it.
    if (!team.length && raw.trim() !== '') team = null;
    else sets = decodeSets(params.get('sets'), team);
  }
  const battle = params.has('battle');
  let opponent;
  if (battle) {
    const value = params.get('battle');
    if (/^\d+$/.test(value)) opponent = { trainer: Number(value) };
    else if (value === 'free' && params.has('foe')) {
      const [species, ...rest] = params.get('foe').split('.');
      opponent = /^\d+$/.test(species) ? sanitizeOpponent({ species: Number(species), set: decodeSet(rest.join('.')) }) : undefined;
    }
  }
  return { team, sets, battle, opponent };
}

export { TEAM_SIZE };
