// Simple pane behavior (Spec 2). Self-contained IIFE: talks only to the
// existing REST endpoints plus window.Reporting / window.ReportingTabs.
// Never touches the Advanced builder's DOM or ReportingViz (the builder's
// chart singleton); the result view owns a private Chart.js instance.
//
// Split across five files (#191, Beautification Phase 2b Tasks 7-8):
// reporting_simple_chart.js (chart trio), reporting_simple_library.js
// (report grid), reporting_simple_result.js (KPI band/anomalies/drill/
// table), reporting_simple_wizard.js (chip editors + 4-step wizard), and
// THIS file -- the entry point. It keeps state/runCurrent/save/init plus
// the window.ReportingSimple export, and loads LAST (see
// _reporting_simple_js.html) since its top-level code wires event
// listeners that call into every other file via RS.*.
(function () {
  window.RS = window.RS || {};
  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var API_PREFIX = window.API_PREFIX;
  var EXPORT_ALLOWED = !!document.getElementById('rsExport');
  RS.EXPORT_ALLOWED = EXPORT_ALLOWED;

  RS.I18N = window.NX_I18N_REPORTING_SIMPLE;

  RS.state = {
    reports: [],            // /api/reporting/reports rows (kind!=='sql')
    sources: null,          // /api/reporting/sources cache
    metricsBySource: null,  // /api/reporting/measures cache
    loaded: false,
    view: 'library',        // library | wizard | result
    current: null,          // { def, name, reportId, owned, canEdit, fromWizard }
    grandTotals: null,      // authoritative per-metric totals for the KPI band
    chart: null,            // private Chart.js instance
    chartData: null,        // prepared labels+datasets for renderChart
    wiz: null,              // wizard state
    sort: 'updated',        // library sort: 'updated' | 'name'
    layout: (function () {  // library card layout: '2' | '4' per row
      try { return localStorage.getItem('nx.reporting.layout') === '4' ? '4' : '2'; }
      catch (e) { return '2'; }
    }())
  };

  // el/api/esc: shared with nx_core.js (Task 11) -- this file's RS.api() never
  // throws (resolves to {ok,status,data}), so it aliases NX.apiSafe, not
  // NX.api.
  RS.el = window.NX.el;
  RS.api = window.NX.apiSafe;
  RS.esc = window.NX.esc;

  function setView(view) {
    RS.state.view = view;
    RS.el('rsLibrary').hidden = view !== 'library';  // #rsSearch nests under it now
    RS.el('rsWizard').hidden = view !== 'wizard';
    RS.el('rsResult').hidden = view !== 'result';
    RS.el('rsDashboard').hidden = view !== 'dashboard';
    RS.el('rsLayouts').hidden = view !== 'layouts';
    // The dashboard grid takes the whole viewport width: the workspace rail
    // and the shell's max-width step aside while it is open (reporting-console.css).
    document.body.classList.toggle('rdb-fullbleed', view === 'dashboard' || view === 'layouts');
    if (view !== 'result') {
      // Only the Chart.js instance is torn down; the rest of the result DOM
      // (KPI band, table, caption, chips, query card) stays rendered so the
      // Results nav item can restore the last result without re-querying
      // (Console design intent #8) — restoreResult() re-mounts the chart
      // from RS.state.lastRun.
      RS.destroyChart();
      hideTimingBadge();
      toggleMoreMenu(false);
    }
    // The Console nav rail follows the Simple pane's internal view.
    document.dispatchEvent(new CustomEvent('rs:viewchanged', { detail: { view: view } }));
  }
  RS.setView = setView;

  // Console "Results" nav: bring back the last rendered result from cache.
  // Returns false when this session has no rendered result yet.
  function restoreResult() {
    var cur = RS.state.current, lr = RS.state.lastRun;
    if (!cur || !lr) return false;
    setView('result');
    var lgrid = RS.el('rsLayoutGrid');
    if (lr.layout && window.ReportingLayoutView) {
      lgrid.hidden = false;
      lgrid.innerHTML = (lr.layout.tiles || []).map(function (t) {
        return '<div class="rdb-card rl-tile" data-card-id="' + RS.esc(t.id) + '" data-type="' + t.type + '" ' +
          'style="' + window.ReportingGrid.geomStyle(t.span, t.rows) + '" data-testid="rs-layout-tile">' +
          '<div class="rdb-card-body" data-tile-body></div></div>';
      }).join('');
      window.ReportingLayoutView.render(lgrid, { layout: lr.layout, def: cur.def, columns: lr.columns, rows: lr.rows,
        derived: lr.derived || {}, i18n: window.NX_I18N_REPORTING_LAYOUTS });
      RS.el('rsKpiBand').hidden = true;
      RS.el('rsChartCard').hidden = true;
      RS.el('rsTableCard').hidden = true;
      RS.el('rsTableToggle').hidden = true;
      return true;
    }
    lgrid.hidden = true;
    if (window.ReportingLayoutView) window.ReportingLayoutView.destroy(lgrid);
    if (lr.hasMetrics && lr.dims) {
      RS.mountChart(cur.def, lr.columns, lr.rows,
        (cur.def.forecast && cur.def.forecast.enabled) ? (lr.forecast || null) : null);
    }
    return true;
  }

  // Entry point for the Console nav rail (js/_reporting_tabs_js.html).
  function navTo(screen) {
    if (screen === 'library') {
      if (RS.state.view !== 'library') { setView('library'); RS.loadLibrary(); }
      return;
    }
    if (screen === 'results') {
      if (RS.state.view === 'result') return;
      if (restoreResult()) return;
      // Nothing rendered yet this session: open the most recent report so
      // Results never shows an empty RS.state.
      var r = (RS.state.reports || []).filter(function (x) { return x.kind !== 'dashboard' && x.kind !== 'layout'; })[0];
      if (r) RS.openReport(r); else setView('library');
      return;
    }
    if (screen === 'dashboards') {
      if (RS.state.view === 'dashboard') return;
      var d = (RS.state.reports || []).filter(function (x) { return x.kind === 'dashboard'; })[0];
      if (d) { RS.openDashboard(d); return; }
      setView('dashboard');
      window.ReportingDashboard.openNew();
    }
    if (screen === 'definitions') {
      if (RS.state.view === 'layouts') return;
      setView('layouts');
      if (window.ReportingLayouts) window.ReportingLayouts.open();
    }
  }

  // Hide the shared masthead timing badge — but only when the Simple pane
  // actually owns the current tab; the Advanced tab's still-rendered result
  // must keep its badge across Simple-pane view changes.
  function hideTimingBadge() {
    if (!(window.ReportingTabs && window.ReportingTabs.current() === 'simple')) return;
    var timing = RS.el('reportingTiming');
    if (timing) timing.hidden = true;
  }
  RS.hideTimingBadge = hideTimingBadge;

  // Result-header ⋯ overflow menu (Task 7) — same open/close idiom as the
  // Advanced tab's process-scope dropdown (toggleScopeMenu/#rpScopeMenu in
  // _reporting_js.html): hidden flag on the menu, aria-expanded on the
  // trigger. Click-to-toggle, outside-click and Escape wiring live at the
  // bottom of this file, next to the other header button bindings.
  function toggleMoreMenu(open) {
    var menu = RS.el('rsMoreMenu');
    var btn = RS.el('rsMore');
    if (!menu || !btn) return;
    var willOpen = (open === undefined) ? menu.hidden : open;
    menu.hidden = !willOpen;
    btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  }
  RS.toggleMoreMenu = toggleMoreMenu;

  // In-flight skeleton (Task 7): a KPI-band-shaped + table-shaped
  // placeholder injected into #rsRunLoading while a run is in flight —
  // replaces the old static dots+text markup so the real KPI band/table
  // don't cause a layout jump on arrival. Pure CSS shimmer (.rp-skeleton),
  // reduced-motion safe via reporting.css's own query; mirrors
  // _reporting_js.html's showRunLoading skeleton for the Advanced pane.
  function resultSkeletonHtml() {
    var kpis = '';
    for (var i = 0; i < 3; i++) kpis += '<div class="rp-skeleton rp-skeleton-kpi"></div>';
    var rows = '';
    for (var j = 0; j < 6; j++) rows += '<div class="rp-skeleton rp-skeleton-row"></div>';
    return '<div class="rp-skeleton-band">' + kpis + '</div>' +
           '<div class="rp-skeleton-table">' + rows + '</div>';
  }

  // ----- Auto AI caption (Task 13) -------------------------------------------
  // Fires after every successful run render when the caption slot exists in
  // the DOM -- it only exists when the page was rendered for a
  // reporting.ai.explain.use holder (Jinja `ai_caption_enabled` gate in
  // _reporting_simple.html), so a caller with no permission is a silent
  // no-op. Shimmers while the request is in flight, then shows the caption
  // with its AI chip -- or hides silently on ANY error (network failure,
  // non-200, bad JSON): unlike the chat panel, this surface never shows an
  // error state or logs to the console. `captionSeq` is a monotonically-
  // increasing token (same idiom as runSeq below): a slow response from an
  // old run is discarded once a newer run has fired its own caption, so a
  // fast filter change/re-run can never show a stale caption over the new
  // result. Duplicated (not shared) in _reporting_js.html for the Advanced
  // pane -- see that file for why.
  var captionSeq = 0;
  // Facts about the grid the caption model can't see for itself (the model
  // otherwise narrates a half-finished month as a drop and a NULL as zero).
  function captionNotes(def, rows) {
    var out = [];
    var c0 = (def.columns || [])[0];
    if (c0 && c0.grain) {
      var cur = RS.currentBucketStart(c0.grain);
      if (rows.some(function (r) { return String(r[0] == null ? '' : r[0]).slice(0, 10) === cur; })) {
        out.push('The bucket ' + cur + ' is the current, still-running period and is incomplete; ' +
                 'do not compare it with finished periods or call it a drop.');
      }
    }
    var modes = RS.metricTotalModes(def), labels = RS.metricLabelsFor(def), metricIdx = (def.columns || []).length;
    modes.forEach(function (m, i) {
      if (m !== 'latest') return;
      out.push('"' + labels[i] + '" is a point-in-time level: never sum it across periods; its total is the latest value.');
      if (rows.some(function (r) { return r[metricIdx + i] == null; })) {
        out.push('Empty "' + labels[i] + '" cells are periods with no snapshot (no measurement), not zero.');
      }
    });
    return out.join(' ');
  }

  // Level metrics (backlog): tell the server which measures must be headlined
  // by their latest value, not a sum over buckets (caption_facts.build_facts).
  function captionLevelFields(def) {
    var labels = RS.metricLabelsFor(def);
    return RS.metricTotalModes(def).map(function (m, i) { return m === 'latest' ? labels[i] : null; })
      .filter(Boolean);
  }

  // "Ask Eddard about this report": the button lives beside the insight card
  // and only exists for a reporting.ai.use holder. null hides it and detaches
  // the report from the chat; a report shows it and pre-attaches, so opening
  // the chat by the header button is grounded too.
  function setAskEddard(report) {
    var btn = RS.el('rsAskEddard');
    if (window.ReportingChat && ReportingChat.setReport) ReportingChat.setReport(report);
    if (!btn) return;
    btn.hidden = !report;
    if (report && !btn._wired) {
      btn._wired = true;
      btn.addEventListener('click', function () {
        if (window.ReportingChat) ReportingChat.askAbout(RS.state.askEddardReport);
      });
    }
    RS.state.askEddardReport = report;
  }

  function fireCaption(boxId, columns, rows, title, dateLabel, notes, levelFields) {
    var box = RS.el(boxId);
    if (!box) return;
    var seq = ++captionSeq;
    box.hidden = false;
    box.classList.add('rp-caption--loading');
    box.textContent = '';
    fetch(API_PREFIX + 'api/reporting/ai/caption', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({
        // The WHOLE grid (payload-capped): the server reduces it to a fact
        // sheet, so the model no longer judges from the first 50 rows.
        columns: columns, rows: rows.slice(0, 5000),
        title: title || undefined, dateLabel: dateLabel || undefined,
        notes: notes || undefined,
        levelFields: (levelFields && levelFields.length) ? levelFields : undefined
      })
    }).then(function (res) {
      if (!res.ok) throw new Error('caption http ' + res.status);
      return res.json();
    }).then(function (data) {
      if (seq !== captionSeq) return;   // a newer run superseded this one
      if (!data || !data.caption) { box.hidden = true; box.classList.remove('rp-caption--loading'); return; }
      box.classList.remove('rp-caption--loading');
      var chip = document.createElement('span');
      chip.className = 'rp-caption-chip';
      chip.textContent = RS.I18N.aiChip;
      box.appendChild(chip);
      box.appendChild(document.createTextNode(' ' + data.caption));
    }).catch(function () {
      if (seq !== captionSeq) return;
      box.hidden = true;
      box.classList.remove('rp-caption--loading');
    });
  }

  // Monotonic run token: a newer runCurrent invalidates every pending older
  // one, so a slow report's late responses can't render under a newer
  // report's title (and a double-click renders only once).
  var runSeq = 0;
  var fallbackToastFor = {};

  async function runCurrent() {
    var cur = RS.state.current;
    var seq = ++runSeq;
    RS.setHeaderActionsEnabled(false);
    // A new run supersedes any open drill drawer — it shows rows behind the
    // PREVIOUS result and would sit stale over the new one (e.g. after a
    // chip edit).
    if (window.ReportingDrill) ReportingDrill.close();
    // Fire-and-forget: not every runCurrent() caller already awaits
    // loadSourcesCatalog() first, so warm it here too for the drill
    // affordance (openDrill/renderTable read RS.state.sources). Idempotent — a
    // cache hit resolves immediately, and drill just stays unavailable until
    // this settles on a cold session.
    RS.loadSourcesCatalog().then(function () {
      // Chip labels resolve field keys against the catalog — re-render once it
      // lands (the first paint may fall back to raw keys on a cold session).
      // The seq guard keeps a stale resolve from repainting a newer result.
      // The editor guard keeps a slow resolve from wiping an open chip editor
      // mid-edit (rs-chip-apply vanished between fill and click on slow CI);
      // labels catch up on the next runCurrent() repaint anyway.
      var wrap = RS.el('rsChips');
      if (seq === runSeq && RS.state.current === cur
          && !(wrap && wrap.querySelector('.rs-chip-editor'))) RS.renderAiChips(cur);
    });
    setView('result');
    RS.el('rsError').hidden = true;
    RS.renderErrorOpenAdvanced(false);
    toggleMoreMenu(false);
    RS.el('rsMsg').hidden = true;
    RS.el('rsResultTitle').textContent = cur.name || cur.def.title || '';
    RS.el('rsCrumbName').textContent = cur.name || cur.def.title || '';
    RS.el('rsSavedChip').hidden = !cur.reportId;
    RS.applyTitleStyle();
    RS.el('rsDeleteReport').hidden = !(cur.owned && cur.reportId);
    RS.el('rsSaveCopy').hidden = !cur.reportId;
    saveAsCopy = false;
    RS.renderAiChips(cur);
    var adjustBtn = RS.el('rsAdjustWizard');
    if (adjustBtn) {
      adjustBtn.hidden = cur.builtBy !== 'wizard' && !RS.wizardStateFromDefinition(cur.def);
    }
    RS.el('rsSaveName').hidden = true;
    RS.setGrandTotals(null);
    RS.el('rsChartCard').hidden = true;
    RS.el('rsTableCard').hidden = true;
    RS.el('rsTableToggle').hidden = true;
    RS.el('rsTableWrap').hidden = true;
    RS.el('rsRunLoading').innerHTML = resultSkeletonHtml();
    RS.el('rsRunLoading').hidden = false;
    RS.el('rsDrillHint').hidden = true;
    RS.el('rsKpiBand').hidden = true;
    setAskEddard(null);
    // A prior run's caption sentence must never linger over the new run's
    // (still-loading, possibly failed or empty) result — hidden here just
    // like every other result element above, cleared again by fireCaption()
    // once (and if) the new run actually succeeds. Guarded: the box only
    // exists in the DOM for a reporting.ai.explain.use holder.
    var rsCaptionBox = RS.el('rsCaption');
    if (rsCaptionBox) { rsCaptionBox.hidden = true; rsCaptionBox.textContent = ''; }
    var anomCard = RS.el('rsAnomCard');
    if (anomCard) { anomCard.hidden = true; }

    var def = cur.def;
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;
    var dims = (def.columns || []).length;
    // Console chart-card title: what is plotted (the metric labels), not the
    // report name — that one is already in the result header.
    var chartTitle = RS.el('rsChartTitle');
    if (chartTitle) {
      chartTitle.textContent = hasMetrics
        ? RS.metricLabelsFor(def).join(' · ') : (cur.name || def.title || '');
    }
    // Timing badge: measures the full round-trip (both the optional grand-total
    // call below and the main run), from just before the first request fires
    // to the moment the main run's response lands.
    var runT0 = performance.now();

    // Grand total via a zero-column clone: correct for every aggregation
    // (avg/count_distinct included), unlike a client-side sum of grouped rows.
    // Skipped for zero-dim definitions — there the main run IS the total.
    if (hasMetrics && dims) {
      var totalDef = JSON.parse(JSON.stringify(def));
      totalDef.columns = [];
      totalDef.sort = [];
      delete totalDef.forecast;
      // No compare: true here -- this run only feeds the band's total cards,
      // which never read a comparison payload. The breakdown def below is the
      // one whose comparison drives renderKpiBand's delta chips; asking
      // the backend to also diff THIS zero-column clone's own prior period
      // would be a fully wasted extra query.
      var t = await RS.api('/api/reporting/run', { method: 'POST', body: JSON.stringify(totalDef) });
      if (seq !== runSeq) return;
      if (t.ok && t.data && t.data.rows && t.data.rows.length) {
        RS.setGrandTotals(t.data.rows[0]);
      }
    }

    // Breakdown run (or the plain grid run for non-metric definitions).
    // compare: true is added to a shallow copy of the posted body only --
    // `def` (== cur.def) must stay exactly what the wizard/library built,
    // since it's reused for Save/Adjust-in-wizard/export.
    var res = await RS.api('/api/reporting/run', {
      method: 'POST',
      body: JSON.stringify(Object.assign({}, def, { compare: true }))
    });
    if (seq !== runSeq) return;
    // Hide only after the staleness guard: a slow stale response must never
    // hide the indicator a newer run just showed.
    RS.el('rsRunLoading').hidden = true;
    if (!res.ok) {
      RS.showResultError(RS.friendlyRunError(res.status, res.data),
        { title: cur.name || cur.def.title || '', openAdvanced: true });
      // The toggle must not keep showing the PREVIOUS successful run's
      // forecast-eligible/charted state once this run has errored out.
      syncForecastCtl(def, null, false);
      return;
    }
    RS.setHeaderActionsEnabled(true);
    RS.el('rsTableCard').hidden = false;
    RS.showTiming(res.data.rowCount, performance.now() - runT0);
    RS.state.current.sql = res.data.sql || null;
    RS.state.current.sqlPretty = res.data.sqlPretty || null;
    RS.state.current.sqlDisplay = res.data.sqlDisplay || null;
    RS.state.current.params = res.data.params || [];
    // Console: the Query card sits in the result's side column and is always
    // visible when the run produced SQL — no reveal toggle anymore.
    RS.el('rsSqlView').hidden = !RS.state.current.sql;
    if (RS.state.current.sql) {
      ReportingSqlFormat.render(RS.el('rsSqlText'), ReportingSqlFormat.displayText(RS.state.current));
    }
    RS.el('rsShowSql').hidden = !RS.state.current.sql;
    RS.el('rsShowSql').textContent = RS.I18N.showQuery;
    var peek = RS.el('rsSqlPeek');
    if (RS.state.current.sqlDisplay) {
      peek.textContent = RS.state.current.sqlDisplay.split('\n')[0] + '…';
      peek.hidden = false;
    } else {
      peek.hidden = true;
    }
    var columns = res.data.columns || [], rows = res.data.rows || [];
    rows = RS.zeroFillDateBuckets(def, rows, res.data.resolvedDates || []);
    // A zero-dim run's single row is itself the per-metric grand total.
    if (hasMetrics && !dims && rows.length) RS.setGrandTotals(rows[0]);
    RS.renderKpiBand(dims, rows, res.data.comparison || null, def, columns);
    var rdates = res.data.resolvedDates || [];
    // Hoisted out of the `if` below (Task 13): fireCaption() at the end of
    // this function needs the same resolved-dates label the message line
    // shows, or null when there's nothing to resolve.
    var resolvedTxt = null;
    if (rdates.length) {
      resolvedTxt = rdates.map(function (d) {
        return RS.tokenLabel(d) + ' (' + d.start + ' → ' + d.end + ')';
      }).join(' · ');
      var msg = RS.el('rsMsg');
      msg.textContent = msg.hidden || !msg.textContent
        ? resolvedTxt : msg.textContent + ' — ' + resolvedTxt;
      msg.hidden = false;
    }
    if (res.data.truncated && res.data.rowCount) {
      var tNote = RS.el('rsMsg');
      var tTxt = RS.I18N.truncatedNote.replace('{n}', String(res.data.rowCount));
      tNote.textContent = (!tNote.hidden && tNote.textContent)
        ? tNote.textContent + ' — ' + tTxt : tTxt;
      tNote.hidden = false;
    }
    if (hasMetrics && !dims && rows.length) {
      var totMsg = RS.el('rsMsg');
      totMsg.textContent = (!totMsg.hidden && totMsg.textContent)
        ? totMsg.textContent + ' — ' + RS.I18N.noChartTotalOnly : RS.I18N.noChartTotalOnly;
      totMsg.hidden = false;
    }
    if (!rows.length) {
      RS.el('rsTableWrap').innerHTML =
        '<div class="nx-empty"><div class="nx-empty__art"><i class="fas fa-inbox" aria-hidden="true"></i></div>' +
        '<p class="nx-empty__title">' + RS.esc(RS.I18N.noData) + '</p>' +
        '<p class="nx-empty__hint">' + RS.esc(RS.I18N.noDataHint) + '</p></div>';
      RS.el('rsTableWrap').hidden = false;
      syncForecastCtl(def, null, false);
      return;
    }
    // zeroFillDateBuckets pads `rows` out to the FILTER's display range (e.g.
    // "This year" -> Jan-Dec), but compute_forecast anchors its forecast
    // buckets at the last REAL data bucket (forecast.anchor). For any
    // current-period token whose data doesn't reach the end of the period,
    // the zero-fill above already produced trailing zero rows for the same
    // calendar buckets the forecast is about to append -- duplicate rows/
    // labels, and the dashed line would bridge from a fake zero instead of
    // the last real point. Trim those fabricated trailing buckets back to
    // the anchor before rows reaches either consumer below (mountChart,
    // renderTable) so both see the same, correctly-truncated set.
    var fcForTrim = res.data.forecast || null;
    if (fcForTrim && !fcForTrim.unavailable && fcForTrim.anchor) {
      rows = rows.filter(function (r) {
        return String(r[0] == null ? '' : r[0]).slice(0, 10) <= fcForTrim.anchor;
      });
    }
    // Kept so switching the forecast OFF can re-render from this result
    // without another (slow, lookback-widened) server run.
    RS.state.lastRun = { def: def, columns: columns, rows: rows, hasMetrics: hasMetrics,
                      dims: dims, forecast: res.data.forecast || null };
    setAskEddard({ title: cur.name || def.title || '', definition: def,
                   columns: columns, rows: rows.slice(0, 5000),
                   forecast: res.data.forecast || null });
    // Report definition (layout): render the tile grid instead of band+chart+table.
    var lgrid = RS.el('rsLayoutGrid');
    if (res.data.layoutFallback && !fallbackToastFor[cur.reportId || 'new']) {
      fallbackToastFor[cur.reportId || 'new'] = true;
      window.NX.toast(RS.I18N.layoutFallback, 'warning');
    }
    if (res.data.layout && window.ReportingLayoutView) {
      lgrid.hidden = false;
      lgrid.innerHTML = (res.data.layout.tiles || []).map(function (t) {
        return '<div class="rdb-card rl-tile" data-card-id="' + RS.esc(t.id) + '" data-type="' + t.type + '" ' +
          'style="' + window.ReportingGrid.geomStyle(t.span, t.rows) + '" data-testid="rs-layout-tile">' +
          '<div class="rdb-card-body" data-tile-body></div></div>';
      }).join('');
      window.ReportingLayoutView.render(lgrid, { layout: res.data.layout, def: def, columns: columns, rows: rows,
        derived: res.data.derived || {}, i18n: window.NX_I18N_REPORTING_LAYOUTS });
      RS.el('rsKpiBand').hidden = true;   // the band host renderKpiBand writes into
      RS.el('rsChartCard').hidden = true;
      RS.el('rsTableCard').hidden = true;
      RS.el('rsTableToggle').hidden = true;
      RS.state.lastRun = { def: def, columns: columns, rows: rows, hasMetrics: hasMetrics, dims: dims,
                           forecast: null, layout: res.data.layout, derived: res.data.derived || {} };
      writePreviewCache(dims, hasMetrics, rows);
      return;
    }
    lgrid.hidden = true;
    if (window.ReportingLayoutView) window.ReportingLayoutView.destroy(lgrid);
    var charted = (hasMetrics && dims)
      ? !!RS.mountChart(def, columns, rows, res.data.forecast || null) : false;
    syncForecastCtl(def, res.data.forecast || null, charted);
    RS.renderTable(columns, rows, res.data.forecast || null);
    RS.renderAnomalies(def, columns, rows);
    // The table always shows -- the numbers behind a chart are the point,
    // not a footnote. The toggle only appears when a chart (or a
    // dimensionless stat card) sits above it, so there is something else
    // to look at once the table is hidden.
    RS.el('rsTableWrap').hidden = false;
    RS.el('rsTableToggle').hidden = !(hasMetrics && (charted || !dims));
    RS.el('rsTableToggle').textContent = RS.I18N.hideTable;
    writePreviewCache(dims, hasMetrics, rows);
    // Task 13: auto AI caption over the result that just rendered. Placed
    // after the `!rows.length` early return above, so an empty result never
    // fires one (nothing to caption).
    fireCaption('rsCaption', columns, rows, cur.name || cur.def.title || '', resolvedTxt,
      captionNotes(def, rows), captionLevelFields(def));
  }
  RS.runCurrent = runCurrent;

  // Step 5 — refresh the library card's preview thumbnail from the result
  // that's actually on screen. Only for a SAVED report (RS.state.current.reportId
  // set) — an unsaved ad-hoc result has no card to feed. Wrapped in try/catch:
  // a localStorage quota error (or a browser with storage disabled) must
  // never break a run.
  function writePreviewCache(dims, hasMetrics, rows) {
    var reportId = RS.state.current && RS.state.current.reportId;
    if (!reportId) return;
    try {
      var payload;
      if (hasMetrics && !dims && rows.length) {
        payload = { t: 'total', v: Number(rows[0][0]) || 0, ts: Date.now() };
      } else if (hasMetrics && dims && RS.state.chartData) {
        var series = (RS.state.chartData.datasets[0] || {}).data || [];
        payload = {
          t: RS.state.chartData.type === 'line' ? 'line' : 'bar',
          v: series.slice(0, 16),
          ts: Date.now()
        };
      } else {
        return;
      }
      localStorage.setItem('nx.reporting.preview.' + reportId, JSON.stringify(payload));
    } catch (e) { /* quota or storage disabled — never break a run */ }
  }

  RS.el('rsTableToggle').addEventListener('click', function () {
    var w = RS.el('rsTableWrap');
    w.hidden = !w.hidden;
    RS.el('rsTableToggle').textContent = w.hidden ? RS.I18N.showTable : RS.I18N.hideTable;
  });

  RS.el('rsChartTools').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-type]');
    if (!btn || !RS.state.chartData) return;
    // 'stacked' is a UI-only virtual type; don't persist it as a chartType since
    // it maps to 'bar' with stacked scales and is not a valid Chart.js type.
    if (RS.state.current && RS.state.current.def && btn.dataset.type !== 'stacked') {
      RS.state.current.def.chartType = btn.dataset.type;
    }
    RS.renderChart(btn.dataset.type);
  });

  function forecastEligible(def) {
    var cols = (def && def.columns) || [];
    return cols.length === 1 && !!cols[0].grain &&
      Array.isArray(def.metrics) && def.metrics.length > 0;
  }
  RS.forecastEligible = forecastEligible;
  function syncForecastCtl(def, forecast, charted) {
    var btn = RS.el('rsForecastToggle'), sel = RS.el('rsForecastHorizon');
    if (!btn) return;
    var eligible = forecastEligible(def);
    // Mirrors Advanced's syncForecastCtl (_reporting_js.html): a saved/shared
    // definition must never persist a stale forecast block once the shape
    // (e.g. a second breakdown added, or the date grain removed) makes it
    // permanently unavailable.
    if (!eligible) delete def.forecast;
    var on = eligible && !!(def.forecast && def.forecast.enabled);
    btn.disabled = !eligible;
    btn.title = eligible ? RS.I18N.forecastLabel : RS.I18N.forecastNeedsShape;
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.classList.toggle('is-selected', on);
    sel.hidden = !on;
    if (on && def.forecast.horizon) sel.value = String(def.forecast.horizon);
    // Only disclose forecast state via the shared #rsChartNote when a chart
    // actually mounted. When mountChart bailed (too many points, no Chart.js,
    // three breakdowns) it already wrote a more important note via
    // chartCardNote(...) — clobbering that here would silently destroy it,
    // and there's nothing forecast-related to disclaim if there's no chart.
    if (charted && on && forecast && forecast.unavailable) {
      RS.appendChartNote(RS.I18N.forecastUnavailable);
    } else if (charted && on) {
      RS.appendChartNote(RS.I18N.forecastNote);
    }
  }
  RS.el('rsForecastToggle').addEventListener('click', function () {
    var cur = RS.state.current;
    if (!cur || !cur.def || this.disabled) return;
    if (cur.def.forecast && cur.def.forecast.enabled) {
      delete cur.def.forecast;
      // Off = drop the forecast block from the last result and repaint; the
      // rows are already on hand, no need to hit the server again.
      var lr = RS.state.lastRun;
      if (lr && lr.def === cur.def) {
        var charted = (lr.hasMetrics && lr.dims) ? !!RS.mountChart(cur.def, lr.columns, lr.rows, null) : false;
        syncForecastCtl(cur.def, null, charted);
        RS.renderTable(lr.columns, lr.rows, null);
        return;
      }
    } else {
      var h = RS.el('rsForecastHorizon').value;
      cur.def.forecast = { enabled: true, horizon: h === 'auto' ? 'auto' : parseInt(h, 10) };
    }
    runCurrent();
  });
  RS.el('rsForecastHorizon').addEventListener('change', function () {
    var cur = RS.state.current;
    if (!cur || !cur.def || !cur.def.forecast) return;
    var h = this.value;
    cur.def.forecast.horizon = h === 'auto' ? 'auto' : parseInt(h, 10);
    runCurrent();
  });

  // The rail's breakdown summary names the grain — keep it live.
  RS.el('rsGrain').addEventListener('change', RS.renderWizardRail);

  // ----- Colours & axes popover -----
  // Client-side only: edits def.style and re-renders the mounted chart (no
  // re-run); Save persists it with the report like chartType/forecast.
  function toggleStylePop(open) {
    var pop = RS.el('rsStylePop'), btn = RS.el('rsStyleToggle');
    if (!pop || !btn) return;
    pop.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.setAttribute('aria-pressed', open ? 'true' : 'false');
    btn.classList.toggle('is-selected', open);
    if (open) syncStyleCtl();
  }
  RS.toggleStylePop = toggleStylePop;
  function defaultSeriesColor(d, i) {
    var single = d.datasets.length === 1 && !d.multiSeries;
    var c = single ? (document.documentElement.classList.contains('dark') ? '#818cf8' : '#312e81')
                   : d.datasets[i].borderColor;
    return /^#[0-9a-f]{6}$/i.test(c || '') ? c : '#4f46e5';
  }
  function syncStyleCtl() {
    var d = RS.state.chartData;
    if (!d) return;
    var style = RS.styleOf(), colors = style.colors || {};
    var multi = !!d.multiSeries;
    var circular = RS.state.chartType === 'pie' || RS.state.chartType === 'doughnut';
    var rightKeys = circular ? [] : RS.rightAxisKeys(d, style);
    var html = '';
    d.datasets.forEach(function (ds, i) {
      var key = RS.seriesKey(ds, multi);
      var onRight = rightKeys.indexOf(key) >= 0;
      html += '<div class="rs-style-row" data-key="' + RS.esc(key) + '">' +
        '<input type="color" value="' + RS.esc(colors[key] || defaultSeriesColor(d, i)) +
        '" aria-label="' + RS.esc(ds.label) + '" data-testid="rs-style-color">' +
        '<span>' + RS.esc(ds.label) + '</span>' +
        (!circular && d.datasets.length > 1
          ? '<span class="rs-axis-seg" role="group">' +
            '<button type="button" class="rs-axis-btn" data-axis="left" aria-pressed="' + (!onRight) +
            '" title="' + RS.esc(RS.I18N.styleLeftAxis) + '" data-testid="rs-style-axis-left">' + RS.esc(RS.I18N.axisShortLeft) + '</button>' +
            '<button type="button" class="rs-axis-btn" data-axis="right" aria-pressed="' + onRight +
            '" title="' + RS.esc(RS.I18N.styleRightAxis) + '" data-testid="rs-style-axis-right">' + RS.esc(RS.I18N.axisShortRight) + '</button>' +
            '</span>'
          : '') +
        '</div>';
    });
    RS.el('rsStyleRows').innerHTML = html;
    RS.el('rsStyleTitleColor').value = style.titleColor ||
      RS.rgbToHex(getComputedStyle(RS.el('rsResultTitle')).color);
  }
  // Colour inputs fire `input` continuously while dragging the picker —
  // coalesce to one chart rebuild per frame.
  var styleRaf = 0;
  function rerenderStyled() {
    if (styleRaf) return;
    styleRaf = requestAnimationFrame(function () {
      styleRaf = 0;
      if (RS.state.chartData) RS.renderChart(RS.state.chartType || RS.state.chartData.type);
      RS.applyTitleStyle();
    });
  }
  RS.el('rsStyleToggle').addEventListener('click', function () {
    toggleStylePop(RS.el('rsStylePop').hidden);
  });
  RS.el('rsStyleRows').addEventListener('input', function (e) {
    var cur = RS.state.current, d = RS.state.chartData;
    if (!cur || !cur.def || !d || e.target.type !== 'color') return;
    var row = e.target.closest('.rs-style-row');
    if (!row) return;
    var style = RS.ensureStyle();
    style.colors = style.colors || {};
    style.colors[row.dataset.key] = e.target.value;
    rerenderStyled();
  });
  RS.el('rsStyleRows').addEventListener('click', function (e) {
    var btn = e.target.closest('.rs-axis-btn');
    var cur = RS.state.current, d = RS.state.chartData;
    if (!btn || !cur || !cur.def || !d) return;
    var key = btn.closest('.rs-style-row').dataset.key, style = RS.ensureStyle();
    // Materialise the defaults first so moving a default right-axis series
    // (backlog) back to the left is remembered as an explicit choice.
    var keys = RS.rightAxisKeys(d, style).slice();
    var at = keys.indexOf(key);
    if (btn.dataset.axis === 'right' && at < 0) keys.push(key);
    if (btn.dataset.axis === 'left' && at >= 0) keys.splice(at, 1);
    style.rightAxis = keys;
    rerenderStyled();
    syncStyleCtl();
  });
  RS.el('rsStyleTitleColor').addEventListener('input', function () {
    var cur = RS.state.current;
    if (!cur || !cur.def) return;
    RS.ensureStyle().titleColor = this.value;
    rerenderStyled();
  });
  RS.el('rsStyleReset').addEventListener('click', function () {
    var cur = RS.state.current;
    if (!cur || !cur.def) return;
    delete cur.def.style;
    rerenderStyled();
    syncStyleCtl();
  });

  RS.el('rsShowSql').addEventListener('click', function () {
    // Console: the Query card is already visible in the side column — this
    // menu item just makes sure it's rendered and brings it into view.
    var cur = RS.state.current;
    if (!cur || !cur.sql) return;
    var view = RS.el('rsSqlView');
    view.hidden = false;
    // sqlDisplay = pretty SQL with the parameter literals inlined
    // server-side (display + copy only; execution stays parameterized).
    ReportingSqlFormat.render(RS.el('rsSqlText'), ReportingSqlFormat.displayText(cur));
    view.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  RS.el('rsSqlPeek').addEventListener('click', function () {
    // Same reveal path as the Show-query button — no duplicated panel-fill
    // logic (L9): the peek footer just delegates the click.
    RS.el('rsShowSql').click();
  });
  RS.el('rsSqlCopy').addEventListener('click', function () {
    var cur = RS.state.current;
    if (!cur || !cur.sql) return;
    var text = ReportingSqlFormat.copyText(cur);
    var btn = this;
    navigator.clipboard.writeText(text).then(function () {
      var prev = btn.textContent;
      btn.textContent = RS.I18N.copied;
      setTimeout(function () { btn.textContent = prev; }, 1200);
    }).catch(function () { /* clipboard unavailable (non-HTTPS / unfocused) */ });
  });

  // Reveal the inline rename/save-name input (the pencil, "Save as copy", and
  // Save on a not-yet-saved result all land here).
  function revealSaveNameInput(value) {
    if (!RS.state.current) return;  // error view without a loaded report
    var nameInput = RS.el('rsSaveName');
    nameInput.hidden = false;
    nameInput.value = value || RS.state.current.name || RS.state.current.def.title || '';
    nameInput.focus();
    nameInput.select();
  }

  // True once the result IS a stored report the user may write back to: an
  // owner, or a colleague holding a CanEdit share (the same pair the PUT
  // endpoint accepts).
  function canUpdateCurrent() {
    var cur = RS.state.current;
    return !!(cur && cur.reportId && (cur.owned || cur.canEdit));
  }

  // Armed by "Save as copy" so the next save creates a row instead of writing
  // back; cleared on every render (runCurrent) and after each save.
  var saveAsCopy = false;

  // PUT when we're writing back to the open report, POST when we're making a
  // new one. Renaming is the same call with a different name -- that is what
  // stops the pencil from spawning a duplicate under the new name.
  async function persistCurrent(name) {
    var cur = RS.state.current;
    var update = !saveAsCopy && canUpdateCurrent();
    var res = update
      ? await RS.api('/api/reporting/reports/' + cur.reportId, {
          method: 'PUT', body: JSON.stringify({ name: name, definition: cur.def })
        })
      : await RS.api('/api/reporting/reports', {
          method: 'POST', body: JSON.stringify({ name: name, definition: cur.def })
        });
    if (!res.ok) {
      RS.el('rsError').textContent = (res.data && res.data.error) || RS.I18N.couldNotSave;
      RS.el('rsError').hidden = false;
      return;
    }
    cur.name = name;
    if (!update) {
      // The copy (or the first save) is now the open report -- otherwise the
      // next Save would write back to the original it was copied from.
      cur.reportId = (res.data && res.data.id) || null;
      cur.owned = true;
      cur.canEdit = true;
    }
    saveAsCopy = false;
    RS.el('rsSaveName').hidden = true;
    RS.el('rsResultTitle').textContent = name;
    RS.el('rsCrumbName').textContent = name;
    RS.el('rsSavedChip').hidden = !cur.reportId;
    RS.el('rsDeleteReport').hidden = !(cur.owned && cur.reportId);
    RS.el('rsSaveCopy').hidden = !cur.reportId;
    RS.el('rsError').hidden = true;
    RS.el('rsMsg').textContent = update ? RS.I18N.savedChanges : RS.I18N.savedToMine;
    RS.el('rsMsg').hidden = false;
    RS.loadLibrary();
  }

  RS.el('rsRenamePencil').addEventListener('click', function () { revealSaveNameInput(); });

  RS.el('rsSave').addEventListener('click', function () {
    if (!RS.state.current) return;  // error view without a loaded report
    var nameInput = RS.el('rsSaveName');
    if (!nameInput.hidden) {          // naming a new report, or renaming this one
      var typed = nameInput.value.trim();
      if (typed) persistCurrent(typed);
      return;
    }
    // A saved report keeps its name and takes the edit; anything else has to
    // be named first.
    if (canUpdateCurrent()) persistCurrent(RS.state.current.name || RS.state.current.def.title || '');
    else revealSaveNameInput();
  });

  RS.el('rsSaveName').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); RS.el('rsSave').click(); }
    else if (e.key === 'Escape') { this.hidden = true; saveAsCopy = false; RS.el('rsSave').focus(); }
  });

  RS.el('rsSaveCopy').addEventListener('click', function () {
    if (!RS.state.current) return;
    saveAsCopy = true;
    toggleMoreMenu(false);
    revealSaveNameInput(RS.I18N.copyOf.replace('{name}', RS.state.current.name || RS.state.current.def.title || ''));
  });

  // Open in Advanced. id:null for non-owned reports is LOAD-BEARING: CanEdit
  // shares mutate shared reports in place; a null id makes Advanced's Save
  // default to create-a-copy.
  RS.el('rsAdjustWizard').addEventListener('click', RS.adjustInWizard);

  // ⋯ overflow menu: toggle on the button, close on Escape or an outside
  // click — same idiom as the Advanced tab's process-scope dropdown
  // (rpScopeBtn/#rpScopeWrap wiring at the bottom of _reporting_js.html).
  var rsMoreBtn = RS.el('rsMore');
  if (rsMoreBtn) {
    rsMoreBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMoreMenu(); });
    document.addEventListener('click', function (e) {
      var wrap = RS.el('rsMoreWrap');
      if (wrap && !wrap.contains(e.target)) toggleMoreMenu(false);
    });
    RS.el('rsMoreWrap').addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { toggleMoreMenu(false); rsMoreBtn.focus(); }
    });
  }

  RS.el('rsDeleteReport').addEventListener('click', function () {
    var cur = RS.state.current;
    if (!cur || !cur.reportId) return;
    RS.deleteReport(cur.reportId, cur.name || cur.def.title);
  });

  RS.el('rsOpenAdvanced').addEventListener('click', function () {
    var cur = RS.state.current;
    if (!cur || !window.Reporting || !window.Reporting.applyDefinition) return;
    var id = (cur.owned && cur.canEdit) ? cur.reportId : null;
    window.Reporting.applyDefinition(cur.def, cur.name || cur.def.title, id);
    // Run before switching tabs: run() flips the Advanced pane straight into
    // its loading state, so the tab lands already-loading instead of
    // flashing the empty "Build a report to see results" placeholder first.
    if (window.Reporting.run) window.Reporting.run();
    window.ReportingTabs.show('advanced');
  });

  function chartPngDataUrl() {
    if (!RS.state.chart) return null;
    var src = RS.el('rsChartCanvas');
    var c = document.createElement('canvas');
    c.width = src.width; c.height = src.height;
    var ctx = c.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(src, 0, 0);
    return c.toDataURL('image/png');
  }

  RS.el('rsChartPng').addEventListener('click', function () {
    var url = chartPngDataUrl();
    if (!url) return;
    var a = document.createElement('a');
    a.href = url;
    a.download = ((RS.state.current && RS.state.current.name) || 'report') + '-chart.png';
    a.click();
  });

  if (EXPORT_ALLOWED) {
    RS.el('rsExport').addEventListener('click', async function () {
      if (!RS.state.current) return;  // error view without a loaded report
      var fmtSel = RS.el('rsExportFormat');
      var fmt = (fmtSel && fmtSel.value === 'csv') ? 'csv' : 'xlsx';
      var body = Object.assign({}, RS.state.current.def, { format: fmt });
      var png = fmt === 'xlsx' ? chartPngDataUrl() : null;
      if (png) body.chartImage = png;
      var res;
      try {
        res = await fetch(API_PREFIX + 'api/reporting/export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
          body: JSON.stringify(body)
        });
      } catch (e) { res = { ok: false }; }
      if (!res.ok) {
        RS.el('rsError').textContent = RS.I18N.couldNotExport;
        RS.el('rsError').hidden = false;
        return;
      }
      var blob = await res.blob();
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (RS.state.current.name || 'report') + '.' + fmt;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  // ---------- init ----------
  function initOnce() {
    if (RS.state.loaded) return;
    RS.state.loaded = true;
    RS.loadMetricsCatalog();
    RS.loadLibrary();
    syncLayoutToggle();
  }

  RS.el('rsSearch').addEventListener('input', RS.renderLibrary);
  RS.el('rsSort').addEventListener('change', function () {
    RS.state.sort = this.value === 'name' ? 'name' : 'updated';
    RS.renderLibrary();
  });
  function syncLayoutToggle() {
    RS.el('rsLayout2').classList.toggle('is-active', RS.state.layout === '2');
    RS.el('rsLayout4').classList.toggle('is-active', RS.state.layout === '4');
  }
  function setLayout(n) {
    RS.state.layout = n;
    try { localStorage.setItem('nx.reporting.layout', n); } catch (e) {}
    syncLayoutToggle();
    RS.renderLibrary();
  }
  RS.el('rsLayout2').addEventListener('click', function () { setLayout('2'); });
  RS.el('rsLayout4').addEventListener('click', function () { setLayout('4'); });
  function exitToLibrary() { setView('library'); RS.loadLibrary(); }

  // Back on a result returns to the result's origin: a wizard-built (or
  // wizard-reopened) result goes back into the wizard adjustment; a
  // library-opened or Ask-AI result goes back to the library. The X is
  // always the explicit way out to the library, regardless of origin.
  RS.el('rsBack').addEventListener('click', function () {
    var cur = RS.state.current;
    if (cur && cur.origin === 'wizard') { RS.adjustInWizard(); return; }
    exitToLibrary();
  });
  RS.el('rsExit').addEventListener('click', exitToLibrary);
  RS.el('rsWizardClose').addEventListener('click', exitToLibrary);
  RS.el('rsWizardClose2').addEventListener('click', exitToLibrary);

  // The dashboard builder module is self-contained and never calls setView
  // itself -- it announces intent via a custom event instead of reaching
  // into this module's functions (D3).
  document.addEventListener('rs:dashboard-closed', exitToLibrary);

  RS.el('rsRunAgain').addEventListener('click', function () {
    if (RS.state.current) runCurrent();
  });

  // Result builders shared with the dashboard's whole-report card
  // (_reporting_dashboard_js.html renderReportCard). Everything here is
  // DOM-free except ensureCatalogs (network) and chartConfigFor's one read
  // of document.documentElement.classList for dark mode; none of it touches
  // the Simple pane's own elements, so a card can call them while #rsResult
  // is hidden.
  window.ReportingSimple = {
    openDefinition: RS.openDefinition,
    navTo: navTo,
    ensureCatalogs: RS.ensureCatalogs,
    fmtNumber: RS.fmtNumber,
    zeroFillDateBuckets: RS.zeroFillDateBuckets,
    kpiBandHtml: RS.kpiBandHtml,
    buildChartData: RS.buildChartData,
    chartConfigFor: RS.chartConfigFor,
    tableHtml: RS.tableHtml,
    // Per-card chart tools on the dashboard reuse the Results tab's rules.
    forecastEligible: RS.forecastEligible,
    seriesKey: RS.seriesKey,
    rightAxisKeys: RS.rightAxisKeys,
    defaultSeriesColor: defaultSeriesColor
  };

  document.addEventListener('rp:tabshown', function (e) {
    if (e.detail.tab === 'simple') initOnce();
  });
  if (window.ReportingTabs && window.ReportingTabs.current() === 'simple') initOnce();
}());
