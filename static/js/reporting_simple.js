// Simple pane behavior (Spec 2). Self-contained IIFE: talks only to the
// existing REST endpoints plus window.Reporting / window.ReportingTabs.
// Never touches the Advanced builder's DOM or ReportingViz (the builder's
// chart singleton); the result view owns a private Chart.js instance.
(function () {
  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var API_PREFIX = window.API_PREFIX;
  var EXPORT_ALLOWED = !!document.getElementById('rsExport');

  var I18N = window.NX_I18N_REPORTING_SIMPLE;

  // Wizard category-dimension curation (docprocessing only). Process first
  // (each Octo process = an actual client, so this is the per-client
  // breakdown), then the preferred business dimensions; noise hidden;
  // table sources are untouched.
  var DOCPROC_DIM_ORDER = ['processname', 'docsource', 'doctype', 'forwarding',
                           'ownernr', 'propertynr', 'registered', 'tenancynr'];
  var DOCPROC_DIM_HIDE = { bankpk: 1, crdno: 1, docbarcode: 1,
                           docdate: 1, workitem_id: 1 };

  var state = {
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

  // el/api/esc: shared with nx_core.js (Task 11) -- this file's api() never
  // throws (resolves to {ok,status,data}), so it aliases NX.apiSafe, not
  // NX.api.
  var el = window.NX.el;
  var api = window.NX.apiSafe;
  var esc = window.NX.esc;

  function relTime(iso) {
    var d = new Date(iso); if (isNaN(d)) return '';
    var days = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (days <= 0) return I18N.today;
    if (days === 1) return I18N.yesterday;
    if (days < 7) return days + ' ' + I18N.daysAgo;
    var w = Math.floor(days / 7);
    return w + ' ' + (w === 1 ? I18N.weekAgo : I18N.weeksAgo);
  }

  function setView(view) {
    state.view = view;
    el('rsLibrary').hidden = view !== 'library';  // #rsSearch nests under it now
    el('rsWizard').hidden = view !== 'wizard';
    el('rsResult').hidden = view !== 'result';
    el('rsDashboard').hidden = view !== 'dashboard';
    if (view !== 'result') {
      // Only the Chart.js instance is torn down; the rest of the result DOM
      // (KPI band, table, caption, chips, query card) stays rendered so the
      // Results nav item can restore the last result without re-querying
      // (Console design intent #8) — restoreResult() re-mounts the chart
      // from state.lastRun.
      destroyChart();
      hideTimingBadge();
      toggleMoreMenu(false);
    }
    // The Console nav rail follows the Simple pane's internal view.
    document.dispatchEvent(new CustomEvent('rs:viewchanged', { detail: { view: view } }));
  }

  // Console "Results" nav: bring back the last rendered result from cache.
  // Returns false when this session has no rendered result yet.
  function restoreResult() {
    var cur = state.current, lr = state.lastRun;
    if (!cur || !lr) return false;
    setView('result');
    if (lr.hasMetrics && lr.dims) {
      mountChart(cur.def, lr.columns, lr.rows,
        (cur.def.forecast && cur.def.forecast.enabled) ? (lr.forecast || null) : null);
    }
    return true;
  }

  // Entry point for the Console nav rail (js/_reporting_tabs_js.html).
  function navTo(screen) {
    if (screen === 'library') {
      if (state.view !== 'library') { setView('library'); loadLibrary(); }
      return;
    }
    if (screen === 'results') {
      if (state.view === 'result') return;
      if (restoreResult()) return;
      // Nothing rendered yet this session: open the most recent report so
      // Results never shows an empty state.
      var r = (state.reports || []).filter(function (x) { return x.kind !== 'dashboard'; })[0];
      if (r) openReport(r); else setView('library');
      return;
    }
    if (screen === 'dashboards') {
      if (state.view === 'dashboard') return;
      var d = (state.reports || []).filter(function (x) { return x.kind === 'dashboard'; })[0];
      if (d) { openDashboard(d); return; }
      setView('dashboard');
      window.ReportingDashboard.openNew();
    }
  }

  // Hide the shared masthead timing badge — but only when the Simple pane
  // actually owns the current tab; the Advanced tab's still-rendered result
  // must keep its badge across Simple-pane view changes.
  function hideTimingBadge() {
    if (!(window.ReportingTabs && window.ReportingTabs.current() === 'simple')) return;
    var timing = el('reportingTiming');
    if (timing) timing.hidden = true;
  }

  // Result-header ⋯ overflow menu (Task 7) — same open/close idiom as the
  // Advanced tab's process-scope dropdown (toggleScopeMenu/#rpScopeMenu in
  // _reporting_js.html): hidden flag on the menu, aria-expanded on the
  // trigger. Click-to-toggle, outside-click and Escape wiring live at the
  // bottom of this file, next to the other header button bindings.
  function toggleMoreMenu(open) {
    var menu = el('rsMoreMenu');
    var btn = el('rsMore');
    if (!menu || !btn) return;
    var willOpen = (open === undefined) ? menu.hidden : open;
    menu.hidden = !willOpen;
    btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  }

  function destroyChart() {
    if (state.chart) { state.chart.destroy(); state.chart = null; }
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
        ? '<div class="rs-card-total">' + esc(fmtNumber(cache.v)) + '</div>'
        : '<div class="rs-card-total rs-card-total-label">' + esc(metricLabel) + '</div>';
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
        '" title="' + esc(title) + '">' +
        '<i class="fas ' + icon + '" aria-hidden="true"></i>' + esc(text) + '</span>');
    }
    if (sm.source) {
      // The real database behind the source, same as the sources rail names
      // (published by _reporting_tabs_js once its health probe lands); the
      // registry label is the fallback until then.
      var src = (state.sources || []).find(function (x) { return x.id === sm.source; });
      var db = (window.ReportingSourceDb || {})[sm.source] || (src && src.label) || sm.source;
      fact('fa-database', db, db, true);
    }
    var GRAINS = { day: I18N.grainDay, week: I18N.grainWeek, month: I18N.grainMonth,
                   quarter: I18N.grainQuarter, year: I18N.grainYear };
    if (sm.grain && GRAINS[sm.grain]) fact('fa-calendar-day', GRAINS[sm.grain], I18N.granularity);
    if (sm.metrics) fact('fa-hashtag', String(sm.metrics), I18N.wizMeasure);
    if (sm.dimensions) fact('fa-layer-group', String(sm.dimensions), I18N.wizBreakdown);
    if (sm.filters) fact('fa-filter', String(sm.filters), I18N.aiFilters);
    // Dashboard cards: the one fact a dashboard has (its summary carries no
    // source/grain/metrics -- see _preview_summary's dashboard branch).
    if (sm.cardCount) fact('fa-table-cells-large', String(sm.cardCount), I18N.cardsLabel);
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
      '<p class="rs-card-name" title="' + esc(r.name) + '">' + esc(r.name) + '</p>' +
      previewBandHtml(r) +
      '<div class="rs-card-meta">' +
        '<span class="rs-card-avatar">' + esc(initialsOf(r.ownerName)) + '</span>' +
        '<span class="rs-card-metatext">' + esc(r.ownerName || '') + ' · ' + esc(relTime(r.updatedAt)) +
          // Owner-side 'shared' tag: an explicit per-user grant leaves
          // Visibility = 'private', so the card would otherwise look
          // identical to a private one.
          (r.owned && (r.visibility === 'shared' || r.sharedCount) ? ' · ' + I18N.shared : '') +
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
    kebab.setAttribute('aria-label', I18N.cardMenu + ': ' + r.name);
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
    share.innerHTML = '<i class="fas fa-arrow-up-from-bracket" aria-hidden="true"></i>' + esc(I18N.share);
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
      esc(r.kind === 'dashboard' ? I18N.deleteDashboard : I18N.deleteReport);
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
    if (!window.confirm(I18N.deleteConfirm.replace('{name}', name || ''))) return;
    var res = await api('/api/reporting/reports/' + id, { method: 'DELETE' });
    if (!res.ok) { showResultError(I18N.deleteFailed); return; }
    if (state.current && String(state.current.reportId) === String(id)) {
      state.current = null;
      toggleMoreMenu(false);
      setView('library');
    }
    loadLibrary();
  }

  function renderLibrary() {
    var q = (el('rsSearch').value || '').toLowerCase();
    var groups = { shared: el('rsGroupShared'), mine: el('rsGroupMine'), direct: el('rsGroupDirect') };
    var counts = { shared: 0, mine: 0, direct: 0 };
    Object.keys(groups).forEach(function (k) {
      groups[k].innerHTML = '';
      groups[k].classList.toggle('is-cols-4', state.layout === '4');
    });
    var list = state.reports.slice();
    if (state.sort === 'name') {
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
    var all = el('rsCountAll');
    if (all) {
      var total = counts.shared + counts.mine + counts.direct;
      all.textContent = total === 1 ? I18N.oneReport : I18N.nReports.replace('{n}', String(total));
    }
    var pills = { mine: el('rsCountMine'), shared: el('rsCountShared'), direct: el('rsCountDirect') };
    // The empty-state name line reuses the group's own header string (already
    // translated above the grid); the hint line reuses the existing
    // emptyMine/emptyShared/emptyDirect copy — no new translated sentences.
    var groupEmpty = {
      mine: { name: I18N.groupNameMine, hint: I18N.emptyMine },
      shared: { name: I18N.groupNameShared, hint: I18N.emptyShared },
      direct: { name: I18N.groupNameDirect, hint: I18N.emptyDirect }
    };
    Object.keys(groups).forEach(function (k) {
      if (pills[k]) pills[k].textContent = String(counts[k]);
      if (!counts[k]) {
        groups[k].innerHTML = '<div class="rs-group-empty">' +
          '<p class="rs-group-empty-name">' + esc(groupEmpty[k].name) + '</p>' +
          '<p class="rs-group-empty-hint">' + esc(groupEmpty[k].hint) + '</p></div>';
      }
    });
  }

  async function loadLibrary() {
    var res = await api('/api/reporting/reports');
    if (!res.ok || !Array.isArray(res.data)) return;
    // Viewers can't run sql-kind reports (/api/reporting/run rejects them);
    // they stay fully usable in Advanced.
    state.reports = res.data.filter(function (r) { return r.kind !== 'sql'; });
    renderLibrary();
    // Card facts name the source, so redraw once the catalog lands -- until
    // then they'd read as raw ids.
    if (!state.sources) loadSourcesCatalog().then(renderLibrary);
    // …and again when the rail's health probe reports the real database names,
    // which is what the cards would rather show than the registry label.
    if (!window.ReportingSourceDb) {
      document.addEventListener('rc:sourcehealth', function once() {
        document.removeEventListener('rc:sourcehealth', once);
        if (state.reports) renderLibrary();
      });
    }
    // Feeds the Console nav-rail counts (Library / Dashboards).
    document.dispatchEvent(new CustomEvent('rs:libraryloaded',
      { detail: { reports: state.reports } }));
  }

  async function openReport(r) {
    var res = await api('/api/reporting/reports/' + r.id);
    if (!res.ok || !res.data || !res.data.definition) {
      showResultError(I18N.couldNotLoad); return;
    }
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
    state.current = {
      def: res.data.definition, name: res.data.name, reportId: r.id,
      owned: !!res.data.owned, canEdit: !!res.data.canEdit, fromWizard: false,
      origin: 'library'
    };
    runCurrent();
  }

  // #178 A4: open a raw definition (from the AI chat) straight into the
  // Simple result view -- openReport minus the saved-report id.
  async function openDefinition(def, name) {
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
    state.current = {
      def: def, name: name || def.title || '', reportId: null,
      owned: true, canEdit: true, fromWizard: false, origin: 'ai'
    };
    runCurrent();
  }

  // D3/D17: a dashboard-kind library card opens the builder view (a fourth
  // Simple-pane view, window.ReportingDashboard) instead of the normal
  // single-report result view -- same GET-by-id endpoint as openReport, the
  // response payload IS the {id, name, definition, owned, canEdit} shape
  // window.ReportingDashboard.open() expects.
  async function openDashboard(r) {
    var res = await api('/api/reporting/reports/' + r.id);
    if (!res.ok || !res.data || !res.data.definition) {
      showResultError(I18N.couldNotLoad); return;
    }
    setView('dashboard');
    window.ReportingDashboard.open(res.data);
  }

  async function loadMetricsCatalog() {
    try {
      state.metricsBySource = await ReportingCatalog.metrics();
    } catch (e) { /* non-fatal: the panes treat a missing map as "no metrics" */ }
  }

  // ---------- Result view ----------
  // Save/Export must never act on a definition the last run couldn't produce
  // rows for — disabled while the result pane shows an error, re-enabled the
  // moment a run actually succeeds.
  function setHeaderActionsEnabled(enabled) {
    el('rsSave').disabled = !enabled;
    if (EXPORT_ALLOWED) el('rsExport').disabled = !enabled;
  }

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
    btn.textContent = I18N.openInAdvanced;
    btn.addEventListener('click', function () { el('rsOpenAdvanced').click(); });
    el('rsError').insertAdjacentElement('afterend', btn);
  }

  function showResultError(msg, opts) {
    el('rsRunLoading').hidden = true;
    if (el('rsChips')) el('rsChips').hidden = true;
    setView('result');
    hideTimingBadge();
    toggleMoreMenu(false);
    el('rsResultTitle').textContent = (opts && opts.title) || '';
    el('rsResultTitle').style.color = '';
    el('rsCrumbName').textContent = (opts && opts.title) || '';
    el('rsSavedChip').hidden = true;
    el('rsResultMeta').textContent = '';
    el('rsTableRowCount').textContent = '';
    el('rsMsg').hidden = true;
    el('rsSaveName').hidden = true;
    el('rsError').textContent = msg;
    el('rsError').hidden = false;
    renderErrorOpenAdvanced(!!(opts && opts.openAdvanced));
    setHeaderActionsEnabled(false);
    el('rsChartCard').hidden = true;
    el('rsTableCard').hidden = true;
    el('rsChartNote').hidden = true;
    el('rsChartTools').hidden = true;
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;
    el('rsSqlView').hidden = true;
    el('rsShowSql').hidden = true;
    el('rsDrillHint').hidden = true;
    // Same stale-caption guard as runCurrent()'s run-start block — a failed
    // run must not leave the PREVIOUS run's caption sentence sitting under
    // the error message.
    var rsCaptionErrBox = el('rsCaption');
    if (rsCaptionErrBox) { rsCaptionErrBox.hidden = true; rsCaptionErrBox.textContent = ''; }
    var anomErrCard = el('rsAnomCard');
    if (anomErrCard) anomErrCard.hidden = true;
  }

  // Prefers the server's own error + detail (e.g. "…invalid or outdated. —
  // unknown metric: 'x'") over the generic 400 fallback, so a stale saved
  // report's actual problem is visible instead of a canned line.
  function friendlyRunError(status, data) {
    if (status === 403) return I18N.noAccess;
    if (status === 400) {
      if (data && data.error) return data.error + (data.detail ? ' — ' + data.detail : '');
      return I18N.outdated;
    }
    return (data && data.error) || I18N.couldNotRun;
  }

  var APP_LANG = document.documentElement.lang || undefined;
  function fmtNumber(v) {
    if (v == null) return '–';
    var n = Number(v);
    // App locale (html lang attr), not browser locale — a German UI shows
    // 1'234/1.234 shapes consistently regardless of the OS language. An
    // empty lang attr degrades to the browser locale (undefined arg).
    return isNaN(n) ? String(v) : n.toLocaleString(APP_LANG);
  }

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
      badge.textContent = I18N.timingBadge.replace('{rows}', rowsTxt).replace('{ms}', msTxt);
      badge.hidden = false;
    }
    var meta = el('rsResultMeta');
    if (meta) {
      meta.textContent = I18N.resultMeta
        .replace('{rows}', rowsTxt).replace('{ms}', msTxt).replace('{when}', I18N.runJustNow);
    }
    var tableCount = el('rsTableRowCount');
    if (tableCount) tableCount.textContent = ' · ' + I18N.tableRowCount.replace('{n}', rowsTxt);
  }

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

  function deltaChipHtml(current, prior, priorStart, priorEnd) {
    if (prior == null || !isFinite(current)) return '';
    var d = computeDelta(current, prior);
    var arrow = d.dir === 'up' ? '↑' : d.dir === 'down' ? '↓' : '—';
    var title = I18N.deltaVs + ' ' + priorStart + ' – ' + priorEnd;
    return '<span class="rp-delta rp-delta--' + d.dir + '" data-testid="rp-delta"' +
      ' title="' + esc(title) + '" aria-label="' + esc(title) + '">' +
      arrow + ' ' + Math.round(d.pct) + '%</span>';
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
      '<span class="reporting-ledger-caption">' + esc(caption) + '</span>' +
      '<span class="rs-kpi-value-wrap">' +
        '<span class="reporting-ledger-kpi-value" data-count-target="' + Number(value) + '">0</span>' +
        (deltaHtml || '') +
      '</span>' +
      '<span class="reporting-ledger-kpi-sub">' + esc(sub || '') + '</span></div>';
  }

  // Peak row's sub is the winning bucket's label (empty for the
  // zero-dimension case, where there is none).
  function kpiPeakBlock(testid, caption, label, value, deltaHtml) {
    return '<div class="reporting-ledger-kpi" id="rsKpiPeak" data-testid="' + testid + '">' +
      '<span class="reporting-ledger-caption">' + esc(caption) + '</span>' +
      '<span class="rs-kpi-value-wrap">' +
        '<span class="reporting-ledger-kpi-value" data-count-target="' + Number(value) + '">0</span>' +
        (deltaHtml || '') +
      '</span>' +
      '<span class="reporting-ledger-kpi-sub">' + esc(label || '') + '</span>' +
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
  // rather than inheriting the Simple pane's state.
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
      ? zeroFillDateBuckets(def, comparison.rows, [], [comparison.priorStart, comparison.priorEnd])
      : (comparison ? comparison.rows : null);
    var priorKpi = priorRows ? computeKpiBand(dims, priorRows) : null;
    // kpi.total only feeds the delta chip now (the cards render their own
    // per-measure totals), but it still has to be the same kind of number the
    // prior period's is -- a level's latest bucket, not its sum.
    applyLatestTotal(def, kpi, rows);
    if (priorKpi) applyLatestTotal(def, priorKpi, priorRows);
    var totalDelta = '', avgDelta = '', peakDelta = '', deltaNote = '';
    if (priorKpi) {
      deltaNote = I18N.deltaVs + ' ' + comparison.priorStart + ' – ' + comparison.priorEnd;
      totalDelta = deltaChipHtml(kpi.total, priorKpi.total, comparison.priorStart, comparison.priorEnd);
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
          esc(measureLabel(columns, kpi.idx)) + '</span>' +
        kpiBlock('rs-kpi-buckets', I18N.kpiBuckets, kpi.buckets, '', I18N.kpiBucketsSub) +
        kpiBlock('rs-kpi-avg', I18N.kpiAvg, kpi.avg, avgDelta, I18N.kpiAvgSub) +
        kpiPeakBlock('rs-kpi-peak', I18N.kpiPeak, kpi.peakLabel, kpi.peak, peakDelta) +
      '</div>') : '';
    return measures.map(function (m, i) {
      var first = i === 0;
      // Console card: caption keeps the "Total · <measure>" contract; the
      // explainer (last-bucket note for levels, sum-over-period otherwise)
      // moves to the sub line so every value sits on one baseline.
      return '<div class="rs-kpi-total-card' + (first ? '' : ' rs-kpi-total-card--alt') + '"' +
        ' data-testid="' + (first ? 'rs-kpi-total' : 'rs-kpi-total-extra') + '">' +
        '<span class="reporting-ledger-caption" title="' +
          esc(I18N.kpiTotal + (m.label ? ' · ' + m.label : '')) + '">' +
          esc(I18N.kpiTotal) + (m.label ? ' · ' + esc(m.label) : '') +
        '</span>' +
        '<span class="rs-kpi-value-wrap">' +
          '<span class="reporting-ledger-kpi-value" data-count-target="' + Number(m.total) + '">0</span>' +
          (first && seriesIsHeadline ? totalDelta : '') +
        '</span>' +
        '<span class="reporting-ledger-kpi-sub">' +
          esc(m.latestKey
            ? I18N.kpiLatestSuffix + ' ' + String(m.latestKey).slice(0, 16)
            : I18N.kpiSumSub) +
          // The delta chip's "vs <prior range>" was tooltip-only, so the
          // percentage read as a bare number with nothing to compare against.
          (first && seriesIsHeadline && totalDelta ? ' · ' + esc(deltaNote) : '') +
        '</span>' +
        (first && seriesIsHeadline ? sparkHtml : '') +
        '</div>';
    }).join('') + statsHtml;
  }

  function renderKpiBand(dims, rows, comparison, def, columns) {
    var band = el('rsKpiBand');
    var html = kpiBandHtml(dims, rows, comparison, def, columns);
    if (!html) { band.hidden = true; band.innerHTML = ''; return; }
    band.innerHTML = html;
    band.hidden = false;
    Array.prototype.forEach.call(band.querySelectorAll('[data-count-target]'), function (span) {
      animateValue(span, Number(span.getAttribute('data-count-target')), fmtNumber);
    });
  }

  // Console "Anomalies" card: cheap client-side outlier notes over the rows
  // already rendered — the latest complete bucket's swing per series, plus
  // each series' peak bucket. Only for a single-dimension result (one clean
  // axis). ponytail: ±15% swing heuristic; a real detector belongs
  // server-side if this ever needs to be smarter.
  function renderAnomalies(def, columns, rows) {
    var card = el('rsAnomCard');
    if (!card) return;
    card.hidden = true;
    el('rsAnomRows').innerHTML = '';
    var dims = (def.columns || []).length;
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;
    if (!hasMetrics || dims !== 1 || !rows || rows.length < 3) return;
    var grain = def.columns[0].grain || null;
    var body = rows.slice();
    // Ignore a trailing partial bucket — comparing it against a full one
    // would fabricate a drop (same reasoning as the chart's faded bucket).
    if (grain && body.length &&
        String(body[body.length - 1][0] || '').slice(0, 10) >= currentBucketStart(grain)) {
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
            text: (pct < 0 ? I18N.anomDown : I18N.anomUp)
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
          text: I18N.anomPeak.replace('{label}', label)
            .replace('{bucket}', String(body[maxI][0]).slice(0, 10)),
          value: fmtNumber(vals[maxI])
        });
      }
    }
    out = out.slice(0, 3);
    if (!out.length) return;
    el('rsAnomRows').innerHTML = out.map(function (a) {
      return '<div class="rs-anom-row"><span class="rs-anom-dot ' + a.cls + '"></span>' +
        '<span class="rs-anom-text">' + esc(a.text) + '</span>' +
        '<span class="rs-anom-val">' + esc(a.value) + '</span></div>';
    }).join('');
    card.hidden = false;
  }

  function metricLabelsFor(def) {
    var list = (state.metricsBySource || {})[def.source] || [];
    return (def.metrics || []).map(function (m) {
      var hit = list.find(function (x) { return x.code === m.metric; });
      return hit ? hit.label : m.metric;
    });
  }

  // Authoritative per-metric grand totals (one cell per def.metrics entry),
  // from the zero-column clone run — or from the single row of a zero-dim run,
  // which IS that total. The band renders them; summing the grouped rows in
  // the browser only happens to be right for additive metrics, and would
  // quietly double-count a count_distinct or average an average.
  function setGrandTotals(rowVals) {
    state.grandTotals = Array.isArray(rowVals) ? rowVals : null;
  }

  // The metric's aggregation (sum/avg/count/count_distinct/…), used to decide
  // whether a drilled-into set of rows is a strict "contributing to this
  // number" count (distinct aggregations) vs. an exact breakdown.
  function metricAggFor(def) {
    var m = (def.metrics && def.metrics[0]) || null;
    if (!m) return '';
    var list = (state.metricsBySource || {})[def.source] || [];
    var hit = list.find(function (x) { return x.code === m.metric; });
    return hit ? hit.aggregation : '';
  }

  function metricTotalModeFor(def) {
    var m = (def.metrics && def.metrics[0]) || null;
    if (!m) return 'sum';
    var list = (state.metricsBySource || {})[def.source] || [];
    var hit = list.find(function (x) { return x.code === m.metric; });
    return (hit && hit.totalMode) || 'sum';
  }

  // One totalMode per def.metrics entry ('sum' | 'latest').
  function metricTotalModes(def) {
    var list = (state.metricsBySource || {})[def.source] || [];
    return (def.metrics || []).map(function (m) {
      var hit = list.find(function (x) { return x.code === m.metric; });
      return (hit && hit.totalMode) || 'sum';
    });
  }

  // #178 C10: for a latest-mode metric the "total" is the newest date
  // bucket's sum, not the sum over all buckets -- a level (the backlog) added
  // up across twelve months is a number nobody can spend. Returns
  // {total, key} for column `idx`, or null when there is no date dimension.
  function latestBucketTotal(def, rows, idx) {
    var cols = def.columns || [];
    var dateIdx = -1;
    for (var i = 0; i < cols.length; i++) {
      var m = fieldMetaFor(def, cols[i].field);
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
  // Prefers the authoritative grand total (state.grandTotals); otherwise falls
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
    var grand = grandTotals === undefined ? state.grandTotals : grandTotals;
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
    return ((state.current && state.current.def && state.current.def.columns) || [])
      .map(function (c, i) {
        return { field: c.field, grain: c.grain || null, value: rowValues[i] };
      });
  }

  function openDrill(clicked) {
    var cur = state.current;
    if (!cur || !cur.def) return;
    var src = (state.sources || []).find(function (s) { return s.id === cur.def.source; });
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

  // index/datasetIndex are Chart.js element coordinates from onClick. Drill
  // only engages for aggregate results (a definition with at least one metric
  // and at least one dimension) — raw-row grids never reach mountChart/here.
  function drillFromChart(index, datasetIndex) {
    var cur = state.current;
    if (!cur || !cur.def) return;
    if (!(cur.def.metrics || []).length) return;
    var dims = cur.def.columns || [];
    if (!dims.length) return;
    var cd = state.chartData || {};
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

  // Pure HTML builder for the result grid (data bars + forecast rows).
  // `drillable` only adds the clickable class -- the caller binds the row
  // handlers. Shared with the dashboard's whole-report card.
  function tableHtml(columns, rows, forecast, drillable) {
    var html = '<table class="reporting-table' + (drillable ? ' reporting-drill-clickable' : '') +
      '"><thead><tr>';
    columns.forEach(function (c) { html += '<th>' + esc(c.header || c.field) + '</th>'; });
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
          html += '<td class="reporting-ledger-num rp-cell-num" style="--bar:' + pct + '%">' + esc(v) + '</td>';
        } else {
          html += '<td>' + esc(v == null ? '' : v) + '</td>';
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
            html += '<td>' + esc(String(b).slice(0, 10)) +
              ' <span class="rp-forecast-badge">' + esc(I18N.forecastLabel) + '</span></td>';
          } else if (ci >= mStart) {
            var sv = fcRows.series[ci - mStart];
            html += '<td class="reporting-ledger-num">' +
              esc(fmtChartTooltip(sv.values[bi])) + '</td>';
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

  function renderTable(columns, rows, forecast) {
    var cur = state.current;
    var def = (cur && cur.def) || {};
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;
    var dims = (def.columns || []).length;
    var src = (state.sources || []).find(function (s) { return s.id === def.source; });
    // Drillable only for aggregate results (metric + dimension) whose leading
    // columns resolve to a valid drill definition — probed once with the
    // first row rather than assumed, so e.g. non-filterable dimensions don't
    // get a false affordance.
    var drillable = !!(hasMetrics && dims && src && rows.length &&
      ReportingDrill.buildDrillDefinition(def, src.fields || [], clickedFor(rows[0])));
    el('rsTableWrap').innerHTML = tableHtml(columns, rows, forecast, drillable);
    if (drillable) {
      Array.prototype.forEach.call(
        el('rsTableWrap').querySelectorAll('tbody tr:not(.is-forecast)'), function (tr, i) {
          var rowValues = rows[i];
          tr.tabIndex = 0;
          tr.addEventListener('click', function () { openDrill(clickedFor(rowValues)); });
          tr.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') openDrill(clickedFor(rowValues));
          });
        });
    }
    el('rsDrillHint').hidden = !drillable;
  }

  // Simple owns its OWN Chart.js instance on a private canvas. It must never
  // call ReportingViz.mountChart: that module is a singleton wired to the
  // Advanced pane's hardcoded element ids, so concurrent mounts are unsafe.
  function chartCardNote(msg) {
    el('rsChartCanvas').hidden = true;
    el('rsChartTools').hidden = true;
    el('rsChartNote').textContent = msg;
    el('rsChartNote').hidden = false;
    el('rsChartCard').hidden = false;
  }

  // Same palette ReportingViz's mountChart() uses for pie/doughnut segments
  // and multi-series bar/line. Duplicated here (not shared/imported) rather
  // than reached for via window.ReportingViz -- see the comment above
  // chartCardNote: that module is a singleton wired to the Advanced pane's
  // own DOM/state, and Simple deliberately never touches it. Must stay in
  // sync with _reporting_viz_js.html's own NX_PALETTE constant. 12 entries --
  // this pane's own multi-breakdown chart path caps series at 12 (the
  // `series.length > 12` cap below, mirroring render_chart_png's MAX_SERIES),
  // so anything shorter would silently repeat a color starting at series 8.
  var NX_PALETTE = [
    '#4f46e5', '#7c3aed', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#64748b',
    '#a78bfa', '#0891b2', '#f97316', '#be123c', '#94a3b8'
  ];

  // Chart grid-line color, derived from the theme's border token at draw
  // time so it tracks light/dark mode without a second hardcoded value.
  // Duplicated from _reporting_viz_js.html's own gridColor() for the same
  // isolation reason as NX_PALETTE above -- must stay in sync.
  function gridColor() {
    var v = getComputedStyle(document.documentElement).getPropertyValue('--nx-border').trim();
    return v || 'rgba(100,116,139,.18)';
  }

  // Same number formatter as _reporting_viz_js.html's fmt() (tooltip values
  // only): integers print bare, other numbers to 2 decimals, so aggregated
  // sums/averages don't show floating-point noise in the tooltip.
  function fmtChartTooltip(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
    return String(v);
  }

  // ----- Colours & axes overrides (def.style, Simple tab only) -----
  // style = { colors: {seriesKey: '#rrggbb'}, titleColor: '#rrggbb',
  //           rightAxis: [seriesKey] } -- saved with the report like forecast.
  function styleOf() {
    var cur = state.current;
    return (cur && cur.def && cur.def.style) || {};
  }
  function ensureStyle() {
    var cur = state.current;
    if (!cur.def.style) cur.def.style = {};
    return cur.def.style;
  }
  // Metric code for measure series (locale-stable); the pivoted label for
  // multi-breakdown series, where several series share one measure code.
  function seriesKey(ds, multi) { return (!multi && ds.field) || ds.label; }
  // ponytail: backlog detection by metric code; make it registry-driven if a
  // second level-type measure ever appears.
  function rightAxisKeys(d, style) {
    if (Array.isArray(style.rightAxis)) return style.rightAxis;
    if (!d || d.datasets.length < 2) return [];
    return d.datasets.filter(function (ds) { return /backlog/i.test(ds.field || ''); })
      .map(function (ds) { return seriesKey(ds, !!d.multiSeries); });
  }
  function fadeColor(c) {
    if (typeof c !== 'string') return c;
    if (c.charAt(0) === '#') return hexAlpha(c, .35);
    var m = /^rgba?\(([^)]+)\)$/.exec(c);
    if (!m) return c;
    return 'rgba(' + m[1].split(',').slice(0, 3).map(function (s) { return s.trim(); }).join(',') + ',.35)';
  }
  function localTodayIso() {
    var t = new Date(), p = function (n) { return (n < 10 ? '0' : '') + n; };
    return t.getFullYear() + '-' + p(t.getMonth() + 1) + '-' + p(t.getDate());
  }
  // Start of the bucket that contains today, in the SQL grain's own keys.
  function currentBucketStart(grain) {
    var seq = bucketSeq(localTodayIso(), localTodayIso(), grain);
    return seq && seq.length ? seq[0] : '';
  }
  function hexAlpha(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function rgbToHex(rgb) {
    var m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(rgb || '');
    if (!m) return '#1f2937';
    return '#' + [m[1], m[2], m[3]].map(function (v) {
      return ('0' + parseInt(v, 10).toString(16)).slice(-2);
    }).join('');
  }
  function applyTitleStyle() {
    el('rsResultTitle').style.color = styleOf().titleColor || '';
  }

  // Console x-axis: compact bucket labels ("Jan 25", "Q2 25", "2025",
  // "3 Mar") instead of raw ISO dates — the tooltip title keeps the full
  // value. Category axes (no grain) pass through unchanged.
  function prettyBucketLabel(s, grain) {
    var m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(s == null ? '' : s));
    if (!m || !grain) return s;
    var dte = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3] || 1));
    if (isNaN(dte)) return s;
    if (grain === 'year') return m[1];
    if (grain === 'quarter') return 'Q' + (Math.floor(dte.getMonth() / 3) + 1) + ' ' + m[1].slice(2);
    if (grain === 'month') return dte.toLocaleDateString(undefined, { month: 'short' }) + ' ' + m[1].slice(2);
    return dte.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });  // day / week
  }

  // Pure: the Chart.js config for a chart-data block. `def` supplies the
  // saved style (colours / right-axis picks) and the date grain; opts.onDrill
  // (index, datasetIndex) receives clicks on real (non-forecast) elements.
  // Reads only the dark-mode class and --nx-border from the document.
  // Returns {type, multi, circular, config}. Shared with the dashboard's
  // whole-report card via window.ReportingSimple.
  function chartConfigFor(d, type, def, opts) {
    var style = (def && def.style) || {};
    var onDrill = (opts && opts.onDrill) || function () {};
    var xGrain = ((def && (def.columns || [])[0]) || {}).grain || null;
    var multi = !!(d && d.multiSeries);
    if (multi && (type === 'pie' || type === 'doughnut')) type = 'bar';
    var stacked = type === 'stacked';
    var chartJsType = stacked ? 'bar' : type;
    var circular = chartJsType === 'pie' || chartJsType === 'doughnut';
    // Single-series bar/line get the ink-navy treatment (peak bucket accented
    // in indigo for bars); stacked, pie/doughnut and multi-series charts keep
    // their existing palette.
    var singleSeries = d.datasets.length === 1 && !stacked &&
      (chartJsType === 'bar' || chartJsType === 'line');
    var maxIdx = 0;
    if (singleSeries && chartJsType === 'bar') {
      var vals0 = d.datasets[0].data;
      for (var mi = 1; mi < vals0.length; mi++) { if (vals0[mi] > vals0[maxIdx]) maxIdx = mi; }
    }
    var isDark = document.documentElement.classList.contains('dark');
    // Pie/doughnut segment borders (mirrors mountChart's rlSliceBorder, fixed
    // in edf604f for the Advanced renderer): a hardcoded white border reads
    // as a bright ring against the dark --nx-card canvas (#1e293b) this
    // chart sits on -- recede into the card background in dark mode instead
    // of forcing white.
    var rlSliceBorder = isDark ? '#1e293b' : '#fff';
    var datasets = d.datasets.map(function (ds) {
      var out = Object.assign({}, ds);
      if (!multi && circular) {
        out.backgroundColor = d.labels.map(function (_, i) {
          return NX_PALETTE[i % NX_PALETTE.length];
        });
        out.borderColor = rlSliceBorder;
      } else if (singleSeries) {
        // Ink-navy (#312e81) sits at ~1.3:1 contrast against the dark
        // --nx-card canvas (#1e293b) — effectively invisible. Lift to the
        // #818cf8 family (the existing --nx-accent dark token) only for
        // dark mode; light mode keeps the locked ink-navy/indigo-peak spec.
        var rlNavy = isDark ? '#818cf8' : '#312e81';
        var rlPeak = isDark ? '#c7d2fe' : '#4f46e5';
        if (chartJsType === 'bar') {
          out.backgroundColor = ds.data.map(function (v, i) { return i === maxIdx ? rlPeak : rlNavy; });
        } else {
          out.backgroundColor = isDark ? 'rgba(129,140,248,.18)' : 'rgba(49,46,129,.12)';
        }
        out.borderColor = rlNavy;
      }
      // Rounded bars + a thickness cap (mirrors mountChart's ds.borderRadius/
      // maxBarThickness) — every bar rendering, single-series or stacked.
      if (chartJsType === 'bar') {
        out.borderRadius = 6;
        out.maxBarThickness = 48;
      }
      return out;
    });
    var overrides = style.colors || {};
    var rightKeys = circular ? [] : rightAxisKeys(d, style);
    var useY2 = false;
    datasets = datasets.map(function (ds, i) {
      var key = seriesKey(d.datasets[i], multi);
      var c = overrides[key];
      if (c && !circular) {
        ds.borderColor = c;
        ds.backgroundColor = chartJsType === 'line' ? hexAlpha(c, .15) : c;
      }
      if (rightKeys.indexOf(key) >= 0) { ds.yAxisID = 'y2'; useY2 = true; }
      return ds;
    });
    // The bucket containing today is still filling up: fade it (bar) or dash
    // into it (line) so a low current month reads as "in progress", not a drop.
    var grain0 = (def && (def.columns || [])[0]) ? def.columns[0].grain : null;
    var partialIdx = (grain0 && !circular) ? d.labels.indexOf(currentBucketStart(grain0)) : -1;
    if (partialIdx >= 0) {
      datasets = datasets.map(function (ds) {
        var out = Object.assign({}, ds);
        if (chartJsType === 'bar') {
          var base = out.backgroundColor;
          out.backgroundColor = out.data.map(function (_, i) {
            var c = Array.isArray(base) ? base[i] : base;
            return i === partialIdx ? fadeColor(c) : c;
          });
        } else {
          out.segment = { borderDash: function (ctx) { return ctx.p1DataIndex === partialIdx ? [4, 4] : undefined; } };
          out.pointStyle = out.data.map(function (_, i) { return i === partialIdx ? 'rectRot' : 'circle'; });
        }
        return out;
      });
    }
    // A level's NULL bucket is a gap in knowledge, not a cliff — bridge it.
    if (chartJsType === 'line') datasets.forEach(function (ds) { ds.spanGaps = true; });
    // Axis ownership cues: each Y axis is titled with its series and, when it
    // carries exactly one series, its ticks take that series' colour.
    var leftSeries = [], rightSeries = [];
    datasets.forEach(function (ds) { (ds.yAxisID === 'y2' ? rightSeries : leftSeries).push(ds); });
    function axisTint(list) {
      return (list.length === 1 && typeof list[0].borderColor === 'string') ? list[0].borderColor : undefined;
    }
    function axisTitle(list) { return list.map(function (ds) { return ds.label; }).join(' · '); }
    var fcActive = !!(d.forecast && !multi && !stacked && (chartJsType === 'line' || chartJsType === 'bar'));
    if (fcActive) {
      var fc = d.forecast;
      var histN = d.forecastStart;
      var pad = fc.buckets.map(function () { return null; });
      datasets = datasets.map(function (ds) {
        return Object.assign({}, ds, { data: ds.data.concat(pad) });
      });
      var fcAccent = isDark ? '#818cf8' : '#4f46e5';
      var lead = [];
      for (var li = 0; li < histN - 1; li++) lead.push(null);
      fc.series.forEach(function (s, si) {
        var base = d.datasets[si];
        var styled = datasets[si] || {};
        var bridge = base ? base.data[histN - 1] : null;
        // A user-picked series colour carries over to its forecast line (and
        // its right-axis placement), so the dotted tail stays readable.
        var own = overrides[seriesKey(base || {}, multi)];
        var fcColor = own || (typeof styled.borderColor === 'string' ? styled.borderColor : fcAccent);
        var fcLabel = (base ? base.label : s.field) + ' · ' + I18N.forecastLabel;
        // Bar charts get the forecast as translucent bars of the same colour
        // (dashed lines over bars read as a stray series); line charts keep
        // the dashed tail + confidence band.
        datasets.push(chartJsType === 'bar' ? {
          label: fcLabel, data: lead.concat([null], s.values), type: 'bar',
          backgroundColor: hexAlpha(fcColor, .35), borderColor: fcColor, borderWidth: 1,
          borderRadius: 6, maxBarThickness: 48, yAxisID: styled.yAxisID, _forecast: true
        } : {
          label: fcLabel, data: lead.concat([bridge], s.values),
          type: 'line', borderColor: fcColor, borderDash: [6, 4],
          borderWidth: 2, backgroundColor: 'transparent', yAxisID: styled.yAxisID,
          pointStyle: 'rectRot', fill: false, tension: .25, _forecast: true
        });
      });
      if (fc.series.length === 1 && chartJsType === 'line') {
        var s0 = fc.series[0];
        var b0 = d.datasets[0] ? d.datasets[0].data[histN - 1] : null;
        var own0 = overrides[seriesKey(d.datasets[0] || {}, multi)];
        var bandFill = own0 ? hexAlpha(own0, .15)
          : (isDark ? 'rgba(129,140,248,.18)' : 'rgba(79,70,229,.12)');
        datasets.push({ label: '', data: lead.concat([b0], s0.upper), type: 'line',
          borderWidth: 0, pointRadius: 0, backgroundColor: 'transparent',
          fill: false, _band: true });
        datasets.push({ label: '', data: lead.concat([b0], s0.lower), type: 'line',
          borderWidth: 0, pointRadius: 0, backgroundColor: bandFill,
          fill: '-1', _band: true });
      }
    }
    // Integer-only y-axis ticks when every plotted value across every
    // dataset actually is an integer (e.g. a COUNT/GROUP BY report) — a
    // fractional measure (avg/sum of decimals) keeps Chart.js's normal tick
    // spacing. Mirrors mountChart's allInts guard.
    var allInts = !circular && datasets.every(function (ds) {
      return (ds.data || []).every(function (v) { return Number.isInteger(v); });
    });
    var config = {
      type: chartJsType,
      data: { labels: d.labels, datasets: datasets },
      options: { responsive: true, maintainAspectRatio: false,
                 scales: (circular) ? {}
                   : { x: { stacked: stacked,
                            ticks: {
                              maxRotation: 0,
                              autoSkip: true,
                              maxTicksLimit: 12,
                              callback: function (value) {
                                return prettyBucketLabel(this.getLabelForValue(value), xGrain);
                              }
                            } },
                       y: { stacked: stacked,
                            beginAtZero: true,
                            title: { display: useY2, text: axisTitle(leftSeries), color: axisTint(leftSeries) },
                            ticks: {
                              maxTicksLimit: 6,
                              color: useY2 ? axisTint(leftSeries) : undefined,
                              callback: function (value) {
                                return (allInts && !Number.isInteger(value)) ? undefined : value;
                              }
                            },
                            grid: { color: gridColor() } },
                       // Secondary Y axis for level-type series (backlog in the
                       // hundreds beside imports in the tens of thousands).
                       y2: { display: useY2, position: 'right', beginAtZero: true,
                             title: { display: true, text: axisTitle(rightSeries), color: axisTint(rightSeries) },
                             ticks: { maxTicksLimit: 6, color: axisTint(rightSeries) },
                             grid: { drawOnChartArea: false } } },
                 plugins: { legend: { display: multi || circular || (d.datasets && d.datasets.length > 1) || fcActive,
                                      labels: { color: style.titleColor || undefined,
                                                filter: function (item, data) {
                                        // D6: band + forecast-line datasets are excluded from
                                        // the legend (and drill — see the _forecast/_band guard
                                        // in the drill click-handler below).
                                        var ds = data.datasets[item.datasetIndex] || {};
                                        return !(ds._band || ds._forecast);
                                      } } },
                            tooltip: {
                              callbacks: {
                                // Reuse the module's own number formatter (fmtChartTooltip)
                                // instead of Chart.js's raw float — mirrors mountChart's tooltip.
                                label: function (ctx) {
                                  var raw = ctx.parsed;
                                  var v = (raw && typeof raw === 'object') ? raw.y : raw;
                                  var name = circular ? (ctx.label || '') : (ctx.dataset.label || '');
                                  return (name ? name + ': ' : '') + fmtChartTooltip(v);
                                }
                              }
                            } },
                 onClick: function (evt) {
                   var els = this.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
                   if (!els.length) return;
                   var dsHit = (this.data.datasets || [])[els[0].datasetIndex] || {};
                   if (dsHit._forecast || dsHit._band) return;
                   if (d.forecastStart != null && d.forecast && els[0].index >= d.forecastStart) return;
                   onDrill(els[0].index, els[0].datasetIndex);
                 },
                 onHover: function (evt, els) {
                   evt.native.target.style.cursor = els.length ? 'pointer' : 'default';
                 } }
    };
    return { type: type, multi: multi, circular: circular, config: config };
  }

  function renderChart(type) {
    var d = state.chartData;
    if (!d) return;
    destroyChart();
    var built = chartConfigFor(d, type, (state.current && state.current.def) || {},
                               { onDrill: drillFromChart });
    type = built.type;
    state.chartType = type;
    var multi = built.multi, circular = built.circular;
    state.chart = new Chart(el('rsChartCanvas'), built.config);
    el('rsChartTools').querySelector('[data-type="pie"]').hidden = multi;
    el('rsChartTools').querySelector('[data-type="doughnut"]').hidden = multi;
    // Forecast only draws on line/bar — grey the toggle out on pie/doughnut
    // (syncForecastCtl owns the shape-based disable after each run).
    var fcBtn = el('rsForecastToggle');
    if (circular) { fcBtn.disabled = true; fcBtn.title = I18N.forecastNeedsLineBar; }
    else if (state.current && forecastEligible(state.current.def)) { fcBtn.disabled = false; fcBtn.title = I18N.forecastLabel; }
    el('rsChartTools').querySelector('[data-type="stacked"]').hidden = !multi;
    el('rsChartCanvas').dataset.series = String(d.datasets.length);
    Array.prototype.forEach.call(
      el('rsChartTools').querySelectorAll('button'), function (b) {
        b.classList.toggle('is-selected', b.dataset.type === type);
        b.setAttribute('aria-pressed', b.dataset.type === type ? 'true' : 'false');
      });
  }

  // ----- Zero-fill for date-grain buckets -----
  // "Documents per month in Q1" with data only in February must render three
  // buckets (0, 2, 0), not a single point — sparse SQL GROUP BY drops empty
  // buckets, misleading trend lines. Fills only the single-dimension case
  // with a metric and a bounded between filter on the grain column.
  // ponytail: dims>=2 keeps SQL's buckets — cross-product fill needs a
  // series axis decision; add if sparse multi-series charts start to hurt.
  function bucketSeq(startIso, endIso, grain) {
    var d = new Date(startIso.slice(0, 10) + 'T00:00:00Z');
    var end = new Date(endIso.slice(0, 10) + 'T00:00:00Z');
    if (isNaN(d) || isNaN(end)) return null;
    // Snap to the bucket start the SQL grain produces (week = Monday-anchored,
    // matching query.py's DATEDIFF(week, 0, d)).
    if (grain === 'week') d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    else if (grain === 'month') d.setUTCDate(1);
    else if (grain === 'quarter') d.setUTCMonth(Math.floor(d.getUTCMonth() / 3) * 3, 1);
    else if (grain === 'year') d.setUTCMonth(0, 1);
    var out = [];
    while (d <= end) {
      if (out.length >= 366) return null;   // unbounded/absurd range: skip fill
      out.push(d.toISOString().slice(0, 10));
      if (grain === 'day') d.setUTCDate(d.getUTCDate() + 1);
      else if (grain === 'week') d.setUTCDate(d.getUTCDate() + 7);
      else if (grain === 'month') d.setUTCMonth(d.getUTCMonth() + 1);
      else if (grain === 'quarter') d.setUTCMonth(d.getUTCMonth() + 3);
      else d.setUTCFullYear(d.getUTCFullYear() + 1);
    }
    return out;
  }

  // explicitRange, when given, is a [start, end] ISO-date pair used as-is
  // instead of derived from def's own filters/resolvedDates -- needed for
  // the prior-comparison period, whose [priorStart, priorEnd] window (a
  // length-based shift of def's range, not the same absolute dates) has no
  // filter or resolvedDates entry of its own to derive from.
  function zeroFillDateBuckets(def, rows, resolvedDates, explicitRange) {
    var cols = def.columns || [];
    var grain = cols.length === 1 ? cols[0].grain : null;
    if (!grain || !(def.metrics || []).length) return rows;
    var range = explicitRange || null;
    if (!range) {
      var f = (def.filters || []).find(function (x) {
        return x.field === cols[0].field && x.op === 'between';
      });
      if (!f) return rows;
      if (Array.isArray(f.value) && f.value.length === 2) {
        range = [String(f.value[0]), String(f.value[1])];
      } else if (f.value && typeof f.value === 'object') {
        var rd = resolvedDates.find(function (x) { return x.field === cols[0].field; });
        if (rd) range = [rd.start, rd.end];
      }
    }
    if (!range) return rows;
    // Never fabricate buckets that haven't happened yet: "This year" fills
    // Jan..today, not Jan..Dec — a future month is unknown, not zero.
    var today = localTodayIso();
    var seq = bucketSeq(range[0], range[1] > today ? today : range[1], grain);
    if (!seq) return rows;
    var byBucket = {};
    rows.forEach(function (r) {
      byBucket[String(r[0] == null ? '' : r[0]).slice(0, 10)] = r;
    });
    // Flows (counts) fill with 0 — nothing happened. Levels (latest-mode,
    // e.g. backlog) fill with null — nobody measured, which is not zero.
    var modes = metricTotalModes(def);
    var zeros = (def.metrics || []).map(function (_, i) { return modes[i] === 'latest' ? null : 0; });
    var filled = seq.map(function (b) { return byBucket[b] || [b].concat(zeros); });
    // A data row whose bucket string didn't match the generated sequence
    // (dialect formatting drift) means the fill would DROP data — bail to
    // the raw rows instead.
    var misses = rows.some(function (r) {
      return seq.indexOf(String(r[0] == null ? '' : r[0]).slice(0, 10)) === -1;
    });
    if (misses) return rows;
    var s0 = (def.sort || [])[0];
    if (s0 && s0.field === cols[0].field && s0.dir === 'desc') filled.reverse();
    return filled;
  }

  // Pure: turns a run result into the chart-data block renderChart /
  // chartConfigFor draw. Returns {data, note}: data null = no chart and
  // note says why (too many points); note alongside data = a non-blocking
  // disclosure (first-50 cut, series cap, data-quality notes). DOM-free --
  // shared with the dashboard's whole-report card via window.ReportingSimple.
  function buildChartData(def, columns, rows, forecast) {
    var note = null;
    function addNote(txt) { note = note ? note + ' — ' + txt : txt; }
    var dims = (def.columns || []).length;
    if (!dims || !rows.length) return { data: null, note: null };
    var firstCol = def.columns[0];
    var isDate = !!firstCol.grain || /date/.test(firstCol.field);
    // Single-dim only: here rows.length IS the x-point count, so the raw-row
    // cap is correct. For dims===2 the rows are the (dim1 x dim2) cross-product
    // (e.g. 12 months x 8 sources = 96 rows) that the pivot below collapses to
    // far fewer x-points, so two-dim is judged AFTER pivoting by the xOrder>50
    // guard + 12-series cap (mirrors render_chart_png MAX_X / MAX_SERIES).
    // A bucketed date axis stays readable far past 50 points (53 weeks, a
    // year of days); only categorical axes keep the 50-row cut.
    var xCap = isDate ? 400 : 50;
    if (dims === 1 && rows.length > xCap) {
      if (isDate) return { data: null, note: I18N.noChartTooManyPoints };
      addNote(I18N.chartFirst50.replace('{n}', String(rows.length)));
      rows = rows.slice(0, 50);
    }
    if (dims >= 2) {
      // EVERY metric is pivoted into series: with several measures each
      // (dims × measure) pair becomes its own series ("Process · Measure").
      var metricIdx2 = columns.length - (def.metrics || []).length;
      var nMetrics2 = (def.metrics || []).length || 1;
      var mLabels2 = metricLabelsFor(def);
      var modes2 = metricTotalModes(def);
      var xOrder = [], cell = {}, seriesTot = {}, seriesParts = {}, seriesMetric = {};
      rows.forEach(function (r) {
        var x = String(r[0] == null ? '' : r[0]).slice(0, isDate ? 10 : 200);
        // Series key = ALL remaining breakdowns joined ("Process · Source").
        // With every dim in the key nothing collapses in the pivot, so each
        // cell is one exact aggregate row — correct for any aggregation, not
        // just additive ones (the old third-dim collapse only held for
        // count/sum). The 12-series cap below bounds the cross-product.
        var parts = [], labelParts = [], d;
        for (d = 1; d < dims; d++) {
          var pv = String(r[d] == null ? '' : r[d]);
          parts.push(pv);
          // A non-leading DATE dim (#164) arrives as an ISO datetime — trim it
          // for the legend the same way the x labels are trimmed. parts stays
          // raw so drill-through still gets the full value.
          labelParts.push(def.columns[d] && def.columns[d].grain ? pv.slice(0, 10) : pv);
        }
        if (!cell[x]) { xOrder.push(x); cell[x] = {}; }
        for (var mi = 0; mi < nMetrics2; mi++) {
          var s = nMetrics2 > 1
            ? labelParts.concat([mLabels2[mi] || def.metrics[mi].metric]).join(' · ')
            : labelParts.join(' · ');
          // A level metric (backlog) is NULL, not 0, on legs where it wasn't
          // measured — coercing it to 0 here would silently zero out a real
          // gap once broken down by a second dimension (#follow-up from the
          // stop-at-today/backlog-as-a-level audit). Only fold in a value
          // when this row actually has one; an all-NULL cell stays NULL.
          if (!(s in cell[x])) cell[x][s] = modes2[mi] === 'latest' ? null : 0;
          var raw = r[metricIdx2 + mi];
          if (raw != null) {
            var v = Number(raw) || 0;
            cell[x][s] = (cell[x][s] || 0) + v;
            seriesTot[s] = (seriesTot[s] || 0) + v;
          }
          seriesParts[s] = parts;
          seriesMetric[s] = mi;
        }
      });
      if (xOrder.length > xCap) return { data: null, note: I18N.noChartTooManyPoints };
      var allSeries = Object.keys(seriesTot);
      var byTot = function (a, b) { return seriesTot[b] - seriesTot[a]; };
      var series;
      if (nMetrics2 > 1) {
        // Fair cap: top slots per measure, so a small-valued measure (a
        // backlog of hundreds next to document counts in the tens of
        // thousands) is never crowded out of the chart entirely.
        var per = Math.max(1, Math.floor(12 / nMetrics2));
        series = [];
        for (var mj = 0; mj < nMetrics2; mj++) {
          series = series.concat(allSeries.filter(function (s) {
            return seriesMetric[s] === mj;
          }).sort(byTot).slice(0, per));
        }
      } else {
        series = allSeries.sort(byTot).slice(0, 12);
      }
      if (allSeries.length > series.length) {
        addNote(I18N.chartSeriesCapped
          .replace('{shown}', String(series.length)).replace('{n}', String(allSeries.length)));
      }
      noteDataQuality(def, rows, isDate).forEach(addNote);
      return { data: {
        labels: xOrder,
        // Raw click values for drill-through: the pivot above already
        // stringifies x keys ('' means NULL), so labels === raw here. Series
        // are per-dim value arrays so a click can filter each breakdown.
        rawX: xOrder,
        rawSeries: series.map(function (s) { return seriesParts[s]; }),
        datasets: series.map(function (s, i) {
          return {
            label: s,
            // Style key for the colours/axes popover. With several measures a
            // pivoted series is "<category> · <measure>" — keep the measure
            // code in `field` so a backlog series can default to the right axis.
            field: def.metrics && def.metrics[seriesMetric[s]] ? def.metrics[seriesMetric[s]].metric : null,
            data: xOrder.map(function (x) {
              var v = cell[x] ? cell[x][s] : undefined;
              return v === undefined ? (modes2[seriesMetric[s]] === 'latest' ? null : 0) : v;
            }),
            borderColor: NX_PALETTE[i % NX_PALETTE.length],
            backgroundColor: NX_PALETTE[i % NX_PALETTE.length],
            tension: .25
          };
        }),
        multiSeries: true,
        // Preview cache (Step 5) reads this back to tag the cached series —
        // must match whatever renderChart() below actually draws.
        type: def.chartType || (isDate ? 'line' : 'bar')
      }, note: note };
    }
    var metricIdx = columns.length - (def.metrics || []).length;
    var labels = rows.map(function (r) {
      var v = String(r[0] == null ? '' : r[0]);
      // Date values arrive as ISO datetimes — trim to the date part. Category
      // labels stay intact.
      return isDate ? v.slice(0, 10) : v;
    });
    // Raw click values for drill-through, same order as labels/rows (labels
    // are display strings — e.g. date-trimmed — so NULL/full values live here).
    var rawX = rows.map(function (r) { return r[0]; });
    var mLabels = metricLabelsFor(def);
    var datasets = (def.metrics || []).map(function (m, i) {
      var col = columns[metricIdx + i];
      return {
        label: mLabels[i] || (col ? (col.header || m.metric) : m.metric),
        field: m.metric,
        data: rows.map(function (r) { return r[metricIdx + i] == null ? null : Number(r[metricIdx + i]); }),
        // First metric keeps the classic indigo; further metrics take the
        // series palette so a multi-measure report reads as distinct series.
        borderColor: i === 0 ? '#4f46e5' : NX_PALETTE[i % NX_PALETTE.length],
        backgroundColor: i === 0 ? 'rgba(79,70,229,.45)'
                                 : NX_PALETTE[i % NX_PALETTE.length],
        tension: .25
      };
    });
    var fc = (forecast && !forecast.unavailable &&
              (forecast.buckets || []).length) ? forecast : null;
    var histN = labels.length;
    if (fc) {
      labels = labels.concat(fc.buckets.map(function (b) { return String(b).slice(0, 10); }));
    }
    noteDataQuality(def, rows, isDate).forEach(addNote);
    return { data: {
      labels: labels, rawX: rawX, datasets: datasets, multiSeries: false,
      forecast: fc, forecastStart: histN,
      type: def.chartType || (isDate ? 'line' : 'bar')
    }, note: note };
  }

  function mountChart(def, columns, rows, forecast) {
    destroyChart();
    state.chartData = null;
    el('rsChartNote').hidden = true;
    el('rsChartTools').hidden = true;
    toggleStylePop(false);
    el('rsChartCanvas').hidden = false;
    var dims = (def.columns || []).length;
    if (!dims || !rows.length) { el('rsChartCard').hidden = true; return false; }
    if (!window.Chart) { chartCardNote(I18N.noChartLib); return false; }
    var built = buildChartData(def, columns, rows, forecast);
    if (!built.data) { chartCardNote(built.note || I18N.noChartTooManyPoints); return false; }
    if (built.note) {
      el('rsChartNote').textContent = built.note;
      el('rsChartNote').hidden = false;
    }
    state.chartData = built.data;
    el('rsChartCard').hidden = false;
    el('rsChartTools').hidden = false;
    renderChart(state.chartData.type);
    return true;
  }

  function appendChartNote(txt) {
    var n = el('rsChartNote');
    n.textContent = (!n.hidden && n.textContent) ? n.textContent + ' — ' + txt : txt;
    n.hidden = false;
  }

  // Under-chart disclosures the numbers alone don't carry: the bucket that
  // contains today is still filling up, and a level metric's NULL buckets
  // are unmeasured, not empty.
  function noteDataQuality(def, rows, isDate) {
    var out = [];
    var c0 = (def.columns || [])[0];
    if (!isDate || !c0 || !c0.grain) return out;
    var cur = currentBucketStart(c0.grain);
    if (rows.some(function (r) { return String(r[0] == null ? '' : r[0]).slice(0, 10) === cur; })) {
      out.push(I18N.partialBucketNote);
    }
    var metricIdx = (def.columns || []).length, modes = metricTotalModes(def);
    var gaps = rows.some(function (r) {
      return modes.some(function (m, i) { return m === 'latest' && r[metricIdx + i] == null; });
    });
    if (gaps) out.push(I18N.gapNote);
    return out;
  }

  // One-line transparency note under the title of AI-built reports: the
  // model's own explanation plus the filters/scope it chose, so a wrong guess
  // (bad date range, wrong process) is visible instead of silently rendering
  // an empty table.
  // Relative-date tokens (nx_lib/reporting/tokens.py) — humanized labels for
  // chips/summary lines. A token value is {token: '<name>'[, n: <int>]}.
  var TOKEN_LABELS = {
    today: I18N.tokenToday, yesterday: I18N.tokenYesterday,
    this_week: I18N.thisWeek, last_week: I18N.lastWeek,
    this_month: I18N.thisMonth, last_month: I18N.lastMonth,
    this_quarter: I18N.thisQuarter, last_quarter: I18N.lastQuarter,
    last_3_months: I18N.last3Months, this_year: I18N.thisYear,
    last_year: I18N.lastYear, last_n_days: I18N.lastNDays
  };
  function isTokenValue(v) {
    return !!v && typeof v === 'object' && !Array.isArray(v) && typeof v.token === 'string';
  }
  function tokenLabel(v) {
    if (!v || typeof v.token !== 'string') return '';
    var lbl = TOKEN_LABELS[v.token] || v.token;
    return v.token === 'last_n_days' ? lbl.replace('{n}', v.n) : lbl;
  }

  // ----- Editable AI chips -----
  function fieldMetaFor(def, fieldKey) {
    var src = (state.sources || []).find(function (s) { return s.id === def.source; });
    return ((src && src.fields) || []).find(function (f) { return f.field === fieldKey; });
  }

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
    between: I18N.opBetween, 'in': I18N.opIn, not_in: I18N.opNotIn,
    contains: I18N.opContains, starts_with: I18N.opStartsWith,
    is_null: I18N.opIsEmpty, is_not_null: I18N.opIsNotEmpty
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
    box.textContent = I18N.loadingValues;
    openChipEditor(chipEl, box);
    var src = (state.sources || []).find(function (s) { return s.id === cur.def.source; });
    var values = [], labels = {};
    if (f.field === 'processname' && src && (src.processes || []).length) {
      values = src.processes.slice();
    } else {
      var res = await api('/api/reporting/field_values', {
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
    ok.textContent = I18N.chipApply;
    ok.addEventListener('click', function () {
      var picked = inputs.filter(function (c) { return c.checked; })
                         .map(function (c) { return c.value; });
      if (opts.allMeansNoFilter && picked.length === values.length) {
        var at = cur.def.filters.indexOf(f);
        if (at !== -1) cur.def.filters.splice(at, 1);
        runCurrent();
        return;
      }
      if (!picked.length) return;   // an empty IN () matches nothing — keep editing
      f.value = picked;
      if (opts.onApply) opts.onApply(f);
      runCurrent();
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
      co.textContent = I18N.custom;
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
    ok.textContent = I18N.chipApply;
    ok.addEventListener('click', function () {
      if (preset && preset.value) {
        f.op = 'between';
        f.value = { token: preset.value };
        runCurrent();
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
      runCurrent();
    });
    box.appendChild(input);
    box.appendChild(ok);
    openChipEditor(chipEl, box);
    if (!input.hidden) input.focus();
  }

  async function processChipEditor(cur, chipEl) {
    await loadSourcesCatalog();
    if (!chipEl.isConnected) return;
    var src = (state.sources || []).find(function (s) { return s.id === cur.def.source; });
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
    ok.textContent = I18N.chipApply;
    ok.addEventListener('click', function () {
      var picked = inputs.filter(function (c) { return c.checked; })
                         .map(function (c) { return c.value; });
      cur.def.scope = cur.def.scope || { clients: [], processes: [] };
      cur.def.scope.processes = picked.length === all.length ? [] : picked;
      runCurrent();
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
    [['day', I18N.grainDay], ['week', I18N.grainWeek], ['month', I18N.grainMonth],
     ['quarter', I18N.grainQuarter], ['year', I18N.grainYear]].forEach(function (g) {
      var o = document.createElement('option');
      o.value = g[0]; o.textContent = g[1];
      sel.appendChild(o);
    });
    if (col.grain) sel.value = col.grain;
    var ok = document.createElement('button');
    ok.className = 'reporting-btn';
    ok.setAttribute('data-testid', 'rs-chip-grain-apply');
    ok.textContent = I18N.chipApply;
    ok.addEventListener('click', function () {
      col.grain = sel.value;
      runCurrent();
    });
    box.appendChild(sel);
    box.appendChild(ok);
    openChipEditor(chipEl, box);
  }

  function renderAiChips(cur) {
    var wrap = el('rsChips');
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
    var chipSrc = (state.sources || []).find(function (s) { return s.id === def.source; });
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
          runCurrent();
        }
      ));
    });
    if (!(def.filters || []).length) {
      var none = document.createElement('span');
      none.className = 'rs-chip rs-chip--empty';
      none.textContent = I18N.aiNoFilters;
      wrap.appendChild(none);
    }
    if (pf) {
      var pfVals = (pfFilter && pfFilter.value) || [];
      wrap.appendChild(chip(
        I18N.aiProcesses + ': ' + (pfVals.length ? pfVals.join(', ') : I18N.allProcesses),
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
        I18N.aiProcesses + ': ' + (procs.length ? procs.join(', ') : I18N.allProcesses),
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
      var GRAIN_LABELS = { day: I18N.grainDay, week: I18N.grainWeek, month: I18N.grainMonth,
                           quarter: I18N.grainQuarter, year: I18N.grainYear };
      wrap.appendChild(chip(
        I18N.granularity + ': ' + (GRAIN_LABELS[grainedCol.grain] || I18N.grainDay),
        function (chipEl) { grainChipEditor(cur, grainedCol, chipEl); },
        null
      ));
    }
  }

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
  // reporting.ai.explain_data holder (Jinja `ai_caption_enabled` gate in
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
      var cur = currentBucketStart(c0.grain);
      if (rows.some(function (r) { return String(r[0] == null ? '' : r[0]).slice(0, 10) === cur; })) {
        out.push('The bucket ' + cur + ' is the current, still-running period and is incomplete; ' +
                 'do not compare it with finished periods or call it a drop.');
      }
    }
    var modes = metricTotalModes(def), labels = metricLabelsFor(def), metricIdx = (def.columns || []).length;
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
    var labels = metricLabelsFor(def);
    return metricTotalModes(def).map(function (m, i) { return m === 'latest' ? labels[i] : null; })
      .filter(Boolean);
  }

  function fireCaption(boxId, columns, rows, title, dateLabel, notes, levelFields) {
    var box = el(boxId);
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
      chip.textContent = I18N.aiChip;
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

  async function runCurrent() {
    var cur = state.current;
    var seq = ++runSeq;
    setHeaderActionsEnabled(false);
    // A new run supersedes any open drill drawer — it shows rows behind the
    // PREVIOUS result and would sit stale over the new one (e.g. after a
    // chip edit).
    if (window.ReportingDrill) ReportingDrill.close();
    // Fire-and-forget: not every runCurrent() caller already awaits
    // loadSourcesCatalog() first, so warm it here too for the drill
    // affordance (openDrill/renderTable read state.sources). Idempotent — a
    // cache hit resolves immediately, and drill just stays unavailable until
    // this settles on a cold session.
    loadSourcesCatalog().then(function () {
      // Chip labels resolve field keys against the catalog — re-render once it
      // lands (the first paint may fall back to raw keys on a cold session).
      // The seq guard keeps a stale resolve from repainting a newer result.
      // The editor guard keeps a slow resolve from wiping an open chip editor
      // mid-edit (rs-chip-apply vanished between fill and click on slow CI);
      // labels catch up on the next runCurrent() repaint anyway.
      var wrap = el('rsChips');
      if (seq === runSeq && state.current === cur
          && !(wrap && wrap.querySelector('.rs-chip-editor'))) renderAiChips(cur);
    });
    setView('result');
    el('rsError').hidden = true;
    renderErrorOpenAdvanced(false);
    toggleMoreMenu(false);
    el('rsMsg').hidden = true;
    el('rsResultTitle').textContent = cur.name || cur.def.title || '';
    el('rsCrumbName').textContent = cur.name || cur.def.title || '';
    el('rsSavedChip').hidden = !cur.reportId;
    applyTitleStyle();
    el('rsDeleteReport').hidden = !(cur.owned && cur.reportId);
    el('rsSaveCopy').hidden = !cur.reportId;
    saveAsCopy = false;
    renderAiChips(cur);
    var adjustBtn = el('rsAdjustWizard');
    if (adjustBtn) {
      adjustBtn.hidden = cur.builtBy !== 'wizard' && !wizardStateFromDefinition(cur.def);
    }
    el('rsSaveName').hidden = true;
    setGrandTotals(null);
    el('rsChartCard').hidden = true;
    el('rsTableCard').hidden = true;
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;
    el('rsRunLoading').innerHTML = resultSkeletonHtml();
    el('rsRunLoading').hidden = false;
    el('rsDrillHint').hidden = true;
    el('rsKpiBand').hidden = true;
    // A prior run's caption sentence must never linger over the new run's
    // (still-loading, possibly failed or empty) result — hidden here just
    // like every other result element above, cleared again by fireCaption()
    // once (and if) the new run actually succeeds. Guarded: the box only
    // exists in the DOM for a reporting.ai.explain_data holder.
    var rsCaptionBox = el('rsCaption');
    if (rsCaptionBox) { rsCaptionBox.hidden = true; rsCaptionBox.textContent = ''; }
    var anomCard = el('rsAnomCard');
    if (anomCard) { anomCard.hidden = true; }

    var def = cur.def;
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;
    var dims = (def.columns || []).length;
    // Console chart-card title: what is plotted (the metric labels), not the
    // report name — that one is already in the result header.
    var chartTitle = el('rsChartTitle');
    if (chartTitle) {
      chartTitle.textContent = hasMetrics
        ? metricLabelsFor(def).join(' · ') : (cur.name || def.title || '');
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
      var t = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(totalDef) });
      if (seq !== runSeq) return;
      if (t.ok && t.data && t.data.rows && t.data.rows.length) {
        setGrandTotals(t.data.rows[0]);
      }
    }

    // Breakdown run (or the plain grid run for non-metric definitions).
    // compare: true is added to a shallow copy of the posted body only --
    // `def` (== cur.def) must stay exactly what the wizard/library built,
    // since it's reused for Save/Adjust-in-wizard/export.
    var res = await api('/api/reporting/run', {
      method: 'POST',
      body: JSON.stringify(Object.assign({}, def, { compare: true }))
    });
    if (seq !== runSeq) return;
    // Hide only after the staleness guard: a slow stale response must never
    // hide the indicator a newer run just showed.
    el('rsRunLoading').hidden = true;
    if (!res.ok) {
      showResultError(friendlyRunError(res.status, res.data),
        { title: cur.name || cur.def.title || '', openAdvanced: true });
      // The toggle must not keep showing the PREVIOUS successful run's
      // forecast-eligible/charted state once this run has errored out.
      syncForecastCtl(def, null, false);
      return;
    }
    setHeaderActionsEnabled(true);
    el('rsTableCard').hidden = false;
    showTiming(res.data.rowCount, performance.now() - runT0);
    state.current.sql = res.data.sql || null;
    state.current.sqlPretty = res.data.sqlPretty || null;
    state.current.sqlDisplay = res.data.sqlDisplay || null;
    state.current.params = res.data.params || [];
    // Console: the Query card sits in the result's side column and is always
    // visible when the run produced SQL — no reveal toggle anymore.
    el('rsSqlView').hidden = !state.current.sql;
    if (state.current.sql) {
      ReportingSqlFormat.render(el('rsSqlText'), ReportingSqlFormat.displayText(state.current));
    }
    el('rsShowSql').hidden = !state.current.sql;
    el('rsShowSql').textContent = I18N.showQuery;
    var peek = el('rsSqlPeek');
    if (state.current.sqlDisplay) {
      peek.textContent = state.current.sqlDisplay.split('\n')[0] + '…';
      peek.hidden = false;
    } else {
      peek.hidden = true;
    }
    var columns = res.data.columns || [], rows = res.data.rows || [];
    rows = zeroFillDateBuckets(def, rows, res.data.resolvedDates || []);
    // A zero-dim run's single row is itself the per-metric grand total.
    if (hasMetrics && !dims && rows.length) setGrandTotals(rows[0]);
    renderKpiBand(dims, rows, res.data.comparison || null, def, columns);
    var rdates = res.data.resolvedDates || [];
    // Hoisted out of the `if` below (Task 13): fireCaption() at the end of
    // this function needs the same resolved-dates label the message line
    // shows, or null when there's nothing to resolve.
    var resolvedTxt = null;
    if (rdates.length) {
      resolvedTxt = rdates.map(function (d) {
        return tokenLabel(d) + ' (' + d.start + ' → ' + d.end + ')';
      }).join(' · ');
      var msg = el('rsMsg');
      msg.textContent = msg.hidden || !msg.textContent
        ? resolvedTxt : msg.textContent + ' — ' + resolvedTxt;
      msg.hidden = false;
    }
    if (res.data.truncated && res.data.rowCount) {
      var tNote = el('rsMsg');
      var tTxt = I18N.truncatedNote.replace('{n}', String(res.data.rowCount));
      tNote.textContent = (!tNote.hidden && tNote.textContent)
        ? tNote.textContent + ' — ' + tTxt : tTxt;
      tNote.hidden = false;
    }
    if (hasMetrics && !dims && rows.length) {
      var totMsg = el('rsMsg');
      totMsg.textContent = (!totMsg.hidden && totMsg.textContent)
        ? totMsg.textContent + ' — ' + I18N.noChartTotalOnly : I18N.noChartTotalOnly;
      totMsg.hidden = false;
    }
    if (!rows.length) {
      el('rsTableWrap').innerHTML =
        '<div class="nx-empty"><div class="nx-empty__art"><i class="fas fa-inbox" aria-hidden="true"></i></div>' +
        '<p class="nx-empty__title">' + esc(I18N.noData) + '</p>' +
        '<p class="nx-empty__hint">' + esc(I18N.noDataHint) + '</p></div>';
      el('rsTableWrap').hidden = false;
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
    state.lastRun = { def: def, columns: columns, rows: rows, hasMetrics: hasMetrics,
                      dims: dims, forecast: res.data.forecast || null };
    var charted = (hasMetrics && dims)
      ? !!mountChart(def, columns, rows, res.data.forecast || null) : false;
    syncForecastCtl(def, res.data.forecast || null, charted);
    renderTable(columns, rows, res.data.forecast || null);
    renderAnomalies(def, columns, rows);
    // Collapse the table behind the toggle only when a chart actually rendered
    // (or the stat card carries a dimensionless total). When mountChart bails
    // — three breakdowns, too many points, no Chart.js — the table is the only
    // surface showing the result AND the only drill-through target left, so it
    // must be visible immediately.
    if (hasMetrics && (charted || !dims)) {
      el('rsTableToggle').hidden = false;
      el('rsTableToggle').textContent = I18N.showTable;
      el('rsTableWrap').hidden = true;
    } else {
      el('rsTableWrap').hidden = false;   // plain table reports: grid directly
    }
    writePreviewCache(dims, hasMetrics, rows);
    // Task 13: auto AI caption over the result that just rendered. Placed
    // after the `!rows.length` early return above, so an empty result never
    // fires one (nothing to caption).
    fireCaption('rsCaption', columns, rows, cur.name || cur.def.title || '', resolvedTxt,
      captionNotes(def, rows), captionLevelFields(def));
  }

  // Step 5 — refresh the library card's preview thumbnail from the result
  // that's actually on screen. Only for a SAVED report (state.current.reportId
  // set) — an unsaved ad-hoc result has no card to feed. Wrapped in try/catch:
  // a localStorage quota error (or a browser with storage disabled) must
  // never break a run.
  function writePreviewCache(dims, hasMetrics, rows) {
    var reportId = state.current && state.current.reportId;
    if (!reportId) return;
    try {
      var payload;
      if (hasMetrics && !dims && rows.length) {
        payload = { t: 'total', v: Number(rows[0][0]) || 0, ts: Date.now() };
      } else if (hasMetrics && dims && state.chartData) {
        var series = (state.chartData.datasets[0] || {}).data || [];
        payload = {
          t: state.chartData.type === 'line' ? 'line' : 'bar',
          v: series.slice(0, 16),
          ts: Date.now()
        };
      } else {
        return;
      }
      localStorage.setItem('nx.reporting.preview.' + reportId, JSON.stringify(payload));
    } catch (e) { /* quota or storage disabled — never break a run */ }
  }

  el('rsTableToggle').addEventListener('click', function () {
    var w = el('rsTableWrap');
    w.hidden = !w.hidden;
    el('rsTableToggle').textContent = w.hidden ? I18N.showTable : I18N.hideTable;
  });

  el('rsChartTools').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-type]');
    if (!btn || !state.chartData) return;
    // 'stacked' is a UI-only virtual type; don't persist it as a chartType since
    // it maps to 'bar' with stacked scales and is not a valid Chart.js type.
    if (state.current && state.current.def && btn.dataset.type !== 'stacked') {
      state.current.def.chartType = btn.dataset.type;
    }
    renderChart(btn.dataset.type);
  });

  function forecastEligible(def) {
    var cols = (def && def.columns) || [];
    return cols.length === 1 && !!cols[0].grain &&
      Array.isArray(def.metrics) && def.metrics.length > 0;
  }
  function syncForecastCtl(def, forecast, charted) {
    var btn = el('rsForecastToggle'), sel = el('rsForecastHorizon');
    if (!btn) return;
    var eligible = forecastEligible(def);
    // Mirrors Advanced's syncForecastCtl (_reporting_js.html): a saved/shared
    // definition must never persist a stale forecast block once the shape
    // (e.g. a second breakdown added, or the date grain removed) makes it
    // permanently unavailable.
    if (!eligible) delete def.forecast;
    var on = eligible && !!(def.forecast && def.forecast.enabled);
    btn.disabled = !eligible;
    btn.title = eligible ? I18N.forecastLabel : I18N.forecastNeedsShape;
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
      appendChartNote(I18N.forecastUnavailable);
    } else if (charted && on) {
      appendChartNote(I18N.forecastNote);
    }
  }
  el('rsForecastToggle').addEventListener('click', function () {
    var cur = state.current;
    if (!cur || !cur.def || this.disabled) return;
    if (cur.def.forecast && cur.def.forecast.enabled) {
      delete cur.def.forecast;
      // Off = drop the forecast block from the last result and repaint; the
      // rows are already on hand, no need to hit the server again.
      var lr = state.lastRun;
      if (lr && lr.def === cur.def) {
        var charted = (lr.hasMetrics && lr.dims) ? !!mountChart(cur.def, lr.columns, lr.rows, null) : false;
        syncForecastCtl(cur.def, null, charted);
        renderTable(lr.columns, lr.rows, null);
        return;
      }
    } else {
      var h = el('rsForecastHorizon').value;
      cur.def.forecast = { enabled: true, horizon: h === 'auto' ? 'auto' : parseInt(h, 10) };
    }
    runCurrent();
  });
  el('rsForecastHorizon').addEventListener('change', function () {
    var cur = state.current;
    if (!cur || !cur.def || !cur.def.forecast) return;
    var h = this.value;
    cur.def.forecast.horizon = h === 'auto' ? 'auto' : parseInt(h, 10);
    runCurrent();
  });

  // The rail's breakdown summary names the grain — keep it live.
  el('rsGrain').addEventListener('change', renderWizardRail);

  // ----- Colours & axes popover -----
  // Client-side only: edits def.style and re-renders the mounted chart (no
  // re-run); Save persists it with the report like chartType/forecast.
  function toggleStylePop(open) {
    var pop = el('rsStylePop'), btn = el('rsStyleToggle');
    if (!pop || !btn) return;
    pop.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.setAttribute('aria-pressed', open ? 'true' : 'false');
    btn.classList.toggle('is-selected', open);
    if (open) syncStyleCtl();
  }
  function defaultSeriesColor(d, i) {
    var single = d.datasets.length === 1 && !d.multiSeries;
    var c = single ? (document.documentElement.classList.contains('dark') ? '#818cf8' : '#312e81')
                   : d.datasets[i].borderColor;
    return /^#[0-9a-f]{6}$/i.test(c || '') ? c : '#4f46e5';
  }
  function syncStyleCtl() {
    var d = state.chartData;
    if (!d) return;
    var style = styleOf(), colors = style.colors || {};
    var multi = !!d.multiSeries;
    var circular = state.chartType === 'pie' || state.chartType === 'doughnut';
    var rightKeys = circular ? [] : rightAxisKeys(d, style);
    var html = '';
    d.datasets.forEach(function (ds, i) {
      var key = seriesKey(ds, multi);
      var onRight = rightKeys.indexOf(key) >= 0;
      html += '<div class="rs-style-row" data-key="' + esc(key) + '">' +
        '<input type="color" value="' + esc(colors[key] || defaultSeriesColor(d, i)) +
        '" aria-label="' + esc(ds.label) + '" data-testid="rs-style-color">' +
        '<span>' + esc(ds.label) + '</span>' +
        (!circular && d.datasets.length > 1
          ? '<span class="rs-axis-seg" role="group">' +
            '<button type="button" class="rs-axis-btn" data-axis="left" aria-pressed="' + (!onRight) +
            '" title="' + esc(I18N.styleLeftAxis) + '" data-testid="rs-style-axis-left">' + esc(I18N.axisShortLeft) + '</button>' +
            '<button type="button" class="rs-axis-btn" data-axis="right" aria-pressed="' + onRight +
            '" title="' + esc(I18N.styleRightAxis) + '" data-testid="rs-style-axis-right">' + esc(I18N.axisShortRight) + '</button>' +
            '</span>'
          : '') +
        '</div>';
    });
    el('rsStyleRows').innerHTML = html;
    el('rsStyleTitleColor').value = style.titleColor ||
      rgbToHex(getComputedStyle(el('rsResultTitle')).color);
  }
  // Colour inputs fire `input` continuously while dragging the picker —
  // coalesce to one chart rebuild per frame.
  var styleRaf = 0;
  function rerenderStyled() {
    if (styleRaf) return;
    styleRaf = requestAnimationFrame(function () {
      styleRaf = 0;
      if (state.chartData) renderChart(state.chartType || state.chartData.type);
      applyTitleStyle();
    });
  }
  el('rsStyleToggle').addEventListener('click', function () {
    toggleStylePop(el('rsStylePop').hidden);
  });
  el('rsStyleRows').addEventListener('input', function (e) {
    var cur = state.current, d = state.chartData;
    if (!cur || !cur.def || !d || e.target.type !== 'color') return;
    var row = e.target.closest('.rs-style-row');
    if (!row) return;
    var style = ensureStyle();
    style.colors = style.colors || {};
    style.colors[row.dataset.key] = e.target.value;
    rerenderStyled();
  });
  el('rsStyleRows').addEventListener('click', function (e) {
    var btn = e.target.closest('.rs-axis-btn');
    var cur = state.current, d = state.chartData;
    if (!btn || !cur || !cur.def || !d) return;
    var key = btn.closest('.rs-style-row').dataset.key, style = ensureStyle();
    // Materialise the defaults first so moving a default right-axis series
    // (backlog) back to the left is remembered as an explicit choice.
    var keys = rightAxisKeys(d, style).slice();
    var at = keys.indexOf(key);
    if (btn.dataset.axis === 'right' && at < 0) keys.push(key);
    if (btn.dataset.axis === 'left' && at >= 0) keys.splice(at, 1);
    style.rightAxis = keys;
    rerenderStyled();
    syncStyleCtl();
  });
  el('rsStyleTitleColor').addEventListener('input', function () {
    var cur = state.current;
    if (!cur || !cur.def) return;
    ensureStyle().titleColor = this.value;
    rerenderStyled();
  });
  el('rsStyleReset').addEventListener('click', function () {
    var cur = state.current;
    if (!cur || !cur.def) return;
    delete cur.def.style;
    rerenderStyled();
    syncStyleCtl();
  });

  el('rsShowSql').addEventListener('click', function () {
    // Console: the Query card is already visible in the side column — this
    // menu item just makes sure it's rendered and brings it into view.
    var cur = state.current;
    if (!cur || !cur.sql) return;
    var view = el('rsSqlView');
    view.hidden = false;
    // sqlDisplay = pretty SQL with the parameter literals inlined
    // server-side (display + copy only; execution stays parameterized).
    ReportingSqlFormat.render(el('rsSqlText'), ReportingSqlFormat.displayText(cur));
    view.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  el('rsSqlPeek').addEventListener('click', function () {
    // Same reveal path as the Show-query button — no duplicated panel-fill
    // logic (L9): the peek footer just delegates the click.
    el('rsShowSql').click();
  });
  el('rsSqlCopy').addEventListener('click', function () {
    var cur = state.current;
    if (!cur || !cur.sql) return;
    var text = ReportingSqlFormat.copyText(cur);
    var btn = this;
    navigator.clipboard.writeText(text).then(function () {
      var prev = btn.textContent;
      btn.textContent = I18N.copied;
      setTimeout(function () { btn.textContent = prev; }, 1200);
    }).catch(function () { /* clipboard unavailable (non-HTTPS / unfocused) */ });
  });

  // Reveal the inline rename/save-name input (the pencil, "Save as copy", and
  // Save on a not-yet-saved result all land here).
  function revealSaveNameInput(value) {
    if (!state.current) return;  // error view without a loaded report
    var nameInput = el('rsSaveName');
    nameInput.hidden = false;
    nameInput.value = value || state.current.name || state.current.def.title || '';
    nameInput.focus();
    nameInput.select();
  }

  // True once the result IS a stored report the user may write back to: an
  // owner, or a colleague holding a CanEdit share (the same pair the PUT
  // endpoint accepts).
  function canUpdateCurrent() {
    var cur = state.current;
    return !!(cur && cur.reportId && (cur.owned || cur.canEdit));
  }

  // Armed by "Save as copy" so the next save creates a row instead of writing
  // back; cleared on every render (runCurrent) and after each save.
  var saveAsCopy = false;

  // PUT when we're writing back to the open report, POST when we're making a
  // new one. Renaming is the same call with a different name -- that is what
  // stops the pencil from spawning a duplicate under the new name.
  async function persistCurrent(name) {
    var cur = state.current;
    var update = !saveAsCopy && canUpdateCurrent();
    var res = update
      ? await api('/api/reporting/reports/' + cur.reportId, {
          method: 'PUT', body: JSON.stringify({ name: name, definition: cur.def })
        })
      : await api('/api/reporting/reports', {
          method: 'POST', body: JSON.stringify({ name: name, definition: cur.def })
        });
    if (!res.ok) {
      el('rsError').textContent = (res.data && res.data.error) || I18N.couldNotSave;
      el('rsError').hidden = false;
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
    el('rsSaveName').hidden = true;
    el('rsResultTitle').textContent = name;
    el('rsCrumbName').textContent = name;
    el('rsSavedChip').hidden = !cur.reportId;
    el('rsDeleteReport').hidden = !(cur.owned && cur.reportId);
    el('rsSaveCopy').hidden = !cur.reportId;
    el('rsError').hidden = true;
    el('rsMsg').textContent = update ? I18N.savedChanges : I18N.savedToMine;
    el('rsMsg').hidden = false;
    loadLibrary();
  }

  el('rsRenamePencil').addEventListener('click', function () { revealSaveNameInput(); });

  el('rsSave').addEventListener('click', function () {
    if (!state.current) return;  // error view without a loaded report
    var nameInput = el('rsSaveName');
    if (!nameInput.hidden) {          // naming a new report, or renaming this one
      var typed = nameInput.value.trim();
      if (typed) persistCurrent(typed);
      return;
    }
    // A saved report keeps its name and takes the edit; anything else has to
    // be named first.
    if (canUpdateCurrent()) persistCurrent(state.current.name || state.current.def.title || '');
    else revealSaveNameInput();
  });

  el('rsSaveName').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); el('rsSave').click(); }
    else if (e.key === 'Escape') { this.hidden = true; saveAsCopy = false; el('rsSave').focus(); }
  });

  el('rsSaveCopy').addEventListener('click', function () {
    if (!state.current) return;
    saveAsCopy = true;
    toggleMoreMenu(false);
    revealSaveNameInput(I18N.copyOf.replace('{name}', state.current.name || state.current.def.title || ''));
  });

  // Open in Advanced. id:null for non-owned reports is LOAD-BEARING: CanEdit
  // shares mutate shared reports in place; a null id makes Advanced's Save
  // default to create-a-copy.
  el('rsAdjustWizard').addEventListener('click', adjustInWizard);

  // ⋯ overflow menu: toggle on the button, close on Escape or an outside
  // click — same idiom as the Advanced tab's process-scope dropdown
  // (rpScopeBtn/#rpScopeWrap wiring at the bottom of _reporting_js.html).
  var rsMoreBtn = el('rsMore');
  if (rsMoreBtn) {
    rsMoreBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMoreMenu(); });
    document.addEventListener('click', function (e) {
      var wrap = el('rsMoreWrap');
      if (wrap && !wrap.contains(e.target)) toggleMoreMenu(false);
    });
    el('rsMoreWrap').addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { toggleMoreMenu(false); rsMoreBtn.focus(); }
    });
  }

  el('rsDeleteReport').addEventListener('click', function () {
    var cur = state.current;
    if (!cur || !cur.reportId) return;
    deleteReport(cur.reportId, cur.name || cur.def.title);
  });

  el('rsOpenAdvanced').addEventListener('click', function () {
    var cur = state.current;
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
    if (!state.chart) return null;
    var src = el('rsChartCanvas');
    var c = document.createElement('canvas');
    c.width = src.width; c.height = src.height;
    var ctx = c.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(src, 0, 0);
    return c.toDataURL('image/png');
  }

  el('rsChartPng').addEventListener('click', function () {
    var url = chartPngDataUrl();
    if (!url) return;
    var a = document.createElement('a');
    a.href = url;
    a.download = ((state.current && state.current.name) || 'report') + '-chart.png';
    a.click();
  });

  if (EXPORT_ALLOWED) {
    el('rsExport').addEventListener('click', async function () {
      if (!state.current) return;  // error view without a loaded report
      var fmtSel = el('rsExportFormat');
      var fmt = (fmtSel && fmtSel.value === 'csv') ? 'csv' : 'xlsx';
      var body = Object.assign({}, state.current.def, { format: fmt });
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
        el('rsError').textContent = I18N.couldNotExport;
        el('rsError').hidden = false;
        return;
      }
      var blob = await res.blob();
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (state.current.name || 'report') + '.' + fmt;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  // ---------- Wizard ----------
  // Progress rail (Task 5): a fixed 4-row list mirroring the 4 step divs.
  // Rows are presentational only -- they read state.wiz + the steps' own
  // `hidden` flags, never drive the click flow (renderMeasureStep and co.
  // are untouched and remain the single source of truth for what's shown).
  var WIZ_STEPS = [
    { id: 'rsStepMeasure', label: I18N.wizMeasure },
    { id: 'rsStepScope', label: I18N.wizScope },
    { id: 'rsStepBreakdown', label: I18N.wizBreakdown },
    { id: 'rsStepTime', label: I18N.wizTime }
  ];
  var WIZ_TIME_TOKEN_LABELS = {
    this_week: I18N.thisWeek, this_month: I18N.thisMonth, last_month: I18N.lastMonth,
    this_quarter: I18N.thisQuarter, last_quarter: I18N.lastQuarter,
    last_3_months: I18N.last3Months, this_year: I18N.thisYear, last_year: I18N.lastYear
  };

  // The accordion never re-hides an earlier step once shown (only cascades
  // hidden=true onto LATER steps when an earlier answer changes), so the
  // "current" step is the deepest (highest-index) visible row -- scan from
  // the end. A source with no processes skips rsStepScope entirely, which
  // still yields the right "of 4" position (jumps straight to Breakdown).
  function wizStepIndex() {
    var i;
    for (i = WIZ_STEPS.length - 1; i >= 0; i--) {
      var stepEl = el(WIZ_STEPS[i].id);
      if (stepEl && !stepEl.hidden) return i;
    }
    return 0;
  }

  function wizTimeLabel(token) {
    return WIZ_TIME_TOKEN_LABELS[token] || token;
  }

  // One short summary string per WIZ_STEPS row, in order, from the exact
  // fields the step renderers themselves read/write on state.wiz. Blank
  // until that part of the state is meaningful (no source picked yet, or
  // this source has no processes to scope).
  function wizSummaries() {
    var w = state.wiz || {};
    var out = ['', '', '', ''];
    if ((w.measures || []).length) {
      out[0] = w.measures.map(function (m) { return m.label; }).join(' + ');
    }
    var allProcs = (w.source && w.source.processes) || [];
    if (allProcs.length) {
      var chosen = (w.scopeProcs || []).length || allProcs.length;
      out[1] = (chosen === allProcs.length) ? I18N.allProcesses
        : I18N.wizScopeCount.replace('{n}', chosen).replace('{m}', allProcs.length);
    }
    if (!allProcs.length && w.fieldScope) {
      var n = w.fieldScope.picked.length, m = w.fieldScope.values.length;
      out[1] = n === m ? I18N.allProcesses
        : I18N.wizScopeCount.replace('{n}', n).replace('{m}', m);
    }
    if (w.source) {
      if ((w.breakdowns || []).length) {
        var grainSel = el('rsGrain');
        var grainTxt = grainSel ? grainSel.options[grainSel.selectedIndex].text : '';
        out[2] = w.breakdowns.map(function (b) {
          if (!b.field) return I18N.justTotal;
          return b.kind === 'date' ? (b.field.label + ' (' + grainTxt + ')') : b.field.label;
        }).join(', ');
      } else {
        out[2] = I18N.justTotal;
      }
      if (Array.isArray(w.range)) out[3] = I18N.custom;
      else if (w.range && w.range.token) out[3] = wizTimeLabel(w.range.token);
      else out[3] = I18N.allTime;
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
    el('rsWizardStepNo').textContent = I18N.stepNof4.replace('{n}', idx + 1);
    var sums = wizSummaries();
    var html = '';
    WIZ_STEPS.forEach(function (step, i) {
      var cls = i < idx ? 'is-done' : (i === idx ? 'is-active' : '');
      var dot = i < idx ? '<i class="fas fa-check" aria-hidden="true"></i>' : String(i + 1);
      html += '<span class="rs-rail-step ' + cls + '">'
        + '<span class="rs-rail-dot">' + dot + '</span>'
        + '<span class="rs-rail-title">' + esc(step.label) + '</span></span>';
      if (i < WIZ_STEPS.length - 1) html += '<span class="rs-rail-line"></span>';
    });
    el('rsWizardRail').innerHTML = html;
    var sm = el('rsWizSummary');
    if (sm) {
      sm.innerHTML = WIZ_STEPS.map(function (step, i) {
        var v = (i <= idx && sums[i]) ? sums[i] : '';
        return '<div class="rs-wizsum-row"><span class="rs-wizsum-k">' + esc(step.label) + '</span>'
          + '<span class="rs-wizsum-v' + (v ? '' : ' is-empty') + '">' + esc(v || '—') + '</span></div>';
      }).join('');
    }
  }

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

  async function loadSourcesCatalog() {
    if (state.sources) return state.sources;
    var list = null;
    try { list = await ReportingCatalog.sources(); } catch (e) { list = null; }
    state.sources = Array.isArray(list) ? list : [];
    return state.sources;
  }

  // Warms the two catalogs the shared builders read through state
  // (metricLabelsFor, applyLatestTotal, fieldMetaFor). Idempotent -- both
  // loaders short-circuit once filled. Exposed for the dashboard's
  // whole-report card, which renders while the Simple result view is idle.
  async function ensureCatalogs() {
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
  }

  async function startWizard() {
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
    state.wiz = { measures: [], source: null, breakdowns: [],
                  scopeProcs: [], range: null, dateField: null, _fp: null,
                  fieldScope: null };
    setView('wizard');
    el('rsStepScope').hidden = true;
    el('rsStepBreakdown').hidden = true;
    el('rsStepTime').hidden = true;
    el('rsWizardRun').hidden = true;
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
    var w = state.wiz;
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
    el('rsStepScope').hidden = true;
    el('rsStepBreakdown').hidden = true;
    el('rsStepTime').hidden = true;
    el('rsWizardRun').hidden = true;
    renderMeasureStep();
  }

  function renderMeasureStep() {
    var list = el('rsMeasureList');
    list.innerHTML = '';
    var w = state.wiz;
    if (!Array.isArray(w.measures)) w.measures = [];
    var bySource = state.metricsBySource || {};
    var visible = Object.keys(bySource).filter(function (sid) {
      return (state.sources || []).some(function (s) { return s.id === sid; });
    });
    var multi = visible.length > 1;
    visible.forEach(function (sid) {
      var src = state.sources.find(function (s) { return s.id === sid; });
      (bySource[sid] || []).forEach(function (m) {
        // Sources without metrics never appear; admins grow the wizard's
        // reach by adding rows in the metrics registry, zero code change.
        var srcProcs = src.processes || [];
        var fld = m.baseField
          ? (src.fields || []).find(function (f) { return f.field === m.baseField; })
          : null;
        // A metric whose base field no allowed process provides can never run
        // for this user (resolve_metrics 400s) — don't offer it.
        if (m.baseField && !fld) return;
        var label = multi ? (m.label + ' · ' + src.label) : m.label;
        var btn = choiceBtn(label, function () {
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
          btn.title = I18N.measureCoverage.replace('{n}', fld.processes.length)
            .replace('{m}', srcProcs.length) + '\n' + fld.processes.join('\n');
        }
        list.appendChild(btn);
      });
    });
    if (!list.children.length) {
      list.innerHTML = '<p class="reporting-simple-empty">' + esc(I18N.noMeasures) + '</p>';
    }
    el('rsMeasureNext').hidden = !w.measures.length;
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
    var w = state.wiz;
    var procs = w.source.processes || [];
    var step = el('rsStepScope');
    var pf = processFieldFor(w.source);
    if (!procs.length && !pf) { step.hidden = true; renderBreakdownStep(); return; }
    if (!procs.length && pf) { renderFieldScopeStep(step, pf); return; }
    step.hidden = false;
    el('rsStepBreakdown').hidden = true;
    el('rsStepTime').hidden = true;
    el('rsWizardRun').hidden = true;
    var box = el('rsScopeList');
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
        if (!el('rsStepBreakdown').hidden) renderBreakdownStep();
      });
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + p));
      box.appendChild(lbl);
    });
    if (!prior.length) w.scopeProcs = procs.slice();
    renderWizardRail();
  }

  async function renderFieldScopeStep(step, pf) {
    var w = state.wiz;
    step.hidden = false;
    el('rsStepBreakdown').hidden = true;
    el('rsStepTime').hidden = true;
    el('rsWizardRun').hidden = true;
    var box = el('rsScopeList');
    box.innerHTML = '<p class="reporting-simple-hint">' + esc(I18N.loadingValues) + '</p>';
    renderWizardRail();
    var res = await api('/api/reporting/field_values', {
      method: 'POST',
      body: JSON.stringify({ source: w.source.id, field: pf.field })
    });
    if (state.view !== 'wizard' || el('rsStepScope').hidden) {
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
    el('rsStepBreakdown').hidden = false;
    el('rsStepTime').hidden = true;
    el('rsWizardRun').hidden = true;
    var w = state.wiz;
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
      var chips = el('rsBreakdownList').querySelectorAll('button[data-bd-kind]');
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
      el('rsGrainWrap').hidden = !sourceHasDates;
      el('rsGrain').disabled = !hasDate;
      el('rsGrainWrap').title = hasDate ? '' : I18N.grainNeedsDate;
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
      btn.title = I18N.chipCoverage.replace('{n}', cov.length).replace('{m}', scopeSel().length)
        + '\n' + cov.join('\n');
    }

    // Task 6: "{n} of 3 picked" footer counter, breakdown step only (the
    // footer itself is shared across all four steps -- visibility is a pure
    // CSS :has() shim keyed on #rsStepBreakdown[hidden], see reporting.css).
    function updatePickedCount() {
      el('rsPickedCount').textContent = I18N.pickedCount.replace('{n}', String(w.breakdowns.length));
    }

    function groupLabel(text) {
      var l = document.createElement('div');
      l.className = 'rs-choice-group-label';
      l.textContent = text;
      return l;
    }

    // The chip list is re-rendered whenever the process scope changes: a chip
    // whose field no selected process provides is hidden and its selection
    // pruned (the query would only produce NULL groups for it).
    function renderChipList() {
      var list = el('rsBreakdownList');
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

      if (dateFields.length) list.appendChild(groupLabel(I18N.groupTime));
      dateFields.forEach(function (f) {
        var bd = { kind: 'date', field: f };
        var btn = choiceBtn(I18N.overTime + ' (' + f.label + ')', function () {
          toggleBreakdown(bd);
        }, isSelected(bd));
        btn.dataset.bdKind = 'date';
        btn.dataset.bdField = f.field;
        applyCoverageBadge(btn, f);
        list.appendChild(btn);
      });
      // No cap: everything the Advanced tab offers is available here — the
      // coverage sort keeps rarely-provided fields at the bottom, and the
      // hide-list still filters the noise.
      if (catFields.length) list.appendChild(groupLabel(I18N.groupFields));
      catFields.forEach(function (f) {
        var bd = { kind: 'category', field: f };
        var btn = choiceBtn(f.label, function () {
          toggleBreakdown(bd);
        }, isSelected(bd));
        btn.dataset.bdKind = 'category';
        btn.dataset.bdField = f.field;
        applyCoverageBadge(btn, f);
        list.appendChild(btn);
      });
      list.appendChild(groupLabel(I18N.groupOr));
      var noneBtn = choiceBtn(I18N.justTotal, function () {
        toggleBreakdown({ kind: 'none' });
      }, w.breakdowns.length === 0);
      noneBtn.dataset.bdKind = 'none';
      noneBtn.classList.add('rs-choice-none');
      list.appendChild(noneBtn);
    }

    renderChipList();
    refreshChips();

    // Wire Continue button
    var nextBtn = el('rsBreakdownNext');
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
    if (!state.wiz._fp && window.flatpickr) {
      state.wiz._fp = flatpickr(el('rsTimeRange'), {
        mode: 'range', dateFormat: 'Y-m-d',
        onChange: function (picked) {
          if (picked.length === 2) {
            state.wiz.range = [isoDate(picked[0]), isoDate(picked[1])];
          }
        }
      });
    }
    return state.wiz._fp;
  }

  function renderTimeStep() {
    el('rsStepTime').hidden = false;
    el('rsWizardRun').hidden = false;
    el('rsTimeCustom').hidden = !Array.isArray(state.wiz.range);
    // A restored definition's literal range (adjustInWizard) must be visible
    // in the picker, not just applied silently on Show result — seed it here
    // (display = state, no change event) rather than waiting for the user to
    // click Custom themselves.
    if (Array.isArray(state.wiz.range) && window.flatpickr) {
      ensureRangePicker();
      if (state.wiz._fp) state.wiz._fp.setDate(state.wiz.range, false);
    }
    var fields = state.wiz.source.fields || [];
    var anchoredTime = !!(state.wiz.measures.length && state.wiz.measures[0].anchor);
    var dateFields = fields.filter(function (f) { return f.grainable; })
      .filter(function (f) {
        return anchoredTime ? f.field === 'activity_date' : f.field !== 'activity_date';
      });
    var list = el('rsTimeList');
    // Skipped when the source exposes no date field.
    if (!dateFields.length) {
      list.innerHTML = '<p class="reporting-simple-empty">' + esc(I18N.noDateField) + '</p>';
      el('rsTimeFieldWrap').hidden = true;
      state.wiz.range = null;
      el('rsAllTimeHint').hidden = true;
      renderWizardRail();
      return;
    }
    // Date field defaults to import_date, switchable to export_date.
    var sel = el('rsTimeField');
    sel.innerHTML = '';
    dateFields.forEach(function (f) {
      var o = document.createElement('option');
      o.value = f.field; o.textContent = f.label;
      sel.appendChild(o);
    });
    if (state.wiz.dateField
        && dateFields.some(function (f) { return f.field === state.wiz.dateField; })) {
      sel.value = state.wiz.dateField;
    } else if (dateFields.some(function (f) { return f.field === 'import_date'; })) {
      sel.value = 'import_date';
    }
    el('rsTimeFieldWrap').hidden = dateFields.length < 2;
    state.wiz.dateField = sel.value;
    sel.onchange = function () { state.wiz.dateField = sel.value; };

    list.innerHTML = '';
    [['this_week', I18N.thisWeek], ['this_month', I18N.thisMonth],
     ['last_month', I18N.lastMonth], ['this_quarter', I18N.thisQuarter],
     ['last_quarter', I18N.lastQuarter], ['last_3_months', I18N.last3Months],
     ['this_year', I18N.thisYear], ['last_year', I18N.lastYear],
     ['all_time', I18N.allTime], ['custom', I18N.custom]].forEach(function (p) {
      list.appendChild(choiceBtn(p[1], function () {
        el('rsTimeCustom').hidden = p[0] !== 'custom';
        if (p[0] === 'custom') {
          ensureRangePicker();
          // Re-selecting Custom keeps whatever range the picker still shows
          // (display and state must agree); empty picker = no filter yet.
          var fp = state.wiz._fp;
          state.wiz.range = (fp && fp.selectedDates && fp.selectedDates.length === 2)
            ? [isoDate(fp.selectedDates[0]), isoDate(fp.selectedDates[1])]
            : null;
        } else {
          // Preset = relative-date token: resolved server-side on every run.
          // all_time = no filter.
          state.wiz.range = p[0] === 'all_time' ? null : { token: p[0] };
        }
        el('rsAllTimeHint').hidden = state.wiz.range !== null;
        renderWizardRail();
      }, state.wiz.range === p[0] ||
         (state.wiz.range && state.wiz.range.token === p[0]) ||
         (p[0] === 'custom' && Array.isArray(state.wiz.range)) ||
         (p[0] === 'all_time' && state.wiz.range === null)));
    });
    // Only default to all-time if no prior choice is being restored.
    if (!state.wiz.range) state.wiz.range = null;
    el('rsAllTimeHint').hidden = state.wiz.range !== null;
    renderWizardRail();
  }

  // Wizard invariants (validator-enforced server-side): sort fields are among
  // the selected columns or metric codes; grain only on grainable fields;
  // metric codes from the registry; the between filter always targets the
  // RAW date field (the Spec-1 contract), never the bucketed expression.
  function wizardDefinition() {
    var w = state.wiz;
    var columns = [], sort = [], filters = [];
    var title = w.measures.map(function (m) { return m.label; }).join(' + ');
    var bds = (w.breakdowns || []).slice();
    // date first: it becomes the chart axis (X)
    bds.sort(function (a, b) {
      return (a.kind === 'date' ? 0 : 1) - (b.kind === 'date' ? 0 : 1);
    });
    var grain = el('rsGrain').value || 'month';
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
        var per = I18N.per + ' ' + el('rsGrain').options[el('rsGrain').selectedIndex].text.toLowerCase();
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
        title += ' ' + I18N.by + ' ' + titleParts.join(' / ');
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
    var src = (state.sources || []).find(function (s) { return s.id === def.source; });
    var mlist = (state.metricsBySource || {})[def.source] || [];
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

  async function adjustInWizard() {
    var cur = state.current;
    if (!cur) return;
    if (cur.builtBy === 'wizard' && state.wiz && (state.wiz.measures || []).length) {
      reopenWizard(); return;
    }
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
    var mapped = wizardStateFromDefinition(cur.def);
    if (!mapped) return;
    state.wiz = mapped.wiz;
    if (mapped.grain) el('rsGrain').value = mapped.grain;
    reopenWizard();
  }

  async function reopenWizard() {
    if (!state.wiz || !(state.wiz.measures || []).length) { startWizard(); return; }
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
    setView('wizard');
    renderMeasureStep();
    renderScopeStep();
    renderBreakdownStep();
    renderTimeStep();
  }

  el('rsNewReport').addEventListener('click', startWizard);
  el('rsNewDashboard').addEventListener('click', function () {
    setView('dashboard');
    window.ReportingDashboard.openNew();
  });
  el('rsMeasureNext').addEventListener('click', function () { renderScopeStep(); });
  el('rsScopeNext').addEventListener('click', function () { renderBreakdownStep(); });
  // Back steps one wizard step backwards (picks are preserved in state.wiz);
  // only from step 1 does it exit. The ✕ stays the explicit exit at any point.
  el('rsWizardBack').addEventListener('click', function () {
    if (!el('rsStepTime').hidden) {           // time -> breakdown
      el('rsStepTime').hidden = true;
      el('rsWizardRun').hidden = true;
      renderWizardRail();
      return;
    }
    if (!el('rsStepBreakdown').hidden) {      // breakdown -> scope (or measure)
      el('rsStepBreakdown').hidden = true;
      if (!el('rsStepScope').hidden) { renderWizardRail(); return; }  // scope step stays visible above
      // no scope step for this source: renderScopeStep would have skipped it
      var procs = (state.wiz && state.wiz.source && state.wiz.source.processes) || [];
      if (procs.length) el('rsStepScope').hidden = false;
      renderWizardRail();
      return;
    }
    if (!el('rsStepScope').hidden) {          // scope -> measure
      el('rsStepScope').hidden = true;
      renderWizardRail();
      return;
    }
    setView('library');                       // measure -> out
  });
  el('rsWizardRun').addEventListener('click', function () {
    if (!state.wiz || !(state.wiz.measures || []).length) return;
    var def = wizardDefinition();
    state.current = { def: def, name: def.title, reportId: null,
                      owned: true, canEdit: true, fromWizard: true,
                      builtBy: 'wizard', origin: 'wizard' };
    runCurrent();
  });

  // (The old hero Ask-AI bar is gone — Console intent #1. The AI entry point
  // is the top-bar "AI chat" button; window.ReportingChat owns that panel.)

  // ---------- init ----------
  function initOnce() {
    if (state.loaded) return;
    state.loaded = true;
    loadMetricsCatalog();
    loadLibrary();
    syncLayoutToggle();
  }

  el('rsSearch').addEventListener('input', renderLibrary);
  el('rsSort').addEventListener('change', function () {
    state.sort = this.value === 'name' ? 'name' : 'updated';
    renderLibrary();
  });
  function syncLayoutToggle() {
    el('rsLayout2').classList.toggle('is-active', state.layout === '2');
    el('rsLayout4').classList.toggle('is-active', state.layout === '4');
  }
  function setLayout(n) {
    state.layout = n;
    try { localStorage.setItem('nx.reporting.layout', n); } catch (e) {}
    syncLayoutToggle();
    renderLibrary();
  }
  el('rsLayout2').addEventListener('click', function () { setLayout('2'); });
  el('rsLayout4').addEventListener('click', function () { setLayout('4'); });
  function exitToLibrary() { setView('library'); loadLibrary(); }

  // Back on a result returns to the result's origin: a wizard-built (or
  // wizard-reopened) result goes back into the wizard adjustment; a
  // library-opened or Ask-AI result goes back to the library. The X is
  // always the explicit way out to the library, regardless of origin.
  el('rsBack').addEventListener('click', function () {
    var cur = state.current;
    if (cur && cur.origin === 'wizard') { adjustInWizard(); return; }
    exitToLibrary();
  });
  el('rsExit').addEventListener('click', exitToLibrary);
  el('rsWizardClose').addEventListener('click', exitToLibrary);
  el('rsWizardClose2').addEventListener('click', exitToLibrary);

  // The dashboard builder module is self-contained and never calls setView
  // itself -- it announces intent via a custom event instead of reaching
  // into this module's functions (D3).
  document.addEventListener('rs:dashboard-closed', exitToLibrary);

  el('rsRunAgain').addEventListener('click', function () {
    if (state.current) runCurrent();
  });

  // Result builders shared with the dashboard's whole-report card
  // (_reporting_dashboard_js.html renderReportCard). Everything here is
  // DOM-free except ensureCatalogs (network) and chartConfigFor's one read
  // of document.documentElement.classList for dark mode; none of it touches
  // the Simple pane's own elements, so a card can call them while #rsResult
  // is hidden.
  window.ReportingSimple = {
    openDefinition: openDefinition,
    navTo: navTo,
    ensureCatalogs: ensureCatalogs,
    fmtNumber: fmtNumber,
    zeroFillDateBuckets: zeroFillDateBuckets,
    kpiBandHtml: kpiBandHtml,
    buildChartData: buildChartData,
    chartConfigFor: chartConfigFor,
    tableHtml: tableHtml
  };

  document.addEventListener('rp:tabshown', function (e) {
    if (e.detail.tab === 'simple') initOnce();
  });
  if (window.ReportingTabs && window.ReportingTabs.current() === 'simple') initOnce();
}());
