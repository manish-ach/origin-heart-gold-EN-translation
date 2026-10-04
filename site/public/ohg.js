// Origin HeartGold guide: small progressive enhancements. Everything works without this script.
// - quest pages: game setup (starter, gender, post-game), per-quest "done" ticks, report links
// - tables/lists: text filter, select and checkbox filters, click-to-sort headers
(() => {
	const store = {
		get(k, d) { try { const v = localStorage.getItem('ohg:' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
		set(k, v) { try { localStorage.setItem('ohg:' + k, JSON.stringify(v)); } catch { /* private mode */ } },
	};
	const repo = document.querySelector('meta[name="ohg-repo"]')?.content;

	// ---------------------------------------------------------------- technical references
	// Script files, flags and code addresses are hidden by CSS (.tech). Maintainers turn them on in their own
	// browser by opening any page with ?tech=1 (remembered), and off again with ?tech=0.
	const techParam = new URLSearchParams(location.search).get('tech');
	if (techParam !== null) store.set('tech', techParam === '1');
	if (store.get('tech', false)) document.documentElement.dataset.tech = 'on';

	// ---------------------------------------------------------------- quests
	// "Done" ticks are stored per page and quest: "guide/<page>#<heading id>", or the quest's own id when the
	// guide gives one (<section data-quest-id>). Version 1 stored bare heading ids, which two pages could share
	// ("small-extras"); those are carried over page by page, except the shared ones (data-legacy-shared).
	function pageKey() {
		const m = location.pathname.match(/\/(guide\/[^/]+)\/?(?:index\.html)?$/);
		return m ? m[1] : location.pathname.replace(/\/+$/, '');
	}
	function asArray(v) { return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []; }

	function setupQuests() {
		const quests = [...document.querySelectorAll('section.quest')];
		if (!quests.length) return;
		const page = pageKey();
		const keyOf = (q) => {
			if (q.dataset.questId) return 'quest:' + q.dataset.questId;
			const id = q.querySelector('h2')?.id;
			return id ? page + '#' + id : null;
		};
		const done = new Set(asArray(store.get('done2', [])));
		// one-time migration of this page's version-1 ticks
		const migrated = new Set(asArray(store.get('done2-migrated', [])));
		if (!migrated.has(page)) {
			const legacy = new Set(asArray(store.get('done', [])));
			if (legacy.size) {
				for (const q of quests) {
					const id = q.querySelector('h2')?.id;
					const key = keyOf(q);
					if (id && key && legacy.has(id) && !q.dataset.legacyShared) done.add(key);
				}
				store.set('done2', [...done]);
			}
			migrated.add(page);
			store.set('done2-migrated', [...migrated]);
		}
		let setup = store.get('setup', null);
		if (!setup || typeof setup !== 'object') setup = { starter: '', gender: '', postgame: true };

		const panel = document.createElement('div');
		panel.className = 'game-setup not-content';
		panel.innerHTML = `
			<strong>Your game</strong>
			<label>Starter <select name="starter"><option value="">Any</option><option>Charmander</option><option>Pikachu</option><option>Bulbasaur</option></select></label>
			<label>Playing as <select name="gender"><option value="">Either</option><option value="male">Boy</option><option value="female">Girl</option></select></label>
			<label title="Quests that open only after your final Hall of Fame entry"><input type="checkbox" name="postgame"> Show quests after the final Hall of Fame</label>
			<label><input type="checkbox" name="hidedone"> Hide finished</label>
			<span class="hidden-count" aria-live="polite"></span>`;
		const content = document.querySelector('.sl-markdown-content');
		content?.prepend(panel);
		const $ = (n) => panel.querySelector(`[name="${n}"]`);
		$('starter').value = ['Charmander', 'Pikachu', 'Bulbasaur'].includes(setup.starter) ? setup.starter : '';
		$('gender').value = ['male', 'female'].includes(setup.gender) ? setup.gender : '';
		$('postgame').checked = setup.postgame !== false; $('hidedone').checked = !!setup.hidedone;

		for (const q of quests) {
			const h = q.querySelector('h2');
			const id = h?.id;
			const key = keyOf(q);
			if (!id || !key) continue;
			const tools = document.createElement('p');
			tools.className = 'quest-tools not-content';
			const issue = repo ? `${repo}/issues/new?template=guide-problem.yml&page=${encodeURIComponent(location.pathname + '#' + id)}&title=${encodeURIComponent('[' + h.textContent.trim() + '] ')}` : '';
			tools.innerHTML = `<label><input type="checkbox"> Done</label>${issue ? `<a href="${issue}" rel="noopener">Report a problem with this quest</a>` : ''}`;
			const box = tools.querySelector('input');
			box.checked = done.has(key);
			q.classList.toggle('is-done', box.checked);
			box.addEventListener('change', () => {
				box.checked ? done.add(key) : done.delete(key);
				q.classList.toggle('is-done', box.checked);
				store.set('done2', [...done]);
				apply();
			});
			(q.querySelector('.quest-meta') || h).after(tools);
		}

		// the quest a link points at is never hidden
		const hashQuest = () => {
			let t = null;
			try { t = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null; } catch { /* bad hash */ }
			return t?.closest('section.quest') || null;
		};

		function apply() {
			const s = { starter: $('starter').value, gender: $('gender').value, postgame: $('postgame').checked, hidedone: $('hidedone').checked };
			store.set('setup', s);
			const target = hashQuest();
			let hidden = 0;
			for (const q of quests) {
				const st = q.dataset.starter?.split(',');
				const g = q.dataset.gender?.split(',');
				const key = keyOf(q);
				const hide = q !== target && ((s.starter && st && !st.includes(s.starter)) || (s.gender && g && !g.includes(s.gender)) ||
					(!s.postgame && q.dataset.postgame) || (s.hidedone && key && done.has(key)));
				q.classList.toggle('is-hidden', !!hide);
				if (hide) hidden++;
			}
			panel.querySelector('.hidden-count').textContent = hidden ? `${hidden} quest${hidden > 1 ? 's' : ''} hidden for your game` : '';
			// keep the page's table of contents in step
			document.querySelectorAll('starlight-toc a, mobile-starlight-toc a').forEach((a) => {
				let t = null;
				try { t = document.getElementById(decodeURIComponent(a.hash.slice(1))); } catch { /* bad hash */ }
				const sec = t?.closest('section.quest');
				a.parentElement.style.display = sec?.classList.contains('is-hidden') ? 'none' : '';
			});
		}
		panel.addEventListener('change', apply);
		// a link to a hidden quest still shows it, also for links on the same page
		window.addEventListener('hashchange', () => {
			apply();
			hashQuest()?.querySelector('h2')?.scrollIntoView();
		});
		apply();
	}

	// ---------------------------------------------------------------- tables and lists
	function setupFilters() {
		for (const f of document.querySelectorAll('.table-filter')) {
			const target = document.getElementById(f.dataset.table);
			if (!target) continue;
			const rows = [...target.querySelectorAll('tbody tr, [data-row]')];
			const text = rows.map((r) => r.textContent.toLowerCase());
			const input = f.querySelector('input[type="search"]');
			const selects = [...f.querySelectorAll('select[data-key]')];
			const checks = [...f.querySelectorAll('input[type="checkbox"][data-key]')];
			const count = f.querySelector('.filter-count');
			const run = () => {
				const q = (input?.value || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
				let n = 0;
				rows.forEach((r, i) => {
					let ok = q.every((w) => text[i].includes(w));
					for (const s of selects) if (ok && s.value && r.dataset[s.dataset.key] !== s.value) ok = false;
					for (const c of checks) if (ok && !c.checked && r.dataset[c.dataset.key] === c.dataset.showValue) ok = false;
					r.hidden = !ok;
					if (ok) n++;
				});
				if (count) count.textContent = `${n} shown`;
			};
			f.addEventListener('input', run);
			f.addEventListener('change', run);
			run();
		}
		for (const t of document.querySelectorAll('table.sortable')) {
			const ths = [...t.querySelectorAll('thead th')];
			const sortBy = (th, col) => {
				const dir = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
				ths.forEach((x) => x.removeAttribute('aria-sort'));
				th.setAttribute('aria-sort', dir);
				const body = t.tBodies[0];
				const key = (r) => r.cells[col]?.textContent.trim() ?? '';
				const rows = [...body.rows].sort((a, b) => {
					const x = key(a), y = key(b);
					const nx = parseFloat(x.replace(/[$,]/g, '')), ny = parseFloat(y.replace(/[$,]/g, ''));
					const c = !isNaN(nx) && !isNaN(ny) ? nx - ny : x.localeCompare(y);
					return dir === 'ascending' ? c : -c;
				});
				body.append(...rows);
			};
			ths.forEach((th, col) => {
				// a real button inside each header, so the sort works from the keyboard too
				const btn = document.createElement('button');
				btn.type = 'button';
				btn.className = 'sort-button';
				btn.append(...th.childNodes);
				th.append(btn);
				btn.addEventListener('click', () => sortBy(th, col));
			});
		}
	}

	const init = () => { setupQuests(); setupFilters(); };
	document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
