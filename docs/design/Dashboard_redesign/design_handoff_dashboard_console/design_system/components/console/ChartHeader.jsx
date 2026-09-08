const React = window.React;

export function ChartHeader({ title, meta, right, style }) {
  return React.createElement('div', {
    style: Object.assign({ display: 'flex', alignItems: 'center', gap: 10 }, style)
  },
    React.createElement('h3', { style: { margin: 0, fontSize: 'var(--fs-title)', fontWeight: 700, letterSpacing: 'var(--tracking-title)', color: 'var(--nx-text)' } }, title),
    meta ? React.createElement('span', { style: { fontSize: 'var(--fs-micro)', color: 'var(--nx-text-meta)', fontVariantNumeric: 'tabular-nums' } }, meta) : null,
    React.createElement('span', { style: { flex: 1 } }),
    right);
}
