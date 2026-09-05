const React = window.React;

export function UnderlineTabs({ tabs = [], value, onChange, style }) {
  return React.createElement('div', { style: Object.assign({ display: 'inline-flex', gap: 16 }, style) },
    tabs.map((t, i) => {
      const label = t.label !== undefined ? t.label : t;
      const val = t.value !== undefined ? t.value : t;
      const active = val === value;
      return React.createElement('button', {
        key: i, onClick: () => onChange && onChange(val),
        style: {
          border: 'none', background: 'transparent', padding: '0 0 5px', cursor: 'pointer',
          fontFamily: 'var(--nx-font)', fontSize: 12, fontWeight: 600,
          color: active ? 'var(--nx-text)' : 'var(--nx-text-meta)',
          borderBottom: '2px solid ' + (active ? 'var(--nx-accent)' : 'transparent')
        }
      }, label);
    }));
}
