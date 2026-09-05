/* Dashboard console (option 1a). Behaviour only -- strings and Jinja data
   arrive on window.NX_DASH; see templates/js/_dashboard_js.html. */
(function () {
    'use strict';

    const S = window.NX_DASH.strings;
    const P = window.API_PREFIX;
    const SERIES_DASH = [[], [6, 4], [2, 3], [10, 3, 2, 3], [4, 2]];

    let processedChart, hourlyChart, backlogChart;
    let view = 'time';
    let range = window.NX_DASH.range || 14;
    let countdown = window.NX_DASH.refreshMs / 1000;

    // Count-up start values, so a refresh animates from the number already on
    // screen instead of restarting at zero.
    const last = { imported: 0, processed: 0, backlog: 0 };

    // The shim's strings carry {name} placeholders (gettext's own %(name)s
    // cannot survive Jinja's _(), which always runs `rv % variables`).
    function fmt(str, vars) {
        return String(str).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    }

    function token(name, fallback) {
        return (getComputedStyle(document.body).getPropertyValue(name) || fallback).trim();
    }

    // Theme-aware chart colors: read the --nx-* design tokens (which flip
    // under html.dark) and re-theme live charts when dark mode is toggled.
    function nxAxis() {
        return { grid: token('--nx-divider', '#f3f4f6'), text: token('--nx-text-meta', '#9ca3af') };
    }

    function seriesColor(i) { return token(`--nx-series-${(i % 5) + 1}`, '#d97706'); }

    function applyChartTheme() {
        const { grid, text } = nxAxis();
        if (window.Chart) Chart.defaults.color = text;
        [processedChart, hourlyChart, backlogChart].forEach(ch => {
            if (!ch || !ch.options || !ch.options.scales) return;
            Object.values(ch.options.scales).forEach(sc => {
                if (sc && sc.grid) sc.grid.color = grid;
                if (sc) sc.ticks = Object.assign({}, sc.ticks, { color: text });
            });
            ch.update('none');
        });
    }
    new MutationObserver(applyChartTheme).observe(
        document.documentElement, { attributes: true, attributeFilter: ['class'] });

    // ponytail: one plugin, not a rewrite of every chart's empty-state markup
    const noDataPlugin = {
        id: 'noData',
        afterDraw(chart) {
            const hasData = chart.data.datasets.some(ds => ds.data.some(v => v > 0));
            if (hasData) return;
            const { ctx, chartArea: { left, top, right, bottom } } = chart;
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = "14px 'Inter', sans-serif";
            ctx.fillStyle = nxAxis().text;
            ctx.fillText(S.noData, (left + right) / 2, (top + bottom) / 2);
            ctx.restore();
        }
    };

    function animateValue(element, start, end, duration, suffix = '') {
        if (!element) return;
        start = parseFloat(start) || 0;
        end = parseFloat(end) || 0;
        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            element.innerText = Math.floor(progress * (end - start) + start).toLocaleString() + suffix;
            if (progress < 1) window.requestAnimationFrame(step);
        };
        window.requestAnimationFrame(step);
    }

    /* ---------- sparklines: 7 points, hand-built polyline (D3) ---------- */
    function drawSparkline(svg, values, color) {
        if (!svg) return;
        svg.innerHTML = '';
        const pts = (values || []).filter((v) => v !== null && v !== undefined);
        if (pts.length < 2) return;
        const min = Math.min(...pts), max = Math.max(...pts);
        const span = max - min || 1;
        const step = 120 / (pts.length - 1);
        const xy = pts.map((v, i) => [i * step, 34 - ((v - min) / span) * 30]);
        const line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join('');
        const area = `${line}L120,36L0,36Z`;
        svg.insertAdjacentHTML('beforeend',
            `<path d="${area}" fill="${color}" fill-opacity="0.14" stroke="none"></path>` +
            `<path d="${line}" fill="none" stroke="${color}" stroke-width="1.6"></path>`);
    }

    /* ---------- one KPI cell ---------- */
    function renderKpi(id, value, prev, series, opts) {
        opts = opts || {};
        const cell = document.getElementById(`kpi-${id}`);
        if (!cell) return;
        const valueEl = cell.querySelector('.nx-kpi__value');
        const deltaEl = cell.querySelector('.nx-kpi__delta');
        if (opts.display !== undefined) {
            valueEl.textContent = opts.display;
        } else if (opts.countFrom !== undefined) {
            // The cell still holds its skeleton span on the first paint;
            // animateValue writes plain text over it.
            animateValue(valueEl, opts.countFrom, value, 1500);
        } else {
            valueEl.textContent = Number(value || 0).toLocaleString();
        }

        deltaEl.className = 'nx-kpi__delta';
        // A user with no process grants gets 0/0 (never null) from kpi_stats,
        // so a plain 0-vs-0 comparison would paint a green "+0% vs. yesterday"
        // across an empty dashboard. Nothing happened -- show nothing.
        if (prev === null || prev === undefined || value === null || value === undefined
            || (!value && !prev)) {
            deltaEl.textContent = '';
        } else {
            const diff = value - prev;
            // Direction-aware: fewer backlog items / less processing time is good.
            const good = opts.lowerIsBetter ? diff <= 0 : diff >= 0;
            deltaEl.classList.add(good ? 'nx-kpi__delta--good' : 'nx-kpi__delta--bad');
            const shown = opts.formatDelta ? opts.formatDelta(diff)
                : `${diff >= 0 ? '+' : ''}${prev ? Math.round((diff / prev) * 100) : 0}%`;
            deltaEl.innerHTML = `${window.NX.esc(shown)} <span>${window.NX.esc(S.vsYesterday)}</span>`;
        }
        drawSparkline(cell.querySelector('.nx-kpi__spark'), series,
            opts.lowerIsBetter ? token('--nx-success', '#059669') : token('--nx-accent', '#d97706'));
    }

    /* ---------- the four KPI cells ---------- */
    async function updateKpis() {
        try {
            const [statsRes, aptRes] = await Promise.all([
                fetch(`${P}api/dashboard/kpi_stats`, { headers: { 'Content-Type': 'application/json' } }),
                fetch(`${P}api/dashboard/avg_processing_time`, { headers: { 'Content-Type': 'application/json' } })
            ]);
            if (!statsRes.ok || !aptRes.ok) {
                console.error('kpi_stats HTTP', statsRes.status, 'avg_processing_time HTTP', aptRes.status);
                return;
            }
            const stats = await statsRes.json();
            const apt = await aptRes.json();
            const series = stats.series || {};

            renderKpi('imported', stats.imported_today, stats.prev_imported,
                series.imported, { countFrom: last.imported });
            renderKpi('processed', stats.processed_today, stats.prev_processed,
                series.processed, { countFrom: last.processed });
            renderKpi('backlog', stats.current_backlog, stats.prev_backlog, series.backlog, {
                countFrom: last.backlog,
                lowerIsBetter: true,
                formatDelta: (d) => (d >= 0 ? '+' : '') + d.toLocaleString()
            });
            last.imported = stats.imported_today || 0;
            last.processed = stats.processed_today || 0;
            last.backlog = stats.current_backlog || 0;

            renderKpi('avgtime', apt.avg_minutes, apt.prev_avg_minutes, apt.series, {
                display: apt.avg_display || '—',
                lowerIsBetter: true,
                formatDelta: (d) => `${d >= 0 ? '+' : ''}${(d / 60).toFixed(1)}h`
            });
        } catch (error) {
            console.error('Failed to update KPI stats:', error);
        }
    }

    /* Parts 2 and 3 of Task 11 land here: updateOverTime(), updateHourly(),
       setView(), setRange(), updateBacklog(), refreshAll()/tick(). */

    async function setProcessFilter(value) {
        try {
            await fetch(`${P}api/dashboard/set_filter`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.NX.csrfToken() },
                body: JSON.stringify({ process_name: value })
            });
            updateKpis();
        } catch (error) {
            console.error('Failed to set process filter:', error);
        }
    }
    // The page-level NexoraProcessPicker binding in templates/dashboard.html
    // calls this by name -- the one global this module exposes.
    window.setProcessFilter = setProcessFilter;

    document.addEventListener('DOMContentLoaded', () => {
        updateKpis();
    });
})();
