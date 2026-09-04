const React = window.React;

export function Field({ label, hint, error, children, style }) {
  return React.createElement('div', { style: Object.assign({ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }, style) },
    label ? React.createElement('label', { style: { fontSize: 'var(--fs-eyebrow)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 'var(--tracking-eyebrow)', color: 'var(--nx-text-meta)' } }, label) : null,
    children,
    error ? React.createElement('span', { style: { fontSize: 11, color: 'var(--nx-danger)' } }, error)
      : hint ? React.createElement('span', { style: { fontSize: 11, color: 'var(--nx-text-meta)' } }, hint) : null);
}
