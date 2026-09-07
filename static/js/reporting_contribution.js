/* Contribution analysis drawer ("Why did it move?"). Reuses the drill shell
   (#rdPanel etc., owned by templates/reporting.html) and hands row clicks to
   ReportingDrill.open. Behaviour only — strings come from the shim
   templates/js/_reporting_contribution_js.html (#191). */
window.ReportingContribution = (function () {
  'use strict';
  var I18N = window.NX_I18N_REPORTING_CONTRIBUTION || {};
  var el = window.NX.el, esc = window.NX.esc;
  var fmt = function (n) { return (window.RS && RS.fmtNumber) ? RS.fmtNumber(n) : String(n); };
  var current = null;      // {definition, fields, data} of the open drawer

  function pct(v) { return (v > 0 ? '+' : '') + Math.round(v * 100) + '%'; }
  function dir(delta) { return delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'; }
  function arrow(delta) { return delta > 0 ? '↑' : delta < 0 ? '↓' : '—'; }

  function headerHtml(d) {
    var delta = d.currentTotal - d.priorTotal;
    var rel = d.priorTotal ? ' (' + pct(delta / d.priorTotal) + ')' : '';
    return '<p class="reporting-contrib-head" data-testid="contrib-head">' +
      esc(d.metricLabel) + ' · ' + esc(fmt(d.priorTotal)) + ' → ' + esc(fmt(d.currentTotal)) +
      ' <span class="rp-delta rp-delta--' + dir(delta) + '">' + arrow(delta) + ' ' +
      esc(fmt(Math.abs(delta))) + esc(rel) + '</span>' +
      ' · ' + esc(I18N.prior) + ' ' + esc(d.priorStart) + ' – ' + esc(d.priorEnd) + '</p>';
  }

  function tabHtml(dim, i, active) {
    return '<button type="button" role="tab" class="reporting-contrib-tab' +
      (active ? ' is-active' : '') + '" data-tab="' + i + '"' +
      ' aria-selected="' + (active ? 'true' : 'false') + '" data-testid="contrib-tab">' +
      esc(dim.label) + '</button>';
  }

  function rowsHtml(dim, i, active, isRatio) {
    var max = 0;
    dim.rows.forEach(function (r) { max = Math.max(max, Math.abs(r.delta)); });
    return '<div class="reporting-contrib-rows" data-panel="' + i + '"' + (active ? '' : ' hidden') +
      ' data-testid="contrib-rows">' +
      dim.rows.map(function (r, ri) {
        var other = r.value === '(other)';
        var w = max ? Math.round(Math.abs(r.delta) / max * 100) : 0;
        var label = r.value === '(empty)' ? ReportingDrill.I18N.nullLabel
          : other ? I18N.other : r.value;
        return '<div class="reporting-contrib-row' + (other ? ' is-other' : '') + '"' +
          (other ? '' : ' tabindex="0" data-row="' + ri + '"') + ' data-testid="contrib-row">' +
          '<span class="reporting-contrib-label" title="' + esc(label) + '">' + esc(label) + '</span>' +
          '<span class="reporting-contrib-bar rp-delta--' + dir(r.delta) + '">' +
            (other ? '' : '<i style="width:' + w + '%"></i>') + '</span>' +
          '<span class="reporting-contrib-nums">' +
            esc(fmt(r.prior)) + ' → ' + esc(fmt(r.current)) +
            ' <b class="rp-delta rp-delta--' + dir(r.delta) + '">' + arrow(r.delta) + ' ' +
            esc(fmt(Math.abs(r.delta))) + '</b>' +
            (!isRatio && r.share != null ? ' <small>' + esc(pct(r.share)) + '</small>' : '') +
          '</span></div>';
      }).join('') + '</div>';
  }

  function render(d) {
    var body = el('rdBody');
    if (!d.dimensions.length) {
      body.innerHTML = headerHtml(d) + '<p class="reporting-drill-note">' + esc(I18N.noDimensions) + '</p>';
      return;
    }
    body.innerHTML = headerHtml(d) +
      '<div class="reporting-contrib-tabs" role="tablist">' +
        d.dimensions.map(function (dim, i) { return tabHtml(dim, i, i === 0); }).join('') +
      '</div>' +
      d.dimensions.map(function (dim, i) { return rowsHtml(dim, i, i === 0, d.isRatio); }).join('');
    var note = [I18N.drillHint];
    if (d.skipped && d.skipped.length) note.push(I18N.notShown.replace('{fields}', d.skipped.join(', ')));
    el('rdNote').textContent = note.join(' ');
  }

  function onBodyClick(e) {
    if (!current) return;
    var tab = e.target.closest('[data-tab]');
    if (tab) {
      var idx = tab.getAttribute('data-tab');
      el('rdBody').querySelectorAll('[data-tab]').forEach(function (t) {
        var on = t.getAttribute('data-tab') === idx;
        t.classList.toggle('is-active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      el('rdBody').querySelectorAll('[data-panel]').forEach(function (p) {
        p.hidden = p.getAttribute('data-panel') !== idx;
      });
      return;
    }
    var row = e.target.closest('[data-row]');
    if (!row) return;
    drill(row);
  }

  // Called whenever this module gives up the shared #rdPanel shell without
  // drilling: #rdClose, backdrop click, Escape. Must also run at the start
  // of drill()'s hand-over -- ReportingDrill.open() never un-hides these
  // (it doesn't know they exist), so open()'s hide-them-here must always be
  // paired with exactly one of these paths un-hiding them again, or every
  // later normal drill (opened directly from a chart/table) is left with
  // invisible export buttons for the rest of the page session.
  function release() {
    current = null;
    if (el('rdExportCsv')) el('rdExportCsv').hidden = false;
    if (el('rdExportXlsx')) el('rdExportXlsx').hidden = false;
  }

  function onBodyKey(e) {
    if (!current) return;
    if (e.key !== 'Enter') return;
    var row = e.target.closest('[data-row]');
    if (row) drill(row);
  }

  function drill(rowEl) {
    var panel = rowEl.closest('[data-panel]');
    var dim = current.data.dimensions[Number(panel.getAttribute('data-panel'))];
    var r = dim.rows[Number(rowEl.getAttribute('data-row'))];
    var value = r.value === '(empty)' ? null : r.value;
    var def = current.definition, fields = current.fields;
    var clicked = [{ field: dim.field, grain: null, value: value }];
    // The server picks dimensions by type=="string" without checking
    // filterable, so a clicked field can be absent from the source's field
    // list (or explicitly unfilterable). Check before handing the shell
    // over: ReportingDrill.open would toast and bail internally, but by
    // then #rdBody would already show contribution content with no owner
    // left to react to further clicks (onBodyClick/onBodyKey both require
    // `current`) -- a drawer that looks alive but is inert. Keep `current`
    // (and the export buttons hidden) so the contribution drawer stays usable.
    if (!ReportingDrill.buildDrillDefinition(def, fields, clicked)) {
      window.NX.toast(ReportingDrill.I18N.cannotFilter, true);
      return;
    }
    release();                                // the drill now owns the shell
    ReportingDrill.open({
      definition: def, fields: fields,
      clicked: clicked,
      header: dim.label + ' = ' + (value === null ? ReportingDrill.I18N.nullLabel : String(value).slice(0, 60))
    });
  }

  /* definition: the Simple definition whose KPI band showed the chip (tokens
     intact). fields: that source's catalog field list. opts.header: title. */
  function open(definition, fields, opts) {
    opts = opts || {};
    current = { definition: definition, fields: fields, data: null };
    var token = current;
    el('rdTitle').textContent = opts.header || I18N.title;
    el('rdSubtitle').textContent = I18N.subtitle;
    el('rdChips').innerHTML = '';
    el('rdNote').textContent = '';
    // #rdExportCsv/#rdExportXlsx are drill-only actions -- dead here.
    // Re-shown right before handing the shell over to ReportingDrill.open.
    if (el('rdExportCsv')) el('rdExportCsv').hidden = true;
    if (el('rdExportXlsx')) el('rdExportXlsx').hidden = true;
    // A leftover callout from a previous drill (ReportingDrill.ensureCallout
    // inserts it lazily and never removes it) doesn't belong in a
    // contribution drawer; the drill re-inserts its own on its next open().
    var callout = el('rdCallout');
    if (callout && callout.parentNode) callout.parentNode.removeChild(callout);
    el('rdBody').innerHTML =
      '<div class="reporting-ai-loading"><span class="reporting-ai-dots" aria-hidden="true">' +
      '<i></i><i></i><i></i></span><span role="status">' + esc(I18N.loading) + '</span></div>';
    el('rdPanel').hidden = false;
    el('rdBackdrop').hidden = false;
    // NX.apiSafe resolves a leading-slash URL through API_PREFIX itself and
    // sets Content-Type + X-CSRFToken (see resolveUrl in nx_core.js).
    window.NX.apiSafe('/api/reporting/contribution', {
      method: 'POST', body: JSON.stringify(definition)
    }).then(function (r) {
      // Bail if superseded by a later open() OR if the shared shell was
      // closed/handed to another owner (backdrop click, Escape, or a drill
      // hand-over) in the meantime -- those clear `current` and/or hide
      // #rdPanel without going through this module's own close path.
      if (current !== token || el('rdPanel').hidden) return;
      if (!r.ok) {
        el('rdBody').innerHTML = '<p class="reporting-drill-note" data-testid="contrib-error">' +
          esc((r.data && r.data.error) || I18N.loadError) + '</p>';
        return;
      }
      current.data = r.data;
      render(r.data);
    });
  }

  el('rdBody').addEventListener('click', onBodyClick);
  el('rdBody').addEventListener('keydown', onBodyKey);
  el('rdClose').addEventListener('click', release);
  // ReportingDrill.wire() owns #rdBackdrop's click and document Escape --
  // both close #rdPanel and null the drill's own `current`, but know nothing
  // about this module's `current`. Mirror both here so a late contribution
  // response (guarded above by el('rdPanel').hidden) never fires against a
  // shell the user already dismissed, and so the export buttons don't stay
  // hidden after a non-drill close.
  el('rdBackdrop').addEventListener('click', release);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') release();
  });

  return { open: open };
})();
