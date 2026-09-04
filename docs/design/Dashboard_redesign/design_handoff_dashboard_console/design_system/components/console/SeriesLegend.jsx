const React = window.React;

export function SeriesLegend({ items = [], style }) {
  return React.createElement('div', { style: Object.assign({ display: 'flex', flexWrap: 'wrap', gap: 12 }, style) },
    items.map((it, i) => React.createElement('span', {
      key: i, style: { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--fs-micro)', color: 'var(--nx-text-sec)' }
    },
      React.createElement('span', { style: { width: 16, height: 0, borderTop: '2.5px ' + (it.dash || 'solid') + ' ' + it.color } }),
      it.name,
      it.count !== undefined ? React.createElement('span', { style: { color: 'var(--nx-text-meta)', fontVariantNumeric: 'tabular-nums' } }, it.count) : null)));
}
