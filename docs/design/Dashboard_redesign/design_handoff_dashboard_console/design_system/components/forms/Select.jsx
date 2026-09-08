const React = window.React;

export function Select({ options = [], size = 'md', style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return React.createElement('span', { style: Object.assign({ position: 'relative', display: 'inline-block', minWidth: 148 }, style) },
    React.createElement('select', Object.assign({
      onFocus: () => setFocus(true), onBlur: () => setFocus(false),
      style: {
        height: size === 'lg' ? 'var(--ctl-h-lg)' : 'var(--ctl-h)',
        boxSizing: 'border-box', width: '100%', appearance: 'none',
        padding: '0 28px 0 10px', fontFamily: 'var(--nx-font)', fontSize: 'var(--fs-control)',
        color: 'var(--nx-text-sec)', background: 'var(--nx-card)',
        border: '1px solid ' + (focus ? 'var(--nx-accent)' : 'var(--nx-border)'),
        borderRadius: 'var(--nx-radius-ctl)', outline: 'none', cursor: 'pointer'
      }
    }, rest), options.map((o, i) => React.createElement('option', { key: i, value: o.value !== undefined ? o.value : o }, o.label !== undefined ? o.label : o))),
    React.createElement('i', { className: 'fas fa-chevron-down', style: { position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 9.5, color: 'var(--nx-text-meta)', pointerEvents: 'none' } }));
}
