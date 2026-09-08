// Reporting Simple pane -- chart trio (Beautification Phase 2b, Task 7).
// Split out of reporting_simple.js: zero-fill date-bucket helpers, the
// Chart.js config builder + renderChart, and buildChartData/mountChart.
// Shares state via window.RS (see reporting_simple.js's own top-of-file
// comment for the RS.state/RS.el/RS.esc/RS.api/RS.I18N contract). This file
// is loaded BEFORE reporting_simple.js (see _reporting_simple_js.html) --
// every RS.* reference below into things reporting_simple.js defines
// (RS.metricLabelsFor, RS.metricTotalModes, RS.forecastEligible,
// RS.toggleStylePop, RS.drillFromChart, RS.seriesKey, RS.rightAxisKeys) is
// only ever called from inside a function body, never at top-level load
// time, so the load order is safe: by the time any of these functions is
// actually invoked (a user action), reporting_simple.js has already run.
(function () {
  window.RS = window.RS || {};
  // Defensive fallback (see reporting_simple.js's top-of-file comment for
  // the RS.state/RS.el/RS.esc/RS.api/RS.I18N contract, and
  // reporting_simple_wizard.js's top-of-file comment for why this matters
  // even though nothing here reads them at module-load time today). Keeps
  // the load-order invariant structural rather than something to remember.
  RS.esc = RS.esc || window.NX.esc;
  RS.api = RS.api || window.NX.apiSafe;
  RS.state = RS.state || {};

  function destroyChart() {
    if (RS.state.chart) { RS.state.chart.destroy(); RS.state.chart = null; }
  }

  // Simple owns its OWN Chart.js instance on a private canvas. It must never
  // call ReportingViz.mountChart: that module is a singleton wired to the
  // Advanced pane's hardcoded element ids, so concurrent mounts are unsafe.
  function chartCardNote(msg) {
    RS.el('rsChartCanvas').hidden = true;
    RS.el('rsChartTools').hidden = true;
    RS.el('rsChartNote').textContent = msg;
    RS.el('rsChartNote').hidden = false;
    RS.el('rsChartCard').hidden = false;
  }

  // Same palette ReportingViz's mountChart() uses for pie/doughnut segments
  // and multi-series bar/line. Duplicated here (not shared/imported) rather
  // than reached for via window.ReportingViz -- see the comment above
  // chartCardNote: that module is a singleton wired to the Advanced pane's
  // own DOM/state, and Simple deliberately never touches it. Must stay in
  // sync with _reporting_viz_js.html's own NX_PALETTE constant. 12 entries --
  // this pane's own multi-breakdown chart path caps series at 12 (the
  // `series.length > 12` cap below, mirroring render_chart_png's MAX_SERIES),
  // so anything shorter would silently repeat a color starting at series 8.
  var NX_PALETTE = [
    '#4f46e5', '#7c3aed', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#64748b',
    '#a78bfa', '#0891b2', '#f97316', '#be123c', '#94a3b8'
  ];

  // Chart grid-line color, derived from the theme's border token at draw
  // time so it tracks light/dark mode without a second hardcoded value.
  // Duplicated from _reporting_viz_js.html's own gridColor() for the same
  // isolation reason as NX_PALETTE above -- must stay in sync.
  function gridColor() {
    var v = getComputedStyle(document.documentElement).getPropertyValue('--nx-border').trim();
    return v || 'rgba(100,116,139,.18)';
  }

  // Same number formatter as _reporting_viz_js.html's fmt() (tooltip values
  // only): integers print bare, other numbers to 2 decimals, so aggregated
  // sums/averages don't show floating-point noise in the tooltip.
  function fmtChartTooltip(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
    return String(v);
  }

  function fadeColor(c) {
    if (typeof c !== 'string') return c;
    if (c.charAt(0) === '#') return hexAlpha(c, .35);
    var m = /^rgba?\(([^)]+)\)$/.exec(c);
    if (!m) return c;
    return 'rgba(' + m[1].split(',').slice(0, 3).map(function (s) { return s.trim(); }).join(',') + ',.35)';
  }

  function localTodayIso() {
    var t = new Date(), p = function (n) { return (n < 10 ? '0' : '') + n; };
    return t.getFullYear() + '-' + p(t.getMonth() + 1) + '-' + p(t.getDate());
  }

  // Start of the bucket that contains today, in the SQL grain's own keys.
  function currentBucketStart(grain) {
    var seq = bucketSeq(localTodayIso(), localTodayIso(), grain);
    return seq && seq.length ? seq[0] : '';
  }

  function hexAlpha(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')';
  }

  // Console x-axis: compact bucket labels ("Jan 25", "Q2 25", "2025",
  // "3 Mar") instead of raw ISO dates — the tooltip title keeps the full
  // value. Category axes (no grain) pass through unchanged.
  function prettyBucketLabel(s, grain) {
    var m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(s == null ? '' : s));
    if (!m || !grain) return s;
    var dte = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3] || 1));
    if (isNaN(dte)) return s;
    if (grain === 'year') return m[1];
    if (grain === 'quarter') return 'Q' + (Math.floor(dte.getMonth() / 3) + 1) + ' ' + m[1].slice(2);
    if (grain === 'month') return dte.toLocaleDateString(undefined, { month: 'short' }) + ' ' + m[1].slice(2);
    return dte.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });  // day / week
  }

  // Pure: the Chart.js config for a chart-data block. `def` supplies the
  // saved style (colours / right-axis picks) and the date grain; opts.onDrill
  // (index, datasetIndex) receives clicks on real (non-forecast) elements.
  // Reads only the dark-mode class and --nx-border from the document.
  // Returns {type, multi, circular, config}. Shared with the dashboard's
  // whole-report card via window.ReportingSimple.
  function chartConfigFor(d, type, def, opts) {
    var style = (def && def.style) || {};
    var onDrill = (opts && opts.onDrill) || function () {};
    var xGrain = ((def && (def.columns || [])[0]) || {}).grain || null;
    var multi = !!(d && d.multiSeries);
    if (multi && (type === 'pie' || type === 'doughnut')) type = 'bar';
    var stacked = type === 'stacked';
    var chartJsType = stacked ? 'bar' : type;
    var circular = chartJsType === 'pie' || chartJsType === 'doughnut';
    // Single-series bar/line get the ink-navy treatment (peak bucket accented
    // in indigo for bars); stacked, pie/doughnut and multi-series charts keep
    // their existing palette.
    var singleSeries = d.datasets.length === 1 && !stacked &&
      (chartJsType === 'bar' || chartJsType === 'line');
    var maxIdx = 0;
    if (singleSeries && chartJsType === 'bar') {
      var vals0 = d.datasets[0].data;
      for (var mi = 1; mi < vals0.length; mi++) { if (vals0[mi] > vals0[maxIdx]) maxIdx = mi; }
    }
    var isDark = document.documentElement.classList.contains('dark');
    // Pie/doughnut segment borders (mirrors mountChart's rlSliceBorder, fixed
    // in edf604f for the Advanced renderer): a hardcoded white border reads
    // as a bright ring against the dark --nx-card canvas (#1e293b) this
    // chart sits on -- recede into the card background in dark mode instead
    // of forcing white.
    var rlSliceBorder = isDark ? '#1e293b' : '#fff';
    var datasets = d.datasets.map(function (ds) {
      var out = Object.assign({}, ds);
      if (!multi && circular) {
        out.backgroundColor = d.labels.map(function (_, i) {
          return NX_PALETTE[i % NX_PALETTE.length];
        });
        out.borderColor = rlSliceBorder;
      } else if (singleSeries) {
        // Ink-navy (#312e81) sits at ~1.3:1 contrast against the dark
        // --nx-card canvas (#1e293b) — effectively invisible. Lift to the
        // #818cf8 family (the existing --nx-accent dark token) only for
        // dark mode; light mode keeps the locked ink-navy/indigo-peak spec.
        var rlNavy = isDark ? '#818cf8' : '#312e81';
        var rlPeak = isDark ? '#c7d2fe' : '#4f46e5';
        if (chartJsType === 'bar') {
          out.backgroundColor = ds.data.map(function (v, i) { return i === maxIdx ? rlPeak : rlNavy; });
        } else {
          out.backgroundColor = isDark ? 'rgba(129,140,248,.18)' : 'rgba(49,46,129,.12)';
        }
        out.borderColor = rlNavy;
      }
      // Rounded bars + a thickness cap (mirrors mountChart's ds.borderRadius/
      // maxBarThickness) — every bar rendering, single-series or stacked.
      if (chartJsType === 'bar') {
        out.borderRadius = 6;
        out.maxBarThickness = 48;
      }
      return out;
    });
    var overrides = style.colors || {};
    var rightKeys = circular ? [] : RS.rightAxisKeys(d, style);
    var useY2 = false;
    datasets = datasets.map(function (ds, i) {
      var key = RS.seriesKey(d.datasets[i], multi);
      var c = overrides[key];
      if (c && !circular) {
        ds.borderColor = c;
        ds.backgroundColor = chartJsType === 'line' ? hexAlpha(c, .15) : c;
      }
      if (rightKeys.indexOf(key) >= 0) { ds.yAxisID = 'y2'; useY2 = true; }
      return ds;
    });
    // The bucket containing today is still filling up: fade it (bar) or dash
    // into it (line) so a low current month reads as "in progress", not a drop.
    var grain0 = (def && (def.columns || [])[0]) ? def.columns[0].grain : null;
    var partialIdx = (grain0 && !circular) ? d.labels.indexOf(currentBucketStart(grain0)) : -1;
    if (partialIdx >= 0) {
      datasets = datasets.map(function (ds) {
        var out = Object.assign({}, ds);
        if (chartJsType === 'bar') {
          var base = out.backgroundColor;
          out.backgroundColor = out.data.map(function (_, i) {
            var c = Array.isArray(base) ? base[i] : base;
            return i === partialIdx ? fadeColor(c) : c;
          });
        } else {
          out.segment = { borderDash: function (ctx) { return ctx.p1DataIndex === partialIdx ? [4, 4] : undefined; } };
          out.pointStyle = out.data.map(function (_, i) { return i === partialIdx ? 'rectRot' : 'circle'; });
        }
        return out;
      });
    }
    // Chart annotations (#284): one marker dataset, a triangle at y=0 on each
    // annotated bucket. Tagged _nxAnnotations so the legend filter and the
    // drill click-handler treat it like _band/_forecast. Never on pie/doughnut.
    var annMap = (opts && opts.annotations) || null;
    if (annMap && !circular) {
      var annData = d.labels.map(function (lbl, i) {
        return (i < (d.forecastStart == null ? d.labels.length : d.forecastStart) && annMap[lbl]) ? 0 : null;
      });
      if (annData.some(function (v) { return v !== null; })) {
        datasets = datasets.concat([{
          _nxAnnotations: true,
          label: RS.I18N.annotationMarker,
          type: 'line',
          showLine: false,
          data: annData,
          pointStyle: 'triangle',
          pointRadius: 7,
          pointHoverRadius: 9,
          pointBackgroundColor: '#f59e0b',
          pointBorderColor: '#b45309',
          pointBorderWidth: 1,
          yAxisID: 'y',
          order: -1
        }]);
      }
    }
    // A level's NULL bucket is a gap in knowledge, not a cliff — bridge it.
    if (chartJsType === 'line') datasets.forEach(function (ds) { ds.spanGaps = true; });
    // Axis ownership cues: each Y axis is titled with its series and, when it
    // carries exactly one series, its ticks take that series' colour.
    var leftSeries = [], rightSeries = [];
    datasets.forEach(function (ds) {
      if (ds._nxAnnotations) return;
      (ds.yAxisID === 'y2' ? rightSeries : leftSeries).push(ds);
    });
    function axisTint(list) {
      return (list.length === 1 && typeof list[0].borderColor === 'string') ? list[0].borderColor : undefined;
    }
    function axisTitle(list) { return list.map(function (ds) { return ds.label; }).join(' · '); }
    var fcActive = !!(d.forecast && !multi && !stacked && (chartJsType === 'line' || chartJsType === 'bar'));
    if (fcActive) {
      var fc = d.forecast;
      var histN = d.forecastStart;
      var pad = fc.buckets.map(function () { return null; });
      datasets = datasets.map(function (ds) {
        return Object.assign({}, ds, { data: ds.data.concat(pad) });
      });
      var fcAccent = isDark ? '#818cf8' : '#4f46e5';
      var lead = [];
      for (var li = 0; li < histN - 1; li++) lead.push(null);
      fc.series.forEach(function (s, si) {
        var base = d.datasets[si];
        var styled = datasets[si] || {};
        var bridge = base ? base.data[histN - 1] : null;
        // A user-picked series colour carries over to its forecast line (and
        // its right-axis placement), so the dotted tail stays readable.
        var own = overrides[RS.seriesKey(base || {}, multi)];
        var fcColor = own || (typeof styled.borderColor === 'string' ? styled.borderColor : fcAccent);
        var fcLabel = (base ? base.label : s.field) + ' · ' + RS.I18N.forecastLabel;
        // Bar charts get the forecast as translucent bars of the same colour
        // (dashed lines over bars read as a stray series); line charts keep
        // the dashed tail + confidence band.
        datasets.push(chartJsType === 'bar' ? {
          label: fcLabel, data: lead.concat([null], s.values), type: 'bar',
          backgroundColor: hexAlpha(fcColor, .35), borderColor: fcColor, borderWidth: 1,
          borderRadius: 6, maxBarThickness: 48, yAxisID: styled.yAxisID, _forecast: true
        } : {
          label: fcLabel, data: lead.concat([bridge], s.values),
          type: 'line', borderColor: fcColor, borderDash: [6, 4],
          borderWidth: 2, backgroundColor: 'transparent', yAxisID: styled.yAxisID,
          pointStyle: 'rectRot', fill: false, tension: .25, _forecast: true
        });
      });
      if (fc.series.length === 1 && chartJsType === 'line') {
        var s0 = fc.series[0];
        var b0 = d.datasets[0] ? d.datasets[0].data[histN - 1] : null;
        var own0 = overrides[RS.seriesKey(d.datasets[0] || {}, multi)];
        var bandFill = own0 ? hexAlpha(own0, .15)
          : (isDark ? 'rgba(129,140,248,.18)' : 'rgba(79,70,229,.12)');
        datasets.push({ label: '', data: lead.concat([b0], s0.upper), type: 'line',
          borderWidth: 0, pointRadius: 0, backgroundColor: 'transparent',
          fill: false, _band: true });
        datasets.push({ label: '', data: lead.concat([b0], s0.lower), type: 'line',
          borderWidth: 0, pointRadius: 0, backgroundColor: bandFill,
          fill: '-1', _band: true });
      }
    }
    // Integer-only y-axis ticks when every plotted value across every
    // dataset actually is an integer (e.g. a COUNT/GROUP BY report) — a
    // fractional measure (avg/sum of decimals) keeps Chart.js's normal tick
    // spacing. Mirrors mountChart's allInts guard.
    var allInts = !circular && datasets.every(function (ds) {
      if (ds._nxAnnotations) return true;
      return (ds.data || []).every(function (v) { return Number.isInteger(v); });
    });
    var config = {
      type: chartJsType,
      data: { labels: d.labels, datasets: datasets },
      options: { responsive: true, maintainAspectRatio: false,
                 scales: (circular) ? {}
                   : { x: { stacked: stacked,
                            ticks: {
                              maxRotation: 0,
                              autoSkip: true,
                              maxTicksLimit: 12,
                              callback: function (value) {
                                return prettyBucketLabel(this.getLabelForValue(value), xGrain);
                              }
                            } },
                       y: { stacked: stacked,
                            beginAtZero: true,
                            title: { display: useY2, text: axisTitle(leftSeries), color: axisTint(leftSeries) },
                            ticks: {
                              maxTicksLimit: 6,
                              color: useY2 ? axisTint(leftSeries) : undefined,
                              callback: function (value) {
                                return (allInts && !Number.isInteger(value)) ? undefined : value;
                              }
                            },
                            grid: { color: gridColor() } },
                       // Secondary Y axis for level-type series (backlog in the
                       // hundreds beside imports in the tens of thousands).
                       y2: { display: useY2, position: 'right', beginAtZero: true,
                             title: { display: true, text: axisTitle(rightSeries), color: axisTint(rightSeries) },
                             ticks: { maxTicksLimit: 6, color: axisTint(rightSeries) },
                             grid: { drawOnChartArea: false } } },
                 plugins: { legend: { display: multi || circular || (d.datasets && d.datasets.length > 1) || fcActive,
                                      labels: { color: style.titleColor || undefined,
                                                filter: function (item, data) {
                                        // D6: band + forecast-line datasets are excluded from
                                        // the legend (and drill — see the _forecast/_band guard
                                        // in the drill click-handler below).
                                        var ds = data.datasets[item.datasetIndex] || {};
                                        return !(ds._band || ds._forecast || ds._nxAnnotations);
                                      } } },
                            tooltip: {
                              callbacks: {
                                // Reuse the module's own number formatter (fmtChartTooltip)
                                // instead of Chart.js's raw float — mirrors mountChart's tooltip.
                                label: function (ctx) {
                                  if (ctx.dataset._nxAnnotations) {
                                    return ((annMap || {})[ctx.label] || []).join(' · ');
                                  }
                                  var raw = ctx.parsed;
                                  var v = (raw && typeof raw === 'object') ? raw.y : raw;
                                  var name = circular ? (ctx.label || '') : (ctx.dataset.label || '');
                                  return (name ? name + ': ' : '') + fmtChartTooltip(v);
                                }
                              }
                            } },
                 onClick: function (evt) {
                   var els = this.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
                   if (!els.length) return;
                   var dsHit = (this.data.datasets || [])[els[0].datasetIndex] || {};
                   if (dsHit._forecast || dsHit._band) return;
                   if (d.forecastStart != null && d.forecast && els[0].index >= d.forecastStart) return;
                   var onAnnotate = opts && opts.onAnnotate;
                   if (onAnnotate && (dsHit._nxAnnotations || (evt.native && evt.native.altKey))) {
                     onAnnotate(els[0].index, dsHit._nxAnnotations ? null : els[0].datasetIndex); return;
                   }
                   if (dsHit._nxAnnotations) return;
                   onDrill(els[0].index, els[0].datasetIndex);
                 },
                 onHover: function (evt, els) {
                   evt.native.target.style.cursor = els.length ? 'pointer' : 'default';
                 } }
    };
    return { type: type, multi: multi, circular: circular, config: config };
  }

  function renderChart(type) {
    var d = RS.state.chartData;
    if (!d) return;
    destroyChart();
    var built = chartConfigFor(d, type, (RS.state.current && RS.state.current.def) || {},
                               { onDrill: RS.drillFromChart,
                                 annotations: RS.annotations ? RS.annotations.byBucket() : null,
                                 onAnnotate: RS.annotations ? RS.annotations.onChartAnnotate : null });
    type = built.type;
    RS.state.chartType = type;
    var multi = built.multi, circular = built.circular;
    RS.state.chart = new Chart(RS.el('rsChartCanvas'), built.config);
    RS.el('rsChartTools').querySelector('[data-type="pie"]').hidden = multi;
    RS.el('rsChartTools').querySelector('[data-type="doughnut"]').hidden = multi;
    // Forecast only draws on line/bar — grey the toggle out on pie/doughnut
    // (syncForecastCtl owns the shape-based disable after each run).
    var fcBtn = RS.el('rsForecastToggle');
    if (circular) { fcBtn.disabled = true; fcBtn.title = RS.I18N.forecastNeedsLineBar; }
    else if (RS.state.current && RS.forecastEligible(RS.state.current.def)) { fcBtn.disabled = false; fcBtn.title = RS.I18N.forecastLabel; }
    RS.el('rsChartTools').querySelector('[data-type="stacked"]').hidden = !multi;
    RS.el('rsChartCanvas').dataset.series = String(d.datasets.length);
    Array.prototype.forEach.call(
      RS.el('rsChartTools').querySelectorAll('button'), function (b) {
        b.classList.toggle('is-selected', b.dataset.type === type);
        b.setAttribute('aria-pressed', b.dataset.type === type ? 'true' : 'false');
      });
  }

  // ----- Zero-fill for date-grain buckets -----
  // "Documents per month in Q1" with data only in February must render three
  // buckets (0, 2, 0), not a single point — sparse SQL GROUP BY drops empty
  // buckets, misleading trend lines. Fills only the single-dimension case
  // with a metric and a bounded between filter on the grain column.
  // ponytail: dims>=2 keeps SQL's buckets — cross-product fill needs a
  // series axis decision; add if sparse multi-series charts start to hurt.
  function bucketSeq(startIso, endIso, grain) {
    var d = new Date(startIso.slice(0, 10) + 'T00:00:00Z');
    var end = new Date(endIso.slice(0, 10) + 'T00:00:00Z');
    if (isNaN(d) || isNaN(end)) return null;
    // Snap to the bucket start the SQL grain produces (week = Monday-anchored,
    // matching query.py's DATEDIFF(week, 0, d)).
    if (grain === 'week') d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    else if (grain === 'month') d.setUTCDate(1);
    else if (grain === 'quarter') d.setUTCMonth(Math.floor(d.getUTCMonth() / 3) * 3, 1);
    else if (grain === 'year') d.setUTCMonth(0, 1);
    var out = [];
    while (d <= end) {
      if (out.length >= 366) return null;   // unbounded/absurd range: skip fill
      out.push(d.toISOString().slice(0, 10));
      if (grain === 'day') d.setUTCDate(d.getUTCDate() + 1);
      else if (grain === 'week') d.setUTCDate(d.getUTCDate() + 7);
      else if (grain === 'month') d.setUTCMonth(d.getUTCMonth() + 1);
      else if (grain === 'quarter') d.setUTCMonth(d.getUTCMonth() + 3);
      else d.setUTCFullYear(d.getUTCFullYear() + 1);
    }
    return out;
  }

  // explicitRange, when given, is a [start, end] ISO-date pair used as-is
  // instead of derived from def's own filters/resolvedDates -- needed for
  // the prior-comparison period, whose [priorStart, priorEnd] window (a
  // length-based shift of def's range, not the same absolute dates) has no
  // filter or resolvedDates entry of its own to derive from.
  function zeroFillDateBuckets(def, rows, resolvedDates, explicitRange) {
    var cols = def.columns || [];
    var grain = cols.length === 1 ? cols[0].grain : null;
    if (!grain || !(def.metrics || []).length) return rows;
    var range = explicitRange || null;
    if (!range) {
      var f = (def.filters || []).find(function (x) {
        return x.field === cols[0].field && x.op === 'between';
      });
      if (!f) return rows;
      if (Array.isArray(f.value) && f.value.length === 2) {
        range = [String(f.value[0]), String(f.value[1])];
      } else if (f.value && typeof f.value === 'object') {
        var rd = resolvedDates.find(function (x) { return x.field === cols[0].field; });
        if (rd) range = [rd.start, rd.end];
      }
    }
    if (!range) return rows;
    // Never fabricate buckets that haven't happened yet: "This year" fills
    // Jan..today, not Jan..Dec — a future month is unknown, not zero.
    var today = localTodayIso();
    var seq = bucketSeq(range[0], range[1] > today ? today : range[1], grain);
    if (!seq) return rows;
    var byBucket = {};
    rows.forEach(function (r) {
      byBucket[String(r[0] == null ? '' : r[0]).slice(0, 10)] = r;
    });
    // Flows (counts) fill with 0 — nothing happened. Levels (latest-mode,
    // e.g. backlog) fill with null — nobody measured, which is not zero.
    var modes = RS.metricTotalModes(def);
    var zeros = (def.metrics || []).map(function (_, i) { return modes[i] === 'latest' ? null : 0; });
    var filled = seq.map(function (b) { return byBucket[b] || [b].concat(zeros); });
    // A data row whose bucket string didn't match the generated sequence
    // (dialect formatting drift) means the fill would DROP data — bail to
    // the raw rows instead.
    var misses = rows.some(function (r) {
      return seq.indexOf(String(r[0] == null ? '' : r[0]).slice(0, 10)) === -1;
    });
    if (misses) return rows;
    var s0 = (def.sort || [])[0];
    if (s0 && s0.field === cols[0].field && s0.dir === 'desc') filled.reverse();
    return filled;
  }

  // Pure: turns a run result into the chart-data block renderChart /
  // chartConfigFor draw. Returns {data, note}: data null = no chart and
  // note says why (too many points); note alongside data = a non-blocking
  // disclosure (first-50 cut, series cap, data-quality notes). DOM-free --
  // shared with the dashboard's whole-report card via window.ReportingSimple.
  function buildChartData(def, columns, rows, forecast) {
    var note = null;
    function addNote(txt) { note = note ? note + ' — ' + txt : txt; }
    var dims = (def.columns || []).length;
    if (!dims || !rows.length) return { data: null, note: null };
    var firstCol = def.columns[0];
    var isDate = !!firstCol.grain || /date/.test(firstCol.field);
    // Single-dim only: here rows.length IS the x-point count, so the raw-row
    // cap is correct. For dims===2 the rows are the (dim1 x dim2) cross-product
    // (e.g. 12 months x 8 sources = 96 rows) that the pivot below collapses to
    // far fewer x-points, so two-dim is judged AFTER pivoting by the xOrder>50
    // guard + 12-series cap (mirrors render_chart_png MAX_X / MAX_SERIES).
    // A bucketed date axis stays readable far past 50 points (53 weeks, a
    // year of days); only categorical axes keep the 50-row cut.
    var xCap = isDate ? 400 : 50;
    if (dims === 1 && rows.length > xCap) {
      if (isDate) return { data: null, note: RS.I18N.noChartTooManyPoints };
      addNote(RS.I18N.chartFirst50.replace('{n}', String(rows.length)));
      rows = rows.slice(0, 50);
    }
    if (dims >= 2) {
      // EVERY metric is pivoted into series: with several measures each
      // (dims × measure) pair becomes its own series ("Process · Measure").
      var metricIdx2 = columns.length - (def.metrics || []).length;
      var nMetrics2 = (def.metrics || []).length || 1;
      var mLabels2 = RS.metricLabelsFor(def);
      var modes2 = RS.metricTotalModes(def);
      var xOrder = [], cell = {}, seriesTot = {}, seriesParts = {}, seriesMetric = {};
      rows.forEach(function (r) {
        var x = String(r[0] == null ? '' : r[0]).slice(0, isDate ? 10 : 200);
        // Series key = ALL remaining breakdowns joined ("Process · Source").
        // With every dim in the key nothing collapses in the pivot, so each
        // cell is one exact aggregate row — correct for any aggregation, not
        // just additive ones (the old third-dim collapse only held for
        // count/sum). The 12-series cap below bounds the cross-product.
        var parts = [], labelParts = [], d;
        for (d = 1; d < dims; d++) {
          var pv = String(r[d] == null ? '' : r[d]);
          parts.push(pv);
          // A non-leading DATE dim (#164) arrives as an ISO datetime — trim it
          // for the legend the same way the x labels are trimmed. parts stays
          // raw so drill-through still gets the full value.
          labelParts.push(def.columns[d] && def.columns[d].grain ? pv.slice(0, 10) : pv);
        }
        if (!cell[x]) { xOrder.push(x); cell[x] = {}; }
        for (var mi = 0; mi < nMetrics2; mi++) {
          var s = nMetrics2 > 1
            ? labelParts.concat([mLabels2[mi] || def.metrics[mi].metric]).join(' · ')
            : labelParts.join(' · ');
          // A level metric (backlog) is NULL, not 0, on legs where it wasn't
          // measured — coercing it to 0 here would silently zero out a real
          // gap once broken down by a second dimension (#follow-up from the
          // stop-at-today/backlog-as-a-level audit). Only fold in a value
          // when this row actually has one; an all-NULL cell stays NULL.
          if (!(s in cell[x])) cell[x][s] = modes2[mi] === 'latest' ? null : 0;
          var raw = r[metricIdx2 + mi];
          if (raw != null) {
            var v = Number(raw) || 0;
            cell[x][s] = (cell[x][s] || 0) + v;
            seriesTot[s] = (seriesTot[s] || 0) + v;
          }
          seriesParts[s] = parts;
          seriesMetric[s] = mi;
        }
      });
      if (xOrder.length > xCap) return { data: null, note: RS.I18N.noChartTooManyPoints };
      var allSeries = Object.keys(seriesTot);
      var byTot = function (a, b) { return seriesTot[b] - seriesTot[a]; };
      var series;
      if (nMetrics2 > 1) {
        // Fair cap: top slots per measure, so a small-valued measure (a
        // backlog of hundreds next to document counts in the tens of
        // thousands) is never crowded out of the chart entirely.
        var per = Math.max(1, Math.floor(12 / nMetrics2));
        series = [];
        for (var mj = 0; mj < nMetrics2; mj++) {
          series = series.concat(allSeries.filter(function (s) {
            return seriesMetric[s] === mj;
          }).sort(byTot).slice(0, per));
        }
      } else {
        series = allSeries.sort(byTot).slice(0, 12);
      }
      if (allSeries.length > series.length) {
        addNote(RS.I18N.chartSeriesCapped
          .replace('{shown}', String(series.length)).replace('{n}', String(allSeries.length)));
      }
      noteDataQuality(def, rows, isDate).forEach(addNote);
      return { data: {
        labels: xOrder,
        // Raw click values for drill-through: the pivot above already
        // stringifies x keys ('' means NULL), so labels === raw here. Series
        // are per-dim value arrays so a click can filter each breakdown.
        rawX: xOrder,
        rawSeries: series.map(function (s) { return seriesParts[s]; }),
        datasets: series.map(function (s, i) {
          return {
            label: s,
            // Style key for the colours/axes popover. With several measures a
            // pivoted series is "<category> · <measure>" — keep the measure
            // code in `field` so a backlog series can default to the right axis.
            field: def.metrics && def.metrics[seriesMetric[s]] ? def.metrics[seriesMetric[s]].metric : null,
            data: xOrder.map(function (x) {
              var v = cell[x] ? cell[x][s] : undefined;
              return v === undefined ? (modes2[seriesMetric[s]] === 'latest' ? null : 0) : v;
            }),
            borderColor: NX_PALETTE[i % NX_PALETTE.length],
            backgroundColor: NX_PALETTE[i % NX_PALETTE.length],
            tension: .25
          };
        }),
        multiSeries: true,
        // Preview cache (Step 5) reads this back to tag the cached series —
        // must match whatever renderChart() below actually draws.
        type: def.chartType || (isDate ? 'line' : 'bar')
      }, note: note };
    }
    var metricIdx = columns.length - (def.metrics || []).length;
    var labels = rows.map(function (r) {
      var v = String(r[0] == null ? '' : r[0]);
      // Date values arrive as ISO datetimes — trim to the date part. Category
      // labels stay intact.
      return isDate ? v.slice(0, 10) : v;
    });
    // Raw click values for drill-through, same order as labels/rows (labels
    // are display strings — e.g. date-trimmed — so NULL/full values live here).
    var rawX = rows.map(function (r) { return r[0]; });
    var mLabels = RS.metricLabelsFor(def);
    var datasets = (def.metrics || []).map(function (m, i) {
      var col = columns[metricIdx + i];
      return {
        label: mLabels[i] || (col ? (col.header || m.metric) : m.metric),
        field: m.metric,
        data: rows.map(function (r) { return r[metricIdx + i] == null ? null : Number(r[metricIdx + i]); }),
        // First metric keeps the classic indigo; further metrics take the
        // series palette so a multi-measure report reads as distinct series.
        borderColor: i === 0 ? '#4f46e5' : NX_PALETTE[i % NX_PALETTE.length],
        backgroundColor: i === 0 ? 'rgba(79,70,229,.45)'
                                 : NX_PALETTE[i % NX_PALETTE.length],
        tension: .25
      };
    });
    var fc = (forecast && !forecast.unavailable &&
              (forecast.buckets || []).length) ? forecast : null;
    var histN = labels.length;
    if (fc) {
      labels = labels.concat(fc.buckets.map(function (b) { return String(b).slice(0, 10); }));
    }
    noteDataQuality(def, rows, isDate).forEach(addNote);
    return { data: {
      labels: labels, rawX: rawX, datasets: datasets, multiSeries: false,
      forecast: fc, forecastStart: histN,
      type: def.chartType || (isDate ? 'line' : 'bar')
    }, note: note };
  }

  function mountChart(def, columns, rows, forecast) {
    destroyChart();
    RS.state.chartData = null;
    RS.el('rsChartNote').hidden = true;
    RS.el('rsChartTools').hidden = true;
    RS.toggleStylePop(false);
    RS.el('rsChartCanvas').hidden = false;
    var dims = (def.columns || []).length;
    if (!dims || !rows.length) { RS.el('rsChartCard').hidden = true; return false; }
    if (!window.Chart) { chartCardNote(RS.I18N.noChartLib); return false; }
    var built = buildChartData(def, columns, rows, forecast);
    if (!built.data) { chartCardNote(built.note || RS.I18N.noChartTooManyPoints); return false; }
    if (built.note) {
      RS.el('rsChartNote').textContent = built.note;
      RS.el('rsChartNote').hidden = false;
    }
    RS.state.chartData = built.data;
    RS.el('rsChartCard').hidden = false;
    RS.el('rsChartTools').hidden = false;
    renderChart(RS.state.chartData.type);
    if (RS.annotations) RS.annotations.renderList();
    return true;
  }

  // Under-chart disclosures the numbers alone don't carry: the bucket that
  // contains today is still filling up, and a level metric's NULL buckets
  // are unmeasured, not empty.
  function noteDataQuality(def, rows, isDate) {
    var out = [];
    var c0 = (def.columns || [])[0];
    if (!isDate || !c0 || !c0.grain) return out;
    var cur = currentBucketStart(c0.grain);
    if (rows.some(function (r) { return String(r[0] == null ? '' : r[0]).slice(0, 10) === cur; })) {
      out.push(RS.I18N.partialBucketNote);
    }
    var metricIdx = (def.columns || []).length, modes = RS.metricTotalModes(def);
    var gaps = rows.some(function (r) {
      return modes.some(function (m, i) { return m === 'latest' && r[metricIdx + i] == null; });
    });
    if (gaps) out.push(RS.I18N.gapNote);
    return out;
  }

  // Bridge exports (chart.js -> reporting_simple.js) -- core code that still
  // needs these after the split (setView's destroyChart, renderAnomalies'/
  // captionNotes' currentBucketStart, tableHtml's fmtChartTooltip, runCurrent/
  // restoreResult/the forecast toggle's mountChart, the chart-type buttons'/
  // style-popover's renderChart, and window.ReportingSimple's
  // zeroFillDateBuckets/buildChartData/chartConfigFor) reaches them via RS.
  RS.destroyChart = destroyChart;
  RS.currentBucketStart = currentBucketStart;
  RS.fmtChartTooltip = fmtChartTooltip;
  RS.chartConfigFor = chartConfigFor;
  RS.renderChart = renderChart;
  RS.zeroFillDateBuckets = zeroFillDateBuckets;
  RS.buildChartData = buildChartData;
  RS.mountChart = mountChart;
}());
