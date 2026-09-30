/* Sydoc BPS (#415, redesigned in #427). Behaviour only -- strings and Jinja
   data arrive on window.NX_BPS; see templates/js/_bps_js.html.

   One summary request per period returns hours and bookings per
   task / customer / package / person, for the period and for the one before
   it. The band's totals, the daily chart and the drill-down are all built
   from it in the browser, so switching the order, the view or a filter never
   goes back to the server. The drill-down zooms one level at a time (Table
   or Treemap, pure logic in bps_view.js); only the leaf (the third level)
   loads its single bookings, with their comments, from /api/bps/entries.
   The period picker's hours per month load lazily from /api/bps/months.

   Colour carries category only (billable / other service / absence), always
   next to a text label; the three hues are the page's --bps-* tokens, checked
   with the dataviz validator in both themes. */
(function () {
    'use strict';

    const CFG = window.NX_BPS;
    const S = CFG.strings;
    const esc = window.NX.esc;
    const V = window.BpsView;
    const Sy = window.NXSydoc;
    const fmt = Sy.fmt;
    const lang = document.documentElement.lang || undefined;
    const dateLang = !lang || lang === 'en' ? 'en-GB' : lang;

    const intFmt = new Intl.NumberFormat(lang);
    const hFmt = new Intl.NumberFormat(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const hFine = new Intl.NumberFormat(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const pctFmt = new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 0 });
    const dFmt = opts => new Intl.DateTimeFormat(dateLang, Object.assign({ timeZone: 'UTC' }, opts));
    const dayOnly = dFmt({ day: 'numeric' });
    const dayMonth = dFmt({ day: 'numeric', month: 'short' });
    const dayMonthYear = dFmt({ day: 'numeric', month: 'short', year: 'numeric' });
    const monthShort = dFmt({ month: 'short' });
    const weekdayShort = dFmt({ weekday: 'short' });
    const weekdayFmt = dFmt({ weekday: 'short', day: 'numeric', month: 'short' });

    const hours = n => hFmt.format(Number(n) || 0);
    const hUnit = n => fmt(S.h, { n });
    const pct = (a, b) => pctFmt.format(b > 0 ? a / b : 0);
    const utc = iso => {
        const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
        return new Date(Date.UTC(y, m - 1, d));
    };
    const ymd = d => d.toISOString().slice(0, 10);
    const label = key => (key === null || key === undefined || key === '' ? '–' : String(key));
    const MINUS = '−';
    const signed = (n, f) => (n > 0 ? '+' : n < 0 ? MINUS : '±') + f(Math.abs(n));

    function rangeText(from, to) {
        const a = utc(from);
        const b = utc(to);
        // formatRange knows each locale's own shape ("1–31 Aug 2026", "1.–31. Aug. 2026").
        if (dayMonthYear.formatRange && a < b) return dayMonthYear.formatRange(a, b).replace(/\s*[–-]\s*/, ' – ');
        const sameYear = a.getUTCFullYear() === b.getUTCFullYear();
        const sameMonth = sameYear && a.getUTCMonth() === b.getUTCMonth();
        const head = sameMonth ? dayOnly.format(a) : sameYear ? dayMonth.format(a) : dayMonthYear.format(a);
        return fmt(S.rangeText, { from: head, to: dayMonthYear.format(b) });
    }

    // ---- headline -----------------------------------------------------------
    const hl = Sy.periodHeadline(CFG.from, CFG.to, lang, S.weekLabel, CFG.today);
    document.querySelector('[data-role="period-main"]').textContent = hl.main;
    document.querySelector('[data-role="period-year"]').textContent = hl.year;
    document.querySelector('[data-role="range-text"]').textContent = rangeText(CFG.from, CFG.to);

    // ---- period picker: presets, months with their hours, a free range --------
    const form = document.getElementById('bps-period');
    const fromEl = document.getElementById('bps-from');
    const toEl = document.getElementById('bps-to');
    const picker = document.getElementById('bps-picker');
    const today = utc(CFG.today);
    const PRESETS = {
        'last-month': t => [new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() - 1, 1)), new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), 0))],
        'this-month': t => [new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), 1)), t],
        'last-week': t => {
            const monday = new Date(t.getTime() - (((t.getUTCDay() + 6) % 7) + 7) * 86400000);
            return [monday, new Date(monday.getTime() + 6 * 86400000)];
        },
        'quarter': t => [new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() - 3, 1)), new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), 0))],
    };
    function go(from, to) {
        fromEl.value = from;
        toEl.value = to;
        form.requestSubmit();
    }
    picker.querySelectorAll('[data-preset]').forEach(btn => {
        const [a, b] = PRESETS[btn.dataset.preset](today);
        const active = ymd(a) === CFG.from && ymd(b) === CFG.to;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.addEventListener('click', () => go(ymd(a), ymd(b)));
    });

    let viewYear = utc(CFG.to).getUTCFullYear();
    let monthsState = 'idle'; // idle | loading | done | failed
    const grid = picker.querySelector('[data-role="months"]');

    function firstYear() {
        const keys = Object.keys(CFG.months || {}).sort();
        return keys.length ? Number(keys[0].slice(0, 4)) : viewYear;
    }

    function renderMonths() {
        picker.querySelector('[data-role="year"]').textContent = String(viewYear);
        picker.querySelector('[data-role="year-prev"]').disabled = monthsState === 'done' && viewYear <= firstYear();
        picker.querySelector('[data-role="year-next"]').disabled = viewYear >= today.getUTCFullYear();
        const selFrom = utc(CFG.from);
        const selTo = utc(CFG.to);
        grid.innerHTML = Sy.monthCells(viewYear, CFG.today, lang).map(c => {
            const [y, m] = c.key.split('-').map(Number);
            const first = new Date(Date.UTC(y, m - 1, 1));
            const last = new Date(Date.UTC(y, m, 0));
            const v = (CFG.months || {})[c.key] || 0;
            let status = '';
            let cls = '';
            let disabled = c.future;
            if (c.future) {
                status = '';
            } else if (monthsState !== 'done') {
                status = monthsState === 'failed' ? '' : '…';
            } else if (c.current) {
                status = `<span class="nx-sydoc-dot"></span>${esc(fmt(S.runningH, { h: hUnit(hours(v)) }))}`;
                cls = ' nx-sydoc-picker__cell-status--running';
            } else if (!v) {
                status = esc(S.noData);
                disabled = true;
            } else {
                status = esc(hUnit(hours(v)));
            }
            const selected = ymd(first) === ymd(selFrom) && (ymd(last) === ymd(selTo) || (c.current && ymd(selTo) === CFG.today));
            const to = c.current ? CFG.today : ymd(last);
            return `<button type="button" class="nx-sydoc-picker__cell${selected ? ' is-selected' : ''}" data-from="${ymd(first)}" data-to="${to}"${disabled ? ' disabled' : ''}${selected ? ' aria-current="true"' : ''}>
                <span class="nx-sydoc-picker__cell-name">${esc(c.name)}</span>
                <span class="nx-sydoc-picker__cell-status${cls}">${status}</span>
              </button>`;
        }).join('');
    }

    async function loadMonths() {
        if (monthsState === 'loading' || monthsState === 'done') return;
        monthsState = 'loading';
        const res = await window.NX.apiSafe('/api/bps/months');
        if (res.ok && res.data && !res.data.error) {
            CFG.months = res.data.months || {};
            monthsState = 'done';
        } else {
            monthsState = 'failed';
            if (window.NX.toast) window.NX.toast(S.monthsFail, 'error');
        }
        renderMonths();
    }

    grid.addEventListener('click', e => {
        const cell = e.target.closest('[data-from]');
        if (cell && !cell.disabled) go(cell.dataset.from, cell.dataset.to);
    });
    picker.querySelector('[data-role="year-prev"]').addEventListener('click', () => { viewYear -= 1; renderMonths(); });
    picker.querySelector('[data-role="year-next"]').addEventListener('click', () => { viewYear += 1; renderMonths(); });
    Sy.initPicker({
        root: picker,
        opener: document.querySelector('[data-testid="bps-period-button"]'),
        onOpen: () => { renderMonths(); loadMonths(); },
    });

    // ---- state ---------------------------------------------------------------
    function readView() {
        try { return window.localStorage.getItem('nx.bps.view') === 'map' ? 'map' : 'table'; } catch (e) { return 'table'; }
    }
    const state = {
        rows: [],
        prevRows: [],
        prev: null,
        order: ['Aufgabe', 'Kunde', 'Benutzer'],
        path: [],
        view: readView(),
        billableOnly: false,
        hideAbsences: true,
        query: '',
        openDays: new Set(),
        loaded: false,
    };
    const PARAM = { Aufgabe: 'task', Kunde: 'customer', Benutzer: 'person' };
    let groups = [];

    function setStatus(text, kind) {
        const el = document.getElementById('bps-status');
        el.classList.toggle('is-failed', kind === 'failed');
        el.querySelector('[data-role="dot"]').className = `nx-sydoc-dot nx-sydoc-dot--${kind || 'running'}`;
        document.getElementById('bps-status-text').textContent = text;
    }

    function showError(payload) {
        const el = document.getElementById('bps-error');
        const detail = payload && payload.detail ? `<span class="nx-bps-error__detail">${esc(payload.detail)}</span>` : '';
        el.innerHTML = `<i class="fas fa-triangle-exclamation" aria-hidden="true"></i><span>${esc((payload && payload.error) || S.failed)}</span>${detail}`;
        el.hidden = false;
    }

    // ---- band: totals and composition ------------------------------------------
    function totalsHtml(t) {
        const service = t.billable + t.service;
        const unit = esc(hUnit('').trim());
        const cell = (key, k, v, sub) => `
            <div class="nx-bps-totals__cell" data-testid="bps-kpi-${key}">
              <span class="nx-bps-totals__k">${esc(k)}</span>
              <span class="nx-bps-totals__v">${esc(v)}${sub ? `<small>${esc(sub)}</small>` : ''}</span>
            </div>`;
        return `
            <div class="nx-bps-totals__lead" data-testid="bps-kpi-total">
              <span class="nx-bps-totals__k">${esc(S.totalHours)}</span>
              <span class="nx-bps-totals__big">${esc(hours(t.hours))}<small>${unit}</small></span>
            </div>
            <div class="nx-bps-totals__grid">
              ${cell('service', S.serviceHours, hours(service), fmt(S.ofTotal, { pct: pct(service, t.hours) }))}
              ${cell('bookings', S.bookings, intFmt.format(t.count), '')}
              ${cell('people', S.people, intFmt.format(t.people), S.withHours)}
            </div>`;
    }

    function compHtml(t) {
        const service = t.billable + t.service;
        const parts = [
            { cat: 'billable', label: S.catBillable, h: t.billable, sub: fmt(S.ofService, { pct: pct(t.billable, service) }) },
            { cat: 'service', label: S.catService, h: t.service, sub: fmt(S.ofTotal, { pct: pct(t.service, t.hours) }) },
            { cat: 'absence', label: S.catAbsence, h: t.absence, sub: fmt(S.ofTotal, { pct: pct(t.absence, t.hours) }) },
        ].filter(p => p.h > 0);
        const share = p => (t.hours > 0 ? (p.h / t.hours) * 100 : 0);
        const bar = parts.map(p => `<span class="nx-bps-comp__seg nx-bps-comp__seg--${p.cat}" style="width:${share(p).toFixed(2)}%"></span>`).join('');
        const cols = parts.map(p => `minmax(min-content, ${Math.max(share(p), 1).toFixed(2)}fr)`).join(' ');
        const labels = parts.map(p => `
            <div class="nx-bps-comp__cell">
              <span class="nx-bps-comp__name"><span class="nx-bps-swatch nx-bps-swatch--${p.cat}"></span>${esc(p.label)}</span>
              <span class="nx-bps-comp__v">${esc(hUnit(hours(p.h)))}<small>${esc(p.sub)}</small></span>
            </div>`).join('');
        return { bar, cols, labels };
    }

    // ---- chart ---------------------------------------------------------------
    let chart = null;
    let days = [];
    function token(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }
    const weekendPlugin = {
        id: 'nxWeekends',
        beforeDatasetsDraw(c) {
            const x = c.scales.x;
            const area = c.chartArea;
            if (!x || !area || !days.length) return;
            const step = x.width / days.length;
            const ctx = c.ctx;
            ctx.save();
            ctx.fillStyle = document.documentElement.classList.contains('dark') ? token('--nx-alt') : '#f3f4f6';
            days.forEach((d, i) => {
                const wd = utc(d.date).getUTCDay();
                if (wd !== 0 && wd !== 6) return;
                const cx = x.getPixelForValue(i);
                const left = cx - step / 2 + 1;
                const w = step - 2;
                ctx.beginPath();
                if (ctx.roundRect) ctx.roundRect(left, area.top, w, area.bottom - area.top, [4, 4, 0, 0]);
                else ctx.rect(left, area.top, w, area.bottom - area.top);
                ctx.fill();
            });
            ctx.restore();
        },
    };
    function drawChart() {
        const canvas = document.getElementById('bps-chart');
        if (!window.Chart || !canvas) return;
        const surface = token('--nx-card') || '#fff';
        const series = [
            { key: 'billable', label: S.catBillable, color: token('--bps-billable') },
            { key: 'service', label: S.catService, color: token('--bps-service') },
            { key: 'absence', label: S.catAbsence, color: token('--bps-absence') },
        ];
        const column = days.length ? canvas.parentElement.clientWidth / days.length : 22;
        const data = {
            labels: days.map(d => d.date),
            datasets: series.map((s, i) => ({
                label: s.label,
                data: days.map(d => d[s.key]),
                backgroundColor: s.color,
                // A 2px surface gap between stacked segments; the rounded end
                // sits on the top segment only (absence), anchored bars below.
                borderColor: surface,
                borderWidth: { top: 2, bottom: 0, left: 0, right: 0 },
                borderSkipped: 'bottom',
                borderRadius: i === series.length - 1 ? { topLeft: 3, topRight: 3 } : 0,
                maxBarThickness: Math.max(4, column - 6),
                categoryPercentage: 1,
                barPercentage: 1,
            })),
        };
        const ink = token('--nx-text-meta') || '#9ca3af';
        const grid = token('--nx-divider') || '#f3f4f6';
        const options = {
            responsive: true,
            maintainAspectRatio: false,
            animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 250 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: items => weekdayFmt.format(utc(days[items[0].dataIndex].date)),
                        label: item => ` ${item.dataset.label}: ${hUnit(hFine.format(item.raw))}`,
                        footer: items => fmt(S.dayTotal, { n: hFine.format(items.reduce((a, i) => a + (Number(i.raw) || 0), 0)) }),
                    },
                },
            },
            scales: {
                x: {
                    stacked: true,
                    grid: { display: false },
                    border: { color: token('--nx-border') || '#e5e7eb' },
                    // Up to ~6 weeks: day numbers (the 1st of a month named);
                    // longer ranges: only the month names at their 1st.
                    ticks: {
                        color: ink, maxRotation: 0, autoSkip: days.length <= 45, autoSkipPadding: 4, font: { size: 10.5 },
                        callback: (v, i) => {
                            if (!days[i]) return '';
                            const d = utc(days[i].date);
                            if (days.length > 45) return d.getUTCDate() === 1 ? monthShort.format(d) : '';
                            return d.getUTCDate() === 1 && i > 0 ? dayMonth.format(d) : d.getUTCDate();
                        },
                    },
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    grid: { color: grid, drawTicks: false },
                    border: { display: false, dash: [3, 3] },
                    ticks: { display: false },
                    afterBuildTicks: ax => { ax.ticks = [{ value: ax.max / 2 }, { value: ax.max }]; },
                },
            },
        };
        if (chart) chart.destroy();
        chart = new window.Chart(canvas, { type: 'bar', data, options, plugins: [weekendPlugin] });
        const total = days.reduce((a, d) => a + d.billable + d.service + d.absence, 0);
        document.getElementById('bps-chart-meta').textContent = fmt(S.chartMeta, { days: days.length, n: hours(total) });
    }
    // Repaint on a theme switch: the hues and the gap colour are tokens.
    new MutationObserver(() => { if (days.length) drawChart(); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });

    // ---- drill-down ------------------------------------------------------------
    function keep(r) {
        if (state.billableOnly && r.category !== 'billable') return false;
        if (state.hideAbsences && r.category === 'absence') return false;
        const q = state.query.trim().toLowerCase();
        if (q) {
            const hay = `${r.task} ${r.customer} ${r.package || ''} ${r.person}`.toLowerCase();
            if (!hay.includes(q)) return false;
        }
        return true;
    }
    const visibleRows = () => state.rows.filter(keep);
    const visiblePrev = () => state.prevRows.filter(keep);

    function prevName() {
        if (!state.prev) return '';
        // "July" -- or "December 2025" / "Sep 2024 – Aug 2025" when its year
        // is not the headline's, so the comparison is never ambiguous.
        const p = Sy.periodHeadline(state.prev.from, state.prev.to, lang, S.weekLabel);
        return p.year === hl.year ? p.main : `${p.main} ${p.year}`;
    }

    function vsHtml(value, prev) {
        const d = V.delta(value, prev);
        const period = prevName();
        if (d.dir === 'new') {
            const note = fmt(S.notBooked, { period });
            return `<span class="nx-bps-vs is-up" title="${esc(note)}"><span class="nx-bps-vs__pct"><i class="fas fa-arrow-trend-up" aria-hidden="true"></i>${esc(S.isNew)}</span><span class="nx-bps-vs__h">${esc(note)}</span></span>`;
        }
        const cls = d.dir === 'up' ? 'is-up' : d.dir === 'down' ? 'is-down' : 'is-flat';
        const icon = d.dir === 'up' ? 'fa-arrow-trend-up' : d.dir === 'down' ? 'fa-arrow-trend-down' : 'fa-minus';
        const p = d.ratio === null ? '' : signed(Math.round(d.ratio * 100), n => `${n}%`);
        return `<span class="nx-bps-vs ${cls}" title="${esc(fmt(S.vsPrev, { period }))}"><span class="nx-bps-vs__pct"><i class="fas ${icon}" aria-hidden="true"></i>${esc(p)}</span><span class="nx-bps-vs__h">${esc(hUnit(signed(d.diff, hours)))}</span></span>`;
    }

    function splitSegs(g, cls) {
        const parts = [['billable', g.billable], ['service', g.service], ['absence', g.absence]].filter(p => p[1] > 0);
        return parts.map(([cat, h]) => `<span class="${cls} ${cls}--${cat}" style="flex:${h} 1 0"></span>`).join('');
    }

    function tableHtml(dim, levelTotal, prevLevel) {
        const max = groups.length ? groups[0].hours : 1;
        const head = `
            <div class="nx-bps-trow nx-bps-trow--head" aria-hidden="true">
              <span>${esc(S.names[dim])}</span><span class="nx-num">${esc(S.colHours)}</span><span class="nx-num">${esc(S.catBillable)}</span>
              <span class="nx-num">${esc(S.bookings)}</span><span class="nx-num nx-bps-trow__vs" title="${esc(fmt(S.vsPrev, { period: prevName() }))}">${esc(fmt(S.vsPrev, { period: prevName() }))}</span><span>${esc(S.split)}</span><span></span>
            </div>`;
        const rows = groups.map((g, i) => `
            <button type="button" class="nx-bps-trow" data-zoom="${i}">
              <span class="nx-bps-trow__name"><span class="nx-bps-mark nx-bps-mark--${g.cat}" aria-hidden="true"></span><span class="nx-bps-trow__text">${esc(label(g.key))}</span></span>
              <span class="nx-num nx-bps-trow__h">${esc(hours(g.hours))}</span>
              <span class="nx-num nx-bps-trow__sub">${g.billable ? esc(hours(g.billable)) : '·'}</span>
              <span class="nx-num nx-bps-trow__sub">${esc(intFmt.format(g.count))}</span>
              ${vsHtml(g.hours, g.prev)}
              <span class="nx-bps-split">
                <span class="nx-bps-split__track"><span class="nx-bps-split__bar" style="width:${((g.hours / max) * 100).toFixed(1)}%">${splitSegs(g, 'nx-bps-split__seg')}</span></span>
                <span class="nx-bps-split__pct">${esc(pct(g.hours, levelTotal))}</span>
              </span>
              <i class="fas fa-chevron-right nx-bps-trow__chev" aria-hidden="true"></i>
            </button>`).join('');
        const billable = groups.reduce((a, g) => a + g.billable, 0);
        const count = groups.reduce((a, g) => a + g.count, 0);
        const total = `
            <div class="nx-bps-trow nx-bps-trow--total">
              <span class="nx-bps-trow__name">${esc(S.total)}</span>
              <span class="nx-num">${esc(hours(levelTotal))}</span>
              <span class="nx-num">${esc(hours(billable))}</span>
              <span class="nx-num">${esc(intFmt.format(count))}</span>
              ${vsHtml(levelTotal, prevLevel)}
              <span></span><span></span>
            </div>`;
        return `<div class="nx-bps-table">${head}${rows}${total}</div>`;
    }

    const MAP_H = 440;
    const GAP = 4;
    function mapHtml(levelTotal) {
        const box = document.getElementById('bps-drill');
        const W = Math.max(200, box.clientWidth);
        const rects = V.squarify(groups.map(g => ({ h: g.hours })), W + GAP, MAP_H + GAP);
        const period = prevName();
        const tiles = rects.map(r => {
            const g = groups[r.i];
            const w = r.w - GAP;
            const h = r.h - GAP;
            const big = w > 220 && h > 110;
            const title = `${label(g.key)} · ${hUnit(hours(g.hours))} · ${fmt(S.nBookings, { n: intFmt.format(g.count) })}`;
            let text = '';
            // Narrow tall tiles still get a label, set vertically; small
            // squarish ones a compact one; only slivers rely on the tooltip.
            const vertical = w <= 70 && w >= 22 && h >= 90;
            const compact = !vertical && w <= 70 && w > 40 && h > 40;
            if (vertical || compact) {
                text = `<span class="nx-bps-tile__text nx-bps-tile__text--${vertical ? 'vertical' : 'compact'}">
                    <span class="nx-bps-tile__name">${esc(label(g.key))}</span>
                    <span class="nx-bps-tile__h">${esc(hours(g.hours))}</span>
                  </span>`;
            } else if (w > 70 && h > 46) {
                let pill = '';
                if (w > 110 && h > 70) {
                    const d = V.delta(g.hours, g.prev);
                    if (d.dir === 'new') pill = `<span class="nx-bps-tile__pill is-up">↗ ${esc(S.isNew)}</span>`;
                    else if (d.ratio !== null) {
                        const arrow = d.dir === 'up' ? '↗' : d.dir === 'down' ? '↘' : '→';
                        const cls = d.dir === 'up' ? 'is-up' : d.dir === 'down' ? 'is-down' : 'is-flat';
                        pill = `<span class="nx-bps-tile__pill ${cls}">${arrow} ${esc(signed(Math.round(d.ratio * 100), n => `${n}%`))} ${esc(fmt(S.vsPrev, { period }))}</span>`;
                    }
                }
                text = `<span class="nx-bps-tile__text">
                    <span class="nx-bps-tile__name">${esc(label(g.key))}</span>
                    <span class="nx-bps-tile__h">${esc(hours(g.hours))}<small>${esc(hUnit('').trim())} · ${esc(pct(g.hours, levelTotal))}</small></span>
                    ${pill}
                  </span>`;
            }
            return `<button type="button" class="nx-bps-tile nx-bps-tile--${g.cat}${big ? ' nx-bps-tile--big' : ''}" data-zoom="${r.i}" title="${esc(title)}" aria-label="${esc(title)}"
                style="left:${r.x.toFixed(1)}px;top:${r.y.toFixed(1)}px;width:${Math.max(0, w).toFixed(1)}px;height:${Math.max(0, h).toFixed(1)}px">
                ${text}<span class="nx-bps-tile__strip" aria-hidden="true">${splitSegs(g, 'nx-bps-tile__seg')}</span>
              </button>`;
        }).join('');
        return `<div class="nx-bps-map" style="height:${MAP_H}px">${tiles}</div>`;
    }

    // ---- the leaf: a person's (or task's) single bookings, per day ------------
    const entriesCache = new Map();
    const pathKey = () => state.order.join(',') + '␟' + state.path.join('␟');
    const DAY_ROWS = 5;

    function leafList(res) {
        return res.entries.filter(e => (!state.billableOnly || e.category === 'billable') && (!state.hideAbsences || e.category !== 'absence'));
    }

    function leafHtml(res) {
        if (!res) return `<p class="nx-bps-msg">${esc(S.entries)}</p>`;
        if (res.error) return `<p class="nx-bps-msg is-error">${esc(res.error || S.entriesFail)}</p>`;
        const list = leafList(res);
        if (!list.length) return `<p class="nx-bps-msg">${esc(S.nothing)}</p>`;
        const blocks = V.byDay(list).map(d => {
            const date = utc(d.date);
            const open = state.openDays.has(d.date);
            const shown = open ? d.entries : d.entries.slice(0, DAY_ROWS);
            const rows = shown.map(e => {
                const comment = e.comment
                    ? `<span class="nx-bps-bk__c" title="${esc(e.comment)}">${esc(e.comment)}</span>`
                    : `<span class="nx-bps-bk__c is-empty">${esc(S.noComment)}</span>`;
                return `<div class="nx-bps-bk">${comment}<span class="nx-bps-bk__p" title="${esc(e.package || '')}">${esc(e.package || '')}</span><span class="nx-bps-bk__h">${esc(hFine.format(e.hours))}</span></div>`;
            }).join('');
            const more = d.entries.length > DAY_ROWS
                ? `<button type="button" class="nx-bps-more" data-day="${esc(d.date)}" aria-expanded="${open}">${esc(open ? S.showFewer : fmt(S.showMore, { n: d.entries.length - DAY_ROWS }))}</button>`
                : '';
            return `<div class="nx-bps-day">
                <div class="nx-bps-day__when">
                  <div class="nx-bps-day__date"><b>${esc(dayMonth.format(date))}</b><span>${esc(weekdayShort.format(date))}</span></div>
                  <div class="nx-bps-day__total">${esc(hUnit(hFine.format(d.hours)))}</div>
                  <div class="nx-bps-day__count">${esc(fmt(S.nBookings, { n: intFmt.format(d.count) }))}</div>
                </div>
                <div class="nx-bps-day__list">${rows}${more}</div>
              </div>`;
        }).join('');
        return `<div class="nx-bps-days">${blocks}</div>` + (res.truncated ? `<p class="nx-bps-msg">${esc(S.entriesCut)}</p>` : '');
    }

    function leafMeta(res) {
        if (!res || res.error) return '';
        const list = leafList(res);
        if (!list.length) return '';
        const sum = list.reduce((a, e) => a + (Number(e.hours) || 0), 0);
        return fmt(S.leafMeta, { h: hUnit(hFine.format(sum)), n: intFmt.format(list.length) });
    }

    async function loadEntries(key) {
        const params = new URLSearchParams({ from: CFG.from, to: CFG.to });
        state.order.forEach((dim, i) => params.set(PARAM[dim], state.path[i]));
        const res = await window.NX.apiSafe('/api/bps/entries?' + params.toString());
        entriesCache.set(key, res.ok && res.data && !res.data.error ? res.data : { error: (res.data && res.data.error) || S.entriesFail });
        if (pathKey() === key) render();
    }

    // ---- render ------------------------------------------------------------------
    function crumbsHtml() {
        const items = [S.allOf[state.order[0]]].concat(state.path.map(label));
        return items.map((text, depth) => {
            const sep = depth ? '<i class="fas fa-chevron-right nx-bps-crumbs__sep" aria-hidden="true"></i>' : '';
            if (depth === items.length - 1) return `${sep}<span class="nx-bps-crumb is-current" aria-current="page">${esc(text)}</span>`;
            return `${sep}<button type="button" class="nx-bps-crumb" data-depth="${depth}">${esc(text)}</button>`;
        }).join('');
    }

    function render(focus) {
        if (!state.loaded) return;
        const drill = document.getElementById('bps-drill');
        const leaf = state.path.length >= state.order.length;
        // Zooming swaps a long level for a shorter one (or the one-line
        // "Loading bookings…"); the page would shrink under the reader and the
        // browser clamp the scroll, throwing them up the page. So: bring the
        // breadcrumb into view when it has scrolled off, then keep at least a
        // viewport of room below the drill-down's top while it re-renders.
        const crumbsRow = document.querySelector('.nx-bps-crumbs');
        if (focus && crumbsRow.getBoundingClientRect().top < 0) {
            crumbsRow.scrollIntoView({ block: 'start', behavior: 'instant' });
        }
        drill.style.minHeight = `${Math.max(0, Math.round(window.innerHeight - drill.getBoundingClientRect().top))}px`;
        document.getElementById('bps-crumbs').innerHTML = crumbsHtml();
        document.getElementById('bps-back').hidden = state.path.length === 0;
        document.getElementById('bps-legend-hint').textContent = state.view === 'map' ? S.hintMap : S.hintTable;
        document.querySelectorAll('#bps-view [data-view]').forEach(b => b.setAttribute('aria-pressed', b.dataset.view === state.view ? 'true' : 'false'));
        document.getElementById('bps-view').hidden = leaf;
        const meta = document.getElementById('bps-level-meta');

        if (leaf) {
            groups = [];
            const key = pathKey();
            if (!entriesCache.has(key)) {
                entriesCache.set(key, null);
                loadEntries(key);
            }
            const res = entriesCache.get(key);
            drill.innerHTML = leafHtml(res);
            meta.textContent = leafMeta(res);
        } else {
            const dim = state.order[state.path.length];
            groups = V.level(visibleRows(), visiblePrev(), state.order, state.path);
            const levelTotal = groups.reduce((a, g) => a + g.hours, 0);
            meta.textContent = groups.length
                ? fmt(S.levelMeta, { items: fmt(S.plural[dim], { n: intFmt.format(groups.length) }), h: hUnit(hours(levelTotal)) })
                : '';
            if (!groups.length) {
                drill.innerHTML = `<p class="nx-bps-msg">${esc(state.rows.length ? S.nothing : S.emptyPeriod)}</p>`;
            } else if (state.view === 'map') {
                drill.innerHTML = mapHtml(levelTotal);
            } else {
                drill.innerHTML = tableHtml(dim, levelTotal, V.prevTotal(visiblePrev(), state.order, state.path));
            }
        }
        if (focus) {
            const first = drill.querySelector('button, a[href]');
            (first || drill).focus({ preventScroll: true });
        }
    }

    // Going up lands the focus on the row (or tile) the reader came from.
    function zoomTo(depth) {
        const target = Math.max(0, depth);
        const came = state.path.length > target ? state.path[target] : undefined;
        state.path.length = target;
        state.openDays.clear();
        render(true);
        const i = groups.findIndex(g => g.key === came);
        const row = i >= 0 && document.querySelector(`#bps-drill [data-zoom="${i}"]`);
        if (row) row.focus({ preventScroll: true });
    }

    const drillEl = document.getElementById('bps-drill');
    drillEl.tabIndex = -1;
    drillEl.addEventListener('click', e => {
        const more = e.target.closest('[data-day]');
        if (more) {
            const day = more.dataset.day;
            if (state.openDays.has(day)) state.openDays.delete(day); else state.openDays.add(day);
            render();
            const again = drillEl.querySelector(`[data-day="${CSS.escape(day)}"]`);
            if (again) again.focus();
            return;
        }
        const z = e.target.closest('[data-zoom]');
        if (!z) return;
        const g = groups[Number(z.dataset.zoom)];
        if (!g) return;
        state.path.push(g.key);
        state.openDays.clear();
        render(true);
    });
    document.getElementById('bps-crumbs').addEventListener('click', e => {
        const c = e.target.closest('[data-depth]');
        if (c) zoomTo(Number(c.dataset.depth));
    });
    document.getElementById('bps-back').addEventListener('click', () => zoomTo(state.path.length - 1));
    document.getElementById('bps-tree').addEventListener('keydown', e => {
        const typing = e.target.matches('input, textarea, select');
        if (!state.path.length || typing) return;
        if (e.key === 'Backspace' || (e.altKey && e.key === 'ArrowLeft')) {
            e.preventDefault();
            zoomTo(state.path.length - 1);
        }
    });

    // ---- toolbar -------------------------------------------------------------
    document.querySelectorAll('#bps-order [data-order]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#bps-order [data-order]').forEach(b => {
                b.classList.toggle('is-active', b === btn);
                b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
            });
            state.order = btn.dataset.order.split(',');
            state.path = [];
            render();
        });
    });
    document.querySelectorAll('#bps-view [data-view]').forEach(btn => {
        btn.addEventListener('click', () => {
            state.view = btn.dataset.view;
            try { window.localStorage.setItem('nx.bps.view', state.view); } catch (e) { /* private mode */ }
            render();
        });
    });
    function chip(id, key) {
        const el = document.getElementById(id);
        el.addEventListener('click', () => {
            state[key] = !state[key];
            el.setAttribute('aria-pressed', state[key] ? 'true' : 'false');
            render();
        });
    }
    chip('bps-billable-only', 'billableOnly');
    chip('bps-hide-absences', 'hideAbsences');
    let searchTimer = null;
    document.getElementById('bps-search').addEventListener('input', e => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            state.query = e.target.value;
            state.path = [];
            render();
        }, 150);
    });
    let resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (state.view === 'map' && state.path.length < state.order.length) render();
            if (days.length) drawChart();
        }, 150);
    });

    // ---- load ----------------------------------------------------------------
    async function load() {
        setStatus(S.loading, 'running');
        const params = new URLSearchParams({ from: CFG.from, to: CFG.to });
        const res = await window.NX.apiSafe('/api/bps/summary?' + params.toString());
        const kpis = document.getElementById('bps-kpis');
        kpis.setAttribute('aria-busy', 'false');
        if (!res.ok || !res.data || res.data.error) {
            setStatus(S.failed, 'failed');
            showError(res.data);
            kpis.innerHTML = '';
            return;
        }
        const p = res.data;
        state.rows = p.rows;
        state.prev = p.prev || null;
        state.prevRows = (p.prev && p.prev.rows) || [];
        state.loaded = true;
        days = p.days;
        kpis.innerHTML = totalsHtml(p.totals);
        const comp = compHtml(p.totals);
        document.getElementById('bps-comp').innerHTML = comp.bar;
        const labels = document.getElementById('bps-comp-labels');
        labels.style.gridTemplateColumns = comp.cols;
        labels.innerHTML = comp.labels;
        drawChart();
        render();
        setStatus(fmt(S.bookingsLoaded, { n: intFmt.format(p.totals.count) }), 'live');
        if (p.truncated) showError({ error: S.truncated });
    }

    load();
})();
