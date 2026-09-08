const React = window.React;

export function PageHead({ icon, title, meta, status, statusTone = 'ok', actions, style }) {
  const dot = statusTone === 'warn' ? 'var(--nx-warning)' : statusTone === 'error' ? 'var(--nx-danger)' : 'var(--nx-success)';
  return React.createElement('div', {
    style: Object.assign({ display: 'flex', alignItems: 'center', gap: 12 }, style)
  },
    icon ? React.createElement('span', {
      style: {
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 36, height: 36, borderRadius: 'var(--nx-radius-lg)', flexShrink: 0,
        background: 'var(--nx-brand-grad)', color: '#fff', fontSize: 15,
        boxShadow: 'var(--nx-shadow-brand)'
      }
    }, React.createElement('i', { className: icon })) : null,
    React.createElement('span', { style: { fontSize: 'var(--fs-h1)', fontWeight: 600, letterSpacing: 'var(--tracking-h1)', color: 'var(--nx-text)' } }, title),
    meta ? React.createElement('span', { style: { fontSize: 'var(--fs-meta)', color: 'var(--nx-text-meta)' } }, meta) : null,
    React.createElement('span', { style: { flex: 1 } }),
    status ? React.createElement('span', {
      style: { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--fs-meta)', color: 'var(--nx-text-meta)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
    },
      React.createElement('span', { style: { width: 7, height: 7, borderRadius: 99, background: dot, display: 'inline-block' } }),
      status) : null,
    actions);
}
