/**
 * Build-time projection for the damage calculator (served at /team-builder/battle-data.json and
 * fetched only when the calculator opens; the damage engine's own data is calc-data.json).
 *
 *   trainers: [id, cls, name, double 0|1, flags, area, places, team] in play order
 *             flags: 1 = only your partner, 2 = scene can never trigger, 4 = no known battle location,
 *                    8 = rematch or later battle (listed after the route, by level)
 *             places: [[map, how, conditions]] (distinct battles, player-facing text from trainers.json)
 *             team: [speciesId, level, abilityId, itemId, moveIds, nature, ivs, hpIvs, evs, gender, friendship]
 *   learnsets: {speciesId: [levelUp (flat [level, moveId, ...]), otherMoveIds (TM, tutor, egg)]}
 *   evolutions: {speciesId: [preEvolutionId, level]}: the species it evolves from (the first listed method) and
 *             the level of that step (0 when the method is not a level)
 *
 * Play order: places follow the quest guide's route order (`areas.json` rank; the unranked Sevii Island areas
 * sort right after Cinnabar Island, where the quest guide covers them). Each place has a typical level: the
 * median highest level of the teams that battle only there (with fewer than 3 such teams, the previous place's
 * level). A team is listed under the first place where it battles you whose typical level it does not exceed
 * by more than levelMargin (max(10 levels, 35 %)); a Gym challenge always stays at its Gym. Teams that fit none
 * of their places (rematches, return visits), Gym Leader teams stronger than that leader's Gym challenge (the
 * quest guide's "Other Gym Leader battles") and teams that only battle after the final Hall of Fame form a later
 * "Rematches and later battles" group sorted by level. Within a place, lower-level teams come first, and a Gym Leader's challenge team follows the
 * Gym's trainers of the same level. Teams that only fight beside you, scenes that can never trigger and teams
 * with no known battle location come last.
 *   area: the slug of the place it is listed under (for later battles: its first place; '' for the last group)
 *   areaNames: {slug: name}
 *   mainIds: {record id: main record id} for records whose trainer profile page is another record's (links use it)
 */
import { buildTrainerProfiles, trainerMainIds } from './trainer-encounters.mjs';
export const BATTLE_DATA_VERSION = 2;

const AFTER_CINNABAR = 43.5;
export const LATER = 8;
export const levelMargin = typical => Math.max(10, Math.round(typical * 0.35));

export function playOrder({ trainers, areas, guide = [] }) {
  const rankBySlug = new Map(areas.map(area => {
    const rank = area.rank >= 10000 && area.region === 'kanto' ? AFTER_CINNABAR : area.rank;
    return [area.slug, rank];
  }));
  const rank = slug => rankBySlug.get(slug) ?? 10000;
  const challengeSections = guide.filter(section => /Gym challenges/.test(section.title));
  const gymChallenges = new Set(challengeSections.flatMap(section => section.entries.flatMap(entry => entry.ids)));
  const maxLevel = t => Math.max(0, ...(t.team ?? []).map(m => m.level ?? 0));
  const byId = new Map(trainers.map(t => [t.id, t]));
  // A leader's Gym challenge level ("Brock — Pewter Gym" → Brock); stronger teams of that leader are rematches.
  const leaderName = title => title.split(' — ')[0].trim();
  const challengeLevel = new Map();
  for (const entry of challengeSections.flatMap(section => section.entries)) {
    const levels = entry.ids.map(id => byId.get(id)).filter(Boolean).map(maxLevel);
    if (levels.length) challengeLevel.set(leaderName(entry.title), Math.max(...levels));
  }
  const rematches = new Set();
  for (const entry of guide.filter(section => /Other Gym Leader battles/.test(section.title)).flatMap(section => section.entries)) {
    const level = challengeLevel.get(leaderName(entry.title));
    if (level != null) for (const id of entry.ids) if (byId.get(id) && maxLevel(byId.get(id)) > level) rematches.add(id);
  }
  const inactive = p => p.conds?.length > 0 && p.conds.every(c => c.startsWith('never '));
  const partner = p => p.how?.startsWith('your partner');
  const live = t => (t.places ?? []).filter(p => !inactive(p) && !partner(p));
  const postGame = p => p.conds?.length > 0 && p.conds.every(c => /after the final Hall of Fame/.test(c));

  // Typical level per place, from teams that battle only there.
  const samples = new Map();
  for (const t of trainers) {
    if (!t.team?.some(m => m.id)) continue;
    const places = [...new Set(live(t).map(p => p.area))];
    if (places.length === 1 && places[0]) samples.set(places[0], [...(samples.get(places[0]) ?? []), maxLevel(t)]);
  }
  const typical = new Map();
  let previous = 5;
  for (const slug of [...new Set([...rankBySlug.keys(), ...samples.keys()])].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))) {
    const levels = (samples.get(slug) ?? []).slice().sort((a, b) => a - b);
    if (levels.length >= 3) previous = levels[levels.length >> 1];
    typical.set(slug, previous);
  }

  const flags = t => {
    const places = t.places ?? [];
    return (places.length && places.every(partner) ? 1 : 0) | (places.length && places.every(inactive) ? 2 : 0) | (places.length ? 0 : 4);
  };
  const place = t => {
    const level = maxLevel(t);
    const places = live(t).filter(p => p.area).sort((a, b) => rank(a.area) - rank(b.area));
    if (!places.length) return { r: Infinity, area: '', later: 0 };
    if (places.every(postGame) || rematches.has(t.id)) return { r: rank(places[0].area), area: places[0].area, later: LATER };
    for (const p of places) {
      if (postGame(p)) continue;
      const band = typical.get(p.area);
      if (band == null || gymChallenges.has(t.id) || level <= band + levelMargin(band)) return { r: rank(p.area), area: p.area, later: 0 };
    }
    return { r: rank(places[0].area), area: places[0].area, later: LATER };
  };
  return trainers.map(t => {
    const f = flags(t);
    const where = place(t);
    return { t, f: f | (f & 3 ? 0 : where.later), ...where, g: gymChallenges.has(t.id) ? 1 : 0, l: maxLevel(t) };
  }).sort((a, b) => {
    // Normal route order, then later battles by level, then partners / inactive scenes, then unknown places.
    const section = e => e.f & 3 ? 2 : e.later ? 1 : e.r === Infinity ? 3 : 0;
    // Places sharing a rank (the Sevii Islands) follow their typical level, so each place forms one group.
    const byPlace = (x, y) => x.r - y.r || (typical.get(x.area) ?? 0) - (typical.get(y.area) ?? 0) || x.area.localeCompare(y.area);
    return section(a) - section(b) || (section(a) === 1 ? a.l - b.l || byPlace(a, b) : byPlace(a, b) || a.l - b.l) ||
      a.g - b.g || a.t.id - b.t.id;
  });
}

const LEVEL_STEP = /^Lv (\d+)/;

export function buildBattleData({ trainers, areas, guide = [], species, tms = [] }) {
  const order = playOrder({ trainers, areas, guide }).filter(({ t }) => t.team?.some(m => m.id));
  const used = new Set(order.map(entry => entry.area).filter(Boolean));
  const allTms = [...new Set(tms.map(tm => tm.moveId))];
  const learnsets = {};
  for (const mon of species) {
    const levelUp = (mon.levelup ?? []).flatMap(([level, move]) => [level, move]);
    const tmMoves = mon.tms === 'all' ? allTms : (Array.isArray(mon.tms) ? mon.tms.map(entry => entry[1]) : []);
    const learnt = new Set((mon.levelup ?? []).map(entry => entry[1]));
    const other = [...new Set([...tmMoves, ...(mon.tutors ?? []), ...(mon.egg ?? [])])].filter(id => id > 0 && !learnt.has(id)).sort((a, b) => a - b);
    if (levelUp.length || other.length) learnsets[mon.id] = [levelUp, other];
  }
  const known = new Set(species.map(mon => mon.id));
  const evolutions = {};
  for (const mon of species) {
    const from = (mon.evoFrom ?? []).find(e => known.has(e.id));
    if (from) evolutions[mon.id] = [from.id, Number(LEVEL_STEP.exec(from.how ?? '')?.[1] ?? 0)];
  }
  return {
    v: BATTLE_DATA_VERSION,
    areaNames: Object.fromEntries(areas.filter(area => used.has(area.slug)).map(area => [area.slug, area.name])),
    mainIds: trainerMainIds(buildTrainerProfiles(trainers).profiles),
    trainers: order.map(({ t, f, area }) => {
      // The battle in the place it is listed under comes first (the picker shows the first place).
      const live = p => !p.how?.startsWith('your partner') && !(p.conds?.length && p.conds.every(c => c.startsWith('never ')));
      const sorted = [...(t.places ?? [])].sort((a, b) => (b.area === area && live(b) ? 1 : 0) - (a.area === area && live(a) ? 1 : 0) || (live(b) ? 1 : 0) - (live(a) ? 1 : 0));
      const places = [...new Map(sorted.map(p => [`${p.map}|${p.how}|${p.conds.join('|')}`, [p.map ?? '', p.how ?? '', (p.conds ?? []).join(' or ')]])).values()];
      return [t.id, t.cls ?? '', t.name ?? '', t.double ? 1 : 0, f, area, places,
        t.team.filter(m => m.id).map(m => [m.id, m.level, m.abilityId ?? null, m.itemId ?? null, m.moveIds ?? [], m.nature ?? null,
          m.ivs ?? 0, m.hpIvs ?? m.ivs ?? 0, m.evs ?? null, m.gender ?? null, m.friendship ?? null])];
    }),
    learnsets,
    evolutions,
  };
}

/** Client side: the trainer.json-shaped Pokémon that the engine's fromTrainerMon expects. */
export function trainerMon([id, level, abilityId, itemId, moveIds, nature, ivs, hpIvs, evs, gender, friendship]) {
  return { id, level, abilityId, itemId, moveIds, nature, ivs, hpIvs, evs, gender, friendship };
}
