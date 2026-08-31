/* Source visualizer -- click a card in the Console's Sources rail to see the
   database behind it: a filterable table list (columns, types, keys, row
   counts) and an ER diagram (tables as boxes, foreign keys as arrows, pan +
   zoom). Data comes from GET /api/reporting/sources/<id>/schema
   (nx_lib/reporting/db_schema.py), gated on reporting.sources.schema -- when
   the grant is missing the panel markup isn't rendered and this file isn't
   loaded, so the rail cards stay inert.

   Self-contained IIFE, exposes window.ReportingSchema.open(sourceId, dbName).
   Layout is a BFS-per-component columnar placement rather than a real graph
   layout library: no dependency, deterministic, and good enough for the FK
   graphs these databases actually have.
   ponytail: no edge-crossing minimisation -- if a schema ever looks like
   spaghetti, that's the upgrade path (or a real layout lib). */
(function () {
  'use strict';
  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var API_PREFIX = window.API_PREFIX;
  var I18N = window.NX_I18N_REPORTING_SCHEMA || {};

  function el(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var nf = new Intl.NumberFormat(document.documentElement.lang || 'en');
  function num(n) { return n == null ? '—' : nf.format(n); }

  // ---------- state ----------
  var data = null;          // last /schema payload
  var view = 'list';        // 'list' | 'diagram'
  var expanded = {};        // table key -> bool
  var filter = '';
  var laidOut = null;       // memoized diagram layout for `data`
  var pan = { x: 0, y: 0, k: 1 };

  // ---------- list view ----------

  function matches(t) {
    if (!filter) return true;
    var f = filter.toLowerCase();
    if ((t.schema + '.' + t.name).toLowerCase().indexOf(f) !== -1) return true;
    return t.columns.some(function (c) { return c.name.toLowerCase().indexOf(f) !== -1; });
  }

  function columnRowsHtml(t) {
    return '<table class="rc-schema-cols"><tbody>' + t.columns.map(function (c) {
      var badges = '';
      if (c.pk) badges += '<span class="rc-schema-key rc-schema-key--pk" title="' +
        esc(I18N.primaryKey || 'Primary key') + '"><i class="fas fa-key"></i></span>';
      if (c.fk) badges += '<button type="button" class="rc-schema-key rc-schema-key--fk" ' +
        'data-goto="' + esc(c.fk.table) + '" title="' +
        esc((I18N.references || 'References {t}').replace('{t}', c.fk.table + '.' + c.fk.column)) +
        '"><i class="fas fa-link"></i></button>';
      return '<tr><td class="rc-schema-col-name">' + esc(c.name) + badges + '</td>' +
        '<td class="rc-schema-col-type">' + esc(c.type) + '</td>' +
        '<td class="rc-schema-col-null">' + (c.nullable ? 'NULL' : 'NOT NULL') + '</td></tr>';
    }).join('') + '</tbody></table>';
  }

  function renderList() {
    var wrap = el('rcSchemaTables');
    if (!wrap) return;
    var shown = data.tables.filter(matches);
    if (!shown.length) {
      wrap.innerHTML = '<p class="rc-schema-empty">' +
        esc(I18N.noMatch || 'Nothing matches that.') + '</p>';
      return;
    }
    wrap.innerHTML = shown.map(function (t) {
      var key = t.schema + '.' + t.name;
      var open = !!expanded[key];
      return '<div class="rc-schema-item' + (open ? ' is-open' : '') +
        '" data-key="' + esc(key) + '" data-testid="rc-schema-item">' +
        '<button type="button" class="rc-schema-item-head" data-toggle="' + esc(key) + '">' +
          '<i class="fas fa-chevron-right rc-schema-caret"></i>' +
          '<span class="rc-schema-item-name">' + esc(key) + '</span>' +
          (t.kind === 'view' ? '<span class="rc-schema-tag">' +
            esc(I18N.view || 'view') + '</span>' : '') +
          '<span class="rc-schema-item-meta">' +
            (t.rows == null ? '' : '<span>' + esc(num(t.rows)) + ' ' +
              esc(I18N.rows || 'rows') + '</span>') +
            '<span>' + esc(String(t.columns.length)) + ' ' +
              esc(I18N.cols || 'cols') + '</span>' +
          '</span>' +
        '</button>' +
        (open ? columnRowsHtml(t) : '') + '</div>';
    }).join('');
  }

  function gotoTable(key) {
    expanded[key] = true;
    if (view !== 'list') showView('list');
    if (filter) { filter = ''; var f = el('rcSchemaFilter'); if (f) f.value = ''; }
    renderList();
    var node = document.querySelector('.rc-schema-item[data-key="' + key.replace(/"/g, '') + '"]');
    if (node) node.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  // ---------- diagram ----------

  var NODE_W = 210, ROW_H = 15, HEAD_H = 26, PAD_B = 8;
  var COL_GAP = 96, ROW_GAP = 26, MAX_NODES = 60, MAX_COLS_SHOWN = 8;

  // Keys and FK columns first -- they are what the arrows mean; the rest fill
  // the remaining slots so a box still reads as the table it is.
  function boxColumns(t) {
    var ranked = t.columns.slice().sort(function (a, b) {
      return (b.pk ? 2 : b.fk ? 1 : 0) - (a.pk ? 2 : a.fk ? 1 : 0);
    });
    return ranked.slice(0, MAX_COLS_SHOWN);
  }

  function layout() {
    if (laidOut) return laidOut;
    var byKey = {};
    data.tables.forEach(function (t) { byKey[t.schema + '.' + t.name] = t; });
    var rels = data.relations.filter(function (r) { return byKey[r.from] && byKey[r.to]; });

    var deg = {};
    rels.forEach(function (r) {
      deg[r.from] = (deg[r.from] || 0) + 1;
      deg[r.to] = (deg[r.to] || 0) + 1;
    });
    var keys = Object.keys(deg);
    // No foreign keys at all (common for the statistics databases): fall back
    // to the biggest tables so the diagram still shows something useful.
    if (!keys.length) keys = data.tables.slice(0, 24).map(function (t) { return t.schema + '.' + t.name; });
    keys.sort(function (a, b) { return (deg[b] || 0) - (deg[a] || 0); });
    var capped = keys.length > MAX_NODES;
    keys = keys.slice(0, MAX_NODES);
    var kept = {};
    keys.forEach(function (k) { kept[k] = true; });
    rels = rels.filter(function (r) { return kept[r.from] && kept[r.to]; });

    var adj = {};
    keys.forEach(function (k) { adj[k] = []; });
    rels.forEach(function (r) {
      if (adj[r.from].indexOf(r.to) === -1) adj[r.from].push(r.to);
      if (adj[r.to].indexOf(r.from) === -1) adj[r.to].push(r.from);
    });

    var nodes = {}, seen = {}, top = 20;
    // No foreign keys anywhere (the statistics databases): a BFS would stack
    // every table in one column, so grid them instead -- roughly square, so
    // the fit() zoom has something to work with.
    if (!rels.length) {
      var per = Math.max(1, Math.round(Math.sqrt(keys.length * 1.7)));
      var rowH = 0;
      keys.forEach(function (k, i) {
        var t = byKey[k], cols = boxColumns(t);
        var h = HEAD_H + cols.length * ROW_H + PAD_B;
        var c = i % per;
        if (c === 0 && i) { top += rowH + ROW_GAP; rowH = 0; }
        rowH = Math.max(rowH, h);
        nodes[k] = { key: k, table: t, cols: cols, x: 20 + c * (NODE_W + 40), y: top, w: NODE_W, h: h };
      });
      top += rowH;
    }
    keys.forEach(function (root) {
      if (nodes[root]) return;
      if (seen[root]) return;
      // BFS from the most-connected unplaced table: depth becomes the column,
      // which keeps parents and children next to each other without a real
      // layered-graph solver, and tolerates cycles for free.
      var levels = [], queue = [[root, 0]];
      seen[root] = true;
      while (queue.length) {
        var cur = queue.shift(), k = cur[0], lvl = cur[1];
        (levels[lvl] = levels[lvl] || []).push(k);
        adj[k].forEach(function (n) {
          if (!seen[n]) { seen[n] = true; queue.push([n, lvl + 1]); }
        });
      }
      var bottom = top;
      levels.forEach(function (col, i) {
        var y = top;
        col.forEach(function (k) {
          var t = byKey[k], cols = boxColumns(t);
          var h = HEAD_H + cols.length * ROW_H + PAD_B;
          nodes[k] = { key: k, table: t, cols: cols, x: 20 + i * (NODE_W + COL_GAP), y: y, w: NODE_W, h: h };
          y += h + ROW_GAP;
        });
        bottom = Math.max(bottom, y);
      });
      top = bottom + 40;
    });

    var w = 40, h = 40;
    Object.keys(nodes).forEach(function (k) {
      w = Math.max(w, nodes[k].x + nodes[k].w + 20);
      h = Math.max(h, nodes[k].y + nodes[k].h + 20);
    });
    laidOut = { nodes: nodes, rels: rels, width: w, height: h, capped: capped, total: keys.length };
    return laidOut;
  }

  function edgePath(a, b) {
    // Anchor on facing sides; same-column pairs leave and enter on the right.
    var ax, bx, dir;
    if (b.x >= a.x + a.w) { ax = a.x + a.w; bx = b.x; dir = 1; }
    else if (a.x >= b.x + b.w) { ax = a.x; bx = b.x + b.w; dir = -1; }
    else { ax = a.x + a.w; bx = b.x + b.w; dir = 1; }
    var ay = a.y + a.h / 2, by = b.y + b.h / 2;
    var c = Math.max(40, Math.abs(bx - ax) / 2) * dir;
    return 'M' + ax + ',' + ay + ' C' + (ax + c) + ',' + ay + ' ' + (bx - c) + ',' + by +
      ' ' + bx + ',' + by;
  }

  function renderDiagram() {
    var svg = el('rcSchemaSvg');
    if (!svg) return;
    var L = layout();
    var edges = L.rels.map(function (r) {
      var a = L.nodes[r.from], b = L.nodes[r.to];
      // A view->table edge carries no columns; dashed, and labelled as what
      // the view reads rather than as a key join.
      var isView = r.kind === 'view';
      var tip = isView
        ? r.from + '  →  ' + r.to
        : r.from + '.' + r.fromColumns.join(', ') + '  →  ' + r.to + '.' + r.toColumns.join(', ');
      return '<path class="rc-erd-edge' + (isView ? ' rc-erd-edge--view' : '') +
        '" d="' + edgePath(a, b) + '" marker-end="url(#rcErdArrow)">' +
        '<title>' + esc(tip) + '</title></path>';
    }).join('');
    var boxes = Object.keys(L.nodes).map(function (k) {
      var n = L.nodes[k], t = n.table;
      var rows = n.cols.map(function (c, i) {
        var y = n.y + HEAD_H + i * ROW_H + 11;
        // Key markers as plain circles: Font Awesome glyphs would need the
        // icon font loaded inside the SVG; a dot needs nothing.
        var dot = (c.pk || c.fk)
          ? '<circle class="rc-erd-dot' + (c.pk ? ' rc-erd-dot--pk' : '') + '" cx="' +
            (n.x + 12) + '" cy="' + (y - 4) + '" r="3"></circle>' : '';
        return dot +
          '<text class="rc-erd-col" x="' + (n.x + 22) + '" y="' + y + '">' +
          esc(c.name.length > 20 ? c.name.slice(0, 19) + '…' : c.name) + '</text>' +
          '<text class="rc-erd-type" x="' + (n.x + n.w - 10) + '" y="' + y + '" text-anchor="end">' +
          esc(c.type.length > 12 ? c.type.slice(0, 11) + '…' : c.type) + '</text>';
      }).join('');
      var extra = t.columns.length - n.cols.length;
      var title = (t.schema === 'dbo' ? t.name : k);
      return '<g class="rc-erd-node" data-key="' + esc(k) + '" data-testid="rc-erd-node">' +
        '<rect class="rc-erd-box" x="' + n.x + '" y="' + n.y + '" width="' + n.w +
          '" height="' + n.h + '" rx="8"></rect>' +
        '<rect class="rc-erd-head' + (t.kind === 'view' ? ' rc-erd-head--view' : '') +
          '" x="' + n.x + '" y="' + n.y + '" width="' + n.w + '" height="' + HEAD_H + '" rx="8"></rect>' +
        '<text class="rc-erd-title" x="' + (n.x + 10) + '" y="' + (n.y + 17) + '">' +
          esc(title.length > 22 ? title.slice(0, 21) + '…' : title) + '</text>' +
        '<text class="rc-erd-rows" x="' + (n.x + n.w - 10) + '" y="' + (n.y + 17) +
          '" text-anchor="end">' + esc(t.rows == null ? '' : num(t.rows)) + '</text>' +
        rows +
        (extra > 0 ? '<text class="rc-erd-more" x="' + (n.x + 10) + '" y="' +
          (n.y + n.h - 2) + '">+' + extra + '</text>' : '') +
        '<title>' + esc(k) + '</title></g>';
    }).join('');
    svg.innerHTML =
      '<defs><marker id="rcErdArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" ' +
      'markerHeight="7" orient="auto-start-reverse">' +
      '<path class="rc-erd-arrowhead" d="M0,0 L10,5 L0,10 z"></path></marker></defs>' +
      '<g id="rcSchemaG">' + edges + boxes + '</g>';
    var note = el('rcSchemaErdNote');
    if (note) {
      var msg = '';
      if (!data.relations.length) {
        msg = data.filter === 'used'
          ? (I18N.onlyUsed || 'These are the tables this source reads.')
          : (I18N.noRelations || 'No foreign keys defined — showing the biggest tables.');
      } else if (L.capped) {
        msg = (I18N.erdCapped || 'Showing the {n} most connected tables.').replace('{n}', L.total);
      }
      note.textContent = msg;
      note.hidden = !msg;
    }
    fit();
  }

  // ---------- pan / zoom ----------

  function applyPan() {
    var g = el('rcSchemaG');
    if (g) g.setAttribute('transform', 'translate(' + pan.x + ',' + pan.y + ') scale(' + pan.k + ')');
  }

  function fit() {
    var svg = el('rcSchemaSvg'), L = laidOut;
    if (!svg || !L) return;
    var box = svg.getBoundingClientRect();
    if (!box.width || !box.height) return;
    pan.k = Math.min(1, box.width / L.width, box.height / L.height);
    pan.x = (box.width - L.width * pan.k) / 2;
    pan.y = 12;
    applyPan();
  }

  function zoom(factor, cx, cy) {
    var k = Math.min(2.5, Math.max(0.15, pan.k * factor));
    if (cx == null) { var b = el('rcSchemaSvg').getBoundingClientRect(); cx = b.width / 2; cy = b.height / 2; }
    // Keep the point under the cursor fixed while scaling.
    pan.x = cx - (cx - pan.x) * (k / pan.k);
    pan.y = cy - (cy - pan.y) * (k / pan.k);
    pan.k = k;
    applyPan();
  }

  function wireCanvas() {
    var svg = el('rcSchemaSvg');
    if (!svg || svg.dataset.wired) return;
    svg.dataset.wired = '1';
    svg.addEventListener('wheel', function (e) {
      e.preventDefault();
      var b = svg.getBoundingClientRect();
      zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - b.left, e.clientY - b.top);
    }, { passive: false });
    var drag = null;
    svg.addEventListener('pointerdown', function (e) {
      // setPointerCapture retargets the matching pointerup at the <svg>, so the
      // box that was pressed has to be remembered here.
      drag = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y, moved: false, target: e.target };
      svg.setPointerCapture(e.pointerId);
      svg.classList.add('is-panning');
    });
    svg.addEventListener('pointermove', function (e) {
      if (!drag) return;
      pan.x = drag.px + (e.clientX - drag.x);
      pan.y = drag.py + (e.clientY - drag.y);
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 3) drag.moved = true;
      applyPan();
    });
    svg.addEventListener('pointerup', function () {
      var pressed = drag && !drag.moved ? drag.target : null;
      drag = null;
      svg.classList.remove('is-panning');
      var node = pressed && pressed.closest ? pressed.closest('.rc-erd-node') : null;
      if (node) gotoTable(node.getAttribute('data-key'));
    });
    svg.addEventListener('pointercancel', function () { drag = null; svg.classList.remove('is-panning'); });
  }

  // ---------- panel shell ----------

  function showView(next) {
    view = next;
    var list = el('rcSchemaList'), diag = el('rcSchemaDiagram');
    if (list) list.hidden = next !== 'list';
    if (diag) diag.hidden = next !== 'diagram';
    ['list', 'diagram'].forEach(function (v) {
      var b = el(v === 'list' ? 'rcSchemaTabList' : 'rcSchemaTabDiagram');
      if (b) b.classList.toggle('is-active', v === next);
    });
    if (next === 'diagram' && data) { wireCanvas(); renderDiagram(); }
  }

  function close() {
    var p = el('rcSchemaPanel'), b = el('rcSchemaBackdrop');
    if (p) p.hidden = true;
    if (b) b.hidden = true;
  }

  function setStatus(html) {
    var s = el('rcSchemaStatus');
    if (!s) return;
    s.innerHTML = html;
    s.hidden = !html;
  }

  async function open(sourceId, dbName) {
    var panel = el('rcSchemaPanel');
    if (!panel) return;
    data = null; laidOut = null; expanded = {}; filter = '';
    var f = el('rcSchemaFilter'); if (f) f.value = '';
    el('rcSchemaTitle').textContent = dbName || '';
    el('rcSchemaSub').textContent = I18N.loading || 'Loading…';
    el('rcSchemaTables').innerHTML = '';
    setStatus('<span class="rc-schema-spin"><i class="fas fa-circle-notch fa-spin"></i> ' +
      esc(I18N.loading || 'Loading…') + '</span>');
    showView('list');
    el('rcSchemaBackdrop').hidden = false;
    panel.hidden = false;

    var res, payload = null;
    try {
      res = await fetch(API_PREFIX + 'api/reporting/sources/' + encodeURIComponent(sourceId) + '/schema',
        { headers: { 'X-CSRFToken': csrf } });
      payload = await res.json();
    } catch (e) { res = null; }
    if (!res || !res.ok || !payload || !payload.tables) {
      el('rcSchemaSub').textContent = '';
      setStatus('<span class="rc-schema-error"><i class="fas fa-triangle-exclamation"></i> ' +
        esc((payload && payload.error) || I18N.failed || 'Could not read this database.') + '</span>');
      return;
    }
    setStatus('');
    data = payload;
    el('rcSchemaTitle').textContent = payload.db || dbName || '';
    var parts = [
      (I18N.tablesN || '{n} tables').replace('{n}', num(payload.tables.length)),
      (I18N.relationsN || '{n} relationships').replace('{n}', num(payload.relations.length))
    ];
    if (payload.hidden) {
      parts.push((I18N.hiddenN || '{n} hidden').replace('{n}', num(payload.hidden)));
    }
    if (payload.truncated) {
      parts.push((I18N.truncatedN || '{n} more not shown').replace('{n}', num(payload.truncated)));
    }
    el('rcSchemaSub').textContent = parts.join(' · ');
    renderList();
  }

  // ---------- wiring ----------

  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t.closest) return;
    if (t.closest('#rcSchemaClose') || t.closest('#rcSchemaBackdrop')) { close(); return; }
    var tab = t.closest('.rc-schema-tab');
    if (tab) { showView(tab.getAttribute('data-view')); return; }
    var z = t.closest('[data-zoom]');
    if (z) {
      var a = z.getAttribute('data-zoom');
      if (a === 'fit') fit(); else zoom(a === 'in' ? 1.25 : 1 / 1.25);
      return;
    }
    var goTo = t.closest('[data-goto]');
    if (goTo) { e.stopPropagation(); gotoTable(goTo.getAttribute('data-goto')); return; }
    var head = t.closest('[data-toggle]');
    if (head) {
      var key = head.getAttribute('data-toggle');
      expanded[key] = !expanded[key];
      renderList();
    }
  });

  document.addEventListener('input', function (e) {
    if (e.target.id !== 'rcSchemaFilter') return;
    filter = e.target.value.trim();
    if (data) renderList();
  });

  document.addEventListener('keydown', function (e) {
    var p = el('rcSchemaPanel');
    if (e.key === 'Escape' && p && !p.hidden) close();
  });

  window.ReportingSchema = { open: open, close: close };
}());
