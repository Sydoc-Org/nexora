/* Dashboard builder (kind:'dashboard' saved reports) -- Task 11 skeleton.
   State model + open/save/edit-toggle handlers ported from the design
   prototype (docs/superpowers/specs/2026-07-20-reporting-dashboard-prototype.dc.html)
   per spec section 3 (docs/superpowers/specs/2026-07-20-reporting-redesign-handoff.md).
   A dashboard is simply a saved report whose DefinitionJSON is
   {kind:'dashboard', schemaVersion:1, title, globalFilters, cards} --
   persisted through the existing /api/reporting/reports CRUD, zero
   backend change. This module only builds the skeleton: open/close/save/
   toggleEditing and a render dispatch drawing bare card shells. Card
   rendering, per-card/global filters, drag-reorder and export are later
   tasks (12-15) layered on top of the state model here (setCards/addCard
   already exist for them to build on). Self-contained IIFE: talks only to
   /api/reporting/reports and exposes window.ReportingDashboard. */
(function () {
  'use strict';
  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";

  // Same shape as the Simple pane's api() helper (templates/js/_reporting_simple_js.html):
  // never throws, always resolves to {ok, status, data}.
  async function api(url, opts) {
    if (url.startsWith('/')) url = API_PREFIX + url.slice(1);
    opts = opts || {};
    var res;
    try {
      res = await fetch(url, Object.assign(
        { headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf } }, opts));
    } catch (e) {
      return { ok: false, status: 0, data: null };
    }
    var data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON */ }
    return { ok: res.ok, status: res.status, data: data };
  }

  function el(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // In-page toast -- same DOM/CSS contract as the Advanced tab's private
  // toast() (.reporting-toast / data-testid="reporting-toast", defined in
  // _reporting_js.html): this module is self-contained so it draws its own,
  // reusing the existing shared CSS class rather than a new one.
  function toast(msg, isError) {
    var t = document.createElement('div');
    t.className = 'reporting-toast' + (isError ? ' reporting-toast--error' : '');
    t.setAttribute('role', 'status');
    t.setAttribute('data-testid', 'reporting-toast');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('is-gone'); }, 2600);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3000);
  }

  var I18N = window.NX_I18N_REPORTING_DASHBOARD;

  // Chart.js palette for bar/donut cards (spec §Dashboard "Cards") -- cycles
  // if a card has more categories than colors.
  var CARD_PALETTE = ['#4f46e5', '#6366f1', '#7c3aed', '#8b5cf6', '#a5b4fc'];

  // Multi-series palette for two-dimension line/bar cards (#174) -- the first
  // 8 of the Simple pane's NX_PALETTE, duplicated rather than shared for the
  // same reason that pane duplicates it from _reporting_viz_js.html. Its
  // length IS the per-card series cap: a 190px-tall card body cannot carry
  // Simple's 12 legible lines, and every drawn series must own a color.
  var SERIES_PALETTE = [
    '#4f46e5', '#7c3aed', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#64748b', '#a78bfa'
  ];

  // Filter-op set + labels for the global-filter popover (D11/Task 13) --
  // mirrors _reporting_js.html's OP_LABELS/op <select> (same msgids, so
  // translations can't drift apart between the two). Narrower than that
  // list: no between/in/not_in here -- those need the multi-value UI the
  // Simple/Advanced panes have and this self-contained popover doesn't.
  var FILTER_OPS = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'starts_with', 'is_null', 'is_not_null'];
  var OP_LABELS = {
    eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤',
    contains: I18N.opContains, starts_with: I18N.opStartsWith,
    is_null: I18N.opIsEmpty, is_not_null: I18N.opIsNotEmpty
  };

  // ---- State model (D2/D3 -- exact shape, Tasks 12-15 build on this) -------
  var state = { editing: false, dirty: false, reportId: null, canEdit: true,
                dragId: null, overId: null, seq: 100, def: null };

  var DEFAULT_SPAN = { kpi: 3, line: 8, donut: 4, bar: 6, table: 6, report: 12 };

  // Card height is a whole number of grid rows (--rdb-row / --rdb-gap in
  // reporting.css); .rdb-card's height calc() reads the count off the
  // --rdb-cardrows custom property cardGeomStyle() writes. Saved dashboards
  // predating the `rows` field fall back to the per-type default, sized to the
  // fixed body heights those cards used to have -- so an older dashboard
  // reopens looking as it did before resizing existed.
  var DEFAULT_ROWS = { kpi: 1, line: 2, donut: 2, bar: 2, table: 2, report: 4 };
  var GRID_COLS = 12, MAX_ROWS = 6;

  function clampInt(v, lo, hi, dflt) {
    var n = parseInt(v, 10);
    if (!isFinite(n)) n = dflt;
    return Math.max(lo, Math.min(hi, n));
  }

  function cardSpan(c) {
    return clampInt(c && c.span, 1, GRID_COLS, DEFAULT_SPAN[c && c.type] || 6);
  }

  function cardRows(c) {
    return clampInt(c && c.rows, 1, MAX_ROWS, DEFAULT_ROWS[c && c.type] || 2);
  }

  function cardGeomStyle(span, rows) {
    return 'grid-column:span ' + span + ';--rdb-cardrows:' + rows;
  }

  function blankDef() {
    return { kind: 'dashboard', schemaVersion: 1, title: I18N.untitled,
             globalFilters: [], cards: [] };
  }

  // ---- Card-array helpers (ported from the prototype's setCards/addCard;
  // per-card remove/duplicate + drag-reorder + real filter editing are
  // Tasks 12/13's job -- this only proves the array -> render round trip). ----
  function setCards(fn) {
    state.def.cards = fn((state.def.cards || []).slice());
    state.dirty = true;
    render();
  }

  function addCard(type, opts) {
    if (!state.editing) return null;
    // opts comes from the add-card mask: an adopted saved-report definition,
    // a title and an explicit size. Without it this is still the old empty
    // placeholder (D14) -- a "configure this card" body until a saved report
    // is adopted into it (openReportPicker/adoptReport).
    opts = opts || {};
    var card = { id: 'n' + state.seq, type: type,
                 span: clampInt(opts.span, 1, GRID_COLS, DEFAULT_SPAN[type] || 6),
                 rows: clampInt(opts.rows, 1, MAX_ROWS, DEFAULT_ROWS[type] || 2),
                 title: opts.title || I18N.newCard,
                 definition: opts.definition ||
                   { source: null, metrics: [], columns: [], filters: [] },
                 filterOverrides: [] };
    state.seq += 1;
    setCards(function (list) { return list.concat([card]); });
    return card;
  }

  // ---- Public entry points (window.ReportingDashboard) ---------------------
  function openNew() {
    state.def = blankDef();
    state.reportId = null;
    state.canEdit = true;
    state.editing = true;
    state.dirty = true;   // nothing persisted yet -- first Done must create it
    state.dragId = null; state.overId = null; state.seq = 100;
    render();
  }

  // addCard/duplicateCard mint ids as 'n' + state.seq++ / 'dup' + state.seq++,
  // and those ids are persisted as part of the saved card definitions. Always
  // resetting seq to the literal 100 on open() meant a saved dashboard whose
  // cards already used n100/dup100 (from a prior add/duplicate) would collide
  // with the very next add/duplicate after being reopened -- two cards with
  // the same id, breaking every id-keyed lookup (findCardById, the charts/
  // cardRunData/runGen maps, remove/duplicate targeting). Seed instead from
  // the highest existing n-/dup-prefixed numeric suffix in the loaded
  // definition, ignoring non-matching ids (e.g. prototype-style k1/c1/t1
  // fixtures, which aren't in this numeric scheme).
  function nextSeqFor(cards) {
    var max = 99;
    (cards || []).forEach(function (c) {
      var m = /^(?:n|dup)(\d+)$/.exec(c && c.id);
      if (m) {
        var n = parseInt(m[1], 10);
        if (n > max) max = n;
      }
    });
    return max + 1;
  }

  function open(report) {
    state.def = report.definition;
    state.reportId = report.id;
    state.canEdit = !!report.canEdit;
    state.editing = false;
    state.dirty = false;
    state.dragId = null; state.overId = null;
    state.seq = nextSeqFor(state.def.cards);
    render();
  }

  function close() {
    if (el('rsDashboard')) el('rsDashboard').hidden = true;
    // The Simple pane owns the view-state switch back to the library; this
    // module never calls setView itself (self-contained modules don't reach
    // into each other's functions) -- it just announces the intent.
    document.dispatchEvent(new CustomEvent('rs:dashboard-closed'));
  }

  async function save() {
    var body = JSON.stringify({ name: (state.def.title || I18N.untitled), definition: state.def });
    var res = state.reportId
      ? await api('/api/reporting/reports/' + state.reportId, { method: 'PUT', body: body })
      : await api('/api/reporting/reports', { method: 'POST', body: body });
    if (res.ok) {
      if (!state.reportId && res.data && res.data.id) state.reportId = res.data.id;
      state.dirty = false;
      toast(I18N.saved);
    } else {
      toast(I18N.saveFailed, true);
    }
  }

  function toggleEditing() {
    if (!state.canEdit) return;
    if (state.editing && state.dirty) save();  // Done autosaves (D2/D3)
    state.editing = !state.editing;
    render();
  }

  // ---- Rendering -------------------------------------------------------
  var built = false;

  // Export (D9) is perm-gated like every other export control
  // (has_permission('reporting.export')) -- the dashboard header is
  // JS-rendered so no Jinja if-block can wrap the button directly; the
  // permission flag instead rides on #rsDashboard's data-can-export
  // attribute (set in templates/_reporting_simple.html), read once here.
  var canExport = false;

  function ensureShell() {
    if (built) return;
    canExport = el('rsDashboard').getAttribute('data-can-export') === '1';
    el('rsDashboard').innerHTML =
      '<div class="rdb-head">' +
        '<button type="button" id="rdbBack" class="nx-btn nx-btn--secondary" data-testid="rdb-back">' +
          '<i class="fas fa-arrow-left" aria-hidden="true"></i>' + esc(I18N.library) + '</button>' +
        '<div class="rdb-titleblock">' +
          '<div class="rdb-titlerow">' +
            '<h2 id="rdbTitle" class="rdb-title" data-testid="rdb-title"></h2>' +
            '<button type="button" id="rdbRenamePencil" class="rs-rename-pencil" ' +
              'title="' + esc(I18N.rename) + '" aria-label="' + esc(I18N.rename) + '">' +
              '<i class="fas fa-pencil" aria-hidden="true"></i></button>' +
            '<input id="rdbTitleInput" class="reporting-input rdb-title-input" hidden ' +
              'aria-label="' + esc(I18N.rename) + '">' +
          '</div>' +
          '<p id="rdbMeta" class="rdb-meta"></p>' +
        '</div>' +
        '<span class="rdb-spacer"></span>' +
        '<span id="rdbEditingPill" class="rdb-editing-pill" hidden>' +
          '<span class="rdb-editing-dot" aria-hidden="true"></span>' + esc(I18N.editing) + '</span>' +
        '<button type="button" id="rdbAddCard" class="rdb-addcard-btn" data-testid="rdb-add-card" hidden>' +
          '<i class="fas fa-plus" aria-hidden="true"></i>' + esc(I18N.addCard) + '</button>' +
        (canExport ?
          '<button type="button" id="rdbExport" class="nx-btn nx-btn--secondary" data-testid="rdb-export">' +
            '<i class="fas fa-file-export" aria-hidden="true"></i>' + esc(I18N.export_) + '</button>'
          : '') +
        '<button type="button" id="rdbEditToggle" class="nx-btn nx-btn--primary" data-testid="rdb-edit-toggle"></button>' +
      '</div>' +
      '<div id="rdbFilterBar" class="rdb-filterbar" data-testid="rdb-filter-bar">' +
        '<span class="rdb-filterbar-label"><i class="fas fa-filter" aria-hidden="true"></i>' +
          esc(I18N.globalFilters) + '</span>' +
        '<span class="rdb-filterbar-divider"></span>' +
        '<span id="rdbFilterChips" class="rdb-filterchips"></span>' +
        '<span class="rdb-spacer"></span>' +
        '<span class="rdb-filterbar-hint">' + esc(I18N.filterHint) + '</span>' +
      '</div>' +
      '<div id="rdbGrid" class="rdb-grid" data-testid="rdb-grid"></div>';
    el('rdbBack').addEventListener('click', close);
    el('rdbRenamePencil').addEventListener('click', revealTitleInput);
    el('rdbTitleInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') commitTitle();
    });
    el('rdbTitleInput').addEventListener('blur', commitTitle);
    if (canExport) el('rdbExport').addEventListener('click', toggleExportMenu);
    // Header "Add card" and the grid's add-card tile both open the same
    // one-dialog mask (report -> type -> size). There is no fast path that
    // drops an unconfigured card straight onto the grid any more.
    el('rdbAddCard').addEventListener('click', openAddMask);
    el('rdbEditToggle').addEventListener('click', toggleEditing);
    // Delegated grid clicks -- cards (and the add-card tile) are rebuilt/
    // replaced on every render, so direct per-element listeners would be
    // lost on re-render.
    el('rdbGrid').addEventListener('click', function (e) {
      var filterX = e.target.closest && e.target.closest('[data-testid="rdb-card-filter-remove"]');
      if (filterX) {
        var filterCardEl = filterX.closest('[data-card-id]');
        if (filterCardEl) clearCardOverrides(filterCardEl.getAttribute('data-card-id'));
        return;
      }
      var dup = e.target.closest && e.target.closest('[data-testid="rdb-card-dup"]');
      if (dup) {
        var dupCardEl = dup.closest('[data-card-id]');
        if (dupCardEl) duplicateCard(dupCardEl.getAttribute('data-card-id'));
        return;
      }
      var rm = e.target.closest && e.target.closest('[data-testid="rdb-card-remove"]');
      if (rm) {
        var rmCardEl = rm.closest('[data-card-id]');
        if (rmCardEl) removeCard(rmCardEl.getAttribute('data-card-id'));
        return;
      }
      var configure = e.target.closest && e.target.closest('[data-testid="rdb-card-configure"]');
      if (configure) {
        var cfgCardEl = configure.closest('[data-card-id]');
        if (cfgCardEl) openReportPicker(cfgCardEl.getAttribute('data-card-id'));
        return;
      }
      var addTile = e.target.closest && e.target.closest('[data-testid="rdb-add-tile"]');
      if (addTile) { openAddMask(); return; }
      // Whole-report card: table toggle (show/hide the full grid in place,
      // same msgids as the Simple pane's own #rsTableToggle) and row
      // drill-through (mirrors handleCardTableRowClick; forecast rows stay
      // inert).
      var rtToggle = e.target.closest && e.target.closest('.rdb-report-table-toggle');
      if (rtToggle) {
        var rtCardEl = rtToggle.closest('[data-card-id]');
        var rtWrap = rtCardEl && rtCardEl.querySelector('.rdb-report-table');
        if (rtWrap) {
          rtWrap.hidden = !rtWrap.hidden;
          rtToggle.textContent = rtWrap.hidden ? I18N.showTable : I18N.hideTable;
        }
        return;
      }
      var rtRow = e.target.closest && e.target.closest('.rdb-report-table tbody tr');
      if (rtRow) {
        if (rtRow.classList.contains('is-forecast') || !rtRow.closest('.reporting-drill-clickable')) return;
        var rtRows = Array.prototype.filter.call(rtRow.parentNode.children, function (tr) {
          return !tr.classList.contains('is-forecast');
        });
        var rtCardWrap = rtRow.closest('[data-card-id]');
        var rtCard = rtCardWrap && findCardById(rtCardWrap.getAttribute('data-card-id'));
        if (rtCard) handleCardTableRowClick(rtCard, rtRows.indexOf(rtRow));
        return;
      }
      // Table-card row drill-through (Task 15): renderTable draws each row as
      // a flat k/v span pair (no per-row wrapper element -- see its comment),
      // so the row index is derived from the hit span's position among its
      // siblings rather than a data-row-index attribute.
      var tableHit = e.target.closest && e.target.closest('.rdb-table-k, .rdb-table-v');
      if (tableHit) {
        var rowsContainer = tableHit.closest('[data-testid="rdb-table-rows"]');
        var tableCardEl = tableHit.closest('[data-card-id]');
        if (rowsContainer && tableCardEl) {
          var siblings = Array.prototype.slice.call(rowsContainer.children);
          var pos = siblings.indexOf(tableHit);
          var tableCard = pos > -1 && findCardById(tableCardEl.getAttribute('data-card-id'));
          if (tableCard) handleCardTableRowClick(tableCard, Math.floor(pos / 2));
        }
      }
    });
    // Drag-to-reorder (D10, ported 1:1 from the prototype's onDragStart/
    // onDragOver/onDrop/onDragEnd) -- delegated on the grid since HTML5 DnD
    // events bubble and cards are rebuilt on every render.
    // Corner-resize drags (Pointer Events) are delegated on the grid for the
    // same reason: the handle is rebuilt with its card on every render.
    el('rdbGrid').addEventListener('pointerdown', handleGridPointerDown);
    el('rdbGrid').addEventListener('dragstart', handleGridDragStart);
    el('rdbGrid').addEventListener('dragover', handleGridDragOver);
    el('rdbGrid').addEventListener('drop', handleGridDrop);
    el('rdbGrid').addEventListener('dragend', handleGridDragEnd);
    // Filter popover / export menu: outside-click / Escape close -- same
    // idiom as the Simple pane's rs-more-menu (hidden flag + outside-click +
    // Escape).
    document.addEventListener('click', function (e) {
      if (filterPop.open) {
        var pop = el('rdbFilterPop');
        if (pop && !pop.contains(e.target)) closeFilterPopover();
      }
      if (exportMenu.open) {
        var menu = el('rdbExportMenu');
        var onBtn = e.target.closest && e.target.closest('#rdbExport');
        if (menu && !menu.contains(e.target) && !onBtn) closeExportMenu();
      }
    });
    document.addEventListener('keydown', function (e) {
      if (filterPop.open && e.key === 'Escape') closeFilterPopover();
      if (reportPicker.open && e.key === 'Escape') closeReportPicker();
      if (addMask.open && e.key === 'Escape') closeAddMask();
      if (exportMenu.open && e.key === 'Escape') closeExportMenu();
    });
    built = true;
  }

  function revealTitleInput() {
    if (!state.editing) return;
    var input = el('rdbTitleInput');
    input.value = state.def.title || '';
    input.hidden = false;
    el('rdbTitle').hidden = true;
    el('rdbRenamePencil').hidden = true;
    input.focus();
  }

  function commitTitle() {
    var input = el('rdbTitleInput');
    if (input.hidden) return;
    var v = input.value.trim();
    if (v && v !== state.def.title) { state.def.title = v; state.dirty = true; }
    renderHeader();
  }

  function renderHeader() {
    var def = state.def || blankDef();
    el('rdbTitle').hidden = false;
    el('rdbTitle').textContent = def.title || I18N.untitled;
    el('rdbTitleInput').hidden = true;
    el('rdbMeta').textContent = I18N.cardsMeta.replace('{n}', String((def.cards || []).length));
    el('rdbEditingPill').hidden = !state.editing;
    el('rdbAddCard').hidden = !state.editing;
    el('rdbRenamePencil').hidden = !state.editing || !state.canEdit;
    el('rdbEditToggle').hidden = !state.canEdit;
    el('rdbEditToggle').textContent = state.editing ? I18N.done : I18N.edit;
  }

  // ---- D4 filter merge -------------------------------------------------
  // card.definition.filters (base) + state.def.globalFilters (dashboard-
  // wide) + card.filterOverrides (per-card), concatenated in that order.
  // De-duping is by EXACT duplicate only (same field+op+value) -- two
  // DIFFERENT filters on the same field (e.g. a "date >= X" + "date <= Y"
  // range pair split across gte/lte) both survive as an AND. Previously
  // this keyed by field with last-write-wins (`byField[f.field] = f`),
  // which silently dropped the earlier of two same-field filters and
  // widened the card's query (Task 61). Exact semantics Tasks 13 (override
  // editing UI) and 15 (KPI trend/drill) build on -- keep this shape if
  // it's ever extended.
  function effectiveFilters(card) {
    var result = [];
    var seen = {};
    function apply(list) {
      (list || []).forEach(function (f) {
        if (!f || f.field == null) return;
        var key = f.field + '|' + f.op + '|' + JSON.stringify(f.value);
        if (seen[key]) return;
        seen[key] = true;
        result.push(f);
      });
    }
    apply(card.definition && card.definition.filters);
    apply(state.def && state.def.globalFilters);
    apply(card.filterOverrides);
    return result;
  }

  // ---- KPI trend period-shift (D8) ---------------------------------------
  // A "date-range filter" is any effective filter with op 'between' -- the
  // same signal the Advanced pane's own drill code uses to spot the date
  // axis (see _reporting_js.html: `x.op === 'between'`). Its value is either
  // a relative-date token {token:'<name>'} or a literal [start, end] ISO
  // pair (the Simple wizard's own two shapes -- _reporting_simple_js.html's
  // isTokenValue/TOKEN_LABELS).
  function isTokenValue(v) {
    return !!v && typeof v === 'object' && !Array.isArray(v) && typeof v.token === 'string';
  }

  // Known relative-date tokens with a documented "previous period" sibling
  // (nx_lib/reporting/tokens.py's RELATIVE_DATE_TOKENS) -- mapped directly,
  // never re-derived client-side. Tokens without a listed sibling here
  // (last_year, last_month, last_quarter, last_week, last_3_months,
  // last_n_days, today, yesterday) are NOT resolved locally -- doing so
  // would duplicate the server's own date math -- so shiftDateRangeFilter
  // returns null for them (D8: honest numbers or nothing).
  var PREV_TOKEN = {
    this_week: 'last_week', this_month: 'last_month',
    this_quarter: 'last_quarter', this_year: 'last_year'
  };

  function isoDate(d) { return d.toISOString().slice(0, 10); }

  // Pure: given ONE date-range filter, returns the equivalent filter for
  // "one period back", or null when no shift is possible. A token with a
  // sibling in PREV_TOKEN maps directly; a literal [start, end] pair shifts
  // back by its own (inclusive) length, ending the day before `start`.
  function shiftDateRangeFilter(f) {
    if (!f || f.op !== 'between') return null;
    var v = f.value;
    if (isTokenValue(v)) {
      var prev = PREV_TOKEN[v.token];
      return prev ? { field: f.field, op: 'between', value: { token: prev } } : null;
    }
    if (Array.isArray(v) && v.length === 2 && v[0] && v[1]) {
      var start = new Date(String(v[0]).slice(0, 10) + 'T00:00:00Z');
      var end = new Date(String(v[1]).slice(0, 10) + 'T00:00:00Z');
      if (isNaN(start.getTime()) || isNaN(end.getTime()) || end < start) return null;
      var spanMs = end.getTime() - start.getTime();
      var newEnd = new Date(start.getTime() - 86400000);
      var newStart = new Date(newEnd.getTime() - spanMs);
      return { field: f.field, op: 'between', value: [isoDate(newStart), isoDate(newEnd)] };
    }
    return null;
  }

  // ---- Filter-field catalog (D11) ----------------------------------------
  // Self-contained: fetches its own copy of the same catalog endpoints the
  // Simple pane loads (GET /api/reporting/sources + /metrics) -- this is a
  // separate IIFE, it can't read the Simple pane's already-fetched state.
  // Lazy: only fetched the first time a filter popover opens, cached after.
  var catalog = { loaded: false, sources: [] };

  async function ensureCatalog() {
    if (catalog.loaded) return;
    var list = null;
    try { list = await ReportingCatalog.sources(); } catch (e) { list = null; }
    catalog.sources = Array.isArray(list) ? list : [];
    catalog.loaded = true;
  }

  // Distinct source ids actually used by this dashboard's cards. Empty on a
  // brand-new/empty dashboard -- filterableFieldCatalog() then falls back to
  // every catalog source (nothing to narrow by yet).
  function cardSourceIds() {
    var ids = [];
    ((state.def && state.def.cards) || []).forEach(function (c) {
      var sid = c.definition && c.definition.source;
      if (sid && ids.indexOf(sid) === -1) ids.push(sid);
    });
    return ids;
  }

  // The popover field <select>'s options: filterable fields of the sources
  // the card sources' shared catalog. Deduped by field key (first match's
  // label wins) since a global filter targets one field across every card.
  function filterableFieldCatalog() {
    var ids = cardSourceIds();
    var out = [], seen = {};
    catalog.sources.forEach(function (src) {
      if (ids.length && ids.indexOf(src.id) === -1) return;
      (src.fields || []).forEach(function (f) {
        if (!f.filterable || seen[f.field]) return;
        seen[f.field] = 1;
        out.push(f);
      });
    });
    return out;
  }

  function fieldMetaByKey(key) {
    var match = null;
    filterableFieldCatalog().forEach(function (f) { if (f.field === key) match = f; });
    return match;
  }

  // Text vs. date value input -- same rule as the Simple pane's chip editor
  // (filterChipEditor in _reporting_simple_js.html) and the Advanced
  // builder's filter row (_reporting_js.html): grainable OR a "date"-ish type.
  function isDateFieldMeta(meta) {
    return !!(meta && (meta.grainable || /date/i.test(meta.type || '')));
  }

  function filterChipLabel(f) {
    var meta = fieldMetaByKey(f.field);
    var parts = [(meta && meta.label) || f.field, OP_LABELS[f.op] || f.op];
    if (f.value != null && f.value !== '') parts.push(String(f.value));
    return parts.join(' ');
  }

  // ---- Global filter popover (D11 -- field/op/value, self-contained) -----
  var filterPop = { open: false, index: -1 };

  function closeFilterPopover() {
    var pop = el('rdbFilterPop');
    if (pop && pop.parentNode) pop.parentNode.removeChild(pop);
    filterPop.open = false;
    filterPop.index = -1;
  }

  function positionFilterPopover(pop, anchorEl) {
    var bar = el('rdbFilterBar');
    var barRect = bar.getBoundingClientRect();
    var aRect = anchorEl.getBoundingClientRect();
    pop.style.top = (aRect.bottom - barRect.top + 8) + 'px';
    pop.style.left = Math.max(0, aRect.left - barRect.left) + 'px';
  }

  // is_null/is_not_null carry no value (mirrors the Simple/Advanced chip
  // editors skipping a value for those ops); text vs. date otherwise.
  function refreshFilterPopoverValueField(pop) {
    var fieldSel = pop.querySelector('[data-testid="rdb-filter-field"]');
    var opSel = pop.querySelector('[data-testid="rdb-filter-op"]');
    var valInput = pop.querySelector('[data-testid="rdb-filter-value"]');
    var isNullOp = opSel.value === 'is_null' || opSel.value === 'is_not_null';
    valInput.hidden = isNullOp;
    valInput.type = isDateFieldMeta(fieldMetaByKey(fieldSel.value)) ? 'date' : 'text';
  }

  // Opens (or replaces) the popover under anchorEl. existing/index are null/-1
  // for a brand-new filter (appended on apply); otherwise the filter object +
  // its index in state.def.globalFilters being edited in place ("cycle"
  // becomes "open popover pre-filled" per D11 -- no more fixed value lists).
  async function openFilterPopover(anchorEl, existing, index) {
    await ensureCatalog();
    // Task 34: defer the actual open past this click's bubble phase.
    // ensureCatalog()'s promise is cached after the first call, so on every
    // later open the `await` above resolves in a microtask -- and browsers
    // run queued microtasks between bubble-phase listeners of the SAME
    // event, i.e. before this click finishes bubbling to the document-level
    // outside-click closer wired in build(). That closer would then see
    // filterPop.open just flipped true and the click target outside the
    // (brand new) popover, and close it immediately -- the popover would
    // only ever survive the first, slow, uncached open. setTimeout(fn, 0)
    // pushes the popover-creation into its own task, strictly after the
    // triggering click's synchronous dispatch (and the closer's check
    // against it) has already completed, so there is nothing left for the
    // closer to mistake for an outside click.
    setTimeout(function () {
      if (!anchorEl.isConnected) return;  // bar re-rendered while fetching
      closeFilterPopover();
      var fields = filterableFieldCatalog();
      if (!fields.length) return;  // nothing filterable to offer
      var f = existing || { field: fields[0].field, op: 'eq', value: '' };

      var pop = document.createElement('div');
      pop.id = 'rdbFilterPop';
      pop.className = 'rdb-filter-pop';
      pop.setAttribute('data-testid', 'rdb-filter-pop');
      pop.setAttribute('role', 'dialog');
      pop.setAttribute('aria-label', I18N.globalFilters);

      var fieldLabelEl = document.createElement('label');
      fieldLabelEl.textContent = I18N.filterField;
      var fieldSel = document.createElement('select');
      fieldSel.setAttribute('data-testid', 'rdb-filter-field');
      fields.forEach(function (fm) {
        var o = document.createElement('option');
        o.value = fm.field; o.textContent = fm.label || fm.field;
        fieldSel.appendChild(o);
      });
      fieldSel.value = f.field;

      var opLabelEl = document.createElement('label');
      opLabelEl.textContent = I18N.filterOperator;
      var opSel = document.createElement('select');
      opSel.setAttribute('data-testid', 'rdb-filter-op');
      FILTER_OPS.forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o; opt.textContent = OP_LABELS[o] || o;
        opSel.appendChild(opt);
      });
      opSel.value = f.op || 'eq';

      var valLabelEl = document.createElement('label');
      valLabelEl.textContent = I18N.filterValue;
      var valInput = document.createElement('input');
      valInput.className = 'reporting-input';
      valInput.setAttribute('data-testid', 'rdb-filter-value');
      valInput.value = f.value == null ? '' : f.value;

      var actions = document.createElement('div');
      actions.className = 'rdb-filter-pop-actions';
      var cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'nx-btn nx-btn--secondary';
      cancelBtn.setAttribute('data-testid', 'rdb-filter-cancel');
      cancelBtn.textContent = I18N.cancel;
      cancelBtn.addEventListener('click', closeFilterPopover);
      var applyBtn = document.createElement('button');
      applyBtn.type = 'button';
      applyBtn.className = 'nx-btn nx-btn--primary';
      applyBtn.setAttribute('data-testid', 'rdb-filter-apply');
      applyBtn.textContent = I18N.apply;
      applyBtn.addEventListener('click', function () {
        var isNullOp = opSel.value === 'is_null' || opSel.value === 'is_not_null';
        applyGlobalFilter(index, fieldSel.value, opSel.value, isNullOp ? null : valInput.value);
      });
      actions.appendChild(cancelBtn);
      actions.appendChild(applyBtn);

      pop.appendChild(fieldLabelEl); pop.appendChild(fieldSel);
      pop.appendChild(opLabelEl); pop.appendChild(opSel);
      pop.appendChild(valLabelEl); pop.appendChild(valInput);
      pop.appendChild(actions);

      fieldSel.addEventListener('change', function () { refreshFilterPopoverValueField(pop); });
      opSel.addEventListener('change', function () { refreshFilterPopoverValueField(pop); });

      el('rdbFilterBar').appendChild(pop);
      refreshFilterPopoverValueField(pop);
      positionFilterPopover(pop, anchorEl);
      filterPop.open = true;
      filterPop.index = (index === undefined || index === null) ? -1 : index;
      valInput.focus();
    }, 0);
  }

  // ---- Selective re-run (only cards whose effectiveFilters() changed) ----
  function snapshotEffectiveByCard() {
    var map = {};
    ((state.def && state.def.cards) || []).forEach(function (c) {
      map[c.id] = JSON.stringify(effectiveFilters(c));
    });
    return map;
  }

  function rerunCardsWhereChanged(before) {
    ((state.def && state.def.cards) || []).forEach(function (c) {
      if (JSON.stringify(effectiveFilters(c)) !== before[c.id]) renderCard(c);
    });
  }

  function applyGlobalFilter(index, field, op, value) {
    var before = snapshotEffectiveByCard();
    state.def.globalFilters = state.def.globalFilters || [];
    var f = { field: field, op: op, value: value };
    if (index == null || index < 0) {
      state.def.globalFilters.push(f);
    } else {
      state.def.globalFilters[index] = f;
    }
    state.dirty = true;
    closeFilterPopover();
    renderFilterBar();
    rerunCardsWhereChanged(before);
  }

  function removeGlobalFilter(index) {
    var before = snapshotEffectiveByCard();
    state.def.globalFilters.splice(index, 1);
    state.dirty = true;
    closeFilterPopover();
    renderFilterBar();
    rerunCardsWhereChanged(before);
  }

  // Per-card override chip's x: clears filterOverrides ENTIRELY for that
  // card (no partial-edit UI in v1 -- overrides are set elsewhere, e.g. a
  // dropped saved report's own filters; this task only ships clearing them).
  function clearCardOverrides(cardId) {
    var card = ((state.def && state.def.cards) || []).find(function (c) { return c.id === cardId; });
    if (!card || !card.filterOverrides || !card.filterOverrides.length) return;
    card.filterOverrides = [];
    state.dirty = true;
    renderCard(card);
  }

  function renderFilterBar() {
    closeFilterPopover();
    var chips = el('rdbFilterChips');
    chips.innerHTML = '';
    var filters = (state.def && state.def.globalFilters) || [];
    filters.forEach(function (f, i) {
      var chipEl = document.createElement('span');
      chipEl.className = 'reporting-drill-chip reporting-drill-chip--indigo rdb-gfilter';
      chipEl.setAttribute('data-testid', 'rdb-gfilter');
      chipEl.tabIndex = 0;
      var icon = document.createElement('i');
      icon.className = 'fas fa-filter';
      icon.setAttribute('aria-hidden', 'true');
      var label = document.createElement('span');
      label.textContent = filterChipLabel(f);
      var x = document.createElement('i');
      x.className = 'fas fa-xmark rdb-gfilter-x';
      x.setAttribute('data-testid', 'rdb-gfilter-remove');
      x.setAttribute('aria-hidden', 'true');
      x.addEventListener('click', function (e) { e.stopPropagation(); removeGlobalFilter(i); });
      chipEl.appendChild(icon); chipEl.appendChild(label); chipEl.appendChild(x);
      chipEl.addEventListener('click', function () { openFilterPopover(chipEl, f, i); });
      chips.appendChild(chipEl);
    });
    var add = document.createElement('button');
    add.type = 'button';
    add.className = 'rdb-add-filter';
    add.setAttribute('data-testid', 'rdb-add-filter');
    add.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i>' + esc(I18N.addFilter);
    add.addEventListener('click', function () { openFilterPopover(add, null, -1); });
    chips.appendChild(add);
  }

  // ---- Chart instance lifecycle -----------------------------------------
  // Keyed by card id. Same destroy-before-recreate discipline as
  // ReportingViz.destroyChart (templates/js/_reporting_viz_js.html) --
  // forgetting this leaks a canvas + its ResizeObserver on every re-render.
  var charts = {};

  function destroyCardChart(id) {
    if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  }

  function destroyChartsExcept(keepIds) {
    Object.keys(charts).forEach(function (id) {
      if (!keepIds[id]) destroyCardChart(id);
    });
  }

  // ---- Small formatting/number helpers -----------------------------------
  function toNum(v) {
    if (v === null || v === undefined || v === '') return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }

  function fmtNum(v) {
    var n = toNum(v);
    if (n === null) return v == null ? '—' : String(v);
    return n.toLocaleString('en-US', { maximumFractionDigits: Number.isInteger(n) ? 0 : 2 });
  }

  function fmtLabel(v) { return v == null ? '' : String(v); }

  // Leading response columns are the definition's dimensions, the trailing
  // ones its metrics; the first metric is the value a card draws. A
  // zero-dimension definition (KPI cards run a zero-column clone, same
  // pattern as the Simple pane's grand-total call) returns just the metric
  // columns, so there's no dimension to read.
  //
  // `dims` is every dimension index: dims[0] is the axis, dims[1..] are the
  // breakdown that renderLine/renderBar pivot into series (#174). Before
  // that this returned a fixed val:1, so a two-dimension report read its
  // SECOND DIMENSION as the value -- toNum('Invoice') === null -- and every
  // such card drew a flat zero line while the same report charted correctly
  // in the Simple result view.
  function dimValIdx(columns, card) {
    var nMetrics = ((card && card.definition && card.definition.metrics) || []).length || 1;
    var val = Math.max(0, columns.length - nMetrics);
    var dims = [];
    for (var i = 0; i < val; i++) dims.push(i);
    return { dim: dims.length ? 0 : -1, val: val, dims: dims };
  }

  // Display label for a row's dimensions: the axis value on its own for a
  // single-dim card, all of them joined for a breakdown ("Jan · Invoice"),
  // matching the Simple pane's series labels.
  function dimLabel(row, idx) {
    return idx.dims.map(function (d) { return fmtLabel(row[d]); }).join(' · ');
  }

  // Two-dimension pivot: first dim = axis, the remaining dims joined = one
  // series each. Ported from the Simple pane's chart builder
  // (_reporting_simple_js.html, its `dims >= 2` branch) per #174 -- the logic
  // already existed, cards just never used it. Series are ordered by total
  // desc and capped at SERIES_PALETTE.length; the overflow count comes back
  // in `hidden` so the caller can say so rather than truncate silently.
  function pivotCard(rows, idx) {
    var xOrder = [], rawX = [], cell = {}, tot = {}, parts = {};
    rows.forEach(function (r) {
      var x = fmtLabel(r[idx.dims[0]]);
      var pv = [], lbl = [];
      for (var d = 1; d < idx.dims.length; d++) { pv.push(r[idx.dims[d]]); lbl.push(fmtLabel(r[idx.dims[d]])); }
      var s = lbl.join(' · ');
      var v = toNum(r[idx.val]) || 0;
      if (!cell[x]) { xOrder.push(x); rawX.push(r[idx.dims[0]]); cell[x] = {}; }
      // Every breakdown dim is in the series key, so a cell is one exact
      // aggregate row -- nothing is summed across buckets, which keeps
      // avg/min/max metrics honest (same reasoning as the Simple pane).
      cell[x][s] = (cell[x][s] || 0) + v;
      tot[s] = (tot[s] || 0) + v;
      parts[s] = pv;
    });
    var keys = Object.keys(tot).sort(function (a, b) { return tot[b] - tot[a]; });
    var shown = keys.slice(0, SERIES_PALETTE.length);
    return {
      labels: xOrder, rawX: rawX, hidden: keys.length - shown.length, total: keys.length,
      series: shown.map(function (s, i) {
        return {
          label: s, parts: parts[s], color: SERIES_PALETTE[i],
          data: xOrder.map(function (x) { return cell[x][s] || 0; })
        };
      })
    };
  }

  // Note line above a chart body when the pivot dropped series (never a
  // silent cap). Returns '' when everything fit.
  function seriesCapNoteHtml(pv) {
    if (!pv.hidden) return '';
    return '<p class="rdb-card-note" data-testid="rdb-card-note">' + esc(
      I18N.chartSeriesCapped.replace('{shown}', String(pv.series.length))
                            .replace('{n}', String(pv.total))) + '</p>';
  }

  // Chart.js options shared by the multi-series line/bar branches: a legend
  // (single-series cards keep it off -- one unnamed series needs no key) and
  // the drill-through hit-test, which for a pivoted card must carry the
  // clicked SERIES as well as the x bucket.
  function multiSeriesOptions(card, pv) {
    return {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: true, position: 'bottom',
        labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: 'circle',
                  font: { family: 'Inter', size: 10.5 }, color: tickColor(), padding: 10 } } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { family: 'Inter', size: 10.5 }, color: tickColor() } },
        y: { grid: { color: dividerColor() },
             ticks: { font: { family: 'Inter', size: 10.5 }, color: tickColor() } }
      },
      onClick: function (evt) {
        var els = this.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
        if (els.length) handleCardSeriesClick(card, pv, els[0].datasetIndex, els[0].index);
      }
    };
  }

  function findCardEl(id) {
    var nodes = el('rdbGrid').children;
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].getAttribute('data-card-id') === id) return nodes[i];
    }
    return null;
  }

  function findCardById(id) {
    return ((state.def && state.def.cards) || []).find(function (c) { return c.id === id; });
  }

  function dividerColor() {
    return getComputedStyle(document.documentElement).getPropertyValue('--nx-divider').trim() || '#e5e7eb';
  }

  // Chart-build-time dark check (Task 16) -- read once per render call, not
  // live-reactive: toggling dark mode with a dashboard open re-themes on the
  // next render, which is acceptable v1 (see the redesign plan's Task 16).
  function isDark() {
    return document.documentElement.classList.contains('dark');
  }

  function tickColor() {
    return isDark() ? '#64748b' : '#9ca3af';
  }

  // ---- Drill-through (chart-element / table-row clicks) ------------------
  // Last successful {columns, rows} per card id -- feeds the click handlers
  // below (a Chart.js onClick only gets the clicked point's index; the raw
  // row values it maps to live here, same idea as the Simple pane's own
  // state.chartData.rawX). Populated by runCard() on every successful run.
  var cardRunData = {};

  // Mirrors the Simple pane's chart onClick -> ReportingDrill.open call
  // exactly (_reporting_simple_js.html's drillFromChart/openDrill): fields
  // come from this module's own lazily-fetched source catalog (D11, Task
  // 13's ensureCatalog), definition = the card definition with merged
  // filters, clicked = one {field, grain, value} entry per dimension the card
  // breaks down by (see clickedFor -- a pivoted two-dim card drills on axis
  // AND series), header = the card's own title (simpler than Simple's
  // per-value header, since a dashboard card's title already names what's
  // being drilled into).
  async function openCardDrill(card, clicked) {
    if (!card.definition || !card.definition.source) return;
    await ensureCatalog();
    var src = catalog.sources.find(function (s) { return s.id === card.definition.source; });
    if (!src) return;
    var def = Object.assign({}, card.definition || {});
    def.filters = effectiveFilters(card);
    ReportingDrill.open({
      definition: def, fields: src.fields || [],
      clicked: clicked, header: card.title || ''
    });
  }

  // One {field, grain, value} entry per dimension, given that dimension's
  // raw values. The field/grain come from the CARD'S OWN DEFINITION
  // (card.definition.columns) -- mirrors the Simple pane's own
  // clickedFor/drillFromChart in _reporting_simple_js.html, which reads
  // state.current.def.columns rather than the run result's columns. The run
  // result's columns are only {field, header} (api_reports_run never echoes
  // grain), so sourcing grain from there always drilled as an exact-value
  // match on the truncated bucket label instead of a date range.
  function clickedFor(card, idx, values) {
    var defCols = (card.definition && card.definition.columns) || [];
    var out = [];
    idx.dims.forEach(function (d, i) {
      var col = defCols[d];
      if (col) out.push({ field: col.field, grain: col.grain || null, value: values[i] });
    });
    return out;
  }

  // index is the Chart.js element index from onClick (getElementsAtEventForMode).
  function handleCardChartClick(card, index) {
    var data = cardRunData[card.id];
    if (!data) return;
    var idx = dimValIdx(data.columns, card);
    if (idx.dim < 0) return;  // no dimension column -- nothing to drill on
    var row = data.rows[index];
    if (!row) return;
    var clicked = clickedFor(card, idx, idx.dims.map(function (d) { return row[d]; }));
    if (clicked.length) openCardDrill(card, clicked);
  }

  // Pivoted (multi-series) line/bar cards: the clicked element identifies a
  // series AND an x bucket, and both must reach the drill -- otherwise
  // clicking one process's point drills into every process for that month.
  // The pivot keeps each series' raw per-dim values in `parts`, same as the
  // Simple pane's chartData.rawSeries.
  function handleCardSeriesClick(card, pv, datasetIndex, index) {
    var idx = dimValIdx((cardRunData[card.id] || {}).columns || [], card);
    var s = pv.series[datasetIndex];
    if (!s || index >= pv.rawX.length) return;
    var clicked = clickedFor(card, idx, [pv.rawX[index]].concat(s.parts));
    if (clicked.length) openCardDrill(card, clicked);
  }

  // rowIndex is the table card's row position (0-based, matching the capped
  // rows renderTable actually drew).
  function handleCardTableRowClick(card, rowIndex) {
    var data = cardRunData[card.id];
    if (!data) return;
    var idx = dimValIdx(data.columns, card);
    if (idx.dim < 0) return;
    var row = data.rows[rowIndex];
    if (!row) return;
    var clicked = clickedFor(card, idx, idx.dims.map(function (d) { return row[d]; }));
    if (clicked.length) openCardDrill(card, clicked);
  }

  // ---- Per-type card body renderers --------------------------------------
  // Each takes the already-cleared <body> element for the card plus the
  // {columns, rows} the run returned, and draws into it.
  function renderKpi(card, body, columns, rows) {
    var idx = dimValIdx(columns, card);
    var v = rows.length ? rows[0][idx.val] : null;
    body.innerHTML = '<p class="rdb-kpi-value" data-testid="rdb-kpi-value">' + esc(fmtNum(v)) + '</p>';
  }

  function renderLine(card, body, columns, rows) {
    destroyCardChart(card.id);
    if (typeof Chart === 'undefined') { body.textContent = I18N.chartUnavailable; return; }
    var idx = dimValIdx(columns, card);
    if (idx.dims.length > 1) return renderMultiSeries(card, body, rows, idx, 'line');
    body.innerHTML = '<div class="rdb-chart-wrap"><canvas></canvas></div>';
    var canvas = body.querySelector('canvas');
    var labels = rows.map(function (r) { return idx.dim >= 0 ? fmtLabel(r[idx.dim]) : ''; });
    var data = rows.map(function (r) { return toNum(r[idx.val]) || 0; });
    var ctx = canvas.getContext('2d');
    var h = (canvas.parentNode && canvas.parentNode.clientHeight) || 190;
    var gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, 'rgba(79,70,229,.20)');
    gradient.addColorStop(1, 'rgba(79,70,229,0)');
    charts[card.id] = new Chart(ctx, {
      type: 'line',
      data: { labels: labels, datasets: [{
        data: data, borderColor: '#4f46e5', borderWidth: 2.5, tension: 0.4,
        pointRadius: 0, fill: true, backgroundColor: gradient
      }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { family: 'Inter', size: 10.5 }, color: tickColor() } },
          y: { grid: { color: dividerColor() },
               ticks: { font: { family: 'Inter', size: 10.5 }, color: tickColor() } }
        },
        // Drill-through (Task 15): same getElementsAtEventForMode hit-test
        // the Simple pane's own chart onClick uses.
        onClick: function (evt) {
          var els = this.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
          if (els.length) handleCardChartClick(card, els[0].index);
        }
      }
    });
  }

  function renderBar(card, body, columns, rows) {
    destroyCardChart(card.id);
    if (typeof Chart === 'undefined') { body.textContent = I18N.chartUnavailable; return; }
    var idx = dimValIdx(columns, card);
    if (idx.dims.length > 1) return renderMultiSeries(card, body, rows, idx, 'bar');
    body.innerHTML = '<div class="rdb-chart-wrap"><canvas></canvas></div>';
    var canvas = body.querySelector('canvas');
    var labels = rows.map(function (r) { return idx.dim >= 0 ? fmtLabel(r[idx.dim]) : ''; });
    var data = rows.map(function (r) { return toNum(r[idx.val]) || 0; });
    var colors = labels.map(function (_, i) { return CARD_PALETTE[i % CARD_PALETTE.length]; });
    charts[card.id] = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { labels: labels, datasets: [{ data: data, backgroundColor: colors, borderRadius: 5, barThickness: 26 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { family: 'Inter', size: 10.5 }, color: tickColor() } },
          y: { grid: { color: dividerColor() },
               ticks: { font: { family: 'Inter', size: 10.5 }, color: tickColor() } }
        },
        onClick: function (evt) {
          var els = this.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
          if (els.length) handleCardChartClick(card, els[0].index);
        }
      }
    });
  }

  // Two-dimension line/bar cards (#174): axis = first dim, one colored,
  // named series per remaining-dims combination -- what the Simple result
  // view has always drawn for the same report. Legend on (a named series
  // needs its key); single-series cards keep their locked indigo look above.
  function renderMultiSeries(card, body, rows, idx, type) {
    var pv = pivotCard(rows, idx);
    body.innerHTML = seriesCapNoteHtml(pv) + '<div class="rdb-chart-wrap"><canvas></canvas></div>';
    var canvas = body.querySelector('canvas');
    charts[card.id] = new Chart(canvas.getContext('2d'), {
      type: type,
      data: {
        labels: pv.labels,
        datasets: pv.series.map(function (s) {
          return type === 'line'
            ? { label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color,
                borderWidth: 2, tension: 0.4, pointRadius: 0, fill: false }
            : { label: s.label, data: s.data, backgroundColor: s.color,
                borderRadius: 5, maxBarThickness: 26 };
        })
      },
      options: multiSeriesOptions(card, pv)
    });
  }

  // Donut/table cap at 8 rows; donuts additionally roll the remainder into
  // an 8th "Other" segment (tables just show the first 8, no roll-up row).
  // A second dimension is not pivoted here -- a donut has no axis to pivot
  // against -- but it IS named: the segment label joins every dimension
  // ("Jan · Invoice"), so each segment stays one exact aggregate row rather
  // than silently charting the breakdown column as if it were the value.
  function renderDonut(card, body, columns, rows) {
    destroyCardChart(card.id);
    var idx = dimValIdx(columns, card);
    var pairs = rows.map(function (r) {
      return { label: dimLabel(r, idx), value: toNum(r[idx.val]) || 0 };
    });
    if (pairs.length > 8) {
      var rest = pairs.slice(7).reduce(function (a, p) { return a + p.value; }, 0);
      pairs = pairs.slice(0, 7).concat([{ label: I18N.other, value: rest }]);
    }
    var total = pairs.reduce(function (a, p) { return a + p.value; }, 0);
    var colors = pairs.map(function (_, i) { return CARD_PALETTE[i % CARD_PALETTE.length]; });
    body.innerHTML =
      '<div class="rdb-donut-wrap">' +
        '<div class="rdb-donut-ring">' +
          '<canvas></canvas>' +
          '<div class="rdb-donut-center" data-testid="rdb-donut-center">' +
            '<span class="rdb-donut-total-value">' + esc(fmtNum(total)) + '</span>' +
            '<span class="rdb-donut-total-label">' + esc(I18N.total) + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="rdb-donut-legend">' +
          pairs.map(function (p, i) {
            return '<div class="rdb-donut-legend-row">' +
              '<span class="rdb-donut-swatch" style="background:' + colors[i] + '"></span>' +
              '<span class="rdb-donut-legend-label">' + esc(p.label) + '</span>' +
              '<span class="rdb-donut-legend-value">' + esc(fmtNum(p.value)) + '</span>' +
            '</div>';
          }).join('') +
        '</div>' +
      '</div>';
    if (typeof Chart === 'undefined') return;
    var canvas = body.querySelector('canvas');
    charts[card.id] = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: { labels: pairs.map(function (p) { return p.label; }),
              datasets: [{ data: pairs.map(function (p) { return p.value; }),
                           backgroundColor: colors, borderColor: '#fff', borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '68%',
                 plugins: { legend: { display: false } } }
    });
  }

  // Each row is a flat k/v span pair with no wrapping element (2 children
  // per row, k then v) -- kept minimal since the CSS grid places them
  // directly; the grid's delegated click handler above derives the row
  // index from the hit span's position among rowsContainer.children.
  function renderTable(card, body, columns, rows) {
    destroyCardChart(card.id);
    var idx = dimValIdx(columns, card);
    var capped = rows.slice(0, 8);
    body.innerHTML = '<div class="rdb-table-rows" data-testid="rdb-table-rows">' +
      capped.map(function (r) {
        return '<span class="rdb-table-k">' + esc(dimLabel(r, idx)) + '</span>' +
               '<span class="rdb-table-v">' + esc(fmtNum(r[idx.val])) + '</span>';
      }).join('') +
    '</div>';
  }

  // Whole-report card: the saved report as the Simple tab shows it -- the
  // KPI band (one labelled total per measure, then Buckets/Avg/Peak), the
  // chart with its saved colours / right axis / forecast, and the full
  // table behind a toggle.
  // Everything is drawn by the Simple pane's own builders
  // (window.ReportingSimple), so the two surfaces cannot drift apart. `def`
  // is the effective definition that was POSTed (global filters merged).
  async function renderReportCard(card, body, def, data, gen) {
    destroyCardChart(card.id);
    var RS = window.ReportingSimple;
    await RS.ensureCatalogs();   // metric labels / latest-mode totals
    await ensureCatalog();       // this module's own source catalog (drill probe)
    if (runGen[card.id] !== gen) return;
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;
    var dims = (def.columns || []).length;
    var columns = data.columns || [];
    var rows = RS.zeroFillDateBuckets(def, data.rows || [], data.resolvedDates || []);
    var fc = data.forecast || null;
    // Same trailing trim as the Simple pane's runCurrent: zero-fill pads to
    // the filter range, but the forecast starts at the last REAL bucket.
    if (fc && !fc.unavailable && fc.anchor) {
      rows = rows.filter(function (r) {
        return String(r[0] == null ? '' : r[0]).slice(0, 10) <= fc.anchor;
      });
    }
    cardRunData[card.id] = { columns: columns, rows: rows };
    body.innerHTML =
      '<div class="rdb-report" data-testid="rdb-report">' +
        '<div class="rdb-report-side">' +
          '<div class="reporting-ledger-kpis rdb-report-kpis" data-testid="rdb-report-kpis" hidden></div>' +
        '</div>' +
        '<div class="nx-card nx-card--pad rdb-report-chartcard" data-testid="rdb-report-chartcard">' +
          '<p class="reporting-simple-chartnote rdb-report-note" data-testid="rdb-report-note" hidden></p>' +
          '<div class="rdb-report-chart"><canvas></canvas></div>' +
        '</div>' +
      '</div>' +
      '<div class="rdb-report-tablebar">' +
        '<button type="button" class="reporting-link rdb-report-table-toggle" ' +
          'data-testid="rdb-report-table-toggle">' + esc(I18N.showTable) + '</button>' +
      '</div>' +
      '<div class="reporting-table-wrap rdb-report-table" data-testid="rdb-report-table" hidden></div>';
    var q = function (sel) { return body.querySelector(sel); };

    // Per-measure grand totals. With a breakdown dimension, via a zero-column
    // clone -- correct for every aggregation (avg / count_distinct), unlike
    // summing the grouped rows. Same clone the Simple pane's runCurrent fires.
    // With NO dimension the breakdown run's own first row already IS the
    // total for this shape, so no second request is needed.
    var grandTotals = null;
    if (hasMetrics && dims) {
      var totalDef = JSON.parse(JSON.stringify(def));
      totalDef.columns = []; totalDef.sort = [];
      delete totalDef.forecast; delete totalDef.compare;
      var t = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(totalDef) });
      if (runGen[card.id] !== gen) return;
      if (t.ok && t.data && Array.isArray(t.data.rows) && t.data.rows.length) {
        grandTotals = t.data.rows[0];
      }
    } else if (hasMetrics && rows.length) {
      grandTotals = rows[0];
    }

    // KPI band (one labelled total per measure, then Buckets/Avg/Peak and the
    // prior-period chips). Cards skip the count-up animation and write the
    // final numbers.
    var kpiHtml = hasMetrics
      ? RS.kpiBandHtml(dims, rows, data.comparison || null, def, columns, grandTotals) : '';
    if (kpiHtml) {
      var kpis = q('.rdb-report-kpis');
      kpis.innerHTML = kpiHtml;
      kpis.hidden = false;
      Array.prototype.forEach.call(kpis.querySelectorAll('[data-count-target]'), function (span) {
        span.textContent = RS.fmtNumber(Number(span.getAttribute('data-count-target')));
      });
    }

    // Chart -- identical config to the Simple result view (saved colours,
    // right axis, forecast tail/band), on the card's own canvas.
    var charted = false;
    if (hasMetrics && dims && rows.length && typeof Chart !== 'undefined') {
      var built = RS.buildChartData(def, columns, rows, fc);
      if (built.note) { q('.rdb-report-note').textContent = built.note; q('.rdb-report-note').hidden = false; }
      if (built.data) {
        var cfg = RS.chartConfigFor(built.data, built.data.type, def, {
          onDrill: function (index, datasetIndex) { reportCardChartDrill(card, built.data, index, datasetIndex); }
        });
        charts[card.id] = new Chart(q('.rdb-report-chart canvas'), cfg.config);
        charted = true;
      } else {
        q('.rdb-report-chart').hidden = true;
      }
    } else {
      q('.rdb-report-chartcard').hidden = true;
    }

    // Table -- full rows (+ forecast rows). Collapsed behind the toggle only
    // when a chart carries the result, exactly like the Simple pane.
    var drillable = !!(hasMetrics && dims && rows.length && reportCardDrillable(card, def, columns, rows));
    q('.rdb-report-table').innerHTML = RS.tableHtml(columns, rows, fc, drillable);
    if (!charted) { q('.rdb-report-table').hidden = false; q('.rdb-report-tablebar').hidden = true; }
    prefixTestIds(body);
  }

  // The Simple builders stamp their own data-testids (rs-kpi-total,
  // rs-forecast-row, ...). Inside a card those would collide with the
  // (hidden but still mounted) Simple result view under Playwright's strict
  // mode, so they get an rdb- prefix: rs-kpi-total -> rdb-rs-kpi-total.
  function prefixTestIds(root) {
    Array.prototype.forEach.call(root.querySelectorAll('[data-testid^="rs-"]'), function (n) {
      n.setAttribute('data-testid', 'rdb-' + n.getAttribute('data-testid'));
    });
  }

  // Mirrors the Simple pane's renderTable probe: drillable only when the
  // leading columns resolve to a valid drill definition for the first row.
  function reportCardDrillable(card, def, columns, rows) {
    if (!window.ReportingDrill || !catalog.sources) return false;
    var src = catalog.sources.find(function (s) { return s.id === def.source; });
    if (!src) return false;
    var idx = dimValIdx(columns, card);
    var clicked = clickedFor(card, idx, idx.dims.map(function (d) { return rows[0][d]; }));
    return !!(clicked.length && ReportingDrill.buildDrillDefinition(def, src.fields || [], clicked));
  }

  // Chart click -> drill, mirroring the Simple pane's drillFromChart: the x
  // value comes from rawX; on a pivoted (multi-series) chart the clicked
  // series' raw per-dim values feed the remaining breakdowns.
  function reportCardChartDrill(card, d, index, datasetIndex) {
    var cols = (card.definition && card.definition.columns) || [];
    if (!cols.length) return;
    var clicked = [{ field: cols[0].field, grain: cols[0].grain || null,
                     value: (d.rawX || d.labels || [])[index] }];
    if (d.multiSeries && cols.length > 1) {
      var parts = (d.rawSeries || [])[datasetIndex] || [];
      for (var i = 1; i < cols.length; i++) {
        clicked.push({ field: cols[i].field, grain: cols[i].grain || null, value: parts[i - 1] });
      }
    }
    openCardDrill(card, clicked);
  }

  function renderCardContent(card, body, columns, rows) {
    if (card.type === 'kpi') return renderKpi(card, body, columns, rows);
    if (card.type === 'line') return renderLine(card, body, columns, rows);
    if (card.type === 'bar') return renderBar(card, body, columns, rows);
    if (card.type === 'donut') return renderDonut(card, body, columns, rows);
    if (card.type === 'table') return renderTable(card, body, columns, rows);
    body.textContent = '';
  }

  // ---- Per-card run: one POST /api/reporting/run per card ----------------
  var runGen = {};  // per-card fetch generation -- staleness guard (same idea
                     // as the Simple pane's seq/runSeq): a card can be
                     // re-rendered (edit toggled, cards changed) while an
                     // older fetch for the same card id is still in flight.

  // D-KPI: a KPI card's run payload must never carry a breakdown dimension.
  // renderKpi (and the trend calc below) read rows[0] as THE total -- with a
  // dimension present that's just the first bucket, not a sum (and summing
  // client-side is explicitly wrong for avg/min/max metrics). The card's own
  // definition.columns can still hold a breakdown dim (e.g. adapted from a
  // chart card), so clear it here before POSTing, same zero-column-clone
  // idea as _reporting_simple_js.html's runCurrent grand-total call.
  function cardRunDef(card, filters) {
    var def = Object.assign({}, card.definition || {});
    def.filters = filters;
    if (card.type === 'kpi') { def.columns = []; def.sort = []; }
    return def;
  }

  async function runCard(card, cardEl) {
    if (!cardEl) return;
    var gen = (runGen[card.id] = (runGen[card.id] || 0) + 1);
    var def = cardRunDef(card, effectiveFilters(card));
    // Whole-report cards mirror the Simple result run: compare: true rides on
    // a COPY of the body (cardRunDef's value also feeds Export) so the KPI
    // band gets its prior-period delta chips.
    var posted = card.type === 'report' ? Object.assign({}, def, { compare: true }) : def;
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(posted) });
    if (runGen[card.id] !== gen) return;  // superseded by a newer render/run
    var body = cardEl.querySelector('[data-testid="rdb-card-body"]');
    if (!body) return;
    if (!res.ok || !res.data || !Array.isArray(res.data.columns) || !Array.isArray(res.data.rows)) {
      destroyCardChart(card.id);
      body.className = 'rdb-card-body rdb-card-body--error';
      body.innerHTML = '<p class="rdb-card-error" data-testid="rdb-card-error">' +
        esc(I18N.couldNotLoad) + '</p>';
      return;
    }
    body.className = 'rdb-card-body';
    if (card.type === 'report') { renderReportCard(card, body, def, res.data, gen); return; }
    cardRunData[card.id] = { columns: res.data.columns, rows: res.data.rows };
    renderCardContent(card, body, res.data.columns, res.data.rows);
    if (card.type === 'kpi') maybeRenderKpiTrend(card, body, res.data.columns, res.data.rows, gen);
  }

  // ---- KPI trend (D8): a second /api/reporting/run with the one date-range
  // filter shifted back a period, rendered as "+x.y% vs previous period" --
  // computed only when the card's effective filters hold EXACTLY one
  // date-range filter and its shift is possible (shiftDateRangeFilter);
  // otherwise no trend line at all (honest numbers or nothing, per D8).
  async function maybeRenderKpiTrend(card, body, columns, rows, gen) {
    var dateFilters = effectiveFilters(card).filter(function (f) { return f.op === 'between'; });
    if (dateFilters.length !== 1) return;
    var shifted = shiftDateRangeFilter(dateFilters[0]);
    if (!shifted) return;
    var idx = dimValIdx(columns, card);
    var curVal = toNum(rows.length ? rows[0][idx.val] : null);
    if (curVal === null) return;
    var filters2 = effectiveFilters(card).map(function (f) {
      return f === dateFilters[0] ? shifted : f;
    });
    var def2 = cardRunDef(card, filters2);
    var res2 = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(def2) });
    if (runGen[card.id] !== gen) return;  // superseded meanwhile
    if (!res2.ok || !res2.data || !Array.isArray(res2.data.rows)) return;
    var prevVal = toNum(res2.data.rows.length ? res2.data.rows[0][idx.val] : null);
    if (!prevVal) return;  // null or 0 -- no honest percentage to show
    var pct = ((curVal - prevVal) / prevVal) * 100;
    var up = pct >= 0;
    var text = (up ? '+' : '') + pct.toFixed(1) + '% ' + I18N.vsPreviousPeriod;
    var trendEl = document.createElement('p');
    trendEl.className = 'rdb-kpi-trend rdb-kpi-trend--' + (up ? 'up' : 'down');
    trendEl.setAttribute('data-testid', 'rdb-kpi-trend');
    trendEl.innerHTML = '<i class="fas ' + (up ? 'fa-arrow-trend-up' : 'fa-arrow-trend-down') +
      '" aria-hidden="true"></i> ' + esc(text);
    body.appendChild(trendEl);
  }

  // ---- Card shells (loading skeleton until the run resolves) -------------
  function loadingBodyHtml(type) {
    if (type === 'kpi') return '<div class="rdb-skeleton rdb-skeleton--kpi"></div>';
    if (type === 'donut') {
      return '<div class="rdb-donut-wrap">' +
        '<div class="rdb-skeleton rdb-skeleton--donut"></div>' +
        '<div class="rdb-skeleton rdb-skeleton--legend"></div>' +
      '</div>';
    }
    if (type === 'table') {
      return '<div class="rdb-skeleton rdb-skeleton--row"></div>' +
        '<div class="rdb-skeleton rdb-skeleton--row"></div>' +
        '<div class="rdb-skeleton rdb-skeleton--row"></div>';
    }
    if (type === 'report') {
      return '<div class="rdb-skeleton rdb-skeleton--kpi"></div>' +
        '<div class="rdb-skeleton rdb-skeleton--chart"></div>';
    }
    return '<div class="rdb-skeleton rdb-skeleton--chart"></div>';  // line/bar
  }

  // Per-card head extras after the title: a violet override-summary chip
  // (with its own x) when the card overrides the global filters, otherwise
  // an "inherits global filters" note -- except on KPI cards, which hide the
  // note (prototype's showInherit: !c.filter && c.type !== 'kpi').
  function cardHeadExtrasHtml(c) {
    var overrides = c.filterOverrides || [];
    if (overrides.length) {
      var summary = overrides.map(function (f) {
        var parts = [esc(f.field), esc(OP_LABELS[f.op] || f.op)];
        if (f.value != null && f.value !== '') parts.push(esc(String(f.value)));
        return parts.join(' ');
      }).join(', ');
      return '<span class="reporting-drill-chip reporting-drill-chip--violet rdb-card-filter-chip" ' +
        'data-testid="rdb-card-filter" title="' + esc(I18N.overrideTitle) + '">' +
        '<i class="fas fa-filter" aria-hidden="true"></i>' + summary +
        '<i class="fas fa-xmark rdb-card-filter-x" data-testid="rdb-card-filter-remove" ' +
          'aria-hidden="true"></i></span>' +
        '<span class="rdb-spacer"></span>';
    }
    if (c.type !== 'kpi') {
      return '<span class="rdb-spacer"></span><span class="rdb-card-inherit">' + esc(I18N.inherits) + '</span>';
    }
    return '';
  }

  // A card with no source yet (the add-card tile's placeholder shape, D14)
  // never gets POSTed to /api/reporting/run -- it renders a "configure this
  // card" body instead until a saved report is adopted into it.
  function isEmptyCardDef(c) {
    return !c.definition || !c.definition.source;
  }

  // Hover control cluster (Task 14, edit mode only): duplicate + remove,
  // top:-11px;right:10px per D10, built fresh on every render like the rest
  // of the card shell.
  function cardControlClusterHtml() {
    return '<div class="rdb-card-controls">' +
      '<button type="button" class="rdb-card-ctrl-btn" data-testid="rdb-card-dup" ' +
        'title="' + esc(I18N.duplicate) + '" aria-label="' + esc(I18N.duplicate) + '">' +
        '<i class="fas fa-clone" aria-hidden="true"></i></button>' +
      '<button type="button" class="rdb-card-ctrl-btn rdb-card-ctrl-btn--danger" ' +
        'data-testid="rdb-card-remove" title="' + esc(I18N.remove) + '" aria-label="' + esc(I18N.remove) + '">' +
        '<i class="fas fa-xmark" aria-hidden="true"></i></button>' +
    '</div>';
  }

  // Empty-definition card body: clickable (opens the report picker) only in
  // edit mode -- a static note otherwise, since the picker is a mutation.
  function emptyCardBodyHtml() {
    if (state.editing) {
      return '<button type="button" class="rdb-card-configure" data-testid="rdb-card-configure">' +
        '<i class="fas fa-plug" aria-hidden="true"></i>' + esc(I18N.configureCard) + '</button>';
    }
    return '<p class="rdb-card-unconfigured">' + esc(I18N.configureCard) + '</p>';
  }

  function cardShellHtml(c) {
    var empty = isEmptyCardDef(c);
    var bodyClass = 'rdb-card-body' + (empty ? '' : ' rdb-card-body--loading');
    return '<div class="rdb-card" data-testid="rdb-card" data-card-id="' + esc(c.id) + '" ' +
      'data-type="' + esc(c.type) + '" draggable="' + (state.editing ? 'true' : 'false') + '" ' +
      'style="' + cardGeomStyle(cardSpan(c), cardRows(c)) + '">' +
      (state.editing ? cardControlClusterHtml() : '') +
      '<div class="rdb-card-head">' +
        (state.editing ? '<i class="fas fa-grip-vertical rdb-card-grip" aria-hidden="true"></i>' : '') +
        '<span class="rdb-card-title">' + esc(c.title || '') + '</span>' +
        cardHeadExtrasHtml(c) +
      '</div>' +
      '<div class="' + bodyClass + '" data-testid="rdb-card-body">' +
        (empty ? emptyCardBodyHtml() : loadingBodyHtml(c.type)) +
      '</div>' +
      (state.editing ? cardResizeHandleHtml() : '') +
    '</div>';
  }

  // Renders (or re-renders in place) exactly one card: builds its shell,
  // inserts/replaces it in the grid, then kicks off its run -- unless the
  // card has no source yet (D14 empty placeholder), in which case there's
  // nothing to run. Public per the plan so Tasks 13/15 can re-render a
  // single card (e.g. after a filter override edit) without rebuilding the
  // whole grid.
  function renderCard(card) {
    destroyCardChart(card.id);
    var existing = findCardEl(card.id);
    var html = cardShellHtml(card);
    if (existing) { existing.outerHTML = html; } else { el('rdbGrid').insertAdjacentHTML('beforeend', html); }
    var cardEl = findCardEl(card.id);
    if (!isEmptyCardDef(card)) runCard(card, cardEl);
    return cardEl;
  }

  // Add-card tile: last grid item in edit mode, span 6. Clicking anywhere on
  // it opens the add-card mask (openAddMask) -- the old type pills are gone,
  // the mask asks for the type along with the report, title and size.
  function addTileHtml() {
    return '<button type="button" class="rdb-add-tile" data-testid="rdb-add-tile" ' +
      'style="grid-column:span 6">' +
      '<span class="rdb-add-tile-icon"><i class="fas fa-plus" aria-hidden="true"></i></span>' +
      '<span class="rdb-add-tile-label">' + esc(I18N.addCardTile) + '</span>' +
      '<span class="rdb-add-tile-hint">' + esc(I18N.addTileHint) + '</span>' +
    '</button>';
  }

  function renderGrid() {
    var grid = el('rdbGrid');
    grid.classList.toggle('rdb-grid--editing', state.editing);
    var cards = (state.def && state.def.cards) || [];
    var keep = {};
    cards.forEach(function (c) { keep[c.id] = 1; });
    destroyChartsExcept(keep);
    grid.innerHTML = '';
    cards.forEach(renderCard);
    if (state.editing) grid.insertAdjacentHTML('beforeend', addTileHtml());
  }

  // ---- Drag-to-reorder (D10) ---------------------------------------------
  // Live reorder: the dragged card is spliced to its landing position the
  // moment the pointer enters a different card, so the grid itself is the
  // preview -- the dashed .rdb-card--dragging box sits exactly where the card
  // will end up, and drop() only has to clear the drag state. Cards are moved
  // by direct DOM insertBefore() (reorderGridDom) rather than a renderGrid()
  // re-render, so an in-flight drag never tears down/rebuilds Chart.js
  // canvases or re-fetches every card's data mid-reorder. -----------------
  function handleGridDragStart(e) {
    // A corner-resize drag starts with a pointerdown on the same (draggable)
    // card, so never let it turn into an HTML5 reorder drag as well.
    if (resizing || (e.target.closest && e.target.closest('[data-testid="rdb-card-resize"]'))) {
      e.preventDefault();
      return;
    }
    var cardEl = e.target.closest && e.target.closest('[data-card-id]');
    if (!state.editing || !cardEl) return;
    state.dragId = cardEl.getAttribute('data-card-id');
    state.overId = null;
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
    cardEl.classList.add('rdb-card--dragging');
    el('rdbGrid').classList.add('rdb-grid--dragging');
  }

  function handleGridDragOver(e) {
    if (!state.editing || !state.dragId) return;
    var cardEl = e.target.closest && e.target.closest('[data-card-id]');
    if (!cardEl) return;
    e.preventDefault();  // required for drop to fire
    var id = cardEl.getAttribute('data-card-id');
    // Hovering the dragged card itself is a no-op that deliberately does NOT
    // clear overId: right after a live move the pointer sits over the moved
    // card, and re-entering the same neighbour must not splice it back and
    // forth (that oscillation is what a drop-only reorder avoids for free).
    if (id === state.dragId || id === state.overId) return;
    state.overId = id;
    moveDragged(id);
  }

  function reorderGridDom() {
    var grid = el('rdbGrid');
    var addTile = grid.querySelector('[data-testid="rdb-add-tile"]');
    (state.def.cards || []).forEach(function (c) {
      var node = findCardEl(c.id);
      if (node) grid.insertBefore(node, addTile || null);
    });
  }

  function moveDragged(toId) {
    var cards = (state.def && state.def.cards) || [];
    var fi = cards.findIndex(function (c) { return c.id === state.dragId; });
    var ti = cards.findIndex(function (c) { return c.id === toId; });
    if (fi < 0 || ti < 0 || fi === ti) return;
    // ti is read off the PRE-removal array (the inner splice is evaluated
    // first), which is what lands a forward drag after the hovered card and a
    // backward drag before it -- the same index arithmetic the drop-time
    // reorder used.
    cards.splice(ti, 0, cards.splice(fi, 1)[0]);
    state.dirty = true;
    reorderGridDom();
  }

  function endDrag() {
    var dragEl = state.dragId && findCardEl(state.dragId);
    if (dragEl) dragEl.classList.remove('rdb-card--dragging');
    var grid = el('rdbGrid');
    if (grid) grid.classList.remove('rdb-grid--dragging');
    state.dragId = null; state.overId = null;
  }

  function handleGridDrop(e) {
    if (!state.editing || !state.dragId) return;
    e.preventDefault();  // the reorder already happened on dragover
    endDrag();
  }

  function handleGridDragEnd() { endDrag(); }

  // ---- Corner resize (span x rows, Pointer Events) ------------------------
  // No library: the drag maps pixel delta -> whole grid columns / rows,
  // writes the new geometry straight onto the element's inline style for live
  // feedback, and commits it to the card (marking the dashboard dirty) on
  // release. Nothing re-renders while dragging -- every chart is built
  // responsive:true/maintainAspectRatio:false, so Chart.js re-fits each one
  // as its container changes size.
  // ponytail: a line card's fill gradient is built once from the wrap height
  // at creation, so a resized line card keeps its original fade until the
  // card re-runs (Edit -> Done). Rebuild it per resize if that ever shows.
  var resizing = null;

  function pxVar(name, dflt) {
    var raw = getComputedStyle(el('rdbGrid')).getPropertyValue(name);
    var n = parseFloat(raw);
    return isFinite(n) && n > 0 ? n : dflt;
  }

  function cardResizeHandleHtml() {
    return '<span class="rdb-card-resize" data-testid="rdb-card-resize" ' +
      'title="' + esc(I18N.resizeCard) + '" aria-hidden="true"></span>';
  }

  function handleGridPointerDown(e) {
    var handle = e.target.closest && e.target.closest('[data-testid="rdb-card-resize"]');
    if (!state.editing || !handle) return;
    var cardEl = handle.closest('[data-card-id]');
    var card = cardEl && findCardById(cardEl.getAttribute('data-card-id'));
    if (!card) return;
    e.preventDefault();  // suppresses the native drag this pointerdown would start
    var gap = pxVar('--rdb-gap', 14);
    var gridW = el('rdbGrid').getBoundingClientRect().width;
    var span = cardSpan(card), rows = cardRows(card);
    resizing = { card: card, cardEl: cardEl, x: e.clientX, y: e.clientY,
                 span: span, rows: rows, nextSpan: span, nextRows: rows,
                 colStep: (gridW - gap * (GRID_COLS - 1)) / GRID_COLS + gap,
                 rowStep: pxVar('--rdb-row', 118) + gap };
    cardEl.classList.add('rdb-card--resizing');
    window.addEventListener('pointermove', handleResizeMove);
    window.addEventListener('pointerup', handleResizeEnd);
  }

  function handleResizeMove(e) {
    if (!resizing) return;
    var span = clampInt(resizing.span + Math.round((e.clientX - resizing.x) / resizing.colStep),
                        1, GRID_COLS, resizing.span);
    var rows = clampInt(resizing.rows + Math.round((e.clientY - resizing.y) / resizing.rowStep),
                        1, MAX_ROWS, resizing.rows);
    if (span === resizing.nextSpan && rows === resizing.nextRows) return;
    resizing.nextSpan = span;
    resizing.nextRows = rows;
    resizing.cardEl.setAttribute('style', cardGeomStyle(span, rows));
  }

  function handleResizeEnd() {
    if (!resizing) return;
    var r = resizing;
    resizing = null;
    window.removeEventListener('pointermove', handleResizeMove);
    window.removeEventListener('pointerup', handleResizeEnd);
    r.cardEl.classList.remove('rdb-card--resizing');
    if (r.nextSpan === r.span && r.nextRows === r.rows) return;
    r.card.span = r.nextSpan;
    r.card.rows = r.nextRows;
    state.dirty = true;   // Done autosaves the new geometry like any edit
  }

  // ---- Duplicate / remove (D10) ------------------------------------------
  function duplicateCard(id) {
    if (!state.editing) return;
    var cards = (state.def && state.def.cards) || [];
    var found = cards.find(function (c) { return c.id === id; });
    if (!found) return;
    var copy = Object.assign({}, found, { id: 'dup' + state.seq });
    state.seq += 1;
    setCards(function (list) {
      var idx = list.findIndex(function (c) { return c.id === id; });
      if (idx > -1) list.splice(idx + 1, 0, copy);
      return list;
    });
  }

  function removeCard(id) {
    if (!state.editing) return;
    setCards(function (list) { return list.filter(function (c) { return c.id !== id; }); });
  }

  // ---- Saved-report picker (D14 v1 card configuration) -------------------
  // Self-contained, like the filter catalog above: fetches its own copy of
  // GET /api/reporting/reports (the same endpoint/shape the Simple pane's
  // library uses), filtered to the caller's own non-SQL, non-dashboard
  // reports. Adopting one copies its definition + name into the card.
  var reportPicker = { open: false, cardId: null };

  function closeReportPicker() {
    var overlay = el('rdbReportPicker');
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    reportPicker.open = false;
    reportPicker.cardId = null;
  }

  async function adoptReport(cardId, reportId) {
    var res = await api('/api/reporting/reports/' + reportId);
    if (!res.ok || !res.data) { toast(I18N.couldNotLoad, true); return; }
    var card = ((state.def && state.def.cards) || []).find(function (c) { return c.id === cardId; });
    if (!card) return;
    card.definition = res.data.definition;
    card.title = res.data.name;
    state.dirty = true;
    closeReportPicker();
    renderCard(card);
  }

  function reportPickerBodyHtml(reports) {
    if (!reports.length) return '<p class="rdb-modal-empty">' + esc(I18N.noSavedReports) + '</p>';
    return '<ul class="rdb-report-list">' +
      reports.map(function (r) {
        return '<li><button type="button" class="rdb-report-item" data-testid="rdb-report-pick" ' +
          'data-report-id="' + esc(r.id) + '">' + esc(r.name) + '</button></li>';
      }).join('') +
    '</ul>';
  }

  async function openReportPicker(cardId) {
    if (!state.editing) return;
    closeReportPicker();
    reportPicker.open = true;
    reportPicker.cardId = cardId;
    var overlay = document.createElement('div');
    overlay.id = 'rdbReportPicker';
    overlay.className = 'rdb-modal-overlay';
    overlay.setAttribute('data-testid', 'rdb-report-picker');
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', I18N.pickReport);
    overlay.innerHTML =
      '<div class="rdb-modal">' +
        '<div class="rdb-modal-head"><span class="rdb-modal-title">' + esc(I18N.pickReport) + '</span>' +
          '<button type="button" class="rdb-modal-close" data-testid="rdb-report-picker-close" ' +
            'aria-label="' + esc(I18N.cancel) + '"><i class="fas fa-xmark" aria-hidden="true"></i></button></div>' +
        '<div class="rdb-modal-body" data-testid="rdb-report-picker-body">' +
          '<p class="rdb-modal-loading">' + esc(I18N.loading) + '</p></div>' +
      '</div>';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay || (e.target.closest && e.target.closest('[data-testid="rdb-report-picker-close"]'))) {
        closeReportPicker();
        return;
      }
      var pick = e.target.closest && e.target.closest('[data-testid="rdb-report-pick"]');
      if (pick) adoptReport(cardId, pick.getAttribute('data-report-id'));
    });

    var res = await api('/api/reporting/reports');
    if (!reportPicker.open || reportPicker.cardId !== cardId) return;  // closed/superseded meanwhile
    var reports = (res.ok && Array.isArray(res.data)) ? res.data.filter(function (r) {
      return r.owned && r.kind !== 'sql' && r.kind !== 'dashboard';
    }) : [];
    var body = overlay.querySelector('[data-testid="rdb-report-picker-body"]');
    if (body) body.innerHTML = reportPickerBodyHtml(reports);
  }

  // ---- Add-card mask (one dialog: report -> type -> size) ----------------
  // Replaces the old two-step flow, where a type pill on the add tile dropped
  // an unconfigured card that then had to be clicked to reach the saved-report
  // picker. Reads the same GET /api/reporting/reports list that picker uses.
  // Submitting with no report selected still adds the empty "configure this
  // card" placeholder, so an empty library is not a dead end -- and
  // openReportPicker() below still configures those cards.
  var MASK_TYPES = [
    { t: 'line',   icon: 'fa-chart-line',      label: 'pillChart' },
    { t: 'kpi',    icon: 'fa-hashtag',         label: 'pillKpi' },
    { t: 'table',  icon: 'fa-table',           label: 'pillTable' },
    { t: 'donut',  icon: 'fa-chart-pie',       label: 'pillDonut' },
    { t: 'report', icon: 'fa-window-maximize', label: 'pillReport' }
  ];

  var addMask = { open: false, reportId: null, type: 'line', span: 8, rows: 2,
                  sizeTouched: false, busy: false };

  function closeAddMask() {
    var overlay = el('rdbAddMask');
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    addMask.open = false;
    addMask.busy = false;
  }

  function maskTypePillsHtml() {
    return MASK_TYPES.map(function (m) {
      return '<button type="button" class="rdb-mask-pill" data-mask-type="' + m.t + '" ' +
        'data-testid="rdb-mask-type-' + m.t + '" aria-pressed="false">' +
        '<i class="fas ' + m.icon + '" aria-hidden="true"></i>' + esc(I18N[m.label]) + '</button>';
    }).join('');
  }

  function maskReportsHtml(reports) {
    if (!reports.length) return '<p class="rdb-modal-empty">' + esc(I18N.noSavedReports) + '</p>';
    return '<ul class="rdb-report-list">' + reports.map(function (r) {
      return '<li><button type="button" class="rdb-report-item" data-testid="rdb-mask-report" ' +
        'data-report-id="' + esc(r.id) + '" data-report-name="' + esc(r.name) + '" ' +
        'aria-pressed="false">' + esc(r.name) + '</button></li>';
    }).join('') + '</ul>';
  }

  // Single source of truth for the mask's visible state: pressed pills, the
  // pressed report row, both slider read-outs and the proportional preview
  // box (width as a share of the 12 columns, height in row units).
  function syncMask() {
    var overlay = el('rdbAddMask');
    if (!overlay) return;
    Array.prototype.forEach.call(overlay.querySelectorAll('[data-mask-type]'), function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-mask-type') === addMask.type));
    });
    Array.prototype.forEach.call(overlay.querySelectorAll('[data-testid="rdb-mask-report"]'), function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-report-id') === String(addMask.reportId)));
    });
    el('rdbMaskSpan').value = addMask.span;
    el('rdbMaskRows').value = addMask.rows;
    el('rdbMaskSpanOut').textContent = addMask.span + '/' + GRID_COLS;
    el('rdbMaskRowsOut').textContent = String(addMask.rows);
    var box = el('rdbMaskPreviewBox');
    box.style.width = (addMask.span / GRID_COLS * 100) + '%';
    box.style.height = (addMask.rows * 17) + 'px';
    box.textContent = addMask.span + ' × ' + addMask.rows;
    box.setAttribute('data-geom', addMask.span + 'x' + addMask.rows);
  }

  async function submitAddMask() {
    if (addMask.busy) return;
    var type = addMask.type;
    var opts = { span: addMask.span, rows: addMask.rows,
                 title: (el('rdbMaskTitle').value || '').trim() };
    if (addMask.reportId) {
      addMask.busy = true;
      var res = await api('/api/reporting/reports/' + addMask.reportId);
      addMask.busy = false;
      if (!addMask.open) return;                      // closed meanwhile
      if (!res.ok || !res.data) { toast(I18N.couldNotLoad, true); return; }
      opts.definition = res.data.definition;
      if (!opts.title) opts.title = res.data.name;
    }
    closeAddMask();
    addCard(type, opts);
  }

  function applyMaskType(type) {
    addMask.type = type;
    // The sliders track the type's default size until the user moves one --
    // picking "Whole report" after "KPI" should not leave a full report
    // squeezed into 3 columns.
    if (!addMask.sizeTouched) {
      addMask.span = DEFAULT_SPAN[type] || 6;
      addMask.rows = DEFAULT_ROWS[type] || 2;
    }
    syncMask();
  }

  async function openAddMask() {
    if (!state.editing) return;
    closeAddMask();
    addMask.open = true;
    addMask.reportId = null;
    addMask.type = 'line';
    addMask.sizeTouched = false;
    addMask.span = DEFAULT_SPAN.line;
    addMask.rows = DEFAULT_ROWS.line;
    var overlay = document.createElement('div');
    overlay.id = 'rdbAddMask';
    overlay.className = 'rdb-modal-overlay';
    overlay.setAttribute('data-testid', 'rdb-add-mask');
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', I18N.addCardTitle);
    overlay.innerHTML =
      '<div class="rdb-modal rdb-modal--mask">' +
        '<div class="rdb-modal-head">' +
          '<span class="rdb-modal-title">' + esc(I18N.addCardTitle) + '</span>' +
          '<button type="button" class="rdb-modal-close" data-testid="rdb-add-mask-close" ' +
            'aria-label="' + esc(I18N.cancel) + '"><i class="fas fa-xmark" aria-hidden="true"></i></button>' +
        '</div>' +
        '<div class="rdb-modal-body rdb-mask-body">' +
          '<p class="rdb-mask-step"><span class="rdb-mask-stepno">1</span>' +
            esc(I18N.maskStepReport) + '</p>' +
          '<div id="rdbMaskReports" class="rdb-mask-reports" data-testid="rdb-add-mask-reports">' +
            '<p class="rdb-modal-loading">' + esc(I18N.loading) + '</p></div>' +
          '<p class="rdb-mask-hint">' + esc(I18N.maskReportHint) + '</p>' +
          '<p class="rdb-mask-step"><span class="rdb-mask-stepno">2</span>' +
            esc(I18N.maskStepType) + '</p>' +
          '<div class="rdb-mask-pills">' + maskTypePillsHtml() + '</div>' +
          '<p class="rdb-mask-step"><span class="rdb-mask-stepno">3</span>' +
            esc(I18N.maskStepSize) + '</p>' +
          '<input id="rdbMaskTitle" class="reporting-input rdb-mask-input" ' +
            'data-testid="rdb-add-mask-title" aria-label="' + esc(I18N.maskTitle) + '" ' +
            'placeholder="' + esc(I18N.maskTitle) + '">' +
          '<div class="rdb-mask-sizes">' +
            '<label class="rdb-mask-label" for="rdbMaskSpan">' + esc(I18N.maskWidth) +
              '<span id="rdbMaskSpanOut" class="rdb-mask-out"></span></label>' +
            '<input type="range" id="rdbMaskSpan" data-testid="rdb-add-mask-span" ' +
              'min="1" max="' + GRID_COLS + '" step="1">' +
            '<label class="rdb-mask-label" for="rdbMaskRows">' + esc(I18N.maskHeight) +
              '<span id="rdbMaskRowsOut" class="rdb-mask-out"></span></label>' +
            '<input type="range" id="rdbMaskRows" data-testid="rdb-add-mask-rows" ' +
              'min="1" max="' + MAX_ROWS + '" step="1">' +
          '</div>' +
          '<div class="rdb-mask-preview" aria-hidden="true">' +
            '<div id="rdbMaskPreviewBox" class="rdb-mask-preview-box" ' +
              'data-testid="rdb-add-mask-preview"></div></div>' +
        '</div>' +
        '<div class="rdb-modal-foot">' +
          '<button type="button" class="nx-btn nx-btn--secondary" data-testid="rdb-add-mask-cancel">' +
            esc(I18N.cancel) + '</button>' +
          '<button type="button" class="nx-btn nx-btn--primary" data-testid="rdb-add-mask-submit">' +
            '<i class="fas fa-plus" aria-hidden="true"></i>' + esc(I18N.addCard) + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (e) {
      var hit = e.target.closest ? e.target : null;
      if (e.target === overlay ||
          (hit && (hit.closest('[data-testid="rdb-add-mask-close"]') ||
                   hit.closest('[data-testid="rdb-add-mask-cancel"]')))) {
        closeAddMask();
        return;
      }
      if (!hit) return;
      var pill = hit.closest('[data-mask-type]');
      if (pill) { applyMaskType(pill.getAttribute('data-mask-type')); return; }
      var pick = hit.closest('[data-testid="rdb-mask-report"]');
      if (pick) {
        addMask.reportId = pick.getAttribute('data-report-id');
        el('rdbMaskTitle').value = pick.getAttribute('data-report-name') || '';
        syncMask();
        return;
      }
      if (hit.closest('[data-testid="rdb-add-mask-submit"]')) submitAddMask();
    });
    overlay.addEventListener('input', function (e) {
      if (e.target.id !== 'rdbMaskSpan' && e.target.id !== 'rdbMaskRows') return;
      addMask.sizeTouched = true;
      addMask.span = clampInt(el('rdbMaskSpan').value, 1, GRID_COLS, addMask.span);
      addMask.rows = clampInt(el('rdbMaskRows').value, 1, MAX_ROWS, addMask.rows);
      syncMask();
    });
    syncMask();

    var res = await api('/api/reporting/reports');
    if (!addMask.open) return;   // closed meanwhile
    var reports = (res.ok && Array.isArray(res.data)) ? res.data.filter(function (r) {
      return r.owned && r.kind !== 'sql' && r.kind !== 'dashboard';
    }) : [];
    var host = el('rdbMaskReports');
    if (host) host.innerHTML = maskReportsHtml(reports);
    syncMask();
  }

  // ---- Export (D9 -- per-card, gated by data-can-export) ------------------
  // #rdbExport opens a menu of card titles; picking one POSTs that card's
  // EFFECTIVE (post-merge) definition to the existing /api/reporting/export
  // and downloads it -- mirrors the Simple pane's own #rsExport fetch ->
  // blob -> anchor-click listener exactly (_reporting_simple_js.html),
  // xlsx only in v1 (no format picker here, unlike Simple's).
  var exportMenu = { open: false };

  function closeExportMenu() {
    var menu = el('rdbExportMenu');
    if (menu && menu.parentNode) menu.parentNode.removeChild(menu);
    exportMenu.open = false;
  }

  function positionExportMenu(menu) {
    var btn = el('rdbExport');
    var r = btn.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.top = (r.bottom + 6) + 'px';
    menu.style.right = (window.innerWidth - r.right) + 'px';
  }

  function openExportMenu() {
    closeExportMenu();
    var cards = ((state.def && state.def.cards) || []).filter(function (c) { return !isEmptyCardDef(c); });
    var menu = document.createElement('div');
    menu.id = 'rdbExportMenu';
    menu.className = 'rdb-export-menu';
    menu.setAttribute('data-testid', 'rdb-export-menu');
    menu.setAttribute('role', 'menu');
    menu.innerHTML = cards.length
      ? cards.map(function (c) {
          return '<button type="button" class="rdb-export-item" role="menuitem" ' +
            'data-testid="rdb-export-item" data-card-id="' + esc(c.id) + '">' +
            esc(c.title || '') + '</button>';
        }).join('')
      : '<p class="rdb-modal-empty">' + esc(I18N.noExportableCards) + '</p>';
    document.body.appendChild(menu);
    positionExportMenu(menu);
    menu.addEventListener('click', function (e) {
      var item = e.target.closest && e.target.closest('[data-testid="rdb-export-item"]');
      if (item) { exportCard(item.getAttribute('data-card-id')); closeExportMenu(); }
    });
    exportMenu.open = true;
  }

  function toggleExportMenu() {
    if (exportMenu.open) closeExportMenu(); else openExportMenu();
  }

  async function exportCard(cardId) {
    var card = findCardById(cardId);
    if (!card) return;
    var def = Object.assign({}, card.definition || {});
    def.filters = effectiveFilters(card);
    def.format = 'xlsx';
    var res;
    try {
      res = await fetch(API_PREFIX + 'api/reporting/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify(def)
      });
    } catch (e) { res = { ok: false }; }
    if (!res.ok) { toast(I18N.couldNotExport, true); return; }
    var blob = await res.blob();
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (card.title || I18N.export_) + '.xlsx';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function render() {
    ensureShell();
    renderHeader();
    renderFilterBar();
    renderGrid();
  }

  window.ReportingDashboard = { openNew: openNew, open: open, close: close };
}());
