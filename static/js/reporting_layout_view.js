// Renders a layout's tiles (KPI / chart / table) into an already-laid-out
// .rdb-grid. Shared by the definitions editor preview and both result views.
// Charts are drawn straight from (columns, rows) with Chart.js: column 0 is
// the x axis, every all-numeric column one dataset (the metric columns).
(function () {
  'use strict';
  var esc = (window.NX && window.NX.esc) || function (s) { return String(s); };
  var charts = new WeakMap();   // host -> [Chart]
  var SERIES = ['--nx-series-1', '--nx-series-2', '--nx-series-3', '--nx-series-4', '--nx-series-5'];

  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function seriesFor(columns, rows, def) {
    var labels = rows.map(function (r) { return r[0] == null ? '' : String(r[0]).slice(0, 10); });
    var datasets = [];
    for (var i = 1; i < columns.length; i++) {
      var cells = rows.map(function (r) { return r[i]; }).filter(function (v) { return v != null; });
      if (!cells.length || !cells.every(isNum)) continue;
      var col = columns[i];
      datasets.push({ label: col.header || col.field, data: rows.map(function (r) { return isNum(r[i]) ? r[i] : null; }) });
    }
    return { labels: labels, datasets: datasets };
  }
  function cssVar(name, dflt) {
    if (typeof getComputedStyle !== 'function') return dflt;
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || dflt;
  }
  function colour(i) { return cssVar(SERIES[i % SERIES.length], '#4f46e5'); }
  function fmt(v) {
    if (v == null || !isFinite(v)) return '—';
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(v);
  }
  function destroy(host) {
    (charts.get(host) || []).forEach(function (c) { try { c.destroy(); } catch (e) {} });
    charts.set(host, []);
  }
  function keep(host, chart) { var list = charts.get(host) || []; list.push(chart); charts.set(host, list); }

  function kpiHtml(tile, ctx) {
    var d = (ctx.derived || {})[tile.measure] || {};
    var ms = (ctx.layout.measures || []).find(function (m) { return m.id === tile.measure; }) || {};
    var label = (ctx.i18n && ctx.i18n.op && ctx.i18n.op[ms.op]) || ms.op || '';
    var value = d.unavailable ? '—' : (ms.op === 'minmax' ? fmt(d.min) + ' – ' + fmt(d.max) : fmt(d.value));
    var sub = d.unavailable ? (ctx.i18n ? ctx.i18n.unavailable : d.unavailable)
      : (ms.op === 'percentile' ? 'p' + Math.round((ms.q || 0.5) * 100) : (d.n != null ? 'n = ' + d.n : ''));
    return '<div class="rl-kpi" title="' + esc(d.unavailable || '') + '">' +
      '<span class="rl-kpi-label rdb-card-meta">' + esc(label) + '</span>' +
      '<span class="rl-kpi-value" data-testid="rl-kpi-value">' + esc(value) + '</span>' +
      '<span class="rl-kpi-sub">' + esc(sub) + '</span>' +
      (tile.sparkline ? '<canvas class="rl-kpi-spark"></canvas>' : '') + '</div>';
  }
  function singleDateDim(def) {
    var cols = (def && def.columns) || [];
    return cols.length === 1 && (!!cols[0].grain || /date/i.test(cols[0].field || ''));
  }
  function mountSpark(host, canvas, ctx) {
    if (!window.Chart || !singleDateDim(ctx.def)) { canvas.remove(); return; }
    var s = seriesFor(ctx.columns, ctx.rows, ctx.def);
    if (!s.datasets.length) { canvas.remove(); return; }
    keep(host, new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: s.labels, datasets: [{ data: s.datasets[0].data, borderColor: colour(0), borderWidth: 1.5, pointRadius: 0, tension: .3, spanGaps: true }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false,
                 plugins: { legend: { display: false }, tooltip: { enabled: false } },
                 scales: { x: { display: false }, y: { display: false } } }
    }));
  }
  function chartConfig(tile, s, ctx) {
    var t = tile.chart;
    var base = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: s.datasets.length > 1 } } };
    if (t === 'pie' || t === 'doughnut') {
      return { type: t, data: { labels: s.labels, datasets: [{ data: s.datasets[0].data, backgroundColor: s.labels.map(function (_, i) { return colour(i); }) }] }, options: base };
    }
    if (t === 'gauge') {
      var d = ctx.derived || {}, cur = null, lo = null, hi = null;
      Object.keys(d).forEach(function (k) {
        if (d[k].op === 'current' && isNum(d[k].value)) cur = d[k].value;
        if (d[k].op === 'minmax') { lo = d[k].min; hi = d[k].max; }
      });
      var data = s.datasets[0].data.filter(isNum);
      if (cur == null) cur = data.length ? data[data.length - 1] : 0;
      if (lo == null) lo = data.length ? Math.min.apply(null, data) : 0;
      if (hi == null) hi = data.length ? Math.max.apply(null, data) : 1;
      var span = Math.max(hi - lo, 1e-9);
      return { type: 'doughnut',
        data: { labels: [fmt(cur), ''], datasets: [{ data: [cur - lo, Math.max(hi - cur, 0)], backgroundColor: [colour(0), cssVar('--nx-border', '#e5e7eb')], borderWidth: 0 }] },
        options: Object.assign({}, base, { circumference: 180, rotation: 270, cutout: '70%', plugins: { legend: { display: false }, tooltip: { enabled: false } } }) };
    }
    var datasets = s.datasets.map(function (ds, i) {
      return { label: ds.label, data: ds.data, borderColor: colour(i), backgroundColor: colour(i) + (t === 'area' ? '33' : ''),
               fill: t === 'area', tension: .3, spanGaps: true };
    });
    var type = (t === 'line' || t === 'area') ? 'line' : 'bar';
    var scales = { y: { beginAtZero: true, ticks: { maxTicksLimit: 6 } } };
    if (t === 'stacked_bar') { scales.x = { stacked: true }; scales.y.stacked = true; }
    return { type: type, data: { labels: s.labels, datasets: datasets }, options: Object.assign({}, base, { scales: scales }) };
  }
  function tableHtml(ctx) {
    var cols = ctx.columns || [], rows = (ctx.rows || []).slice(0, 200);
    return '<div class="rl-table"><table><thead><tr>' +
      cols.map(function (c) { return '<th>' + esc(c.header || c.field) + '</th>'; }).join('') + '</tr></thead><tbody>' +
      rows.map(function (r) { return '<tr>' + r.map(function (v) { return '<td>' + esc(v == null ? '' : v) + '</td>'; }).join('') + '</tr>'; }).join('') +
      '</tbody></table></div>';
  }

  function render(host, ctx) {
    destroy(host);
    var hasData = ctx.columns && ctx.columns.length && ctx.rows && ctx.rows.length;
    var s = hasData ? seriesFor(ctx.columns, ctx.rows, ctx.def) : { labels: [], datasets: [] };
    (ctx.layout.tiles || []).forEach(function (tile) {
      var card = host.querySelector('[data-card-id="' + tile.id + '"]');
      var body = card && card.querySelector('[data-tile-body]');
      if (!body) return;
      if (!hasData && tile.type !== 'kpi') {
        body.innerHTML = '<div class="rl-placeholder">' + esc(tile.type === 'chart' ? (ctx.i18n.chart[tile.chart] || tile.chart) : ctx.i18n.table) + '</div>';
        return;
      }
      if (tile.type === 'kpi') {
        body.innerHTML = kpiHtml(tile, ctx);
        var spark = body.querySelector('.rl-kpi-spark');
        if (spark && hasData) mountSpark(host, spark, ctx);
        return;
      }
      if (tile.type === 'table') { body.innerHTML = tableHtml(ctx); return; }
      body.innerHTML = '<div class="rl-chart"><canvas></canvas></div>';
      if (!window.Chart || !s.datasets.length) { body.innerHTML = '<div class="rl-placeholder">' + esc(ctx.i18n.unavailable) + '</div>'; return; }
      keep(host, new Chart(body.querySelector('canvas').getContext('2d'), chartConfig(tile, s, ctx)));
    });
  }

  window.ReportingLayoutView = { render: render, seriesFor: seriesFor, destroy: destroy };
}());
