// Origin HeartGold guide: small progressive enhancements. Everything works without this script.
// - quest pages: game setup and quest filters, per-quest "done" ticks, report links
// - guide pages on phones: steps and quests as rows that open on tap, a dock with Sections and Quests sheets
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
			<label>Quest type <select name="kind"><option value="">All quests</option><option value="main">Main quest</option><option value="side">Side quest</option></select></label>
			<label><input type="checkbox" name="hidedone"> Hide finished</label>
			<span class="hidden-count" role="status" aria-live="polite"></span>`;
		const content = document.querySelector('.sl-markdown-content');
		content?.prepend(panel);
		const $ = (n) => panel.querySelector(`[name="${n}"]`);
		$('starter').value = ['Charmander', 'Pikachu', 'Bulbasaur'].includes(setup.starter) ? setup.starter : '';
		$('gender').value = ['male', 'female'].includes(setup.gender) ? setup.gender : '';
		$('kind').value = ['main', 'side'].includes(setup.kind) ? setup.kind : '';
		$('hidedone').checked = !!setup.hidedone;

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

		// a quest is filtered out when the player's game can't get it (starter, gender) or it is the other quest type
		const filteredOut = (ds, s) => !!((s.starter && ds.starter && !ds.starter.split(',').includes(s.starter)) ||
			(s.gender && ds.gender && !ds.gender.split(',').includes(s.gender)) || (s.kind && ds.kind && ds.kind !== s.kind));

		// Chapter walkthrough: quest links under "Opens up" and "Warning". Done quests are crossed out; filtered-out ones
		// vanish. A Warning box disappears when everything in it is done or filtered out, and an empty list goes with its box.
		function applyChapterLinks(s) {
			for (const li of document.querySelectorAll('li.chapter-quest')) {
				const isDone = done.has('quest:' + li.dataset.questId);
				li.classList.toggle('is-done', isDone);
				li.classList.toggle('is-hidden', filteredOut(li.dataset, s));
			}
			for (const box of document.querySelectorAll('.chapter-warning, .chapter-unlocks')) {
				const items = [...box.querySelectorAll('li.chapter-quest')];
				const warn = box.classList.contains('chapter-warning');
				const live = items.filter((li) => !li.classList.contains('is-hidden') && !(warn && li.classList.contains('is-done')));
				box.classList.toggle('is-hidden', !live.length);
			}
		}

		function apply() {
			const s = { starter: $('starter').value, gender: $('gender').value, kind: $('kind').value, hidedone: $('hidedone').checked };
			store.set('setup', s);
			const target = hashQuest();
			let hidden = 0;
			for (const q of quests) {
				const st = q.dataset.starter?.split(',');
				const g = q.dataset.gender?.split(',');
				const key = keyOf(q);
				const hide = q !== target && (filteredOut(q.dataset, s) || (s.hidedone && key && done.has(key)));
				q.classList.toggle('is-hidden', !!hide);
				if (hide) hidden++;
			}
			applyChapterLinks(s);
			panel.querySelector('.hidden-count').textContent = `${quests.length - hidden} of ${quests.length} quests shown.${hidden === quests.length ? ' No matching quests in this chapter. Change your filters to see more.' : ''}${target ? ' The linked quest stays visible.' : ''}`;
			// keep the page's table of contents in step
			document.querySelectorAll('starlight-toc a, mobile-starlight-toc a').forEach((a) => {
				let t = null;
				try { t = document.getElementById(decodeURIComponent(a.hash.slice(1))); } catch { /* bad hash */ }
				const sec = t?.closest('section.quest');
				a.parentElement.style.display = sec?.classList.contains('is-hidden') ? 'none' : '';
			});
			document.dispatchEvent(new Event('ohg:quests'));
		}
		panel.addEventListener('change', apply);
		// a link to a hidden quest still shows it, also for links on the same page
		window.addEventListener('hashchange', () => {
			apply();
			hashQuest()?.querySelector('h2')?.scrollIntoView();
		});
		apply();
	}

	// ---------------------------------------------------------------- guide pages on phones
	// Below 50rem a guide page becomes one sequence. Walkthrough steps are rows that open on tap; the quests a step
	// opens move under that step (and the separate "Quests in this chapter" section goes), each a row with its Done tick
	// that opens on tap too. A dock at the bottom opens two sheets: Sections (the page's steps and headings, with a find
	// box) and Quests (every quest on the page with its tick and a jump link, plus the game filters). Wider screens are
	// untouched: the extra controls stay hidden unless <html data-ohg-mobile> is set, and the quests go back where they were.
	function setupMobileGuide() {
		if (!/\/guide\//.test(location.pathname)) return;
		const content = document.querySelector('.sl-markdown-content');
		if (!content) return;
		const steps = [...content.querySelectorAll('.chapter-step')];
		const quests = [...content.querySelectorAll('section.quest')];
		const tocLinks = [...document.querySelectorAll('mobile-starlight-toc nav a')];
		if (!steps.length && !quests.length && tocLinks.length < 2) return;
		const root = document.documentElement;
		const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; return e; };
		const esc = (t) => t.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
		const chevron = '<svg class="ohg-m-chevron" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
		const byHash = (hash) => { try { return hash ? document.getElementById(decodeURIComponent(hash.slice(1))) : null; } catch { return null; } };
		const questById = new Map(quests.map((q) => [q.dataset.questId, q]));

		// folds: data-open on the element shows its body; its toggle carries aria-expanded
		const setOpen = (fold, open) => {
			fold.toggleAttribute('data-open', open);
			fold.querySelector(':scope > .ohg-m-row .ohg-m-toggle, :scope > .ohg-m-toggle')?.setAttribute('aria-expanded', String(open));
		};
		// a link into a fold opens it and every fold around it
		const openTo = (t) => { for (let f = t?.closest('.ohg-m-fold'); f; f = f.parentElement?.closest('.ohg-m-fold')) setOpen(f, true); };

		// quests: a row with the Done tick (a mirror of the quest's own box, which setupQuests owns) and the title; the
		// body opens on tap. The real heading stays in the body for anchors and screen readers.
		const questTitle = (q) => q.querySelector('h2')?.textContent.trim() || '';
		quests.forEach((q) => {
			const h = q.querySelector('h2');
			const real = q.querySelector('.quest-tools input[type="checkbox"]');
			if (!h || !real) return;
			const tags = [...q.querySelectorAll('.quest-meta .tag-missable, .quest-meta .tag-starter, .quest-meta .tag-gender, .quest-meta .tag-postgame')]
				.map((t) => t.textContent.trim()).join(' · ');
			const row = el('div', 'ohg-m-row', `<label class="ohg-m-tick"><input type="checkbox" aria-label="Done: ${esc(questTitle(q))}"></label>` +
				`<button type="button" class="ohg-m-toggle"><span class="ohg-m-title">${esc(questTitle(q))}</span>${tags ? `<span class="ohg-m-meta">${esc(tags)}</span>` : ''}${chevron}</button>`);
			const box = row.querySelector('input');
			const sync = () => { box.checked = real.checked; q.classList.toggle('ohg-m-done', real.checked); };
			box.addEventListener('change', () => { real.checked = box.checked; real.dispatchEvent(new Event('change', { bubbles: true })); });
			document.addEventListener('ohg:quests', sync);
			sync();
			row.querySelector('.ohg-m-toggle').addEventListener('click', () => setOpen(q, !q.hasAttribute('data-open')));
			q.prepend(row);
			q.classList.add('ohg-m-fold');
			setOpen(q, false);
		});

		// steps: a row that opens the text, then the quests it opens (moved in from the quests section), then the warning
		const places = new Map(); // quest -> the comment node that holds its place in the quests section
		steps.forEach((step, i) => {
			const title = step.dataset.title || step.querySelector('p strong')?.textContent.replace(/[.:]\s*$/, '') || `Step ${i + 1}`;
			const unlocks = step.querySelector('.chapter-unlocks');
			const mine = [...(unlocks?.querySelectorAll('li.chapter-quest') || [])].map((li) => questById.get(li.dataset.questId)).filter(Boolean);
			const meta = [];
			if (step.classList.contains('chapter-optional')) meta.push('Optional');
			if (mine.length) meta.push(mine.length === 1 ? '1 quest' : `${mine.length} quests`);
			if (step.querySelector('.chapter-warning')) meta.push('<span class="ohg-m-warn">Closes a missable</span>');
			const toggle = el('button', 'ohg-m-toggle', `<span class="ohg-m-title">${esc(title)}</span>${meta.length ? `<span class="ohg-m-meta">${meta.join(' · ')}</span>` : ''}${chevron}`);
			toggle.type = 'button';
			toggle.addEventListener('click', () => setOpen(step, !step.hasAttribute('data-open')));
			const row = el('div', 'ohg-m-row');
			row.append(toggle);
			step.prepend(row);
			step.classList.add('ohg-m-fold', 'ohg-m-step');
			step.dataset.quests = String(mine.length);
			if (mine.length) {
				const list = el('div', 'ohg-m-quests');
				list.dataset.for = step.id || '';
				unlocks.after(list);
				step.ohgQuests = { list, mine };
			}
			setOpen(step, false);
		});
		const placed = new Set(steps.flatMap((s) => s.ohgQuests?.mine || []));
		const loose = quests.filter((q) => !placed.has(q)); // quests no step opens: they stay where they are
		const questsHeading = document.getElementById('quests-in-this-chapter')?.closest('.sl-heading-wrapper') || document.getElementById('quests-in-this-chapter');
		const questsIntro = questsHeading?.nextElementSibling?.matches('p') ? questsHeading.nextElementSibling : null;
		const moveIn = () => {
			for (const step of steps) {
				if (!step.ohgQuests) continue;
				for (const q of step.ohgQuests.mine) {
					if (!places.has(q)) { const c = document.createComment('quest'); q.before(c); places.set(q, c); }
					step.ohgQuests.list.append(q);
				}
			}
			questsHeading?.classList.toggle('ohg-m-hidden', !loose.length);
			questsIntro?.classList.toggle('ohg-m-hidden', !loose.length);
		};
		const moveBack = () => {
			for (const [q, c] of places) c.replaceWith(q);
			places.clear();
			questsHeading?.classList.remove('ohg-m-hidden');
			questsIntro?.classList.remove('ohg-m-hidden');
		};

		// sheets: a native modal <dialog> (focus, Escape and the top layer for free); a tap on the backdrop closes it
		const sheet = (id, title) => {
			const d = el('dialog', 'ohg-m-sheet not-content');
			d.setAttribute('aria-labelledby', id + '-title');
			d.innerHTML = `<div class="ohg-m-sheet-head"><h2 id="${id}-title">${title}</h2><button type="button" class="ohg-m-close" aria-label="Close"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div><div class="ohg-m-sheet-body"></div>`;
			d.querySelector('.ohg-m-close').addEventListener('click', () => d.close());
			d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
			// following a link inside closes the sheet first, so the page can scroll to it
			d.addEventListener('click', (e) => { if (e.target.closest('a[href^="#"]')) d.close(); });
			document.body.append(d);
			return d;
		};
		const dock = el('nav', 'ohg-m-dock not-content');
		dock.setAttribute('aria-label', 'Page tools');
		const dockButton = (label, icon, cls) => {
			const b = el('button', cls, `${icon}<span>${label}</span>`);
			b.type = 'button';
			dock.append(b);
			return b;
		};

		// Sections: the walkthrough steps and the page's other headings
		const sections = sheet('ohg-m-sections', 'On this page');
		const sectionsBody = sections.querySelector('.ohg-m-sheet-body');
		sectionsBody.innerHTML = '<input type="search" class="ohg-m-find" placeholder="Find a step or section" aria-label="Find a step or section"><ul class="ohg-m-toc"></ul>';
		const find = sectionsBody.querySelector('.ohg-m-find');
		const tocList = sectionsBody.querySelector('.ohg-m-toc');
		const renderSections = () => {
			tocList.innerHTML = '';
			const add = (href, text, cls) => {
				const li = el('li', cls);
				const a = el('a');
				a.href = href;
				a.textContent = text;
				li.append(a);
				tocList.append(li);
			};
			const links = tocLinks.length ? tocLinks : [...content.querySelectorAll('h2[id]')].map((h) => ({ hash: '#' + h.id, textContent: h.textContent }));
			for (const a of links) {
				if (a.parentElement && a.parentElement.style?.display === 'none') continue;
				const href = a.hash || a.getAttribute('href');
				const t = byHash(href);
				const q = t?.closest('section.quest');
				if (q && placed.has(q)) continue; // quests under their steps are in the Quests sheet
				if (href === '#quests-in-this-chapter' && !loose.length) continue;
				const sub = q || parseInt(a.style?.getPropertyValue('--depth') || '0', 10) > 0;
				add(href, a.textContent.trim(), sub ? 'ohg-m-sub' : '');
				if (href === '#walkthrough') steps.forEach((s) => s.id && add('#' + s.id, s.dataset.title || s.id, 'ohg-m-sub ohg-m-stepline' + (s.classList.contains('chapter-optional') ? ' ohg-m-optional' : '')));
			}
			filterSections();
		};
		const filterSections = () => {
			const q = searchText(find.value.trim());
			for (const li of tocList.children) li.hidden = !!q && !searchText(li.textContent).includes(q);
		};
		find.addEventListener('input', filterSections);
		const sectionsButton = dockButton('Sections', '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M4 6h16M4 12h10M4 18h13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>', 'ohg-m-dock-sections');
		sectionsButton.addEventListener('click', () => { renderSections(); find.value = ''; filterSections(); sections.showModal(); });

		// Quests: one row per quest the filters leave on the page, with its tick and a jump link, and the game filters.
		// The tick drives the quest's own Done box; setupQuests announces changes with "ohg:quests" and the list redraws.
		let questsSheet = null;
		const panel = content.querySelector('.game-setup');
		if (quests.length) {
			questsSheet = sheet('ohg-m-quests', 'Quests');
			const body = questsSheet.querySelector('.ohg-m-sheet-body');
			const list = el('ul', 'ohg-m-quest-list');
			body.append(list);
			const render = () => {
				const focused = document.activeElement?.closest('.ohg-m-quest')?.dataset.key;
				list.innerHTML = '';
				for (const q of quests) {
					if (q.classList.contains('is-hidden')) continue;
					const h = q.querySelector('h2');
					const real = q.querySelector('.quest-tools input[type="checkbox"]');
					if (!h || !real) continue;
					const flags = [...q.querySelectorAll('.quest-meta .tag-missable, .quest-meta .tag-postgame')].map((t) => t.textContent.trim());
					const li = el('li', 'ohg-m-quest');
					li.dataset.key = h.id;
					li.classList.toggle('is-done', real.checked);
					li.innerHTML = `<label class="ohg-m-tick"><input type="checkbox" aria-label="Done: ${esc(questTitle(q))}"></label>` +
						`<a class="ohg-m-jump" href="#${esc(h.id)}"><span class="ohg-m-title">${esc(questTitle(q))}</span>${flags.length ? `<span class="ohg-m-meta">${esc(flags.join(' · '))}</span>` : ''}</a>`;
					const box = li.querySelector('input');
					box.checked = real.checked;
					box.addEventListener('change', () => { real.checked = box.checked; real.dispatchEvent(new Event('change', { bubbles: true })); });
					list.append(li);
				}
				if (!list.children.length) list.innerHTML = '<li class="ohg-m-empty">No quests match your filters.</li>';
				if (focused) list.querySelector(`[data-key="${CSS.escape(focused)}"] input`)?.focus();
			};
			document.addEventListener('ohg:quests', render);
			render();
			const questsButton = dockButton('Quests', '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M9 11l3 3 8-8M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>', 'ohg-m-dock-quests');
			questsButton.addEventListener('click', () => { render(); questsSheet.showModal(); });
		}
		document.body.append(dock);

		// switch between the phone layout and the normal one as the width changes
		const mq = matchMedia('(max-width: 50rem)');
		const update = () => {
			root.toggleAttribute('data-ohg-mobile', mq.matches);
			if (mq.matches) moveIn(); else moveBack();
			if (panel) {
				if (mq.matches && questsSheet) questsSheet.querySelector('.ohg-m-sheet-body').prepend(panel);
				else if (panel.parentElement !== content) content.prepend(panel);
			}
			if (!mq.matches) document.querySelectorAll('dialog.ohg-m-sheet[open]').forEach((d) => d.close());
		};
		mq.addEventListener ? mq.addEventListener('change', update) : mq.addListener(update);
		update();
		openTo(byHash(location.hash));
		window.addEventListener('hashchange', () => { const t = byHash(location.hash); openTo(t); t?.scrollIntoView(); });
		// the same link twice fires no hashchange, so a tap on an in-page link opens its fold as well
		document.addEventListener('click', (e) => {
			const a = e.target.closest?.('a[href^="#"]');
			if (a && root.hasAttribute('data-ohg-mobile')) openTo(byHash(a.hash));
		});
	}

	// ---------------------------------------------------------------- tables and lists
	// Accept ordinary keyboard spellings such as "poke ball" and "kings rock".
	const searchText = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
		.replace(/['’]/g, '').toLowerCase();
	function setupFilters() {
		const filters = [...document.querySelectorAll('.table-filter')];
		const tables = [...document.querySelectorAll('table.sortable')];
		const targets = [...new Set([...filters.map(f => document.getElementById(f.dataset.table)), ...tables])].filter(Boolean);
		const states = targets.map((target, index) => {
			const f = filters.find(f => f.dataset.table === target.id), body = target.tBodies?.[0];
			const rows = body ? [...body.rows] : [...target.querySelectorAll('[data-row]')].filter(r => !r.parentElement?.closest('[data-row]'));
			const text = new Map(rows.map(r => [r, searchText(r.textContent)]));
			const input = f?.querySelector('input[type="search"]');
			const selects = [...(f?.querySelectorAll('select[data-key]') || [])];
			const checks = [...(f?.querySelectorAll('input[type="checkbox"][data-key]') || [])];
			const defaults = new Map(checks.map(c => [c, c.checked]));
			const ths = tables.includes(target) ? [...target.querySelectorAll('thead th')] : [];
			const labels = ths.map(th => th.textContent.trim());
			// Single indexes have short keys; each table on multi-table pages has its own namespace.
			const prefix = targets.length === 1 ? '' : (target.id || `table-${index + 1}`) + '.';
			const param = key => prefix + key, count = f?.querySelector('.filter-count');
			if (count) { count.setAttribute('role', 'status'); count.setAttribute('aria-atomic', 'true'); }
			const empty = document.createElement('p');
			empty.className = 'filter-empty'; empty.hidden = true;
			empty.textContent = 'No matching results. Change your search or filters, or reset to show everything.';
			if (f) target.after(empty);
			const reset = document.createElement('button');
			reset.type = 'button'; reset.className = 'filter-reset'; reset.textContent = 'Reset';
			const resetName = target.tagName === 'TABLE' ? tableName(target) : '';
			reset.setAttribute('aria-label', `Reset search, filters and sorting${resetName ? ` for ${resetName}` : ''}`);
			if (f) f.append(reset);
			// `sorted`: whether the rows are out of page order. Re-appending every row is costly on long tables, so it only
			// happens while sorting or when going back to page order (W-051).
			let sort = null, searchEditing = false, sorted = false;
			function apply() {
				const words = searchText(input?.value || '').trim().split(/\s+/).filter(Boolean);
				let n = 0;
				for (const r of rows) {
					const tokens = key => (r.dataset[key] || '').split('|');
					const ok = words.every(w => text.get(r).includes(w)) && selects.every(s => !s.value || tokens(s.dataset.key).includes(s.value)) && checks.every(c => c.checked || !tokens(c.dataset.key).includes(c.dataset.showValue));
					if (r.hidden === ok) r.hidden = !ok; if (ok) n++;
				}
				ths.forEach((th, col) => th.setAttribute('aria-sort', sort?.col === col ? sort.dir : 'none'));
				if (body && (sort || sorted)) {
					sorted = !!sort;
					const ordered = [...rows];
					if (sort) {
						const key = r => r.cells[sort.col]?.dataset.sortValue ?? r.cells[sort.col]?.textContent.trim() ?? '';
						const number = value => /^[-+]?[$]?\d[\d,]*(?:\.\d+)?%?$/.test(value) ? Number(value.replace(/[$,%]/g, '')) : NaN;
						const numeric = ths[sort.col].dataset.sortType === 'number' || ordered.every(r => !key(r) || ['—', 'var.'].includes(key(r)) || !Number.isNaN(number(key(r))));
						const order = new Map(rows.map((r, i) => [r, i]));
						ordered.sort((a, b) => {
							const x = key(a), y = key(b), nx = number(x), ny = number(y);
							if (numeric && (Number.isNaN(nx) || Number.isNaN(ny))) return Number.isNaN(nx) && Number.isNaN(ny) ? order.get(a) - order.get(b) : Number.isNaN(nx) ? 1 : -1;
							const c = numeric ? nx - ny : x.localeCompare(y, undefined, {numeric: true});
							return (sort.dir === 'ascending' ? c : -c) || order.get(a) - order.get(b);
						});
					}
					body.append(...ordered);
				}
				if (count) count.textContent = `${n} of ${rows.length} shown${sort ? `; sorted by ${labels[sort.col]}, ${sort.dir}` : ''}`;
				empty.hidden = n !== 0;
			}
			function restore() {
				const params = new URLSearchParams(location.search);
				if (input) input.value = params.get(param('q')) || '';
				for (const s of selects) { const value = params.get(param(s.dataset.key)); s.value = [...s.options].some(o => o.value === value) ? value : ''; }
				for (const c of checks) { const value = params.get(param(c.dataset.key)); c.checked = value === '1' ? true : value === '0' ? false : defaults.get(c); }
				const match = params.get(param('sort'))?.match(/^(\d+)-(asc|desc)$/);
				sort = match && Number(match[1]) < ths.length ? {col: Number(match[1]), dir: match[2] === 'asc' ? 'ascending' : 'descending'} : null;
				searchEditing = false; apply();
			}
			function save(replace = false) {
				const url = new URL(location.href);
				const set = (key, value) => value ? url.searchParams.set(param(key), value) : url.searchParams.delete(param(key));
				set('q', input?.value.trim());
				for (const s of selects) set(s.dataset.key, s.value);
				for (const c of checks) set(c.dataset.key, c.checked === defaults.get(c) ? '' : c.checked ? '1' : '0');
				set('sort', sort ? `${sort.col}-${sort.dir === 'ascending' ? 'asc' : 'desc'}` : '');
				if (url.href === location.href) return false;
				history[replace ? 'replaceState' : 'pushState'](null, '', url);
				return true;
			}
			input?.addEventListener('input', () => { apply(); if (save(searchEditing)) searchEditing = true; });
			input?.addEventListener('blur', () => { searchEditing = false; });
			f?.addEventListener('change', e => { if (e.target !== input) { apply(); save(); } searchEditing = false; });
			reset.addEventListener('click', () => { if (input) input.value = ''; selects.forEach(s => { s.value = ''; }); checks.forEach(c => { c.checked = defaults.get(c); }); sort = null; searchEditing = false; apply(); save(); });
			ths.forEach((th, col) => {
				const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'sort-button'; btn.append(...th.childNodes); th.append(btn);
				btn.addEventListener('click', () => { sort = {col, dir: sort?.col === col && sort.dir === 'ascending' ? 'descending' : 'ascending'}; searchEditing = false; apply(); save(); });
			});
			restore(); return {restore};
		});
		window.addEventListener('popstate', () => states.forEach(s => s.restore()));
	}

	// Keep wide reference tables inside an accessible, independently scrollable panel.
	// A table's name: its caption or ARIA label, else the nearest heading before it (W-033). The panel becomes a
	// focusable, named region only while it really scrolls; otherwise it is a plain div with no ARIA (W-032).
	const textOf = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
	function tableName(table) {
		const own = textOf(table.caption) || table.getAttribute?.('aria-label') ||
			(table.getAttribute?.('aria-labelledby') || '').split(/\s+/).map(id => textOf(document.getElementById(id))).join(' ').trim();
		if (own) return own;
		const headings = [...document.querySelectorAll('.sl-markdown-content :is(h2, h3, h4), h1')];
		const before = headings.filter(h => h.compareDocumentPosition?.(table) & 4).pop();
		return textOf(before);
	}
	function setupTableScroll(root = document) {
		const updates = [];
		root.querySelectorAll('.sl-markdown-content table').forEach(table => {
			if (table.closest('.table-scroll, .save-editor')) return;
			const name = tableName(table);
			if (name && !textOf(table.caption) && !table.getAttribute('aria-label') && !table.getAttribute('aria-labelledby')) table.setAttribute('aria-label', name);
			const panel = document.createElement('div');
			panel.className = 'table-scroll';
			const hint = document.createElement('p');
			hint.className = 'table-scroll-hint';
			hint.textContent = 'Scroll sideways to see all columns →';
			hint.hidden = true;
			table.before(panel); panel.append(table); panel.after(hint);
			const update = () => {
				const overflow = panel.scrollWidth > panel.clientWidth + 2;
				hint.hidden = !overflow;
				if (overflow) {
					panel.tabIndex = 0; panel.setAttribute('role', 'region');
					panel.setAttribute('aria-label', `${name || 'Table'} (scrolls sideways)`);
				} else { panel.removeAttribute('tabindex'); panel.removeAttribute('role'); panel.removeAttribute('aria-label'); }
			};
			updates.push(update);
			if (typeof ResizeObserver !== 'undefined') new ResizeObserver(update).observe(panel);
			update();
		});
		if (typeof ResizeObserver === 'undefined') window.addEventListener('resize', () => updates.forEach(update => update()));
	}

	// Pages that insert tables later (trainer cards on /trainers/) give them the same panel.
	window.ohgTableScroll = setupTableScroll;
	const init = () => { setupQuests(); setupFilters(); setupTableScroll(); setupMobileGuide(); };
	document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
