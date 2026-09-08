const React = window.React;

const BASE = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
  boxSizing: 'border-box', fontFamily: 'var(--nx-font)', fontWeight: 600,
  borderRadius: 'var(--nx-radius-ctl)', border: '1px solid transparent',
  cursor: 'pointer', whiteSpace: 'nowrap', textDecoration: 'none',
  transition: 'background-color var(--nx-dur) var(--nx-ease), border-color var(--nx-dur) var(--nx-ease), color var(--nx-dur) var(--nx-ease)'
};

const SIZES = {
  sm: { height: 27, padding: '0 9px', fontSize: 11.5 },
  md: { height: 'var(--ctl-h)', padding: '0 var(--ctl-px)', fontSize: 'var(--fs-control)' },
  lg: { height: 'var(--ctl-h-lg)', padding: '0 12px', fontSize: 'var(--fs-control)' }
};

const VARIANTS = {
  primary:   { background: 'var(--nx-accent)', color: '#fff' },
  secondary: { background: 'var(--nx-card)', color: 'var(--nx-text)', borderColor: 'var(--nx-border)' },
  ghost:     { background: 'transparent', color: 'var(--nx-text-sec)' },
  tint:      { background: 'var(--nx-accent-tint)', color: 'var(--nx-accent-hover)' },
  danger:    { background: 'var(--nx-danger)', color: '#fff' }
};

const HOVER = {
  primary:   { background: 'var(--nx-accent-hover)' },
  secondary: { borderColor: 'var(--nx-border-strong)' },
  ghost:     { color: 'var(--nx-text)' },
  tint:      { borderColor: 'var(--nx-accent)' },
  danger:    { filter: 'brightness(1.06)' }
};

export function Button({ children, variant = 'secondary', size = 'md', icon, iconRight, disabled, href, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const Tag = href ? 'a' : 'button';
  const s = Object.assign({}, BASE, SIZES[size] || SIZES.md, VARIANTS[variant] || VARIANTS.secondary,
    hover && !disabled ? (HOVER[variant] || {}) : null,
    disabled ? { opacity: 0.5, cursor: 'not-allowed' } : null, style);
  return React.createElement(Tag, {
    href, onClick: disabled ? undefined : onClick, disabled: href ? undefined : disabled,
    style: s, onMouseEnter: () => setHover(true), onMouseLeave: () => setHover(false), ...rest
  },
    icon ? React.createElement('i', { className: icon, style: { fontSize: '0.92em', opacity: variant === 'secondary' || variant === 'ghost' ? 0.7 : 1 } }) : null,
    children,
    iconRight ? React.createElement('i', { className: iconRight, style: { fontSize: '0.85em', opacity: 0.7 } }) : null
  );
}
