const React = window.React;

export function ScopePicker({ groups = [], selected = [], onChange, summary, width = 260, style }) {
  const [open, setOpen] = React.useState(false);
  const all = groups.reduce((a, g) => a.concat(g.items.map(i => i.id)), []);
  const label = summary || (selected.length === 0 || selected.length === all.length
    ? 'Alle Prozesse'
    : selected.length === 1
      ? (groups.flatMap(g => g.items).find(i => i.id === selected[0]) || {}).name || '1 Prozess'
      : selected.length + ' Prozesse');
  const toggle = (id) => {
    if (!onChange) return;
    onChange(selected.includes(id) ? selected.filter(x => x !== id) : selected.concat([id]));
  };
  const row = (content, key, extra) => React.createElement('label', {
    key,
    style: Object.assign({ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px', borderRadius: 6, fontSize: 'var(--fs-control)', cursor: 'pointer' }, extra),
    onMouseEnter: e => e.currentTarget.style.background = 'var(--nx-accent-tint)',
    onMouseLeave: e => e.currentTarget.style.background = 'transparent'
  }, content);

  return React.createElement('div', { style: Object.assign({ position: 'relative', minWidth: width }, style) },
    React.createElement('button', {
      onClick: () => setOpen(!open), 'aria-expanded': open,
      style: {
        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
        height: 'var(--ctl-h)', boxSizing: 'border-box', padding: '0 9px',
        border: '1px solid ' + (open ? 'var(--nx-accent)' : 'var(--nx-border)'),
        borderRadius: 'var(--nx-radius-ctl)', background: 'var(--nx-card)',
        fontFamily: 'var(--nx-font)', fontSize: 'var(--fs-control)', fontWeight: 500,
        color: 'var(--nx-text)', cursor: 'pointer'
      }
    },
      React.createElement('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, label),
      React.createElement('i', { className: 'fas fa-chevron-down', style: { fontSize: 10, color: 'var(--nx-text-meta)', transform: open ? 'rotate(180deg)' : 'none' } })),
    open ? React.createElement('div', {
      style: {
        position: 'absolute', zIndex: 30, left: 0, right: 0, marginTop: 4, padding: 4,
        maxHeight: '50vh', overflow: 'auto', background: 'var(--nx-card)',
        border: '1px solid var(--nx-border)', borderRadius: 'var(--nx-radius-ctl)',
        boxShadow: 'var(--nx-shadow-menu)'
      }
    }, groups.map((g, gi) => [
      row([
        React.createElement('input', { key: 'c', type: 'checkbox', checked: g.items.every(i => selected.includes(i.id)), onChange: () => { if (!onChange) return; const ids = g.items.map(i => i.id); const on = ids.every(i => selected.includes(i)); onChange(on ? selected.filter(x => !ids.includes(x)) : Array.from(new Set(selected.concat(ids)))); }, style: { width: 15, height: 15, margin: 0, accentColor: 'var(--nx-accent)', flexShrink: 0 } }),
        React.createElement('span', { key: 'n', style: { fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, g.name)
      ], 'g' + gi, gi ? { borderTop: '1px solid var(--nx-border)' } : null),
      ...g.items.map((it, ii) => row([
        React.createElement('input', { key: 'c', type: 'checkbox', checked: selected.includes(it.id), onChange: () => toggle(it.id), style: { width: 15, height: 15, margin: 0, accentColor: 'var(--nx-accent)', flexShrink: 0 } }),
        React.createElement('span', { key: 'n', style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--nx-text-sec)' } }, it.name),
        React.createElement('span', { key: 's', style: { flex: 1 } }),
        it.count !== undefined ? React.createElement('span', { key: 'v', style: { fontSize: 11, color: 'var(--nx-text-meta)', fontVariantNumeric: 'tabular-nums' } }, it.count) : null
      ], 'g' + gi + 'i' + ii, { paddingLeft: 26 }))
    ])) : null);
}
