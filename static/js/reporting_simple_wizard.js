// Reporting Simple pane -- wizard (Beautification Phase 2b, Task 8).
// Split out of reporting_simple.js: the editable AI filter chips plus the
// 4-step report-building wizard (measure/scope/breakdown/time). Shares
// state via window.RS (see reporting_simple.js's own top-of-file comment
// for the RS.state/RS.el/RS.esc/RS.api/RS.I18N contract). This file is
// loaded BEFORE reporting_simple.js (see _reporting_simple_js.html) --
// every RS.* reference below into things reporting_simple.js/
// reporting_simple_library.js/reporting_simple_result.js define (RS.setView,
// RS.runCurrent, RS.loadMetricsCatalog) is only ever called from inside a
// function body, never at top-level load time, so the load order is safe:
// by the time any of these functions is actually invoked (a user action),
// every file has already run.
//
// TOKEN_LABELS/OP_LABELS/WIZ_STEPS/WIZ_TIME_TOKEN_LABELS below are the
// exception -- they read RS.I18N at module-load time (not deferred inside a
// function), so this file cannot rely on reporting_simple.js (which sets
// RS.I18N) having already run when THIS file loads first. The fallback
// below makes RS.I18N available regardless of load order; reporting_simple.
// js's own `RS.I18N = window.NX_I18N_REPORTING_SIMPLE` later is a harmless
// no-op re-assignment of the same value.
(function () {
  window.RS = window.RS || {};
  RS.I18N = RS.I18N || window.NX_I18N_REPORTING_SIMPLE;
  // Same load-order problem as RS.I18N above: this file's own bottom-of-file
  // event-listener wiring block calls RS.el(...) at top level (module-load
  // time), before reporting_simple.js (which normally sets RS.el) has run --
  // it loads last (see _reporting_simple_js.html). window.NX.el is nx_core.js's
  // real implementation and nx_core.js always loads first (templates/_header.
  // html), so this fallback is safe regardless of script order; core's own
  // later `RS.el = window.NX.el` is a harmless no-op re-assignment.
  RS.el = RS.el || window.NX.el;
  // Same load-order problem, extended to the other two nx_core.js aliases and
  // to RS.state -- see reporting_simple.js's top-of-file comment for what
  // those normally hold. Nothing in this file reads them at module-load time
  // today, but the fallback keeps that an invariant rather than a thing to
  // remember next time someone adds top-level code here.
  RS.esc = RS.esc || window.NX.esc;
  RS.api = RS.api || window.NX.apiSafe;
  RS.state = RS.state || {};

  // Wizard category-dimension curation (docprocessing only). Process first
  // (each Octo process = an actual client, so this is the per-client
  // breakdown), then the preferred business dimensions; noise hidden;
  // table sources are untouched.
  var DOCPROC_DIM_ORDER = ['processname', 'pagecount', 'doctype', 'docsource', 'crdname',
                           'forwarding', 'ownernr', 'propertynr', 'registered', 'tenancynr'];
  var DOCPROC_DIM_HIDE = { bankpk: 1, crdno: 1, docbarcode: 1,
                           docdate: 1, workitem_id: 1 };
  // Everything else docprocessing exposes folds behind "Show advanced fields".
  // Table sources flag theirs in ColumnsJSON ("advanced":true) instead.
  var DOCPROC_DIM_MAIN = { processname: 1, pagecount: 1, doctype: 1, docsource: 1, crdname: 1 };

  // One-line transparency note under the title of AI-built reports: the
  // model's own explanation plus the filters/scope it chose, so a wrong guess
  // (bad date range, wrong process) is visible instead of silently rendering
  // an empty table.
  // Relative-date tokens (nx_lib/reporting/tokens.py) — humanized labels for
  // chips/summary lines. A token value is {token: '<name>'[, n: <int>]}.
  var TOKEN_LABELS = {
    today: RS.I18N.tokenToday, yesterday: RS.I18N.tokenYesterday,
    this_week: RS.I18N.thisWeek, last_week: RS.I18N.lastWeek,
    this_month: RS.I18N.thisMonth, last_month: RS.I18N.lastMonth,
    this_quarter: RS.I18N.thisQuarter, last_quarter: RS.I18N.lastQuarter,
    last_3_months: RS.I18N.last3Months, this_year: RS.I18N.thisYear,
    last_year: RS.I18N.lastYear, last_n_days: RS.I18N.lastNDays
  };
  function isTokenValue(v) {
    return !!v && typeof v === 'object' && !Array.isArray(v) && typeof v.token === 'string';
  }
  function tokenLabel(v) {
    if (!v || typeof v.token !== 'string') return '';
    var lbl = TOKEN_LABELS[v.token] || v.token;
    return v.token === 'last_n_days' ? lbl.replace('{n}', v.n) : lbl;
  }
  RS.tokenLabel = tokenLabel;

  // ----- Editable AI chips -----
  function fieldMetaFor(def, fieldKey) {
    var src = (RS.state.sources || []).find(function (s) { return s.id === def.source; });
    return ((src && src.fields) || []).find(function (f) { return f.field === fieldKey; });
  }
  RS.fieldMetaFor = fieldMetaFor;

  function chipValueLabel(v, op) {
    if (isTokenValue(v)) return tokenLabel(v);
    // 'in'/'not_in' carry a value LIST, not a range — a comma reads honestly;
    // '→' is reserved for an actual between-range so the two can't be confused.
    if (Array.isArray(v)) return v.join(op === 'in' || op === 'not_in' ? ', ' : ' → ');
    return v === null || v === undefined ? '' : String(v);
  }

  // Filter-op labels for chips — mirrored in _reporting_js.html's OP_LABELS
  // with the same msgids, so the two maps can never translate apart.
  var OP_LABELS = {
    eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤',
    between: RS.I18N.opBetween, 'in': RS.I18N.opIn, not_in: RS.I18N.opNotIn,
    contains: RS.I18N.opContains, starts_with: RS.I18N.opStartsWith,
    is_null: RS.I18N.opIsEmpty, is_not_null: RS.I18N.opIsNotEmpty
  };

  function chip(text, onEdit, onRemove) {
    var c = document.createElement('span');
    c.className = 'rs-chip';
    c.setAttribute('data-testid', 'rs-chip');
    var t = document.createElement('span');
    t.textContent = text;
    c.appendChild(t);
    if (onRemove) {
      var x = document.createElement('span');
      x.className = 'rs-chip-x';
      x.setAttribute('data-testid', 'rs-chip-remove');
      x.textContent = '×';
      x.addEventListener('click', function (e) { e.stopPropagation(); onRemove(); });
      c.appendChild(x);
    }
    if (onEdit) {
      // A clickable <span> is invisible to the keyboard — give it button
      // semantics so Tab reaches it and Enter/Space opens the editor.
      c.tabIndex = 0;
      c.setAttribute('role', 'button');
      c.addEventListener('click', function () { onEdit(c); });
      c.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onEdit(c); }
      });
    }
    return c;
  }

  // Swap a chip for its inline editor and give the editor a way out. Without
  // this the only exits were Apply or a full re-render — clicking elsewhere or
  // pressing Escape left the popover stuck open (escape-routes, modal-escape).
  function openChipEditor(chipEl, box) {
    chipEl.replaceWith(box);
    function close() {
      document.removeEventListener('mousedown', onDoc, true);
      document.removeEventListener('keydown', onKey, true);
      if (box.isConnected) box.replaceWith(chipEl);
    }
    function onDoc(e) {
      // Apply re-renders the chip row, which disconnects the box — drop the
      // listeners rather than resurrecting a stale chip over the new row.
      if (!box.isConnected) {
        document.removeEventListener('mousedown', onDoc, true);
        document.removeEventListener('keydown', onKey, true);
        return;
      }
      if (!box.contains(e.target)) close();
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.stopPropagation(); close(); }
    }
    document.addEventListener('mousedown', onDoc, true);
    document.addEventListener('keydown', onKey, true);
  }

  function filterChipEditor(cur, f, chipEl) {
    // Value-LIST ops get a checkbox picker of the field's known values
    // (typing comma-separated process names by hand is hostile); every other
    // op keeps the text/preset editor.
    if (f.op === 'in' || f.op === 'not_in') {
      valueListChipEditor(cur, f, chipEl, null);
      return;
    }
    textChipEditor(cur, f, chipEl);
  }

  // Checkbox picker for 'in'/'not_in' values. Values come from the source's
  // process registry (processname) or /api/reporting/field_values (table
  // sources); falls back to the text editor when neither yields values.
  // opts: {allMeansNoFilter, onApply} — used by the process chip, which
  // treats "everything picked" as "no filter" and may add the filter lazily.
  async function valueListChipEditor(cur, f, chipEl, opts) {
    opts = opts || {};
    var box = document.createElement('span');
    box.className = 'rs-chip rs-chip-editor';
    box.setAttribute('data-testid', 'rs-chip-values');
    box.textContent = RS.I18N.loadingValues;
    openChipEditor(chipEl, box);
    var src = (RS.state.sources || []).find(function (s) { return s.id === cur.def.source; });
    var values = [], labels = {};
    if (f.field === 'processname' && src && (src.processes || []).length) {
      values = src.processes.slice();
    } else {
      var res = await RS.api('/api/reporting/field_values', {
        method: 'POST',
        body: JSON.stringify({ source: cur.def.source, field: f.field })
      });
      values = (res.ok && res.data && res.data.values) || [];
      labels = (res.ok && res.data && res.data.labels) || {};
    }
    if (!box.isConnected) return;
    if (!values.length) { textChipEditor(cur, f, box); return; }
    var selected = Array.isArray(f.value) ? f.value.slice()
      : (f.value === null || f.value === undefined ? [] : [f.value]);
    // A previously typed value the column no longer holds must stay pickable.
    selected.forEach(function (v) { if (values.indexOf(v) === -1) values.push(v); });
    box.textContent = '';
    var inputs = values.map(function (p) {
      var lbl = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = p;
      cb.checked = opts.allMeansNoFilter && !selected.length
        ? true : selected.indexOf(p) !== -1;
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + (labels[p] || p)));
      box.appendChild(lbl);
      return cb;
    });
    var ok = document.createElement('button');
    ok.className = 'reporting-btn';
    ok.setAttribute('data-testid', 'rs-chip-apply');
    ok.textContent = RS.I18N.chipApply;
    ok.addEventListener('click', function () {
      var picked = inputs.filter(function (c) { return c.checked; })
                         .map(function (c) { return c.value; });
      if (opts.allMeansNoFilter && picked.length === values.length) {
        var at = cur.def.filters.indexOf(f);
        if (at !== -1) cur.def.filters.splice(at, 1);
        RS.runCurrent();
        return;
      }
      if (!picked.length) return;   // an empty IN () matches nothing — keep editing
      f.value = picked;
      if (opts.onApply) opts.onApply(f);
      RS.runCurrent();
    });
    box.appendChild(ok);
  }

  function textChipEditor(cur, f, chipEl) {
    var box = document.createElement('span');
    box.className = 'rs-chip rs-chip-editor';
    var meta = fieldMetaFor(cur.def, f.field);
    var isDateField = !!(meta && (meta.grainable || /date/i.test(meta.type || '')));
    var preset = null;
    if (isDateField && typeof TOKEN_LABELS !== 'undefined') {
      preset = document.createElement('select');
      preset.setAttribute('data-testid', 'rs-chip-preset');
      var co = document.createElement('option');
      co.value = '';
      co.textContent = RS.I18N.custom;
      preset.appendChild(co);
      Object.keys(TOKEN_LABELS).forEach(function (k) {
        if (k === 'last_n_days') return;
        var o = document.createElement('option');
        o.value = k;
        o.textContent = TOKEN_LABELS[k];
        preset.appendChild(o);
      });
      if (isTokenValue(f.value)) preset.value = f.value.token;
      box.appendChild(preset);
    }
    var input = document.createElement('input');
    input.className = 'reporting-input';
    input.setAttribute('data-testid', 'rs-chip-input');
    input.value = Array.isArray(f.value) ? chipValueLabel(f.value, f.op)
      : isTokenValue(f.value) ? '' : chipValueLabel(f.value, f.op);
    input.hidden = !!(preset && preset.value);
    if (preset) {
      preset.onchange = function () { input.hidden = !!preset.value; };
    }
    var ok = document.createElement('button');
    ok.className = 'reporting-btn';
    ok.setAttribute('data-testid', 'rs-chip-apply');
    ok.textContent = RS.I18N.chipApply;
    ok.addEventListener('click', function () {
      if (preset && preset.value) {
        f.op = 'between';
        f.value = { token: preset.value };
        RS.runCurrent();
        return;
      }
      var v = input.value.trim();
      if (f.op === 'in' || f.op === 'not_in') {
        // Value LIST, not a range — keep op as-is, split back into a list.
        // Comma-separated (see chipValueLabel); tolerate a stray '→' too so
        // re-editing an older arrow-joined display doesn't lose values.
        var listParts = v.split(/[,→]/).map(function (s) { return s.trim(); }).filter(Boolean);
        if (listParts.length) f.value = listParts;
        // else empty input: leave value unchanged
      } else if (isTokenValue(f.value) || Array.isArray(f.value) || f.op === 'between') {
        var parts = v.split('→').map(function (s) { return s.trim(); }).filter(Boolean);
        if (parts.length === 2) { f.op = 'between'; f.value = parts; }
        else if (parts.length === 1) { f.op = 'eq'; f.value = parts[0]; }
        // else empty input: leave value unchanged
      } else {
        f.value = v;
      }
      RS.runCurrent();
    });
    box.appendChild(input);
    box.appendChild(ok);
    openChipEditor(chipEl, box);
    if (!input.hidden) input.focus();
  }

  async function processChipEditor(cur, chipEl) {
    await loadSourcesCatalog();
    if (!chipEl.isConnected) return;
    var src = (RS.state.sources || []).find(function (s) { return s.id === cur.def.source; });
    var all = (src && src.processes) || [];
    if (!all.length) return;
    var box = document.createElement('span');
    box.className = 'rs-chip rs-chip-editor';
    box.setAttribute('data-testid', 'rs-chip-procs');
    var selected = ((cur.def.scope || {}).processes || []);
    var inputs = all.map(function (p) {
      var lbl = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = p;
      cb.checked = !selected.length || selected.indexOf(p) !== -1;
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + p));
      box.appendChild(lbl);
      return cb;
    });
    var ok = document.createElement('button');
    ok.className = 'reporting-btn';
    ok.setAttribute('data-testid', 'rs-chip-apply');
    ok.textContent = RS.I18N.chipApply;
    ok.addEventListener('click', function () {
      var picked = inputs.filter(function (c) { return c.checked; })
                         .map(function (c) { return c.value; });
      cur.def.scope = cur.def.scope || { clients: [], processes: [] };
      cur.def.scope.processes = picked.length === all.length ? [] : picked;
      RS.runCurrent();
    });
    box.appendChild(ok);
    openChipEditor(chipEl, box);
  }

  function grainChipEditor(cur, col, chipEl) {
    var box = document.createElement('span');
    box.className = 'rs-chip rs-chip-editor';
    box.setAttribute('data-testid', 'rs-chip-grain');
    var sel = document.createElement('select');
    sel.className = 'reporting-input';
    [['day', RS.I18N.grainDay], ['week', RS.I18N.grainWeek], ['month', RS.I18N.grainMonth],
     ['quarter', RS.I18N.grainQuarter], ['year', RS.I18N.grainYear]].forEach(function (g) {
      var o = document.createElement('option');
      o.value = g[0]; o.textContent = g[1];
      sel.appendChild(o);
    });
    if (col.grain) sel.value = col.grain;
    var ok = document.createElement('button');
    ok.className = 'reporting-btn';
    ok.setAttribute('data-testid', 'rs-chip-grain-apply');
    ok.textContent = RS.I18N.chipApply;
    ok.addEventListener('click', function () {
      col.grain = sel.value;
      RS.runCurrent();
    });
    box.appendChild(sel);
    box.appendChild(ok);
    openChipEditor(chipEl, box);
  }

  function renderAiChips(cur) {
    var wrap = RS.el('rsChips');
    if (!wrap) return;
    wrap.innerHTML = '';
    // Chips are definition-driven — every Simple result (AI, wizard, library)
    // gets them; edits mutate the in-memory copy only (Save creates a new row).
    var hasDef = !!(cur && cur.def);
    wrap.hidden = !hasDef;
    if (!hasDef) return;
    var def = cur.def || {};
    def.filters = def.filters || [];
    // Sources without a process registry (table sources, e.g. backlog_history)
    // carry their process restriction as a plain in-filter on the
    // processFieldFor field. Render THAT as the process chip instead of a
    // duplicate filter chip next to a lying "Processes: all" (#178).
    var chipSrc = (RS.state.sources || []).find(function (s) { return s.id === def.source; });
    var pf = chipSrc ? processFieldFor(chipSrc) : null;
    var pfFilter = pf ? (def.filters || []).find(function (ft) {
      return ft.op === 'in' && ft.field === pf.field;
    }) || null : null;
    (def.filters || []).forEach(function (f) {
      if (f === pfFilter) return;
      var meta = fieldMetaFor(def, f.field);
      var parts = [(meta && meta.label) || f.field, OP_LABELS[f.op] || f.op];
      var vl = chipValueLabel(f.value, f.op);
      if (vl) parts.push(vl);        // is_null/is_not_null carry no value
      var label = parts.join(' ');
      wrap.appendChild(chip(
        label,
        function (chipEl) { filterChipEditor(cur, f, chipEl); },
        function () {
          def.filters.splice(def.filters.indexOf(f), 1);
          RS.runCurrent();
        }
      ));
    });
    if (!(def.filters || []).length) {
      var none = document.createElement('span');
      none.className = 'rs-chip rs-chip--empty';
      none.textContent = RS.I18N.aiNoFilters;
      wrap.appendChild(none);
    }
    if (pf) {
      var pfVals = (pfFilter && pfFilter.value) || [];
      wrap.appendChild(chip(
        RS.I18N.aiProcesses + ': ' + (pfVals.length ? pfVals.join(', ') : RS.I18N.allProcesses),
        function (chipEl) {
          var f = pfFilter || { field: pf.field, op: 'in', value: [] };
          valueListChipEditor(cur, f, chipEl, {
            allMeansNoFilter: true,
            onApply: function (ft) {
              if (def.filters.indexOf(ft) === -1) def.filters.push(ft);
            }
          });
        },
        null
      ));
    } else {
      var procs = (def.scope && def.scope.processes) || [];
      wrap.appendChild(chip(
        RS.I18N.aiProcesses + ': ' + (procs.length ? procs.join(', ') : RS.I18N.allProcesses),
        function (chipEl) { processChipEditor(cur, chipEl); },
        null
      ));
    }
    var grainedCol = (def.columns || []).find(function (c) { return c.grain; });
    if (!grainedCol) {
      grainedCol = (def.columns || []).find(function (c) {
        var m = fieldMetaFor(def, c.field);
        return m && m.grainable;
      }) || null;
    }
    if (grainedCol) {
      var GRAIN_LABELS = { day: RS.I18N.grainDay, week: RS.I18N.grainWeek, month: RS.I18N.grainMonth,
                           quarter: RS.I18N.grainQuarter, year: RS.I18N.grainYear };
      wrap.appendChild(chip(
        RS.I18N.granularity + ': ' + (GRAIN_LABELS[grainedCol.grain] || RS.I18N.grainDay),
        function (chipEl) { grainChipEditor(cur, grainedCol, chipEl); },
        null
      ));
    }
  }
  RS.renderAiChips = renderAiChips;

  // ---------- Wizard ----------
  // Progress rail (Task 5): a fixed 4-row list mirroring the 4 step divs.
  // Rows are presentational only -- they read RS.state.wiz + the steps' own
  // `hidden` flags, never drive the click flow (renderMeasureStep and co.
  // are untouched and remain the single source of truth for what's shown).
  var WIZ_STEPS = [
    { id: 'rsStepMeasure', label: RS.I18N.wizMeasure },
    { id: 'rsStepScope', label: RS.I18N.wizScope },
    { id: 'rsStepBreakdown', label: RS.I18N.wizBreakdown },
    { id: 'rsStepTime', label: RS.I18N.wizTime }
  ];
  var WIZ_TIME_TOKEN_LABELS = {
    this_week: RS.I18N.thisWeek, this_month: RS.I18N.thisMonth, last_month: RS.I18N.lastMonth,
    this_quarter: RS.I18N.thisQuarter, last_quarter: RS.I18N.lastQuarter,
    last_3_months: RS.I18N.last3Months, this_year: RS.I18N.thisYear, last_year: RS.I18N.lastYear
  };

  // The accordion never re-hides an earlier step once shown (only cascades
  // hidden=true onto LATER steps when an earlier answer changes), so the
  // "current" step is the deepest (highest-index) visible row -- scan from
  // the end. A source with no processes skips rsStepScope entirely, which
  // still yields the right "of 4" position (jumps straight to Breakdown).
  function wizStepIndex() {
    var i;
    for (i = WIZ_STEPS.length - 1; i >= 0; i--) {
      var stepEl = RS.el(WIZ_STEPS[i].id);
      if (stepEl && !stepEl.hidden) return i;
    }
    return 0;
  }

  function wizTimeLabel(token) {
    return WIZ_TIME_TOKEN_LABELS[token] || token;
  }

  // One short summary string per WIZ_STEPS row, in order, from the exact
  // fields the step renderers themselves read/write on RS.state.wiz. Blank
  // until that part of the state is meaningful (no source picked yet, or
  // this source has no processes to scope).
  function wizSummaries() {
    var w = RS.state.wiz || {};
    var out = ['', '', '', ''];
    if ((w.measures || []).length) {
      out[0] = w.measures.map(function (m) { return m.label; }).join(' + ');
    }
    var allProcs = (w.source && w.source.processes) || [];
    if (allProcs.length) {
      var chosen = (w.scopeProcs || []).length || allProcs.length;
      out[1] = (chosen === allProcs.length) ? RS.I18N.allProcesses
        : RS.I18N.wizScopeCount.replace('{n}', chosen).replace('{m}', allProcs.length);
    }
    if (!allProcs.length && w.fieldScope) {
      var n = w.fieldScope.picked.length, m = w.fieldScope.values.length;
      out[1] = n === m ? RS.I18N.allProcesses
        : RS.I18N.wizScopeCount.replace('{n}', n).replace('{m}', m);
    }
    if (w.source) {
      if ((w.breakdowns || []).length) {
        var grainSel = RS.el('rsGrain');
        var grainTxt = grainSel ? grainSel.options[grainSel.selectedIndex].text : '';
        out[2] = w.breakdowns.map(function (b) {
          if (!b.field) return RS.I18N.justTotal;
          return b.kind === 'date' ? (b.field.label + ' (' + grainTxt + ')') : b.field.label;
        }).join(', ');
      } else {
        out[2] = RS.I18N.justTotal;
      }
      if (Array.isArray(w.range)) out[3] = RS.I18N.custom;
      else if (w.range && w.range.token) out[3] = wizTimeLabel(w.range.token);
      else out[3] = RS.I18N.allTime;
    }
    return out;
  }

  // Called from every point that shows/hides a wizard step (renderMeasureStep,
  // renderScopeStep, renderBreakdownStep, renderTimeStep and the Back button
  // handler) so the header step counter + rail always match the visible step.
  function renderWizardRail() {
    // Console: horizontal step chips (active = accent tint, done = check dot)
    // + the "So far" summary panel beside the step card.
    var idx = wizStepIndex();
    RS.el('rsWizardStepNo').textContent = RS.I18N.stepNof4.replace('{n}', idx + 1);
    var sums = wizSummaries();
    var html = '';
    WIZ_STEPS.forEach(function (step, i) {
      var cls = i < idx ? 'is-done' : (i === idx ? 'is-active' : '');
      var dot = i < idx ? '<i class="fas fa-check" aria-hidden="true"></i>' : String(i + 1);
      html += '<span class="rs-rail-step ' + cls + '">'
        + '<span class="rs-rail-dot">' + dot + '</span>'
        + '<span class="rs-rail-title">' + RS.esc(step.label) + '</span></span>';
      if (i < WIZ_STEPS.length - 1) html += '<span class="rs-rail-line"></span>';
    });
    RS.el('rsWizardRail').innerHTML = html;
    var sm = RS.el('rsWizSummary');
    if (sm) {
      sm.innerHTML = WIZ_STEPS.map(function (step, i) {
        var v = (i <= idx && sums[i]) ? sums[i] : '';
        return '<div class="rs-wizsum-row"><span class="rs-wizsum-k">' + RS.esc(step.label) + '</span>'
          + '<span class="rs-wizsum-v' + (v ? '' : ' is-empty') + '">' + RS.esc(v || '—') + '</span></div>';
      }).join('');
    }
  }
  RS.renderWizardRail = renderWizardRail;

  // In-chip coverage bar: n of m allowed/selected processes provide this
  // field or metric's base field. Same three colour tiers everywhere it's
  // used (renderMeasureStep, applyCoverageBadge in renderBreakdownStep);
  // the caller is still responsible for the (unchanged) tooltip text.
  function covBadge(n, m) {
    var frac = n / m;
    var tier = frac <= 1 / 3 ? 'is-cov-low' : (frac >= 0.8 ? 'is-cov-high' : 'is-cov-mid');
    var b = document.createElement('span');
    b.className = 'reporting-simple-chip-cov ' + tier;
    var bar = document.createElement('span');
    bar.className = 'rs-cov-bar';
    var fill = document.createElement('span');
    fill.className = 'rs-cov-fill';
    fill.style.width = Math.round(frac * 100) + '%';
    bar.appendChild(fill);
    b.appendChild(bar);
    b.appendChild(document.createTextNode(n + '/' + m));
    return b;
  }

  function choiceBtn(label, onpick, selected) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'reporting-simple-choice';
    if (selected) b.classList.add('is-selected');
    b.setAttribute('aria-pressed', selected ? 'true' : 'false');
    b.textContent = label;
    b.addEventListener('click', function () {
      Array.prototype.forEach.call(b.parentNode.children, function (s) {
        s.classList.remove('is-selected');
        if (s.setAttribute) s.setAttribute('aria-pressed', 'false');
      });
      b.classList.add('is-selected');
      b.setAttribute('aria-pressed', 'true');
      onpick();
    });
    return b;
  }

  // Uppercase caption above a cluster of choice chips. Used by both the
  // measure step (one cluster per source) and the breakdown step (Time /
  // Document fields / Or); the class is a full-width flex item, so it forces
  // the wrap onto its own row.
  function groupLabel(text) {
    var l = document.createElement('div');
    l.className = 'rs-choice-group-label';
    l.textContent = text;
    return l;
  }

  async function loadSourcesCatalog() {
    if (RS.state.sources) return RS.state.sources;
    var list = null;
    try { list = await ReportingCatalog.sources(); } catch (e) { list = null; }
    RS.state.sources = Array.isArray(list) ? list : [];
    return RS.state.sources;
  }
  RS.loadSourcesCatalog = loadSourcesCatalog;

  // Warms the two catalogs the shared builders read through state
  // (metricLabelsFor, applyLatestTotal, fieldMetaFor). Idempotent -- both
  // loaders short-circuit once filled. Exposed for the dashboard's
  // whole-report card, which renders while the Simple result view is idle.
  async function ensureCatalogs() {
    await loadSourcesCatalog();
    if (!RS.state.metricsBySource) await RS.loadMetricsCatalog();
  }
  RS.ensureCatalogs = ensureCatalogs;

  async function startWizard() {
    await loadSourcesCatalog();
    if (!RS.state.metricsBySource) await RS.loadMetricsCatalog();
    RS.state.wiz = { measures: [], source: null, breakdowns: [],
                  scopeProcs: [], range: null, dateField: null, _fp: null,
                  fieldScope: null };
    RS.setView('wizard');
    RS.el('rsStepScope').hidden = true;
    RS.el('rsStepBreakdown').hidden = true;
    RS.el('rsStepTime').hidden = true;
    RS.el('rsWizardRun').hidden = true;
    renderMeasureStep();
  }

  // Measures are toggle-select; the first pick pins the source (the query
  // engine is single-source), other sources' chips gray out until empty.
  // Anchored measures (imported/exported/backlog, m.anchor set) plot on the
  // shared activity_date axis and can't mix with plain measures — the server
  // rejects such definitions, so don't let the wizard build one.
  function anchorMismatch(w, m) {
    return !!(w.measures.length && (!!m.anchor) !== (!!w.measures[0].anchor));
  }

  function toggleMeasure(m, src) {
    var w = RS.state.wiz;
    if (w.source && w.source.id !== src.id) return;   // disabled chip
    if (anchorMismatch(w, m)) return;                 // disabled chip
    var idx = -1, i;
    for (i = 0; i < w.measures.length; i++) {
      if (w.measures[i].code === m.code) { idx = i; break; }
    }
    if (idx !== -1) { w.measures.splice(idx, 1); } else { w.measures.push(m); }
    if (!w.measures.length) {
      // Unpinning the source invalidates everything downstream.
      w.source = null; w.scopeProcs = []; w.breakdowns = [];
    } else {
      w.source = src;
    }
    // Any change re-gates the later steps behind Continue.
    RS.el('rsStepScope').hidden = true;
    RS.el('rsStepBreakdown').hidden = true;
    RS.el('rsStepTime').hidden = true;
    RS.el('rsWizardRun').hidden = true;
    renderMeasureStep();
  }

  function renderMeasureStep() {
    var list = RS.el('rsMeasureList');
    list.innerHTML = '';
    var w = RS.state.wiz;
    if (!Array.isArray(w.measures)) w.measures = [];
    var bySource = RS.state.metricsBySource || {};
    // Walk sources in registry order (sortOrder) so a tenant's block stays
    // together; only sources that carry measures are visible.
    var visible = (RS.state.sources || []).filter(function (s) { return bySource[s.id]; })
      .map(function (s) { return s.id; });
    var multi = visible.length > 1;
    var lastGroup = null;
    visible.forEach(function (sid) {
      var src = RS.state.sources.find(function (s) { return s.id === sid; });
      var srcProcs = src.processes || [];
      // Resolve each metric's base field up front. A metric whose base field no
      // allowed process provides can never run for this user (resolve_metrics
      // 400s), so it is not offered — and resolving first is also what keeps a
      // source that ends up with no offerable metric from printing a caption
      // over an empty cluster.
      var offered = (bySource[sid] || []).map(function (m) {
        return {
          m: m,
          fld: m.baseField
            ? (src.fields || []).find(function (f) { return f.field === m.baseField; })
            : null
        };
      }).filter(function (o) { return !o.m.baseField || o.fld; });
      if (!offered.length) return;
      // One captioned cluster per source, the same shape the breakdown step
      // uses. With a single source there is nothing to tell apart, so the
      // caption is dropped and the chips read as one plain list.
      // Sources without metrics never appear; admins grow the wizard's reach
      // by adding rows in the metrics registry, zero code change.
      // "Tenant — Thing" labels share one heading per tenant with a sub-label
      // per source, so five Generali sources read as one Generali passage.
      if (multi) {
        var parts = src.label.split(' — ');
        if (parts.length > 1) {
          if (parts[0] !== lastGroup) list.appendChild(groupLabel(parts[0]));
          var sub = groupLabel(parts.slice(1).join(' — '));
          sub.className += ' rs-choice-group-sublabel';
          list.appendChild(sub);
          lastGroup = parts[0];
        } else {
          list.appendChild(groupLabel(src.label));
          lastGroup = null;
        }
      }
      offered.forEach(function (o) {
        var m = o.m;
        var fld = o.fld;
        var btn = choiceBtn(m.label, function () {
          toggleMeasure(m, src);
        }, !!(w.source && w.source.id === src.id
              && w.measures.some(function (x) { return x.code === m.code; })));
        if (w.source && w.source.id !== src.id) btn.disabled = true;
        if (anchorMismatch(w, m)) btn.disabled = true;
        // Partial coverage (vs ALL allowed processes — no scope exists yet at
        // this step): same badge as the breakdown chips.
        if (fld && fld.processes && fld.processes.length && srcProcs.length
            && fld.processes.length < srcProcs.length) {
          btn.appendChild(covBadge(fld.processes.length, srcProcs.length));
          btn.title = RS.I18N.measureCoverage.replace('{n}', fld.processes.length)
            .replace('{m}', srcProcs.length) + '\n' + fld.processes.join('\n');
        }
        list.appendChild(btn);
      });
    });
    if (!list.children.length) {
      list.innerHTML = '<p class="reporting-simple-empty">' + RS.esc(RS.I18N.noMeasures) + '</p>';
    }
    RS.el('rsMeasureNext').hidden = !w.measures.length;
    renderWizardRail();
  }

  // Own wizard step between measure and breakdown: sources without processes
  // (table sources) skip straight to the breakdown step. Emits the same
  // scope serialisation as before; empty/full selection = all allowed (the
  // server clamps to grants either way).
  // #178 B8: a table source without a process registry still gets a
  // process step when it carries a filterable string field named like one
  // (backlog_history.ProcessName). Selection serializes to a plain
  // in-filter, not scope.processes.
  function processFieldFor(src) {
    if ((src.processes || []).length) return null;
    return (src.fields || []).find(function (f) {
      return f.type === 'string' && f.filterable &&
        /process/i.test(f.field + ' ' + (f.label || ''));
    }) || null;
  }

  function renderScopeStep() {
    var w = RS.state.wiz;
    var procs = w.source.processes || [];
    var step = RS.el('rsStepScope');
    var pf = processFieldFor(w.source);
    if (!procs.length && !pf) { step.hidden = true; renderBreakdownStep(); return; }
    if (!procs.length && pf) { renderFieldScopeStep(step, pf); return; }
    step.hidden = false;
    RS.el('rsStepBreakdown').hidden = true;
    RS.el('rsStepTime').hidden = true;
    RS.el('rsWizardRun').hidden = true;
    var box = RS.el('rsScopeList');
    box.innerHTML = '';
    var prior = w.scopeProcs || [];
    procs.forEach(function (p) {
      var lbl = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.value = p;
      cb.checked = !prior.length || prior.indexOf(p) !== -1;
      cb.addEventListener('change', function () {
        w.scopeProcs = Array.prototype.map.call(
          box.querySelectorAll('input:checked'), function (c) { return c.value; });
        // The chip list follows the scope live when the breakdown step is
        // already open (reopened wizard / user stepped back).
        if (!RS.el('rsStepBreakdown').hidden) renderBreakdownStep();
      });
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + p));
      box.appendChild(lbl);
    });
    if (!prior.length) w.scopeProcs = procs.slice();
    renderWizardRail();
  }

  async function renderFieldScopeStep(step, pf) {
    var w = RS.state.wiz;
    step.hidden = false;
    RS.el('rsStepBreakdown').hidden = true;
    RS.el('rsStepTime').hidden = true;
    RS.el('rsWizardRun').hidden = true;
    var box = RS.el('rsScopeList');
    box.innerHTML = '<p class="reporting-simple-hint">' + RS.esc(RS.I18N.loadingValues) + '</p>';
    renderWizardRail();
    var res = await RS.api('/api/reporting/field_values', {
      method: 'POST',
      body: JSON.stringify({ source: w.source.id, field: pf.field })
    });
    if (RS.state.view !== 'wizard' || RS.el('rsStepScope').hidden) {
      // User stepped away mid-fetch (e.g. back to the measure step) --
      // clear the stale "Loading values..." hint so a later re-entry to this
      // step doesn't show it frozen until the NEXT fetch resolves (#178).
      box.innerHTML = '';
      return;
    }
    var values = (res.ok && res.data && res.data.values) || [];
    var valueLabels = (res.ok && res.data && res.data.labels) || {};
    if (!values.length) {  // endpoint down or empty column: skip the step
      w.fieldScope = null;
      step.hidden = true;
      renderBreakdownStep();
      return;
    }
    var prior = (w.fieldScope && w.fieldScope.picked) || [];
    w.fieldScope = { field: pf.field, label: pf.label || pf.field,
                     values: values, picked: prior.length ? prior : values.slice() };
    box.innerHTML = '';
    values.forEach(function (p) {
      var lbl = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.value = p;
      cb.checked = w.fieldScope.picked.indexOf(p) !== -1;
      cb.addEventListener('change', function () {
        w.fieldScope.picked = Array.prototype.map.call(
          box.querySelectorAll('input:checked'), function (c) { return c.value; });
      });
      lbl.appendChild(cb);
      // labelWith companion (e.g. "privera.03_Invoice_New"); value stays bare.
      lbl.appendChild(document.createTextNode(' ' + (valueLabels[p] || p)));
      box.appendChild(lbl);
    });
    renderWizardRail();
  }

  function renderBreakdownStep() {
    RS.el('rsStepBreakdown').hidden = false;
    RS.el('rsStepTime').hidden = true;
    RS.el('rsWizardRun').hidden = true;
    var w = RS.state.wiz;
    if (!Array.isArray(w.breakdowns)) w.breakdowns = [];
    var allProcs = w.source.processes || [];
    var sourceHasDates = (w.source.fields || []).some(function (f) { return f.grainable; });

    function isSelected(bd) {
      if (bd.kind === 'none') return w.breakdowns.length === 0;
      var i;
      for (i = 0; i < w.breakdowns.length; i++) {
        var b = w.breakdowns[i];
        if (b.kind === bd.kind && b.field && bd.field && b.field.field === bd.field.field) return true;
      }
      return false;
    }

    function refreshChips() {
      var chips = RS.el('rsBreakdownList').querySelectorAll('button[data-bd-kind]');
      var ci;
      for (ci = 0; ci < chips.length; ci++) {
        var btn = chips[ci];
        var bd = { kind: btn.dataset.bdKind,
                   field: btn.dataset.bdField ? { field: btn.dataset.bdField } : null };
        var sel = isSelected(bd);
        btn.classList.toggle('is-selected', sel);
        btn.setAttribute('aria-pressed', String(sel));
      }
      var hasDate = false;
      for (ci = 0; ci < w.breakdowns.length; ci++) {
        if (w.breakdowns[ci].kind === 'date') { hasDate = true; break; }
      }
      RS.el('rsGrainWrap').hidden = !sourceHasDates;
      RS.el('rsGrain').disabled = !hasDate;
      RS.el('rsGrainWrap').title = hasDate ? '' : RS.I18N.grainNeedsDate;
      updatePickedCount();
    }

    function toggleBreakdown(bd) {
      if (bd.kind === 'none') {
        w.breakdowns = [];
        refreshChips();
        return;
      }
      var idx = -1, i;
      for (i = 0; i < w.breakdowns.length; i++) {
        var b = w.breakdowns[i];
        if (b.kind === bd.kind && b.field && bd.field && b.field.field === bd.field.field) {
          idx = i; break;
        }
      }
      if (idx !== -1) { w.breakdowns.splice(idx, 1); refreshChips(); renderWizardRail(); return; }
      // ponytail: date breakdowns are no longer mutually exclusive (#164) --
      // export+import date together is a plain 2-dim group-by, which the query
      // builder already supports (grain is per-column server-side). They share
      // the single rsGrain select; per-date grains would need a second control.
      if (w.breakdowns.length >= 3) { refreshChips(); return; }
      w.breakdowns.push(bd);
      refreshChips();
      renderWizardRail();
    }

    // --- process coverage (docprocessing) --------------------------------
    // Mirrors the Advanced tab's isFieldAvailable(): a field with no
    // `processes` tag (table sources) is universal. The effective scope is
    // the picker selection; empty selection = all allowed (the same
    // convention the definition serializer uses).
    function scopeSel() {
      return (w.scopeProcs && w.scopeProcs.length) ? w.scopeProcs : allProcs;
    }
    function coveredBy(f) {
      if (!allProcs.length || !f.processes || !f.processes.length) return null;
      var sel = scopeSel();
      return f.processes.filter(function (p) { return sel.indexOf(p) !== -1; });
    }
    function inScope(f) {
      var cov = coveredBy(f);
      return cov === null || cov.length > 0;
    }
    function applyCoverageBadge(btn, f) {
      var cov = coveredBy(f);
      if (cov === null || cov.length >= scopeSel().length) return;
      btn.appendChild(covBadge(cov.length, scopeSel().length));
      btn.title = RS.I18N.chipCoverage.replace('{n}', cov.length).replace('{m}', scopeSel().length)
        + '\n' + cov.join('\n');
    }

    // Task 6: "{n} of 3 picked" footer counter, breakdown step only (the
    // footer itself is shared across all four steps -- visibility is a pure
    // CSS :has() shim keyed on #rsStepBreakdown[hidden], see reporting.css).
    function updatePickedCount() {
      RS.el('rsPickedCount').textContent = RS.I18N.pickedCount.replace('{n}', String(w.breakdowns.length));
    }

    // The chip list is re-rendered whenever the process scope changes: a chip
    // whose field no selected process provides is hidden and its selection
    // pruned (the query would only produce NULL groups for it).
    function renderChipList() {
      var list = RS.el('rsBreakdownList');
      list.innerHTML = '';
      var fields = w.source.fields || [];
      // Anchored measures use ONLY the shared activity_date axis; plain
      // measures never do (each anchored metric buckets its own date onto it).
      var anchoredWiz = !!(w.measures.length && w.measures[0].anchor);
      var dateFields = fields.filter(function (f) { return f.grainable; }).filter(inScope)
        .filter(function (f) {
          return anchoredWiz ? f.field === 'activity_date' : f.field !== 'activity_date';
        });
      var catFields = fields.filter(function (f) {
        return f.type === 'string' && f.filterable;
      }).filter(inScope);

      if (w.source.id === 'docprocessing') {
        catFields = catFields.filter(function (f) { return !DOCPROC_DIM_HIDE[f.field]; });
        // Coverage first (full-coverage chips on top, 1/x at the bottom,
        // recomputed against the CURRENT process scope), curated order and
        // label only break ties within the same coverage.
        var fracOf = function (f) {
          var cov = coveredBy(f);
          return cov === null ? 1 : cov.length / scopeSel().length;
        };
        catFields.sort(function (a, b) {
          var fa = fracOf(a), fb = fracOf(b);
          if (fa !== fb) return fb - fa;
          var ia = DOCPROC_DIM_ORDER.indexOf(a.field), ib = DOCPROC_DIM_ORDER.indexOf(b.field);
          if (ia === -1) ia = DOCPROC_DIM_ORDER.length;
          if (ib === -1) ib = DOCPROC_DIM_ORDER.length;
          return (ia - ib) || a.label.localeCompare(b.label);
        });
      }

      // Scope narrowing can strand a selected breakdown on a hidden field.
      w.breakdowns = w.breakdowns.filter(function (b) { return !b.field || inScope(b.field); });

      if (dateFields.length) list.appendChild(groupLabel(RS.I18N.groupTime));
      dateFields.forEach(function (f) {
        var bd = { kind: 'date', field: f };
        // Plain field label ("Import date"): the Time caption above already
        // says these are the over-time breakdowns.
        var btn = choiceBtn(f.label, function () {
          toggleBreakdown(bd);
        }, isSelected(bd));
        btn.dataset.bdKind = 'date';
        btn.dataset.bdField = f.field;
        applyCoverageBadge(btn, f);
        list.appendChild(btn);
      });
      // Rare/diagnostic dimensions fold behind one "Show advanced fields"
      // chip: docprocessing keeps a fixed main five, table sources mark
      // theirs with "advanced":true in ColumnsJSON. A selected advanced
      // field (reopened wizard) keeps the fold open.
      var isAdv = w.source.id === 'docprocessing'
        ? function (f) { return !DOCPROC_DIM_MAIN[f.field]; }
        : function (f) { return !!f.advanced; };
      var advFields = catFields.filter(isAdv);
      catFields = catFields.filter(function (f) { return !isAdv(f); });
      if (advFields.some(function (f) { return isSelected({ kind: 'category', field: f }); })) w.advOpen = true;

      function addCatChip(f) {
        var bd = { kind: 'category', field: f };
        var btn = choiceBtn(f.label, function () {
          toggleBreakdown(bd);
        }, isSelected(bd));
        btn.dataset.bdKind = 'category';
        btn.dataset.bdField = f.field;
        applyCoverageBadge(btn, f);
        list.appendChild(btn);
      }
      // No cap: everything the Advanced tab offers is available here — the
      // coverage sort keeps rarely-provided fields at the bottom, and the
      // hide-list still filters the noise.
      if (catFields.length) list.appendChild(groupLabel(RS.I18N.groupFields));
      catFields.forEach(addCatChip);
      if (advFields.length) {
        if (w.advOpen) {
          list.appendChild(groupLabel(RS.I18N.groupAdvanced));
          advFields.forEach(addCatChip);
        } else {
          var advBtn = choiceBtn(RS.I18N.showAdvanced.replace('{n}', String(advFields.length)), function () {
            w.advOpen = true; renderChipList();
          }, false);
          advBtn.classList.add('rs-choice-none');
          advBtn.dataset.testid = 'rs-breakdown-advanced';
          list.appendChild(advBtn);
        }
      }
      list.appendChild(groupLabel(RS.I18N.groupOr));
      var noneBtn = choiceBtn(RS.I18N.justTotal, function () {
        toggleBreakdown({ kind: 'none' });
      }, w.breakdowns.length === 0);
      noneBtn.dataset.bdKind = 'none';
      noneBtn.classList.add('rs-choice-none');
      list.appendChild(noneBtn);
    }

    renderChipList();
    refreshChips();

    // Wire Continue button
    var nextBtn = RS.el('rsBreakdownNext');
    if (nextBtn) {
      nextBtn.onclick = function () { renderTimeStep(); };
    }
    renderWizardRail();
  }

  function isoDate(d) {
    return d.getFullYear() + '-' +
      String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
  }

  // Lazily creates the Custom-range flatpickr on rsTimeRange (shared by the
  // Custom choiceBtn handler and the restore-from-definition path below), so
  // the mode/format/onChange options exist in exactly one place.
  function ensureRangePicker() {
    if (!RS.state.wiz._fp && window.flatpickr) {
      RS.state.wiz._fp = flatpickr(RS.el('rsTimeRange'), {
        mode: 'range', dateFormat: 'Y-m-d',
        onChange: function (picked) {
          if (picked.length === 2) {
            RS.state.wiz.range = [isoDate(picked[0]), isoDate(picked[1])];
          }
        }
      });
    }
    return RS.state.wiz._fp;
  }

  function renderTimeStep() {
    RS.el('rsStepTime').hidden = false;
    RS.el('rsWizardRun').hidden = false;
    RS.el('rsTimeCustom').hidden = !Array.isArray(RS.state.wiz.range);
    // A restored definition's literal range (adjustInWizard) must be visible
    // in the picker, not just applied silently on Show result — seed it here
    // (display = state, no change event) rather than waiting for the user to
    // click Custom themselves.
    if (Array.isArray(RS.state.wiz.range) && window.flatpickr) {
      ensureRangePicker();
      if (RS.state.wiz._fp) RS.state.wiz._fp.setDate(RS.state.wiz.range, false);
    }
    var fields = RS.state.wiz.source.fields || [];
    var anchoredTime = !!(RS.state.wiz.measures.length && RS.state.wiz.measures[0].anchor);
    var dateFields = fields.filter(function (f) { return f.grainable; })
      .filter(function (f) {
        return anchoredTime ? f.field === 'activity_date' : f.field !== 'activity_date';
      });
    var list = RS.el('rsTimeList');
    // Skipped when the source exposes no date field.
    if (!dateFields.length) {
      list.innerHTML = '<p class="reporting-simple-empty">' + RS.esc(RS.I18N.noDateField) + '</p>';
      RS.el('rsTimeFieldWrap').hidden = true;
      RS.state.wiz.range = null;
      RS.el('rsAllTimeHint').hidden = true;
      renderWizardRail();
      return;
    }
    // Date field defaults to import_date, switchable to export_date.
    var sel = RS.el('rsTimeField');
    sel.innerHTML = '';
    dateFields.forEach(function (f) {
      var o = document.createElement('option');
      o.value = f.field; o.textContent = f.label;
      sel.appendChild(o);
    });
    if (RS.state.wiz.dateField
        && dateFields.some(function (f) { return f.field === RS.state.wiz.dateField; })) {
      sel.value = RS.state.wiz.dateField;
    } else if (dateFields.some(function (f) { return f.field === 'import_date'; })) {
      sel.value = 'import_date';
    }
    RS.el('rsTimeFieldWrap').hidden = dateFields.length < 2;
    RS.state.wiz.dateField = sel.value;
    sel.onchange = function () { RS.state.wiz.dateField = sel.value; };

    list.innerHTML = '';
    [['this_week', RS.I18N.thisWeek], ['this_month', RS.I18N.thisMonth],
     ['last_month', RS.I18N.lastMonth], ['this_quarter', RS.I18N.thisQuarter],
     ['last_quarter', RS.I18N.lastQuarter], ['last_3_months', RS.I18N.last3Months],
     ['this_year', RS.I18N.thisYear], ['last_year', RS.I18N.lastYear],
     ['all_time', RS.I18N.allTime], ['custom', RS.I18N.custom]].forEach(function (p) {
      list.appendChild(choiceBtn(p[1], function () {
        RS.el('rsTimeCustom').hidden = p[0] !== 'custom';
        if (p[0] === 'custom') {
          ensureRangePicker();
          // Re-selecting Custom keeps whatever range the picker still shows
          // (display and state must agree); empty picker = no filter yet.
          var fp = RS.state.wiz._fp;
          RS.state.wiz.range = (fp && fp.selectedDates && fp.selectedDates.length === 2)
            ? [isoDate(fp.selectedDates[0]), isoDate(fp.selectedDates[1])]
            : null;
        } else {
          // Preset = relative-date token: resolved server-side on every run.
          // all_time = no filter.
          RS.state.wiz.range = p[0] === 'all_time' ? null : { token: p[0] };
        }
        RS.el('rsAllTimeHint').hidden = RS.state.wiz.range !== null;
        renderWizardRail();
      }, RS.state.wiz.range === p[0] ||
         (RS.state.wiz.range && RS.state.wiz.range.token === p[0]) ||
         (p[0] === 'custom' && Array.isArray(RS.state.wiz.range)) ||
         (p[0] === 'all_time' && RS.state.wiz.range === null)));
    });
    // Only default to all-time if no prior choice is being restored.
    if (!RS.state.wiz.range) RS.state.wiz.range = null;
    RS.el('rsAllTimeHint').hidden = RS.state.wiz.range !== null;
    renderWizardRail();
  }

  // Wizard invariants (validator-enforced server-side): sort fields are among
  // the selected columns or metric codes; grain only on grainable fields;
  // metric codes from the registry; the between filter always targets the
  // RAW date field (the Spec-1 contract), never the bucketed expression.
  function wizardDefinition() {
    var w = RS.state.wiz;
    var columns = [], sort = [], filters = [];
    var title = w.measures.map(function (m) { return m.label; }).join(' + ');
    var bds = (w.breakdowns || []).slice();
    // date first: it becomes the chart axis (X)
    bds.sort(function (a, b) {
      return (a.kind === 'date' ? 0 : 1) - (b.kind === 'date' ? 0 : 1);
    });
    var grain = RS.el('rsGrain').value || 'month';
    var titleParts = [];
    var hasDate = false;
    var nDates = bds.filter(function (b) { return b.kind === 'date'; }).length;
    bds.slice(0, 3).forEach(function (b) {
      if (b.kind === 'date') {
        hasDate = true;
        columns.push({ field: b.field.field, header: b.field.label, grain: grain });
        sort.push({ field: b.field.field, dir: 'asc' });
        // With two date breakdowns "per month / per month" is meaningless —
        // name the field so the two axes stay distinguishable (#164).
        var per = RS.I18N.per + ' ' + RS.el('rsGrain').options[RS.el('rsGrain').selectedIndex].text.toLowerCase();
        titleParts.push(nDates > 1 ? (b.field.label + ' ' + per) : per);
      } else if (b.kind === 'category') {
        columns.push({ field: b.field.field, header: b.field.label });
        titleParts.push(b.field.label);
      }
    });
    if (!sort.length && columns.length) {
      sort.push({ field: w.measures[0].code, dir: 'desc' });
    }
    if (titleParts.length) {
      if (hasDate && bds.length === 1) {
        title += ' ' + titleParts.join(' / ');
      } else {
        title += ' ' + RS.I18N.by + ' ' + titleParts.join(' / ');
      }
    }
    if (w.range && w.dateField) {
      filters.push({ field: w.dateField, op: 'between', value: w.range });
    }
    if (w.fieldScope && w.fieldScope.picked.length &&
        w.fieldScope.picked.length < w.fieldScope.values.length) {
      filters.push({ field: w.fieldScope.field, op: 'in', value: w.fieldScope.picked.slice() });
    }
    var scope = { clients: [], processes: [] };
    var allProcs = w.source.processes || [];
    if (allProcs.length && w.scopeProcs.length && w.scopeProcs.length < allProcs.length) {
      scope.processes = w.scopeProcs.slice();
    }
    return {
      schemaVersion: 1, source: w.source.id, visualization: 'table',
      title: title, subtitle: null,
      columns: columns,
      metrics: w.measures.map(function (m) { return { metric: m.code }; }),
      filters: filters, sort: sort, scope: scope, rowLimit: 5000
    };
  }

  // Wizard presets that renderTimeStep offers; other tokens (e.g. last_n_days,
  // last_week) can't be represented in the wizard UI, so such defs don't map.
  var WIZ_TOKENS = ['this_week', 'this_month', 'last_month', 'this_quarter',
                    'last_quarter', 'last_3_months', 'this_year', 'last_year'];

  // Inverse of wizardDefinition(): returns {wiz, grain} for wizard-shaped
  // definitions, or null when the def can't be represented in the wizard
  // (multiple columns/filters/metrics, exotic ops, client scope).
  function wizardStateFromDefinition(def) {
    if (!def || !Array.isArray(def.metrics) || !def.metrics.length) return null;
    var src = (RS.state.sources || []).find(function (s) { return s.id === def.source; });
    var mlist = (RS.state.metricsBySource || {})[def.source] || [];
    var measures = [];
    for (var mi = 0; mi < def.metrics.length; mi++) {
      var code = def.metrics[mi].metric;
      var hit = mlist.find(function (x) { return x.code === code; });
      if (!hit) return null;
      measures.push(hit);
    }
    if (!src) return null;
    var cols = def.columns || [];
    if (cols.length > 3) return null;
    var breakdowns = [], grain = null;
    var ci;
    for (ci = 0; ci < cols.length; ci++) {
      var f = (src.fields || []).find(function (x) { return x.field === cols[ci].field; });
      if (!f) return null;
      if (cols[ci].grain) {
        // Several date columns are fine (#164), but the wizard has ONE grain
        // select — a def whose date columns disagree can't be represented.
        if (!f.grainable || (grain && cols[ci].grain !== grain)) return null;
        breakdowns.push({ kind: 'date', field: f });
        grain = cols[ci].grain;
      } else {
        breakdowns.push({ kind: 'category', field: f });
      }
    }
    var filters = def.filters || [];
    // Only a filter on the SAME field processFieldFor(src) would offer can be
    // the wizard's field-scope pick — matching any string in-filter would
    // silently swallow (registry-process sources) or misattribute
    // (multi-string-field sources) an unrelated filter (#178 review finding).
    var pf = processFieldFor(src);
    var fieldScopeFilter = null;
    var rest = [];
    filters.forEach(function (ft) {
      if (!fieldScopeFilter && ft.op === 'in' && pf && ft.field === pf.field) {
        fieldScopeFilter = ft;
      } else {
        rest.push(ft);
      }
    });
    filters = rest;
    if (filters.length > 1) return null;
    var range = null, dateField = null;
    if (filters.length === 1) {
      var ft = filters[0];
      if (ft.op !== 'between') return null;
      var df = (src.fields || []).find(function (x) {
        return x.field === ft.field && x.grainable;
      });
      if (!df) return null;
      dateField = ft.field;
      if (ft.value && ft.value.token) {
        if (WIZ_TOKENS.indexOf(ft.value.token) === -1) return null;
        range = { token: ft.value.token };
      } else if (Array.isArray(ft.value) && ft.value.length === 2) {
        range = ft.value.slice();
      } else { return null; }
    }
    var scope = def.scope || {};
    if ((scope.clients || []).length) return null;
    return { wiz: { measures: measures, source: src, breakdowns: breakdowns,
                    scopeProcs: (scope.processes || []).slice(),
                    range: range, dateField: dateField, _fp: null,
                    fieldScope: fieldScopeFilter
                      ? { field: fieldScopeFilter.field, label: fieldScopeFilter.field,
                          values: fieldScopeFilter.value.slice(), picked: fieldScopeFilter.value.slice() }
                      : null },
             grain: grain };
  }
  RS.wizardStateFromDefinition = wizardStateFromDefinition;

  async function adjustInWizard() {
    var cur = RS.state.current;
    if (!cur) return;
    if (cur.builtBy === 'wizard' && RS.state.wiz && (RS.state.wiz.measures || []).length) {
      reopenWizard(); return;
    }
    await loadSourcesCatalog();
    if (!RS.state.metricsBySource) await RS.loadMetricsCatalog();
    var mapped = wizardStateFromDefinition(cur.def);
    if (!mapped) return;
    RS.state.wiz = mapped.wiz;
    if (mapped.grain) RS.el('rsGrain').value = mapped.grain;
    reopenWizard();
  }
  RS.adjustInWizard = adjustInWizard;

  async function reopenWizard() {
    if (!RS.state.wiz || !(RS.state.wiz.measures || []).length) { startWizard(); return; }
    await loadSourcesCatalog();
    if (!RS.state.metricsBySource) await RS.loadMetricsCatalog();
    RS.setView('wizard');
    renderMeasureStep();
    renderScopeStep();
    renderBreakdownStep();
    renderTimeStep();
  }

  RS.el('rsNewReport').addEventListener('click', startWizard);
  RS.el('rsNewDashboard').addEventListener('click', function () {
    RS.setView('dashboard');
    window.ReportingDashboard.openNew();
  });
  RS.el('rsMeasureNext').addEventListener('click', function () { renderScopeStep(); });
  RS.el('rsScopeNext').addEventListener('click', function () { renderBreakdownStep(); });
  // Back steps one wizard step backwards (picks are preserved in RS.state.wiz);
  // only from step 1 does it exit. The ✕ stays the explicit exit at any point.
  RS.el('rsWizardBack').addEventListener('click', function () {
    if (!RS.el('rsStepTime').hidden) {           // time -> breakdown
      RS.el('rsStepTime').hidden = true;
      RS.el('rsWizardRun').hidden = true;
      renderWizardRail();
      return;
    }
    if (!RS.el('rsStepBreakdown').hidden) {      // breakdown -> scope (or measure)
      RS.el('rsStepBreakdown').hidden = true;
      if (!RS.el('rsStepScope').hidden) { renderWizardRail(); return; }  // scope step stays visible above
      // no scope step for this source: renderScopeStep would have skipped it
      var procs = (RS.state.wiz && RS.state.wiz.source && RS.state.wiz.source.processes) || [];
      if (procs.length) RS.el('rsStepScope').hidden = false;
      renderWizardRail();
      return;
    }
    if (!RS.el('rsStepScope').hidden) {          // scope -> measure
      RS.el('rsStepScope').hidden = true;
      renderWizardRail();
      return;
    }
    RS.setView('library');                       // measure -> out
  });
  RS.el('rsWizardRun').addEventListener('click', function () {
    if (!RS.state.wiz || !(RS.state.wiz.measures || []).length) return;
    var def = wizardDefinition();
    RS.state.current = { def: def, name: def.title, reportId: null,
                      owned: true, canEdit: true, fromWizard: true,
                      builtBy: 'wizard', origin: 'wizard' };
    RS.runCurrent();
  });

  // (The old hero Ask-AI bar is gone — Console intent #1. The AI entry point
  // is the top-bar "AI chat" button; window.ReportingChat owns that panel.)
}());
