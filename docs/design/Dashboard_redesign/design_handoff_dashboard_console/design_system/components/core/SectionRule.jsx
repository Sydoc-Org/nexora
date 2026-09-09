const React = window.React;

export function SectionRule({ title, meta, right, eyebrow, children, style }) {
  return React.createElement('section', {
    style: Object.assign({ borderTop: '1px solid var(--nx-border)', paddingTop: 18, marginTop: 10 }, style)
  },
    (title || right) ? React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
      title ? React.createElement('h3', { style: { margin: 0, fontSize: 'var(--fs-title)', fontWeight: 700, letterSpacing: 'var(--tracking-title)', color: 'var(--nx-text)' } }, title) : null,
      meta ? React.createElement('span', { style: { fontSize: 'var(--fs-micro)', color: 'var(--nx-text-meta)', fontVariantNumeric: 'tabular-nums' } }, meta) : null,
      React.createElement('span', { style: { flex: 1 } }),
      right) : null,
    eyebrow ? React.createElement('p', { style: { margin: '10px 0 4px', fontSize: 'var(--fs-eyebrow)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 'var(--tracking-eyebrow)', color: 'var(--nx-text-meta)' } }, eyebrow) : null,
    children);
}
