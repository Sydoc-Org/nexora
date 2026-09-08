const React = window.React;

export function SegmentedControl({ options = [], value, onChange, size = 'md', style }) {
  return React.createElement('div', {
    style: Object.assign({
      display: 'inline-flex', border: '1px solid var(--nx-border)', borderRadius: 'var(--nx-radius-ctl)',
      background: 'var(--nx-card)', overflow: 'hidden', height: size === 'lg' ? 'var(--ctl-h-lg)' : 'var(--ctl-h)'
    }, style)
  }, options.map((o, i) => {
    const label = o.label !== undefined ? o.label : o;
    const val = o.value !== undefined ? o.value : o;
    const active = val === value;
    return React.createElement('button', {
      key: i, onClick: () => onChange && onChange(val),
      style: {
        border: 'none', borderLeft: i ? '1px solid var(--nx-border)' : 'none',
        padding: '0 11px', cursor: 'pointer', fontFamily: 'var(--nx-font)',
        fontSize: 11.5, fontWeight: active ? 600 : 500,
        background: active ? 'var(--nx-accent-tint)' : 'var(--nx-card)',
        color: active ? 'var(--nx-accent-hover)' : 'var(--nx-text-meta)'
      }
    }, label);
  }));
}
