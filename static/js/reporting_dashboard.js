/* Dashboard builder (kind:'dashboard' saved reports).
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
  var API_PREFIX = window.API_PREFIX;

  // el/api/esc/toast: shared with nx_core.js (Task 11) -- this file's api()
  // never throws (resolves to {ok,status,data}), so it aliases NX.apiSafe,
  // not NX.api.
  var api = window.NX.apiSafe;
  var el = window.NX.el;
  var esc = window.NX.esc;
  var toast = window.NX.toast;

  var I18N = window.NX_I18N_REPORTING_DASHBOARD;

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

  var DEFAULT_SPAN = { kpi: 3, chart: 8, table: 6, report: 12 };

  // Card height is a whole number of grid rows (--rdb-row / --rdb-gap in
  // reporting.css); .rdb-card's height calc() reads the count off the
  // --rdb-cardrows custom property cardGeomStyle() writes. Saved dashboards
  // predating the `rows` field fall back to the per-type default, sized to the
  // fixed body heights those cards used to have -- so an older dashboard
  // reopens looking as it did before resizing existed.
  var DEFAULT_ROWS = { kpi: 1, chart: 3, table: 2, report: 4 };
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

  // ---- Card-array helpers ----------------------------------------------------
  function setCards(fn) {
    state.def.cards = fn((state.def.cards || []).slice());
    state.dirty = true;
    render();
  }

  // A card is a reference to a saved report plus the piece of it to show:
  // type = 'report' | 'chart' | 'table' | 'kpi' (kpiIndex picks the tile).
  // `definition` is the report's live definition, attached when the dashboard
  // opens (hydrateCards) and stripped again on save (persistedDef) -- the
  // dashboard never stores its own copy.
  function addCard(type, opts) {
    if (!state.editing) return null;
    opts = opts || {};
    var card = { id: 'n' + state.seq, type: type, reportId: String(opts.reportId),
                 span: clampInt(opts.span, 1, GRID_COLS, DEFAULT_SPAN[type] || 6),
                 rows: clampInt(opts.rows, 1, MAX_ROWS, DEFAULT_ROWS[type] || 2),
                 title: opts.title || I18N.newCard,
                 definition: opts.definition || null,
                 filterOverrides: [] };
    if (type === 'kpi') card.kpiIndex = opts.kpiIndex || 0;
    state.seq += 1;
    setCards(function (list) { return list.concat([card]); });
    return card;
  }

  // GET each distinct report once and attach its definition to the cards
  // that reference it. A deleted report leaves definition null and the card
  // says so (runCard).
  async function hydrateCards(cards) {
    var ids = [];
    (cards || []).forEach(function (c) {
      if (c.reportId && ids.indexOf(c.reportId) === -1) ids.push(c.reportId);
    });
    var defs = {};
    await Promise.all(ids.map(async function (id) {
      var res = await api('/api/reporting/reports/' + id);
      defs[id] = (res.ok && res.data && res.data.definition) || null;
    }));
    (cards || []).forEach(function (c) { if (c.reportId) c.definition = defs[c.reportId]; });
  }

  function persistedDef() {
    var d = Object.assign({}, state.def);
    d.cards = (d.cards || []).map(function (c) {
      if (!c.reportId) return c;
      var o = Object.assign({}, c);
      delete o.definition;
      return o;
    });
    return d;
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

  async function open(report) {
    state.def = report.definition;
    state.reportId = report.id;
    state.canEdit = !!report.canEdit;
    state.editing = false;
    state.dirty = false;
    state.dragId = null; state.overId = null;
    state.seq = nextSeqFor(state.def.cards);
    await hydrateCards(state.def.cards);
    if (state.def !== report.definition) return;   // another dashboard opened meanwhile
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
    var body = JSON.stringify({ name: (state.def.title || I18N.untitled), definition: persistedDef() });
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
    // overlay: pick a saved report, then take pieces of it.
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
      var addTile = e.target.closest && e.target.closest('[data-testid="rdb-add-tile"]');
      if (addTile) { openAddMask(); return; }
      // Table toggle (whole-report cards; same msgids as the Simple pane's
      // own #rsTableToggle) and table-row drill-through (forecast rows stay
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

  // Leading response columns are the definition's dimensions, the trailing
  // ones its metrics. `dims` is every dimension index (dims[0] is the axis);
  // a zero-dimension result has none to drill on.
  function dimValIdx(columns, card) {
    var nMetrics = ((card && card.definition && card.definition.metrics) || []).length || 1;
    var val = Math.max(0, columns.length - nMetrics);
    var dims = [];
    for (var i = 0; i < val; i++) dims.push(i);
    return { dim: dims.length ? 0 : -1, val: val, dims: dims };
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

  // rowIndex is the table card's row position (0-based, matching the capped
  // rows the table actually drew).
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
    var piece = card.type || 'report';
    var grandTotals = null;
    if (hasMetrics && dims && piece !== 'chart' && piece !== 'table') {
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
    if (piece !== 'kpi' && piece !== 'table' && hasMetrics && dims && rows.length && typeof Chart !== 'undefined') {
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
    applyPiece(card, body, piece);
    prefixTestIds(body);
  }

  // A card shows ONE piece of its report -- a KPI tile, the chart, the table
  // or the whole thing. Everything is drawn by the same renderer above and
  // the piece simply hides the rest, so a card can never drift from what the
  // report itself shows.
  function applyPiece(card, body, piece) {
    if (piece === 'report') return;
    var show = function (sel, on) { var n = body.querySelector(sel); if (n) n.hidden = !on; };
    body.classList.add('rdb-report--' + piece);
    show('.rdb-report-side', piece === 'kpi');
    show('.rdb-report-chartcard', piece === 'chart');
    show('.rdb-report-tablebar', false);
    show('.rdb-report-table', piece === 'table');
    if (piece === 'kpi') {
      var tiles = kpiTiles(body);
      var keep = tiles[clampInt(card.kpiIndex, 0, Math.max(0, tiles.length - 1), 0)];
      tiles.forEach(function (t) { if (t !== keep && t.parentNode) t.parentNode.removeChild(t); });
      var statsTitle = body.querySelector('.rs-kpi-stats-title');
      if (statsTitle) statsTitle.hidden = true;   // the card's own caption names the measure
    }
    if (piece === 'table') {
      var cardEl = body.closest('[data-card-id]');
      var meta = cardEl && cardEl.querySelector('.rdb-card-meta');
      var n = (cardRunData[card.id] || {}).rows;
      if (meta && n) meta.textContent = I18N.tableRowCount.replace('{n}', String(n.length));
    }
  }

  // The band's pickable tiles in DOM order: one per measure, then Buckets,
  // Avg and Peak each on their own -- the same four tiles the Results tab's
  // strip shows. kpiIndex on a card is a position in this list.
  function kpiTiles(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll('.rs-kpi-total-card, .rs-kpi-stats-card .reporting-ledger-kpi'));
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

  // Mirrors the Simple pane's table probe: drillable only when the
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

  // ---- Per-card run: one POST /api/reporting/run per card ----------------
  var runGen = {};  // per-card fetch generation -- staleness guard: a card can
                     // be re-rendered while an older fetch is still in flight.

  function cardRunDef(card, filters) {
    var def = Object.assign({}, card.definition || {});
    def.filters = filters;
    return def;
  }

  async function runCard(card, cardEl) {
    if (!cardEl) return;
    var gen = (runGen[card.id] = (runGen[card.id] || 0) + 1);
    var body = cardEl.querySelector('[data-testid="rdb-card-body"]');
    if (!body) return;
    if (!card.definition) {   // the saved report behind this card is gone
      body.className = 'rdb-card-body rdb-card-body--error';
      body.innerHTML = '<p class="rdb-card-error" data-testid="rdb-card-error">' +
        esc(I18N.reportGone) + '</p>';
      return;
    }
    var def = cardRunDef(card, effectiveFilters(card));
    // compare: true rides on a COPY of the body (cardRunDef's value also feeds
    // Export) so the KPI band gets its prior-period delta chips. Chart and
    // table pieces never draw the band, so they skip the extra work.
    var wantsBand = card.type === 'report' || card.type === 'kpi';
    var posted = wantsBand ? Object.assign({}, def, { compare: true }) : def;
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(posted) });
    if (runGen[card.id] !== gen) return;  // superseded by a newer render/run
    body = cardEl.querySelector('[data-testid="rdb-card-body"]');
    if (!body) return;
    if (!res.ok || !res.data || !Array.isArray(res.data.columns) || !Array.isArray(res.data.rows)) {
      destroyCardChart(card.id);
      body.className = 'rdb-card-body rdb-card-body--error';
      body.innerHTML = '<p class="rdb-card-error" data-testid="rdb-card-error">' +
        esc(I18N.couldNotLoad) + '</p>';
      return;
    }
    body.className = 'rdb-card-body';
    renderReportCard(card, body, def, res.data, gen);
  }

  // ---- Card shells (loading skeleton until the run resolves) -------------
  function loadingBodyHtml(type) {
    if (type === 'kpi') return '<div class="rdb-skeleton rdb-skeleton--kpi"></div>';
    if (type === 'table') {
      return '<div class="rdb-skeleton rdb-skeleton--row"></div>' +
        '<div class="rdb-skeleton rdb-skeleton--row"></div>' +
        '<div class="rdb-skeleton rdb-skeleton--row"></div>';
    }
    if (type === 'report') {
      return '<div class="rdb-skeleton rdb-skeleton--kpi"></div>' +
        '<div class="rdb-skeleton rdb-skeleton--chart"></div>';
    }
    return '<div class="rdb-skeleton rdb-skeleton--chart"></div>';
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

  // Cards predating the pick-a-piece flow carried a copied definition and a
  // type of their own (kpi/line/bar/donut/table); they have no reportId. They
  // are never run -- the body says to remove and re-add the piece.
  function isLegacyCard(c) {
    return !c.reportId;
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

  function legacyCardBodyHtml() {
    return '<p class="rdb-card-unconfigured" data-testid="rdb-card-legacy">' + esc(I18N.legacyCard) + '</p>';
  }

  function cardShellHtml(c) {
    var empty = isLegacyCard(c);
    var bodyClass = 'rdb-card-body' + (empty ? '' : ' rdb-card-body--loading');
    return '<div class="rdb-card" data-testid="rdb-card" data-card-id="' + esc(c.id) + '" ' +
      'data-type="' + esc(c.type) + '" draggable="' + (state.editing ? 'true' : 'false') + '" ' +
      'style="' + cardGeomStyle(cardSpan(c), cardRows(c)) + '">' +
      (state.editing ? cardControlClusterHtml() : '') +
      '<div class="rdb-card-head">' +
        (state.editing ? '<i class="fas fa-grip-vertical rdb-card-grip" aria-hidden="true"></i>' : '') +
        '<span class="rdb-card-title">' + esc(c.title || '') + '</span>' +
        '<span class="rdb-card-meta" data-testid="rdb-card-meta"></span>' +
        cardHeadExtrasHtml(c) +
      '</div>' +
      '<div class="' + bodyClass + '" data-testid="rdb-card-body">' +
        (empty ? legacyCardBodyHtml() : loadingBodyHtml(c.type)) +
      '</div>' +
      (state.editing ? cardResizeHandleHtml() : '') +
    '</div>';
  }

  // Renders (or re-renders in place) exactly one card: builds its shell,
  // inserts/replaces it in the grid, then kicks off its run -- unless the
  // card is a legacy one, in which case there's nothing to run.
  function renderCard(card) {
    destroyCardChart(card.id);
    var existing = findCardEl(card.id);
    var html = cardShellHtml(card);
    if (existing) { existing.outerHTML = html; } else { el('rdbGrid').insertAdjacentHTML('beforeend', html); }
    var cardEl = findCardEl(card.id);
    if (!isLegacyCard(card)) runCard(card, cardEl);
    return cardEl;
  }

  // Add-card tile: last grid item in edit mode, span 6. Clicking anywhere on
  // it opens the add-card overlay (openAddMask): pick a report, take pieces.
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
    if (addMask.open) keep[PICK_ID] = 1;   // the pick overlay's own chart survives re-renders
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

  // ---- Add card: pick a saved report, then take pieces of it -------------
  // The report renders in an overlay exactly as its whole-report card would
  // (same renderReportCard), and every piece -- each KPI tile, the chart, the
  // table, the whole report -- carries an "Add to dashboard" button. The
  // overlay stays open so several pieces can be taken in a row.
  var PICK_ID = '__pick';
  var addMask = { open: false, report: null };

  function closeAddMask() {
    var overlay = el('rdbAddMask');
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    destroyCardChart(PICK_ID);
    delete cardRunData[PICK_ID];
    addMask.open = false;
    addMask.report = null;
  }

  function maskReportsHtml(reports) {
    if (!reports.length) return '<p class="rdb-modal-empty">' + esc(I18N.noSavedReports) + '</p>';
    return '<ul class="rdb-report-list">' + reports.map(function (r) {
      return '<li><button type="button" class="rdb-report-item" data-testid="rdb-mask-report" ' +
        'data-report-id="' + esc(r.id) + '">' + esc(r.name) + '</button></li>';
    }).join('') + '</ul>';
  }

  function pickBtnHtml(piece, extraAttrs) {
    return '<button type="button" class="rdb-pick-btn" data-pick="' + piece + '"' + (extraAttrs || '') +
      ' data-testid="rdb-pick-' + piece + '"><i class="fas fa-plus" aria-hidden="true"></i>' +
      esc(I18N.pickAdd) + '</button>';
  }

  async function openAddMask() {
    if (!state.editing) return;
    closeAddMask();
    addMask.open = true;
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
          '<span class="rdb-modal-title" data-testid="rdb-add-mask-title">' + esc(I18N.addCardTitle) + '</span>' +
          '<span class="rdb-spacer"></span>' +
          '<span id="rdbMaskActions"></span>' +
          '<button type="button" class="rdb-modal-close" data-testid="rdb-add-mask-close" ' +
            'aria-label="' + esc(I18N.cancel) + '"><i class="fas fa-xmark" aria-hidden="true"></i></button>' +
        '</div>' +
        '<div class="rdb-modal-body" id="rdbMaskBody" data-testid="rdb-add-mask-body">' +
          '<p class="rdb-modal-loading">' + esc(I18N.loading) + '</p></div>' +
      '</div>';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (e) {
      var hit = e.target.closest ? e.target : null;
      if (e.target === overlay || (hit && hit.closest('[data-testid="rdb-add-mask-close"]'))) {
        closeAddMask();
        return;
      }
      if (!hit) return;
      var pick = hit.closest('[data-testid="rdb-mask-report"]');
      if (pick) { openPickReport(pick.getAttribute('data-report-id')); return; }
      var btn = hit.closest('[data-pick]');
      if (btn) pickPiece(btn);
    });

    var res = await api('/api/reporting/reports');
    if (!addMask.open) return;   // closed meanwhile
    var reports = (res.ok && Array.isArray(res.data)) ? res.data.filter(function (r) {
      return r.owned && r.kind !== 'sql' && r.kind !== 'dashboard';
    }) : [];
    el('rdbMaskBody').innerHTML =
      '<p class="rdb-mask-step">' + esc(I18N.maskStepReport) + '</p>' + maskReportsHtml(reports);
  }

  // Step 2: the picked report, rendered whole, with a pick button on every
  // piece. Global filters apply here too, so what you see is what the card
  // will show.
  async function openPickReport(reportId) {
    var res = await api('/api/reporting/reports/' + reportId);
    if (!addMask.open) return;
    if (!res.ok || !res.data) { toast(I18N.couldNotLoad, true); return; }
    addMask.report = { id: String(reportId), name: res.data.name, definition: res.data.definition };
    var overlay = el('rdbAddMask');
    overlay.querySelector('.rdb-modal').classList.add('rdb-modal--pick');
    overlay.querySelector('[data-testid="rdb-add-mask-title"]').textContent = res.data.name;
    el('rdbMaskActions').innerHTML =
      '<button type="button" class="nx-btn nx-btn--secondary" data-pick="report" data-testid="rdb-pick-report">' +
        '<i class="fas fa-plus" aria-hidden="true"></i>' + esc(I18N.pickWhole) + '</button>';
    var body = el('rdbMaskBody');
    body.className = 'rdb-modal-body rdb-card-body rdb-pick-host';
    body.innerHTML = '<p class="rdb-mask-hint">' + esc(I18N.pickHint) + '</p>' +
      '<div class="rdb-skeleton rdb-skeleton--kpi"></div><div class="rdb-skeleton rdb-skeleton--chart"></div>';
    var pseudo = { id: PICK_ID, type: 'report', title: res.data.name,
                   definition: res.data.definition, filterOverrides: [] };
    var def = cardRunDef(pseudo, effectiveFilters(pseudo));
    var gen = (runGen[PICK_ID] = (runGen[PICK_ID] || 0) + 1);
    var run = await api('/api/reporting/run', {
      method: 'POST', body: JSON.stringify(Object.assign({}, def, { compare: true }))
    });
    if (!addMask.open || runGen[PICK_ID] !== gen) return;
    if (!run.ok || !run.data || !Array.isArray(run.data.columns) || !Array.isArray(run.data.rows)) {
      body.innerHTML = '<p class="rdb-card-error">' + esc(I18N.couldNotLoad) + '</p>';
      return;
    }
    body.innerHTML = '<p class="rdb-mask-hint">' + esc(I18N.pickHint) + '</p>';
    var host = document.createElement('div');
    host.setAttribute('data-testid', 'rdb-pick-report-body');
    body.appendChild(host);
    await renderReportCard(pseudo, host, def, run.data, gen);
    if (!addMask.open || runGen[PICK_ID] !== gen) return;
    kpiTiles(host).forEach(function (tile, i) {
      tile.insertAdjacentHTML('beforeend', pickBtnHtml('kpi', ' data-kpi-index="' + i + '"'));
    });
    var chartcard = host.querySelector('.rdb-report-chartcard');
    if (chartcard && !chartcard.hidden) chartcard.insertAdjacentHTML('afterbegin', pickBtnHtml('chart'));
    var table = host.querySelector('.rdb-report-table');
    var bar = host.querySelector('.rdb-report-tablebar');
    if (table) {
      table.hidden = false;
      if (bar) { bar.hidden = false; bar.innerHTML = pickBtnHtml('table'); }
    }
  }

  function pickPiece(btn) {
    var r = addMask.report;
    if (!r) return;
    var piece = btn.getAttribute('data-pick');
    var opts = { reportId: r.id, definition: r.definition, title: r.name };
    if (piece === 'kpi') {
      opts.kpiIndex = parseInt(btn.getAttribute('data-kpi-index'), 10) || 0;
      var tile = btn.closest('.rs-kpi-total-card, .reporting-ledger-kpi');
      var cap = tile && tile.querySelector('.reporting-ledger-caption');
      if (cap && cap.textContent.trim()) opts.title += ' · ' + cap.textContent.trim();
    }
    addCard(piece, opts);
    btn.classList.add('is-added');
    btn.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i>' + esc(I18N.pickAdded);
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
    var cards = ((state.def && state.def.cards) || []).filter(function (c) { return !isLegacyCard(c) && c.definition; });
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
