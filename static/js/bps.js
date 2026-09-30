/* Sydoc BPS (#415). Behaviour only -- strings and Jinja data arrive on
   window.NX_BPS; see templates/js/_bps_js.html.

   One summary request per period returns hours and bookings per
   task / customer / package / person. The KPI strip, the daily chart and the
   drill-down tree are all built from it in the browser, so switching the
   tree's order or filtering it never goes back to the server. Only a leaf
   (the third level) loads its single bookings, with their comments, on
   demand from /api/bps/entries.

   Colour carries category only (billable / other service / absence), always
   next to a text label; the three hues are the page's --bps-* tokens, checked
   with the dataviz validator in both themes. */
(function () {
    'use strict';

    const CFG = window.NX_BPS;
    const S = CFG.strings;
    const esc = window.NX.esc;
    const lang = document.documentElement.lang || undefined;

    const intFmt = new Intl.NumberFormat(lang);
    const hFmt = new Intl.NumberFormat(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const hFine = new Intl.NumberFormat(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const pctFmt = new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 0 });
    const dayFmt = new Intl.DateTimeFormat(lang, { day: 'numeric', month: 'short' });
    const weekdayFmt = new Intl.DateTimeFormat(lang, { weekday: 'short', day: 'numeric', month: 'short' });

    function fmt(str, vars) {
        return String(str).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    }
    const hours = n => hFmt.format(Number(n) || 0);
    const pct = (a, b) => pctFmt.format(b > 0 ? a / b : 0);
    const isoDate = iso => new Date(iso + 'T00:00:00');

    // ---- period form: presets fill the two dates and submit ------------------
    const form = document.getElementById('bps-period');
    const fromEl = document.getElementById('bps-from');
    const toEl = document.getElementById('bps-to');
    function ymd(d) {
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    }
    const PRESETS = {
        'last-month': t => [new Date(t.getFullYear(), t.getMonth() - 1, 1), new Date(t.getFullYear(), t.getMonth(), 0)],
        'this-month': t => [new Date(t.getFullYear(), t.getMonth(), 1), t],
        'last-week': t => {
            const monday = new Date(t);
            monday.setDate(t.getDate() - ((t.getDay() + 6) % 7) - 7);
            const sunday = new Date(monday);
            sunday.setDate(monday.getDate() + 6);
            return [monday, sunday];
        },
        'quarter': t => [new Date(t.getFullYear(), t.getMonth() - 3, 1), new Date(t.getFullYear(), t.getMonth(), 0)],
    };
    const today = isoDate(CFG.today);
    form.querySelectorAll('[data-preset]').forEach(btn => {
        const [a, b] = PRESETS[btn.dataset.preset](today);
        const active = ymd(a) === CFG.from && ymd(b) === CFG.to;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.addEventListener('click', () => {
            fromEl.value = ymd(a);
            toEl.value = ymd(b);
            form.requestSubmit();
        });
    });

    // ---- state ---------------------------------------------------------------
    const state = {
        rows: [],
        order: ['Aufgabe', 'Kunde', 'Benutzer'],
        billableOnly: false,
        hideAbsences: true,
        query: '',
        open: new Set(),
    };
    const FIELD = { Aufgabe: 'task', Kunde: 'customer', Benutzer: 'person' };
    const PARAM = { Aufgabe: 'task', Kunde: 'customer', Benutzer: 'person' };

    function setStatus(text, cls) {
        const el = document.getElementById('bps-status');
        el.classList.remove('is-done', 'is-failed');
        if (cls) el.classList.add(cls);
        document.getElementById('bps-status-text').textContent = text;
    }

    function showError(payload) {
        const el = document.getElementById('bps-error');
        const detail = payload && payload.detail ? `<span class="nx-bps-error__detail">${esc(payload.detail)}</span>` : '';
        el.innerHTML = `<i class="fas fa-triangle-exclamation" aria-hidden="true"></i><span>${esc((payload && payload.error) || S.failed)}</span>${detail}`;
        el.hidden = false;
    }

    // ---- KPIs ----------------------------------------------------------------
    function kpisHtml(t) {
        const service = t.billable + t.service;
        const tiles = [
            { key: 'total', label: S.totalHours, value: hours(t.hours), sub: S.inPeriod },
            { key: 'service', label: S.serviceHours, value: hours(service), sub: fmt(S.ofTotal, { pct: pct(service, t.hours) }) },
            { key: 'billable', label: S.billable, value: hours(t.billable), sub: fmt(S.ofService, { pct: pct(t.billable, service) }), cat: 'billable' },
            { key: 'absence', label: S.absence, value: hours(t.absence), sub: fmt(S.ofTotal, { pct: pct(t.absence, t.hours) }), cat: 'absence' },
            { key: 'bookings', label: S.bookings, value: intFmt.format(t.count), sub: S.inPeriod },
            { key: 'people', label: S.people, value: intFmt.format(t.people), sub: S.withHours },
        ];
        return tiles.map(k => `
            <div class="nx-kpi" data-testid="bps-kpi-${k.key}">
              <p class="nx-kpi__label">${k.cat ? `<span class="nx-bps-swatch nx-bps-swatch--${k.cat}" aria-hidden="true"></span>` : ''}${esc(k.label)}</p>
              <div class="nx-kpi__body"><div>
                <p class="nx-kpi__value">${esc(k.value)}</p>
                <p class="nx-kpi__delta">${esc(k.sub)}</p>
              </div></div>
            </div>`).join('');
    }

    // ---- chart ---------------------------------------------------------------
    let chart = null;
    let days = [];
    function token(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }
    function drawChart() {
        const canvas = document.getElementById('bps-chart');
        if (!window.Chart || !canvas) return;
        const surface = token('--nx-card') || '#fff';
        const series = [
            { key: 'billable', label: S.catBillable, color: token('--bps-billable') },
            { key: 'service', label: S.catService, color: token('--bps-service') },
            { key: 'absence', label: S.catAbsence, color: token('--bps-absence') },
        ];
        const labels = days.map(d => dayFmt.format(isoDate(d.date)));
        const data = {
            labels,
            datasets: series.map((s, i) => ({
                label: s.label,
                data: days.map(d => d[s.key]),
                backgroundColor: s.color,
                // A 2px surface gap between stacked segments; the rounded end
                // sits on the top segment only (absence), anchored bars below.
                borderColor: surface,
                borderWidth: { top: 2, bottom: 0, left: 0, right: 0 },
                borderSkipped: 'bottom',
                borderRadius: i === series.length - 1 ? { topLeft: 4, topRight: 4 } : 0,
                maxBarThickness: 22,
                categoryPercentage: 0.8,
                barPercentage: 0.9,
            })),
        };
        const ink = token('--nx-text-meta') || '#6b7280';
        const grid = token('--nx-divider') || 'rgba(0,0,0,.06)';
        const options = {
            responsive: true,
            maintainAspectRatio: false,
            animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 250 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: items => weekdayFmt.format(isoDate(days[items[0].dataIndex].date)),
                        label: item => ` ${item.dataset.label}: ${fmt(S.h, { n: hFine.format(item.raw) })}`,
                        footer: items => fmt(S.dayTotal, { n: hFine.format(items.reduce((a, i) => a + (Number(i.raw) || 0), 0)) }),
                    },
                },
            },
            scales: {
                x: { stacked: true, grid: { display: false }, ticks: { color: ink, maxRotation: 0, autoSkipPadding: 12, font: { size: 11 } }, border: { color: grid } },
                y: { stacked: true, beginAtZero: true, grid: { color: grid }, border: { display: false }, ticks: { color: ink, font: { size: 11 }, callback: v => fmt(S.h, { n: intFmt.format(v) }) } },
            },
        };
        if (chart) chart.destroy();
        chart = new window.Chart(canvas, { type: 'bar', data, options });
        const total = days.reduce((a, d) => a + d.billable + d.service + d.absence, 0);
        document.getElementById('bps-chart-meta').textContent = fmt(S.chartMeta, { days: days.length, n: hours(total) });
    }
    // Repaint on a theme switch: the hues and the gap colour are tokens.
    new MutationObserver(() => { if (days.length) drawChart(); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });

    // ---- tree ----------------------------------------------------------------
    function visibleRows() {
        const q = state.query.trim().toLowerCase();
        return state.rows.filter(r => {
            if (state.billableOnly && r.category !== 'billable') return false;
            if (state.hideAbsences && r.category === 'absence') return false;
            if (q) {
                const hay = `${r.task} ${r.customer} ${r.package || ''} ${r.person}`.toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });
    }

    // rows -> nested nodes along state.order, each with hours/billable/count.
    function buildTree(rows) {
        const root = { children: new Map(), hours: 0, billable: 0, count: 0, cats: new Set() };
        rows.forEach(r => {
            let node = root;
            const add = n => {
                n.hours += r.hours;
                n.count += r.count;
                if (r.category === 'billable') n.billable += r.hours;
                n.cats.add(r.category);
            };
            add(node);
            state.order.forEach(dim => {
                const key = r[FIELD[dim]];
                if (!node.children.has(key)) {
                    node.children.set(key, { key, dim, children: new Map(), hours: 0, billable: 0, count: 0, cats: new Set() });
                }
                node = node.children.get(key);
                add(node);
            });
        });
        return root;
    }

    function sorted(node) {
        return Array.from(node.children.values()).sort((a, b) => b.hours - a.hours || String(a.key).localeCompare(String(b.key)));
    }

    function tagHtml(node) {
        if (node.dim !== 'Aufgabe') return '';
        if (node.cats.size === 1 && node.cats.has('billable')) {
            return ` <span class="nx-label nx-label--nodot nx-bps-tag nx-bps-tag--billable">${esc(S.billableTag)}</span>`;
        }
        if (node.cats.has('billable')) {
            return ` <span class="nx-label nx-label--nodot nx-bps-tag nx-bps-tag--partly">${esc(S.partly)}</span>`;
        }
        if (node.cats.size === 1 && node.cats.has('absence')) {
            return ` <span class="nx-label nx-label--nodot nx-bps-tag nx-bps-tag--absence">${esc(S.catAbsence)}</span>`;
        }
        return '';
    }

    function shareHtml(value, total) {
        const share = total > 0 ? value / total : 0;
        return `<span class="nx-bps-share"><span class="nx-bps-share__bar" aria-hidden="true"><span class="nx-bps-share__fill" style="width:${(Math.min(1, share) * 100).toFixed(1)}%"></span></span><span class="nx-bps-share__pct">${esc(pctFmt.format(share))}</span></span>`;
    }

    function rowsHtml(node, path, level, parentHours) {
        const out = [];
        sorted(node).forEach(child => {
            const childPath = path.concat([[child.dim, child.key]]);
            const id = childPath.map(p => p[1]).join('␟');
            const leaf = level === state.order.length;
            const open = state.open.has(id);
            const label = child.key === null || child.key === '' ? '–' : child.key;
            out.push(`
              <tr class="nx-bps-row nx-bps-row--l${level}${open ? ' is-open' : ''}" aria-level="${level}" data-id="${esc(id)}">
                <th scope="row" class="nx-bps-name">
                  <button type="button" class="nx-bps-toggle" aria-expanded="${open ? 'true' : 'false'}"
                          data-toggle="${esc(id)}" data-leaf="${leaf ? '1' : ''}" data-path="${esc(JSON.stringify(childPath))}"
                          aria-label="${esc(fmt(S.expand, { name: label }))}">
                    <i class="fas fa-chevron-right" aria-hidden="true"></i>
                  </button>
                  <span class="nx-bps-name__text">${esc(label)}</span>${tagHtml(child)}
                </th>
                <td class="nx-num">${esc(hours(child.hours))}</td>
                <td class="nx-num${child.billable ? '' : ' is-zero'}">${child.billable ? esc(hours(child.billable)) : '·'}</td>
                <td class="nx-num">${esc(intFmt.format(child.count))}</td>
                <td class="nx-num">${shareHtml(child.hours, parentHours)}</td>
              </tr>`);
            if (open) {
                if (leaf) {
                    out.push(`<tr class="nx-bps-entries-row" data-for="${esc(id)}"><td colspan="5"><div class="nx-bps-entries" data-entries="${esc(id)}">${entriesCache.has(id) ? entriesHtml(entriesCache.get(id)) : `<p class="nx-bps-entries__msg">${esc(S.entries)}</p>`}</div></td></tr>`);
                } else {
                    out.push(rowsHtml(child, childPath, level + 1, child.hours));
                }
            }
        });
        return out.join('');
    }

    function renderTree() {
        const tree = buildTree(visibleRows());
        document.getElementById('bps-col-name').textContent = state.order.map(d => S.names[d]).join(' › ');
        const body = document.getElementById('bps-tree-body');
        const foot = document.getElementById('bps-tree-foot');
        if (!tree.children.size) {
            body.innerHTML = `<tr><td colspan="5" class="nx-bps-empty">${esc(state.rows.length ? S.nothing : S.emptyPeriod)}</td></tr>`;
            foot.innerHTML = '';
            return;
        }
        body.innerHTML = rowsHtml(tree, [], 1, tree.hours);
        foot.innerHTML = `<tr><th scope="row">${esc(S.total)}</th><td class="nx-num">${esc(hours(tree.hours))}</td>` +
            `<td class="nx-num">${esc(hours(tree.billable))}</td><td class="nx-num">${esc(intFmt.format(tree.count))}</td><td></td></tr>`;
    }

    // ---- bookings of a leaf --------------------------------------------------
    const entriesCache = new Map();
    function entriesHtml(res) {
        if (!res || res.error) return `<p class="nx-bps-entries__msg is-error">${esc((res && res.error) || S.entriesFail)}</p>`;
        const list = res.entries.filter(e => (!state.billableOnly || e.category === 'billable') && (!state.hideAbsences || e.category !== 'absence'));
        if (!list.length) return `<p class="nx-bps-entries__msg">${esc(S.nothing)}</p>`;
        const rows = list.map(e => `
            <tr>
              <td class="nx-bps-e__date">${esc(weekdayFmt.format(isoDate(e.date)))}</td>
              <td>${esc(e.package || '')}</td>
              <td class="nx-num">${esc(hFine.format(e.hours))}</td>
              <td class="nx-bps-e__comment">${esc(e.comment || '')}</td>
            </tr>`).join('');
        return `<table class="nx-table nx-bps-e">
            <thead><tr><th scope="col">${esc(S.colDate)}</th><th scope="col">${esc(S.colPackage)}</th><th scope="col" class="nx-num">${esc(S.colHours)}</th><th scope="col">${esc(S.colComment)}</th></tr></thead>
            <tbody>${rows}</tbody></table>` +
            (res.truncated ? `<p class="nx-bps-entries__msg">${esc(S.entriesCut)}</p>` : '');
    }

    async function loadEntries(id, path) {
        const params = new URLSearchParams({ from: CFG.from, to: CFG.to });
        path.forEach(([dim, key]) => params.set(PARAM[dim], key));
        const res = await window.NX.apiSafe('/api/bps/entries?' + params.toString());
        entriesCache.set(id, res.ok && res.data ? res.data : { error: S.entriesFail });
        const box = document.querySelector(`[data-entries="${CSS.escape(id)}"]`);
        if (box) box.innerHTML = entriesHtml(entriesCache.get(id));
    }

    document.getElementById('bps-tree').addEventListener('click', e => {
        const btn = e.target.closest('[data-toggle]');
        const row = e.target.closest('.nx-bps-row');
        const target = btn || (row && row.querySelector('[data-toggle]'));
        if (!target) return;
        const id = target.dataset.toggle;
        const opening = !state.open.has(id);
        if (opening) state.open.add(id); else state.open.delete(id);
        renderTree();
        const again = document.querySelector(`[data-toggle="${CSS.escape(id)}"]`);
        if (again) again.focus();
        if (opening && target.dataset.leaf && !entriesCache.has(id)) {
            loadEntries(id, JSON.parse(target.dataset.path));
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
            state.open.clear();
            entriesCache.clear();
            renderTree();
        });
    });
    document.getElementById('bps-billable-only').addEventListener('change', e => { state.billableOnly = e.target.checked; renderTree(); });
    document.getElementById('bps-hide-absences').addEventListener('change', e => { state.hideAbsences = e.target.checked; renderTree(); });
    let searchTimer = null;
    document.getElementById('bps-search').addEventListener('input', e => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            state.query = e.target.value;
            // A filter narrows the tree; open every branch so matches are visible.
            state.open.clear();
            if (state.query.trim()) {
                const tree = buildTree(visibleRows());
                const walk = (node, path, level) => sorted(node).forEach(c => {
                    const p = path.concat([c.key]);
                    if (level < state.order.length) {
                        state.open.add(p.join('␟'));
                        walk(c, p, level + 1);
                    }
                });
                walk(tree, [], 1);
            }
            renderTree();
        }, 150);
    });

    // ---- load ----------------------------------------------------------------
    async function load() {
        setStatus(S.loading);
        const params = new URLSearchParams({ from: CFG.from, to: CFG.to });
        const res = await window.NX.apiSafe('/api/bps/summary?' + params.toString());
        const kpis = document.getElementById('bps-kpis');
        kpis.setAttribute('aria-busy', 'false');
        if (!res.ok || !res.data || res.data.error) {
            setStatus(S.failed, 'is-failed');
            showError(res.data);
            kpis.innerHTML = '';
            return;
        }
        const p = res.data;
        state.rows = p.rows;
        days = p.days;
        kpis.innerHTML = kpisHtml(p.totals);
        drawChart();
        renderTree();
        setStatus(fmt(S.loaded, {
            n: intFmt.format(p.totals.count),
            from: window.NX.formatDate(p.from),
            to: window.NX.formatDate(p.to),
        }), 'is-done');
        if (p.truncated) showError({ error: S.truncated });
    }

    load();
})();
