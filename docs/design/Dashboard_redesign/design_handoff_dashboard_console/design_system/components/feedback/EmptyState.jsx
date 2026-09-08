const React = window.React;

export function EmptyState({ icon = 'fas fa-inbox', title, hint, action, style }) {
  return React.createElement('div', {
    style: Object.assign({ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '44px 24px', gap: 4 }, style)
  },
    React.createElement('i', { className: icon, style: { fontSize: 20, color: 'var(--nx-text-meta)', marginBottom: 10 } }),
    React.createElement('p', { style: { margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--nx-text)' } }, title),
    hint ? React.createElement('p', { style: { margin: 0, fontSize: 'var(--fs-body)', color: 'var(--nx-text-sec)', maxWidth: 360 } }, hint) : null,
    action ? React.createElement('div', { style: { marginTop: 12 } }, action) : null);
}
