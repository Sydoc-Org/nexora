const React = window.React;

const TONES = {
  success: ['var(--nx-l-green)', 'var(--nx-l-green-fg)', 'fas fa-circle-check'],
  error:   ['var(--nx-l-red)', 'var(--nx-l-red-fg)', 'fas fa-circle-exclamation'],
  info:    ['var(--nx-l-blue)', 'var(--nx-l-blue-fg)', 'fas fa-circle-info'],
  warn:    ['var(--nx-l-amber)', 'var(--nx-l-amber-fg)', 'fas fa-triangle-exclamation']
};

export function Flash({ tone = 'info', children, onDismiss, style }) {
  const [bg, fg, icon] = TONES[tone] || TONES.info;
  return React.createElement('div', {
    style: Object.assign({ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 'var(--nx-radius-sm)', background: bg, color: fg, fontSize: 'var(--fs-body)' }, style)
  },
    React.createElement('i', { className: icon, style: { fontSize: 12 } }),
    React.createElement('span', { style: { flex: 1 } }, children),
    onDismiss ? React.createElement('button', {
      onClick: onDismiss, 'aria-label': 'Schließen',
      style: { border: 'none', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12, opacity: 0.7 }
    }, React.createElement('i', { className: 'fas fa-xmark' })) : null);
}
