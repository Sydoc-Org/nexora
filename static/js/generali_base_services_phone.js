/* Generali Base Services -- quick hours entry on a phone (#354).
 *
 * The survey of 29.09 named one thing that had to work on a phone: booking
 * Basisleistungen hours. The desktop form (a modal with a date field, a
 * category dropdown and a number input) technically fit the screen but took
 * a dozen taps and the keyboard. This board does it in three: a day chip, a
 * category button, an hours preset -- then Save.
 *
 * Touch phones only, by the same gate as the tab bar; on a desktop the
 * section stays hidden and nothing here runs past the gate check.
 *
 * Always books for the signed-in user. Booking for somebody else stays in
 * the full form behind "More options", which opens prefilled with whatever
 * was picked here.
 *
 * `csrfToken` is header.js's page-wide const, as in generali_reporting.js.
 *
 * Data and strings come from the Jinja shim in
 * templates/js/_generali_base_services_js.html (window.NX_BASE_SERVICES_QUICK
 * and window.NX_GENERALI_BASE_SERVICES); the server keeps every rule it has
 * for the full form (category allow-list, add deadline, effort > 0).
 */
(function () {
    'use strict';

    const box = document.getElementById('bsQuick');
    const CFG = window.NX_BASE_SERVICES_QUICK;
    const PAGE = window.NX_GENERALI_BASE_SERVICES;
    if (!box || !CFG || !PAGE) return;

    const T = CFG.i18n;
    const API = `${window.API_PREFIX}api/generali/baseservices`;
    const PHONE = window.matchMedia('(max-width: 768px) and (pointer: coarse)');
    const PRESETS = [0.5, 1, 2, 4, 8];
    const STEP = 0.5;
    const MAX_HOURS = 24;
    const LAST_CATEGORY_KEY = 'nx.generali.baseservices.lastCategory';

    const fmtHours = window.NX.formatHours;
    const fmtDate = window.NX.formatDate;
    const esc = window.NX.esc;

    const state = { date: null, category: null, hours: null, saving: false };

    // ------------------------------------------------------------ helpers
    function localDay(d) {
        const p = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    }
    function daysAgo(n) {
        const d = new Date();
        d.setDate(d.getDate() - n);
        return localDay(d);
    }
    // The same add deadline the full form enforces client-side (the server
    // enforces it again): null when the viewer may book any past date.
    function minDay() {
        const m = PAGE.crud.getAddMinDate();
        return m ? localDay(m) : null;
    }
    function readLastCategory() {
        try { return localStorage.getItem(LAST_CATEGORY_KEY); } catch (e) { return null; }
    }
    function writeLastCategory(c) {
        try { localStorage.setItem(LAST_CATEGORY_KEY, c); } catch (e) { /* private mode */ }
    }
    function fill(template, values) {
        return template.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
    }

    // ------------------------------------------------------------- render
    const dayChips = box.querySelectorAll('.bs-chip[data-day]');
    const dateInput = document.getElementById('bsQuickDate');
    const catsEl = document.getElementById('bsQuickCats');
    const presetsEl = document.getElementById('bsQuickPresets');
    const hoursEl = document.getElementById('bsQuickHours');
    const minusBtn = document.getElementById('bsQuickMinus');
    const plusBtn = document.getElementById('bsQuickPlus');
    const saveBtn = document.getElementById('bsQuickSave');
    const errEl = document.getElementById('bsQuickError');
    const mineEl = document.getElementById('bsQuickMine');
    const monthEl = document.getElementById('bsQuickMonth');

    function buildButtons() {
        catsEl.innerHTML = PAGE.categories.map(c =>
            `<button type="button" class="bs-cat" data-category="${esc(c)}" aria-pressed="false">${esc(c)}</button>`
        ).join('');
        presetsEl.innerHTML = PRESETS.map(h =>
            `<button type="button" class="bs-chip bs-chip--hours" data-hours="${h}" aria-pressed="false">${esc(fmtHours(h))} h</button>`
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
        document.getElementById('bsQuickDateLabel').textContent = state.date ? fmtDate(state.date) : '';

        catsEl.querySelectorAll('.bs-cat').forEach(b =>
            b.setAttribute('aria-pressed', String(b.dataset.category === state.category)));
        presetsEl.querySelectorAll('[data-hours]').forEach(b =>
            b.setAttribute('aria-pressed', String(Number(b.dataset.hours) === state.hours)));

        hoursEl.textContent = state.hours ? `${fmtHours(state.hours)} h` : '–';
        minusBtn.disabled = !state.hours || state.hours <= STEP;
        plusBtn.disabled = !!state.hours && state.hours >= MAX_HOURS;
        saveBtn.disabled = state.saving || !state.date || !state.category || !state.hours;
    }

    function showError(msg) {
        errEl.textContent = msg || '';
        errEl.hidden = !msg;
    }

    // ------------------------------------------- your entries, month total
    let mineSeq = 0;
    async function loadMine() {
        if (!state.date) return;
        const seq = ++mineSeq;
        const day = state.date;
        const monthStart = `${localDay(new Date()).slice(0, 8)}01`;
        const q = (start, end) => `${API}?${new URLSearchParams({
            startDate: start, endDate: end, userId: String(CFG.userId), page: '1',
        })}`;
        try {
            const getJson = async url => (await window.NX.api(url)).json();
            const [dayRes, monthRes] = await Promise.all([
                getJson(q(day, day)),
                getJson(q(monthStart, localDay(new Date()))),
            ]);
            if (seq !== mineSeq) return;  // a newer day was picked meanwhile
            const records = (dayRes && dayRes.records) || [];
            if (!records.length) {
                mineEl.innerHTML = `<p class="bs-mine__empty">${esc(T.nothingYet)}</p>`;
            } else {
                mineEl.innerHTML =
                    `<p class="bs-mine__total">${esc(fill(T.dayTotal, { hours: fmtHours(dayRes.totalHours || 0) }))}</p>` +
                    `<ul class="bs-mine__list">${records.map(r =>
                        `<li class="bs-mine__row"><span class="bs-mine__cat">${esc(r.category || '—')}</span>` +
                        `<span class="bs-mine__h">${esc(fmtHours(r.effortInHours))} h</span></li>`
                    ).join('')}</ul>`;
            }
            monthEl.textContent = fill(T.monthTotal, { hours: fmtHours((monthRes && monthRes.totalHours) || 0) });
            monthEl.hidden = false;
        } catch (e) {
            if (seq !== mineSeq) return;
            mineEl.innerHTML = `<p class="bs-mine__empty">${esc(T.failedToLoad)}</p>`;
        }
    }

    // --------------------------------------------------------------- save
    async function save() {
        if (!state.date || !state.category || !state.hours) { showError(T.pickBoth); return; }
        state.saving = true;
        showError('');
        paint();
        const picked = { ...state };
        try {
            const res = await fetch(API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({
                    forDate: picked.date, category: picked.category, effortInHours: picked.hours,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!data.success) throw new Error(data.error || T.saveFailed);
            writeLastCategory(picked.category);
            // Keep the day and category: the next entry is usually the same
            // day, often the same category. The hours are what changes.
            state.hours = null;
            window.NX.undoPill.show(document.getElementById('bsUndo'), {
                text: `${T.saved} · ${fmtHours(picked.hours)} h · ${picked.category}`,
                title: `${fmtDate(picked.date)} · ${picked.category}`,
                failText: T.saveFailed,
                undo: data.id ? async () => {
                    const r = await fetch(`${API}/${data.id}/undo`, {
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
        PAGE.crud.loadRecords(1);
    }

    // ------------------------------------------------------------- wiring
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
        minDate: PAGE.crud.getAddMinDate(),
        onChange: (sel, str) => { if (str) setDate(str); },
    });

    catsEl.addEventListener('click', e => {
        const b = e.target.closest('.bs-cat');
        if (!b) return;
        state.category = b.dataset.category;
        showError('');
        paint();
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

    // The full form, prefilled with what was picked here -- for booking on
    // behalf of someone else, or anything this board does not cover.
    document.getElementById('bsQuickMore').addEventListener('click', () => {
        if (!PAGE.openAddModal) return;
        PAGE.openAddModal();
        const dateEl = document.getElementById('addForDate');
        if (state.date && dateEl) {
            if (dateEl._flatpickr) dateEl._flatpickr.setDate(state.date, false);
            else dateEl.value = state.date;
        }
        if (state.category) document.getElementById('addCategory').value = state.category;
        if (state.hours) document.getElementById('addEffortHours').value = String(state.hours);
    });

    // ------------------------------------------------------------ the gate
    let started = false;
    function apply() {
        box.hidden = !PHONE.matches;
        if (!PHONE.matches || started) return;
        started = true;
        buildButtons();
        const last = readLastCategory();
        if (last && PAGE.categories.includes(last)) state.category = last;
        setDate(daysAgo(0));
    }
    PHONE.addEventListener('change', apply);
    apply();
})();
