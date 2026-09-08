// Simple tab: chart annotations (#284). Loads the open report's annotations,
// feeds chartConfigFor a bucket->texts map (marker dataset), renders the list
// under the chart and owns the add popover. Owner-only chrome; viewers get
// the markers and a read-only list. Loads AFTER reporting_simple_chart.js.
(function () {
  'use strict';
  var RS = window.RS = window.RS || {};
  RS.el = RS.el || window.NX.el;
  RS.api = RS.api || window.NX.apiSafe;
  RS.esc = RS.esc || window.NX.esc;

  var A = RS.annotations = { list: [], reportId: null };
  var popIndex = null;   // labels[] index the popover is for, or null (select)

  function canEdit() {
    var cur = RS.state && RS.state.current;
    return !!(cur && cur.reportId && cur.owned);
  }

  function chartBuckets() {
    var cd = RS.state && RS.state.chartData;
    if (!cd || !cd.labels) return [];
    var n = cd.forecastStart == null ? cd.labels.length : cd.forecastStart;
    return cd.labels.slice(0, n);
  }

  A.byBucket = function () {
    var m = {};
    A.list.forEach(function (a) { (m[a.bucket] = m[a.bucket] || []).push(a.text); });
    return m;
  };

  A.load = async function (reportId) {
    A.reportId = reportId || null;
    A.list = [];
    if (reportId) {
      var res = await RS.api('/api/reporting/reports/' + reportId + '/annotations');
      if (A.reportId !== reportId) return;   // user opened another report meanwhile
      // 403/404 (unshared meanwhile) reads as "no annotations" -- no toast.
      if (res.ok && Array.isArray(res.data)) A.list = res.data;
    }
    A.refresh();
  };

  // Re-draw the chart (marker dataset) and the list from A.list.
  A.refresh = function () {
    if (RS.state.chartData && RS.state.chart) RS.renderChart(RS.state.chartType || RS.state.chartData.type);
    A.renderList();
  };

  A.renderList = function () {
    var box = RS.el('rsAnnotations'), ul = RS.el('rsAnnotationsList');
    var editable = canEdit();
    var ct = RS.state.chartType || (RS.state.chartData && RS.state.chartData.type);
    var circular = ct === 'pie' || ct === 'doughnut';
    RS.el('rsAnnotationAdd').hidden = !editable || circular;
    ul.innerHTML = A.list.map(function (a) {
      return '<li data-testid="rs-annotation-row" data-id="' + a.id + '">' +
        '<span class="rs-annotation-bucket">' + RS.esc(a.bucket) + '</span>' +
        '<span class="rs-annotation-text">' + RS.esc(a.text) + '</span>' +
        '<span class="rs-annotation-author">' + RS.esc(a.author || '') + '</span>' +
        (editable ? '<button type="button" class="rs-annotation-delete" data-id="' + a.id +
                    '" title="' + RS.esc(RS.I18N.annotationDelete) + '" aria-label="' +
                    RS.esc(RS.I18N.annotationDelete) + '" data-testid="rs-annotation-delete">×</button>' : '') +
        '</li>';
    }).join('');
    // Hidden unless there is something to show: rows, or the owner's Add button.
    box.hidden = !(A.list.length || (editable && !circular && chartBuckets().length));
  };

  // ----- popover -----
  A.openPopover = function (index, anchor) {
    var pop = RS.el('rsAnnotationPop');
    var sel = RS.el('rsAnnotationBucketSelect');
    var buckets = chartBuckets();
    if (!canEdit() || !buckets.length) return;
    popIndex = (index != null && index < buckets.length) ? index : null;
    RS.el('rsAnnotationBucket').textContent = popIndex != null ? buckets[popIndex] : RS.I18N.annotationAdd;
    sel.hidden = popIndex != null;
    if (popIndex == null) {
      sel.innerHTML = buckets.map(function (b) { return '<option value="' + RS.esc(b) + '">' + RS.esc(b) + '</option>'; }).join('');
    }
    RS.el('rsAnnotationText').value = '';
    pop.hidden = false;
    // Anchor near the click inside the chart card (position:relative), else
    // under the list header.
    var card = RS.el('rsChartCard').getBoundingClientRect();
    if (anchor) {
      pop.style.left = Math.max(8, Math.min(anchor.x - card.left, card.width - 330)) + 'px';
      pop.style.top = (anchor.y - card.top + 8) + 'px';
    } else {
      var head = RS.el('rsAnnotations').getBoundingClientRect();
      pop.style.left = '8px';
      pop.style.top = (head.top - card.top + 24) + 'px';
    }
    RS.el('rsAnnotationText').focus();
  };

  A.closePopover = function () { RS.el('rsAnnotationPop').hidden = true; popIndex = null; };

  // Chart click-handler hook (chartConfigFor opts.onAnnotate): Alt+click on a
  // bucket, or a click on an existing marker.
  A.onChartAnnotate = function (index, dsIndex) {
    if (!canEdit()) { if (dsIndex != null) RS.drillFromChart(index, dsIndex); return; }
    var c = RS.state.chart, pt = null;
    if (c && c.canvas) {
      var r = c.canvas.getBoundingClientRect();
      var x = c.scales && c.scales.x ? c.scales.x.getPixelForValue(index) : r.width / 2;
      pt = { x: r.left + x, y: r.top + r.height / 2 };
    }
    A.openPopover(index, pt);
  };

  async function save() {
    var buckets = chartBuckets();
    var bucket = popIndex != null ? buckets[popIndex] : RS.el('rsAnnotationBucketSelect').value;
    var text = RS.el('rsAnnotationText').value.trim();
    if (!bucket || !text || !A.reportId) return;
    var res = await RS.api('/api/reporting/reports/' + A.reportId + '/annotations', {
      method: 'POST', body: JSON.stringify({ bucket: bucket, text: text })
    });
    if (!res.ok) {
      window.NX.toast((res.data && res.data.error) || RS.I18N.annotationCouldNotSave, 'error');
      return;
    }
    A.closePopover();
    await A.load(A.reportId);
  }

  async function remove(id) {
    if (!A.reportId) return;
    var res = await RS.api('/api/reporting/reports/' + A.reportId + '/annotations/' + id, { method: 'DELETE' });
    if (!res.ok) {
      window.NX.toast((res.data && res.data.error) || RS.I18N.annotationCouldNotDelete, 'error');
      return;
    }
    A.list = A.list.filter(function (a) { return String(a.id) !== String(id); });
    A.refresh();
  }

  // ----- wiring -----
  RS.el('rsAnnotationAdd').addEventListener('click', function () { A.openPopover(null, null); });
  RS.el('rsAnnotationSave').addEventListener('click', save);
  RS.el('rsAnnotationCancel').addEventListener('click', A.closePopover);
  RS.el('rsAnnotationText').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); save(); }
    if (e.key === 'Escape') { e.preventDefault(); A.closePopover(); }
  });
  RS.el('rsAnnotationsList').addEventListener('click', function (e) {
    var btn = e.target.closest('.rs-annotation-delete');
    if (btn) remove(btn.dataset.id);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !RS.el('rsAnnotationPop').hidden) A.closePopover();
  });
}());
