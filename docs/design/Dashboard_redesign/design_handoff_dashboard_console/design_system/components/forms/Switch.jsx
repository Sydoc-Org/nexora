const React = window.React;

export function Switch({ checked, onChange, label, disabled, style }) {
  const track = React.createElement('span', {
    onClick: disabled ? undefined : onChange,
    style: {
      position: 'relative', width: 30, height: 17, flexShrink: 0,
      borderRadius: 99, cursor: disabled ? 'not-allowed' : 'pointer',
      background: checked ? 'var(--nx-accent)' : 'var(--nx-border-strong)',
      transition: 'background var(--nx-dur) var(--nx-ease)'
    }
  }, React.createElement('span', {
    style: {
      position: 'absolute', top: 2, left: checked ? 15 : 2, width: 13, height: 13,
      borderRadius: 99, background: '#fff', transition: 'left var(--nx-dur) var(--nx-ease)'
    }
  }));
  if (!label) return React.createElement('span', { style }, track);
  return React.createElement('label', { style: Object.assign({ display: 'inline-flex', alignItems: 'center', gap: 9, fontSize: 'var(--fs-control)', color: 'var(--nx-text)', opacity: disabled ? 0.5 : 1 }, style) }, track, label);
}
