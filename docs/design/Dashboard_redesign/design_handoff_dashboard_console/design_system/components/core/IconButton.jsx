const React = window.React;

export function IconButton({ icon, label, size = 'md', variant = 'ghost', onClick, active, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const dim = size === 'sm' ? 24 : size === 'lg' ? 33 : 29;
  const s = Object.assign({
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: dim, height: dim, boxSizing: 'border-box', padding: 0,
    borderRadius: 'var(--nx-radius-ctl)', cursor: 'pointer',
    fontSize: size === 'sm' ? 11 : 12.5,
    background: variant === 'outline' ? 'var(--nx-card)' : hover ? 'var(--nx-sunken)' : 'transparent',
    border: variant === 'outline' ? '1px solid var(--nx-border)' : '1px solid transparent',
    color: active ? 'var(--nx-accent)' : hover ? 'var(--nx-text)' : 'var(--nx-text-sec)',
    transition: 'background var(--nx-dur) var(--nx-ease), color var(--nx-dur) var(--nx-ease)'
  }, style);
  return React.createElement('button', {
    'aria-label': label, title: label, onClick, style: s,
    onMouseEnter: () => setHover(true), onMouseLeave: () => setHover(false), ...rest
  }, React.createElement('i', { className: icon }));
}
