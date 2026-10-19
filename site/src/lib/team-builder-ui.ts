import { TEAM_SIZE, filterCatalog, availableTeamPokemon } from './team-builder.mjs';
import { loadStoredState, saveStoredState, parseStateHash, stateHash, sanitizeSets, sanitizeSet, sanitizeOpponent, replaceMember, removeMember } from './team-builder-state.mjs';
import { encounterChance } from './encounter-format.mjs';
import { referenceArtwork } from '../../../work/save-editor/src/ui/artwork';
import { formatTimeHints } from './time-hints.mjs';
import { formatCatchHint } from './catch-hints.mjs';
import { formatEncounterHints } from './encounter-hints.mjs';

type Mon = { id: number; name: string; slug: string; baseSpeciesId: number; formId: number; types: string[]; region: string; stats: number[]; abilities: string[]; hidden: string | null; availability: string };
export const escape = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!);
const labels: Record<string, string> = { documented: 'Documented source', unknown: 'No known source', battle: 'Battle only', unavailable: 'Unavailable' };
const kinds: Record<string, string> = { gift: 'Gift', egg: 'Gift Egg', trade: 'Trade', loan: 'Loan', 'loan-return': 'Loan return', starter: 'Starter choice', prize: 'Prize', static: 'Scripted encounter' };
export const hues: Record<string, number> = { Normal: 42, Grass: 140, Poison: 280, Fire: 22, Water: 205, Electric: 46, Ice: 182, Fighting: 10, Ground: 32, Flying: 220, Psychic: 326, Bug: 85, Rock: 40, Ghost: 268, Dragon: 250, Dark: 255, Steel: 195, Fairy: 330 };
/** Pokémon artwork in its type-coloured frame (shared with the damage calculator page). */
export function artHtml(baseSpeciesId: number, formId: number, type: string, extra = '') {
  const image = referenceArtwork(baseSpeciesId, formId);
  return `<span class="tb-art${extra}" style="--mon-hue:${hues[type] ?? 42}">${image ? `<img src="${escape(image.src)}" data-fallback="${escape(image.fallback)}" alt="" width="128" height="128" loading="lazy" />` : '<span class="tb-art-empty" aria-hidden="true">◇</span>'}</span>`;
}
/** Falls back to the second artwork source, then hides a missing image. */
export const wireImages = (parent: HTMLElement) => parent.querySelectorAll<HTMLImageElement>('img[data-fallback]').forEach(img => {
  img.addEventListener('error', () => {
    if (img.dataset.fallback) { const fallback = img.dataset.fallback; delete img.dataset.fallback; img.src = fallback; }
    else { img.hidden = true; img.parentElement!.classList.add('tb-art-unavailable'); }
  });
});

export function setupTeamBuilder() {
  const root = document.querySelector<HTMLElement>('#team-builder');
  if (!root || root.dataset.ready) return;
  root.dataset.ready = 'true';
  const catalog: Mon[] = JSON.parse(document.querySelector('#tb-data')!.textContent!);
  const byId = new Map(catalog.map(mon => [mon.id, mon]));
  const availableCatalog: Mon[] = availableTeamPokemon(catalog);
  const knownIds = new Set(availableCatalog.map(mon => mon.id));
  const get = <T extends HTMLElement = HTMLElement>(id: string) => root.querySelector<T>(`#tb-${id}`)!;
  const url = (path: string) => `${root.dataset.base!.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
  const link = (href: string | null, text: unknown) => href ? `<a href="${escape(url(href))}">${escape(text)}</a>` : escape(text);
  const types = (mon: Mon) => mon.types.map(type => `<span class="type type-${escape(type.toLowerCase())}">${escape(type)}</span>`).join('');
  const tone = (mon: Mon) => `style="--mon-hue:${hues[mon.types[0]] ?? 42}"`;
  const art = (mon: Mon, extra = '') => artHtml(mon.baseSpeciesId, mon.formId, mon.types[0], extra);
  let team: number[] = [];
  let sets: Record<number, any> = {};
  let opponent: any = null;
  let storageAvailable = true;
  try { ({ team, sets, opponent } = loadStoredState(localStorage, knownIds)); }
  catch { storageAvailable = false; }
  const linked = parseStateHash(location.hash, knownIds);
  // An explicit shared team (and its sets) takes precedence over browser storage.
  if (linked.team) { team = linked.team; sets = linked.sets ?? {}; }
  if (linked.opponent !== undefined) opponent = linked.opponent;
  let active: number | null = team[0] ?? null;
  let page = 0;
  let request = 0;
  const pageSize = 24;
  const cache = new Map<number, any>();
  const status = (text: string) => { get('status').textContent = text; };

  // The link always shows the current team. Team and set changes replace the history entry; entering or leaving
  // the calculator and picking another opponent add one (`push`), so Back returns to the previous view or opponent.
  // Entries carry {tb: true, view} so popstate can tell Back/Forward from a newly opened link.
  let lastHash = '';
  function persist(push = false) {
    sets = sanitizeSets(sets, team);
    try { saveStoredState(localStorage, { team, sets, opponent }); storageAvailable = true; }
    catch { storageAvailable = false; }
    get('save-status').textContent = storageAvailable
      ? '✓ Saved in this browser'
      : 'Browser storage is unavailable. Copy your team link to keep this team.';
    const hash = stateHash({ team, sets, opponent }, { battle: root.dataset.view === 'battle' });
    try { history[push ? 'pushState' : 'replaceState']({ tb: true, view: root.dataset.view }, '', `${location.pathname}${location.search}${hash}`); }
    catch { /* The planner still works when history is disabled. */ }
    lastHash = location.hash;
    get('share-fallback').hidden = true;
    get<HTMLAnchorElement>('open-calc').href = `${url('/damage-calc/')}${stateHash({ team, sets, opponent }, { battle: true })}`;
  }

  function renderTeam() {
    get('team-count').textContent = `${team.length} / ${TEAM_SIZE}`;
    get<HTMLButtonElement>('clear').disabled = !team.length;
    get('slots').innerHTML = Array.from({ length: TEAM_SIZE }, (_, index) => {
      const mon = byId.get(team[index]);
      return mon ? `<div class="tb-slot ${active === mon.id ? 'is-selected' : ''}" ${tone(mon)}>
        <button class="tb-slot-select" type="button" data-select="${mon.id}" aria-label="View ${escape(mon.name)} acquisition guide" aria-pressed="${active === mon.id}">
          <span class="tb-slot-number">${String(index + 1).padStart(2, '0')}</span>${art(mon)}<strong>${escape(mon.name)}</strong><span>${types(mon)}</span>
          ${mon.formId ? '<small>Standard-form artwork</small>' : ''}
          ${mon.availability !== 'documented' ? `<small class="tb-warning">${labels[mon.availability]}</small>` : ''}
        </button><button type="button" class="tb-remove" data-remove="${mon.id}" aria-label="Remove ${escape(mon.name)} from team">×</button>
      </div>` : `<button type="button" class="tb-slot tb-empty-slot" data-empty aria-label="Find a Pokémon for slot ${index + 1}"><span class="tb-slot-number">${String(index + 1).padStart(2, '0')}</span><span class="tb-plus" aria-hidden="true">+</span><span>Who's next?</span></button>`;
    }).join('');
    wireImages(get('slots'));
    const counts = new Map<string, number>();
    for (const id of team) for (const type of byId.get(id)!.types) counts.set(type, (counts.get(type) ?? 0) + 1);
    get('summary').innerHTML = team.length ? [...counts].map(([type, count]) => `<span class="tb-team-type" style="--mon-hue:${hues[type] ?? 42}"><i aria-hidden="true"></i>${escape(type)} <b>${count}</b></span>`).join('') : '<span class="tb-help">Six spots. Make them yours.</span>';
  }

  function renderCatalog() {
    const matches: Mon[] = filterCatalog(availableCatalog, {
      query: get<HTMLInputElement>('search').value, type: get<HTMLSelectElement>('type').value,
      region: get<HTMLSelectElement>('region').value,
    });
    const pages = Math.max(1, Math.ceil(matches.length / pageSize));
    page = Math.min(page, pages - 1);
    get('result-count').textContent = `${matches.length.toLocaleString()} Pokémon`;
    get('page').textContent = `Page ${page + 1} of ${pages}`;
    get<HTMLButtonElement>('previous').disabled = page === 0;
    get<HTMLButtonElement>('next').disabled = page + 1 === pages;
    get('catalog').innerHTML = matches.length ? matches.slice(page * pageSize, (page + 1) * pageSize).map(mon => {
      const added = team.includes(mon.id), full = team.length === TEAM_SIZE && !added;
      return `<button type="button" class="tb-mon ${added ? 'is-added' : ''}" ${tone(mon)} data-add="${mon.id}" aria-label="${added ? 'View' : 'Add'} ${escape(mon.name)}${added ? ' acquisition guide' : ' to team'}" ${full ? 'disabled' : ''}>
        <span class="tb-dex">#${String(mon.baseSpeciesId).padStart(3, '0')}</span><span class="tb-mon-action" aria-hidden="true">${added ? '✓' : full ? '−' : '+'}</span>
        ${art(mon)}<strong>${escape(mon.name)}</strong><span>${types(mon)}</span>
        ${mon.formId ? '<small>Standard-form artwork</small>' : ''}
        ${mon.availability !== 'documented' ? `<small class="tb-warning">${labels[mon.availability]}</small>` : ''}
      </button>`;
    }).join('') : '<p class="tb-empty">No Pokémon match these filters. Try another name or reset the filters. Only Pokémon with a documented way to obtain them appear here.</p>';
    wireImages(get('catalog'));
  }

  function condition(step: any, compact = false) {
    let text = compact ? step.text.replace(/^Level up at Lv (\d+)$/, 'Lv. $1') : step.text;
    let result = '';
    // Link named requirements before adding time hints: Morning Sun is a move, not a time.
    while (text) {
      const next = step.links.map((entry: any) => ({ ...entry, index: text.indexOf(entry.name) })).filter((entry: any) => entry.index >= 0).sort((a: any, b: any) => a.index - b.index)[0];
      if (!next) { result += formatTimeHints(text, 'evolution'); break; }
      result += formatTimeHints(text.slice(0, next.index), 'evolution') + link(next.href, next.name);
      text = text.slice(next.index + next.name.length);
    }
    return result;
  }

  function evolutionStep(step: any) {
    const from = byId.get(step.from.id), to = byId.get(step.to.id);
    return `<li class="tb-alternative ${step.blocked ? 'tb-blocked' : ''}"><div class="tb-mini-path">${from ? art(from) : ''}${link(step.from.href, step.from.name)} <span aria-hidden="true">→</span>${to ? art(to) : ''}${link(step.to.href, step.to.name)}</div>
      <p>${step.blocked ? '<strong>Unavailable method. </strong>' : step.kind === 'form' ? '<strong>Held-item form. </strong>' : ''}${condition(step)}</p></li>`;
  }

  function evolutionJourney(detail: any) {
    const nodes = [detail.id], chosen: any[] = [];
    const seen = new Set(nodes);
    let current = detail.id;
    while (true) {
      const candidates = detail.steps.filter((step: any) => step.to.id === current && !step.blocked && !seen.has(step.from.id));
      candidates.sort((a: any, b: any) => Number(byId.get(a.from.id)?.availability !== 'documented') - Number(byId.get(b.from.id)?.availability !== 'documented'));
      const step = candidates[0];
      if (!step) break;
      chosen.unshift(step); nodes.unshift(step.from.id); seen.add(step.from.id); current = step.from.id;
    }
    const alternatives = detail.steps.filter((step: any) => !chosen.includes(step));
    return `<div class="tb-journey" role="group" aria-label="Evolution path">${nodes.map((id, i) => {
      const mon = byId.get(id)!;
      return `<div class="tb-stage ${id === detail.id ? 'tb-stage-selected' : ''}" ${tone(mon)}>
        ${i ? '<span class="tb-path-arrow" aria-hidden="true">→</span>' : ''}
        <button type="button" data-stage="${id}" aria-label="Show ${escape(mon.name)} catch locations">${art(mon)}<strong>${escape(mon.name)}</strong><span class="tb-stage-tag">${id === detail.id ? 'Your pick' : i === 0 ? 'Start here' : 'Evolve'}</span></button>
        ${i ? `<div class="tb-evo-condition">${chosen[i - 1].kind === 'form' ? '<span class="tb-help">Held-item form</span>' : ''}${condition(chosen[i - 1], true)}</div>` : ''}
      </div>`;
    }).join('')}</div>${alternatives.length ? `<details class="tb-more"><summary>Other routes &amp; unavailable methods <span>${alternatives.length}</span></summary><ul class="tb-evolution">${alternatives.map(evolutionStep).join('')}</ul></details>` : ''}`;
  }

  function sources(member: any, isSelected: boolean) {
    const wildTable = (rows: any[]) => `<ul class="tb-encounters" aria-label="${escape(member.name)} encounter locations">${rows.map(enc => `<li><div>${link(enc.href, enc.place)}<span class="tb-method">${formatEncounterHints(enc.method)}</span></div><div class="tb-encounter-rate"><strong title="Encounter chance">${escape(encounterChance(enc))}</strong><span>Lv. ${escape(enc.level ?? '—')}</span></div></li>`).join('')}</ul>`;
    const notes = [...new Set(member.wild.flatMap((enc: any) => enc.notes))];
    const mon = byId.get(member.id)!;
    const places = new Set(member.wild.map((enc: any) => enc.area)).size;
    const sourceSummary = [places ? `${places} wild ${places === 1 ? 'location' : 'locations'}` : '', member.acquisitions.length ? `${member.acquisitions.length} ${member.acquisitions.length === 1 ? 'gift / trade' : 'gifts / trades'}` : '', member.calendar.length ? 'Calendar event' : ''].filter(Boolean).join(' · ') || (member.unavailableReason ? 'Unavailable' : member.otherSources || 'See requirements');
    return `<details class="tb-source" id="tb-source-${member.id}">
      <summary>${art(mon)}<span class="tb-source-name"><strong>${escape(member.name)}</strong><span>${escape(sourceSummary)}</span></span><span class="tb-source-toggle" aria-hidden="true">+</span></summary>
      <div class="tb-source-body">
        <div class="tb-source-facts"><span>${isSelected ? 'Your pick' : 'Earlier stage / base form'}</span><span>${formatCatchHint(member.catchRate)}</span></div>
        ${member.unavailableReason ? `<p class="tb-warning"><strong>Unavailable in normal play.</strong> ${escape(member.unavailableReason)}</p>` : ''}
        ${member.battleOnly ? `<p class="tb-warning">${escape(member.battleOnly)}</p>` : ''}
        ${member.acquisitions.length ? `<ul class="tb-acquisitions">${member.acquisitions.map((source: any) => `<li><strong>${escape(kinds[source.kind] ?? source.kind)}${source.level != null ? ` · Lv. ${source.level}` : ''}</strong> — ${link(source.href, source.place)}.
          ${source.offer ? ` Give ${link(source.offer.href, source.offer.name)} in exchange.` : ''} ${escape(source.conditions)}
          ${source.quests.map((quest: any) => link(quest.href, quest.title)).join(' · ')}</li>`).join('')}</ul>` : ''}
        ${member.wild.length ? wildTable(member.wild.slice(0, 3)) : ''}
        ${member.wild.length > 3 ? `<details class="tb-more"><summary>Show ${member.wild.length - 3} more encounters</summary>${wildTable(member.wild.slice(3))}</details>` : ''}
        ${notes.map(note => `<p class="tb-help">${escape(note)}</p>`).join('')}
        ${member.calendar.length ? `<ul class="tb-calendar">${member.calendar.map((event: any) => `<li><strong>${escape(event.date)} · ${formatTimeHints(event.period)}</strong> — ${link(`/locations/${event.area}/#calendar`, event.place)}${event.level != null ? ` · Lv. ${event.level}` : ''}. ${event.status === 'configured' ? '' : '<strong>Availability not confirmed. </strong>'}${escape(event.note)}</li>`).join('')}</ul>` : ''}
        ${member.otherSources ? `<p>${escape(member.otherSources)}</p>` : ''}
        ${!member.wild.length && !member.acquisitions.length && !member.calendar.length && !member.otherSources ? `<p>${member.unavailableReason ? 'No obtainable source is documented.' : 'No direct catch or gift source is documented. Check the evolution or form requirements above.'} ${escape(member.note)}</p>` : ''}
        ${member.quests.length ? `<p class="tb-help">Quest conditions: ${member.quests.map((quest: any) => link(quest.href, quest.title)).join(' · ')}</p>` : ''}
        <p class="tb-help">${link(member.href, `Full ${member.name} Pokédex entry`)}</p>
      </div></details>`;
  }

  async function renderDetails() {
    const token = ++request, id = active;
    const panel = get('details');
    if (id == null) {
      panel.setAttribute('aria-busy', 'false');
      panel.innerHTML = '<div class="tb-empty"><span class="tb-empty-mark" aria-hidden="true">✦</span><strong>Meet your next teammate.</strong><span>Pick a Pokémon to explore its evolution<br />and find your first encounter.</span></div>';
      return;
    }
    const mon = byId.get(id)!;
    panel.setAttribute('aria-busy', 'true');
    panel.innerHTML = `<p>Loading ${escape(mon.name)}’s acquisition guide…</p>`;
    try {
      if (!cache.has(id)) {
        const response = await fetch(url(`/team-builder/pokemon/${id}.json`));
        if (!response.ok) throw new Error('Could not load acquisition data');
        const data = await response.json();
        if (data.id !== id || !Array.isArray(data.members)) throw new Error('Invalid acquisition data');
        cache.set(id, data);
      }
      if (token !== request) return;
      const detail = cache.get(id);
      const members = detail.members;
      const evolutionNotes = [...new Set(detail.members.flatMap((member: any) => member.evoNotes))];
      panel.innerHTML = `<div class="tb-detail-heading" ${tone(mon)}><div><span class="tb-eyebrow">#${String(mon.baseSpeciesId).padStart(3, '0')} · ${escape(mon.region)}</span><h3>${escape(mon.name)}</h3><span>${types(mon)}</span><p>${link(`/pokemon/${mon.slug}/`, 'Pokédex →')}</p>${mon.formId ? '<small class="tb-help">Standard-form artwork</small>' : ''}</div>${art(mon)}</div>
        <details class="tb-stat-details"><summary>Base stats &amp; abilities <span>BST ${mon.stats.reduce((a, b) => a + b, 0)}</span></summary><div class="tb-stat-grid">${['HP', 'Attack', 'Defense', 'Sp. Atk', 'Sp. Def', 'Speed'].map((name, i) => `<div><span>${name}</span><strong>${mon.stats[i]}</strong><i style="--stat:${Math.min(100, mon.stats[i] / 2)}%"></i></div>`).join('')}</div>
        <p class="tb-help">${escape(mon.abilities.join(' / ') || 'None documented')}${mon.hidden ? ` · Hidden: ${escape(mon.hidden)}` : ''}</p></details>
        <h4>Evolution journey <span>${detail.steps.length ? 'Tap a stage to find it' : ''}</span></h4>
        ${evolutionJourney(detail)}
        ${evolutionNotes.length ? `<details class="tb-more tb-evolution-notes"><summary>Before you evolve <span>${evolutionNotes.length} ${evolutionNotes.length === 1 ? 'tip' : 'tips'}</span></summary>${evolutionNotes.map(note => `<p class="tb-evolution-note">${escape(note)}</p>`).join('')}</details>` : ''}
        ${detail.next.length ? `<details class="tb-more"><summary>What ${escape(mon.name)} can become</summary><ul class="tb-evolution">${detail.next.map(evolutionStep).join('')}</ul></details>` : ''}
        <h4>Find &amp; catch <span>Locations, times &amp; conditions</span></h4>
        ${members.map((member: any) => sources(member, member.id === id)).join('')}`;
      wireImages(panel);
    } catch {
      if (token !== request) return;
      panel.innerHTML = `<p>Couldn’t load this acquisition guide. Your team is still saved in the page.</p><button type="button" data-retry>Try again</button> ${link(`/pokemon/${mon.slug}/`, `Open ${mon.name} in the Pokédex`)}`;
    } finally { if (token === request) panel.setAttribute('aria-busy', 'false'); }
  }

  // Damage calculator: its code, the damage engine and their data load only when it is opened.
  let battle: { refresh(): void; selectOpponent(opponent: any): void; openMemberPicker(): void } | null = null;
  let battleLoading: Promise<void> | null = null;
  let battleStale = false;
  function openBattle() {
    if (battle || battleLoading) return;
    const body = get('battle-body');
    body.setAttribute('aria-busy', 'true');
    body.innerHTML = '<p class="tb-help">Loading the damage calculator…</p>';
    battleLoading = import('./battle-check').then(({ mountBattleCheck }) => mountBattleCheck({
      root, panel: body, url, escape, hues, wireImages,
      art: (id, size = 'sm') => { const mon = byId.get(id); return mon ? art(mon, ` tb-art-${size}`) : '<span class="tb-art"></span>'; },
      team: () => team, active: () => active,
      setActive: id => { active = id; renderTeam(); void renderDetails(); },
      sets: () => sets,
      setSet: (id, set) => { const clean = sanitizeSet(set); if (clean) sets[id] = clean; else delete sets[id]; persist(); },
      opponent: () => opponent,
      setOpponent: (next, push) => { opponent = sanitizeOpponent(next); persist(push); },
      replaceTeam: (ids, next) => { team = ids.filter(id => knownIds.has(id)).slice(0, TEAM_SIZE); sets = sanitizeSets(next, team); active = team[0] ?? null; update(); },
      // Team changes from inside the calculator: it redraws itself, and the view and opponent stay.
      replaceMember: (oldId, newId) => {
        const next = replaceMember({ team, sets }, oldId, newId, knownIds);
        if (!next.team) { status(next.reason === 'full' ? 'Your team is full. Remove or swap a Pokémon to add another.' : 'That Pokémon can’t join your team.'); return false; }
        ({ team, sets, active } = next); planner(); return true;
      },
      removeMember: id => { ({ team, sets, active } = removeMember({ team, sets, active }, id)); planner(); },
      canJoin: id => knownIds.has(id),
      status,
    })).then(view => { battle = view; battleStale = false; body.setAttribute('aria-busy', 'false'); })
      .catch(() => {
        battleLoading = null;
        body.setAttribute('aria-busy', 'false');
        body.innerHTML = '<p>Couldn’t load the damage calculator. Your team is still saved in the page.</p><button type="button" data-battle-retry>Try again</button>';
      });
  }
  function showView(view: string) {
    root.dataset.view = view;
    root.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === view)));
    if (view !== 'battle') return;
    openBattle();
    // After the caller's own updates (a linked opponent is checked first), so it never draws a stale opponent.
    if (battle && battleStale) queueMicrotask(() => { if (battleStale && root.dataset.view === 'battle') refreshBattle(); });
  }
  function refreshBattle() { battleStale = false; battle?.refresh(); }
  /** A view change the player asked for. Entering or leaving the calculator adds a history entry. */
  function switchView(view: string) {
    const from = root.dataset.view;
    if (from === view) return;
    const push = from === 'battle' || view === 'battle';
    // The entry being left remembers its view (the Field guide opens without a history entry of its own).
    if (push) { try { history.replaceState({ ...(history.state ?? {}), tb: true, view: from }, ''); } catch { /* no history */ } }
    showView(view);
    persist(push);
  }
  showView(linked.battle ? 'battle' : 'browse');
  // A hidden calculator is redrawn when it is shown again, not on every team change.
  function update() {
    planner();
    if (root.dataset.view === 'battle') refreshBattle(); else battleStale = true;
  }
  /** Everything but the calculator. */
  function planner() { persist(); renderTeam(); renderCatalog(); void renderDetails(); }
  /** The calculator's member picker, for the empty team slots while the calculator is open. */
  function addFromCalculator() { void battleLoading?.then(() => battle?.openMemberPicker()); }
  root.addEventListener('click', event => {
    const button = (event.target as Element).closest<HTMLButtonElement>('button');
    if (!button || button.disabled) return;
    if (button.dataset.view) {
      switchView(button.dataset.view);
      if (button.dataset.view === 'battle' && button.closest('.tb-guide')) get('battle-heading').scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
      return;
    }
    if (button.hasAttribute('data-battle-retry')) { openBattle(); return; }
    if (button.hasAttribute('data-battle-back')) { switchView('guide'); get('guide-heading').scrollIntoView({ block: 'start', behavior: 'instant' }); return; }
    if (button.dataset.stage) {
      const source = get<HTMLDetailsElement>(`source-${button.dataset.stage}`); source.open = true;
      source.querySelector('summary')?.focus({ preventScroll: true });
      source.scrollIntoView({ block: 'nearest', behavior: 'instant' }); return;
    }
    if (button.hasAttribute('data-empty')) {
      // In the calculator, a free slot is filled there: leaving it would lose the fight being prepared.
      if (root.dataset.view === 'battle') { addFromCalculator(); return; }
      showView('browse'); get('search').focus(); return;
    }
    if (button.hasAttribute('data-retry')) { void renderDetails(); return; }
    if (button.dataset.remove) {
      const id = Number(button.dataset.remove), index = team.indexOf(id);
      team = team.filter(member => member !== id);
      if (active === id) active = team[Math.min(index, team.length - 1)] ?? null;
      update(); status(`${byId.get(id)!.name} removed from your team.`);
      get('slots').querySelector<HTMLButtonElement>('[data-select], [data-empty]')?.focus();
    } else if (button.dataset.add || button.dataset.select) {
      const id = Number(button.dataset.add || button.dataset.select);
      if (!knownIds.has(id)) return;
      if (!team.includes(id)) {
        if (team.length === TEAM_SIZE) { status('Your team is full. Remove a Pokémon to add another.'); return; }
        team.push(id); status(`${byId.get(id)!.name} added. ${team.length} of ${TEAM_SIZE} slots filled.`);
      }
      active = id; update();
      const selector = button.dataset.add ? `[data-add="${id}"]` : `[data-select="${id}"]`;
      root.querySelector<HTMLButtonElement>(selector)?.focus({ preventScroll: true });
      if (button.dataset.select && root.dataset.view === 'battle') { status(`${byId.get(id)!.name} selected in the damage calculator.`); return; }
      if (button.dataset.select) { showView('guide'); get('guide-heading').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }); }
    }
  });
  for (const id of ['search', 'type', 'region']) get(id).addEventListener(id === 'search' ? 'input' : 'change', () => { page = 0; renderCatalog(); });
  get('reset').addEventListener('click', () => {
    for (const id of ['search', 'type', 'region']) get<HTMLInputElement>('' + id).value = '';
    page = 0; renderCatalog(); get('search').focus();
  });
  get('previous').addEventListener('click', () => { page--; renderCatalog(); });
  get('next').addEventListener('click', () => { page++; renderCatalog(); });
  get('clear').addEventListener('click', () => { team = []; sets = {}; active = null; if (root.dataset.view !== 'battle') showView('browse'); update(); status('Team cleared. Choose a Pokémon to start again.'); get('search').focus(); });
  get('share').addEventListener('click', async () => {
    const href = new URL(location.href); href.hash = stateHash({ team, sets, opponent }, { battle: root.dataset.view === 'battle' });
    try { await navigator.clipboard.writeText(href.href); status('Team link copied. Anyone with this link can open your team.'); }
    catch { get('share-fallback').hidden = false; const input = get<HTMLInputElement>('share-url'); input.value = href.href; input.focus(); input.select(); status('Copy the selected link to share your team.'); }
  });
  // Back/Forward between the planner's own entries: the view and the opponent come from the entry, the team stays
  // as it is now (an older entry's link may hold an older team). A newly opened link is handled by hashchange.
  window.addEventListener('popstate', event => {
    if (!event.state?.tb) return;
    const shared = parseStateHash(location.hash, knownIds);
    if (shared.battle) {
      opponent = shared.opponent ?? null;
      showView('battle');
      battle?.selectOpponent(opponent);
    } else showView(event.state.view === 'battle' ? 'browse' : event.state.view ?? 'browse');
    update();
  });
  window.addEventListener('hashchange', () => {
    if (location.hash === lastHash) return; // already handled by popstate, or written by persist
    const shared = parseStateHash(location.hash, knownIds);
    if (shared.team !== null) { team = shared.team; sets = shared.sets ?? {}; active = team[0] ?? null; }
    if (shared.battle) {
      if (shared.opponent !== undefined) { opponent = shared.opponent; }
      showView('battle');
      if (battle && shared.opponent !== undefined) battle.selectOpponent(shared.opponent);
    }
    if (shared.team !== null || shared.battle) update();
  });
  root.querySelector<HTMLElement>('.tb-app')!.hidden = false;
  update();
}
