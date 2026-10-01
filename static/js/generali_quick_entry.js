/* Generali quick entry on a phone (#354).
 *
 * The survey of 29.09 named one thing that had to work on a phone: booking
 * hours. The desktop forms (a modal with a date field, category dropdowns
 * and a number input) technically fit the screen but took a dozen taps and
 * the keyboard. This board does it in a few: a day chip, the category (one
 * tap per level), an amount preset -- Save.
 *
 * Shared by the four Generali booking pages, which differ only in shape:
 *   Base Services        one flat category list, hours
 *   Additional Services  main category -> subcategory, hours
 *   Project Management   no category, an optional comment, hours
 *   PDQM                 up to three levels, a document count, not hours
 * The markup is templates/_generali_quick_entry.html; each page's Jinja shim
 * calls NX.generaliQuickEntry.mount() with what differs.
 *
 * Categories are a tree: [{value, label, fields, children}]. You tap down
 * until you reach a node without children; `fields` on each node on that
 * path are merged into the POST body, so every page decides which column a
 * level fills (PDQM: parentCategory, parentSubCategory, subCategory).
 *
 * Touch phones only, by the same gate as the tab bar; on a desktop the
 * section stays hidden and nothing here runs past the gate check.
 *
 * Always books for the signed-in user. Booking for somebody else stays in
 * the full form behind "More options", which opens prefilled with whatever
 * was picked here. The server keeps every rule it has for the full form
 * (category checks, add deadline, amount limits).
 *
 * `csrfToken` is header.js's page-wide const, as in generali_reporting.js.
 */
(function () {
    'use strict';

    const PHONE = window.matchMedia('(max-width: 768px) and (pointer: coarse)');
    const RECENT_MAX = 4;
    const RECENT_DAYS = 60;

    // Hours, unless the page says otherwise (PDQM counts documents).
    const HOURS = {
        presets: [0.5, 1, 2, 4, 8], step: 0.5, min: 0.5, max: 24,
        recordField: 'effortInHours', totalField: 'totalHours',
        format: n => `${window.NX.formatHours(n)} h`,
    };

    function localDay(d) {
        const p = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    }
    function daysAgo(n) {
        const d = new Date();
        d.setDate(d.getDate() - n);
        return localDay(d);
    }
    function fill(template, values) {
        return template.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
    }
    const samePath = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

    /**
     * cfg:
     *   api            e.g. `${API_PREFIX}api/generali/baseservices`
     *   userId         the signed-in user (list filter for "your entries")
     *   i18n           strings from the page's shim
     *   crud           the page's NX.generaliCrud instance
     *   openAddModal   the page's full add form, or null
     *   storageKey     localStorage key for the last category path
     *   categories     the tree above, a Promise of it (pages that load their
     *                  catalogue), or null for a page without categories
     *   amount         optional, overrides HOURS: {presets, step, min, max,
     *                  recordField, totalField, format(n), chip(n)} -- chip
     *                  labels the preset buttons (defaults to format)
     *   buildBody(p)   picked {date, amount, comment, fields} -> POST body
     *   recordPath(r)  list record -> category path of values, as in the tree
     *   rowLabel(r)    optional: list record -> text for "your entries"
     *   pillLabel(p)   optional: picked -> what the Undo pill names
     *   fillFullForm(p)  prefill the full form for "More options"
     */
    function mount(cfg) {
        const box = document.getElementById('gqQuick');
        if (!box) return;

        const T = cfg.i18n;
        const A = Object.assign({}, HOURS, cfg.amount || {});
        const fmtDate = window.NX.formatDate;
        const esc = window.NX.esc;

        const hasCats = cfg.categories != null;
        const state = { date: null, path: [], amount: null, saving: false };
        let tree = [];

        const $ = id => document.getElementById(id);
        const dayChips = box.querySelectorAll('.gq-chip[data-day]');
        const dateInput = $('gqQuickDate');
        const catsEl = $('gqQuickCats');
        const subsWrap = $('gqQuickSubsWrap');
        const subsEl = $('gqQuickSubs');
        const recentWrap = $('gqQuickRecentWrap');
        const recentEl = $('gqQuickRecent');
        const presetsEl = $('gqQuickPresets');
        const amountEl = $('gqQuickAmount');
        const minusBtn = $('gqQuickMinus');
        const plusBtn = $('gqQuickPlus');
        const saveBtn = $('gqQuickSave');
        const errEl = $('gqQuickError');
        const mineEl = $('gqQuickMine');
        const monthEl = $('gqQuickMonth');
        const commentEl = $('gqQuickComment');

        // ------------------------------------------------------- the tree
        // Nodes along `path`, or null when the path does not exist (any more).
        function nodesFor(path) {
            const out = [];
            let level = tree;
            for (const v of path) {
                const n = (level || []).find(x => x.value === v);
                if (!n) return null;
                out.push(n);
                level = n.children;
            }
            return out;
        }
        function isLeafPath(path) {
            const nodes = nodesFor(path);
            return !!(nodes && nodes.length && !(nodes[nodes.length - 1].children || []).length);
        }
        function pathLabel(path) {
            const nodes = nodesFor(path) || [];
            return nodes.map(n => n.label).join(' · ');
        }
        function lastLabel(path) {
            const nodes = nodesFor(path) || [];
            return nodes.length ? nodes[nodes.length - 1].label : '';
        }
        function pathFields(path) {
            return Object.assign({}, ...(nodesFor(path) || []).map(n => n.fields || {}));
        }

        // ------------------------------------------------------- helpers
        // The add deadline the full form enforces client-side (the server
        // enforces it again): null when the viewer may book any past date.
        function minDay() {
            const m = cfg.crud.getAddMinDate();
            return m ? localDay(m) : null;
        }
        function rowLabel(r) {
            if (cfg.rowLabel) return cfg.rowLabel(r) || '—';
            return pathLabel(cfg.recordPath(r)) || '—';
        }
        function readLast() {
            try { return JSON.parse(localStorage.getItem(cfg.storageKey) || 'null'); } catch (e) { return null; }
        }
        function writeLast(v) {
            try { localStorage.setItem(cfg.storageKey, JSON.stringify(v)); } catch (e) { /* private mode */ }
        }
        function clamp(n) { return Math.min(A.max, Math.max(A.min, n)); }

        // -------------------------------------------------------- render
        function buildStatic() {
            if (catsEl) catsEl.innerHTML = tree.map(n =>
                `<button type="button" class="gq-cat" data-path="${esc(JSON.stringify([n.value]))}" aria-pressed="false">${esc(n.label)}</button>`
            ).join('');
            presetsEl.innerHTML = A.presets.map(v =>
                `<button type="button" class="gq-chip" data-amount="${v}" aria-pressed="false">${esc((A.chip || A.format)(v))}</button>`
            ).join('');
        }

        // One group per level below the first, down the picked path: the
        // children of each picked node, so a three-level catalogue (PDQM)
        // reads as source first, then reason.
        function buildLevels() {
            if (!subsEl) return;
            const nodes = nodesFor(state.path) || [];
            const groups = [];
            nodes.forEach((n, depth) => {
                const kids = n.children || [];
                if (!kids.length) return;
                const prefix = state.path.slice(0, depth + 1);
                groups.push(`<div class="gq-quick__level">${kids.map(k =>
                    `<button type="button" class="gq-sub" data-path="${esc(JSON.stringify([...prefix, k.value]))}" aria-pressed="false">${esc(k.label)}</button>`
                ).join('')}</div>`);
            });
            subsWrap.hidden = !groups.length;
            subsEl.innerHTML = groups.join('');
        }

        function paint() {
            const min = minDay();
            dayChips.forEach(b => {
                const day = daysAgo(Number(b.dataset.day));
                b.disabled = !!min && day < min;
                b.setAttribute('aria-pressed', String(day === state.date));
            });
            const pickedOther = state.date && ![...dayChips].some(b => daysAgo(Number(b.dataset.day)) === state.date);
            dateInput.classList.toggle('is-on', !!pickedOther);
            if (!pickedOther && dateInput.value) dateInput.value = '';
            $('gqQuickDateLabel').textContent = state.date ? fmtDate(state.date) : '';

            // A button is "on" when its path is a prefix of the picked one;
            // a recent shortcut only when it is the picked path exactly.
            box.querySelectorAll('.gq-cat[data-path], .gq-sub[data-path]').forEach(b => {
                const p = JSON.parse(b.dataset.path);
                b.setAttribute('aria-pressed', String(samePath(p, state.path.slice(0, p.length))));
            });
            if (recentEl) recentEl.querySelectorAll('[data-path]').forEach(b =>
                b.setAttribute('aria-pressed', String(samePath(JSON.parse(b.dataset.path), state.path))));
            presetsEl.querySelectorAll('[data-amount]').forEach(b =>
                b.setAttribute('aria-pressed', String(Number(b.dataset.amount) === state.amount)));

            amountEl.textContent = state.amount ? A.format(state.amount) : '–';
            minusBtn.disabled = !state.amount || state.amount <= A.min;
            plusBtn.disabled = !!state.amount && state.amount >= A.max;
            saveBtn.disabled = state.saving || !ready();
        }

        function ready() {
            return !!(state.date && state.amount && (!hasCats || isLeafPath(state.path)));
        }

        function showError(msg) {
            errEl.textContent = msg || '';
            errEl.hidden = !msg;
        }

        function pick(path) {
            state.path = path;
            buildLevels();
            showError('');
            paint();
        }

        // ------------------------------------------- list API reads
        const listUrl = (start, end) => `${cfg.api}?${new URLSearchParams({
            startDate: start, endDate: end, userId: String(cfg.userId), page: '1',
        })}`;
        const getJson = async url => (await window.NX.api(url)).json();

        // Your entries on the picked day, and this month's total.
        let mineSeq = 0;
        async function loadMine() {
            if (!state.date) return;
            const seq = ++mineSeq;
            const day = state.date;
            const today = localDay(new Date());
            try {
                const [dayRes, monthRes] = await Promise.all([
                    getJson(listUrl(day, day)),
                    getJson(listUrl(`${today.slice(0, 8)}01`, today)),
                ]);
                if (seq !== mineSeq) return;  // a newer day was picked meanwhile
                const records = (dayRes && dayRes.records) || [];
                if (!records.length) {
                    mineEl.innerHTML = `<p class="gq-mine__empty">${esc(T.nothingYet)}</p>`;
                } else {
                    mineEl.innerHTML =
                        `<p class="gq-mine__total">${esc(fill(T.dayTotal, { amount: A.format(dayRes[A.totalField] || 0) }))}</p>` +
                        `<ul class="gq-mine__list">${records.map(r =>
                            `<li class="gq-mine__row"><span class="gq-mine__cat">${esc(rowLabel(r))}</span>` +
                            `<span class="gq-mine__h">${esc(A.format(r[A.recordField] || 0))}</span></li>`
                        ).join('')}</ul>`;
                }
                monthEl.textContent = fill(T.monthTotal, { amount: A.format((monthRes && monthRes[A.totalField]) || 0) });
                monthEl.hidden = false;
            } catch (e) {
                if (seq !== mineSeq) return;
                mineEl.innerHTML = `<p class="gq-mine__empty">${esc(T.failedToLoad)}</p>`;
            }
        }

        // "Recently booked": your last few distinct category paths, newest
        // first. With dozens of leaves this is what saves the hunt -- most
        // people book the same handful of things.
        async function loadRecent() {
            if (!recentEl) return;
            try {
                const data = await getJson(listUrl(daysAgo(RECENT_DAYS), localDay(new Date())));
                const seen = new Set();
                const recent = [];
                for (const r of (data && data.records) || []) {
                    const path = cfg.recordPath(r);
                    if (!isLeafPath(path)) continue;  // only what can still be booked as is
                    const id = JSON.stringify(path);
                    if (seen.has(id)) continue;
                    seen.add(id);
                    recent.push(path);
                    if (recent.length === RECENT_MAX) break;
                }
                recentWrap.hidden = !recent.length;
                recentEl.innerHTML = recent.map(p =>
                    `<button type="button" class="gq-recent" data-path="${esc(JSON.stringify(p))}" aria-pressed="false">${esc(pathLabel(p))}</button>`
                ).join('');
                paint();
            } catch (e) {
                recentWrap.hidden = true;
            }
        }

        // ---------------------------------------------------------- save
        function picked() {
            return {
                date: state.date,
                path: state.path.slice(),
                amount: state.amount,
                comment: commentEl ? commentEl.value.trim() : '',
                fields: pathFields(state.path),
            };
        }

        async function save() {
            if (!ready()) { showError(T.pickBoth); return; }
            state.saving = true;
            showError('');
            paint();
            const p = picked();
            try {
                const res = await fetch(cfg.api, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(cfg.buildBody(p)),
                });
                const data = await res.json().catch(() => ({}));
                if (!data.success) throw new Error(data.error || T.saveFailed);
                if (hasCats) writeLast(p.path);
                // Keep the day and category: the next entry is usually the
                // same day, often the same category. The amount is what changes.
                state.amount = null;
                if (commentEl) commentEl.value = '';
                // The pill is small: the last level alone says what was
                // booked; the tooltip carries the full path.
                const what = cfg.pillLabel ? cfg.pillLabel(p) : pathLabel(p.path);
                const short = cfg.pillLabel ? what : lastLabel(p.path);
                window.NX.undoPill.show($('gqUndo'), {
                    text: [T.saved, A.format(p.amount), short].filter(Boolean).join(' · '),
                    title: [fmtDate(p.date), what].filter(Boolean).join(' · '),
                    failText: T.saveFailed,
                    undo: data.id ? async () => {
                        const r = await fetch(`${cfg.api}/${data.id}/undo`, {
                            method: 'POST', headers: { 'X-CSRFToken': csrfToken },
                        });
                        const d = await r.json().catch(() => ({}));
                        if (!d.success) throw new Error(d.error || T.saveFailed);
                        refresh();
                        return T.undone;
                    } : null,
                });
                refresh();
            } catch (e) {
                showError(e instanceof TypeError ? T.networkError : (e.message || T.saveFailed));
            } finally {
                state.saving = false;
                paint();
            }
        }

        function refresh() {
            loadMine();
            loadRecent();
            cfg.crud.loadRecords(1);
        }

        // -------------------------------------------------------- wiring
        function setDate(day) {
            state.date = day;
            showError('');
            paint();
            loadMine();
        }

        dayChips.forEach(b => b.addEventListener('click', () => setDate(daysAgo(Number(b.dataset.day)))));
        window.flatpickr(dateInput, {
            dateFormat: 'Y-m-d',
            maxDate: 'today',
            minDate: cfg.crud.getAddMinDate(),
            onChange: (sel, str) => { if (str) setDate(str); },
        });
        // Category buttons, level buttons and recent shortcuts all carry
        // their full path.
        box.addEventListener('click', e => {
            const b = e.target.closest('.gq-cat[data-path], .gq-sub[data-path], .gq-recent[data-path]');
            if (b) pick(JSON.parse(b.dataset.path));
        });
        presetsEl.addEventListener('click', e => {
            const b = e.target.closest('[data-amount]');
            if (!b) return;
            state.amount = Number(b.dataset.amount);
            showError('');
            paint();
        });
        minusBtn.addEventListener('click', () => {
            if (state.amount) state.amount = clamp(state.amount - A.step);
            paint();
        });
        plusBtn.addEventListener('click', () => {
            state.amount = state.amount ? clamp(state.amount + A.step) : A.min;
            paint();
        });
        saveBtn.addEventListener('click', save);
        $('gqQuickMore').addEventListener('click', () => {
            if (!cfg.openAddModal) return;
            cfg.openAddModal();
            cfg.fillFullForm(picked());
        });

        // ------------------------------------------------------ the gate
        let started = false;
        async function apply() {
            box.hidden = !PHONE.matches;
            if (!PHONE.matches || started) return;
            started = true;
            tree = hasCats ? (await Promise.resolve(cfg.categories)) || [] : [];
            buildStatic();
            const last = hasCats ? readLast() : null;
            if (Array.isArray(last) && nodesFor(last)) state.path = last;
            buildLevels();
            setDate(daysAgo(0));
            loadRecent();
        }
        PHONE.addEventListener('change', apply);
        apply();
    }

    window.NX = window.NX || {};
    window.NX.generaliQuickEntry = { mount };
})();
