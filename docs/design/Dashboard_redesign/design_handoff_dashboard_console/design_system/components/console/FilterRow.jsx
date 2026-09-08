const React = window.React;

export function FilterRow({ label, children, right, style }) {
  return React.createElement('div', {
    style: Object.assign({ display: 'flex', alignItems: 'center', gap: 8, marginTop: 18, paddingBottom: 14, borderBottom: '1px solid var(--nx-border)' }, style)
  },
    label ? React.createElement('span', { style: { fontSize: 'var(--fs-eyebrow)', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--nx-text-meta)', marginRight: 2 } }, label) : null,
    children,
    React.createElement('span', { style: { flex: 1 } }),
    right);
}
