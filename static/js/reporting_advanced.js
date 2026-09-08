// Behaviour for templates/js/_reporting_js.html (#191 shim-ification): the
// Advanced tab's query builder, SQL sandbox, sharing and scheduling. Jinja-
// rendered strings ride in via window.NX_I18N_REPORTING_ADVANCED (built by
// the paired shim) instead of being inlined here.
(function () {
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const API_PREFIX = window.API_PREFIX;
  var I18N = window.NX_I18N_REPORTING_ADVANCED;
  const state = {
    source: null, fields: [], columns: [], filters: [], sort: [],
    // Process scope. `allProcesses` is the caller's allowed '<client>.<process>'
    // list for the current source (the pickable set); `selProcesses` is the
    // selected subset. Serialised to scope.clients/processes by buildScope().
    allProcesses: [], selProcesses: [],
    mode: 'table', sqlSource: null, sqlSources: [], sourcesById: {},
    lastResult: null, lastDef: null, view: 'grid', currentReportId: null, currentReportName: null,
    currentReportOwned: true, currentReportCanEdit: true,
    // Semantic metrics: cached full map {sourceId: [{code,label,...}]} (null until
    // fetched), the per-source available list, and the selected metric codes.
    metricsBySource: null, availableMetrics: [], metrics: [],
    // Forecast toggle state: {enabled: true, horizon: 'auto'|number} or null.
    // Mirrors the Simple tab's shape (see def.forecast in _reporting_simple_js.html)
    // so buildDefinition()/applyDefinition() can pass it through verbatim.
    forecast: null
  };

  // Relative-date token presets for date-typed filter fields. Token shape
  // {token: '<name>'[, n]} matches nx_lib/reporting/tokens.py.
  var DATE_TOKEN_PRESETS = [
    ['today', I18N.today],
    ['yesterday', I18N.yesterday],
    ['this_week', I18N.thisWeek],
    ['last_week', I18N.lastWeek],
    ['this_month', I18N.thisMonth],
    ['last_month', I18N.lastMonth],
    ['this_quarter', I18N.thisQuarter],
    ['last_quarter', I18N.lastQuarter],
    ['last_3_months', I18N.last3Months],
    ['this_year', I18N.thisYear],
    ['last_year', I18N.lastYear],
    ['last_n_days', I18N.lastNDaysToken]
  ];
  var CUSTOM_DATES_LABEL = I18N.customDates;

  // api: shared with nx_core.js (Task 11) -- this file's api() throws on a
  // non-2xx response, so it aliases NX.api, not NX.apiSafe.
  const api = window.NX.api;

  // ---- Process scope (client / process picker) -------------------------------
  // Processes are '<client>.<process>'; the client is the text before the first
  // dot (mirrors nx_lib/process_helpers).
  function clientOf(p) {
    var i = p.indexOf('.');
    return i < 0 ? p : p.slice(0, i);
  }

  // allProcesses grouped by client, preserving first-seen order.
  function processGroups() {
    var groups = [], byClient = {};
    state.allProcesses.forEach(function (p) {
      var c = clientOf(p);
      if (!byClient[c]) { byClient[c] = { client: c, procs: [] }; groups.push(byClient[c]); }
      byClient[c].procs.push(p);
    });
    return groups;
  }

  function isSelected(p) { return state.selProcesses.indexOf(p) !== -1; }

  // Serialise the selection into {clients, processes}. A fully-selected client is
  // emitted as a client (durable — it picks up processes added under it later); a
  // partially selected client emits its individually-picked processes. Everything
  // selected -> empty scope, which the server reads as "all allowed" (keeps saved
  // definitions portable and matches the pre-picker default).
  function buildScope() {
    var all = state.allProcesses, sel = state.selProcesses;
    if (!all.length || sel.length >= all.length) return { clients: [], processes: [] };
    var selSet = {};
    sel.forEach(function (p) { selSet[p] = true; });
    var clients = [], processes = [];
    processGroups().forEach(function (g) {
      if (g.procs.every(function (p) { return selSet[p]; })) { clients.push(g.client); return; }
      g.procs.forEach(function (p) { if (selSet[p]) processes.push(p); });
    });
    return { clients: clients, processes: processes };
  }

  // Adopt a source's allowed process list, selecting everything (default) or the
  // subset implied by a saved scope {clients, processes}.
  function setProcessScope(allProcesses, savedScope) {
    state.allProcesses = (allProcesses || []).slice();
    var sc = savedScope || {};
    var clients = sc.clients || [], procs = sc.processes || [];
    if (!clients.length && !procs.length) {
      state.selProcesses = state.allProcesses.slice();
    } else {
      var clientSet = {}; clients.forEach(function (c) { clientSet[c] = true; });
      var procSet = {}; procs.forEach(function (p) { procSet[p] = true; });
      state.selProcesses = state.allProcesses.filter(function (p) {
        return procSet[p] || clientSet[clientOf(p)];
      });
      // A saved scope that now resolves to nothing (perms changed) falls back to all.
      if (!state.selProcesses.length) state.selProcesses = state.allProcesses.slice();
    }
    renderProcessPicker();
  }

  function toggleProcess(p) {
    if (isSelected(p)) {
      // Keep at least one selected. The native click already unchecked the box,
      // so re-render to repaint it to its true (still-selected) state.
      if (state.selProcesses.length <= 1) { renderProcessPicker(); return; }
      state.selProcesses = state.selProcesses.filter(function (x) { return x !== p; });
    } else {
      state.selProcesses = state.selProcesses.concat([p]);
    }
    onScopeChanged();
  }

  function toggleClient(client) {
    var procs = state.allProcesses.filter(function (p) { return clientOf(p) === client; });
    if (procs.every(isSelected)) {
      var next = state.selProcesses.filter(function (p) { return clientOf(p) !== client; });
      // Would empty the whole selection — repaint to undo the native uncheck.
      if (!next.length) { renderProcessPicker(); return; }
      state.selProcesses = next;
    } else {
      var add = procs.filter(function (p) { return !isSelected(p); });
      state.selProcesses = state.selProcesses.concat(add);
    }
    onScopeChanged();
  }

  function selectAllProcesses() {
    state.selProcesses = state.allProcesses.slice();
    onScopeChanged();
  }

  // A docprocessing field is available when at least one selected process exposes
  // it (mirrors the workitems field list: a single process shows its own fields,
  // "all" shows the union). Fields with no `processes` tag — e.g. table sources —
  // are always shown.
  function isFieldAvailable(f) {
    if (!state.allProcesses.length) return true;          // non-docprocessing: no scope
    if (!f.processes || !f.processes.length) return true;
    for (var i = 0; i < f.processes.length; i++) {
      if (state.selProcesses.indexOf(f.processes[i]) !== -1) return true;
    }
    return false;
  }

  // Drop selected columns / filters / sort whose field is no longer available under
  // the current process scope, so narrowing the scope can't leave a broken
  // definition (the query builder rejects a field absent from every scoped process).
  function pruneUnavailableSelections() {
    var avail = {};
    state.fields.forEach(function (f) { if (isFieldAvailable(f)) avail[f.field] = true; });
    state.columns = state.columns.filter(function (c) { return avail[c.field]; });
    state.filters = state.filters.filter(function (f) {
      return f.field === 'processname' || avail[f.field]; // processname is synthetic + always valid
    });
    state.sort = state.sort.filter(function (s) { return avail[s.field]; });
  }

  // The user changed the process scope: refresh the picker, prune now-invalid
  // picks, and re-render the field list + wells + filters.
  function onScopeChanged() {
    renderProcessPicker();
    pruneUnavailableSelections();
    renderFields();
    renderWells();
    renderFilters();
  }

  // One checkbox row (a <label> wrapping the box + text). Clicking the label
  // toggles the box natively, firing `onToggle`.
  function scopeRow(labelText, checked, indeterminate, onToggle) {
    var row = document.createElement('label');
    row.className = 'nx-scope-row';
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = checked;
    box.indeterminate = !!indeterminate;
    box.addEventListener('change', onToggle);
    var span = document.createElement('span');
    span.textContent = labelText;
    row.appendChild(box);
    row.appendChild(span);
    return row;
  }

  function renderProcessPicker() {
    var wrap = document.getElementById('rpScopeWrap');
    if (!wrap) return;
    // Only sources that carry processes (docprocessing) get the picker; table
    // sources have an empty allowed list -> hide the control entirely.
    if (!state.allProcesses.length) {
      wrap.hidden = true;
      toggleScopeMenu(false);
      return;
    }
    wrap.hidden = false;

    var menu = document.getElementById('rpScopeMenu');
    menu.innerHTML = '';
    var total = state.allProcesses.length, selN = state.selProcesses.length;

    var allRow = scopeRow(I18N.allProcesses, selN >= total, selN > 0 && selN < total,
      function () { selectAllProcesses(); });
    allRow.classList.add('nx-scope-all');
    menu.appendChild(allRow);

    processGroups().forEach(function (g) {
      var sel = g.procs.filter(isSelected).length;
      var clientRow = scopeRow(g.client, sel === g.procs.length, sel > 0 && sel < g.procs.length,
        (function (c) { return function () { toggleClient(c); }; })(g.client));
      clientRow.classList.add('nx-scope-client');
      menu.appendChild(clientRow);
      g.procs.forEach(function (p) {
        var label = p.slice(g.client.length + 1) || p; // process part after '<client>.'
        var row = scopeRow(label, isSelected(p), false,
          (function (proc) { return function () { toggleProcess(proc); }; })(p));
        row.classList.add('nx-scope-proc');
        menu.appendChild(row);
      });
    });

    updateScopeSummary();
  }

  function updateScopeSummary() {
    var summary = document.getElementById('rpScopeSummary');
    if (!summary) return;
    var total = state.allProcesses.length, selN = state.selProcesses.length;
    summary.textContent = (selN >= total) ? I18N.allProcesses : (selN + ' / ' + total);
  }

  function toggleScopeMenu(open) {
    var menu = document.getElementById('rpScopeMenu');
    var btn = document.getElementById('rpScopeBtn');
    if (!menu || !btn) return;
    var willOpen = (open === undefined) ? menu.hidden : open;
    menu.hidden = !willOpen;
    btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  }

  function buildDefinition() {
    var d = {
      schemaVersion: 1,
      source: state.source,
      visualization: 'table',
      title: document.getElementById('rpTitle').value || I18N.untitledReport,
      subtitle: document.getElementById('rpSubtitle').value || null,
      columns: state.columns.map(function (c) {
        var col = { field: c.field, header: c.header || c.label, agg: null };
        if (c.grain) col.grain = c.grain;
        return col;
      }),
      groupBy: [],
      filters: state.filters,
      sort: state.sort,
      // Canonical metrics: when present the selected Columns become the grouping
      // and the server returns these as aggregations. Omit when none selected.
      metrics: state.metrics.map(function (c) { return { metric: c }; }),
      scope: buildScope(),
      rowLimit: 5000,
      sql: null,
      sqlTarget: null,
    };
    if (state.forecast && state.forecast.enabled) d.forecast = state.forecast;
    return d;
  }

  // Definition for whichever mode is active (curated builder vs SQL editor).
  function currentDefinition() {
    return state.mode === 'sql' ? sqlDefinition() : buildDefinition();
  }

  function reportTitle() {
    return document.getElementById('rpTitle').value
      || (state.mode === 'sql' ? I18N.sqlReport : I18N.report);
  }

  function exportFormat() {
    var el = document.getElementById('rpExportFormat');
    return (el && el.value) || 'xlsx';
  }

  function downloadBlob(blob, filename) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }

  // Leading field-type icon for the source-field list (Task 10). The
  // catalog's `type` is a free-form string (nx_lib/reporting/catalog.py:
  // FieldMetadata.DataType when present, else "date"/"string") rather than a
  // fixed enum, so this is a best-effort classifier -- same /date/i +
  // grainable idiom renderFilters() below (and _reporting_simple_js.html)
  // already use to detect date fields.
  function fieldTypeIconClass(f) {
    var t = String(f.type || '');
    if (f.grainable || /date/i.test(t)) return 'fa-calendar';
    if (/int|decimal|float|numeric|money|double|real|bit/i.test(t)) return 'fa-hashtag';
    return 'fa-font';
  }

  function renderFields() {
    var q = document.getElementById('rpFieldSearch').value.toLowerCase();
    var ul = document.getElementById('rpFieldList');
    ul.innerHTML = '';
    state.fields.filter(function (f) {
      return isFieldAvailable(f) && f.label.toLowerCase().indexOf(q) !== -1;
    }).forEach(function (f) {
      var li = document.createElement('li');
      var icon = document.createElement('i');
      icon.className = 'fas ' + fieldTypeIconClass(f) + ' reporting-field-icon';
      icon.setAttribute('aria-hidden', 'true');
      var label = document.createElement('span');
      label.textContent = f.label;
      li.appendChild(icon);
      li.appendChild(label);
      li.onclick = function () {
        if (!state.columns.find(function (c) { return c.field === f.field; })) {
          state.columns.push(Object.assign({}, f, {
            header: f.label,
            grain: f.grainable ? 'month' : undefined,
          }));
          renderWells();
        }
      };
      ul.appendChild(li);
    });
  }

  function renderWells() {
    var cols = document.getElementById('rpWellColumns');
    cols.innerHTML = '';
    state.columns.forEach(function (c, i) {
      var li = document.createElement('li');
      li.className = 'reporting-col-row';
      // Display-only drag-handle glyph (Task 10) -- columns have no
      // reorder logic today (add/remove/rename/grain only), so this adds
      // no dragstart/dragover wiring, just the visual affordance.
      var grip = document.createElement('i');
      grip.className = 'fas fa-grip-vertical reporting-col-grip';
      grip.setAttribute('aria-hidden', 'true');
      var inp = document.createElement('input');
      inp.value = c.header;
      inp.oninput = function (e) { c.header = e.target.value; };
      // Date columns get a grain selector (day/week/month/quarter/year).
      var grainSel = null;
      if (c.grainable) {
        grainSel = document.createElement('select');
        grainSel.className = 'reporting-grain';
        [['day', I18N.grainDay], ['week', I18N.grainWeek], ['month', I18N.grainMonth],
         ['quarter', I18N.grainQuarter], ['year', I18N.grainYear]].forEach(function (g) {
          var opt = document.createElement('option');
          opt.value = g[0]; opt.textContent = g[1];
          grainSel.appendChild(opt);
        });
        grainSel.value = c.grain || 'month';
        grainSel.onchange = function (e) { c.grain = e.target.value; };
      }
      var rm = document.createElement('button');
      rm.textContent = '×';
      rm.onclick = function () { state.columns.splice(i, 1); renderWells(); };
      li.appendChild(grip);
      li.appendChild(inp);
      if (grainSel) li.appendChild(grainSel);
      li.appendChild(rm);
      cols.appendChild(li);
    });
    // Sort entries reference selected columns, so drop any whose column was
    // removed, then re-render the Sort well.
    state.sort = state.sort.filter(function (s) {
      return state.columns.find(function (c) { return c.field === s.field; });
    });
    renderSort();
  }

  // ----- Auto AI caption (Task 13) -------------------------------------------
  // Fires on chart mount (below) when the caption slot exists in the DOM --
  // it only exists when the page was rendered for a reporting.ai.explain.use
  // holder (Jinja `ai_caption_enabled` gate in reporting.html), so a caller
  // with no permission is a silent no-op. Shimmers while the request is in
  // flight, then shows the caption with its AI chip -- or hides silently on
  // ANY error (network failure, non-200, bad JSON): unlike the chat panel,
  // this surface never shows an error state or logs to the console.
  // `captionSeq` is a monotonically-increasing token: a slow response from an
  // old run is discarded once a newer run has fired its own caption, so a
  // fast filter change/re-run can never show a stale caption over the new
  // result. Duplicated (not shared) from _reporting_simple_js.html -- Simple
  // and Advanced are separate self-contained IIFEs with no shared util
  // partial today, and this task deliberately doesn't invent one.
  var captionSeq = 0;
  function fireCaption(boxId, columns, rows, title, dateLabel) {
    var box = document.getElementById(boxId);
    if (!box) return;
    var seq = ++captionSeq;
    box.hidden = false;
    box.classList.add('rp-caption--loading');
    box.textContent = '';
    fetch(API_PREFIX + 'api/reporting/ai/caption', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({
        columns: columns, rows: rows.slice(0, 5000),   // whole grid -> server-side fact sheet
        title: title || undefined, dateLabel: dateLabel || undefined
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
      chip.textContent = I18N.aiChip;
      box.appendChild(chip);
      box.appendChild(document.createTextNode(' ' + data.caption));
    }).catch(function () {
      if (seq !== captionSeq) return;
      box.hidden = true;
      box.classList.remove('rp-caption--loading');
    });
  }

  function resetViews(hasData) {
    state._chartMounted = false;
    state._pivotMounted = false;
    document.getElementById('rpViewToggle').hidden = !hasData;
    // A prior run's caption only ever fires on chart mount, but it must not
    // linger once a NEW run lands — whether that run's grid has data, is
    // empty, or the user never revisits the Chart view. Guarded: the box
    // only exists in the DOM for a reporting.ai.explain.use holder.
    var rpCaptionBox = document.getElementById('rpCaption');
    if (rpCaptionBox) { rpCaptionBox.hidden = true; rpCaptionBox.textContent = ''; }
    setView('grid');
  }

  function setView(view) {
    state.view = view;
    document.getElementById('rpResults').hidden = view !== 'grid';
    document.getElementById('rpChart').hidden = view !== 'chart';
    document.getElementById('rpPivot').hidden = view !== 'pivot';
    [['rpViewGrid', 'grid'], ['rpViewChart', 'chart'], ['rpViewPivot', 'pivot']]
      .forEach(function (p) {
        document.getElementById(p[0]).classList.toggle('active', p[1] === view);
      });
    if (!state.lastResult) return;
    if (view === 'chart' && !state._chartMounted) {
      // onElementClick is omitted entirely (not just a no-op) when the result
      // isn't drill-eligible (see canDrill) — Advanced's chart can plot ANY
      // grid, aggregate or not, so a raw non-aggregate chart must not show a
      // pointer cursor that leads nowhere.
      var chartOpts = canDrill(state.lastDef) ? { onElementClick: drillFromChart } : {};
      chartOpts.forecast = state.lastResult.forecast || null;
      ReportingViz.mountChart(document.getElementById('rpChart'),
        state.lastResult.columns, state.lastResult.rows, chartOpts);
      state._chartMounted = true;
      // Task 13: fires once per chart mount (guarded by _chartMounted above,
      // which resetViews() clears on every new run), not on every setView
      // call — switching Grid -> Chart -> Grid -> Chart again re-fires
      // nothing since the chart is already mounted.
      fireCaption('rpCaption', state.lastResult.columns, state.lastResult.rows,
        reportTitle(), state._lastResolvedDatesLabel || null);
    }
    if (view === 'pivot' && !state._pivotMounted) {
      ReportingViz.mountPivot(document.getElementById('rpPivot'),
        state.lastResult.columns, state.lastResult.rows);
      state._pivotMounted = true;
    }
  }

  // Filter-op labels — mirrored in _reporting_simple_js.html's OP_LABELS with
  // the same msgids, so the two maps can never translate apart.
  var OP_LABELS = {
    eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤',
    between: I18N.opBetween,
    'in': I18N.opIn,
    not_in: I18N.opNotIn,
    contains: I18N.opContains,
    starts_with: I18N.opStartsWith,
    is_null: I18N.opIsEmpty,
    is_not_null: I18N.opIsNotEmpty
  };

  // ----- Drill-through (Advanced: chart clicks + grid rows) -----
  // Mirrors _reporting_simple_js.html's metricAggFor/clickedFor/openDrill/
  // drillFromChart, adapted to the Advanced builder's state shape: the
  // definition that produced the currently-shown result lives in
  // state.lastDef (captured at request time by run()/runSql(), rather than a
  // "current report" object), and the source field catalog is state.sourcesById
  // (keyed by source id, populated by loadSources()).

  // Per-plan gate: aggregate curated results only (>=1 metric, >=1 dimension,
  // never a SQL-sandbox definition, which carries no `source` to transform).
  // Used both to decide whether the chart gets a click handler at all (so a
  // plain, non-aggregate grid charted ad hoc never shows a misleading
  // pointer cursor) and to gate the grid-row affordance below.
  function canDrill(def) {
    return !!(def && def.kind !== 'sql' && (def.metrics || []).length && (def.columns || []).length);
  }

  // The metric's aggregation (sum/avg/count/count_distinct/…) — decides
  // whether a drilled-into set of rows is a "contributing to this number"
  // count (distinct aggregations) vs. an exact breakdown.
  function metricAggFor(def) {
    var m = (def.metrics && def.metrics[0]) || null;
    if (!m) return '';
    var list = (state.metricsBySource || {})[def.source] || [];
    var hit = list.find(function (x) { return x.code === m.metric; });
    return hit ? hit.aggregation : '';
  }

  // Maps a definition's leading columns (dimensions come first in the result
  // row) to ReportingDrill's {field, grain, value} shape.
  function clickedFor(def, rowValues) {
    return ((def && def.columns) || []).map(function (c, i) {
      return { field: c.field, grain: c.grain || null, value: rowValues[i] };
    });
  }

  function openDrill(clicked) {
    var def = state.lastDef;
    if (!def || !def.source) return;
    var src = state.sourcesById[def.source];
    if (!src) return;
    var header = clicked.map(function (c) {
      var f = (src.fields || []).find(function (x) { return x.field === c.field; });
      var v = (c.value === null || c.value === undefined || c.value === '')
        ? ReportingDrill.I18N.nullLabel : String(c.value).slice(0, 60);
      return ((f && f.label) || c.field) + ' = ' + v;
    }).join(' · ');
    var isDistinct = /distinct/i.test(String(metricAggFor(def) || ''));
    ReportingDrill.open({
      definition: def, fields: src.fields || [],
      clicked: clicked, header: header, isDistinct: isDistinct
    });
  }

  // index/datasetIndex are Chart.js element coordinates from ReportingViz's
  // onElementClick callback. Unlike Simple's fixed definition-driven chart,
  // Advanced's chart lets the user pick ANY result column as the X axis
  // (ReportingViz.getChartXField), so a click only drills when that column is
  // actually one of the definition's dimensions — picking a metric column as
  // X is a no-op here rather than a false drill.
  function drillFromChart(index, datasetIndex) {
    var def = state.lastDef;
    if (!canDrill(def)) return;
    var dims = def.columns || [];
    var xField = window.ReportingViz && ReportingViz.getChartXField && ReportingViz.getChartXField();
    if (!xField) return;
    var dimCol = dims.find(function (d) { return d.field === xField; });
    if (!dimCol) return;
    var rawVal = ReportingViz.getChartLabelAt(index);
    if (rawVal === undefined) return;
    openDrill([{ field: dimCol.field, grain: dimCol.grain || null, value: rawVal }]);
  }

  // Advanced has no named number-formatting helper (grid cells render via
  // String(v)); this mirrors Simple's fmtNumber numeric check (Number(v) +
  // isNaN, guarded against null/empty) so both panes tag result-table cells
  // reporting-ledger-num (mono/tabular-nums/right-aligned) the same way.
  function isNumericCell(v) {
    if (v == null || v === '') return false;
    var n = Number(v);
    return !isNaN(n) && isFinite(n);
  }

  // KPI stat band (L7 locked decision): total/buckets/avg computed
  // client-side from the rows the pane already has — no second query. The
  // first column after the definition's group-by dimensions (def.columns)
  // whose values are ALL finite numbers is treated as the measure; hidden
  // when there are no rows or no such column. Mirrors
  // _reporting_simple_js.html's own computeKpiBand/renderKpiBand.
  function computeKpiBand(def, rows) {
    if (!rows.length) return null;
    var dims = ((def && def.columns) || []).length;
    var idx = -1;
    for (var i = dims; i < rows[0].length; i++) {
      if (rows.every(function (r) { return isNumericCell(r[i]); })) { idx = i; break; }
    }
    if (idx === -1) return null;
    // Mirrors Simple's computeKpiBand: NULL-leading-dimension rows are not
    // periods, and buckets counts that dimension's distinct values rather than
    // the rows (a second dimension used to multiply it by its own
    // cardinality). cells is the row count, and what avg divides by.
    var kept = dims ? rows.filter(function (r) { return r[0] != null; }) : rows;
    if (!kept.length) return null;
    var total = 0, cells = 0;
    var periods = Object.create(null);
    kept.forEach(function (r) {
      if (dims) periods[String(r[0])] = 1;
      total += Number(r[idx]);
      cells++;
    });
    var buckets = dims ? Object.keys(periods).length : cells;
    return { total: total, buckets: buckets, cells: cells,
             avg: cells ? total / cells : 0, idx: idx };
  }

  // Result-column header for a measure ("Documents imported"), so a KPI says
  // WHAT it totals instead of just "Total". Mirrors Simple's measureLabel.
  function measureLabel(columns, idx) {
    var c = (columns || [])[idx];
    return (c && (c.header || c.field)) || '';
  }

  function metricTotalModes(def) {
    var list = (state.metricsBySource || {})[def && def.source] || [];
    return ((def && def.metrics) || []).map(function (m) {
      var hit = list.find(function (x) { return x.code === m.metric; });
      return (hit && hit.totalMode) || 'sum';
    });
  }

  // Newest date bucket's sum for column `idx` — a level (the backlog) totalled
  // across every bucket would be nonsense. Mirrors Simple's latestBucketTotal;
  // null when the definition has no grained date dimension.
  function latestBucketTotal(def, rows, idx) {
    var cols = (def && def.columns) || [];
    var dateIdx = -1;
    for (var i = 0; i < cols.length; i++) {
      if (cols[i].grain) { dateIdx = i; break; }
    }
    if (dateIdx === -1) return null;
    var maxKey = null;
    rows.forEach(function (r) {
      if (r[idx] == null) return;
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

  // One labelled total per metric: the aggregate query projects the metrics
  // after the dimensions in def.metrics order, so measure n lives at dims + n.
  // The primary (kpi.idx) is skipped — the band already shows it.
  function otherMeasureTotals(def, columns, rows, kpi) {
    var modes = metricTotalModes(def);
    if (modes.length < 2 || !rows.length || !kpi) return [];
    var dims = ((def && def.columns) || []).length;
    var out = [];
    for (var n = 0; n < modes.length; n++) {
      var idx = dims + n;
      if (idx === kpi.idx || idx >= rows[0].length) continue;
      var latest = modes[n] === 'latest' ? latestBucketTotal(def, rows, idx) : null;
      var total = 0, any = !!latest;
      if (latest) {
        total = latest.total;
      } else {
        rows.forEach(function (r) {
          if (isNumericCell(r[idx])) { total += Number(r[idx]); any = true; }
        });
      }
      if (any) out.push({ label: measureLabel(columns, idx), total: total });
    }
    return out;
  }

  // Advanced has no named number-formatting helper elsewhere (grid cells
  // render via plain String(v)); this mirrors Simple's fmtNumber
  // (Number(v) + toLocaleString(APP_LANG)) for the KPI band's own figures.
  var APP_LANG = document.documentElement.lang || undefined;
  function fmtKpiNumber(v) {
    var n = Number(v);
    return isNaN(n) ? String(v) : n.toLocaleString(APP_LANG);
  }

  function kpiBlock(testid, caption, value) {
    var block = document.createElement('div');
    block.className = 'reporting-ledger-kpi';
    block.setAttribute('data-testid', testid);
    var cap = document.createElement('span');
    cap.className = 'reporting-ledger-caption';
    cap.textContent = caption;
    var val = document.createElement('span');
    val.className = 'reporting-ledger-kpi-value';
    val.textContent = fmtKpiNumber(value);
    block.appendChild(cap);
    block.appendChild(val);
    return block;
  }

  function renderKpiBand(def, rows, columns) {
    var band = document.getElementById('rpKpiBand');
    if (!band) return;
    var kpi = computeKpiBand(def, rows);
    band.innerHTML = '';
    if (!kpi) { band.hidden = true; return; }
    // Every figure names its measure — "Total" alone never said total of what,
    // and a multi-metric run silently showed only the first metric's.
    var primary = measureLabel(columns, kpi.idx);
    var withLabel = function (caption, label) {
      return label ? caption + ' · ' + label : caption;
    };
    band.appendChild(kpiBlock('reporting-kpi-total', withLabel(I18N.kpiTotal, primary), kpi.total));
    otherMeasureTotals(def, columns, rows, kpi).forEach(function (m) {
      band.appendChild(kpiBlock('reporting-kpi-total-extra', withLabel(I18N.kpiTotal, m.label), m.total));
    });
    band.appendChild(kpiBlock('reporting-kpi-buckets', I18N.kpiBuckets, kpi.buckets));
    band.appendChild(kpiBlock('reporting-kpi-avg',
      withLabel(kpi.cells === kpi.buckets ? I18N.kpiAvg : I18N.kpiAvgCell, primary), kpi.avg));
    band.hidden = false;
  }

  // Forecast toggle (mirrors _reporting_simple_js.html's forecastEligible/
  // syncForecastCtl, adapted to the Advanced builder's def shape): eligible
  // only for a single grained date column + at least one metric, same shape
  // the server's /run forecast block requires.
  function forecastEligibleDef(def) {
    var cols = (def && def.columns) || [];
    return !!(def && def.kind !== 'sql' && cols.length === 1 && cols[0].grain &&
      Array.isArray(def.metrics) && def.metrics.length > 0);
  }
  function syncForecastCtl() {
    var wrap = document.getElementById('rpForecastWrap');
    var box = document.getElementById('rpForecast');
    var sel = document.getElementById('rpForecastHorizon');
    if (!wrap) return;
    var eligible = forecastEligibleDef(state.lastDef);
    wrap.hidden = !eligible;
    var on = eligible && !!(state.forecast && state.forecast.enabled);
    box.checked = on;
    sel.hidden = !on;
    if (!eligible) state.forecast = null;
  }
  document.getElementById('rpForecast').addEventListener('change', function () {
    var h = document.getElementById('rpForecastHorizon').value;
    state.forecast = this.checked
      ? { enabled: true, horizon: h === 'auto' ? 'auto' : parseInt(h, 10) } : null;
    run();
  });
  document.getElementById('rpForecastHorizon').addEventListener('change', function () {
    if (!state.forecast) return;
    var h = this.value;
    state.forecast.horizon = h === 'auto' ? 'auto' : parseInt(h, 10);
    run();
  });

  function renderResults(data) {
    state.lastResult = { columns: data.columns || [], rows: data.rows || [], forecast: data.forecast || null };
    syncForecastCtl();
    // Resolved-dates label for fireCaption() on chart mount (Task 13) --
    // Advanced has no per-token i18n label map like Simple's tokenLabel(), so
    // this is just the field + the resolved start/end, e.g. "ForDate: 2026-06-01
    // → 2026-06-30". Good enough context for the caption prompt; not shown
    // anywhere in the Advanced UI itself.
    var rdates = data.resolvedDates || [];
    state._lastResolvedDatesLabel = rdates.length
      ? rdates.map(function (d) { return d.field + ': ' + d.start + ' → ' + d.end; }).join(' · ')
      : null;
    renderKpiBand(state.lastDef, data.rows || [], data.columns || []);
    // Stash the echoed SQL for the Show query panel. Only /run echoes sql;
    // SQL-sandbox runs (/api/reporting/sql/run) never set a sql key — button stays hidden.
    var sqlBtn = document.getElementById('rpShowSql');
    var sqlView = document.getElementById('rpSqlView');
    state._lastSql = data.sql || null;
    state._lastSqlPretty = data.sqlPretty || null;
    state._lastSqlDisplay = data.sqlDisplay || null;
    state._lastParams = data.params || [];
    if (sqlBtn) {
      sqlBtn.hidden = !state._lastSql;
      sqlBtn.textContent = I18N.showQuery;
    }
    if (sqlView) sqlView.hidden = true;
    var sqlPeek = document.getElementById('rpSqlPeek');
    if (sqlPeek) {
      if (state._lastSqlDisplay) {
        sqlPeek.textContent = state._lastSqlDisplay.split('\n')[0] + '…';
        sqlPeek.hidden = false;
      } else {
        sqlPeek.hidden = true;
      }
    }
    resetViews(!!(data.rows && data.rows.length));
    var wrap = document.getElementById('rpResults');
    wrap.innerHTML = '';
    if (!data.rows.length) {
      var empty = document.createElement('div');
      empty.className = 'nx-empty reporting-empty';
      empty.setAttribute('data-testid', 'reporting-no-rows');
      var art = document.createElement('div');
      art.className = 'nx-empty__art';
      art.innerHTML = '<i class="fas fa-inbox" aria-hidden="true"></i>';
      var t = document.createElement('p');
      t.className = 'nx-empty__title';
      t.textContent = I18N.noRowsMatched;
      var s = document.createElement('p');
      s.className = 'nx-empty__sub';
      s.textContent = I18N.noRowsHint;
      empty.appendChild(art); empty.appendChild(t); empty.appendChild(s);
      wrap.appendChild(empty);
      return;
    }
    if (data.truncated && data.rowCount) {
      var note = document.createElement('p');
      note.className = 'reporting-truncated-note';
      note.textContent = I18N.truncatedNote.replace('{n}', String(data.rowCount));
      wrap.appendChild(note);
    }

    // Drillable only for aggregate results (see canDrill) whose leading
    // columns resolve to a valid drill definition — probed once with the
    // first row, same gating as Simple's renderTable.
    var def = state.lastDef || {};
    var src = state.sourcesById[def.source];
    var drillable = !!(canDrill(def) && src &&
      ReportingDrill.buildDrillDefinition(def, src.fields || [], clickedFor(def, data.rows[0])));

    var table = document.createElement('table');
    table.className = 'reporting-table' + (drillable ? ' reporting-drill-clickable' : '');

    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');
    data.columns.forEach(function (c) {
      var th = document.createElement('th');
      th.textContent = c.header;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    // Data bars (Task 7): one column max per column index, computed once
    // over cells the same isNumericCell check already accepts — a mixed/
    // text column just never gets a bar rather than being skewed by a stray
    // numeric-looking cell.
    var colMax = data.columns.map(function (_, i) {
      var max = 0;
      data.rows.forEach(function (r) {
        if (isNumericCell(r[i])) {
          var n = Math.abs(Number(r[i]));
          if (n > max) max = n;
        }
      });
      return max;
    });

    var tbody = document.createElement('tbody');
    data.rows.forEach(function (r) {
      var tr = document.createElement('tr');
      r.forEach(function (v, i) {
        var td = document.createElement('td');
        if (isNumericCell(v)) {
          td.className = 'reporting-ledger-num rp-cell-num';
          var max = colMax[i];
          var pct = max > 0 ? (Math.abs(Number(v)) / max * 100) : 0;
          td.style.setProperty('--bar', pct + '%');
        }
        td.textContent = (v == null ? '' : String(v));
        tr.appendChild(td);
      });
      if (drillable) {
        tr.tabIndex = 0;
        tr.addEventListener('click', function () { openDrill(clickedFor(def, r)); });
        tr.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') openDrill(clickedFor(def, r));
        });
      }
      tbody.appendChild(tr);
    });
    // Forecast rows (Task 6's Simple-tab reference, adapted to this pane's
    // DOM-built grid): appended after the real data rows, positionally
    // matched to the trailing metric columns (mStart), never drillable.
    var fcRows = (data.forecast && !data.forecast.unavailable && (data.forecast.buckets || []).length)
      ? data.forecast : null;
    if (fcRows) {
      var mStart = data.columns.length - fcRows.series.length;
      fcRows.buckets.forEach(function (b, bi) {
        var ftr = document.createElement('tr');
        ftr.className = 'is-forecast';
        ftr.setAttribute('data-testid', 'rp-forecast-row');
        for (var ci = 0; ci < data.columns.length; ci++) {
          var ftd = document.createElement('td');
          if (ci === 0) {
            ftd.textContent = String(b).slice(0, 10) + ' ';
            var badge = document.createElement('span');
            badge.className = 'rp-forecast-badge';
            badge.textContent = I18N.forecast;
            ftd.appendChild(badge);
          } else if (ci >= mStart) {
            var sv = fcRows.series[ci - mStart];
            var val = sv.values[bi];
            ftd.className = 'reporting-ledger-num rp-cell-num';
            ftd.textContent = (val == null ? '' : String(val));
          }
          ftr.appendChild(ftd);
        }
        tbody.appendChild(ftr);
      });
    }
    table.appendChild(tbody);

    wrap.appendChild(table);
  }

  // Table and SQL mode share one result area, so a mode switch used to leave
  // the *other* mode's output on screen: the builder's pivot shelf, its AI
  // caption, its timing badge and -- worst -- its generated SQL in the "Query
  // sent to the database" panel while the editor above held something else
  // entirely. Reset to a mode-appropriate empty state instead.
  function resetResultArea() {
    var sqlOn = state.mode === 'sql';
    state.lastResult = null;
    state.lastDef = null;
    state._lastSql = null;
    state._lastSqlPretty = null;
    state._lastSqlDisplay = null;
    state._chartMounted = false;
    state._pivotMounted = false;
    ['rpViewToggle', 'rpKpiBand', 'rpSqlView', 'rpShowSql', 'rpSqlPeek',
     'rpCaption', 'rpForecastWrap', 'rpForecastHorizon', 'reportingTiming']
      .forEach(function (id) {
        var e = document.getElementById(id);
        if (e) e.hidden = true;
      });
    var cap = document.getElementById('rpCaption');
    if (cap) cap.textContent = '';
    document.getElementById('rpChart').innerHTML = '';
    document.getElementById('rpPivot').innerHTML = '';
    setView('grid');
    var wrap = document.getElementById('rpResults');
    wrap.innerHTML = '';
    var box = document.createElement('div');
    box.className = 'nx-empty reporting-empty-state';
    box.setAttribute('data-testid', 'reporting-empty-state');
    var art = document.createElement('div');
    art.className = 'nx-empty__art';
    art.innerHTML = '<i class="fas ' + (sqlOn ? 'fa-terminal' : 'fa-chart-column') +
      '" aria-hidden="true"></i>';
    var t = document.createElement('p');
    t.className = 'nx-empty__title';
    t.textContent = sqlOn ? I18N.sqlEmptyTitle : I18N.builderEmptyTitle;
    var sub = document.createElement('p');
    sub.className = 'nx-empty__sub';
    sub.textContent = sqlOn ? I18N.sqlEmptyHint : I18N.builderEmptyHint;
    box.appendChild(art);
    box.appendChild(t);
    box.appendChild(sub);
    wrap.appendChild(box);
  }

  function setMode(mode) {
    var changed = state.mode !== mode;
    state.mode = mode;
    var sqlOn = mode === 'sql';
    document.getElementById('rpModeSql').classList.toggle('active', sqlOn);
    document.getElementById('rpModeTable').classList.toggle('active', !sqlOn);
    document.getElementById('rpSqlPanel').hidden = !sqlOn;
    document.querySelector('.reporting-fields').style.display = sqlOn ? 'none' : '';
    document.querySelector('.reporting-wells').style.display = sqlOn ? 'none' : '';
    // SQL mode hides both sidebars; span the results column full-width so it
    // doesn't collapse into the grid's narrow first track. Table mode restores
    // the 3-column builder layout.
    document.querySelector('.reporting-main').classList.toggle('reporting-main--single', sqlOn);
    if (changed) resetResultArea();
  }

  // toast: shared with nx_core.js (Task 11) -- replaces window.alert for
  // non-blocking feedback. window.confirm() stays native: it needs a
  // blocking answer.
  const toast = window.NX.toast;

  // `detail` is the driver/validator message the API returns alongside the
  // generic `error` (NX.api hangs it on the Error). Without it a Live SQL
  // failure read "Could not run query" and nothing else -- the reason for the
  // failure ("Invalid object name 'Workitem'.") was thrown away.
  function showError(msg, detail) {
    var wrap = document.getElementById('rpResults');
    wrap.innerHTML = '';
    setView('grid');
    var p = document.createElement('p');
    p.className = 'reporting-error';
    p.textContent = msg;
    wrap.appendChild(p);
    if (detail && detail !== msg) {
      var d = document.createElement('pre');
      d.className = 'reporting-error-detail';
      d.setAttribute('data-testid', 'reporting-error-detail');
      d.textContent = detail;
      wrap.appendChild(d);
    }
    // Same stale-caption guard as resetViews() -- a failed run must not leave
    // the PREVIOUS run's caption sentence sitting above the error message.
    var rpCaptionErrBox = document.getElementById('rpCaption');
    if (rpCaptionErrBox) { rpCaptionErrBox.hidden = true; rpCaptionErrBox.textContent = ''; }
  }
  // In-flight indicator for report runs. Lives inside #rpResults so the
  // renderResults/showError innerHTML swap self-cleans it. The view is forced
  // to grid because #rpResults is hidden whenever state.view !== 'grid' —
  // without this, a re-run from Chart/Pivot would show nothing. Run is
  // disabled so a double-click can't fire two parallel requests (rpRun is the
  // only run trigger on this tab). The Motion observer ignores non-TABLE/
  // .reporting-empty/.reporting-error nodes, so this block is
  // animation-inert there — its own shimmer is pure CSS (.rp-skeleton),
  // reduced-motion safe via reporting.css's own query. Task 7: a KPI-band-
  // shaped + table-shaped skeleton replaces the old dots+text spinner (still
  // used elsewhere, e.g. the drill drawer) so the real result doesn't cause a
  // layout jump on arrival; role=status + aria-label keeps the same
  // "Running…" screen-reader announcement the old visible label gave.
  function showRunLoading() {
    document.getElementById('rpRun').disabled = true;
    document.getElementById('rpViewToggle').hidden = true;
    setView('grid');
    var wrap = document.getElementById('rpResults');
    wrap.innerHTML = '';
    // A prior run's caption sentence must never linger over the new run's
    // (still-loading, possibly failed or empty) result -- hidden here just
    // like Simple's runCurrent() does at run-start, cleared again by
    // fireCaption() once (and if) the new run's chart gets mounted. Guarded:
    // the box only exists in the DOM for a reporting.ai.explain.use holder.
    var rpCaptionLoadBox = document.getElementById('rpCaption');
    if (rpCaptionLoadBox) { rpCaptionLoadBox.hidden = true; rpCaptionLoadBox.textContent = ''; }
    var box = document.createElement('div');
    box.setAttribute('data-testid', 'reporting-run-loading');
    box.setAttribute('role', 'status');
    box.setAttribute('aria-label', I18N.running);
    var band = document.createElement('div');
    band.className = 'rp-skeleton-band';
    for (var i = 0; i < 3; i++) {
      var kpi = document.createElement('div');
      kpi.className = 'rp-skeleton rp-skeleton-kpi';
      band.appendChild(kpi);
    }
    var table = document.createElement('div');
    table.className = 'rp-skeleton-table';
    for (var j = 0; j < 6; j++) {
      var row = document.createElement('div');
      row.className = 'rp-skeleton rp-skeleton-row';
      table.appendChild(row);
    }
    box.appendChild(band);
    box.appendChild(table);
    wrap.appendChild(box);
  }
  function endRunLoading() {
    document.getElementById('rpRun').disabled = false;
  }

  // Masthead timing badge, shared with _reporting_simple_js.html's own
  // showTiming (same #reportingTiming element, same "N rows · M ms" shape).
  // Hidden until the first successful run in either pane.
  function showTiming(rows, elapsedMs) {
    var badge = document.getElementById('reportingTiming');
    if (!badge) return;
    badge.textContent = I18N.timing
      .replace('{rows}', String(rows == null ? 0 : rows))
      .replace('{ms}', String(Math.round(elapsedMs)));
    badge.hidden = false;
  }

  // Modal replacement for window.prompt: resolves the trimmed name, or null
  // on cancel/empty.
  function promptName(title, initial) {
    return new Promise(function (resolve) {
      var modal = document.getElementById('rpNameModal');
      var input = document.getElementById('rpNameModalInput');
      var ok = document.getElementById('rpNameModalOk');
      var cancel = document.getElementById('rpNameModalCancel');
      document.getElementById('rpNameModalTitle').textContent = title;
      input.value = initial || '';
      modal.hidden = false;
      input.focus();
      input.select();
      function done(v) {
        modal.hidden = true;
        ok.onclick = cancel.onclick = input.onkeydown = null;
        resolve(v);
      }
      ok.onclick = function () { done(input.value.trim() || null); };
      cancel.onclick = function () { done(null); };
      input.onkeydown = function (e) {
        if (e.key === 'Enter') ok.click();
        if (e.key === 'Escape') cancel.click();
      };
    });
  }

  function ackThen(cb) {
    if (state.sqlSource && state.sqlSource.acknowledged) { cb(); return; }
    var modal = document.getElementById('rpSqlAck');
    modal.hidden = false;
    document.getElementById('rpSqlAckCancel').onclick = function () { modal.hidden = true; };
    document.getElementById('rpSqlAckAccept').onclick = function () {
      api('/api/reporting/sql/ack', { method: 'POST', body: '{}' }).then(function () {
        // Ack is per-user — mark every SQL target acknowledged so switching
        // targets afterwards doesn't re-prompt.
        state.sqlSources.forEach(function (s) { s.acknowledged = true; });
        modal.hidden = true;
        cb();
      }).catch(function (e) { modal.hidden = true; showError(e.message, e.detail); });
    };
  }

  function sqlBody() {
    return {
      target: document.getElementById('rpSqlTarget').value || 'statistics',
      sql: document.getElementById('rpSqlEditor').value,
    };
  }

  function runSql() {
    ackThen(function () {
      showRunLoading();
      api('/api/reporting/sql/run', { method: 'POST', body: JSON.stringify(sqlBody()) })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          endRunLoading();
          // SQL-sandbox results carry no definition to transform into a drill
          // — kind: 'sql' alone is enough for renderResults/drillFromChart's
          // guards to disable the affordance entirely.
          state.lastDef = { kind: 'sql' };
          renderResults(data);
        })
        .catch(function (e) { endRunLoading(); showError(e.message, e.detail); });
    });
  }

  function sqlDefinition() {
    var b = sqlBody();
    return {
      kind: 'sql', target: b.target, sql: b.sql,
      title: document.getElementById('rpTitle').value || I18N.sqlReport,
    };
  }

  // Save the current report. asNew, no loaded report, or a loaded report the
  // caller can't edit => create a copy; otherwise overwrite in place via PUT.
  function doSave(asNew) {
    var def = currentDefinition();
    var canOverwrite = state.currentReportId
      && (state.currentReportOwned || state.currentReportCanEdit);
    if (asNew || !canOverwrite) {
      promptName(I18N.reportName, reportTitle()).then(function (name) {
        if (!name) return;
        api('/api/reporting/reports', {
          method: 'POST',
          body: JSON.stringify({ name: name, definition: def }),
        }).then(function (res) { return res.json(); })
          .then(function (data) {
            state.currentReportId = data.id || null;
            state.currentReportName = name;
            state.currentReportOwned = true;
            state.currentReportCanEdit = true;
            loadReports();
            toast(I18N.saved);
          }).catch(function (e) { toast(I18N.saveFailed + ': ' + e.message, true); });
      });
      return;
    }
    var newName = document.getElementById('rpTitle').value || state.currentReportName || I18N.report;
    api('/api/reporting/reports/' + state.currentReportId, {
      method: 'PUT',
      body: JSON.stringify({ name: newName, definition: def }),
    }).then(function () {
      state.currentReportName = newName;
      loadReports();
      toast(I18N.saved);
    }).catch(function (e) { toast(I18N.saveFailed + ': ' + e.message, true); });
  }

  function save(asNew) {
    if (state.mode === 'sql') { ackThen(function () { doSave(asNew); }); }
    else { doSave(asNew); }
  }

  // Export the raw result grid (curated or SQL) in the chosen file format.
  function exportGridRows() {
    var fmt = exportFormat();
    var ext = fmt === 'csv' ? '.csv' : '.xlsx';
    var body = currentDefinition();
    body.format = fmt;
    if (fmt === 'xlsx') {
      var png = window.ReportingViz && ReportingViz.chartPngDataUrl();
      if (png) body.chartImage = png;
    }
    var run = function () {
      api('/api/reporting/export', { method: 'POST', body: JSON.stringify(body) })
        .then(function (res) { return res.blob(); })
        .then(function (blob) {
          downloadBlob(blob, (document.getElementById('rpTitle').value || 'report') + ext);
        }).catch(function (e) { toast(I18N.exportFailed + ': ' + e.message, true); });
    };
    if (state.mode === 'sql') { ackThen(run); } else { run(); }
  }

  // Export the client-computed pivot matrix via the grid-export endpoint.
  function exportPivot() {
    var ex = ReportingViz.getPivotExport();
    if (!ex || !ex.rows.length) { toast(I18N.nothingToExport); return; }
    var fmt = exportFormat();
    var ext = fmt === 'csv' ? '.csv' : '.xlsx';
    var title = document.getElementById('rpTitle').value || 'pivot';
    var gridBody = { columns: ex.columns, rows: ex.rows, title: title, format: fmt };
    if (fmt === 'xlsx') {
      var png = window.ReportingViz && ReportingViz.chartPngDataUrl();
      if (png) gridBody.chartImage = png;
    }
    api('/api/reporting/export/grid', {
      method: 'POST',
      body: JSON.stringify(gridBody),
    }).then(function (res) { return res.blob(); })
      .then(function (blob) { downloadBlob(blob, title + ext); })
      .catch(function (e) { toast(I18N.exportFailed + ': ' + e.message, true); });
  }

  // Export what's on screen: chart -> PNG, pivot -> matrix, grid -> raw rows.
  function exportCurrent() {
    if (state.view === 'chart') {
      var fn = (document.getElementById('rpTitle').value || 'chart') + '.png';
      if (!ReportingViz.exportChartPng(fn)) { toast(I18N.nothingToExport); }
      return;
    }
    if (state.view === 'pivot') { exportPivot(); return; }
    exportGridRows();
  }

  function loadSources() {
    ReportingCatalog.sources().then(function (sources) {
      var sel = document.getElementById('rpSource');
      sel.innerHTML = '';
      state.sourcesById = {};
      sources.forEach(function (s) { state.sourcesById[s.id] = s; });
      state.sqlSources = sources.filter(function (s) { return s.kind === 'sql'; });
      // Ack is per-user, identical across SQL targets — track via the first one.
      state.sqlSource = state.sqlSources[0] || null;
      var curated = sources.filter(function (s) { return s.kind !== 'sql'; });
      var sqlBtn = document.getElementById('rpModeSql');
      if (state.sqlSources.length) {
        sqlBtn.disabled = false;
        sqlBtn.removeAttribute('title');
        var tsel = document.getElementById('rpSqlTarget');
        tsel.innerHTML = '';
        state.sqlSources.forEach(function (s) {
          var topt = document.createElement('option');
          topt.value = s.target || 'statistics';
          // Name the real database ("RuntimeDatabase", "SYDOC_Statistik",
          // "Generali") -- the same names the Sources rail cards show. The
          // registry label is only the fallback. A target whose read-only
          // login isn't provisioned yet says so rather than 503-ing on Run.
          topt.textContent = (s.db || s.label) +
            (s.configured === false ? ' — ' + I18N.sqlTargetUnconfigured : '');
          if (s.configured === false) topt.disabled = true;
          tsel.appendChild(topt);
        });
        var firstOk = state.sqlSources.find(function (s) { return s.configured !== false; });
        if (firstOk) tsel.value = firstOk.target || 'statistics';
      }
      // Publish the databases Live SQL can reach so the source visualizer
      // (static/js/reporting_schema.js) knows whether to offer its per-table
      // Query button -- it has a database name, not a target id.
      window.ReportingSqlDbs = {};
      state.sqlSources.forEach(function (s) {
        if (s.db && s.configured !== false) window.ReportingSqlDbs[s.db.toLowerCase()] = true;
      });
      curated.forEach(function (s) {
        var opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.label;
        sel.appendChild(opt);
      });
      function pick() {
        var s = curated.find(function (x) { return x.id === sel.value; });
        if (!s) return;
        state.source = s.id;
        state.fields = s.fields || [];
        setProcessScope(s.processes || [], null);
        state.columns = [];
        // The previous source's filters reference fields that may not exist
        // on the new source (or mean something different) — drop them so a
        // source switch can't leave stale chips that 400 every subsequent Run.
        state.filters = [];
        renderFields();
        renderWells();
        renderFilters();
        // Re-derive the per-source metric list (prunes now-unavailable picks).
        refreshAvailableMetrics();
      }
      sel.onchange = pick;
      if (curated.length) pick();
    }).catch(function (e) {
      console.error(I18N.couldNotLoadSources + ':', e.message);
    });
  }

  function run() {
    showRunLoading();
    // A new run supersedes any open drill drawer — it shows rows behind the
    // PREVIOUS result and would sit stale over the new one.
    if (window.ReportingDrill) ReportingDrill.close();
    // Captured here (not recomputed from live builder state in renderResults)
    // so drill-through always transforms the definition that actually
    // produced the rows on screen, even if the builder is edited afterwards.
    var def = buildDefinition();
    var runT0 = performance.now();
    return api('/api/reporting/run', { method: 'POST', body: JSON.stringify(def) })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        endRunLoading();
        state.lastDef = def;
        renderResults(data);
        showTiming(data.rowCount, performance.now() - runT0);
      })
      .catch(function (e) { endRunLoading(); showError(e.message, e.detail); });
  }

  function addFilter() {
    var first = state.fields.find(function (f) { return f.filterable && isFieldAvailable(f); });
    if (!first) return;
    state.filters.push({ field: first.field, op: 'eq', value: '' });
    renderFilters();
  }

  function renderFilters() {
    var box = document.getElementById('rpWellFilters');
    box.innerHTML = '';
    state.filters.forEach(function (f, i) {
      var row = document.createElement('div');
      row.className = 'reporting-filter-row';

      var fld = document.createElement('select');
      state.fields.filter(function (x) {
        return x.filterable && isFieldAvailable(x);
      }).forEach(function (x) {
        var opt = document.createElement('option');
        opt.value = x.field;
        opt.textContent = x.label;
        fld.appendChild(opt);
      });
      fld.value = f.field;
      // Re-render when field changes so flatpickr/presets initialize correctly.
      // Also reset op to 'eq' so a token-shaped value can't survive a switch to
      // a non-date field and 400 on run.
      fld.onchange = function (e) { f.field = e.target.value; f.op = 'eq'; f.value = ''; renderFilters(); };

      var fieldMeta = state.fields.find(function (x) { return x.field === f.field; });
      var isDateField = !!(fieldMeta && (/date/i.test(fieldMeta.type) || fieldMeta.grainable));
      var tokenActive = isDateField && f.value && typeof f.value === 'object'
        && !Array.isArray(f.value) && typeof f.value.token === 'string';

      var preset = null, nInput = null;
      if (isDateField) {
        preset = document.createElement('select');
        var co = document.createElement('option');
        co.value = '';
        co.textContent = CUSTOM_DATES_LABEL;
        preset.appendChild(co);
        DATE_TOKEN_PRESETS.forEach(function (t) {
          var o = document.createElement('option');
          o.value = t[0];
          o.textContent = t[1];
          preset.appendChild(o);
        });
        nInput = document.createElement('input');
        nInput.type = 'number';
        nInput.min = '1';
        nInput.max = '366';
        nInput.hidden = true;
        if (tokenActive) {
          preset.value = f.value.token;
          if (f.value.token === 'last_n_days') {
            nInput.hidden = false;
            nInput.value = f.value.n || 30;
          }
        }
        preset.onchange = function () {
          if (!preset.value) { f.op = 'eq'; f.value = ''; renderFilters(); return; }
          f.op = 'between';
          f.value = preset.value === 'last_n_days'
            ? { token: 'last_n_days', n: parseInt(nInput.value, 10) || 30 }
            : { token: preset.value };
          renderFilters();
        };
        nInput.oninput = function () {
          if (f.value && f.value.token === 'last_n_days') {
            f.value.n = Math.max(1, Math.min(366, parseInt(nInput.value, 10) || 30));
          }
        };
      }

      var op = document.createElement('select');
      ['eq', 'ne', 'contains', 'starts_with', 'gt', 'gte', 'lt', 'lte',
        'is_null', 'is_not_null'].forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o;                        // payload contract: raw op code
        opt.textContent = OP_LABELS[o] || o;  // label localizes, value doesn't
        op.appendChild(opt);
      });
      op.value = tokenActive ? 'eq' : f.op;
      op.onchange = function (e) { f.op = e.target.value; };
      op.hidden = tokenActive;

      var val = document.createElement('input');
      val.value = (!tokenActive && f.value != null) ? f.value : '';
      val.oninput = function (e) { f.value = e.target.value; };
      val.hidden = tokenActive;

      // Initialize flatpickr for date/datetime fields if the library is present.
      if (!tokenActive && fieldMeta && /date/i.test(fieldMeta.type)
          && typeof flatpickr === 'function') {
        var fpOpts = { allowInput: true, onChange: function (d, s) { f.value = s; } };
        if (/time|datetime/i.test(fieldMeta.type)) {
          fpOpts.enableTime = true;
          fpOpts.dateFormat = 'Y-m-d H:i';
        } else {
          fpOpts.dateFormat = 'Y-m-d';
        }
        flatpickr(val, fpOpts);
      }

      var rm = document.createElement('button');
      rm.textContent = '×';
      rm.onclick = function () { state.filters.splice(i, 1); renderFilters(); };

      row.appendChild(fld);
      if (preset) row.appendChild(preset);
      row.appendChild(op);
      row.appendChild(val);
      if (nInput) row.appendChild(nInput);
      row.appendChild(rm);
      box.appendChild(row);
    });
  }

  function addSort() {
    // Sort fields must be among the selected columns (the backend rejects sort
    // fields not in the projection), so seed from the first selected column.
    if (!state.columns.length) return;
    state.sort.push({ field: state.columns[0].field, dir: 'asc' });
    renderSort();
  }

  function renderSort() {
    var box = document.getElementById('rpWellSort');
    box.innerHTML = '';
    state.sort.forEach(function (s, i) {
      var row = document.createElement('div');
      row.className = 'reporting-filter-row';

      var fld = document.createElement('select');
      state.columns.forEach(function (c) {
        var opt = document.createElement('option');
        opt.value = c.field;
        opt.textContent = c.header || c.label || c.field;
        fld.appendChild(opt);
      });
      fld.value = s.field;
      fld.onchange = function (e) { s.field = e.target.value; };

      var dir = document.createElement('select');
      ['asc', 'desc'].forEach(function (d) {
        var opt = document.createElement('option');
        opt.value = d;
        opt.textContent = d;
        dir.appendChild(opt);
      });
      dir.value = s.dir;
      dir.onchange = function (e) { s.dir = e.target.value; };

      var rm = document.createElement('button');
      rm.textContent = '×';
      rm.onclick = function () { state.sort.splice(i, 1); renderSort(); };

      row.appendChild(fld);
      row.appendChild(dir);
      row.appendChild(rm);
      box.appendChild(row);
    });
  }

  // ---- Metrics ----

  // Look up a selected metric's display metadata for the current source.
  function metricMeta(code) {
    return state.availableMetrics.find(function (m) { return m.code === code; })
      || { code: code, label: code };
  }

  // Derive the available metrics for the currently-selected source from the
  // cached map, and prune any selected codes the new source doesn't offer.
  function refreshAvailableMetrics() {
    var map = state.metricsBySource || {};
    state.availableMetrics = map[state.source] || [];
    var codes = {};
    state.availableMetrics.forEach(function (m) { codes[m.code] = true; });
    state.metrics = state.metrics.filter(function (c) { return codes[c]; });
    renderMetrics();
  }

  // Fetch the full accessible-metrics map once and cache it, then derive the
  // per-source list. A failed fetch is non-fatal: treat as "no metrics".
  function loadMetrics() {
    ReportingCatalog.metrics()
      .then(function (map) {
        state.metricsBySource = map || {};
        refreshAvailableMetrics();
      }).catch(function (e) {
        console.error(I18N.couldNotLoadMetrics + ':', e.message);
        state.metricsBySource = {};
        refreshAvailableMetrics();
      });
  }

  function renderMetrics() {
    var ul = document.getElementById('rpWellMetrics');
    ul.innerHTML = '';
    state.metrics.forEach(function (code, i) {
      var li = document.createElement('li');
      li.className = 'reporting-metric-row';
      // A <select> per row (current code + any unselected codes) lets the user
      // swap which metric this row is — same pattern as the Sort well's field
      // picker. If the code isn't in the catalog (stale saved report), still
      // show it as a synthetic option so the row round-trips.
      var sel = document.createElement('select');
      sel.setAttribute('data-testid', 'reporting-metric-select');
      var opts = state.availableMetrics.filter(function (m) {
        return m.code === code || state.metrics.indexOf(m.code) === -1;
      });
      if (!opts.find(function (m) { return m.code === code; })) {
        opts = [metricMeta(code)].concat(opts);
      }
      opts.forEach(function (m) {
        var opt = document.createElement('option');
        opt.value = m.code;
        opt.textContent = m.label || m.code;
        sel.appendChild(opt);
      });
      sel.value = code;
      sel.onchange = function (e) { state.metrics[i] = e.target.value; renderMetrics(); };
      li.appendChild(sel);
      var rm = document.createElement('button');
      rm.type = 'button';
      rm.textContent = '×';
      rm.onclick = function () { state.metrics.splice(i, 1); renderMetrics(); };
      li.appendChild(rm);
      ul.appendChild(li);
    });
    // The hint explains that Columns become the grouping once a metric is picked.
    document.getElementById('rpMetricHint').hidden = state.metrics.length === 0;
    var addBtn = document.getElementById('rpAddMetric');
    // No remaining unselected metrics for this source => nothing to add.
    var remaining = state.availableMetrics.filter(function (m) {
      return state.metrics.indexOf(m.code) === -1;
    });
    addBtn.disabled = remaining.length === 0;
  }

  // Add a metric. Mirrors addSort/addFilter: append the first available
  // unselected code, then re-render so its row appears with a pick <select>.
  function addMetric() {
    var remaining = state.availableMetrics.filter(function (m) {
      return state.metrics.indexOf(m.code) === -1;
    });
    if (!remaining.length) return;
    state.metrics.push(remaining[0].code);
    renderMetrics();
  }

  function loadReports() {
    api('/api/reporting/reports').then(function (res) { return res.json(); })
      .then(function (reports) {
        var sel = document.getElementById('rpSavedReports');
        var current = sel.value;
        sel.innerHTML = '';
        var ph = document.createElement('option');
        ph.value = '';
        ph.textContent = I18N.savedReportsPlaceholder;
        sel.appendChild(ph);
        function addOpt(group, r) {
          var opt = document.createElement('option');
          opt.value = r.id;
          var suffix = (r.kind === 'sql' ? ' (SQL)' : '');
          if (!r.owned && r.ownerName) suffix += ' — ' + r.ownerName;
          // Owner-side 'shared' tag: org-wide visibility OR an explicit
          // per-user grant (which leaves Visibility = 'private').
          else if (r.owned && (r.visibility === 'shared' || r.sharedCount))
            suffix += ' · ' + I18N.sharedSuffix;
          opt.textContent = r.name + suffix;
          opt.dataset.owned = r.owned ? '1' : '0';
          opt.dataset.canEdit = r.canEdit ? '1' : '0';
          group.appendChild(opt);
        }
        // D17: dashboards can't be represented by the Advanced builder's
        // definition shape (unlike sql-kind reports, which just get an
        // ' (SQL)' suffix above and stay pickable) -- drop the row entirely.
        var buildable = (reports || []).filter(function (r) { return r.kind !== 'dashboard'; });
        var mine = buildable.filter(function (r) { return r.owned; });
        var shared = buildable.filter(function (r) { return !r.owned; });
        if (mine.length) {
          var g1 = document.createElement('optgroup');
          g1.label = I18N.myReports;
          mine.forEach(function (r) { addOpt(g1, r); });
          sel.appendChild(g1);
        }
        if (shared.length) {
          var g2 = document.createElement('optgroup');
          g2.label = I18N.sharedWithMe;
          shared.forEach(function (r) { addOpt(g2, r); });
          sel.appendChild(g2);
        }
        if (current) sel.value = current;
        updateShareButton();
      }).catch(function (e) {
        console.error(I18N.couldNotLoadSavedReports + ':', e.message);
      });
  }

  // The Share/Schedule buttons only apply to a report the caller owns.
  function updateShareButton() {
    var sel = document.getElementById('rpSavedReports');
    var opt = sel.options[sel.selectedIndex];
    var owned = !!(opt && opt.dataset && opt.dataset.owned === '1');
    document.getElementById('rpShare').disabled = !owned;
    var sched = document.getElementById('rpSchedule');
    if (sched) sched.disabled = !owned;
  }

  // Restore a saved definition into the builder (curated) or SQL editor.
  function applyDefinition(def, name, id) {
    state.currentReportId = id || null;
    state.currentReportName = name || null;
    document.getElementById('rpTitle').value = name || def.title || '';
    if (def.kind === 'sql') {
      setMode('sql');
      var tsel = document.getElementById('rpSqlTarget');
      if (def.target) tsel.value = def.target;
      document.getElementById('rpSqlEditor').value = def.sql || '';
      return;
    }
    setMode('table');
    state.source = def.source || state.source;
    var src = state.sourcesById[state.source];
    if (src) {
      document.getElementById('rpSource').value = src.id;
      state.fields = src.fields || [];
      // Restore the saved process scope (def.scope) against this source's
      // currently-allowed processes; falls back to "all" when absent.
      setProcessScope(src.processes || [], def.scope);
    }
    // Re-hydrate column metadata (label/type/filterable) from the live catalog;
    // a field that left the catalog still loads with its raw key as the label.
    state.columns = (def.columns || []).map(function (c) {
      var meta = state.fields.find(function (f) { return f.field === c.field; })
        || { field: c.field, label: c.field };
      var col = Object.assign({}, meta, { header: c.header || meta.label });
      if (c.grain) col.grain = c.grain;
      return col;
    });
    state.filters = (def.filters || []).map(function (f) { return Object.assign({}, f); });
    state.sort = (def.sort || []).map(function (s) { return Object.assign({}, s); });
    // Restore selected metrics (def.metrics = [{metric: code}, ...]); derive the
    // available list for the restored source, then keep only codes it still offers.
    state.availableMetrics = (state.metricsBySource || {})[state.source] || [];
    var availCodes = {};
    state.availableMetrics.forEach(function (m) { availCodes[m.code] = true; });
    state.metrics = (def.metrics || [])
      .map(function (m) { return m && m.metric; })
      .filter(function (c) { return c && availCodes[c]; });
    state.forecast = (def.forecast && def.forecast.enabled)
      ? { enabled: true, horizon: def.forecast.horizon || 'auto' } : null;
    document.getElementById('rpSubtitle').value = def.subtitle || '';
    renderFields();
    renderWells();
    renderFilters();
    renderMetrics();
  }

  // Open an AI definition in the builder, run it, then show it as the hinted chart.
  function applyDefinitionAndChart(def, hint) {
    applyDefinition(def, def.title || I18N.aiReport, null);
    // Clear any prior result so a failed run (run() swallows errors) can't leave
    // stale data that the guard below would chart against.
    state.lastResult = null;
    var p = run();
    if (p && p.then) {
      p.then(function () {
        if (!hint || !state.lastResult || !state.lastResult.rows.length) return;
        setView('chart');
        if (window.ReportingViz && ReportingViz.applyChartHint) ReportingViz.applyChartHint(hint);
      });
    }
  }

  function loadSelectedReport() {
    var id = document.getElementById('rpSavedReports').value;
    if (!id) return;
    api('/api/reporting/reports/' + id).then(function (res) { return res.json(); })
      .then(function (data) {
        applyDefinition(data.definition || {}, data.name, data.id);
        state.currentReportOwned = !!data.owned;
        state.currentReportCanEdit = !!data.canEdit;
      })
      .catch(function (e) { showError(e.message, e.detail); });
  }

  function renameSelectedReport() {
    var sel = document.getElementById('rpSavedReports');
    var id = sel.value;
    if (!id) return;
    var current = sel.options[sel.selectedIndex].textContent.replace(/ \(SQL\)$/, '');
    promptName(I18N.newName, current).then(function (name) {
      if (!name || name === current) return;
      // Name-only change; PUT requires the definition too, so fetch it first.
      api('/api/reporting/reports/' + id).then(function (res) { return res.json(); })
        .then(function (data) {
          return api('/api/reporting/reports/' + id, {
            method: 'PUT',
            body: JSON.stringify({ name: name, definition: data.definition }),
          });
        }).then(function () { loadReports(); })
        .catch(function (e) { toast(I18N.renameFailed + ': ' + e.message, true); });
    });
  }

  function deleteSelectedReport() {
    var sel = document.getElementById('rpSavedReports');
    var id = sel.value;
    if (!id) return;
    if (!window.confirm(I18N.deleteReportConfirm)) return;
    api('/api/reporting/reports/' + id, { method: 'DELETE' })
      .then(function () {
        if (String(state.currentReportId) === String(id)) {
          state.currentReportId = null;
          state.currentReportName = null;
        }
        loadReports();
      }).catch(function (e) { toast(I18N.deleteFailed + ': ' + e.message, true); });
  }

  // ---- Sharing ----
  var shareReportId = null;

  // Also the entry point for the Console library card's "…" > Share menu
  // (exported as window.Reporting.openShareFor below).
  function openShareFor(id) {
    shareReportId = id;
    api('/api/reporting/reports/' + shareReportId + '/shares')
      .then(function (res) { return res.json(); })
      .then(function (data) {
        renderShareState(data);
        document.getElementById('rpShareModal').hidden = false;
      }).catch(function (e) { toast(e.message, true); });
  }

  function openShare() {
    var sel = document.getElementById('rpSavedReports');
    var opt = sel.options[sel.selectedIndex];
    if (!opt || opt.dataset.owned !== '1') return;
    openShareFor(sel.value);
  }

  function renderShareState(data) {
    var vis = data.visibility || 'private';
    Array.prototype.forEach.call(
      document.querySelectorAll('input[name="rpShareVis"]'),
      function (r) { r.checked = (r.value === vis); }
    );
    var list = document.getElementById('rpShareList');
    list.innerHTML = '';
    (data.shares || []).forEach(function (s) {
      var li = document.createElement('li');
      var name = document.createElement('span');
      name.className = 'reporting-share-name';
      name.textContent = s.name + (s.canEdit ? ' (' + I18N.canEdit + ')' : '');
      li.appendChild(name);
      var rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'reporting-link';
      rm.textContent = I18N.remove;
      rm.onclick = function () { removeShare(s.userId); };
      li.appendChild(rm);
      list.appendChild(li);
    });
    if (!(data.shares || []).length) {
      var empty = document.createElement('li');
      empty.className = 'reporting-share-empty';
      empty.textContent = I18N.notSharedYet;
      list.appendChild(empty);
    }
  }

  function postShare(body) {
    return api('/api/reporting/reports/' + shareReportId + '/shares', {
      method: 'POST', body: JSON.stringify(body),
    }).then(function (res) { return res.json(); })
      .then(function (data) { renderShareState(data); loadReports(); });
  }

  function removeShare(userId) {
    api('/api/reporting/reports/' + shareReportId + '/shares/' + userId, { method: 'DELETE' })
      .then(function (res) { return res.json(); })
      .then(function (data) { renderShareState(data); loadReports(); })
      .catch(function (e) { toast(e.message, true); });
  }

  document.getElementById('rpShare').addEventListener('click', openShare);
  document.getElementById('rpShareClose').addEventListener('click', function () {
    document.getElementById('rpShareModal').hidden = true;
  });
  // People search for the share input: debounced typeahead into the native
  // datalist (GET /api/reporting/share_targets, 2+ chars).
  var shareSuggestTimer = null;
  document.getElementById('rpShareUser').addEventListener('input', function () {
    var q = this.value.trim();
    clearTimeout(shareSuggestTimer);
    if (q.length < 2) return;
    shareSuggestTimer = setTimeout(function () {
      api('/api/reporting/share_targets?q=' + encodeURIComponent(q))
        .then(function (res) { return res.json(); })
        .then(function (rows) {
          var list = document.getElementById('rpShareUserList');
          list.innerHTML = '';
          (rows || []).forEach(function (u) {
            var opt = document.createElement('option');
            opt.value = u.username;
            opt.label = u.name;
            list.appendChild(opt);
          });
        }).catch(function () { /* typeahead only — never surface an error */ });
    }, 200);
  });
  document.getElementById('rpShareAdd').addEventListener('click', function () {
    var u = document.getElementById('rpShareUser').value.trim();
    if (!u) return;
    var canEdit = document.getElementById('rpShareCanEdit').checked;
    postShare({ user: u, canEdit: canEdit })
      .then(function () {
        document.getElementById('rpShareUser').value = '';
        document.getElementById('rpShareCanEdit').checked = false;
      }).catch(function (e) { toast(e.message, true); });
  });
  Array.prototype.forEach.call(
    document.querySelectorAll('input[name="rpShareVis"]'),
    function (r) {
      r.addEventListener('change', function () {
        if (r.checked) postShare({ visibility: r.value }).catch(function (e) { toast(e.message, true); });
      });
    }
  );
  document.getElementById('rpSavedReports').addEventListener('change', updateShareButton);

  // ---- Scheduling ----
  var scheduleReportId = null;
  var FREQ_LABELS = { daily: I18N.freqDaily, weekly: I18N.freqWeekly, monthly: I18N.freqMonthly };
  var ALERT_LABELS = { gt: '>', gte: '≥', lt: '<', lte: '≤' };

  function schedAlertChanged() {
    var alertOn = !!document.getElementById('rpSchedAlertOp').value;
    document.getElementById('rpSchedAlertValWrap').hidden = !alertOn;
    document.getElementById('rpSchedAlertHint').hidden = !alertOn;
  }

  function schedFreqChanged() {
    var freq = document.getElementById('rpSchedFreq').value;
    document.getElementById('rpSchedWeekdayWrap').hidden = freq !== 'weekly';
    document.getElementById('rpSchedDomWrap').hidden = freq !== 'monthly';
  }

  function openSchedule() {
    var sel = document.getElementById('rpSavedReports');
    var opt = sel.options[sel.selectedIndex];
    if (!opt || opt.dataset.owned !== '1') return;
    scheduleReportId = sel.value;
    schedFreqChanged();
    document.getElementById('rpSchedAlertOp').value = '';
    document.getElementById('rpSchedAlertVal').value = '0';
    schedAlertChanged();
    loadSchedules();
    document.getElementById('rpScheduleModal').hidden = false;
  }

  function loadSchedules() {
    api('/api/reporting/reports/' + scheduleReportId + '/schedules')
      .then(function (res) { return res.json(); })
      .then(renderSchedules).catch(function (e) { toast(e.message, true); });
  }

  function renderSchedules(list) {
    var box = document.getElementById('rpScheduleList');
    box.innerHTML = '';
    if (!(list || []).length) {
      var li = document.createElement('li');
      li.className = 'reporting-share-empty';
      li.textContent = I18N.noSchedulesYet;
      box.appendChild(li);
      return;
    }
    list.forEach(function (s) {
      var li = document.createElement('li');
      var t = (s.hour < 10 ? '0' : '') + s.hour + ':' + (s.minute < 10 ? '0' : '') + s.minute;
      var desc = (FREQ_LABELS[s.frequency] || s.frequency) + ' ' + t + ' UTC · ' +
        s.format.toUpperCase() + ' · ' + s.recipients +
        (s.alertOp ? ' · ' + I18N.onlyWhenTotal + ' ' +
          (ALERT_LABELS[s.alertOp] || s.alertOp) + ' ' + s.alertThreshold : '') +
        (s.enabled ? '' : ' (' + I18N.disabledSuffix + ')');
      var span = document.createElement('span');
      span.className = 'reporting-share-name';
      span.textContent = desc;
      li.appendChild(span);
      var tg = document.createElement('button');
      tg.type = 'button';
      tg.className = 'reporting-link';
      tg.dataset.testid = 'reporting-schedule-toggle';
      tg.textContent = s.enabled ? I18N.disable : I18N.enable;
      tg.onclick = function () { setScheduleEnabled(s, !s.enabled); };
      li.appendChild(tg);
      var rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'reporting-link';
      rm.textContent = I18N.remove;
      rm.onclick = function () { deleteSchedule(s.id); };
      li.appendChild(rm);
      box.appendChild(li);
    });
  }

  function addSchedule() {
    var freq = document.getElementById('rpSchedFreq').value;
    var time = (document.getElementById('rpSchedTime').value || '06:00').split(':');
    var body = {
      frequency: freq,
      hour: parseInt(time[0], 10) || 0,
      minute: parseInt(time[1], 10) || 0,
      format: document.getElementById('rpSchedFormat').value,
      recipients: document.getElementById('rpSchedRecipients').value,
      enabled: true,
    };
    if (freq === 'weekly') body.weekday = parseInt(document.getElementById('rpSchedWeekday').value, 10);
    if (freq === 'monthly') body.dayOfMonth = parseInt(document.getElementById('rpSchedDom').value, 10);
    var alertOp = document.getElementById('rpSchedAlertOp').value;
    if (alertOp) {
      body.alertOp = alertOp;
      body.alertThreshold = parseFloat(document.getElementById('rpSchedAlertVal').value) || 0;
    }
    api('/api/reporting/reports/' + scheduleReportId + '/schedules', {
      method: 'POST', body: JSON.stringify(body),
    }).then(function () {
      document.getElementById('rpSchedRecipients').value = '';
      loadSchedules();
    }).catch(function (e) { toast(e.message, true); });
  }

  function deleteSchedule(id) {
    api('/api/reporting/reports/' + scheduleReportId + '/schedules/' + id, { method: 'DELETE' })
      .then(loadSchedules).catch(function (e) { toast(e.message, true); });
  }

  // Flip Enabled via the (previously UI-less) PUT update endpoint. PUT is
  // full-replace and recomputes NextRunAt, so re-enabling re-anchors the next
  // run. Feedback goes through the in-page toast (the 2026-07 polish swept
  // the window.alert idiom away).
  function setScheduleEnabled(s, enabled) {
    var body = {
      frequency: s.frequency, hour: s.hour, minute: s.minute,
      format: s.format, recipients: s.recipients, enabled: enabled,
    };
    if (s.frequency === 'weekly') body.weekday = s.weekday;
    if (s.frequency === 'monthly') body.dayOfMonth = s.dayOfMonth;
    if (s.alertOp) { body.alertOp = s.alertOp; body.alertThreshold = s.alertThreshold; }
    api('/api/reporting/reports/' + scheduleReportId + '/schedules/' + s.id, {
      method: 'PUT', body: JSON.stringify(body),
    }).then(loadSchedules).catch(function (e) { toast(e.message, true); });
  }

  var rpSchedule = document.getElementById('rpSchedule');
  if (rpSchedule) {
    rpSchedule.addEventListener('click', openSchedule);
    document.getElementById('rpSchedFreq').addEventListener('change', schedFreqChanged);
    document.getElementById('rpSchedAlertOp').addEventListener('change', schedAlertChanged);
    document.getElementById('rpSchedAdd').addEventListener('click', addSchedule);
    document.getElementById('rpScheduleClose').addEventListener('click', function () {
      document.getElementById('rpScheduleModal').hidden = true;
    });
  }

  document.getElementById('rpViewGrid').addEventListener('click', function () { setView('grid'); });
  document.getElementById('rpViewChart').addEventListener('click', function () { setView('chart'); });
  document.getElementById('rpViewPivot').addEventListener('click', function () { setView('pivot'); });
  document.getElementById('rpLoad').addEventListener('click', loadSelectedReport);
  document.getElementById('rpRename').addEventListener('click', renameSelectedReport);
  document.getElementById('rpDelete').addEventListener('click', deleteSelectedReport);
  document.getElementById('rpFieldSearch').addEventListener('input', renderFields);
  document.getElementById('rpRun').addEventListener('click', function () {
    if (state.mode === 'sql') { runSql(); } else { run(); }
  });
  document.getElementById('rpSave').addEventListener('click', function () { save(false); });
  document.getElementById('rpSaveAs').addEventListener('click', function () { save(true); });
  document.getElementById('rpExport').addEventListener('click', exportCurrent);
  document.getElementById('rpModeTable').addEventListener('click', function () { setMode('table'); });
  document.getElementById('rpModeSql').addEventListener('click', function () { setMode('sql'); });

  // "Query" button on a table in the source visualizer (reporting_schema.js):
  // land in Advanced's SQL mode on the target that reads that database, with
  // a SELECT TOP (100) for the table already written, and run it. `db` is the
  // real database name (the visualizer's title / the rail card's data-db) --
  // matched against the `db` each SQL source reports, so this needs no
  // knowledge of which target id belongs to which database.
  document.addEventListener('rc:sqlquery', function (e) {
    var db = e.detail && e.detail.db;
    var table = e.detail && e.detail.table;
    if (!table) return;
    var src = state.sqlSources.find(function (s) {
      return s.db && db && s.db.toLowerCase() === String(db).toLowerCase();
    });
    if (!src || src.configured === false) {
      toast(I18N.sqlTargetUnavailable.replace('{db}', db || '?'));
      return;
    }
    if (window.ReportingTabs && window.ReportingTabs.current() !== 'advanced') {
      window.ReportingTabs.show('advanced');
    }
    setMode('sql');
    document.getElementById('rpSqlTarget').value = src.target || 'statistics';
    // [schema].[name] both bracketed -- a table called "order" or "user" is
    // otherwise a syntax error the moment the user presses Run.
    var parts = String(table).split('.');
    var qualified = parts.length > 1
      ? '[' + parts[0] + '].[' + parts.slice(1).join('.') + ']'
      : '[' + parts[0] + ']';
    document.getElementById('rpSqlEditor').value = 'SELECT TOP (100) * FROM ' + qualified;
    document.getElementById('rpTitle').value = table;
    runSql();
  });
  document.getElementById('rpAddFilter').addEventListener('click', addFilter);
  document.getElementById('rpAddSort').addEventListener('click', addSort);
  document.getElementById('rpAddMetric').addEventListener('click', addMetric);

  // Process-scope dropdown: toggle on the button, close on an outside click.
  var rpScopeBtn = document.getElementById('rpScopeBtn');
  if (rpScopeBtn) {
    rpScopeBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleScopeMenu(); });
    document.addEventListener('click', function (e) {
      var wrap = document.getElementById('rpScopeWrap');
      if (wrap && !wrap.contains(e.target)) toggleScopeMenu(false);
    });
    // Escape (from the button or any checkbox in the menu) closes + returns focus.
    document.getElementById('rpScopeWrap').addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { toggleScopeMenu(false); rpScopeBtn.focus(); }
    });
  }

  var rpShowSqlBtn = document.getElementById('rpShowSql');
  if (rpShowSqlBtn) {
    rpShowSqlBtn.addEventListener('click', function () {
      if (!state._lastSql) return;
      var view = document.getElementById('rpSqlView');
      view.hidden = !view.hidden;
      this.textContent = view.hidden ? I18N.showQuery : I18N.hideQuery;
      if (!view.hidden) {
        // sqlDisplay = pretty SQL with the parameter literals inlined
        // server-side (display + copy only; execution stays parameterized).
        ReportingSqlFormat.render(document.getElementById('rpSqlText'),
          ReportingSqlFormat.displayText({
            sql: state._lastSql, sqlPretty: state._lastSqlPretty,
            sqlDisplay: state._lastSqlDisplay, params: state._lastParams
          }));
      }
    });
  }
  var rpSqlPeekBtn = document.getElementById('rpSqlPeek');
  if (rpSqlPeekBtn) {
    rpSqlPeekBtn.addEventListener('click', function () {
      // Same reveal path as the Show-query button — no duplicated
      // panel-fill logic (L9): the peek footer just delegates the click.
      if (rpShowSqlBtn) rpShowSqlBtn.click();
    });
  }
  var rpSqlViewCopyBtn = document.getElementById('rpSqlViewCopy');
  if (rpSqlViewCopyBtn) {
    rpSqlViewCopyBtn.addEventListener('click', function () {
      if (!state._lastSql) return;
      var text = ReportingSqlFormat.copyText({
        sql: state._lastSql, sqlDisplay: state._lastSqlDisplay,
        params: state._lastParams
      });
      var btn = this;
      navigator.clipboard.writeText(text).then(function () {
        var prev = btn.textContent;
        btn.textContent = I18N.copied;
        setTimeout(function () { btn.textContent = prev; }, 1200);
      }).catch(function () { /* clipboard unavailable */ });
    });
  }

  loadMetrics();
  loadSources();
  loadReports();
  window.Reporting = Object.assign(window.Reporting || {}, { applyDefinition: applyDefinition, setMode: setMode, applyDefinitionAndChart: applyDefinitionAndChart, run: run, openShareFor: openShareFor });
}());
