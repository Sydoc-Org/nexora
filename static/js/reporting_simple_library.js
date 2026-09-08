// Reporting Simple pane -- library (Beautification Phase 2b, Task 8).
// Split out of reporting_simple.js: the report library grid (cards, preview
// SVGs/thumbnails, card menu) plus load/open/delete for a saved report or
// dashboard. Shares state via window.RS (see reporting_simple.js's own
// top-of-file comment for the RS.state/RS.el/RS.esc/RS.api/RS.I18N contract).
// This file is loaded BEFORE reporting_simple.js (see _reporting_simple_js.
// html) -- every RS.* reference below into things reporting_simple.js/
// reporting_simple_result.js/reporting_simple_wizard.js define (RS.setView,
// RS.runCurrent, RS.showResultError, RS.toggleMoreMenu, RS.fmtNumber,
// RS.loadSourcesCatalog) is only ever called from inside a function body,
// never at top-level load time, so the load order is safe: by the time any
// of these functions is actually invoked (a user action), every file has
// already run.
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

  function relTime(iso) {
    var d = new Date(iso); if (isNaN(d)) return '';
    var days = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (days <= 0) return RS.I18N.today;
    if (days === 1) return RS.I18N.yesterday;
    if (days < 7) return days + ' ' + RS.I18N.daysAgo;
    var w = Math.floor(days / 7);
    return w + ' ' + (w === 1 ? RS.I18N.weekAgo : RS.I18N.weeksAgo);
  }

  // ---------- Library ----------
  // Preview cache (D5 contract): 'nx.reporting.preview.<reportId>' =
  // {t:'line'|'bar'|'donut'|'total', v:number[]|number, ts}. Written after a
  // successful run of a SAVED report (writePreviewCache, below); read here to
  // feed the card's inline-SVG thumbnail with real numbers when available.
  function previewCacheGet(id) {
    try { return JSON.parse(localStorage.getItem('nx.reporting.preview.' + id) || 'null'); }
    catch (e) { return null; }
  }

  // Badge/thumbnail kind. The list endpoint computes this server-side
  // (previewKind, derived from DefinitionJSON) so the client just consumes it.
  function previewKindOf(r) {
    if (r.kind === 'dashboard') return 'dash';
    return r.previewKind || 'bar';
  }

  // Shared by the line preview: polyline point list, pure. Scaled between the
  // series' own min and max, not 0..max -- eight values that only differ by a
  // few percent drew as a flat hairline when they were measured off zero.
  function sparkPath(vals, w, h) {
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var span = max - min;
    return vals.map(function (v, i) {
      // A dead-flat series has no shape to show -- centre it instead of /0.
      var t = span ? (v - min) / span : 0.5;
      return (i / (vals.length - 1) * w).toFixed(1) + ',' + (h - 4 - t * (h - 10)).toFixed(1);
    }).join(' ');
  }

  // Deterministic decorative fallback (D5) for reports with no run-cache yet
  // — same id always draws the same shape instead of jittering on refresh.
  // Ids are ints in prod but strings in tests, so fold to an int first.
  function seededVals(id, n) {
    var s = String(id), h = 0, i;
    for (i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    var vals = [], x = (h * 2654435761) % 977;
    for (i = 0; i < n; i++) { x = (x * 48271) % 2147483647; vals.push(40 + (x % 60)); }
    return vals;
  }

  var PREVIEW_BADGE = {
    line: { icon: 'fa-chart-line', label: 'LINE' },
    bar: { icon: 'fa-chart-column', label: 'BAR' },
    donut: { icon: 'fa-chart-pie', label: 'DONUT' },
    total: { icon: 'fa-hashtag', label: 'TOTAL' },
    dash: { icon: 'fa-table-cells-large', label: 'DASHBOARD' }
  };

  function previewSvgLine(vals) {
    // Hover behavior (Console intent #5): the area fill and endpoint dot are
    // invisible at rest and fade in on card hover — CSS transitions on
    // .rs-spark-area / .rs-spark-dot in reporting-console.css. Nothing moves.
    var w = 200, h = 60;
    var pts = sparkPath(vals, w, h).split(' ');
    var last = pts[pts.length - 1].split(',');
    var area = pts.join(' ') + ' ' + w.toFixed(1) + ',' + h + ' 0,' + h;
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" class="rs-card-svg">' +
      '<polygon class="rs-spark-area" points="' + area + '" fill="var(--nx-accent, #4f46e5)"></polygon>' +
      '<polyline points="' + pts.join(' ') + '" fill="none" stroke="var(--nx-accent, #4f46e5)"' +
        // preserveAspectRatio="none" squashes the stroke to a hairline when the
        // 200x60 box is drawn wide and short -- non-scaling-stroke keeps it an
        // even 2px whatever the card width.
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"' +
        ' vector-effect="non-scaling-stroke"></polyline>' +
      '<circle class="rs-spark-dot" cx="' + last[0] + '" cy="' + last[1] + '" r="3" fill="var(--nx-accent, #4f46e5)"></circle>' +
      '</svg>';
  }

  function previewSvgBar(vals) {
    var w = 200, h = 60, n = vals.length, gap = 6;
    var bw = (w - gap * (n - 1)) / n;
    var max = Math.max.apply(null, vals) || 1;
    var maxIdx = 0;
    vals.forEach(function (v, i) { if (v > vals[maxIdx]) maxIdx = i; });
    var bars = vals.map(function (v, i) {
      var bh = Math.max(4, (v / max) * (h - 8));
      var x = i * (bw + gap);
      return '<rect x="' + x.toFixed(1) + '" y="' + (h - bh).toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + bh.toFixed(1) + '" rx="2.5" fill="' + (i === maxIdx ? '#7c3aed' : '#a5b4fc') + '"></rect>';
    }).join('');
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" class="rs-card-svg">' + bars + '</svg>';
  }

  function previewSvgDonut(vals) {
    var cx = 30, cy = 30, r = 22, circ = 2 * Math.PI * r;
    var total = (Number(vals[0]) || 0) + (Number(vals[1]) || 0) || 1;
    var seg1 = (Number(vals[0]) || 0) / total * circ;
    return '<svg viewBox="0 0 60 60" class="rs-card-svg rs-card-svg-donut">' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="#e0e7ff" stroke-width="8"></circle>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="#4f46e5" stroke-width="8" ' +
      'stroke-dasharray="' + seg1.toFixed(1) + ' ' + circ.toFixed(1) + '" ' +
      'transform="rotate(-90 ' + cx + ' ' + cy + ')"></circle></svg>';
  }

  // Dashboard miniature: the card's real layout, packed into 12-col rows the
  // same way the builder grid does -- plain soft tiles, no per-type glyphs
  // (tried, too busy at this size). Falls back to the old generic 2x2 when
  // the dashboard has no cards (or an old cached list payload has no summary).
  function previewSvgDash(cards) {
    if (!cards || !cards.length) {
      var s = 22, gap0 = 6, x0 = 5, y0 = 5, cells = '';
      [[0, 0], [1, 0], [0, 1], [1, 1]].forEach(function (p) {
        cells += '<rect x="' + (x0 + p[0] * (s + gap0)) + '" y="' + (y0 + p[1] * (s + gap0)) +
          '" width="' + s + '" height="' + s + '" rx="4" fill="var(--nx-accent, #4f46e5)" opacity="0.14"></rect>';
      });
      return '<svg viewBox="0 0 60 60" class="rs-card-svg rs-card-svg-dash">' + cells + '</svg>';
    }
    // Pack spans into rows of 12, like the real grid; cap at 3 rows.
    var rows = [], cur = [], used = 0;
    cards.forEach(function (c) {
      var sp = Math.max(1, Math.min(12, parseInt(c.s, 10) || 6));
      if (used + sp > 12 && cur.length) { rows.push(cur); cur = []; used = 0; }
      cur.push({ t: c.t, s: sp, x: used });
      used += sp;
    });
    if (cur.length) rows.push(cur);
    var clipped = rows.length > 3;
    rows = rows.slice(0, 3);
    var w = 200, h = 60, gap = 4;
    var rh = (h - gap * (rows.length - 1)) / rows.length;
    var body = '';
    rows.forEach(function (row, ri) {
      var y = ri * (rh + gap);
      row.forEach(function (c) {
        var x = c.x / 12 * (w + gap);
        var cw = c.s / 12 * (w + gap) - gap;
        body += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + cw.toFixed(1) +
          '" height="' + rh.toFixed(1) + '" rx="3" fill="var(--nx-accent, #4f46e5)" opacity="0.14"></rect>';
      });
    });
    if (clipped) {
      body += '<text x="' + (w - 4) + '" y="' + (h - 3) + '" text-anchor="end" font-size="9" ' +
        'fill="var(--nx-text-meta, #64748b)">…</text>';
    }
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" class="rs-card-svg rs-card-svg-dash">' + body + '</svg>';
  }

  // Preview strip: slim thumbnail (real cache values when the kind matches,
  // else the seeded decorative fallback). The type badge lives in the card's
  // top row (Console), not over the preview.
  function previewBandHtml(r) {
    var kind = previewKindOf(r);
    var cache = previewCacheGet(r.id);
    var real = cache && cache.t === kind;
    var body;
    if (kind === 'total') {
      var metricLabel = (r.definition && r.definition.metrics && r.definition.metrics[0]
        && r.definition.metrics[0].label) || '—';
      body = real
        ? '<div class="rs-card-total">' + RS.esc(RS.fmtNumber(cache.v)) + '</div>'
        : '<div class="rs-card-total rs-card-total-label">' + RS.esc(metricLabel) + '</div>';
    } else if (kind === 'dash') {
      body = previewSvgDash((r.summary || {}).cards);
    } else {
      var n = kind === 'donut' ? 2 : 8;
      var vals = real ? (Array.isArray(cache.v) ? cache.v : [cache.v]) : seededVals(r.id, n);
      body = kind === 'line' ? previewSvgLine(vals)
        : kind === 'bar' ? previewSvgBar(vals) : previewSvgDonut(vals);
    }
    return '<div class="rs-card-preview" data-kind="' + kind + '">' +
      cardFactsHtml(r) +
      '<div class="rs-card-thumb">' + body + '</div>' +
      '</div>';
  }

  // The thumbnail alone left the preview row mostly empty, and a line stretched
  // across the whole card read as a flat smear. It now shares the row with the
  // facts that actually tell reports apart: which source it reads, how it is
  // bucketed, and how narrowed it is. Server-computed (see _preview_summary);
  // labels resolve here so they stay translated, and each fact is dropped
  // rather than guessed when the definition doesn't have it.
  function cardFactsHtml(r) {
    var sm = r.summary || {};
    var facts = [];
    function fact(icon, text, title, wide) {
      facts.push('<span class="rs-card-fact' + (wide ? ' rs-card-fact--wide' : '') +
        '" title="' + RS.esc(title) + '">' +
        '<i class="fas ' + icon + '" aria-hidden="true"></i>' + RS.esc(text) + '</span>');
    }
    if (sm.source) {
      // The real database behind the source, same as the sources rail names
      // (published by _reporting_tabs_js once its health probe lands); the
      // registry label is the fallback until then.
      var src = (RS.state.sources || []).find(function (x) { return x.id === sm.source; });
      var db = (window.ReportingSourceDb || {})[sm.source] || (src && src.label) || sm.source;
      fact('fa-database', db, db, true);
    }
    var GRAINS = { day: RS.I18N.grainDay, week: RS.I18N.grainWeek, month: RS.I18N.grainMonth,
                   quarter: RS.I18N.grainQuarter, year: RS.I18N.grainYear };
    if (sm.grain && GRAINS[sm.grain]) fact('fa-calendar-day', GRAINS[sm.grain], RS.I18N.granularity);
    if (sm.metrics) fact('fa-hashtag', String(sm.metrics), RS.I18N.wizMeasure);
    if (sm.dimensions) fact('fa-layer-group', String(sm.dimensions), RS.I18N.wizBreakdown);
    if (sm.filters) fact('fa-filter', String(sm.filters), RS.I18N.aiFilters);
    // Dashboard cards: the one fact a dashboard has (its summary carries no
    // source/grain/metrics -- see _preview_summary's dashboard branch).
    if (sm.cardCount) fact('fa-table-cells-large', String(sm.cardCount), RS.I18N.cardsLabel);
    if (!facts.length) return '';
    return '<div class="rs-card-facts">' + facts.join('') + '</div>';
  }

  function initialsOf(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
  }

  // One open card menu at a time (Console intent #6).
  var openCardMenu = null;
  function closeCardMenu() {
    if (!openCardMenu) return;
    openCardMenu.menu.hidden = true;
    openCardMenu.btn.setAttribute('aria-expanded', 'false');
    openCardMenu = null;
  }
  document.addEventListener('click', function (e) {
    if (openCardMenu && !openCardMenu.wrap.contains(e.target)) closeCardMenu();
  });

  function card(r) {
    var kind = previewKindOf(r);
    var badge = PREVIEW_BADGE[kind] || PREVIEW_BADGE.bar;
    var wrap = document.createElement('div');
    wrap.className = 'rs-card-wrap';
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'rs-card';
    b.setAttribute('data-testid', 'rs-card');
    b.innerHTML =
      '<div class="rs-card-top">' +
        '<span class="rs-card-tag' + (kind === 'dash' ? ' rs-card-tag--gray' : '') + '">' +
          '<i class="fas ' + badge.icon + '" aria-hidden="true"></i>' + badge.label + '</span>' +
      '</div>' +
      '<p class="rs-card-name" title="' + RS.esc(r.name) + '">' + RS.esc(r.name) + '</p>' +
      previewBandHtml(r) +
      '<div class="rs-card-meta">' +
        '<span class="rs-card-avatar">' + RS.esc(initialsOf(r.ownerName)) + '</span>' +
        '<span class="rs-card-metatext">' + RS.esc(r.ownerName || '') + ' · ' + RS.esc(relTime(r.updatedAt)) +
          // Owner-side 'shared' tag: an explicit per-user grant leaves
          // Visibility = 'private', so the card would otherwise look
          // identical to a private one.
          (r.owned && (r.visibility === 'shared' || r.sharedCount) ? ' · ' + RS.I18N.shared : '') +
          '</span>' +
        '<i class="fas fa-play rs-card-play" aria-hidden="true"></i>' +
      '</div>';
    b.addEventListener('click', function () {
      // D17: a dashboard-kind report routes to the builder view instead of
      // the normal single-report result view.
      if (r.kind === 'dashboard') { openDashboard(r); return; }
      openReport(r);
    });
    wrap.appendChild(b);
    if (!r.owned) return wrap;
    // Owner-only "…" menu: Share / Delete (both owner-scoped server-side too).
    var kebab = document.createElement('button');
    kebab.type = 'button';
    kebab.className = 'rs-card-kebab';
    kebab.setAttribute('data-testid', 'rs-card-kebab');
    kebab.setAttribute('aria-haspopup', 'true');
    kebab.setAttribute('aria-expanded', 'false');
    kebab.setAttribute('aria-label', RS.I18N.cardMenu + ': ' + r.name);
    kebab.innerHTML = '<i class="fas fa-ellipsis" aria-hidden="true"></i>';
    var menu = document.createElement('div');
    menu.className = 'rs-card-menu';
    menu.hidden = true;
    menu.setAttribute('role', 'menu');
    var share = document.createElement('button');
    share.type = 'button';
    share.className = 'rs-card-menu-row';
    share.setAttribute('role', 'menuitem');
    share.setAttribute('data-testid', 'rs-card-share');
    share.innerHTML = '<i class="fas fa-arrow-up-from-bracket" aria-hidden="true"></i>' + RS.esc(RS.I18N.share);
    share.addEventListener('click', function (e) {
      e.stopPropagation();
      closeCardMenu();
      if (window.Reporting && window.Reporting.openShareFor) window.Reporting.openShareFor(r.id);
    });
    var del = document.createElement('button');
    del.type = 'button';
    del.className = 'rs-card-menu-row rs-card-menu-row--danger';
    del.setAttribute('role', 'menuitem');
    del.setAttribute('data-testid', 'rs-card-delete');
    del.innerHTML = '<i class="fas fa-trash-can" aria-hidden="true"></i>' +
      RS.esc(r.kind === 'dashboard' ? RS.I18N.deleteDashboard : RS.I18N.deleteReport);
    del.addEventListener('click', function (e) { e.stopPropagation(); closeCardMenu(); deleteReport(r.id, r.name); });
    menu.appendChild(share);
    var hr = document.createElement('div');
    hr.className = 'rs-card-menu-sep';
    menu.appendChild(hr);
    menu.appendChild(del);
    kebab.addEventListener('click', function (e) {
      e.stopPropagation();
      var isOpen = openCardMenu && openCardMenu.menu === menu;
      closeCardMenu();
      if (!isOpen) {
        menu.hidden = false;
        kebab.setAttribute('aria-expanded', 'true');
        openCardMenu = { wrap: wrap, menu: menu, btn: kebab };
      }
    });
    wrap.appendChild(kebab);
    wrap.appendChild(menu);
    return wrap;
  }

  // Shared by the card trash button and the result view's "More actions" row.
  // ponytail: window.confirm, same as the Advanced tab's delete — swap for a
  // styled dialog when one exists for the page.
  async function deleteReport(id, name) {
    if (!window.confirm(RS.I18N.deleteConfirm.replace('{name}', name || ''))) return;
    var res = await RS.api('/api/reporting/reports/' + id, { method: 'DELETE' });
    if (!res.ok) { RS.showResultError(RS.I18N.deleteFailed); return; }
    if (RS.state.current && String(RS.state.current.reportId) === String(id)) {
      RS.state.current = null;
      RS.toggleMoreMenu(false);
      RS.setView('library');
    }
    loadLibrary();
  }

  function renderLibrary() {
    var q = (RS.el('rsSearch').value || '').toLowerCase();
    var groups = { shared: RS.el('rsGroupShared'), mine: RS.el('rsGroupMine'), direct: RS.el('rsGroupDirect') };
    var counts = { shared: 0, mine: 0, direct: 0 };
    Object.keys(groups).forEach(function (k) {
      groups[k].innerHTML = '';
      groups[k].classList.toggle('is-cols-4', RS.state.layout === '4');
    });
    var list = RS.state.reports.slice();
    if (RS.state.sort === 'name') {
      list.sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
    }  // 'updated' keeps the server order (Owned DESC, UpdatedAt DESC)
    // --i drives the staggered entrance + sparkline draw-in (reporting-console
    // .css). Capped so a large library still finishes settling in under a
    // second instead of trickling in card by card.
    var idx = 0;
    list.forEach(function (r) {
      if (q && r.name.toLowerCase().indexOf(q) === -1) return;
      var g = r.visibility === 'shared' ? 'shared' : (r.owned ? 'mine' : 'direct');
      var c = card(r);
      c.style.setProperty('--i', String(Math.min(idx++, 11)));
      groups[g].appendChild(c);
      counts[g]++;
    });
    var all = RS.el('rsCountAll');
    if (all) {
      var total = counts.shared + counts.mine + counts.direct;
      all.textContent = total === 1 ? RS.I18N.oneReport : RS.I18N.nReports.replace('{n}', String(total));
    }
    var pills = { mine: RS.el('rsCountMine'), shared: RS.el('rsCountShared'), direct: RS.el('rsCountDirect') };
    // The empty-state name line reuses the group's own header string (already
    // translated above the grid); the hint line reuses the existing
    // emptyMine/emptyShared/emptyDirect copy — no new translated sentences.
    var groupEmpty = {
      mine: { name: RS.I18N.groupNameMine, hint: RS.I18N.emptyMine },
      shared: { name: RS.I18N.groupNameShared, hint: RS.I18N.emptyShared },
      direct: { name: RS.I18N.groupNameDirect, hint: RS.I18N.emptyDirect }
    };
    Object.keys(groups).forEach(function (k) {
      if (pills[k]) pills[k].textContent = String(counts[k]);
      if (!counts[k]) {
        groups[k].innerHTML = '<div class="rs-group-empty">' +
          '<p class="rs-group-empty-name">' + RS.esc(groupEmpty[k].name) + '</p>' +
          '<p class="rs-group-empty-hint">' + RS.esc(groupEmpty[k].hint) + '</p></div>';
      }
    });
  }

  async function loadLibrary() {
    var res = await RS.api('/api/reporting/reports');
    if (!res.ok || !Array.isArray(res.data)) return;
    // Viewers can't run sql-kind reports (/api/reporting/run rejects them);
    // they stay fully usable in Advanced.
    RS.state.reports = res.data.filter(function (r) { return r.kind !== 'sql'; });
    renderLibrary();
    // Card facts name the source, so redraw once the catalog lands -- until
    // then they'd read as raw ids.
    if (!RS.state.sources) RS.loadSourcesCatalog().then(renderLibrary);
    // …and again when the rail's health probe reports the real database names,
    // which is what the cards would rather show than the registry label.
    if (!window.ReportingSourceDb) {
      document.addEventListener('rc:sourcehealth', function once() {
        document.removeEventListener('rc:sourcehealth', once);
        if (RS.state.reports) renderLibrary();
      });
    }
    // Feeds the Console nav-rail counts (Library / Dashboards).
    document.dispatchEvent(new CustomEvent('rs:libraryloaded',
      { detail: { reports: RS.state.reports } }));
  }

  async function openReport(r) {
    var res = await RS.api('/api/reporting/reports/' + r.id);
    if (!res.ok || !res.data || !res.data.definition) {
      RS.showResultError(RS.I18N.couldNotLoad); return;
    }
    await RS.loadSourcesCatalog();
    if (!RS.state.metricsBySource) await loadMetricsCatalog();
    RS.state.current = {
      def: res.data.definition, name: res.data.name, reportId: r.id,
      owned: !!res.data.owned, canEdit: !!res.data.canEdit, fromWizard: false,
      origin: 'library'
    };
    if (RS.annotations) RS.annotations.load(r.id);
    RS.runCurrent();
  }

  // #178 A4: open a raw definition (from the AI chat) straight into the
  // Simple result view -- openReport minus the saved-report id.
  async function openDefinition(def, name) {
    await RS.loadSourcesCatalog();
    if (!RS.state.metricsBySource) await loadMetricsCatalog();
    RS.state.current = {
      def: def, name: name || def.title || '', reportId: null,
      owned: true, canEdit: true, fromWizard: false, origin: 'ai'
    };
    if (RS.annotations) RS.annotations.load(null);
    RS.runCurrent();
  }

  // D3/D17: a dashboard-kind library card opens the builder view (a fourth
  // Simple-pane view, window.ReportingDashboard) instead of the normal
  // single-report result view -- same GET-by-id endpoint as openReport, the
  // response payload IS the {id, name, definition, owned, canEdit} shape
  // window.ReportingDashboard.open() expects.
  async function openDashboard(r) {
    var res = await RS.api('/api/reporting/reports/' + r.id);
    if (!res.ok || !res.data || !res.data.definition) {
      RS.showResultError(RS.I18N.couldNotLoad); return;
    }
    RS.setView('dashboard');
    window.ReportingDashboard.open(res.data);
  }

  async function loadMetricsCatalog() {
    try {
      RS.state.metricsBySource = await ReportingCatalog.metrics();
    } catch (e) { /* non-fatal: the panes treat a missing map as "no metrics" */ }
  }

  // Bridged for reporting_simple.js (core: navTo/initOnce/setLayout/
  // exitToLibrary/rsDeleteReport/the window.ReportingSimple export) and
  // reporting_simple_wizard.js (ensureCatalogs/startWizard).
  RS.loadLibrary = loadLibrary;
  RS.renderLibrary = renderLibrary;
  RS.openReport = openReport;
  RS.openDashboard = openDashboard;
  RS.openDefinition = openDefinition;
  RS.loadMetricsCatalog = loadMetricsCatalog;
  RS.deleteReport = deleteReport;
}());
