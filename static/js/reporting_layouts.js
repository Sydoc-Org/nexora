// Report-definitions editor (a "layout": kind:'layout' saved report).
// Lives in the Simple pane's #rsLayouts view like the dashboard builder.
// Model: { kind:'layout', schemaVersion:1, title, measures:[{id,op,q?}],
//          tiles:[{id,type:'kpi'|'chart'|'table', measure?, chart?, sparkline?, span, rows}] }
// Drag/resize: window.ReportingGrid. Tile rendering: window.ReportingLayoutView.
(function () {
  'use strict';
  var API_PREFIX = window.API_PREFIX;
  var api = window.NX.apiSafe, el = window.NX.el, esc = window.NX.esc, toast = window.NX.toast;
  var I18N = window.NX_I18N_REPORTING_LAYOUTS;
  var OPS = ['current', 'mean', 'minmax', 'range', 'stddev', 'percentile'];
  var CHARTS = ['bar', 'stacked_bar', 'line', 'area', 'pie', 'doughnut', 'gauge'];
  var GRID_COLS = 12, MAX_ROWS = 8;
  var DEFAULT_GEOM = { kpi: [3, 2], chart: [9, 4], table: [12, 4] };

  var state = { editing: false, dirty: false, reportId: null, def: null, seq: 100,
                previewId: null, preview: null, saveTimer: null };
  var built = false, grid = null;

  function RS() { return window.ReportingSimple; }
  function layouts() { return (RS().state.reports || []).filter(function (r) { return r.kind === 'layout' && r.owned; }); }
  function runnable() { return (RS().state.reports || []).filter(function (r) { return r.kind !== 'dashboard' && r.kind !== 'layout' && r.kind !== 'sql'; }); }

  function blankDef() {
    return { kind: 'layout', schemaVersion: 1, title: I18N.untitled,
             measures: [{ id: 'm1', op: 'current' }],
             tiles: [{ id: 't1', type: 'kpi', measure: 'm1', span: 3, rows: 2 },
                     { id: 't2', type: 'chart', chart: 'bar', span: 9, rows: 4 },
                     { id: 't3', type: 'table', span: 12, rows: 4 }] };
  }
  function nextId(prefix) { state.seq += 1; return prefix + state.seq; }
  function markDirty() {
    state.dirty = true;
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(save, 600);   // autosave like the dashboard's Done
    render();
  }

  // ---- persistence (existing /api/reporting/reports CRUD) -----------------
  async function save() {
    if (!state.dirty || !state.def) return;
    var body = JSON.stringify({ name: state.def.title, definition: state.def });
    var res = state.reportId
      ? await api('/api/reporting/reports/' + state.reportId, { method: 'PUT', body: body })
      : await api('/api/reporting/reports', { method: 'POST', body: body });
    if (!res.ok) { toast((res.data && res.data.detail) || I18N.saveFailed, 'error'); return; }
    if (!state.reportId && res.data && res.data.id) state.reportId = String(res.data.id);
    state.dirty = false;
    await RS().loadLibrary();   // refresh RS.state.reports + rail counts
    renderList();
  }
  async function remove() {
    if (!state.reportId || !window.confirm(I18N.confirmDelete)) return;
    var res = await api('/api/reporting/reports/' + state.reportId, { method: 'DELETE' });
    if (!res.ok) { toast(I18N.saveFailed, 'error'); return; }
    state.reportId = null; state.def = null; state.editing = false;
    await RS().loadLibrary();
    render();
  }

  // ---- public entry points ------------------------------------------------
  function open() {
    ensureShell();
    if (!state.def) { var first = layouts()[0]; if (first) { openLayout(first); return; } }
    render();
  }
  function openNew() {
    ensureShell();
    state.reportId = null; state.def = blankDef(); state.editing = true; state.dirty = true;
    state.seq = 100;
    render();
    save();
  }
  async function openLayout(report) {
    ensureShell();
    var res = await api('/api/reporting/reports/' + report.id);
    if (!res.ok || !res.data) { toast(I18N.saveFailed, 'error'); return; }
    state.reportId = String(report.id); state.def = res.data.definition; state.editing = false; state.dirty = false;
    state.seq = 100 + (state.def.tiles || []).length + (state.def.measures || []).length;
    render();
  }
  function close() { state.editing = false; if (el('rsLayouts')) el('rsLayouts').hidden = true; }

  // ---- shell ----------------------------------------------------------------
  function ensureShell() {
    if (built) return;
    built = true;
    el('rsLayouts').innerHTML =
      '<div class="rdb-head rl-head">' +
        '<div class="rdb-titleblock"><div class="rdb-titlerow">' +
          '<h2 class="rdb-title" id="rlTitle" data-testid="rl-title"></h2>' +
          '<input id="rlTitleInput" class="reporting-input rdb-title-input" hidden data-testid="rl-title-input">' +
        '</div><p class="rdb-meta" id="rlMeta"></p></div>' +
        '<span class="rdb-spacer"></span>' +
        '<select id="rlList" class="rc-select" data-testid="rl-list"></select>' +
        '<button type="button" id="rlNew" class="rc-btn" data-testid="rl-new">' + esc(I18N.newDefinition) + '</button>' +
        '<button type="button" id="rlDelete" class="rc-btn" data-testid="rl-delete">' + esc(I18N.delete_) + '</button>' +
        '<button type="button" id="rlEdit" class="rc-btn rc-btn--primary" data-testid="rl-edit"></button>' +
      '</div>' +
      '<div class="rl-body">' +
        '<aside class="rl-rail" id="rlRail" data-testid="rl-rail"></aside>' +
        '<div class="rl-main">' +
          '<div class="rl-previewbar"><label>' + esc(I18N.previewWith) + ' <select id="rlPreview" class="rc-select" data-testid="rl-preview"></select></label></div>' +
          '<div id="rlGrid" class="rdb-grid rl-grid" data-testid="rl-grid"></div>' +
        '</div>' +
      '</div>';
    el('rlNew').addEventListener('click', openNew);
    el('rlDelete').addEventListener('click', remove);
    el('rlEdit').addEventListener('click', function () { state.editing = !state.editing; if (!state.editing) save(); render(); });
    el('rlList').addEventListener('change', function () {
      var r = layouts().find(function (x) { return String(x.id) === el('rlList').value; });
      if (r) openLayout(r);
    });
    el('rlPreview').addEventListener('change', function () { state.previewId = el('rlPreview').value || null; runPreview(); });
    el('rlTitle').addEventListener('click', function () {
      if (!state.editing) return;
      el('rlTitle').hidden = true; el('rlTitleInput').hidden = false;
      el('rlTitleInput').value = state.def.title; el('rlTitleInput').focus();
    });
    el('rlTitleInput').addEventListener('blur', commitTitle);
    el('rlTitleInput').addEventListener('keydown', function (e) { if (e.key === 'Enter') commitTitle(); });
    el('rlRail').addEventListener('click', onRailClick);
    el('rlRail').addEventListener('change', onRailChange);
    el('rlGrid').addEventListener('click', onGridClick);
    el('rlGrid').addEventListener('change', onGridChange);
    grid = window.ReportingGrid.attach(el('rlGrid'), {
      cols: GRID_COLS, maxRows: MAX_ROWS,
      isEditing: function () { return state.editing; },
      items: function () { return (state.def && state.def.tiles) || []; },
      findItem: function (id) { return (state.def.tiles || []).find(function (t) { return t.id === id; }); },
      findEl: function (id) { return el('rlGrid').querySelector('[data-card-id="' + id + '"]'); },
      onReorder: function (from, to) { state.def.tiles = window.ReportingGrid.moveIndex(state.def.tiles, from, to); markDirtyNoRender(); },
      onResize: function (tile, span, rows) { tile.span = span; tile.rows = rows; markDirty(); }
    });
  }
  function markDirtyNoRender() { state.dirty = true; clearTimeout(state.saveTimer); state.saveTimer = setTimeout(save, 600); }
  function commitTitle() {
    var v = el('rlTitleInput').value.trim();
    el('rlTitleInput').hidden = true; el('rlTitle').hidden = false;
    if (v && v !== state.def.title) { state.def.title = v; markDirty(); }
  }

  // ---- rail (palettes) ------------------------------------------------------
  function railHtml() {
    var m = '<h4 class="rl-rail-h">' + esc(I18N.measures) + '</h4>' +
      OPS.map(function (op) {
        return '<button type="button" class="rl-pal" data-add-measure="' + op + '" data-testid="rl-add-measure-' + op + '"' +
          (state.editing ? '' : ' disabled') + '>' + esc(I18N.op[op]) + '</button>';
      }).join('') +
      '<ul class="rl-measures" data-testid="rl-measures">' +
      (state.def.measures || []).map(function (ms) {
        return '<li data-measure-id="' + esc(ms.id) + '">' + esc(I18N.op[ms.op]) +
          (ms.op === 'percentile'
            ? ' <input type="number" class="rl-q" min="0.01" max="0.99" step="0.01" value="' + (ms.q || 0.5) + '" data-q-for="' + esc(ms.id) + '"' + (state.editing ? '' : ' disabled') + '>'
            : '') +
          (state.editing ? ' <button type="button" class="rl-x" data-remove-measure="' + esc(ms.id) + '" aria-label="' + esc(I18N.removeTile) + '">&times;</button>' : '') +
          '</li>';
      }).join('') + '</ul>' +
      '<h4 class="rl-rail-h">' + esc(I18N.tiles) + '</h4>' +
      '<button type="button" class="rl-pal" data-add-tile="chart" data-testid="rl-add-chart"' + (state.editing ? '' : ' disabled') + '>' + esc(I18N.addChart) + '</button>' +
      '<button type="button" class="rl-pal" data-add-tile="table" data-testid="rl-add-table"' + (state.editing ? '' : ' disabled') + '>' + esc(I18N.addTable) + '</button>';
    return m;
  }
  function onRailClick(e) {
    var b = e.target.closest('button'); if (!b || !state.editing) return;
    if (b.dataset.addMeasure) {
      var id = nextId('m');
      var ms = { id: id, op: b.dataset.addMeasure };
      if (ms.op === 'percentile') ms.q = 0.95;
      state.def.measures.push(ms);
      state.def.tiles.push({ id: nextId('t'), type: 'kpi', measure: id, span: DEFAULT_GEOM.kpi[0], rows: DEFAULT_GEOM.kpi[1] });
      markDirty();
    } else if (b.dataset.removeMeasure) {
      state.def.measures = state.def.measures.filter(function (x) { return x.id !== b.dataset.removeMeasure; });
      state.def.tiles = state.def.tiles.filter(function (t) { return t.measure !== b.dataset.removeMeasure; });
      markDirty();
    } else if (b.dataset.addTile) {
      var t = { id: nextId('t'), type: b.dataset.addTile, span: DEFAULT_GEOM[b.dataset.addTile][0], rows: DEFAULT_GEOM[b.dataset.addTile][1] };
      if (t.type === 'chart') t.chart = 'bar';
      state.def.tiles.push(t);
      markDirty();
    }
  }
  function onRailChange(e) {
    var q = e.target.closest('[data-q-for]'); if (!q) return;
    var ms = state.def.measures.find(function (x) { return x.id === q.dataset.qFor; });
    var v = parseFloat(q.value);
    if (ms && v > 0 && v < 1) { ms.q = v; markDirty(); }
  }

  // ---- grid -------------------------------------------------------------------
  function tileShellHtml(t) {
    var head = t.type === 'kpi'
      ? esc(I18N.op[(state.def.measures.find(function (m) { return m.id === t.measure; }) || {}).op] || '')
      : t.type === 'chart' ? esc(I18N.chart[t.chart]) : esc(I18N.table);
    var tools = '';
    if (state.editing) {
      if (t.type === 'chart') {
        tools += '<select class="rc-select rl-chart-type" data-chart-for="' + esc(t.id) + '" data-testid="rl-chart-type">' +
          CHARTS.map(function (c) { return '<option value="' + c + '"' + (c === t.chart ? ' selected' : '') + '>' + esc(I18N.chart[c]) + '</option>'; }).join('') + '</select>';
      }
      if (t.type === 'kpi') {
        tools += '<label class="rl-spark"><input type="checkbox" data-spark-for="' + esc(t.id) + '"' + (t.sparkline ? ' checked' : '') + '> ' + esc(I18N.sparkline) + '</label>';
      }
      tools += '<button type="button" class="rl-x" data-remove-tile="' + esc(t.id) + '" aria-label="' + esc(I18N.removeTile) + '" data-testid="rl-remove-tile">&times;</button>';
    }
    return '<div class="rdb-card rl-tile" data-card-id="' + esc(t.id) + '" data-type="' + t.type + '" draggable="' + (state.editing ? 'true' : 'false') + '" ' +
      'style="' + window.ReportingGrid.geomStyle(t.span, t.rows) + '" data-testid="rl-tile">' +
      '<div class="rdb-card-head"><span class="rdb-card-title">' + head + '</span><span class="rdb-spacer"></span>' + tools + '</div>' +
      '<div class="rdb-card-body" data-tile-body></div>' +
      (state.editing ? '<span class="rdb-card-resize" data-testid="rdb-card-resize" title="' + esc(I18N.resizeTile) + '" aria-hidden="true"></span>' : '') +
      '</div>';
  }
  function onGridClick(e) {
    var b = e.target.closest('[data-remove-tile]'); if (!b || !state.editing) return;
    state.def.tiles = state.def.tiles.filter(function (t) { return t.id !== b.dataset.removeTile; });
    markDirty();
  }
  function onGridChange(e) {
    var sel = e.target.closest('[data-chart-for]');
    if (sel) { var t = state.def.tiles.find(function (x) { return x.id === sel.dataset.chartFor; }); if (t) { t.chart = sel.value; markDirty(); } return; }
    var sp = e.target.closest('[data-spark-for]');
    if (sp) { var k = state.def.tiles.find(function (x) { return x.id === sp.dataset.sparkFor; }); if (k) { k.sparkline = sp.checked; markDirty(); } }
  }

  // ---- preview ----------------------------------------------------------------
  async function runPreview() {
    state.preview = null;
    if (!state.previewId || !state.def) { renderTiles(); return; }
    var rep = await api('/api/reporting/reports/' + state.previewId);
    if (!rep.ok || !rep.data || !rep.data.definition) { renderTiles(); return; }
    var def = Object.assign({}, rep.data.definition, { layout: state.def });
    delete def.layoutId;
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(def) });
    if (!res.ok) { toast(I18N.previewFailed, 'error'); renderTiles(); return; }
    state.preview = { def: rep.data.definition, data: res.data };
    renderTiles();
  }
  function renderTiles() {
    var host = el('rlGrid');
    host.classList.toggle('rdb-grid--editing', state.editing);
    host.innerHTML = (state.def.tiles || []).map(tileShellHtml).join('');
    if (!window.ReportingLayoutView) return;
    window.ReportingLayoutView.render(host, {
      layout: state.def,
      def: state.preview ? state.preview.def : null,
      columns: state.preview ? state.preview.data.columns : [],
      rows: state.preview ? state.preview.data.rows : [],
      derived: state.preview ? (state.preview.data.derived || {}) : {},
      i18n: I18N
    });
  }

  // ---- render ----------------------------------------------------------------
  function renderList() {
    var list = layouts();
    el('rlList').innerHTML = list.map(function (r) {
      return '<option value="' + r.id + '"' + (String(r.id) === state.reportId ? ' selected' : '') + '>' + esc(r.name) + '</option>';
    }).join('');
    el('rlList').hidden = !list.length;
    var prev = runnable();
    el('rlPreview').innerHTML = '<option value="">' + esc(prev.length ? '—' : I18N.previewNone) + '</option>' +
      prev.map(function (r) { return '<option value="' + r.id + '"' + (String(r.id) === state.previewId ? ' selected' : '') + '>' + esc(r.name) + '</option>'; }).join('');
  }
  function render() {
    if (!built) return;
    renderList();
    var has = !!state.def;
    el('rlTitle').textContent = has ? state.def.title : I18N.title;
    el('rlMeta').textContent = has ? I18N.tilesMeta.replace('{n}', String(state.def.tiles.length)) : I18N.intro;
    el('rlEdit').textContent = state.editing ? I18N.done : I18N.edit;
    el('rlEdit').hidden = !has; el('rlDelete').hidden = !has || !state.reportId;
    el('rlRail').innerHTML = has ? railHtml() : '';
    if (has) renderTiles(); else el('rlGrid').innerHTML = '';
  }

  window.ReportingLayouts = { open: open, openNew: openNew, openLayout: openLayout, close: close };
}());
