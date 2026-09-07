// Reporting Simple pane -- result view (Beautification Phase 2b, Task 8).
// Split out of reporting_simple.js: the KPI band, anomalies card, drill
// (chart clicks + table rows), the result table builder, and the result-
// view style/error/timing helpers. Shares state via window.RS (see
// reporting_simple.js's own top-of-file comment for the RS.state/RS.el/
// RS.esc/RS.api/RS.I18N contract). This file is loaded BEFORE
// reporting_simple.js (see _reporting_simple_js.html) -- every RS.*
// reference below into things reporting_simple.js/reporting_simple_wizard.js
// define (RS.setView, RS.hideTimingBadge, RS.toggleMoreMenu, RS.EXPORT_ALLOWED,
// RS.fieldMetaFor) is only ever called from inside a function body, never at
// top-level load time, so the load order is safe: by the time any of these
// functions is actually invoked (a user action), every file has already run.
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

  // ---------- Result view ----------
  // Save/Export must never act on a definition the last run couldn't produce
  // rows for — disabled while the result pane shows an error, re-enabled the
  // moment a run actually succeeds.
  function setHeaderActionsEnabled(enabled) {
    RS.el('rsSave').disabled = !enabled;
    if (RS.EXPORT_ALLOWED) RS.el('rsExport').disabled = !enabled;
  }
  RS.setHeaderActionsEnabled = setHeaderActionsEnabled;

  // The Open-in-Advanced escape hatch rendered under rsError (only when the
  // caller passes opts.openAdvanced — e.g. a failed run whose definition can
  // still be fixed up in Advanced). Delegates to the header button's own
  // handler rather than duplicating it.
  function renderErrorOpenAdvanced(show) {
    var existing = document.getElementById('rsErrorOpenAdvanced');
    if (existing) existing.remove();
    if (!show) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'rsErrorOpenAdvanced';
    btn.className = 'reporting-btn nx-btn nx-btn--secondary';
    btn.setAttribute('data-testid', 'rs-error-open-advanced');
    btn.textContent = RS.I18N.openInAdvanced;
    btn.addEventListener('click', function () { RS.el('rsOpenAdvanced').click(); });
    RS.el('rsError').insertAdjacentElement('afterend', btn);
  }
  RS.renderErrorOpenAdvanced = renderErrorOpenAdvanced;

  function showResultError(msg, opts) {
    RS.el('rsRunLoading').hidden = true;
    if (RS.el('rsChips')) RS.el('rsChips').hidden = true;
    RS.setView('result');
    RS.hideTimingBadge();
    RS.toggleMoreMenu(false);
    RS.el('rsResultTitle').textContent = (opts && opts.title) || '';
    RS.el('rsResultTitle').style.color = '';
    RS.el('rsCrumbName').textContent = (opts && opts.title) || '';
    RS.el('rsSavedChip').hidden = true;
    RS.el('rsResultMeta').textContent = '';
    RS.el('rsTableRowCount').textContent = '';
    RS.el('rsMsg').hidden = true;
    RS.el('rsSaveName').hidden = true;
    RS.el('rsError').textContent = msg;
    RS.el('rsError').hidden = false;
    renderErrorOpenAdvanced(!!(opts && opts.openAdvanced));
    setHeaderActionsEnabled(false);
    RS.el('rsChartCard').hidden = true;
    RS.el('rsTableCard').hidden = true;
    RS.el('rsChartNote').hidden = true;
    RS.el('rsChartTools').hidden = true;
    RS.el('rsTableToggle').hidden = true;
    RS.el('rsTableWrap').hidden = true;
    RS.el('rsSqlView').hidden = true;
    RS.el('rsShowSql').hidden = true;
    RS.el('rsDrillHint').hidden = true;
    // Same stale-caption guard as runCurrent()'s run-start block — a failed
    // run must not leave the PREVIOUS run's caption sentence sitting under
    // the error message.
    var rsCaptionErrBox = RS.el('rsCaption');
    if (rsCaptionErrBox) { rsCaptionErrBox.hidden = true; rsCaptionErrBox.textContent = ''; }
    var anomErrCard = RS.el('rsAnomCard');
    if (anomErrCard) anomErrCard.hidden = true;
  }
  RS.showResultError = showResultError;

  // Prefers the server's own error + detail (e.g. "…invalid or outdated. —
  // unknown metric: 'x'") over the generic 400 fallback, so a stale saved
  // report's actual problem is visible instead of a canned line.
  function friendlyRunError(status, data) {
    if (status === 403) return RS.I18N.noAccess;
    if (status === 400) {
      if (data && data.error) return data.error + (data.detail ? ' — ' + data.detail : '');
      return RS.I18N.outdated;
    }
    return (data && data.error) || RS.I18N.couldNotRun;
  }
  RS.friendlyRunError = friendlyRunError;

  var APP_LANG = document.documentElement.lang || undefined;
  function fmtNumber(v) {
    if (v == null) return '–';
    var n = Number(v);
    // App locale (html lang attr), not browser locale — a German UI shows
    // 1'234/1.234 shapes consistently regardless of the OS language. An
    // empty lang attr degrades to the browser locale (undefined arg).
    return isNaN(n) ? String(v) : n.toLocaleString(APP_LANG);
  }
  RS.fmtNumber = fmtNumber;

  // Masthead timing badge, shared with _reporting_js.html's own showTiming
  // (same #reportingTiming element, same "N rows · M ms" shape). Hidden until
  // the first successful run in either pane. #rsResultMeta (Task 7) renders
  // the same rowCount/ms values inline under the result title, and the
  // table card's head row (Task 8) renders the row count a third time —
  // no separate computation, just further formats of the same rowsTxt.
  function showTiming(rows, elapsedMs) {
    var rowsTxt = String(rows == null ? 0 : rows);
    var msTxt = String(Math.round(elapsedMs));
    var badge = document.getElementById('reportingTiming');
    if (badge) {
      badge.textContent = RS.I18N.timingBadge.replace('{rows}', rowsTxt).replace('{ms}', msTxt);
      badge.hidden = false;
    }
    var meta = RS.el('rsResultMeta');
    if (meta) {
      meta.textContent = RS.I18N.resultMeta
        .replace('{rows}', rowsTxt).replace('{ms}', msTxt).replace('{when}', RS.I18N.runJustNow);
    }
    var tableCount = RS.el('rsTableRowCount');
    if (tableCount) tableCount.textContent = ' · ' + RS.I18N.tableRowCount.replace('{n}', rowsTxt);
  }
  RS.showTiming = showTiming;

  // Same numeric check fmtNumber uses (Number(v) + isNaN), guarded against
  // null/empty so blank dimension cells never misclassify as numeric — used
  // to tag result-table cells reporting-ledger-num (mono/tabular-nums/
  // right-aligned) at render time, mirrored in _reporting_js.html.
  function isNumericCell(v) {
    if (v == null || v === '') return false;
    var n = Number(v);
    return !isNaN(n) && isFinite(n);
  }

  // KPI stat band (L7 locked decision): total/buckets/avg computed
  // client-side from the rows the pane already has — no second query. The
  // first numeric column after the definition's dimension columns is
  // treated as the measure (every row's value must be finite); hidden when
  // there are no rows or no such column. Mirrored in _reporting_js.html's
  // own computeKpiBand/renderKpiBand for the Advanced grid.
  // Peak: the single row with the largest metric value -- its leading
  // dimension column(s) become the label (e.g. "bob" for a per-user
  // breakdown). Zero-dimension runs (dims === 0, the grand-total-only
  // case) have no bucket to label, so peakLabel is just left blank.
  function computeKpiBand(dims, rows) {
    if (!rows.length) return null;
    var idx = -1;
    // First numeric metric column; NULL cells are allowed (a level such as
    // the backlog has no value in buckets nobody measured) but skipped below.
    for (var i = dims; i < rows[0].length; i++) {
      var anyNum = rows.some(function (r) { return isNumericCell(r[i]); });
      if (anyNum && rows.every(function (r) { return r[i] == null || isNumericCell(r[i]); })) { idx = i; break; }
    }
    if (idx === -1) return null;
    var total = 0, peak = -Infinity, peakRow = rows[0], buckets = 0;
    rows.forEach(function (r) {
      if (r[idx] == null) return;
      var v = Number(r[idx]);
      total += v;
      buckets++;
      if (v > peak) { peak = v; peakRow = r; }
    });
    var peakLabel = dims ? Array.prototype.slice.call(peakRow, 0, dims).map(function (v) {
      return String(v).replace(/[T ]00:00:00(\.0+)?$/, '');
    }).join(' · ') : '';
    return { total: total, buckets: buckets, avg: buckets ? total / buckets : 0,
             peak: peak, peakLabel: peakLabel, idx: idx };
  }

  // Delta chips vs the prior period (Task 11 / D-COMPARE). The backend's
  // `comparison` block (compare: true) reruns the SAME definition over a
  // window shifted back by the CURRENT window's own length -- not
  // necessarily the previous *calendar* period (a 31-day month shifted back
  // 31 days lands one day short of the 1st of a 30-day prior month). So the
  // chip's only honest claim is the literal priorStart-priorEnd range, never
  // a calendar name like "last month" -- see shifted_definition_for_comparison.
  // Flat when the prior value is 0 (no percentage is meaningful) or the
  // magnitude of change is under 0.5%.
  function computeDelta(current, prior) {
    if (!prior || !isFinite(prior)) return { dir: 'flat', pct: 0 };
    var pct = ((current - prior) / Math.abs(prior)) * 100;
    if (Math.abs(pct) < 0.5) return { dir: 'flat', pct: 0 };
    return { dir: pct > 0 ? 'up' : 'down', pct: Math.abs(pct) };
  }

  function deltaChipHtml(current, prior, priorStart, priorEnd, asButton) {
    if (prior == null || !isFinite(current)) return '';
    var d = computeDelta(current, prior);
    var arrow = d.dir === 'up' ? '↑' : d.dir === 'down' ? '↓' : '—';
    var title = RS.I18N.deltaVs + ' ' + priorStart + ' – ' + priorEnd;
    var body = arrow + ' ' + Math.round(d.pct) + '%';
    if (!asButton) {
      return '<span class="rp-delta rp-delta--' + d.dir + '" data-testid="rp-delta"' +
        ' title="' + RS.esc(title) + '" aria-label="' + RS.esc(title) + '">' + body + '</span>';
    }
    return '<button type="button" class="rp-delta rp-delta--' + d.dir + ' rp-delta--why"' +
      ' data-testid="rp-delta" data-why="1"' +
      ' title="' + RS.esc(title + ' · ' + RS.I18N.whyLabel) + '"' +
      ' aria-label="' + RS.esc(RS.I18N.whyLabel + ' ' + title) + '">' + body + '</button>';
  }

  // Inline sparkline (Task 11): a hand-rolled SVG polyline of the metric
  // series into the total tile -- no second Chart.js instance just for a KPI
  // accent. Gated to the same single-dimension date-grain case bucketSeq/
  // zeroFillDateBuckets already special-case (see the ponytail note there);
  // `rows` here has already been through that zero-fill, so gaps read as
  // real zeros rather than a misleadingly straight line.
  function sparklineHtml(def, rows, kpi) {
    var cols = def.columns || [];
    if (cols.length !== 1 || !cols[0].grain) return '';
    if (!kpi || kpi.idx == null || rows.length < 2) return '';
    var series = rows.map(function (r) { return r[kpi.idx]; })
      .filter(function (v) { return v != null; }).map(Number);
    if (series.length < 2 || series.some(function (v) { return isNaN(v); })) return '';
    var w = 120, h = 32, pad = 2;
    var min = Math.min.apply(null, series), max = Math.max.apply(null, series);
    var span = (max - min) || 1;
    var step = (w - pad * 2) / (series.length - 1);
    var pts = series.map(function (v, i) {
      var x = pad + i * step;
      var y = h - pad - ((v - min) / span) * (h - pad * 2);
      return x.toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');
    return '<svg class="rp-sparkline" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none"' +
      ' aria-hidden="true" data-testid="rp-sparkline">' +
      '<polyline points="' + pts + '" fill="none" stroke="currentColor" stroke-width="2"' +
      ' stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }

  // Count-up (Task 7): 0 -> value over ~500ms via requestAnimationFrame
  // (stays in step with the browser's paint cycle, unlike setInterval).
  // Skipped under prefers-reduced-motion -- the final value is written
  // directly, same gate every other motion helper on this page uses.
  var PREFERS_REDUCED_MOTION = !!(window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  function animateValue(el, target, fmt) {
    var n = Number(target);
    if (isNaN(n) || PREFERS_REDUCED_MOTION) { el.textContent = fmt(target); return; }
    var t0 = null;
    function tick(now) {
      if (t0 === null) t0 = now;
      var p = Math.min(1, (now - t0) / 500);
      el.textContent = fmt(n * p);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // Every value span below carries its real target in data-count-target and
  // starts at "0" text -- renderKpiBand animates them all in one pass once
  // the whole band is in the DOM (see the querySelectorAll loop there).
  // Value + delta chip share one flex item (.rs-kpi-value-wrap) so the row's
  // caption/value space-between layout still sees exactly two top-level
  // children -- a bare 3rd sibling would split away from the value under
  // flex-wrap instead of hugging it.
  // Console KPI cards are a fixed three-row structure (label / value / sub)
  // so every value sits on the same baseline across the row — the sub span
  // renders even when empty.
  function kpiBlock(testid, caption, value, deltaHtml, sub) {
    return '<div class="reporting-ledger-kpi" data-testid="' + testid + '">' +
      '<span class="reporting-ledger-caption">' + RS.esc(caption) + '</span>' +
      '<span class="rs-kpi-value-wrap">' +
        '<span class="reporting-ledger-kpi-value" data-count-target="' + Number(value) + '">0</span>' +
        (deltaHtml || '') +
      '</span>' +
      '<span class="reporting-ledger-kpi-sub">' + RS.esc(sub || '') + '</span></div>';
  }

  // Peak row's sub is the winning bucket's label (empty for the
  // zero-dimension case, where there is none).
  function kpiPeakBlock(testid, caption, label, value, deltaHtml) {
    return '<div class="reporting-ledger-kpi" id="rsKpiPeak" data-testid="' + testid + '">' +
      '<span class="reporting-ledger-caption">' + RS.esc(caption) + '</span>' +
      '<span class="rs-kpi-value-wrap">' +
        '<span class="reporting-ledger-kpi-value" data-count-target="' + Number(value) + '">0</span>' +
        (deltaHtml || '') +
      '</span>' +
      '<span class="reporting-ledger-kpi-sub">' + RS.esc(label || '') + '</span>' +
      '</div>';
  }

  // Left-rail layout (studio result body): one labelled total card per metric
  // (the first gets the gradient, a delta chip and the sparkline), then the
  // Buckets/Avg/Peak rows stacked into a card headed with the measure they
  // describe -- all inside the one #rsKpiBand container computeKpiBand
  // already owned (see the CSS for the ID-scoped override that turns the
  // Advanced pane's shared flat .reporting-ledger-kpis row into this stack
  // for Simple only). Nothing here says a bare "Total" any more: on a
  // multi-metric run that number was one arbitrary metric's, and the reader
  // had no way to tell which. The grand totals used to be repeated in a
  // separate rsStatCard above the band; they live here now.
  // Pure HTML builder for the band above. Returns '' when the rows carry no
  // numeric metric column. DOM-free -- shared with the dashboard's whole-
  // report card via window.ReportingSimple, so it must never touch #rs*
  // elements; a card passes its OWN zero-column run through `grandTotals`
  // rather than inheriting the Simple pane's RS.state.
  function kpiBandHtml(dims, rows, comparison, def, columns, grandTotals) {
    var kpi = computeKpiBand(dims, rows);
    if (!kpi) return '';
    // Prior-period KPIs via the SAME computeKpiBand, fed comparison.rows --
    // no separate delta math to keep in sync. comparison.rows comes straight
    // off the backend's GROUP BY and omits empty date buckets exactly like
    // the current run's raw rows do, so it needs the SAME zero-fill the
    // current run's rows already got (see the call in runCurrent) before
    // `buckets` (and therefore `avg`) is computed -- otherwise the two
    // periods' bucket counts can disagree whenever either has a sparse
    // bucket, which skews the avg delta chip (Task 11 follow-up fix). The
    // prior window is a length-based shift, not calendar-aligned (see the
    // comment above computeDelta), so priorStart/priorEnd -- not def's own
    // date range -- are the correct fill bounds here.
    var priorRows = (comparison && comparison.rows && def)
      ? RS.zeroFillDateBuckets(def, comparison.rows, [], [comparison.priorStart, comparison.priorEnd])
      : (comparison ? comparison.rows : null);
    var priorKpi = priorRows ? computeKpiBand(dims, priorRows) : null;
    // kpi.total only feeds the delta chip now (the cards render their own
    // per-measure totals), but it still has to be the same kind of number the
    // prior period's is -- a level's latest bucket, not its sum.
    applyLatestTotal(def, kpi, rows);
    if (priorKpi) applyLatestTotal(def, priorKpi, priorRows);
    var totalDelta = '', avgDelta = '', peakDelta = '', deltaNote = '';
    if (priorKpi) {
      deltaNote = RS.I18N.deltaVs + ' ' + comparison.priorStart + ' – ' + comparison.priorEnd;
      totalDelta = deltaChipHtml(kpi.total, priorKpi.total, comparison.priorStart, comparison.priorEnd, true);
      // Bucket-count mismatch guard: shifted_definition_for_comparison shifts
      // the prior window back by the CURRENT window's length in DAYS, not by
      // an integer number of grain periods -- for a window whose day-length
      // isn't grain-aligned (e.g. a calendar-quarter preset against a month
      // grain), the shifted priorStart can land mid-month and zero-fill to a
      // different number of buckets than the current period (see Finding 2,
      // Phase 3 review). Averaging total/bucket-count across two genuinely
      // different-length periods would fabricate a percentage, so only the
      // avg chip is suppressed here -- total/peak are unaffected (an extra
      // all-zero bucket contributes 0 to both) and keep rendering normally.
      if (kpi.buckets === priorKpi.buckets) {
        avgDelta = deltaChipHtml(kpi.avg, priorKpi.avg, comparison.priorStart, comparison.priorEnd);
      }
      peakDelta = deltaChipHtml(kpi.peak, priorKpi.peak, comparison.priorStart, comparison.priorEnd);
    }
    var sparkHtml = def ? sparklineHtml(def, rows, kpi) : '';
    var measures = measureTotals(def, columns, rows, dims, kpi, grandTotals);
    // The delta chip and the sparkline both describe the series at kpi.idx,
    // so they only belong on the headline card when that is the measure it
    // shows -- and only while the shown figure IS this pane's own sum of that
    // series. An authoritative grand total (a distinct count, an average)
    // can't be diffed against a client-side sum of the prior period without
    // inventing a percentage.
    var headline = measures[0] || null;
    var seriesIsHeadline = !!headline && headline.idx === kpi.idx &&
      Math.abs(Number(headline.total) - Number(kpi.total)) < 0.5;
    // Buckets/Avg/Peak describe a distribution across the breakdown; a
    // zero-dimension run is a single grand total with nothing to distribute.
    var statsHtml = dims ? (
      '<div class="rs-kpi-stats-card">' +
        '<span class="rs-kpi-stats-title" data-testid="rs-kpi-stats-title">' +
          RS.esc(measureLabel(columns, kpi.idx)) + '</span>' +
        kpiBlock('rs-kpi-buckets', RS.I18N.kpiBuckets, kpi.buckets, '', RS.I18N.kpiBucketsSub) +
        kpiBlock('rs-kpi-avg', RS.I18N.kpiAvg, kpi.avg, avgDelta, RS.I18N.kpiAvgSub) +
        kpiPeakBlock('rs-kpi-peak', RS.I18N.kpiPeak, kpi.peakLabel, kpi.peak, peakDelta) +
      '</div>') : '';
    return measures.map(function (m, i) {
      var first = i === 0;
      // Console card: caption keeps the "Total · <measure>" contract; the
      // explainer (last-bucket note for levels, sum-over-period otherwise)
      // moves to the sub line so every value sits on one baseline.
      return '<div class="rs-kpi-total-card' + (first ? '' : ' rs-kpi-total-card--alt') + '"' +
        ' data-testid="' + (first ? 'rs-kpi-total' : 'rs-kpi-total-extra') + '">' +
        '<span class="reporting-ledger-caption" title="' +
          RS.esc(RS.I18N.kpiTotal + (m.label ? ' · ' + m.label : '')) + '">' +
          RS.esc(RS.I18N.kpiTotal) + (m.label ? ' · ' + RS.esc(m.label) : '') +
        '</span>' +
        '<span class="rs-kpi-value-wrap">' +
          '<span class="reporting-ledger-kpi-value" data-count-target="' + Number(m.total) + '">0</span>' +
          (first && seriesIsHeadline ? totalDelta : '') +
        '</span>' +
        '<span class="reporting-ledger-kpi-sub">' +
          RS.esc(m.latestKey
            ? RS.I18N.kpiLatestSuffix + ' ' + String(m.latestKey).slice(0, 16)
            : RS.I18N.kpiSumSub) +
          // The delta chip's "vs <prior range>" was tooltip-only, so the
          // percentage read as a bare number with nothing to compare against.
          (first && seriesIsHeadline && totalDelta ? ' · ' + RS.esc(deltaNote) : '') +
        '</span>' +
        (first && seriesIsHeadline ? sparkHtml : '') +
        '</div>';
    }).join('') + statsHtml;
  }
  RS.kpiBandHtml = kpiBandHtml;

  function renderKpiBand(dims, rows, comparison, def, columns) {
    var band = RS.el('rsKpiBand');
    var html = kpiBandHtml(dims, rows, comparison, def, columns);
    if (!html) { band.hidden = true; band.innerHTML = ''; return; }
    band.innerHTML = html;
    band.hidden = false;
    Array.prototype.forEach.call(band.querySelectorAll('[data-count-target]'), function (span) {
      animateValue(span, Number(span.getAttribute('data-count-target')), fmtNumber);
    });
  }
  RS.renderKpiBand = renderKpiBand;

  // Console "Anomalies" card: cheap client-side outlier notes over the rows
  // already rendered — the latest complete bucket's swing per series, plus
  // each series' peak bucket. Only for a single-dimension result (one clean
  // axis). ponytail: ±15% swing heuristic; a real detector belongs
  // server-side if this ever needs to be smarter.
  function renderAnomalies(def, columns, rows) {
    var card = RS.el('rsAnomCard');
    if (!card) return;
    card.hidden = true;
    RS.el('rsAnomRows').innerHTML = '';
    var dims = (def.columns || []).length;
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;
    if (!hasMetrics || dims !== 1 || !rows || rows.length < 3) return;
    var grain = def.columns[0].grain || null;
    var body = rows.slice();
    // Ignore a trailing partial bucket — comparing it against a full one
    // would fabricate a drop (same reasoning as the chart's faded bucket).
    if (grain && body.length &&
        String(body[body.length - 1][0] || '').slice(0, 10) >= RS.currentBucketStart(grain)) {
      body = body.slice(0, -1);
    }
    if (body.length < 3) return;
    var out = [];
    var mlabels = metricLabelsFor(def);
    for (var mi = dims; mi < columns.length; mi++) {
      var vals = body.map(function (r) { return Number(r[mi]) || 0; });
      var label = mlabels[mi - dims] || columns[mi].header || columns[mi].field;
      var last = vals[vals.length - 1], prev = vals[vals.length - 2];
      // prev >= 5: a swing between single-digit buckets is noise, not signal
      if (prev >= 5) {
        var pct = (last - prev) / prev;
        if (Math.abs(pct) >= 0.15) {
          out.push({
            cls: pct < 0 ? 'rs-anom-dot--down' : 'rs-anom-dot--up',
            text: (pct < 0 ? RS.I18N.anomDown : RS.I18N.anomUp)
              .replace('{label}', label)
              .replace('{pct}', Math.round(Math.abs(pct) * 100) + '%'),
            value: fmtNumber(last)
          });
        }
      }
      var maxI = 0;
      vals.forEach(function (v, i) { if (v > vals[maxI]) maxI = i; });
      if (vals[maxI] > 0 && maxI !== vals.length - 1) {
        out.push({
          cls: 'rs-anom-dot--peak',
          text: RS.I18N.anomPeak.replace('{label}', label)
            .replace('{bucket}', String(body[maxI][0]).slice(0, 10)),
          value: fmtNumber(vals[maxI])
        });
      }
    }
    out = out.slice(0, 3);
    if (!out.length) return;
    RS.el('rsAnomRows').innerHTML = out.map(function (a) {
      return '<div class="rs-anom-row"><span class="rs-anom-dot ' + a.cls + '"></span>' +
        '<span class="rs-anom-text">' + RS.esc(a.text) + '</span>' +
        '<span class="rs-anom-val">' + RS.esc(a.value) + '</span></div>';
    }).join('');
    card.hidden = false;
  }
  RS.renderAnomalies = renderAnomalies;

  function metricLabelsFor(def) {
    var list = (RS.state.metricsBySource || {})[def.source] || [];
    return (def.metrics || []).map(function (m) {
      var hit = list.find(function (x) { return x.code === m.metric; });
      return hit ? hit.label : m.metric;
    });
  }
  RS.metricLabelsFor = metricLabelsFor;

  // Authoritative per-metric grand totals (one cell per def.metrics entry),
  // from the zero-column clone run — or from the single row of a zero-dim run,
  // which IS that total. The band renders them; summing the grouped rows in
  // the browser only happens to be right for additive metrics, and would
  // quietly double-count a count_distinct or average an average.
  function setGrandTotals(rowVals) {
    RS.state.grandTotals = Array.isArray(rowVals) ? rowVals : null;
  }
  RS.setGrandTotals = setGrandTotals;

  // The metric's aggregation (sum/avg/count/count_distinct/…), used to decide
  // whether a drilled-into set of rows is a strict "contributing to this
  // number" count (distinct aggregations) vs. an exact breakdown.
  function metricAggFor(def) {
    var m = (def.metrics && def.metrics[0]) || null;
    if (!m) return '';
    var list = (RS.state.metricsBySource || {})[def.source] || [];
    var hit = list.find(function (x) { return x.code === m.metric; });
    return hit ? hit.aggregation : '';
  }

  function metricTotalModeFor(def) {
    var m = (def.metrics && def.metrics[0]) || null;
    if (!m) return 'sum';
    var list = (RS.state.metricsBySource || {})[def.source] || [];
    var hit = list.find(function (x) { return x.code === m.metric; });
    return (hit && hit.totalMode) || 'sum';
  }

  // One totalMode per def.metrics entry ('sum' | 'latest').
  function metricTotalModes(def) {
    var list = (RS.state.metricsBySource || {})[def.source] || [];
    return (def.metrics || []).map(function (m) {
      var hit = list.find(function (x) { return x.code === m.metric; });
      return (hit && hit.totalMode) || 'sum';
    });
  }
  RS.metricTotalModes = metricTotalModes;

  // #178 C10: for a latest-mode metric the "total" is the newest date
  // bucket's sum, not the sum over all buckets -- a level (the backlog) added
  // up across twelve months is a number nobody can spend. Returns
  // {total, key} for column `idx`, or null when there is no date dimension.
  function latestBucketTotal(def, rows, idx) {
    var cols = def.columns || [];
    var dateIdx = -1;
    for (var i = 0; i < cols.length; i++) {
      var m = RS.fieldMetaFor(def, cols[i].field);
      if (cols[i].grain || (m && m.grainable)) { dateIdx = i; break; }
    }
    if (dateIdx === -1) return null;
    var maxKey = null;
    rows.forEach(function (r) {
      if (r[idx] == null) return;   // no snapshot in this bucket
      var k = String(r[dateIdx]);
      if (maxKey === null || k > maxKey) maxKey = k;
    });
    if (maxKey === null) return null;
    var t = 0;
    rows.forEach(function (r) {
      if (String(r[dateIdx]) === maxKey) t += Number(r[idx]) || 0;
    });
    return { total: t, key: maxKey };
  }

  // Rewrites kpi.total in place for a latest-mode primary metric; returns the
  // bucket label it used, or null when not applicable.
  function applyLatestTotal(def, kpi, rows) {
    if (!kpi || metricTotalModeFor(def) !== 'latest') return null;
    var latest = latestBucketTotal(def, rows, kpi.idx);
    if (!latest) return null;
    kpi.total = latest.total;
    return latest.key;
  }

  // Result-column header for a measure, e.g. "Documents imported" -- what the
  // /run payload already carries for every projected column (metric columns
  // included, since _prepare_run headers them from the registry label). This
  // is what makes a KPI say WHAT it totals; without it the band just reads
  // "Total" and the reader has to guess which of the metrics it means.
  function measureLabel(columns, idx) {
    var c = (columns || [])[idx];
    return (c && (c.header || c.field)) || '';
  }

  // One labelled total per metric, in def.metrics order — the aggregate query
  // projects the metrics after the dimensions, so measure n lives at dims + n.
  // Prefers the authoritative grand total (RS.state.grandTotals); otherwise falls
  // back to this pane's own arithmetic, which honours each measure's total
  // mode so a level (the backlog) reports its latest snapshot rather than a
  // meaningless sum across buckets. A definition with no semantic metrics
  // (SQL / plain grid) has exactly one measure: whatever numeric column
  // computeKpiBand locked onto.
  function measureTotals(def, columns, rows, dims, kpi, grandTotals) {
    var modes = def ? metricTotalModes(def) : [];
    if (!modes.length) {
      return kpi ? [{ idx: kpi.idx, label: measureLabel(columns, kpi.idx),
                      total: kpi.total, latestKey: null }] : [];
    }
    var grand = grandTotals === undefined ? RS.state.grandTotals : grandTotals;
    return modes.map(function (mode, n) {
      var idx = dims + n;
      var exact = grand && isNumericCell(grand[n]);
      // Computed even when the grand total is authoritative: its bucket key
      // is what the caption annotates ("· last bucket 2026-08-06"), so the
      // reader knows a level is a snapshot and not a period sum.
      var latest = mode === 'latest' ? latestBucketTotal(def, rows, idx) : null;
      var total = 0;
      if (exact) {
        total = Number(grand[n]);
      } else if (latest) {
        total = latest.total;
      } else {
        rows.forEach(function (r) { if (isNumericCell(r[idx])) total += Number(r[idx]); });
      }
      return {
        idx: idx,
        label: measureLabel(columns, idx),
        total: total,
        latestKey: latest ? latest.key : null,
      };
    });
  }

  // ----- Drill-through (Simple: chart clicks + table rows) -----
  // Maps a definition's leading columns (dimensions come first in the result
  // row) to ReportingDrill's {field, grain, value} shape.
  function clickedFor(rowValues) {
    return ((RS.state.current && RS.state.current.def && RS.state.current.def.columns) || [])
      .map(function (c, i) {
        return { field: c.field, grain: c.grain || null, value: rowValues[i] };
      });
  }

  function openDrill(clicked) {
    var cur = RS.state.current;
    if (!cur || !cur.def) return;
    var src = (RS.state.sources || []).find(function (s) { return s.id === cur.def.source; });
    if (!src) return;
    var header = clicked.map(function (c) {
      var f = (src.fields || []).find(function (x) { return x.field === c.field; });
      var v = (c.value === null || c.value === undefined || c.value === '')
        ? ReportingDrill.I18N.nullLabel : String(c.value).slice(0, 60);
      return ((f && f.label) || c.field) + ' = ' + v;
    }).join(' · ');
    var isDistinct = /distinct/i.test(String(metricAggFor(cur.def) || ''));
    ReportingDrill.open({
      definition: cur.def, fields: src.fields || [],
      clicked: clicked, header: header, isDistinct: isDistinct
    });
  }
  RS.openDrill = openDrill;

  // index/datasetIndex are Chart.js element coordinates from onClick. Drill
  // only engages for aggregate results (a definition with at least one metric
  // and at least one dimension) — raw-row grids never reach mountChart/here.
  function drillFromChart(index, datasetIndex) {
    var cur = RS.state.current;
    if (!cur || !cur.def) return;
    if (!(cur.def.metrics || []).length) return;
    var dims = cur.def.columns || [];
    if (!dims.length) return;
    var cd = RS.state.chartData || {};
    var clicked = [{
      field: dims[0].field, grain: dims[0].grain || null,
      value: (cd.rawX || cd.labels || [])[index]
    }];
    if (cd.multiSeries && dims.length > 1) {
      // rawSeries entries are per-dim value arrays (["Process", "Source"]) —
      // one filter per remaining breakdown.
      var parts = (cd.rawSeries || [])[datasetIndex] || [];
      for (var d = 1; d < dims.length; d++) {
        // Grain matters on non-leading dims too now that a second DATE
        // breakdown is allowed (#164) — a bucket must drill to its range,
        // not to an equality on the bucket-start value.
        clicked.push({ field: dims[d].field, grain: dims[d].grain || null, value: parts[d - 1] });
      }
    }
    openDrill(clicked);
  }
  RS.drillFromChart = drillFromChart;

  // Pure HTML builder for the result grid (data bars + forecast rows).
  // `drillable` only adds the clickable class -- the caller binds the row
  // handlers. Shared with the dashboard's whole-report card.
  function tableHtml(columns, rows, forecast, drillable) {
    var html = '<table class="reporting-table' + (drillable ? ' reporting-drill-clickable' : '') +
      '"><thead><tr>';
    columns.forEach(function (c) { html += '<th>' + RS.esc(c.header || c.field) + '</th>'; });
    html += '</tr></thead><tbody>';
    // Data bars (Task 7): one column max per column index, computed once
    // over cells the same isNumericCell check already accepts — mirrors
    // _reporting_js.html's renderResults so both panes' grids get the same
    // treatment.
    var colMax = columns.map(function (_, i) {
      var max = 0;
      rows.forEach(function (r) {
        if (isNumericCell(r[i])) {
          var n = Math.abs(Number(r[i]));
          if (n > max) max = n;
        }
      });
      return max;
    });
    rows.forEach(function (r) {
      html += '<tr>';
      r.forEach(function (v, i) {
        if (isNumericCell(v)) {
          var max = colMax[i];
          var pct = max > 0 ? (Math.abs(Number(v)) / max * 100) : 0;
          html += '<td class="reporting-ledger-num rp-cell-num" style="--bar:' + pct + '%">' + RS.esc(v) + '</td>';
        } else {
          html += '<td>' + RS.esc(v == null ? '' : v) + '</td>';
        }
      });
      html += '</tr>';
    });
    var fcRows = (forecast && !forecast.unavailable && (forecast.buckets || []).length)
      ? forecast : null;
    if (fcRows) {
      var mStart = columns.length - fcRows.series.length;
      fcRows.buckets.forEach(function (b, bi) {
        html += '<tr class="is-forecast" data-testid="rs-forecast-row">';
        for (var ci = 0; ci < columns.length; ci++) {
          if (ci === 0) {
            html += '<td>' + RS.esc(String(b).slice(0, 10)) +
              ' <span class="rp-forecast-badge">' + RS.esc(RS.I18N.forecastLabel) + '</span></td>';
          } else if (ci >= mStart) {
            var sv = fcRows.series[ci - mStart];
            html += '<td class="reporting-ledger-num">' +
              RS.esc(RS.fmtChartTooltip(sv.values[bi])) + '</td>';
          } else {
            html += '<td></td>';
          }
        }
        html += '</tr>';
      });
    }
    html += '</tbody></table>';
    return html;
  }
  RS.tableHtml = tableHtml;

  function renderTable(columns, rows, forecast) {
    var cur = RS.state.current;
    var def = (cur && cur.def) || {};
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;
    var dims = (def.columns || []).length;
    var src = (RS.state.sources || []).find(function (s) { return s.id === def.source; });
    // Drillable only for aggregate results (metric + dimension) whose leading
    // columns resolve to a valid drill definition — probed once with the
    // first row rather than assumed, so e.g. non-filterable dimensions don't
    // get a false affordance.
    var drillable = !!(hasMetrics && dims && src && rows.length &&
      ReportingDrill.buildDrillDefinition(def, src.fields || [], clickedFor(rows[0])));
    RS.el('rsTableWrap').innerHTML = tableHtml(columns, rows, forecast, drillable);
    if (drillable) {
      Array.prototype.forEach.call(
        RS.el('rsTableWrap').querySelectorAll('tbody tr:not(.is-forecast)'), function (tr, i) {
          var rowValues = rows[i];
          tr.tabIndex = 0;
          tr.addEventListener('click', function () { openDrill(clickedFor(rowValues)); });
          tr.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') openDrill(clickedFor(rowValues));
          });
        });
    }
    RS.el('rsDrillHint').hidden = !drillable;
  }
  RS.renderTable = renderTable;

  // ----- Colours & axes overrides (def.style, Simple tab only) -----
  // style = { colors: {seriesKey: '#rrggbb'}, titleColor: '#rrggbb',
  //           rightAxis: [seriesKey] } -- saved with the report like forecast.
  function styleOf() {
    var cur = RS.state.current;
    return (cur && cur.def && cur.def.style) || {};
  }
  RS.styleOf = styleOf;
  function ensureStyle() {
    var cur = RS.state.current;
    if (!cur.def.style) cur.def.style = {};
    return cur.def.style;
  }
  RS.ensureStyle = ensureStyle;
  // Metric code for measure series (locale-stable); the pivoted label for
  // multi-breakdown series, where several series share one measure code.
  function seriesKey(ds, multi) { return (!multi && ds.field) || ds.label; }
  RS.seriesKey = seriesKey;
  // ponytail: backlog detection by metric code; make it registry-driven if a
  // second level-type measure ever appears.
  function rightAxisKeys(d, style) {
    if (Array.isArray(style.rightAxis)) return style.rightAxis;
    if (!d || d.datasets.length < 2) return [];
    return d.datasets.filter(function (ds) { return /backlog/i.test(ds.field || ''); })
      .map(function (ds) { return seriesKey(ds, !!d.multiSeries); });
  }
  RS.rightAxisKeys = rightAxisKeys;
  function rgbToHex(rgb) {
    var m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(rgb || '');
    if (!m) return '#1f2937';
    return '#' + [m[1], m[2], m[3]].map(function (v) {
      return ('0' + parseInt(v, 10).toString(16)).slice(-2);
    }).join('');
  }
  RS.rgbToHex = rgbToHex;
  function applyTitleStyle() {
    RS.el('rsResultTitle').style.color = styleOf().titleColor || '';
  }
  RS.applyTitleStyle = applyTitleStyle;

  function appendChartNote(txt) {
    var n = RS.el('rsChartNote');
    n.textContent = (!n.hidden && n.textContent) ? n.textContent + ' — ' + txt : txt;
    n.hidden = false;
  }
  RS.appendChartNote = appendChartNote;
}());
