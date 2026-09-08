const React = window.React;

export function CountPill({ label, value, style }) {
  return React.createElement('span', {
    style: Object.assign({
      display: 'inline-flex', alignItems: 'center', gap: 9,
      padding: '5px 12px', borderRadius: 'var(--nx-radius-pill)',
      border: '1px solid var(--nx-border)', background: 'var(--nx-card)'
    }, style)
  },
    React.createElement('span', { style: { fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--nx-text-meta)' } }, label),
    React.createElement('span', { style: { fontFamily: 'var(--nx-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 15, fontWeight: 700, lineHeight: 1, color: 'var(--nx-accent-hover)' } }, value));
}
