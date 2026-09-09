/* Resolves the design-system namespace.
   Prefers the compiled bundle (_ds_bundle.js) when the platform has built it;
   otherwise loads the component sources directly so every card and UI kit in
   this project still renders standalone in a plain browser. */
(function () {
  var PATHS = [
    "core/Button",
    "core/IconButton",
    "core/Label",
    "core/CountPill",
    "core/PageHead",
    "core/SectionRule",
    "forms/Input",
    "forms/Select",
    "forms/Field",
    "forms/Checkbox",
    "forms/Switch",
    "forms/ScopePicker",
    "console/FilterRow",
    "console/SegmentedControl",
    "console/UnderlineTabs",
    "console/ChartHeader",
    "console/SeriesLegend",
    "data/Sparkline",
    "data/Metric",
    "data/KpiStrip",
    "data/DataTable",
    "data/Pagination",
    "feedback/EmptyState",
    "feedback/Flash",
    "feedback/Skeleton"
  ];

  function fromBundle() {
    var named = ['NexoraDS', 'Nexora', 'NexoraDesignSystem', 'NexoraSlim', 'DS'];
    for (var i = 0; i < named.length; i++) {
      try {
        var v = window[named[i]];
        if (v && typeof v === 'object' && v.KpiStrip && v.PageHead) return v;
      } catch (e) { /* cross-origin frame named like a global */ }
    }
    var keys = Object.keys(window);
    for (var j = 0; j < keys.length; j++) {
      try {
        var o = window[keys[j]];
        if (o && typeof o === 'object' && !Array.isArray(o) && o.KpiStrip && o.PageHead) return o;
      } catch (e) { /* not readable — skip */ }
    }
    return null;
  }

  window.nexoraDS = function (root) {
    root = root || './';
    var bundled = fromBundle();
    if (bundled) return Promise.resolve(bundled);
    return Promise.all(PATHS.map(function (p) {
      var name = p.split('/').pop();
      return fetch(root + 'components/' + p + '.jsx')
        .then(function (r) { return r.ok ? r.text() : ''; })
        .then(function (src) {
          if (!src) return [name, null];
          try {
            var body = src.replace(/export\s+function\s+/g, 'function ');
            var fn = new Function(body + '\n; return ' + name + ';');
            return [name, fn()];
          } catch (e) {
            console.error('nexoraDS: could not load ' + p, e);
            return [name, null];
          }
        });
    })).then(function (pairs) {
      var ns = {};
      pairs.forEach(function (kv) { if (kv[1]) ns[kv[0]] = kv[1]; });
      window.NexoraDS = ns;
      return ns;
    });
  };
})();
