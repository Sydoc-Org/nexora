/* Generali quick hours entry on a phone (#354).
 *
 * The survey of 29.09 named one thing that had to work on a phone: booking
 * hours. The desktop forms (a modal with a date field, category dropdowns
 * and a number input) technically fit the screen but took a dozen taps and
 * the keyboard. This board does it in three or four: a day chip, a category
 * (and, on Additional Services, its subcategory), an hours preset -- Save.
 *
 * Shared by Base Services (one flat category list) and Additional Services
 * (main category -> optional subcategory, from dbo.EffortCategories). The
 * markup is templates/_generali_quick_entry.html; each page's Jinja shim
 * calls NX.generaliQuickEntry.mount() with what differs.
 *
 * Touch phones only, by the same gate as the tab bar; on a desktop the
 * section stays hidden and nothing here runs past the gate check.
 *
 * Always books for the signed-in user. Booking for somebody else stays in
 * the full form behind "More options", which opens prefilled with whatever
 * was picked here. The server keeps every rule it has for the full form
 * (category checks, add deadline, effort > 0).
 *
 * `csrfToken` is header.js's page-wide const, as in generali_reporting.js.
 */
(function () {
    'use strict';

    const PHONE = window.matchMedia('(max-width: 768px) and (pointer: coarse)');
    const PRESETS = [0.5, 1, 2, 4, 8];
    const STEP = 0.5;
    const MAX_HOURS = 24;
    const RECENT_MAX = 4;
    const RECENT_DAYS = 60;

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

    /**
     * cfg:
     *   api            e.g. `${API_PREFIX}api/generali/baseservices`
     *   userId         the signed-in user (list filter for "your entries")
     *   i18n           strings from the page's shim
     *   crud           the page's NX.generaliCrud instance
     *   openAddModal   the page's full add form, or null
     *   storageKey     localStorage key for the last category
     *   categories     [{value, label, subs: [{value, label}]}] or a
     *                  Promise of that (Additional Services loads them)
     *   twoLevel       true: payload is {parentCategory, subCategory};
     *                  false: {category}
     *   recordKey(r)   list record -> {cat, sub} as stored
     *   fillFullForm(state)  prefill the full form for "More options"
     */
    function mount(cfg) {
        const box = document.getElementById('gqQuick');
        if (!box) return;

        const T = cfg.i18n;
        const fmtHours = window.NX.formatHours;
        const fmtDate = window.NX.formatDate;
        const esc = window.NX.esc;

        const state = { date: null, cat: null, sub: null, hours: null, saving: false };
        let categories = [];
        let labels = {};  // stored value -> shown label

        const $ = id => document.getElementById(id);
        const dayChips = box.querySelectorAll('.gq-chip[data-day]');
        const dateInput = $('gqQuickDate');
        const catsEl = $('gqQuickCats');
        const subsWrap = $('gqQuickSubsWrap');
        const subsEl = $('gqQuickSubs');
        const recentWrap = $('gqQuickRecentWrap');
        const recentEl = $('gqQuickRecent');
        const presetsEl = $('gqQuickPresets');
        const hoursEl = $('gqQuickHours');
        const minusBtn = $('gqQuickMinus');
        const plusBtn = $('gqQuickPlus');
        const saveBtn = $('gqQuickSave');
        const errEl = $('gqQuickError');
        const mineEl = $('gqQuickMine');
        const monthEl = $('gqQuickMonth');

        // ------------------------------------------------------- helpers
        // The add deadline the full form enforces client-side (the server
        // enforces it again): null when the viewer may book any past date.
        function minDay() {
            const m = cfg.crud.getAddMinDate();
            return m ? localDay(m) : null;
        }
        function category(value) { return categories.find(c => c.value === value); }
        function needsSub() { const c = category(state.cat); return !!(c && c.subs.length); }
        function label(value) { return labels[value] || value; }
        function entryLabel(cat, sub) { return sub ? `${label(cat)} · ${label(sub)}` : label(cat); }
        function readLast() {
            try { return JSON.parse(localStorage.getItem(cfg.storageKey) || 'null'); } catch (e) { return null; }
        }
        function writeLast(v) {
            try { localStorage.setItem(cfg.storageKey, JSON.stringify(v)); } catch (e) { /* private mode */ }
        }

        // -------------------------------------------------------- render
        function buildButtons() {
            catsEl.innerHTML = categories.map(c =>
                `<button type="button" class="gq-cat" data-cat="${esc(c.value)}" aria-pressed="false">${esc(c.label)}</button>`
            ).join('');
            presetsEl.innerHTML = PRESETS.map(h =>
                `<button type="button" class="gq-chip" data-hours="${h}" aria-pressed="false">${esc(fmtHours(h))} h</button>`
            ).join('');
        }

        function buildSubs() {
            if (!subsEl) return;
            const c = category(state.cat);
            const subs = (c && c.subs) || [];
            subsWrap.hidden = !subs.length;
            subsEl.innerHTML = subs.map(s =>
                `<button type="button" class="gq-sub" data-sub="${esc(s.value)}" aria-pressed="false">${esc(s.label)}</button>`
            ).join('');
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

            catsEl.querySelectorAll('.gq-cat').forEach(b =>
                b.setAttribute('aria-pressed', String(b.dataset.cat === state.cat)));
            if (subsEl) subsEl.querySelectorAll('.gq-sub').forEach(b =>
                b.setAttribute('aria-pressed', String(b.dataset.sub === state.sub)));
            if (recentEl) recentEl.querySelectorAll('[data-cat]').forEach(b =>
                b.setAttribute('aria-pressed', String(b.dataset.cat === state.cat && (b.dataset.sub || null) === state.sub)));
            presetsEl.querySelectorAll('[data-hours]').forEach(b =>
                b.setAttribute('aria-pressed', String(Number(b.dataset.hours) === state.hours)));

            hoursEl.textContent = state.hours ? `${fmtHours(state.hours)} h` : '–';
            minusBtn.disabled = !state.hours || state.hours <= STEP;
            plusBtn.disabled = !!state.hours && state.hours >= MAX_HOURS;
            saveBtn.disabled = state.saving || !ready();
        }

        function ready() {
            return !!(state.date && state.cat && state.hours && (!needsSub() || state.sub));
        }

        function showError(msg) {
            errEl.textContent = msg || '';
            errEl.hidden = !msg;
        }

        function pick(cat, sub) {
            const changed = cat !== state.cat;
            state.cat = cat;
            state.sub = sub || null;
            if (changed) buildSubs();
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
                        `<p class="gq-mine__total">${esc(fill(T.dayTotal, { hours: fmtHours(dayRes.totalHours || 0) }))}</p>` +
                        `<ul class="gq-mine__list">${records.map(r => {
                            const k = cfg.recordKey(r);
                            return `<li class="gq-mine__row"><span class="gq-mine__cat">${esc(k.cat ? entryLabel(k.cat, k.sub) : '—')}</span>` +
                                `<span class="gq-mine__h">${esc(fmtHours(r.effortInHours))} h</span></li>`;
                        }).join('')}</ul>`;
                }
                monthEl.textContent = fill(T.monthTotal, { hours: fmtHours((monthRes && monthRes.totalHours) || 0) });
                monthEl.hidden = false;
            } catch (e) {
                if (seq !== mineSeq) return;
                mineEl.innerHTML = `<p class="gq-mine__empty">${esc(T.failedToLoad)}</p>`;
            }
        }

        // "Recently booked": your last few distinct (category, sub) pairs,
        // newest first. With thirty-odd subcategories this is what saves the
        // hunt -- most people book the same handful of things.
        async function loadRecent() {
            if (!recentEl) return;
            try {
                const data = await getJson(listUrl(daysAgo(RECENT_DAYS), localDay(new Date())));
                const seen = new Set();
                const recent = [];
                for (const r of (data && data.records) || []) {
                    const k = cfg.recordKey(r);
                    const c = category(k.cat);
                    // Only pairs that can still be booked as they are.
                    if (!c || (k.sub && !c.subs.some(s => s.value === k.sub)) || (!k.sub && c.subs.length)) continue;
                    const id = `${k.cat}\u0000${k.sub || ''}`;
                    if (seen.has(id)) continue;
                    seen.add(id);
                    recent.push(k);
                    if (recent.length === RECENT_MAX) break;
                }
                recentWrap.hidden = !recent.length;
                recentEl.innerHTML = recent.map(k =>
                    `<button type="button" class="gq-recent" data-cat="${esc(k.cat)}" data-sub="${esc(k.sub || '')}" aria-pressed="false">${esc(entryLabel(k.cat, k.sub))}</button>`
                ).join('');
                paint();
            } catch (e) {
                recentWrap.hidden = true;
            }
        }

        // ---------------------------------------------------------- save
        async function save() {
            if (!ready()) { showError(T.pickBoth); return; }
            state.saving = true;
            showError('');
            paint();
            const picked = { ...state };
            const body = cfg.twoLevel
                ? { forDate: picked.date, parentCategory: picked.cat, subCategory: picked.sub, effortInHours: picked.hours }
                : { forDate: picked.date, category: picked.cat, effortInHours: picked.hours };
            try {
                const res = await fetch(cfg.api, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(body),
                });
                const data = await res.json().catch(() => ({}));
                if (!data.success) throw new Error(data.error || T.saveFailed);
                writeLast({ cat: picked.cat, sub: picked.sub });
                // Keep the day and category: the next entry is usually the
                // same day, often the same category. The hours are what changes.
                state.hours = null;
                // The pill is small: the subcategory alone says what was
                // booked; the tooltip carries the full "main · sub" name.
                const what = entryLabel(picked.cat, picked.sub);
                window.NX.undoPill.show($('gqUndo'), {
                    text: `${T.saved} · ${fmtHours(picked.hours)} h · ${label(picked.sub || picked.cat)}`,
                    title: `${fmtDate(picked.date)} · ${what}`,
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
        catsEl.addEventListener('click', e => {
            const b = e.target.closest('.gq-cat');
            if (b) pick(b.dataset.cat, null);
        });
        if (subsEl) subsEl.addEventListener('click', e => {
            const b = e.target.closest('.gq-sub');
            if (b) pick(state.cat, b.dataset.sub);
        });
        if (recentEl) recentEl.addEventListener('click', e => {
            const b = e.target.closest('.gq-recent');
            if (b) pick(b.dataset.cat, b.dataset.sub || null);
        });
        presetsEl.addEventListener('click', e => {
            const b = e.target.closest('[data-hours]');
            if (!b) return;
            state.hours = Number(b.dataset.hours);
            showError('');
            paint();
        });
        minusBtn.addEventListener('click', () => {
            if (state.hours) state.hours = Math.max(STEP, state.hours - STEP);
            paint();
        });
        plusBtn.addEventListener('click', () => {
            state.hours = Math.min(MAX_HOURS, (state.hours || 0) + STEP);
            paint();
        });
        saveBtn.addEventListener('click', save);
        $('gqQuickMore').addEventListener('click', () => {
            if (!cfg.openAddModal) return;
            cfg.openAddModal();
            cfg.fillFullForm({ ...state });
        });

        // ------------------------------------------------------ the gate
        let started = false;
        async function apply() {
            box.hidden = !PHONE.matches;
            if (!PHONE.matches || started) return;
            started = true;
            categories = await Promise.resolve(cfg.categories);
            labels = {};
            categories.forEach(c => {
                labels[c.value] = c.label;
                c.subs.forEach(s => { labels[s.value] = s.label; });
            });
            buildButtons();
            const last = readLast();
            if (last && category(last.cat)) {
                state.cat = last.cat;
                const c = category(last.cat);
                state.sub = last.sub && c.subs.some(s => s.value === last.sub) ? last.sub : null;
            }
            buildSubs();
            setDate(daysAgo(0));
            loadRecent();
        }
        PHONE.addEventListener('change', apply);
        apply();
    }

    window.NX = window.NX || {};
    window.NX.generaliQuickEntry = { mount };
})();
