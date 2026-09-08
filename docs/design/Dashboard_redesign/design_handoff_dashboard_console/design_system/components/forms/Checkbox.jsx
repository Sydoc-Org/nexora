const React = window.React;

export function Checkbox({ label, checked, indeterminate, onChange, disabled, style }) {
  const ref = React.useRef(null);
  React.useEffect(() => { if (ref.current) ref.current.indeterminate = !!indeterminate; }, [indeterminate]);
  return React.createElement('label', {
    style: Object.assign({ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 'var(--fs-control)', color: 'var(--nx-text)', cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1 }, style)
  },
    React.createElement('input', {
      ref, type: 'checkbox', checked: !!checked, onChange, disabled,
      style: { width: 15, height: 15, margin: 0, accentColor: 'var(--nx-accent)', flexShrink: 0, cursor: 'inherit' }
    }),
    label);
}
