/**
 * Team Builder "Battle check": opponent picker, team overview grid and matchup view on top of the damage
 * engine in ./calc. This module, the engine and both data files load only when a player opens Battle check
 * (see setupTeamBuilder), so the planner's first load is unchanged.
 */
import { loadCalc, mirrorField, NO_KO_TEXT } from './calc/index.ts';
import { trainerMon, LATER } from './battle-check-data.mjs';
import {
  createDex, resolveSet, compactSet, learnableMoves, exportShowdown, importShowdown, NATURES, STAT_LABELS, DEFAULT_LEVEL,
  normalizeName, evolutionLevel, EV_TOTAL,
} from './battle-sets.mjs';
import { STATS, BOOST_STATS, STATUSES, sanitizeSet } from './team-builder-state.mjs';
// Loaded as a URL (not `import '…css'`) so Astro doesn't hoist it into the planner's first page load.
import styleHref from '../styles/battle-check.css?url';

type Any = any;
export interface BattleHost {
  root: HTMLElement;
  panel: HTMLElement;
  url(path: string): string;
  escape(value: unknown): string;
  art(speciesId: number, size?: 'sm' | 'md'): string;
  wireImages(parent: HTMLElement): void;
  hues: Record<string, number>;
  team(): number[];
  active(): number | null;
  setActive(id: number): void;
  sets(): Record<number, Any>;
  setSet(id: number, set: Any): void;
  opponent(): Any;
  setOpponent(opponent: Any): void;
  replaceTeam(ids: number[], sets: Record<number, Any>): void;
  canJoin(id: number): boolean;
  status(text: string): void;
  findPokemon(): void;
}

const STATUS_NAMES: Record<string, string> = { brn: 'Burned', par: 'Paralyzed', psn: 'Poisoned', tox: 'Badly poisoned', slp: 'Asleep', frz: 'Frozen' };
const WEATHERS = ['Sun', 'Rain', 'Sand', 'Hail', 'Harsh Sunshine', 'Heavy Rain', 'Strong Winds'];
const TERRAINS = ['Electric', 'Grassy', 'Psychic', 'Misty'];
const SIDE_TOGGLES: Array<[string, string]> = [['reflect', 'Reflect'], ['lightScreen', 'Light Screen'], ['auroraVeil', 'Aurora Veil'], ['helpingHand', 'Helping Hand'], ['tailwind', 'Tailwind'], ['stealthRock', 'Stealth Rock']];
const PAGE = 40;

function loadStyles() {
  if (document.querySelector('link[data-battle-check]')) return Promise.resolve();
  return new Promise<void>(resolve => {
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = styleHref; link.dataset.battleCheck = '';
    link.onload = link.onerror = () => resolve();
    document.head.append(link);
  });
}

export async function mountBattleCheck(host: BattleHost) {
  const base = host.url('/team-builder/');
  const styles = loadStyles();
  const [calcData, battleData] = await Promise.all(['calc-data.json', 'battle-data.json'].map(async file => {
    const response = await fetch(`${base}${file}`);
    if (!response.ok) throw new Error(`Could not load ${file}`);
    return response.json();
  }));
  await styles;
  const calc = loadCalc(calcData);
  const dex = createDex(calcData, battleData);
  const areaNames: Record<string, string> = battleData.areaNames ?? {};
  const trainers = (battleData.trainers as Any[]).map(([id, cls, name, double, flags, area, places, team], order) => {
    const mons = (team as Any[]).map(trainerMon);
    const label = `${cls} ${name}`.trim() || 'Unnamed trainer';
    const levels = mons.map((m: Any) => m.level);
    const lo = Math.min(...levels), hi = Math.max(...levels);
    const search = normalizeSearch([label, areaNames[area] ?? '', ...places.flatMap((p: string[]) => [p[0]]), ...mons.map((m: Any) => dex.species.get(m.id)?.name ?? '')].join(' '));
    return { id, cls, name, label, double: !!double, flags, area, places, mons, order, maxLevel: hi, levelText: lo === hi ? `Lv. ${hi}` : `Lv. ${lo}–${hi}`, search };
  });
  const trainerById = new Map(trainers.map(t => [t.id, t]));
  const saved = host.opponent();
  if ((saved?.trainer != null && !trainerById.has(saved.trainer)) || (saved?.species && !dex.species.has(saved.species))) {
    host.setOpponent(null);
    host.status('That opponent couldn’t be found. Pick one below.');
  }
  const { escape } = host;
  const panel = host.panel;
  const hue = (type: string) => host.hues[type] ?? 42;

  // ------------------------------------------------------------------ view state (not saved)
  let query = '';
  let shown = PAGE;
  let picking = false;
  let foeIndex = 0;
  let field: Any = { format: '', spread: '', weather: '', terrain: '', crit: false, trickRoom: false, gravity: false, mine: {}, theirs: {} };
  const expanded = new Set<string>();
  /** HP %, status and stat stages of trainer Pokémon, by `${trainerId}:${index}` (this visit only). */
  const foeCondition: Record<string, Any> = {};

  panel.innerHTML = `
    <div class="tb-bc">
      <section class="tb-bc-opponent" aria-labelledby="tb-bc-opponent-heading">
        <h3 id="tb-bc-opponent-heading" class="tb-bc-label">Opponent</h3>
        <div id="tb-bc-foe"></div>
        <div id="tb-bc-picker"></div>
      </section>
      <section class="tb-bc-overview" aria-labelledby="tb-bc-overview-heading" id="tb-bc-overview"></section>
      <section class="tb-bc-matchup" aria-labelledby="tb-bc-matchup-heading" id="tb-bc-matchup"></section>
      <div class="tb-bc-tools">
        <details class="tb-bc-disclosure" id="tb-bc-set"></details>
        <details class="tb-bc-disclosure" id="tb-bc-field"></details>
        <details class="tb-bc-disclosure" id="tb-bc-io"></details>
      </div>
      <p class="tb-bc-note">Calculations follow this game’s battle code; flagged results (⚠) are estimates. Who moves first compares Speed only; move priority is listed per move.</p>
    </div>`;
  const $ = <T extends HTMLElement = HTMLElement>(id: string) => panel.querySelector<T>(`#tb-bc-${id}`)!;

  // ------------------------------------------------------------------ sets
  function opponentSets(): Array<{ speciesId: number; set: Any; label: string; details: string[] }> {
    const opp = host.opponent();
    if (opp?.trainer != null) {
      const t = trainerById.get(opp.trainer);
      if (!t) return [];
      return t.mons.map((mon: Any, i: number) => {
        const cond = foeCondition[`${t.id}:${i}`] ?? {};
        const set = { ...calc.fromTrainerMon(mon), curHPPercent: cond.hp ?? 100, status: cond.status ?? '', boosts: { ...(cond.boosts ?? {}) } };
        return { speciesId: mon.id, set, label: dex.species.get(mon.id)?.name ?? `#${mon.id}`, details: monDetails(set) };
      });
    }
    if (opp?.species) {
      const resolved = resolveSet(dex, opp.species, opp.set, { level: DEFAULT_LEVEL });
      return [{ speciesId: opp.species, set: resolved.calc, label: dex.species.get(opp.species)?.name ?? '', details: monDetails(resolved.calc) }];
    }
    return [];
  }
  function monDetails(set: Any) {
    return [`Lv. ${set.level}`, set.itemId ? dex.items.get(set.itemId)?.name : 'No item', set.abilityId ? dex.abilities.get(set.abilityId)?.name : '', set.nature ?? 'Hardy'].filter(Boolean) as string[];
  }
  function contextLevel() {
    const opp = host.opponent();
    if (opp?.trainer != null) {
      const t = trainerById.get(opp.trainer);
      if (t) return { level: t.maxLevel, why: `matches ${t.label}’s highest level` };
    }
    if (opp?.species) {
      const level = sanitizeSet(opp.set)?.level ?? DEFAULT_LEVEL;
      return { level, why: 'matches your opponent’s level' };
    }
    return { level: DEFAULT_LEVEL, why: 'default until you pick an opponent' };
  }
  const mine = (id: number) => resolveSet(dex, id, host.sets()[id], { level: contextLevel().level });
  const teamIds = () => host.team().filter(id => dex.species.has(id));
  const selectedMine = () => {
    const team = teamIds();
    const active = host.active();
    return active != null && team.includes(active) ? active : team[0] ?? null;
  };

  /** The field for your attacks (`out`) or theirs (`back`, already mirrored). */
  function calcField(direction: 'out' | 'back' = 'out'): Any {
    const opp = host.opponent();
    const trainer = opp?.trainer != null ? trainerById.get(opp.trainer) : null;
    const gameType = field.format || (trainer?.double ? 'Doubles' : 'Singles');
    const none = field.weather === 'none' || field.terrain === 'none';
    // Doubles: a spread move against a lone Pokémon does full damage. Automatic: the side being hit has one Pokémon.
    const targets = direction === 'out' ? opponentSets().length : teamIds().length;
    const spreadTargets = gameType !== 'Doubles' ? undefined : field.spread ? Number(field.spread) : targets === 1 ? 1 : undefined;
    const out = {
      gameType, spreadTargets,
      weather: field.weather && field.weather !== 'none' ? field.weather : undefined,
      terrain: field.terrain && field.terrain !== 'none' ? field.terrain : undefined,
      abilityField: !none, crit: field.crit, trickRoom: field.trickRoom, gravity: field.gravity,
      attackerSide: { ...field.mine }, defenderSide: { ...field.theirs },
    };
    return direction === 'out' ? out : mirrorField(out);
  }
  /** Re-renders while keeping keyboard focus (and the caret) on the same control. */
  function selectorFor(el: Element | null): string | null {
    if (!el || !panel.contains(el)) return null;
    if (el.id) return `#${CSS.escape(el.id)}`;
    for (const attr of Array.from(el.attributes)) if (attr.name.startsWith('data-bc-')) return `[${attr.name}="${CSS.escape(attr.value)}"]`;
    if (el.tagName === 'SUMMARY' && el.parentElement) {
      const parent = selectorFor(el.parentElement);
      return parent ? `${parent} > summary` : null;
    }
    return null;
  }
  function keepFocus(draw: () => void) {
    const el = document.activeElement as HTMLElement | null;
    const selector = selectorFor(el);
    const caret = el instanceof HTMLInputElement && /^(text|search)$/.test(el.type) ? [el.selectionStart, el.selectionEnd] : null;
    // Nested disclosures (Advanced, the opponent's set and condition) stay open across re-renders.
    const open = new Map(Array.from(panel.querySelectorAll<HTMLDetailsElement>('details[data-bc-details]')).map(d => [d.dataset.bcDetails, d.open]));
    draw();
    panel.querySelectorAll<HTMLDetailsElement>('details[data-bc-details]').forEach(d => { if (open.has(d.dataset.bcDetails)) d.open = !!open.get(d.dataset.bcDetails); });
    if (!selector || el?.isConnected) return;
    const next = panel.querySelector<HTMLElement>(selector);
    if (!next) return;
    next.focus({ preventScroll: true });
    if (caret && next instanceof HTMLInputElement && caret[0] != null) { try { next.setSelectionRange(caret[0], caret[1]); } catch { /* not a text field */ } }
  }

  // ------------------------------------------------------------------ helpers
  function normalizeSearch(text: string) { return text.normalize('NFKD').replace(/\p{M}/gu, '').replace(/['‘’]/g, '').toLowerCase(); }
  const pct = (n: number) => (Math.round(n * 10) / 10).toString();
  // Above 100 % only says "knocks out": the exact damage is in the move's details.
  const cap = (n: number) => n > 100 ? '>100' : pct(n);
  const range = (m: Any) => m.minPercent > 100 ? '>100%' : `${pct(m.minPercent)}–${pct(Math.min(100, m.maxPercent))}%`;
  const koText = (m: Any) => m.koChanceText || (m.maxDamage > 0 ? NO_KO_TEXT : 'no damage');
  function verdict(m: Any) {
    if (!m || !m.modelled || m.maxDamage <= 0) return '';
    if (!m.koHits) return NO_KO_TEXT;
    const what = m.koHits === 1 ? 'OHKO' : `${m.koHits}HKO`;
    if (m.koChance == null) return `~${what}`;
    return m.koChance >= 1 ? what : `${what} ${Math.round(m.koChance * 1000) / 10}%`;
  }
  const hits = (m: Any) => !m || !m.modelled || m.maxDamage <= 0 ? 99 : !m.koHits ? 50 : m.koHits + (m.koChance != null && m.koChance < 1 ? 0.5 : 0);
  function best(result: Any) {
    const damaging = result.moves.filter((m: Any) => m.modelled && m.category !== 'Status' && m.maxDamage > 0);
    damaging.sort((a: Any, b: Any) => hits(a) - hits(b) || (b.minPercent + b.maxPercent) - (a.minPercent + a.maxPercent));
    return damaging[0] ?? null;
  }
  function safeMatchup(a: Any, b: Any, f: Any) {
    try { return calc.calculateMatchup(a, b, f); } catch { return null; }
  }
  function safeSpeed(a: Any, b: Any, f: Any) {
    try { return calc.speedOrder(a, b, f); } catch { return null; }
  }
  const typeChip = (type: string) => `<span class="type type-${escape(type.toLowerCase())}">${escape(type)}</span>`;

  // ------------------------------------------------------------------ opponent
  function drawFoe() {
    const opp = host.opponent();
    const box = $('foe');
    const t = opp?.trainer != null ? trainerById.get(opp.trainer) : null;
    if (picking || (!t && !opp?.species)) { box.innerHTML = ''; renderPicker(); return; }
    $('picker').innerHTML = '';
    const sets = opponentSets();
    let heading = '';
    if (t) {
      const place = t.places[0];
      heading = `<div class="tb-bc-foe-head"><div><strong class="tb-bc-foe-name">${escape(t.label)}</strong>
        <span class="tb-bc-foe-meta">${escape([place?.[0], t.levelText].filter(Boolean).join(' · '))}${t.double ? ' · <span class="tb-bc-chip">Double battle</span>' : ''}</span>
        ${place ? `<span class="tb-bc-foe-how">${escape(place[1])}${place[2] ? `, ${escape(place[2])}` : ''}${t.places.length > 1 ? ` · <a href="${escape(host.url(`/trainers/records/${t.id}/`))}">${t.places.length - 1} more ${t.places.length === 2 ? 'battle' : 'battles'}</a>` : ''}</span>` : ''}</div>
        <button type="button" class="tb-bc-button" data-bc-change>Change</button></div>`;
    } else {
      heading = `<div class="tb-bc-foe-head"><div><strong class="tb-bc-foe-name">Any Pokémon</strong><span class="tb-bc-foe-meta">A free calculation against one Pokémon you choose.</span></div><button type="button" class="tb-bc-button" data-bc-change>Change</button></div>`;
    }
    foeIndex = Math.min(foeIndex, Math.max(0, sets.length - 1));
    box.innerHTML = `${heading}
      <div class="tb-bc-foe-team" role="group" aria-label="Opponent's Pokémon">${sets.map((entry, i) => {
        const mon = dex.species.get(entry.speciesId);
        return `<button type="button" class="tb-bc-foe-mon" data-bc-foe="${i}" aria-pressed="${i === foeIndex}" style="--mon-hue:${hue(mon?.types?.[0])}">
          ${host.art(entry.speciesId, 'sm')}<span class="tb-bc-foe-text"><strong>${escape(entry.label)}</strong><small>${escape(entry.details.join(' · '))}</small></span></button>`;
      }).join('')}</div>
      ${opp?.species ? customEditor(opp) : ''}
      ${sets[foeIndex] ? conditionPanel(sets[foeIndex], opp?.species ? 'foe' : 'tfoe') : ''}`;
    host.wireImages(box);
  }
  const renderFoe = () => keepFocus(drawFoe);

  /** HP, status and stat stages of the selected opponent Pokémon (a trainer's or the custom one). */
  function conditionPanel(entry: Any, who: string) {
    const s = entry.set;
    const stages = BOOST_STATS.filter((st: string) => s.boosts?.[st]).map((st: string) => `${STAT_LABELS[st]} ${s.boosts[st] > 0 ? '+' : ''}${s.boosts[st]}`);
    const summary = [s.curHPPercent < 100 ? `${s.curHPPercent}% HP` : 'Full HP', s.status ? STATUS_NAMES[s.status] : 'Healthy', stages.length ? stages.join(', ') : 'no stat changes'].join(' · ');
    return `<details class="tb-bc-disclosure tb-bc-condition" data-bc-details="condition"><summary>${escape(entry.label)}’s condition <span>${escape(summary)}</span></summary>
      <div class="tb-bc-form">${conditionFields(who, s)}</div></details>`;
  }
  function conditionFields(who: string, s: Any) {
    return `<label>Current HP %<input type="number" min="1" max="100" inputmode="numeric" data-bc-field="${who}:hp" value="${s.curHPPercent ?? 100}" /></label>
      <label>Status<select data-bc-field="${who}:status">${options([['', 'Healthy'], ...STATUSES.map((st: string) => [st, STATUS_NAMES[st]] as [string, string])], s.status ?? '')}</select></label>
      ${BOOST_STATS.map((st: string) => `<label>${STAT_LABELS[st]} stage<select data-bc-field="${who}:boost:${st}">${options(Array.from({ length: 13 }, (_, i) => [i - 6, i - 6 > 0 ? `+${i - 6}` : String(i - 6)] as [number, string]), s.boosts?.[st] ?? 0)}</select></label>`).join('')}`;
  }

  function drawPicker() {
    const box = $('picker');
    const terms = normalizeSearch(query).trim().split(/\s+/).filter(Boolean);
    const matches = trainers.filter(t => terms.every(term => t.search.includes(term)));
    let lastArea: string | null = null;
    const rows: string[] = [];
    for (const t of matches.slice(0, shown)) {
      const group = t.flags & 3 ? 'Partners and scenes that never happen' : t.flags & LATER ? 'Rematches and later battles' : t.area ? areaNames[t.area] ?? 'Other places' : 'No known battle location';
      if (group !== lastArea) { rows.push(`<li class="tb-bc-group" role="presentation">${escape(group)}</li>`); lastArea = group; }
      const tags = [t.double ? 'Double' : '', t.flags & 1 ? 'Partner' : '', t.flags & 2 ? 'Inactive scene' : ''].filter(Boolean);
      rows.push(`<li><button type="button" class="tb-bc-trainer" data-bc-trainer="${t.id}">
        <span class="tb-bc-trainer-team" aria-hidden="true">${t.mons.slice(0, 6).map((m: Any) => host.art(m.id, 'sm')).join('')}</span>
        <span class="tb-bc-trainer-text"><strong>${escape(t.label)}</strong><small>${escape([t.places[0]?.[0] || 'Location unknown', t.levelText, ...tags].join(' · '))}</small></span></button></li>`);
    }
    const opp = host.opponent();
    box.innerHTML = `<div class="tb-bc-search">
        <label class="tb-search"><span class="sr-only">Search trainers</span><input type="search" id="tb-bc-query" placeholder="Search a trainer, place or Pokémon…" autocomplete="off" value="${escape(query)}" /></label>
        <button type="button" class="tb-bc-button" data-bc-any>Any Pokémon</button>
        ${opp?.trainer != null || opp?.species ? '<button type="button" class="tb-bc-button tb-bc-quiet" data-bc-cancel>Cancel</button>' : ''}
      </div>
      <p class="tb-bc-hint" id="tb-bc-count" role="status">${matches.length ? `${matches.length.toLocaleString()} ${matches.length === 1 ? 'team' : 'teams'} in route order` : 'No trainer matches. Try a name, place or Pokémon.'}</p>
      <ul class="tb-bc-trainers" aria-label="Trainers">${rows.join('')}</ul>
      ${matches.length > shown ? `<button type="button" class="tb-bc-button tb-bc-more" data-bc-more>Show more (${(matches.length - shown).toLocaleString()} left)</button>` : ''}`;
    host.wireImages(box);
  }
  const renderPicker = () => keepFocus(drawPicker);

  function customEditor(opp: Any) {
    const resolved = resolveSet(dex, opp.species, opp.set, { level: DEFAULT_LEVEL });
    return `<details class="tb-bc-disclosure tb-bc-custom" data-bc-details="custom"${opp.set ? '' : ' open'}><summary>Choose the Pokémon and its set <span>${escape(dex.species.get(opp.species)?.name ?? '')}</span></summary>
      <div class="tb-bc-form"><label class="tb-bc-wide">Pokémon<input list="tb-bc-species" data-bc-foe-species value="${escape(dex.species.get(opp.species)?.name ?? '')}" autocomplete="off" /></label>
      ${setFields('foe', opp.species, resolved, `default ${DEFAULT_LEVEL}`, false)}</div></details>`;
  }

  // ------------------------------------------------------------------ overview grid
  function drawOverview() {
    const box = $('overview');
    const team = teamIds();
    const foes = opponentSets();
    if (!foes.length) { box.innerHTML = ''; return; }
    if (!team.length) {
      box.innerHTML = `<div class="tb-bc-empty"><strong>Add Pokémon to your team to compare.</strong><span>Their moves and stats are listed above.</span><button type="button" class="tb-bc-button" data-bc-find>Find Pokémon</button></div>`;
      return;
    }
    const f = calcField('out'), fBack = calcField('back');
    const pickedMine = selectedMine();
    const rows = team.map(id => {
      const me = mine(id).calc;
      const mon = dex.species.get(id)!;
      const cells = foes.map((foe, j) => {
        const out = safeMatchup(me, foe.set, f);
        const back = safeMatchup(foe.set, me, fBack);
        const speed = safeSpeed(me, foe.set, f);
        const a = out ? best(out) : null, b = back ? best(back) : null;
        const ha = hits(a), hb = hits(b);
        const first = speed?.faster === 'a';
        const tone = ha >= 99 && hb >= 99 ? 'even' : ha < hb || (ha === hb && first) ? 'good' : ha > hb || (ha === hb && speed?.faster === 'b') ? 'bad' : 'even';
        const word = { good: 'Favourable', even: 'Even', bad: 'Risky' }[tone];
        const label = `${mon.name} against ${foe.label}: ${a ? `your ${a.name} ${range(a)}, ${koText(a)}` : 'no damaging move'}. ${b ? `Their ${b.name} ${range(b)}` : 'They have no damaging move'}. ${first ? 'You move first' : speed?.faster === 'b' ? 'They move first' : 'Speed tie'}. ${word}.`;
        const selected = id === pickedMine && j === foeIndex;
        return `<td><button type="button" class="tb-bc-cell tb-bc-${tone}" data-bc-cell="${id}:${j}" aria-pressed="${selected}" aria-label="${escape(label)}">
          <strong>${a ? `${escape(cap(a.maxPercent))}%` : '—'}</strong><span>${escape(a ? verdict(a) : 'No damage')}</span>
          <small><span aria-hidden="true">↩</span> ${b ? `${escape(cap(b.maxPercent))}%` : '—'}</small></button></td>`;
      }).join('');
      return `<tr><th scope="row"><button type="button" class="tb-bc-rowhead" data-bc-mine="${id}" aria-pressed="${id === pickedMine}">${host.art(id, 'sm')}<span>${escape(mon.name)}</span></button></th>${cells}</tr>`;
    }).join('');
    box.innerHTML = `<div class="tb-bc-section-head"><h3 id="tb-bc-overview-heading">Team overview</h3>
        <p class="tb-bc-hint">Your best hit (max %) and verdict · <span aria-hidden="true">↩</span> their best hit back. <span class="tb-bc-legend"><i class="tb-bc-good"></i>Favourable <i class="tb-bc-even"></i>Even <i class="tb-bc-bad"></i>Risky</span></p></div>
      <div class="tb-bc-grid-scroll"><table class="tb-bc-grid"><caption class="sr-only">Team overview: your Pokémon against each opponent</caption><thead><tr><td></td>${foes.map((foe, j) => `<th scope="col"><button type="button" class="tb-bc-colhead" data-bc-foe="${j}" aria-pressed="${j === foeIndex}">${host.art(foe.speciesId, 'sm')}<span>${escape(foe.label)}</span></button></th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody></table></div>`;
    host.wireImages(box);
  }
  const renderOverview = () => keepFocus(drawOverview);

  // ------------------------------------------------------------------ matchup
  function moveRow(m: Any, side: string, isBest: boolean, defenderHP: number) {
    const key = `${side}:${m.moveId}`;
    const open = expanded.has(key);
    const detailId = `tb-bc-detail-${side}-${m.moveId}`;
    const flags = m.caveats?.length ?? 0;
    if (!m.modelled) {
      return `<li class="tb-bc-move is-unmodelled"><div class="tb-bc-move-main"><span class="tb-bc-move-name">${escape(m.name)}<small>${escape(m.type)} · not calculated</small></span>
        <span class="tb-bc-reason">${escape(m.caveats?.[0] ?? 'This move’s damage can’t be calculated.')}</span></div></li>`;
    }
    const lo = Math.min(100, m.minPercent), hi = Math.min(100, m.maxPercent);
    const rolls = m.rolls?.length ? m.rolls : [];
    const prio = m.priority ? ` · priority ${m.priority > 0 ? '+' : ''}${m.priority}` : '';
    return `<li class="tb-bc-move${isBest ? ' is-best' : ''}" style="--type-hue:${hue(m.type)}">
      <button type="button" class="tb-bc-move-main" data-bc-move="${escape(key)}" aria-expanded="${open}" aria-controls="${detailId}">
        <span class="tb-bc-move-name">${escape(m.name)}${isBest ? '<em class="tb-bc-best">Best</em>' : ''}<small>${escape(m.type)} · ${escape(m.category)}${escape(prio)}</small></span>
        <span class="tb-bc-bar" aria-hidden="true"><i style="width:${lo}%"></i><b style="left:${lo}%;width:${Math.max(0, hi - lo)}%"></b></span>
        <span class="tb-bc-numbers"><strong>${escape(range(m))}</strong><span>${escape(koText(m))}</span></span>
        ${flags ? `<span class="tb-bc-flag" title="${escape(m.caveats.join(' '))}"><span aria-hidden="true">⚠</span> ${flags}<span class="sr-only"> ${flags === 1 ? 'note' : 'notes'}, open for details</span></span>` : ''}
      </button>
      <div class="tb-bc-move-detail" id="${detailId}"${open ? '' : ' hidden'}>
        ${m.description ? `<p>${escape(m.description)}</p>` : ''}
        ${flags ? `<ul class="tb-bc-caveats">${m.caveats.map((c: string) => `<li><span aria-hidden="true">⚠</span> ${escape(c)}</li>`).join('')}</ul>` : ''}
        ${m.notes?.length ? `<ul class="tb-bc-notes">${m.notes.map((n: string) => `<li><span aria-hidden="true">✓</span> ${escape(n)}</li>`).join('')}</ul>` : ''}
        ${m.maxDamage > 0 ? `<p class="tb-bc-hint">Damage: ${m.minDamage}–${m.maxDamage} HP of ${defenderHP} (${escape(pct(m.minPercent))}–${escape(pct(m.maxPercent))}%)</p>` : ''}
        ${rolls.length ? `<p class="tb-bc-rolls"><span>Damage rolls (of ${defenderHP} HP)</span> ${escape(rolls.join(', '))}</p>` : ''}
        <p class="tb-bc-hint">Critical hit chance: ${escape(critText(m.critChance))}</p>
      </div></li>`;
  }
  function critText(chance: number) {
    if (chance >= 1) return 'always';
    if (chance <= 0) return 'none';
    return `1 in ${Math.round(1 / chance)}`;
  }
  function moveList(result: Any, side: string) {
    if (!result) return '<p class="tb-bc-hint">This matchup couldn’t be calculated.</p>';
    const top = best(result);
    const damaging = result.moves.filter((m: Any) => m.category !== 'Status');
    const status = result.moves.filter((m: Any) => m.category === 'Status');
    return `<ul class="tb-bc-moves">${damaging.map((m: Any) => moveRow(m, side, m === top, result.defender.maxHP)).join('') || '<li class="tb-bc-hint">No damaging moves.</li>'}</ul>
      ${status.length ? `<p class="tb-bc-status">Also: ${status.map((m: Any) => escape(m.name)).join(', ')} <span>(no direct damage)</span></p>` : ''}`;
  }

  function fieldSourceText(result: Any) {
    const out: string[] = [];
    const ability = (from: Any) => dex.abilities.get(dex.abilityByName.get(normalizeName(from.ability)))?.name ?? from.ability;
    const whose = (from: Any) => `${from.side === 'attacker' ? 'your' : 'the opponent’s'} ${from.name}`;
    if (result?.field?.weatherFrom) out.push(`${result.field.weather === 'Hail' ? 'Hail' : `${result.field.weather} weather`} from ${whose(result.field.weatherFrom)} (${ability(result.field.weatherFrom)}).`);
    if (result?.field?.terrainFrom) out.push(`${result.field.terrain} Terrain from ${whose(result.field.terrainFrom)} (${ability(result.field.terrainFrom)}).`);
    return out;
  }
  function noAttackText(id: number, moveIds: number[]) {
    const name = dex.species.get(id)!.name;
    const moveNames = moveIds.map(m => dex.moves.get(m)?.name).filter(Boolean);
    if (moveNames.length === 1 && moveNames[0] === 'Transform') return `${name} only learns Transform, which copies the opponent; that can’t be calculated. Add moves in Edit set to compare.`;
    return `${name} has no damaging move to suggest. Add moves in Edit set to compare.`;
  }
  function drawMatchup() {
    const box = $('matchup');
    const foes = opponentSets();
    const id = selectedMine();
    if (!foes.length || id == null) { box.innerHTML = ''; return; }
    const foe = foes[foeIndex] ?? foes[0];
    const me = mine(id);
    const f = calcField('out');
    const out = safeMatchup(me.calc, foe.set, f);
    const back = safeMatchup(foe.set, me.calc, calcField('back'));
    const speed = safeSpeed(me.calc, foe.set, f);
    const myName = dex.species.get(id)!.name;
    const speedText = !speed ? '' : speed.faster === 'tie'
      ? `Speed tie at ${speed.aSpeed}: either can move first`
      : `${escape(speed.faster === 'a' ? myName : foe.label)} moves first · Speed ${speed.aSpeed} vs ${speed.bSpeed}${speed.trickRoom ? ' (Trick Room)' : ''}`;
    const speedFlags = [...(speed?.caveats ?? [])];
    // Form changes stay here; "checked in game" facts are listed in each move's details.
    const notes = [...new Set([...(out?.notes ?? []), ...(back?.notes ?? [])].filter((n: string) => !/\(checked in game\)\.$/.test(n)))];
    const auto = [...new Set([...fieldSourceText(out)])];
    const damaging = me.calc.moveIds.some((m: number) => dex.moves.get(m)?.cat !== 'Status');
    const team = teamIds();
    box.innerHTML = `<div class="tb-bc-section-head"><h3 id="tb-bc-matchup-heading">Matchup</h3>
        ${team.length > 1 ? `<div class="tb-bc-mine" role="group" aria-label="Your Pokémon">${team.map(m => `<button type="button" data-bc-mine="${m}" aria-pressed="${m === id}" aria-label="${escape(dex.species.get(m)!.name)}">${host.art(m, 'sm')}</button>`).join('')}</div>` : ''}</div>
      <div class="tb-bc-versus">
        <div>${host.art(id, 'md')}<span><strong>${escape(myName)}</strong><small>Lv. ${me.calc.level} · ${out ? `${out.attacker.maxHP} HP` : ''}</small></span></div>
        <span class="tb-bc-vs" aria-hidden="true">vs</span>
        <div>${host.art(foe.speciesId, 'md')}<span><strong>${escape(foe.label)}</strong><small>Lv. ${foe.set.level} · ${out ? `${out.defender.maxHP} HP` : ''}</small></span></div>
      </div>
      ${speed ? `<p class="tb-bc-speed"><span aria-hidden="true">⚡</span> ${speedText}${speedFlags.length ? ` <span class="tb-bc-flag" title="${escape(speedFlags.join(' '))}"><span aria-hidden="true">⚠</span><span class="sr-only">Note: ${escape(speedFlags.join(' '))}</span></span>` : ''}</p>` : ''}
      ${auto.length || notes.length ? `<p class="tb-bc-hint">${[...auto, ...notes].map(n => escape(n)).join(' ')}</p>` : ''}
      <div class="tb-bc-columns">
        <section aria-label="Your moves"><h4>Your moves <span>into ${escape(foe.label)}</span></h4>${me.suggestedMoves ? `<p class="tb-bc-suggested">${escape(damaging ? 'Suggested moves: its strongest attacks by this level, including moves learnt before evolving. Change them in Edit set.' : noAttackText(id, me.calc.moveIds))}</p>` : ''}${moveList(out, 'mine')}</section>
        <section aria-label="Their moves"><h4>Their moves <span>into ${escape(myName)}</span></h4>${moveList(back, 'theirs')}</section>
      </div>`;
    host.wireImages(box);
  }
  const renderMatchup = () => keepFocus(drawMatchup);

  // ------------------------------------------------------------------ set editor
  function options(list: Array<[string | number, string]>, value: unknown) {
    return list.map(([v, label]) => `<option value="${escape(v)}"${String(v) === String(value ?? '') ? ' selected' : ''}>${escape(label)}</option>`).join('');
  }
  function evolutionNote(speciesId: number, level: number) {
    const evo = evolutionLevel(dex, speciesId);
    if (!evo || level >= evo.level) return '';
    return `${dex.species.get(speciesId)!.name} usually evolves at Lv. ${evo.level}${evo.exact ? '' : ' or later'}.`;
  }
  function formNote(set: Any) {
    const form = calc.battlesAs(set);
    if (!form.changed) return null;
    return { text: `Holding ${dex.items.get(set.itemId)?.name}: battles as ${form.name}${form.abilityId ? ` with ${dex.abilities.get(form.abilityId)?.name}` : ''}.`, form };
  }
  function setFields(who: string, speciesId: number, resolved: Any, levelHint: string, condition = true) {
    const s = resolved.calc;
    const evo = evolutionNote(speciesId, s.level);
    const form = formNote(s);
    const learnable = learnableMoves(dex, speciesId);
    const listId = `tb-bc-moves-${who}`;
    const natureLabel = (n: Any[]) => n[1] ? `${n[0]} (+${STAT_LABELS[n[1]]} −${STAT_LABELS[n[2]]})` : `${n[0]} (neutral)`;
    return `
      <label>Level<input type="number" min="1" max="100" inputmode="numeric" data-bc-field="${who}:level" value="${resolved.autoLevel ? '' : s.level}" placeholder="${s.level}" /><small>${escape(resolved.autoLevel ? `Lv. ${s.level}: ${levelHint}` : 'Clear to match the opponent')}</small>${evo ? `<small class="tb-bc-evo">${escape(evo)}</small>` : ''}</label>
      <label>Nature<select data-bc-field="${who}:nature">${options(NATURES.map(n => [n[0], natureLabel(n)]), s.nature ?? 'Hardy')}</select></label>
      <label>Ability<select data-bc-field="${who}:ability">${options(resolved.abilityChoices.map((a: number) => [a, `${dex.abilities.get(a)?.name ?? a}${a === dex.species.get(speciesId)?.hiddenAbilityId && !dex.species.get(speciesId)?.abilityIds.includes(a) ? ' (hidden)' : ''}`]), s.abilityId)}</select>${form ? `<small>${escape(form.text)}</small>` : ''}</label>
      <label>Held item<input list="tb-bc-items" data-bc-field="${who}:item" value="${escape(s.itemId ? dex.items.get(s.itemId)?.name : '')}" placeholder="No item" autocomplete="off" /></label>
      <fieldset class="tb-bc-wide tb-bc-moves-edit"><legend>Moves ${resolved.suggestedMoves ? '<span class="tb-bc-chip">Suggested moves</span>' : `<button type="button" class="tb-bc-link" data-bc-reset-moves="${who}">Use suggested moves</button>`}</legend>
        ${[0, 1, 2, 3].map(i => `<input list="${listId}" data-bc-field="${who}:move${i}" aria-label="Move ${i + 1}" value="${escape(s.moveIds[i] ? dex.moves.get(s.moveIds[i])?.name : '')}" placeholder="—" autocomplete="off" />`).join('')}
        <datalist id="${listId}">${learnable.map(m => `<option value="${escape(dex.moves.get(m)!.name)}"></option>`).join('')}</datalist>
        <small>${learnable.length ? `${learnable.length} moves it can learn in this game` : 'No learnset data: any move is accepted.'}</small></fieldset>
      <details class="tb-bc-advanced tb-bc-wide" data-bc-details="${who}-advanced"><summary>Advanced <span>${condition ? 'IVs, EVs, HP, status, stat stages' : 'IVs, EVs'}</span></summary>
        <div class="tb-bc-stats" role="group" aria-label="IVs and EVs">
          <span></span>${STATS.map(st => `<span class="tb-bc-stat-label">${STAT_LABELS[st]}</span>`).join('')}
          <span class="tb-bc-stat-label">IVs</span>${STATS.map(st => `<input type="number" min="0" max="31" inputmode="numeric" aria-label="${STAT_LABELS[st]} IV" data-bc-field="${who}:iv:${st}" value="${s.ivs[st]}" />`).join('')}
          <span class="tb-bc-stat-label">EVs</span>${STATS.map(st => `<input type="number" min="0" max="255" step="4" inputmode="numeric" aria-label="${STAT_LABELS[st]} EV" data-bc-field="${who}:ev:${st}" value="${s.evs[st]}" />`).join('')}
        </div>
        ${condition ? `<div class="tb-bc-form">${conditionFields(who, s)}</div>` : ''}
      </details>`;
  }

  function setSummary(id: number, resolved: Any) {
    const s = resolved.calc;
    const form = formNote(s)?.form;
    return [`Lv. ${s.level}${resolved.autoLevel ? ' (auto)' : ''}`, s.nature ?? 'Hardy',
      form ? `battles as ${form.name}` : '', dex.abilities.get(form?.abilityId ?? s.abilityId)?.name,
      s.itemId ? dex.items.get(s.itemId)?.name : 'no item', resolved.suggestedMoves ? 'suggested moves' : 'your moves',
      evolutionNote(id, s.level)].filter(Boolean).join(' · ');
  }
  function drawSetEditor() {
    const box = $<HTMLDetailsElement>('set');
    const id = selectedMine();
    if (id == null || !opponentSets().length) { box.hidden = true; return; }
    box.hidden = false;
    const mon = dex.species.get(id)!;
    const resolved = mine(id);
    const ctx = contextLevel();
    const open = box.open;
    box.innerHTML = `<summary>Edit ${escape(mon.name)}’s set <span>${escape(setSummary(id, resolved))}</span></summary>
      <div class="tb-bc-form">${setFields('mine', id, resolved, ctx.why)}</div>
      <div class="tb-bc-row">
        <button type="button" class="tb-bc-button" data-bc-copy-set>Copy as Showdown text</button>
        <button type="button" class="tb-bc-button tb-bc-quiet" data-bc-reset-set${host.sets()[id] ? '' : ' disabled'}>Reset to defaults</button>
      </div>`;
    box.open = open;
  }
  const renderSetEditor = () => keepFocus(drawSetEditor);

  function drawField() {
    const box = $<HTMLDetailsElement>('field');
    if (!opponentSets().length) { box.hidden = true; return; }
    box.hidden = false;
    const f = calcField();
    const sideBoxes = (side: 'mine' | 'theirs') => `<fieldset><legend>${side === 'mine' ? 'Your side' : 'Their side'}</legend>
      ${SIDE_TOGGLES.map(([key, label]) => `<label class="tb-bc-check"><input type="checkbox" data-bc-side="${side}:${key}"${field[side][key] ? ' checked' : ''} />${label}</label>`).join('')}
      <label>Spikes<select data-bc-side="${side}:spikes">${options([[0, 'None'], [1, '1 layer'], [2, '2 layers'], [3, '3 layers']], field[side].spikes ?? 0)}</select></label></fieldset>`;
    const active = [f.gameType, field.weather && field.weather !== 'none' ? field.weather : '', field.terrain && field.terrain !== 'none' ? `${field.terrain} Terrain` : '',
      f.gameType === 'Doubles' && field.spread ? (field.spread === '1' ? 'spread moves hit one' : 'spread moves hit two') : '',
      field.trickRoom ? 'Trick Room' : '', field.gravity ? 'Gravity' : '', field.crit ? 'critical hits' : '',
      ...['mine', 'theirs'].flatMap(side => SIDE_TOGGLES.filter(([key]) => field[side][key]).map(([, label]) => `${label} (${side === 'mine' ? 'you' : 'them'})`))].filter(Boolean);
    const open = box.open;
    box.innerHTML = `<summary>Field <span>${escape(active.join(' · '))}</span></summary>
      <div class="tb-bc-form">
        <label>Battle<select data-bc-global="format">${options([['', `Automatic (${f.gameType === 'Doubles' && !field.format ? 'double' : 'single'} battle)`], ['Singles', 'Single battle'], ['Doubles', 'Double battle']], field.format)}</select></label>
        <label>Spread moves<select data-bc-global="spread"${f.gameType === 'Doubles' ? '' : ' disabled'}>${options([['', 'Automatic (by Pokémon left)'], ['2', 'Hit two Pokémon (×0.75)'], ['1', 'Hit one Pokémon (full damage)']], field.spread)}</select><small>Double battles: moves such as Earthquake or Surf hit for 75% when they hit more than one Pokémon. Automatic uses full damage against a side with one Pokémon.</small></label>
        <label>Weather<select data-bc-global="weather">${options([['', 'Automatic (from Abilities)'], ['none', 'None (ignore Abilities)'], ...WEATHERS.map(w => [w, w] as [string, string])], field.weather)}</select></label>
        <label>Terrain<select data-bc-global="terrain">${options([['', 'Automatic (from Abilities)'], ['none', 'None (ignore Abilities)'], ...TERRAINS.map(t => [t, `${t} Terrain`] as [string, string])], field.terrain)}</select></label>
        <div class="tb-bc-checks">
          <label class="tb-bc-check"><input type="checkbox" data-bc-global="crit"${field.crit ? ' checked' : ''} />Critical hits</label>
          <label class="tb-bc-check"><input type="checkbox" data-bc-global="trickRoom"${field.trickRoom ? ' checked' : ''} />Trick Room</label>
          <label class="tb-bc-check"><input type="checkbox" data-bc-global="gravity"${field.gravity ? ' checked' : ''} />Gravity</label>
        </div>
        ${sideBoxes('mine')}${sideBoxes('theirs')}
      </div>
      <p class="tb-bc-hint">Weather, terrain and Aurora Veil from Abilities such as Drought are applied automatically; the matchup says when. “None” also ignores entry Abilities. Stealth Rock and Spikes count toward the KO chance of the Pokémon on that side.</p>`;
    box.open = open;
  }
  const renderField = () => keepFocus(drawField);

  function renderIO() {
    const box = $<HTMLDetailsElement>('io');
    const open = box.open;
    box.innerHTML = `<summary>Import / export <span>Showdown text</span></summary>
      <p class="tb-bc-hint">Paste one or more sets in Showdown format to replace your team. Names follow this guide (Showdown spellings such as “Raichu-Alola” also work). A set without “Level:” follows the opponent’s level.</p>
      <label class="sr-only" for="tb-bc-import">Showdown text</label>
      <textarea id="tb-bc-import" rows="6" spellcheck="false" placeholder="Venusaur @ Miracle Seed&#10;Ability: Overgrow&#10;Level: 30&#10;Modest Nature&#10;- Giga Drain"></textarea>
      <div class="tb-bc-row">
        <button type="button" class="tb-bc-button" data-bc-import>Import as my team</button>
        <button type="button" class="tb-bc-button tb-bc-quiet" data-bc-import-member>Apply to selected Pokémon</button>
        <button type="button" class="tb-bc-button tb-bc-quiet" data-bc-export>Copy my team as text</button>
      </div>
      <div id="tb-bc-io-result" role="alert"></div>`;
    box.open = open;
  }

  // Shared datalists: items and all species (custom opponent).
  const lists = document.createElement('div');
  lists.innerHTML = `<datalist id="tb-bc-items">${[...dex.items.values()].sort((a: Any, b: Any) => a.name.localeCompare(b.name)).map((i: Any) => `<option value="${escape(i.name)}"></option>`).join('')}</datalist>
    <datalist id="tb-bc-species">${[...dex.species.values()].map((s: Any) => `<option value="${escape(s.name)}"></option>`).join('')}</datalist>`;
  panel.append(lists);

  function renderResults() { renderOverview(); renderMatchup(); }
  function renderAll() { renderFoe(); renderResults(); renderSetEditor(); renderField(); }
  /** Announces the selected matchup through the planner's status line (the panel itself is not a live region). */
  function announceMatchup() {
    const id = selectedMine();
    const foe = opponentSets()[foeIndex];
    if (id != null && foe) host.status(`Matchup: your ${dex.species.get(id)!.name} against ${foe.label}.`);
  }
  function announceOpponent() {
    const opp = host.opponent();
    const t = opp?.trainer != null ? trainerById.get(opp.trainer) : null;
    const sets = opponentSets();
    if (t) host.status(`Opponent: ${t.label}, ${t.levelText}, ${sets.length} Pokémon.`);
    else if (opp?.species) host.status(`Opponent: ${dex.species.get(opp.species)?.name ?? 'a Pokémon'}.`);
  }

  // ------------------------------------------------------------------ editing
  function updateSet(who: string, key: string, raw: string, input: HTMLInputElement | HTMLSelectElement) {
    const opp = host.opponent();
    const speciesId = who === 'mine' ? selectedMine() : opp?.species;
    if (speciesId == null) return;
    const saved = { ...(who === 'mine' ? host.sets()[speciesId] : opp.set) };
    const resolved = who === 'mine' ? mine(speciesId) : resolveSet(dex, speciesId, opp.set, { level: DEFAULT_LEVEL });
    const [field1, stat] = key.split(':');
    const num = Number(raw);
    let error = '';
    if (field1 === 'level') { if (raw === '') delete saved.level; else if (num >= 1 && num <= 100) saved.level = Math.round(num); else error = 'Level must be 1–100.'; }
    else if (field1 === 'nature') saved.nature = raw;
    else if (field1 === 'ability') saved.ability = num;
    else if (field1 === 'item') {
      if (!raw.trim()) delete saved.item;
      else { const item = dex.itemByName.get(normalizeName(raw)); if (item) saved.item = item; else error = `“${raw}” isn’t an item in this game.`; }
    } else if (field1.startsWith('move')) {
      const index = Number(field1.slice(4));
      const moves = [...resolved.calc.moveIds];
      if (!raw.trim()) moves.splice(index, 1);
      else {
        const move = dex.moveByName.get(normalizeName(raw));
        const learnable = learnableMoves(dex, speciesId);
        if (!move) error = `“${raw}” isn’t a move in this game.`;
        else if (learnable.length && !learnable.includes(move)) error = `${dex.species.get(speciesId)!.name} can’t learn ${dex.moves.get(move).name} in this game.`;
        else moves[index] = move;
      }
      if (!error) saved.moves = [...new Set(moves.filter(Boolean))];
    } else if (field1 === 'iv' || field1 === 'ev') {
      const max = field1 === 'iv' ? 31 : 255;
      if (!(num >= 0 && num <= max) || raw === '') error = `${field1 === 'iv' ? 'IVs' : 'EVs'} must be 0–${max}.`;
      else {
        saved[`${field1}s`] = { ...(saved[`${field1}s`] ?? {}), [stat]: Math.round(num) };
        const total = STATS.reduce((sum: number, st: string) => sum + (saved.evs?.[st] ?? 0), 0);
        if (field1 === 'ev' && who === 'mine' && total > EV_TOTAL) error = `EVs add up to ${total}; the most a Pokémon can have is ${EV_TOTAL}.`;
      }
    } else if (field1 === 'hp') { if (num >= 1 && num <= 100) saved.hp = Math.round(num) === 100 ? undefined : Math.round(num); else error = 'HP must be 1–100%.'; }
    else if (field1 === 'status') saved.status = raw || undefined;
    else if (field1 === 'boost') saved.boosts = { ...(saved.boosts ?? {}), [stat]: num };
    input.setAttribute('aria-invalid', String(!!error));
    if (error) { host.status(error); input.title = error; return; }
    input.removeAttribute('title');
    const compact = compactSet(dex, speciesId, saved);
    if (who === 'mine') host.setSet(speciesId, compact);
    else host.setOpponent({ species: speciesId, set: compact ?? undefined });
    renderResults();
    // The custom opponent's level also sets your automatic level: both editors show level-dependent moves.
    if (who === 'foe') renderFoe();
    renderSetEditor();
  }
  /** HP, status and stages of a trainer's Pokémon (kept for this visit only). */
  function updateTrainerFoe(key: string, raw: string, input: HTMLInputElement | HTMLSelectElement) {
    const opp = host.opponent();
    if (opp?.trainer == null) return;
    const slot = `${opp.trainer}:${foeIndex}`;
    const cond = { ...(foeCondition[slot] ?? {}) };
    const [field1, stat] = key.split(':');
    const num = Number(raw);
    if (field1 === 'hp') {
      if (!(num >= 1 && num <= 100)) { input.setAttribute('aria-invalid', 'true'); input.title = 'HP must be 1–100%.'; host.status('HP must be 1–100%.'); return; }
      cond.hp = Math.round(num);
    } else if (field1 === 'status') cond.status = raw;
    else if (field1 === 'boost') cond.boosts = { ...(cond.boosts ?? {}), [stat]: num };
    input.setAttribute('aria-invalid', 'false'); input.removeAttribute('title');
    foeCondition[slot] = cond;
    renderFoe(); renderResults();
  }

  async function copy(text: string, done: string) {
    try { await navigator.clipboard.writeText(text); host.status(done); return true; }
    catch {
      const area = $<HTMLTextAreaElement>('io').querySelector('textarea');
      if (area) { $<HTMLDetailsElement>('io').open = true; area.value = text; area.focus(); area.select(); }
      host.status('Copy the selected text.');
      return false;
    }
  }
  function ioResult(errors: string[], warnings: string[], done = '') {
    const box = $('io-result');
    box.innerHTML = `${errors.length ? `<ul class="tb-bc-errors">${errors.map(e => `<li>${escape(e)}</li>`).join('')}</ul>` : ''}
      ${warnings.length ? `<ul class="tb-bc-warnings">${warnings.map(w => `<li>${escape(w)}</li>`).join('')}</ul>` : ''}${done ? `<p class="tb-bc-done">${escape(done)}</p>` : ''}`;
  }

  // ------------------------------------------------------------------ events
  panel.addEventListener('click', event => {
    const target = event.target as HTMLElement;
    const button = target.closest<HTMLButtonElement>('button');
    if (!button || button.disabled) return;
    const d = button.dataset;
    if (d.bcTrainer) {
      host.setOpponent({ trainer: Number(d.bcTrainer) }); picking = false; foeIndex = 0; expanded.clear();
      renderAll(); announceOpponent();
      $('foe').querySelector<HTMLElement>('[data-bc-change]')?.focus();
    } else if (d.bcChange !== undefined) { picking = true; renderFoe(); $<HTMLInputElement>('query').focus(); }
    else if (d.bcCancel !== undefined) { picking = false; renderFoe(); $('foe').querySelector<HTMLElement>('[data-bc-change]')?.focus(); }
    else if (d.bcAny !== undefined) {
      const current = host.opponent();
      host.setOpponent(current?.species ? current : { species: selectedMine() ?? 25 }); picking = false; foeIndex = 0;
      renderAll(); announceOpponent(); panel.querySelector<HTMLElement>('[data-bc-foe-species]')?.focus();
    } else if (d.bcMore !== undefined) { shown += PAGE; renderPicker(); }
    else if (d.bcFoe) { foeIndex = Number(d.bcFoe); expanded.clear(); renderFoe(); renderResults(); announceMatchup(); }
    else if (d.bcMine) { host.setActive(Number(d.bcMine)); expanded.clear(); renderResults(); renderSetEditor(); announceMatchup(); }
    else if (d.bcCell) {
      const [id, j] = d.bcCell.split(':').map(Number);
      host.setActive(id); foeIndex = j; expanded.clear(); renderFoe(); renderResults(); renderSetEditor(); announceMatchup();
      $('matchup').scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
      $('matchup').querySelector<HTMLElement>('[data-bc-move]')?.focus({ preventScroll: true });
    } else if (d.bcMove) {
      const open = !expanded.has(d.bcMove);
      if (open) expanded.add(d.bcMove); else expanded.delete(d.bcMove);
      button.setAttribute('aria-expanded', String(open));
      const detail = panel.querySelector<HTMLElement>(`#${button.getAttribute('aria-controls')}`);
      if (detail) detail.hidden = !open;
    } else if (d.bcFind !== undefined) host.findPokemon();
    else if (d.bcResetMoves) {
      if (d.bcResetMoves === 'mine') { const id = selectedMine(); if (id == null) return; const s = { ...(host.sets()[id] ?? {}) }; delete s.moves; host.setSet(id, compactSet(dex, id, s)); renderSetEditor(); panel.querySelector<HTMLElement>('[data-bc-field="mine:move0"]')?.focus(); }
      else { const opp = host.opponent(); const s = { ...(opp.set ?? {}) }; delete s.moves; host.setOpponent({ species: opp.species, set: compactSet(dex, opp.species, s) ?? undefined }); renderFoe(); }
      renderResults(); host.status('Suggested moves restored.');
    } else if (d.bcResetSet !== undefined) {
      const id = selectedMine(); if (id == null) return;
      host.setSet(id, null); renderSetEditor(); renderResults(); host.status(`${dex.species.get(id)!.name}’s set reset to defaults.`);
      $('set').querySelector<HTMLElement>('summary')?.focus();
    } else if (d.bcCopySet !== undefined) {
      const id = selectedMine(); if (id == null) return;
      void copy(exportShowdown(dex, id, mine(id)), `${dex.species.get(id)!.name}’s set copied as Showdown text.`);
    } else if (d.bcExport !== undefined) {
      const text = teamIds().map(id => exportShowdown(dex, id, mine(id))).join('\n\n');
      if (!text) { ioResult(['Your team is empty.'], []); return; }
      void copy(text, 'Team copied as Showdown text.').then(ok => ioResult([], [], ok ? 'Team copied as Showdown text.' : 'Copy the selected text.'));
    } else if (d.bcImport !== undefined || d.bcImportMember !== undefined) {
      const text = $<HTMLTextAreaElement>('import').value;
      const result = importShowdown(dex, text, { canUse: (id: number) => host.canJoin(id) });
      const errors = [...result.errors];
      for (const entry of result.sets) if (!host.canJoin(entry.speciesId)) errors.push(`${entry.name} can’t join the planner: it has no documented way to obtain it in this game.`);
      if (d.bcImportMember !== undefined) {
        const id = selectedMine();
        if (id == null) errors.push('Add a Pokémon to your team first.');
        else if (result.sets.length !== 1) errors.push('Paste exactly one set to apply it to the selected Pokémon.');
        else if (result.sets[0].speciesId !== id) errors.push(`This set is for ${result.sets[0].name}, but ${dex.species.get(id)!.name} is selected.`);
        if (errors.length) { ioResult(errors, result.warnings); return; }
        host.setSet(id!, result.sets[0].set); renderSetEditor(); renderResults();
        ioResult([], result.warnings, `Set applied to ${result.sets[0].name}.`); return;
      }
      if (result.sets.length > 6) errors.push('A team has at most six Pokémon.');
      const ids = result.sets.map(entry => entry.speciesId);
      if (new Set(ids).size !== ids.length) errors.push('Each Pokémon can appear only once in the planner.');
      if (errors.length) { ioResult(errors, result.warnings); return; }
      host.replaceTeam(ids, Object.fromEntries(result.sets.map(entry => [entry.speciesId, entry.set])));
      renderAll(); ioResult([], result.warnings, `Imported ${ids.length} Pokémon. Nothing was changed elsewhere.`);
    }
  });
  panel.addEventListener('input', event => {
    const input = event.target as HTMLInputElement;
    if (input.id === 'tb-bc-query') {
      query = input.value; shown = PAGE;
      renderPicker();
    }
  });
  panel.addEventListener('change', event => {
    const input = event.target as HTMLInputElement;
    // A typed field fires "change" as focus leaves it: re-render once focus has reached the next control, so
    // keepFocus can put it back there (Tab keeps working).
    if (input.tagName === 'INPUT' && input.type !== 'checkbox') setTimeout(() => onChange(input), 0);
    else onChange(input);
  });
  function onChange(input: HTMLInputElement) {
    const d = input.dataset;
    if (d.bcField) {
      const [who, ...rest] = d.bcField.split(':');
      if (who === 'tfoe') updateTrainerFoe(rest.join(':'), input.value, input);
      else updateSet(who, rest.join(':'), input.value, input);
    } else if (d.bcGlobal) {
      field[d.bcGlobal] = input.type === 'checkbox' ? input.checked : input.value;
      renderResults(); refreshFieldSummary();
    } else if (d.bcSide) {
      const [side, key] = d.bcSide.split(':');
      field[side] = { ...field[side], [key]: input.type === 'checkbox' ? input.checked : Number(input.value) };
      renderResults(); refreshFieldSummary();
    } else if (input.hasAttribute('data-bc-foe-species')) {
      const ids = dex.speciesByName.get(normalizeName(input.value)) ?? [];
      if (!ids.length) { input.setAttribute('aria-invalid', 'true'); host.status(`“${input.value}” isn’t a Pokémon in this game.`); return; }
      input.setAttribute('aria-invalid', 'false');
      host.setOpponent({ species: ids[0] }); foeIndex = 0; renderFoe(); renderResults(); renderSetEditor(); announceOpponent();
    }
  }
  function refreshFieldSummary() { renderField(); }

  renderAll(); renderIO();
  if (!host.opponent()) $<HTMLInputElement>('query')?.focus({ preventScroll: true });

  return {
    /** The team, active member or opponent changed outside Battle check. */
    refresh() { renderAll(); },
    selectOpponent(opponent: Any) {
      if (opponent?.trainer != null && !trainerById.has(opponent.trainer)) { host.status('That trainer’s team couldn’t be found. Pick an opponent below.'); host.setOpponent(null); picking = true; }
      else if (opponent?.species && !dex.species.has(opponent.species)) { host.status('That Pokémon couldn’t be found. Pick an opponent below.'); host.setOpponent(null); picking = true; }
      else { host.setOpponent(opponent); picking = false; }
      foeIndex = 0; renderAll();
    },
  };
}
