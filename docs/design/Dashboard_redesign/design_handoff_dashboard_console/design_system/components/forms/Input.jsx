const React = window.React;

export function Input({ icon, size = 'md', invalid, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const s = {
    height: size === 'lg' ? 'var(--ctl-h-lg)' : 'var(--ctl-h)',
    boxSizing: 'border-box', width: '100%',
    padding: icon ? '0 10px 0 30px' : '0 10px',
    fontFamily: 'var(--nx-font)', fontSize: 'var(--fs-control)',
    color: 'var(--nx-text)', background: 'var(--nx-card)',
    border: '1px solid ' + (invalid ? 'var(--nx-danger)' : focus ? 'var(--nx-accent)' : 'var(--nx-border)'),
    borderRadius: 'var(--nx-radius-ctl)', outline: 'none',
    boxShadow: focus ? '0 0 0 3px var(--nx-accent-soft)' : 'none',
    transition: 'border-color var(--nx-dur) var(--nx-ease), box-shadow var(--nx-dur) var(--nx-ease)'
  };
  const input = React.createElement('input', Object.assign({
    style: Object.assign(s, icon ? null : { flexShrink: 0, minWidth: 160 }, icon ? null : style),
    onFocus: () => setFocus(true), onBlur: () => setFocus(false)
  }, rest));
  if (!icon) return input;
  return React.createElement('span', { style: Object.assign({ position: 'relative', display: 'block', flexShrink: 0, minWidth: 160 }, style) },
    React.createElement('i', { className: icon, style: { position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', fontSize: 11, color: 'var(--nx-text-meta)', pointerEvents: 'none' } }),
    input);
}
