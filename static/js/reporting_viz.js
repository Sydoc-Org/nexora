// Reporting visualizations: Chart.js charts + a drag-and-drop pivot/matrix.
// Both operate on the result set currently in the grid ({columns, rows}); the
// main reporting script hands that in via window.ReportingViz when the user
// switches the result view. Fields are tracked by column INDEX (not name) so
// duplicate SQL column names never collide.
//
// Translated strings ride in via window.NX_I18N_REPORTING_VIZ, built by the
// paired templates/js/_reporting_viz_js.html shim (#191).
(function () {
  var I18N = window.NX_I18N_REPORTING_VIZ || {};

  // Shared palette for multi-category series (pie/doughnut segments etc.) --
  // the only hardcoded color set outside the locked ink-navy/indigo-peak
  // single-series spec below (see mountChart's rlNavy/rlPeak). 12 entries so
  // Simple's up-to-12-series multi-breakdown charts (its own `series.length
  // > 12` cap, mirroring render_chart_png's MAX_SERIES) never repeat a color
  // within a single chart; entries 8-12 extend the original 7's indigo/
  // violet/sky/emerald/amber/red/slate family with additional lightness/hue
  // variants rather than introducing a new one.
  var NX_PALETTE = [
    '#4f46e5', '#7c3aed', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#64748b',
    '#a78bfa', '#0891b2', '#f97316', '#be123c', '#94a3b8'
  ];
  // Chart grid-line color, derived from the theme's border token at draw
  // time so it tracks light/dark mode without a second hardcoded value.
  function gridColor() {
    var v = getComputedStyle(document.documentElement).getPropertyValue('--nx-border').trim();
    return v || 'rgba(100,116,139,.18)';
  }
  var MAX_CHART_CATEGORIES = 50;

  // Export models for the result views, kept so the toolbar's Export button can
  // serialize exactly what the user is looking at (chart image / pivot matrix).
  var lastChartCanvas = null;
  var lastPivotExport = null;
  var lastChartColumns = null;
  // Drill-through support: the column index currently mapped to the chart's
  // X axis, and the (post-aggregation, post-truncation) label list actually
  // rendered — the caller has no other way to learn which raw value a given
  // Chart.js element index corresponds to. Kept module-tab-agnostic: this
  // module never looks at a report "definition", it just exposes what it
  // drew so a caller (Simple or Advanced) can map it back to one.
  var lastChartXIndex = null;
  var lastChartLabels = null;

  function toNum(v) {
    if (v === null || v === undefined || v === '') return null;
    if (typeof v === 'number') return isFinite(v) ? v : null;
    if (typeof v === 'boolean') return null;
    var s = String(v).trim();
    if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(s)) return null;
    var n = Number(s);
    return isFinite(n) ? n : null;
  }

  // A column is numeric if its first handful of non-empty values all parse.
  function isNumericIndex(rows, idx) {
    var seen = 0;
    for (var i = 0; i < rows.length && seen < 25; i++) {
      var v = rows[i][idx];
      if (v === null || v === undefined || v === '') continue;
      seen++;
      if (toNum(v) === null) return false;
    }
    return seen > 0;
  }

  function aggregate(values, agg) {
    if (agg === 'count') return values.length;
    var nums = [];
    for (var i = 0; i < values.length; i++) {
      var n = toNum(values[i]);
      if (n !== null) nums.push(n);
    }
    if (!nums.length) return null;
    if (agg === 'avg') return nums.reduce(function (a, b) { return a + b; }, 0) / nums.length;
    if (agg === 'min') return Math.min.apply(null, nums);
    if (agg === 'max') return Math.max.apply(null, nums);
    return nums.reduce(function (a, b) { return a + b; }, 0); // sum
  }

  function fmt(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
    return String(v);
  }

  function colLabel(columns, idx) {
    var c = columns[idx];
    return (c && (c.header || c.field)) || ('col' + idx);
  }

  // Sort comparator over two key-tuples (numeric-aware, element by element).
  function cmpTuple(a, b) {
    var n = Math.min(a.length, b.length);
    for (var i = 0; i < n; i++) {
      if (a[i] === b[i]) continue;
      var na = toNum(a[i]), nb = toNum(b[i]);
      if (na !== null && nb !== null) { if (na !== nb) return na - nb; continue; }
      return a[i] < b[i] ? -1 : 1;
    }
    return a.length - b.length;
  }

  // ---- Chart ----------------------------------------------------------------
  var chartInstance = null;

  function destroyChart() {
    if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  }

  // opts: {onElementClick?: function(index, datasetIndex)} — a caller-supplied
  // hook fired from Chart.js onClick. Kept as a plain option rather than a
  // reference to Advanced-pane state, so this module stays usable from either
  // tab (mirrors how mountChart never reaches into report-definition state).
  function mountChart(container, columns, rows, opts) {
    destroyChart();
    lastChartCanvas = null;
    lastChartXIndex = null;
    lastChartLabels = null;
    opts = opts || {};
    container.innerHTML = '';
    if (typeof Chart === 'undefined') {
      container.textContent = I18N.chartUnavailable;
      return;
    }
    if (!columns.length || !rows.length) {
      container.textContent = I18N.noDataToChart;
      return;
    }
    lastChartColumns = columns;
    var measureIdx = -1;
    for (var i = 0; i < columns.length; i++) {
      if (isNumericIndex(rows, i)) { measureIdx = i; break; }
    }
    if (measureIdx === -1) measureIdx = columns.length > 1 ? 1 : 0;

    function sel(opts, val) {
      var s = document.createElement('select');
      opts.forEach(function (o) {
        var op = document.createElement('option');
        op.value = o.value; op.textContent = o.label;
        s.appendChild(op);
      });
      s.value = val;
      return s;
    }
    function lbl(t) {
      var s = document.createElement('span');
      s.className = 'reporting-viz-lbl'; s.textContent = t;
      return s;
    }
    var colOpts = columns.map(function (c, idx) {
      return { value: String(idx), label: colLabel(columns, idx) };
    });
    var typeSel = sel([
      { value: 'bar', label: I18N.typeBar },
      { value: 'line', label: I18N.typeLine },
      { value: 'pie', label: I18N.typePie },
      { value: 'doughnut', label: I18N.typeDoughnut }
    ], 'bar');
    var xSel = sel(colOpts, '0');
    var ySel = sel(colOpts, String(measureIdx));
    typeSel.id = 'rpChartType';
    xSel.id = 'rpChartX';
    ySel.id = 'rpChartY';

    var bar = document.createElement('div');
    bar.className = 'reporting-viz-bar';
    bar.appendChild(lbl(I18N.labelType)); bar.appendChild(typeSel);
    bar.appendChild(lbl(I18N.labelCategory)); bar.appendChild(xSel);
    bar.appendChild(lbl(I18N.labelValue)); bar.appendChild(ySel);
    container.appendChild(bar);

    var canvasWrap = document.createElement('div');
    canvasWrap.className = 'reporting-chart-canvas';
    var canvas = document.createElement('canvas');
    canvasWrap.appendChild(canvas);
    container.appendChild(canvasWrap);
    lastChartCanvas = canvas;
    var note = document.createElement('p');
    note.className = 'reporting-viz-note';
    container.appendChild(note);

    function draw() {
      var xi = parseInt(xSel.value, 10);
      var yi = parseInt(ySel.value, 10);
      var type = typeSel.value;
      // Aggregate (sum) the value column by category label.
      var map = {}, order = [];
      rows.forEach(function (r) {
        var k = r[xi] == null ? '' : String(r[xi]);
        var n = toNum(r[yi]);
        if (!(k in map)) { map[k] = 0; order.push(k); }
        map[k] += (n === null ? 0 : n);
      });
      var pairs = order.map(function (k) { return { k: k, v: map[k] }; });
      var truncated = false;
      if (pairs.length > MAX_CHART_CATEGORIES) {
        pairs.sort(function (a, b) { return b.v - a.v; });
        pairs = pairs.slice(0, MAX_CHART_CATEGORIES);
        truncated = true;
      }
      var labels = pairs.map(function (p) { return p.k; });
      var data = pairs.map(function (p) { return p.v; });
      // Raw click values for drill-through: labels are already the raw
      // per-category stringified values (no date-trimming here, unlike
      // Simple), so labels[index] === the value a click at that index maps to.
      lastChartXIndex = xi;
      lastChartLabels = labels;
      // Moved above the forecast block below (was declared further down,
      // after the dataset build) since the overlay needs it for the band
      // fill colors and must not duplicate the declaration.
      var isDark = document.documentElement.classList.contains('dark');
      // Forecast overlay (Task 7, Advanced mirror of _reporting_simple_js.html's
      // mountChart forecast handling): only when the chart's X axis is column 0
      // (the date dim forecastEligibleDef() requires), the result isn't
      // truncated to the top-N categories, the chart type supports a trailing
      // line, and the selected Y column matches a forecast series field.
      var fcRaw = opts.forecast;
      var fcSeries = null;
      if (fcRaw && !fcRaw.unavailable && (fcRaw.buckets || []).length &&
          xi === 0 && !truncated && (type === 'bar' || type === 'line')) {
        for (var fsi = 0; fsi < (fcRaw.series || []).length; fsi++) {
          var cYi = columns[yi];
          if (cYi && fcRaw.series[fsi].field === cYi.field) { fcSeries = fcRaw.series[fsi]; break; }
        }
      }
      var histN = labels.length;
      if (fcSeries) {
        labels = labels.concat(fcRaw.buckets.map(function (b) { return String(b).slice(0, 10); }));
        lastChartLabels = labels;
      }
      var single = (type === 'bar' || type === 'line');
      var colors = labels.map(function (_, i) { return NX_PALETTE[i % NX_PALETTE.length]; });
      var maxIdx = 0;
      for (var mi = 1; mi < data.length; mi++) { if (data[mi] > data[maxIdx]) maxIdx = mi; }
      // Ink-navy (#312e81) sits at ~1.3:1 contrast against the dark --nx-card
      // canvas (#1e293b) — effectively invisible. Lift to the #818cf8 family
      // (the existing --nx-accent dark token) only for dark mode; light mode
      // keeps the locked ink-navy/indigo-peak spec unchanged.
      var rlNavy = isDark ? '#818cf8' : '#312e81';
      var rlPeak = isDark ? '#c7d2fe' : '#4f46e5';
      var rlLineFill = isDark ? 'rgba(129,140,248,.18)' : 'rgba(49,46,129,.12)';
      // Pie/doughnut segment borders: a hardcoded '#fff' reads as a bright
      // ring against the dark --nx-card canvas (#1e293b) that this chart
      // sits on. Recede into the card background in dark mode instead of
      // forcing white.
      var rlSliceBorder = isDark ? '#1e293b' : '#fff';
      var ds = {
        label: colLabel(columns, yi),
        data: data,
        backgroundColor: single
          ? (type === 'line' ? rlLineFill : data.map(function (v, i) { return i === maxIdx ? rlPeak : rlNavy; }))
          : colors,
        borderColor: single ? rlNavy : rlSliceBorder,
        borderWidth: type === 'line' ? 2 : 1,
        fill: type === 'line'
      };
      var chartDatasets = [ds];
      if (fcSeries) {
        ds.data = data.concat(fcRaw.buckets.map(function () { return null; }));
        var fcAccent2 = isDark ? '#818cf8' : '#4f46e5';
        var lead2 = [];
        for (var l2 = 0; l2 < histN - 1; l2++) lead2.push(null);
        var bridge2 = data[histN - 1];
        chartDatasets.push({
          label: colLabel(columns, yi) + ' · ' + I18N.forecast,
          data: lead2.concat([bridge2], fcSeries.values),
          type: 'line', borderColor: fcAccent2, borderDash: [6, 4], borderWidth: 2,
          backgroundColor: 'transparent', pointStyle: 'rectRot', fill: false, _forecast: true
        });
        chartDatasets.push({ label: '', data: lead2.concat([bridge2], fcSeries.upper),
          type: 'line', borderWidth: 0, pointRadius: 0, backgroundColor: 'transparent',
          fill: false, _band: true });
        chartDatasets.push({ label: '', data: lead2.concat([bridge2], fcSeries.lower),
          type: 'line', borderWidth: 0, pointRadius: 0,
          backgroundColor: isDark ? 'rgba(129,140,248,.18)' : 'rgba(79,70,229,.12)',
          fill: '-1', _band: true });
      }
      if (type === 'bar') {
        ds.borderRadius = 6;
        ds.maxBarThickness = 48;
      }
      // Only hide non-integer axis ticks when every plotted value actually is
      // an integer (e.g. a COUNT/GROUP BY report) -- a fractional measure
      // (avg/sum of decimals) keeps Chart.js's normal tick spacing.
      var allInts = data.every(function (v) { return Number.isInteger(v); });
      destroyChart();
      chartInstance = new Chart(canvas.getContext('2d'), {
        type: type,
        data: { labels: labels, datasets: chartDatasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          // White background so an exported PNG isn't transparent.
          plugins: {
            legend: { display: !single || !!fcSeries,
                      labels: { filter: function (item, data) {
                        // Same both-flags exclusion as _reporting_simple_js.html's
                        // D6 legend filter: band + forecast-line datasets never
                        // get their own legend entry (or drill — see the
                        // _forecast/_band guard in onClick below).
                        var ds = data.datasets[item.datasetIndex] || {};
                        return !(ds._band || ds._forecast);
                      } } },
            tooltip: {
              callbacks: {
                // Reuse the module's existing number formatter (fmt) instead
                // of Chart.js's raw float, so aggregated sums/averages don't
                // show floating-point noise in the tooltip.
                label: function (ctx) {
                  var raw = ctx.parsed;
                  var v = (raw && typeof raw === 'object') ? raw.y : raw;
                  var name = single ? (ctx.dataset.label || '') : (ctx.label || '');
                  return (name ? name + ': ' : '') + fmt(v);
                }
              }
            }
          },
          scales: single ? {
            y: {
              beginAtZero: true,
              ticks: {
                maxTicksLimit: 6,
                callback: function (value) {
                  return (allInts && !Number.isInteger(value)) ? undefined : value;
                }
              },
              grid: { color: gridColor() }
            }
          } : {},
          onClick: opts.onElementClick ? function (evt) {
            var els = this.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
            if (!els.length) return;
            var hit = (this.data.datasets || [])[els[0].datasetIndex] || {};
            if (hit._forecast || hit._band) return;
            if (fcSeries && els[0].index >= histN) return;
            opts.onElementClick(els[0].index, els[0].datasetIndex);
          } : undefined,
          onHover: opts.onElementClick ? function (evt, elsH) {
            evt.native.target.style.cursor = elsH.length ? 'pointer' : 'default';
          } : undefined
        }
      });
      note.textContent = truncated ? I18N.top50Note : '';
    }
    typeSel.onchange = draw;
    xSel.onchange = draw;
    ySel.onchange = draw;
    draw();
  }

  // Return the current chart as a white-background PNG data-URL, or null.
  function chartPngDataUrl() {
    if (!lastChartCanvas) return null;
    var src = lastChartCanvas;
    var out = document.createElement('canvas');
    out.width = src.width; out.height = src.height;
    var ctx = out.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(src, 0, 0);
    return out.toDataURL('image/png');
  }

  // Download the current chart canvas as a PNG (flattened onto white).
  function exportChartPng(filename) {
    var url = chartPngDataUrl();
    if (!url) return false;
    var a = document.createElement('a');
    a.href = url;
    a.download = filename || 'chart.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    return true;
  }

  // Preselect chart type + axes from an AI chartHint, then redraw. No-op if the
  // chart isn't mounted or the hinted values aren't available.
  function applyChartHint(hint) {
    if (!hint) return;
    var t = document.getElementById('rpChartType');
    if (t && hint.type) {
      var ok = Array.prototype.some.call(t.options, function (o) { return o.value === hint.type; });
      if (ok) t.value = hint.type;
    }
    function setAxis(id, field) {
      if (!field || !lastChartColumns) return;
      var idx = -1;
      for (var i = 0; i < lastChartColumns.length; i++) {
        if (lastChartColumns[i].field === field) { idx = i; break; }
      }
      var el = document.getElementById(id);
      if (el && idx >= 0) el.value = String(idx);
    }
    setAxis('rpChartX', hint.x);
    setAxis('rpChartY', hint.y);
    if (t && t.onchange) t.onchange();  // draw() reads type/x/y from the selects
  }

  // ---- Pivot (drag-and-drop, multi-dimension) -------------------------------
  function mountPivot(container, columns, rows) {
    container.innerHTML = '';
    lastPivotExport = null;
    if (!columns.length || !rows.length) {
      container.textContent = I18N.noDataToPivot;
      return;
    }
    // assign[zone] = ordered list of {idx, agg?}; idx is the column index.
    var assign = { src: [], rows: [], cols: [], vals: [] };
    columns.forEach(function (_, idx) { assign.src.push({ idx: idx }); });

    var zones = {};
    var dragging = null;

    function findField(idx) {
      var names = ['src', 'rows', 'cols', 'vals'];
      for (var z = 0; z < names.length; z++) {
        var arr = assign[names[z]];
        for (var i = 0; i < arr.length; i++) {
          if (arr[i].idx === idx) return { zone: names[z], i: i, d: arr[i] };
        }
      }
      return null;
    }

    function moveField(idx, toZone) {
      var loc = findField(idx);
      if (!loc || loc.zone === toZone) return;
      assign[loc.zone].splice(loc.i, 1);
      var d = loc.d;
      if (toZone === 'vals') {
        if (d.agg === undefined) d.agg = isNumericIndex(rows, d.idx) ? 'sum' : 'count';
      } else {
        delete d.agg;
      }
      assign[toZone].push(d);
      renderShelf();
      renderMatrix();
    }

    function chip(d, zoneName) {
      var c = document.createElement('div');
      c.className = 'reporting-pivot-chip';
      c.draggable = true;
      var label = document.createElement('span');
      label.textContent = colLabel(columns, d.idx);
      c.appendChild(label);
      if (zoneName === 'vals') {
        var ag = document.createElement('select');
        ['sum', 'avg', 'count', 'min', 'max'].forEach(function (a) {
          var o = document.createElement('option');
          o.value = a; o.textContent = a;
          ag.appendChild(o);
        });
        ag.value = d.agg || 'sum';
        ag.onchange = function () { d.agg = ag.value; renderMatrix(); };
        ag.onmousedown = function (e) { e.stopPropagation(); };
        c.appendChild(ag);
      }
      if (zoneName !== 'src') {
        var rm = document.createElement('button');
        rm.type = 'button';
        rm.className = 'reporting-pivot-rm';
        rm.textContent = '×';
        rm.onclick = function () { moveField(d.idx, 'src'); };
        c.appendChild(rm);
      }
      c.addEventListener('dragstart', function (e) {
        dragging = d.idx;
        e.dataTransfer.setData('text/plain', String(d.idx));
        e.dataTransfer.effectAllowed = 'move';
      });
      c.addEventListener('dragend', function () { dragging = null; });
      return c;
    }

    function makeZone(name, title) {
      var z = document.createElement('div');
      z.className = 'reporting-pivot-zone';
      z.dataset.zone = name;
      var h = document.createElement('h5');
      h.textContent = title;
      z.appendChild(h);
      var list = document.createElement('div');
      list.className = 'reporting-pivot-list';
      z.appendChild(list);
      z.addEventListener('dragover', function (e) { e.preventDefault(); z.classList.add('drop-hover'); });
      z.addEventListener('dragleave', function () { z.classList.remove('drop-hover'); });
      z.addEventListener('drop', function (e) {
        e.preventDefault();
        z.classList.remove('drop-hover');
        var raw = e.dataTransfer.getData('text/plain');
        var idx = raw === '' ? dragging : parseInt(raw, 10);
        if (idx !== null && idx !== undefined && !isNaN(idx)) moveField(idx, name);
      });
      zones[name] = { el: z, list: list };
      return z;
    }

    function renderShelf() {
      ['src', 'rows', 'cols', 'vals'].forEach(function (z) {
        zones[z].list.innerHTML = '';
        assign[z].forEach(function (d) { zones[z].list.appendChild(chip(d, z)); });
      });
    }

    function tup(r, dims) {
      return dims.map(function (d) { return r[d.idx] == null ? '' : String(r[d.idx]); });
    }

    function measLabel(v) {
      return colLabel(columns, v.idx) + ' (' + (v.agg || 'sum') + ')';
    }

    function renderMatrix() {
      out.innerHTML = '';
      lastPivotExport = null;
      if (!assign.vals.length) {
        var p = document.createElement('p');
        p.className = 'reporting-empty';
        p.textContent = I18N.dragFieldToValues;
        out.appendChild(p);
        return;
      }
      var rowDims = assign.rows, colDims = assign.cols, vals = assign.vals;
      var rowKeys = [], rowSeen = {}, rowArr = {};
      var colKeys = [], colSeen = {}, colArr = {};
      var bucket = {};
      rows.forEach(function (r) {
        var rk = JSON.stringify(tup(r, rowDims));
        var ck = JSON.stringify(tup(r, colDims));
        if (!(rk in rowSeen)) { rowSeen[rk] = 1; rowKeys.push(rk); rowArr[rk] = tup(r, rowDims); }
        if (!(ck in colSeen)) { colSeen[ck] = 1; colKeys.push(ck); colArr[ck] = tup(r, colDims); }
        if (!bucket[rk]) bucket[rk] = {};
        if (!bucket[rk][ck]) bucket[rk][ck] = vals.map(function () { return []; });
        vals.forEach(function (v, vi) { bucket[rk][ck][vi].push(r[v.idx]); });
      });
      // Sort so siblings are contiguous (needed for nested-header grouping) and
      // the matrix reads in a stable order.
      rowKeys.sort(function (x, y) { return cmpTuple(rowArr[x], rowArr[y]); });
      colKeys.sort(function (x, y) { return cmpTuple(colArr[x], colArr[y]); });

      // Flat export model accumulated alongside the DOM (single-line headers).
      var exportCols = [];
      if (rowDims.length) {
        rowDims.forEach(function (d) { exportCols.push({ header: colLabel(columns, d.idx) }); });
      } else {
        exportCols.push({ header: '' });
      }
      colKeys.forEach(function (ck) {
        vals.forEach(function (v) {
          var prefix = colDims.length ? (colArr[ck].join(' / ') + ' · ') : '';
          exportCols.push({ header: prefix + measLabel(v) });
        });
      });
      vals.forEach(function (v) {
        exportCols.push({ header: I18N.total + ' · ' + measLabel(v) });
      });
      var exportRows = [];

      var table = document.createElement('table');
      table.className = 'reporting-table reporting-pivot-table';

      // --- Nested header: one row per column dimension + a measure row. ---
      var thead = document.createElement('thead');
      var nHeaderRows = colDims.length + 1;
      var headRows = [];
      for (var hr = 0; hr < nHeaderRows; hr++) {
        var tr = document.createElement('tr');
        headRows.push(tr);
        thead.appendChild(tr);
      }
      var leftCols = rowDims.length || 1;
      // Top-left: row-dimension names, spanning the full header height.
      if (rowDims.length) {
        rowDims.forEach(function (d) {
          var th = document.createElement('th');
          th.textContent = colLabel(columns, d.idx);
          th.rowSpan = nHeaderRows;
          th.className = 'reporting-pivot-corner';
          headRows[0].appendChild(th);
        });
      } else {
        var th0 = document.createElement('th');
        th0.rowSpan = nHeaderRows;
        th0.className = 'reporting-pivot-corner';
        headRows[0].appendChild(th0);
      }
      // Column-dimension levels: group contiguous colKeys sharing a prefix.
      for (var d = 0; d < colDims.length; d++) {
        var rowEl = headRows[d];
        var i = 0;
        while (i < colKeys.length) {
          var prefix = JSON.stringify(colArr[colKeys[i]].slice(0, d + 1));
          var j = i;
          while (j < colKeys.length &&
                 JSON.stringify(colArr[colKeys[j]].slice(0, d + 1)) === prefix) j++;
          var th = document.createElement('th');
          th.textContent = colArr[colKeys[i]][d];
          th.colSpan = (j - i) * vals.length;
          rowEl.appendChild(th);
          i = j;
        }
      }
      // Measure row (bottom of the header): one cell per colKey × measure.
      var measRow = headRows[nHeaderRows - 1];
      colKeys.forEach(function (ck) {
        vals.forEach(function (v) {
          var th = document.createElement('th');
          th.textContent = measLabel(v);
          measRow.appendChild(th);
        });
      });
      // Grand-total columns: span the full header height, far right.
      vals.forEach(function (v) {
        var th = document.createElement('th');
        th.className = 'reporting-pivot-total';
        th.rowSpan = nHeaderRows;
        th.textContent = I18N.total + ' · ' + colLabel(columns, v.idx);
        headRows[0].appendChild(th);
      });
      table.appendChild(thead);

      var tbody = document.createElement('tbody');
      rowKeys.forEach(function (rk) {
        var tr = document.createElement('tr');
        var exRow = [];
        if (rowDims.length) {
          rowArr[rk].forEach(function (val) {
            var td = document.createElement('td');
            td.className = 'reporting-pivot-rowhdr';
            td.textContent = val;
            tr.appendChild(td);
            exRow.push(val);
          });
        } else {
          var tdAll = document.createElement('td');
          tdAll.className = 'reporting-pivot-rowhdr';
          tdAll.textContent = I18N.all;
          tr.appendChild(tdAll);
          exRow.push(I18N.all);
        }
        colKeys.forEach(function (ck) {
          vals.forEach(function (v, vi) {
            var td = document.createElement('td');
            var arr = (bucket[rk] && bucket[rk][ck]) ? bucket[rk][ck][vi] : [];
            var cell = fmt(aggregate(arr, v.agg || 'sum'));
            td.textContent = cell;
            tr.appendChild(td);
            exRow.push(cell);
          });
        });
        vals.forEach(function (v, vi) {
          var all = [];
          colKeys.forEach(function (ck) {
            if (bucket[rk] && bucket[rk][ck]) all = all.concat(bucket[rk][ck][vi]);
          });
          var td = document.createElement('td');
          td.className = 'reporting-pivot-total';
          var cell = fmt(aggregate(all, v.agg || 'sum'));
          td.textContent = cell;
          tr.appendChild(td);
          exRow.push(cell);
        });
        tbody.appendChild(tr);
        exportRows.push(exRow);
      });

      var trT = document.createElement('tr');
      trT.className = 'reporting-pivot-totalrow';
      var exTot = [];
      for (var s = 0; s < leftCols; s++) {
        var tdh = document.createElement('td');
        tdh.className = 'reporting-pivot-rowhdr';
        tdh.textContent = s === 0 ? I18N.total : '';
        trT.appendChild(tdh);
        exTot.push(s === 0 ? I18N.total : '');
      }
      colKeys.forEach(function (ck) {
        vals.forEach(function (v, vi) {
          var all = [];
          rowKeys.forEach(function (rk) {
            if (bucket[rk] && bucket[rk][ck]) all = all.concat(bucket[rk][ck][vi]);
          });
          var td = document.createElement('td');
          td.className = 'reporting-pivot-total';
          var cell = fmt(aggregate(all, v.agg || 'sum'));
          td.textContent = cell;
          trT.appendChild(td);
          exTot.push(cell);
        });
      });
      vals.forEach(function (v, vi) {
        var all = [];
        rowKeys.forEach(function (rk) {
          colKeys.forEach(function (ck) {
            if (bucket[rk] && bucket[rk][ck]) all = all.concat(bucket[rk][ck][vi]);
          });
        });
        var td = document.createElement('td');
        td.className = 'reporting-pivot-total';
        var cell = fmt(aggregate(all, v.agg || 'sum'));
        td.textContent = cell;
        trT.appendChild(td);
        exTot.push(cell);
      });
      tbody.appendChild(trT);
      exportRows.push(exTot);
      table.appendChild(tbody);
      out.appendChild(table);

      lastPivotExport = { columns: exportCols, rows: exportRows };
    }

    var wrap = document.createElement('div');
    wrap.className = 'reporting-pivot';
    var shelf = document.createElement('div');
    shelf.className = 'reporting-pivot-shelf';
    shelf.appendChild(makeZone('src', I18N.fields));
    shelf.appendChild(makeZone('rows', I18N.rowsLabel));
    shelf.appendChild(makeZone('cols', I18N.columnsLabel));
    shelf.appendChild(makeZone('vals', I18N.valuesLabel));
    wrap.appendChild(shelf);
    var out = document.createElement('div');
    out.className = 'reporting-pivot-out reporting-table-wrap';
    wrap.appendChild(out);
    container.appendChild(wrap);

    renderShelf();
    // Seed a sensible default: first categorical -> Rows, first numeric -> Values.
    var firstNum = -1, firstCat = -1;
    for (var i = 0; i < columns.length; i++) {
      var num = isNumericIndex(rows, i);
      if (firstNum === -1 && num) firstNum = i;
      if (firstCat === -1 && !num) firstCat = i;
    }
    if (firstCat !== -1) moveField(firstCat, 'rows');
    if (firstNum !== -1) moveField(firstNum, 'vals');
    renderMatrix();
  }

  function getPivotExport() { return lastPivotExport; }

  // Drill-through helpers: which result column is currently the chart's X
  // axis, and the raw value a given (post-truncation) label index stands
  // for. A caller combines these with its own report-definition state to
  // decide whether/how to drill — this module has no opinion on that.
  function getChartXField() {
    if (!lastChartColumns || lastChartXIndex == null) return null;
    var c = lastChartColumns[lastChartXIndex];
    return c ? c.field : null;
  }
  function getChartLabelAt(index) {
    return (lastChartLabels && index >= 0 && index < lastChartLabels.length)
      ? lastChartLabels[index] : undefined;
  }

  window.ReportingViz = {
    mountChart: mountChart,
    mountPivot: mountPivot,
    destroyChart: destroyChart,
    exportChartPng: exportChartPng,
    chartPngDataUrl: chartPngDataUrl,
    getPivotExport: getPivotExport,
    applyChartHint: applyChartHint,
    getChartXField: getChartXField,
    getChartLabelAt: getChartLabelAt
  };
}());
