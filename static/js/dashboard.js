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
            // Scale colours are read live from options, but a dataset's
            // borderColor was resolved once at construction -- the backlog
            // lines would keep their light-mode hues after a theme flip.
            if (ch === backlogChart) {
                ch.data.datasets.forEach((ds, i) => { ds.borderColor = seriesColor(i); });
            }
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
        // An all-zero series has nothing to show: drawn, it is a flat line
        // pinned to the baseline, which reads as a stray horizontal rule
        // rather than as data. Leave the cell empty instead.
        if (!pts.some((v) => v > 0)) return;
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
        // Sparkline colour is per-KPI (design 1a alternates accent/success down
        // the strip), NOT semantic. Deriving it from lowerIsBetter drew a
        // *rising* backlog in success-green -- reading as good news beside a
        // delta correctly coloured bad.
        drawSparkline(cell.querySelector('.nx-kpi__spark'), series,
            opts.spark === 'success' ? token('--nx-success', '#059669')
                : token('--nx-accent', '#d97706'));
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
                series.imported, { countFrom: last.imported, spark: 'accent' });
            renderKpi('processed', stats.processed_today, stats.prev_processed,
                series.processed, { countFrom: last.processed, spark: 'success' });
            renderKpi('backlog', stats.current_backlog, stats.prev_backlog, series.backlog, {
                countFrom: last.backlog,
                lowerIsBetter: true,
                spark: 'accent',
                formatDelta: (d) => (d >= 0 ? '+' : '') + d.toLocaleString()
            });
            last.imported = stats.imported_today || 0;
            last.processed = stats.processed_today || 0;
            last.backlog = stats.current_backlog || 0;

            renderKpi('avgtime', apt.avg_minutes, apt.prev_avg_minutes, apt.series, {
                display: apt.avg_display || '—',
                lowerIsBetter: true,
                spark: 'success',
                formatDelta: (d) => `${d >= 0 ? '+' : ''}${(d / 60).toFixed(1)}h`
            });
        } catch (error) {
            console.error('Failed to update KPI stats:', error);
        }
    }

    /* ---------- chart-head meta line ---------- */
    // Both views share one #chart-meta slot, so the summary is rebuilt from
    // whichever chart is currently on screen rather than written at fetch time.
    const meta = { days: null, hour: null };

    function renderMeta() {
        const el = document.getElementById('chart-meta');
        if (!el) return;
        const m = view === 'hour' ? meta.hour : meta.days;
        el.textContent = m || '';
    }

    /* ---------- "over time" line/area chart ---------- */
    async function updateOverTime() {
        try {
            const response = await fetch(`${P}api/dashboard/processed_over_time?range=${range}`, {
                headers: { 'Content-Type': 'application/json' }
            });
            if (!response.ok) {
                console.error('processed_over_time HTTP', response.status);
                return;
            }
            const data = await response.json();
            const canvas = document.getElementById('processedOverTimeChart');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');

            const values = data.data || [];
            meta.days = fmt(S.daysMeta, {
                days: range,
                peak: (values.length ? Math.max(...values) : 0).toLocaleString()
            });
            renderMeta();

            // Canvas needs a resolved color, not a CSS custom property string --
            // same pattern as nxAxis() above, just for the accent (and, below,
            // the tooltip card) instead of the grid/text tokens.
            const accent = token('--nx-accent', '#4f46e5');
            const nxCard = token('--nx-card', '#1e293b');
            const nxBorder = token('--nx-border', '#334155');
            const nxText = token('--nx-text', '#e2e8f0');
            const nxTextMeta = token('--nx-text-meta', '#64748b');
            const gradient = ctx.createLinearGradient(0, 0, 0, 300);
            gradient.addColorStop(0, `color-mix(in srgb, ${accent} 20%, transparent)`);
            gradient.addColorStop(1, 'transparent');

            if (processedChart) {
                processedChart.data.labels = data.labels;
                processedChart.data.datasets[0].data = values;
                processedChart.update();
                return;
            }

            processedChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: S.documents,
                        data: values,
                        fill: true,
                        backgroundColor: gradient,
                        borderColor: accent,
                        borderWidth: 3,
                        pointBackgroundColor: accent,
                        pointRadius: 0,
                        pointHoverRadius: 6,
                        tension: 0.4
                    }]
                },
                plugins: [noDataPlugin],
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    // Default Chart.js interaction requires the cursor to sit
                    // exactly on the line (intersect: true) to trigger the
                    // tooltip. 'index' + intersect:false instead matches on
                    // x-position alone, so hovering anywhere in that column
                    // -- not just the 3px-wide line itself -- shows the value.
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { beginAtZero: true, grid: { borderDash: [5, 5], color: nxAxis().grid } },
                        // Cap the labels: a 90-day window otherwise renders 90
                        // rotated dates into an unreadable smear.
                        x: {
                            grid: { display: false },
                            ticks: { maxTicksLimit: 14, autoSkip: true, maxRotation: 0 }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        // Default Chart.js tooltip is a plain black box that
                        // clashes with the rest of the app's card styling --
                        // reskin it to match (rounded, bordered, --nx-* colors).
                        tooltip: {
                            backgroundColor: nxCard,
                            titleColor: nxTextMeta,
                            bodyColor: nxText,
                            borderColor: nxBorder,
                            borderWidth: 1,
                            cornerRadius: 10,
                            padding: 10,
                            boxPadding: 6,
                            usePointStyle: true,
                            titleFont: { size: 11, weight: '600' },
                            titleMarginBottom: 6,
                            bodyFont: { size: 13, weight: '600' },
                            caretSize: 6
                        }
                    }
                }
            });

            // Chart.js's own mode:'index' hover only registers inside
            // chartArea. This dataset is beginAtZero with mostly-low
            // values, so the line sits right at chartArea's bottom edge
            // for most of its length -- a cursor a pixel below where the
            // line visually is (still "on the line" to the eye) falls
            // outside chartArea and the tooltip vanishes, while hovering
            // further up (safely inside chartArea) always works. Clamp
            // the pointer into chartArea before hit-testing so the whole
            // canvas height is a reliable hover target, not just the
            // area above the line.
            ctx.canvas.addEventListener('mousemove', (e) => {
                const area = processedChart.chartArea;
                const rect = ctx.canvas.getBoundingClientRect();
                const x = Math.min(Math.max(e.clientX - rect.left, area.left), area.right);
                const y = Math.min(Math.max(e.clientY - rect.top, area.top), area.bottom);
                // getElementsAtEventForMode -> getRelativePosition treats
                // {x, y} as already-canvas-relative ONLY when a `native`
                // key is present at all (`'native' in event`); without it,
                // it assumes a raw DOM event was passed and resolves x/y
                // to null, silently matching nothing.
                const elements = processedChart.getElementsAtEventForMode(
                    { x, y, native: true }, 'index', { intersect: false }, true
                );
                processedChart.tooltip.setActiveElements(elements, { x, y });
                processedChart.update('none');
            });
        } catch (error) {
            console.error('Failed to update processed chart:', error);
        }
    }

    /* ---------- "today by hour" bar chart ---------- */
    async function updateHourly() {
        try {
            const response = await fetch(`${P}api/dashboard/hourly_stats`, {
                headers: { 'Content-Type': 'application/json' }
            });
            if (!response.ok) {
                console.error('hourly_stats HTTP', response.status);
                return;
            }
            const data = await response.json();
            // Office hours only -- 06:00-17:00 is where every process runs.
            const labels = (data.labels || []).slice(6, 18);
            const chartData = (data.data || []).slice(6, 18);

            const peak = chartData.length ? Math.max(...chartData) : 0;
            const peakHour = peak > 0 ? labels[chartData.indexOf(peak)] : '—';
            meta.hour = fmt(S.hourMeta, { peak: peak.toLocaleString(), hour: peakHour });
            if (view === 'hour') renderMeta();

            // display:none !important cannot be beaten by an inline style --
            // the utility class is the only handle on these two.
            const empty = document.getElementById('hourlyChartEmpty');
            if (empty) empty.classList.add('[display:none]!');

            const canvas = document.getElementById('hourlyChart');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');

            if (hourlyChart) {
                hourlyChart.data.labels = labels;
                hourlyChart.data.datasets[0].data = chartData;
                hourlyChart.update();
                return;
            }

            hourlyChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: S.documents,
                        data: chartData,
                        backgroundColor: `color-mix(in srgb, ${seriesColor(2)} 18%, transparent)`,
                        borderColor: seriesColor(2),
                        borderWidth: 2,
                        borderRadius: 6,
                        borderSkipped: false
                    }]
                },
                plugins: [noDataPlugin],
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { beginAtZero: true, grid: { borderDash: [5, 5], color: nxAxis().grid } },
                        // Cap the labels: a 90-day window otherwise renders 90
                        // rotated dates into an unreadable smear.
                        x: {
                            grid: { display: false },
                            ticks: { maxTicksLimit: 14, autoSkip: true, maxRotation: 0 }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: token('--nx-card', '#1e293b'),
                            titleColor: token('--nx-text-meta', '#64748b'),
                            bodyColor: token('--nx-text', '#e2e8f0'),
                            borderColor: token('--nx-border', '#334155'),
                            borderWidth: 1,
                            cornerRadius: 10,
                            padding: 10,
                            boxPadding: 6,
                            usePointStyle: true,
                            titleFont: { size: 11, weight: '600' },
                            titleMarginBottom: 6,
                            bodyFont: { size: 13, weight: '600' },
                            caretSize: 6
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Failed to update hourly chart:', error);
        }
    }

    /* ---------- per-process backlog trend ---------- */
    function renderBacklogLegend(series) {
        const box = document.getElementById('backlog-legend');
        if (!box) return;
        // Series names come from the database (process names) -- escape them.
        box.innerHTML = series.map((s, i) => {
            const dash = SERIES_DASH[i % SERIES_DASH.length] || [];
            const mod = dash.length === 0 ? ''
                : (dash.length === 2 && dash[0] <= 2 ? ' nx-legend__swatch--dotted'
                    : ' nx-legend__swatch--dashed');
            return `<span class="nx-legend__item">`
                + `<span class="nx-legend__swatch${mod}" style="color: ${window.NX.esc(seriesColor(i))}"></span>`
                + `${window.NX.esc(s.name)}`
                + `<span class="nx-legend__count">${window.NX.esc(Number(s.current || 0).toLocaleString())}</span>`
                + `</span>`;
        }).join('');
    }

    async function updateBacklog() {
        try {
            const response = await fetch(`${P}api/dashboard/backlog_trend?range=${range}`, {
                headers: { 'Content-Type': 'application/json' }
            });
            if (!response.ok) {
                console.error('backlog_trend HTTP', response.status);
                return;
            }
            const data = await response.json();
            const series = data.series || [];

            const totalEl = document.getElementById('backlog-total');
            if (totalEl) totalEl.textContent = Number(data.total || 0).toLocaleString();
            const deltaEl = document.getElementById('backlog-delta');
            if (deltaEl) {
                const diff = Number(data.total || 0) - Number(data.prev_total || 0);
                deltaEl.textContent = fmt(S.sinceYesterday, {
                    delta: `${diff >= 0 ? '+' : ''}${diff.toLocaleString()}`
                });
            }
            const eyebrowEl = document.getElementById('backlog-eyebrow');
            if (eyebrowEl) eyebrowEl.textContent = fmt(S.trendDays, { days: range });

            renderBacklogLegend(series);

            const canvas = document.getElementById('backlogTrendChart');
            if (!canvas) return;
            const datasets = series.map((s, i) => ({
                label: s.name,
                data: s.values || [],
                borderColor: seriesColor(i),
                borderDash: SERIES_DASH[i % SERIES_DASH.length],
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.3,
                fill: false
            }));
            // Raw ISO dates, matching the over-time chart directly above. Running
            // these through NX.formatDate gave the two charts on one page two
            // different date formats (2026-08-23 above, 23/08/2026 below).
            const labels = data.labels || [];

            if (backlogChart) {
                backlogChart.data.labels = labels;
                backlogChart.data.datasets = datasets;
                backlogChart.update();
                return;
            }

            backlogChart = new Chart(canvas.getContext('2d'), {
                type: 'line',
                data: { labels: labels, datasets: datasets },
                plugins: [noDataPlugin],
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { beginAtZero: true, grid: { borderDash: [5, 5], color: nxAxis().grid } },
                        // Cap the labels: a 90-day window otherwise renders 90
                        // rotated dates into an unreadable smear.
                        x: {
                            grid: { display: false },
                            ticks: { maxTicksLimit: 14, autoSkip: true, maxRotation: 0 }
                        }
                    },
                    plugins: {
                        // The page renders its own #backlog-legend so the
                        // swatches can match the dash patterns exactly.
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: token('--nx-card', '#1e293b'),
                            titleColor: token('--nx-text-meta', '#64748b'),
                            bodyColor: token('--nx-text', '#e2e8f0'),
                            borderColor: token('--nx-border', '#334155'),
                            borderWidth: 1,
                            cornerRadius: 10,
                            padding: 10,
                            boxPadding: 6,
                            usePointStyle: true,
                            titleFont: { size: 11, weight: '600' },
                            titleMarginBottom: 6,
                            bodyFont: { size: 13, weight: '600' },
                            caretSize: 6
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Failed to update backlog trend:', error);
        }
    }

    /* ---------- the two chart tabs: client-side only, no refetch ---------- */
    function setView(next) {
        view = next === 'hour' ? 'hour' : 'time';
        document.querySelectorAll('#dash-view-tabs .nx-tab').forEach((btn) => {
            const on = btn.dataset.view === view;
            btn.classList.toggle('is-active', on);
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        const title = document.getElementById('chart-title');
        if (title) title.textContent = view === 'hour' ? S.byHour : S.overTime;

        const timeBody = document.getElementById('chart-body-time');
        const hourBody = document.getElementById('chart-body-hour');
        if (timeBody) timeBody.classList.toggle('[display:none]!', view === 'hour');
        if (hourBody) hourBody.classList.toggle('[display:none]!', view !== 'hour');
        // Chart.js sizes to a zero-height parent while hidden; nudge it once
        // the body is visible again.
        if (view === 'hour' && hourlyChart) hourlyChart.resize();
        if (view === 'time' && processedChart) processedChart.resize();
        renderMeta();
    }

    /* ---------- 14 / 30 / 90 day range ---------- */
    async function setRange(next) {
        range = Number(next) || range;
        document.querySelectorAll('#dash-range .nx-segmented__btn[data-range]').forEach((btn) => {
            const on = Number(btn.dataset.range) === range;
            btn.classList.toggle('is-active', on);
            btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        try {
            // Persisted server-side so the KPI/hourly endpoints (which read the
            // session, not the query string) agree with the line chart.
            await fetch(`${P}api/dashboard/set_filter`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.NX.csrfToken() },
                body: JSON.stringify({ range: range })
            });
        } catch (error) {
            console.error('Failed to set range:', error);
        }
        updateKpis();
        updateOverTime();
        updateBacklog();
    }

    async function setProcessFilter(value) {
        try {
            await fetch(`${P}api/dashboard/set_filter`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.NX.csrfToken() },
                body: JSON.stringify({ process_name: value })
            });
            updateKpis();
            updateOverTime();
            updateHourly();
            updateBacklog();
        } catch (error) {
            console.error('Failed to set process filter:', error);
        }
    }
    // The page-level NexoraProcessPicker binding in templates/dashboard.html
    // calls this by name -- the one global this module exposes.
    window.setProcessFilter = setProcessFilter;

    /* ---------- live refresh: one interval for all four panels ---------- */
    function refreshAll() {
        updateKpis();
        updateOverTime();
        updateHourly();
        updateBacklog();
        const stamp = document.getElementById('dash-live-time');
        if (stamp) stamp.textContent = new Date().toLocaleTimeString();
        countdown = window.NX_DASH.refreshMs / 1000;
        const counter = document.getElementById('dash-countdown');
        if (counter) counter.textContent = countdown;
    }

    function tick() {
        countdown -= 1;
        if (countdown <= 0) {
            refreshAll();
            return;
        }
        const counter = document.getElementById('dash-countdown');
        if (counter) counter.textContent = countdown;
    }

    document.addEventListener('DOMContentLoaded', () => {
        // No inline onclick anywhere -- CSP is PROD-only, so an inline handler
        // would work on INT and be silently refused in production.
        const tabs = document.getElementById('dash-view-tabs');
        if (tabs) {
            tabs.addEventListener('click', (e) => {
                const btn = e.target.closest('.nx-tab[data-view]');
                if (btn) setView(btn.dataset.view);
            });
        }
        const rangeBox = document.getElementById('dash-range');
        if (rangeBox) {
            rangeBox.addEventListener('click', (e) => {
                const btn = e.target.closest('.nx-segmented__btn[data-range]');
                if (btn) setRange(btn.dataset.range);
            });
        }

        const refreshBtn = document.getElementById('dash-refresh');
        if (refreshBtn) refreshBtn.addEventListener('click', () => refreshAll());

        setView(view);
        // refreshAll() is the first paint too -- it runs all four updaters and
        // stamps the live indicator, so there is no separate initial fetch.
        refreshAll();
        setInterval(tick, 1000);
    });
})();
