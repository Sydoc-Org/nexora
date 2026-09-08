// Shared 12-column tile grid engine: HTML5 drag-to-reorder + Pointer-Events
// corner resize, lifted out of reporting_dashboard.js so the dashboard and the
// report-definitions editor (reporting_layouts.js) share one set of drag maths
// and one CSS contract (.rdb-grid / .rdb-card / --rdb-cardrows in reporting.css).
//
// The engine owns only transient drag state. The caller's model is reached
// through hooks: items(), findItem(id), findEl(id), onReorder(from, to),
// onResize(item, span, rows). Nothing here reads window.NX or i18n.
(function () {
  'use strict';

  function clampInt(v, lo, hi, dflt) {
    var n = parseInt(v, 10);
    if (!isFinite(n)) n = dflt;
    return Math.max(lo, Math.min(hi, n));
  }

  function geomStyle(span, rows) {
    return 'grid-column:span ' + span + ';--rdb-cardrows:' + rows;
  }

  // Splice `from` out and insert at `to` read off the PRE-removal array: a
  // forward drag lands after the hovered item, a backward drag before it.
  function moveIndex(list, from, to) {
    var out = list.slice();
    if (from < 0 || to < 0 || from === to || from >= out.length || to >= out.length) return out;
    out.splice(to, 0, out.splice(from, 1)[0]);
    return out;
  }

  function attach(gridEl, hooks) {
    var cols = hooks.cols || 12, maxRows = hooks.maxRows || 6;
    var itemAttr = hooks.itemAttr || 'data-card-id';
    var handleSel = hooks.resizeHandleSelector || '[data-testid="rdb-card-resize"]';
    var addTileSel = hooks.addTileSelector || '[data-testid="rdb-add-tile"]';
    var dragId = null, overId = null, resizing = null;

    function idOf(target) {
      var el = target && target.closest && target.closest('[' + itemAttr + ']');
      return el ? el.getAttribute(itemAttr) : null;
    }
    function indexOf(id) {
      var list = hooks.items();
      for (var i = 0; i < list.length; i++) if (list[i].id === id) return i;
      return -1;
    }
    function reorderDom() {
      var addTile = gridEl.querySelector(addTileSel);
      hooks.items().forEach(function (it) {
        var node = hooks.findEl(it.id);
        if (node) gridEl.insertBefore(node, addTile || null);
      });
    }
    function endDrag() {
      var dragEl = dragId && hooks.findEl(dragId);
      if (dragEl) dragEl.classList.remove('rdb-card--dragging');
      gridEl.classList.remove('rdb-grid--dragging');
      dragId = null; overId = null;
    }

    function onDragStart(e) {
      if (resizing || (e.target.closest && e.target.closest(handleSel))) { e.preventDefault(); return; }
      var id = idOf(e.target);
      if (!hooks.isEditing() || !id) return;
      dragId = id; overId = null;
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
      hooks.findEl(id).classList.add('rdb-card--dragging');
      gridEl.classList.add('rdb-grid--dragging');
    }
    function onDragOver(e) {
      if (!hooks.isEditing() || !dragId) return;
      var id = idOf(e.target);
      if (!id) return;
      e.preventDefault();
      if (id === dragId || id === overId) return;
      overId = id;
      var fi = indexOf(dragId), ti = indexOf(id);
      if (fi < 0 || ti < 0 || fi === ti) return;
      hooks.onReorder(fi, ti);
      reorderDom();
    }
    function onDrop(e) { if (hooks.isEditing() && dragId) { e.preventDefault(); endDrag(); } }
    function onDragEnd() { endDrag(); }

    function pxVar(name, dflt) {
      var n = parseFloat(getComputedStyle(gridEl).getPropertyValue(name));
      return isFinite(n) && n > 0 ? n : dflt;
    }
    function onPointerDown(e) {
      var handle = e.target.closest && e.target.closest(handleSel);
      if (!hooks.isEditing() || !handle) return;
      var id = idOf(handle), item = id && hooks.findItem(id), itemEl = id && hooks.findEl(id);
      if (!item || !itemEl) return;
      e.preventDefault();
      var gap = pxVar('--rdb-gap', 14), gridW = gridEl.getBoundingClientRect().width;
      var span = clampInt(item.span, 1, cols, 6), rows = clampInt(item.rows, 1, maxRows, 2);
      resizing = { item: item, el: itemEl, x: e.clientX, y: e.clientY, span: span, rows: rows,
                   nextSpan: span, nextRows: rows,
                   colStep: (gridW - gap * (cols - 1)) / cols + gap, rowStep: pxVar('--rdb-row', 118) + gap };
      itemEl.classList.add('rdb-card--resizing');
      window.addEventListener('pointermove', onResizeMove);
      window.addEventListener('pointerup', onResizeEnd);
    }
    function onResizeMove(e) {
      if (!resizing) return;
      var span = clampInt(resizing.span + Math.round((e.clientX - resizing.x) / resizing.colStep), 1, cols, resizing.span);
      var rows = clampInt(resizing.rows + Math.round((e.clientY - resizing.y) / resizing.rowStep), 1, maxRows, resizing.rows);
      if (span === resizing.nextSpan && rows === resizing.nextRows) return;
      resizing.nextSpan = span; resizing.nextRows = rows;
      resizing.el.setAttribute('style', (hooks.geomStyle || geomStyle)(span, rows));
    }
    function onResizeEnd() {
      if (!resizing) return;
      var r = resizing; resizing = null;
      window.removeEventListener('pointermove', onResizeMove);
      window.removeEventListener('pointerup', onResizeEnd);
      r.el.classList.remove('rdb-card--resizing');
      if (r.nextSpan === r.span && r.nextRows === r.rows) return;
      hooks.onResize(r.item, r.nextSpan, r.nextRows);
    }

    gridEl.addEventListener('dragstart', onDragStart);
    gridEl.addEventListener('dragover', onDragOver);
    gridEl.addEventListener('drop', onDrop);
    gridEl.addEventListener('dragend', onDragEnd);
    gridEl.addEventListener('pointerdown', onPointerDown);
    return {
      detach: function () {
        gridEl.removeEventListener('dragstart', onDragStart);
        gridEl.removeEventListener('dragover', onDragOver);
        gridEl.removeEventListener('drop', onDrop);
        gridEl.removeEventListener('dragend', onDragEnd);
        gridEl.removeEventListener('pointerdown', onPointerDown);
      },
      isResizing: function () { return !!resizing; }
    };
  }

  window.ReportingGrid = { attach: attach, clampInt: clampInt, geomStyle: geomStyle, moveIndex: moveIndex };
}());
