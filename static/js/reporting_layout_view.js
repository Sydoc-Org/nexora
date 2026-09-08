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
  // SUM/AVG over a decimal column arrives as a numeric string ("938.4499"):
  // Flask serialises Decimal that way. Coerce, but never treat '' as 0.
  function num(v) {
    if (isNum(v)) return v;
    if (typeof v === 'string' && v.trim() !== '' && isFinite(Number(v))) return Number(v);
    return null;
  }
  function numericCols(columns, rows) {
    var out = [];
    for (var i = 1; i < columns.length; i++) {
      var cells = rows.map(function (r) { return r[i]; }).filter(function (v) { return v != null; });
      if (cells.length && cells.every(function (v) { return num(v) != null; })) out.push(i);
    }
    return out;
  }
  function seriesFor(columns, rows, def) {
    var nums = numericCols(columns, rows);
    var lbl = function (v) { return v == null ? '' : String(v).slice(0, 10); };
    // Two dimensions + one metric (e.g. month / customer / hours): pivot the
    // second dimension into one series per value, like the standard chart.
    if (nums.length === 1 && columns.length >= 3 && nums[0] !== 1) {
      var idx = nums[0], labels = [], seen = {}, groups = {}, order = [];
      rows.forEach(function (r) {
        var x = lbl(r[0]); if (!seen[x]) { seen[x] = true; labels.push(x); }
        var g = r[1] == null ? '' : String(r[1]);
        if (!groups[g]) { groups[g] = {}; order.push(g); }
        groups[g][x] = (groups[g][x] || 0) + (num(r[idx]) || 0);
      });
      return { labels: labels, datasets: order.map(function (g) {
        return { label: g, data: labels.map(function (x) { return x in groups[g] ? groups[g][x] : null; }) };
      }) };
    }
    var labels = rows.map(function (r) { return lbl(r[0]); });
    return { labels: labels, datasets: nums.map(function (i) {
      var col = columns[i];
      return { label: col.header || col.field, data: rows.map(function (r) { return num(r[i]); }) };
    }) };
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
  var PANEL_IDS = { caption: 'rsCaptionCard', ask: 'rsAskEddard', anomalies: 'rsAnomCard', sql: 'rsSqlView' };
  var adopted = [];   // [{node, parent, next}] side-column nodes moved into tiles
  function adopt(node, body) {
    if (!node.__rlHome) node.__rlHome = { parent: node.parentNode, next: node.nextSibling };
    body.appendChild(node);
    adopted.push(node);
  }
  function restorePanels() {
    adopted.splice(0).forEach(function (n) {
      var h = n.__rlHome; if (!h || !h.parent) return;
      if (h.next && h.next.parentNode === h.parent) h.parent.insertBefore(n, h.next); else h.parent.appendChild(n);
    });
  }
  function destroy(host) {
    (charts.get(host) || []).forEach(function (c) { try { c.destroy(); } catch (e) {} });
    charts.set(host, []);
    restorePanels();
  }
  function keep(host, chart) { var list = charts.get(host) || []; list.push(chart); charts.set(host, list); }

  function kpiHtml(tile, ctx) {
    var d = (ctx.derived || {})[tile.measure] || {};
    var ms = (ctx.layout.measures || []).find(function (m) { return m.id === tile.measure; }) || {};
    var label = (ctx.i18n && ctx.i18n.op && ctx.i18n.op[ms.op]) || ms.op || '';
    var value = d.unavailable ? '—'
      : ms.op === 'minmax' ? fmt(d.min) + ' – ' + fmt(d.max)
      : ms.op === 'delta' ? (d.value > 0 ? '+' : '') + fmt(d.value)
      : fmt(d.value);
    var sub = d.unavailable ? (ctx.i18n ? ctx.i18n.unavailable : d.unavailable)
      : ms.op === 'percentile' ? 'p' + Math.round((ms.q || 0.5) * 100)
      : ms.op === 'delta' ? (isNum(d.pct) ? (d.pct > 0 ? '+' : '') + Math.round(d.pct * 100) + ' %' : '')
      : (d.n != null ? 'n = ' + d.n : '');
    var tone = ms.op === 'delta' && !d.unavailable && d.value ? (d.value > 0 ? ' rl-kpi--up' : ' rl-kpi--down') : '';
    return '<div class="rl-kpi' + tone + '" title="' + esc(d.unavailable || '') + '">' +
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
      if (tile.type === 'panel') {
        var live = ctx.live && document.getElementById(PANEL_IDS[tile.panel]);
        if (live) { adopt(live, body); if (tile.panel === 'sql') live.hidden = !live.querySelector('pre').textContent; }
        else body.innerHTML = '<div class="rl-placeholder">' + esc((ctx.i18n.panel || {})[tile.panel] || tile.panel) + '</div>';
        return;
      }
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

  window.ReportingLayoutView = { render: render, seriesFor: seriesFor, destroy: destroy, num: num };
}());
