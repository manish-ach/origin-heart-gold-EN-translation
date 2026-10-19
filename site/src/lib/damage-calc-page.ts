/**
 * The standalone damage calculator (/damage-calc/): the Team Builder's calculator without the planner around it.
 * It reads and writes the same saved team, sets and opponent (team-builder-state.mjs) and the same link format, so
 * both pages always show the same team. With no opponent yet, the trainer picker (every fight in route order) opens.
 */
import { escape, hues, artHtml, wireImages } from './team-builder-ui';
import {
  STORAGE_KEY_V2, TEAM_SIZE, loadStoredState, saveStoredState, parseStateHash, stateHash, sanitizeSets, sanitizeSet, sanitizeOpponent,
  replaceMember, removeMember,
} from './team-builder-state.mjs';

/** [record id, base species id, form id, first type, 1 = can join a team] for every species (artwork and joining). */
type Row = [number, number, number, string, number];

export function setupDamageCalc() {
  const root = document.querySelector<HTMLElement>('#team-builder.tb-calc-page');
  if (!root || root.dataset.ready) return;
  root.dataset.ready = 'true';
  const rows: Row[] = JSON.parse(document.querySelector('#tb-calc-data')!.textContent!);
  const byId = new Map(rows.map(row => [row[0], row]));
  const knownIds = new Set(rows.filter(row => row[4]).map(row => row[0]));
  const get = <T extends HTMLElement = HTMLElement>(id: string) => root.querySelector<T>(`#tb-${id}`)!;
  const url = (path: string) => `${root.dataset.base!.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
  const status = (text: string) => { get('status').textContent = text; };

  let team: number[] = [];
  let sets: Record<number, any> = {};
  let opponent: any = null;
  let storageAvailable = true;
  try { ({ team, sets, opponent } = loadStoredState(localStorage, knownIds)); } catch { storageAvailable = false; }
  const linked = parseStateHash(location.hash, knownIds);
  // A shared team (and its sets) takes precedence over browser storage, as in the Team Builder, except in this
  // page's own history entries (Back, Forward, reload), whose link may hold an older team than the saved one.
  if (linked.team && !(history.state?.tb && storageAvailable)) { team = linked.team; sets = linked.sets ?? {}; }
  if (linked.opponent !== undefined) opponent = linked.opponent;
  let active: number | null = team[0] ?? null;

  // Same history rules as the Team Builder: team and set changes replace the entry, a new opponent adds one.
  let lastHash = '';
  function persist(push = false) {
    sets = sanitizeSets(sets, team);
    try { saveStoredState(localStorage, { team, sets, opponent }); storageAvailable = true; } catch { storageAvailable = false; }
    get('save-status').textContent = storageAvailable
      ? '✓ Saved in this browser. The Team Builder shows the same team.'
      : 'Browser storage is unavailable. Copy this page’s link to keep your team.';
    writeLink(push);
  }
  /** The link and the Team Builder link for the current state, without saving (see the storage listener). */
  function writeLink(push = false) {
    try { history[push ? 'pushState' : 'replaceState']({ tb: true, view: 'battle' }, '', `${location.pathname}${location.search}${stateHash({ team, sets, opponent }, { battle: true })}`); }
    catch { /* still works when history is disabled */ }
    lastHash = location.hash;
    // The Team Builder reads the saved team; the link carries it only when there is no storage.
    get<HTMLAnchorElement>('builder-link').href = `${url('/team-builder/')}${storageAvailable ? '' : stateHash({ team, sets })}`;
  }

  let battle: { refresh(): void; selectOpponent(opponent: any): void } | null = null;
  const body = get('battle-body');
  function open() {
    body.setAttribute('aria-busy', 'true');
    body.innerHTML = '<p class="tb-help">Loading the damage calculator…</p>';
    import('./battle-check').then(({ mountBattleCheck }) => mountBattleCheck({
      root, panel: body, url, escape, hues, wireImages,
      art: (id, size = 'sm') => { const row = byId.get(id); return row ? artHtml(row[1], row[2], row[3], ` tb-art-${size}`) : '<span class="tb-art"></span>'; },
      team: () => team, active: () => active,
      setActive: id => { active = id; },
      sets: () => sets,
      setSet: (id, set) => { const clean = sanitizeSet(set); if (clean) sets[id] = clean; else delete sets[id]; persist(); },
      opponent: () => opponent,
      setOpponent: (next, push) => { opponent = sanitizeOpponent(next); persist(push); },
      replaceTeam: (ids, next) => { team = ids.filter(id => knownIds.has(id)).slice(0, TEAM_SIZE); sets = sanitizeSets(next, team); active = team[0] ?? null; persist(); },
      replaceMember: (oldId, newId) => {
        const next = replaceMember({ team, sets }, oldId, newId, knownIds);
        if (!next.team) { status(next.reason === 'full' ? 'Your team is full. Remove or swap a Pokémon to add another.' : 'That Pokémon can’t join your team.'); return false; }
        ({ team, sets, active } = next); persist(); return true;
      },
      removeMember: id => { ({ team, sets, active } = removeMember({ team, sets, active }, id)); persist(); },
      canJoin: id => knownIds.has(id),
      status,
    })).then(view => { battle = view; body.setAttribute('aria-busy', 'false'); })
      .catch(() => {
        body.setAttribute('aria-busy', 'false');
        body.innerHTML = '<p>Couldn’t load the damage calculator. Your team is still saved in the page.</p><button type="button" data-battle-retry>Try again</button>';
      });
  }
  root.addEventListener('click', event => {
    if ((event.target as Element).closest('[data-battle-retry]')) open();
  });
  // Back/Forward: the opponent comes from the entry; the team stays as it is now.
  window.addEventListener('popstate', event => {
    if (!event.state?.tb) return;
    opponent = parseStateHash(location.hash, knownIds).opponent ?? null;
    battle?.selectOpponent(opponent);
    persist();
  });
  // A newly opened link (a trainer's "Damage calc" link while this page is open, or a pasted one).
  window.addEventListener('hashchange', () => {
    if (location.hash === lastHash) return;
    const shared = parseStateHash(location.hash, knownIds);
    if (shared.team !== null) { team = shared.team; sets = shared.sets ?? {}; active = team[0] ?? null; }
    if (shared.opponent !== undefined) { opponent = shared.opponent; battle?.selectOpponent(opponent); }
    else battle?.refresh();
    persist();
  });
  // The saved team changed in another tab, or while this page waited in the browser's cache: show it here too.
  // The opponent stays, and nothing is saved back, so two open tabs never overwrite each other.
  function reloadSaved() {
    try { ({ team, sets } = loadStoredState(localStorage, knownIds)); } catch { return; }
    if (active == null || !team.includes(active)) active = team[0] ?? null;
    writeLink();
    battle?.refresh();
  }
  window.addEventListener('storage', event => { if (event.key === STORAGE_KEY_V2) reloadSaved(); });
  window.addEventListener('pageshow', event => { if (event.persisted) reloadSaved(); });
  root.querySelector<HTMLElement>('.tb-app')!.hidden = false;
  persist();
  open();
}
