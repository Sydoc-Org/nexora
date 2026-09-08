const React = window.React;

export function DataTable({ columns = [], rows = [], onRowClick, dense, style }) {
  const [hover, setHover] = React.useState(-1);
  const align = (c) => c.align || 'left';
  return React.createElement('table', {
    style: Object.assign({ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--fs-body)', color: 'var(--nx-text)' }, style)
  },
    React.createElement('thead', null,
      React.createElement('tr', null, columns.map((c, i) => React.createElement('th', {
        key: i,
        style: {
          textAlign: align(c), whiteSpace: 'nowrap',
          padding: dense ? '6px 12px 6px 0' : '0 16px 8px 0',
          paddingLeft: i ? 16 : 0,
          fontSize: 'var(--fs-eyebrow)', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: 'var(--tracking-eyebrow)', color: 'var(--nx-text-meta)',
          borderBottom: '1px solid var(--nx-border)'
        }
      }, c.header))) ),
    React.createElement('tbody', null, rows.map((r, ri) => React.createElement('tr', {
      key: ri,
      onClick: onRowClick ? () => onRowClick(r, ri) : undefined,
      onMouseEnter: () => setHover(ri), onMouseLeave: () => setHover(-1),
      style: {
        cursor: onRowClick ? 'pointer' : 'default',
        background: hover === ri && onRowClick ? 'var(--nx-alt)' : 'transparent',
        boxShadow: hover === ri && onRowClick ? 'inset 2px 0 0 0 var(--nx-accent)' : 'none'
      }
    }, columns.map((c, ci) => React.createElement('td', {
      key: ci,
      style: {
        textAlign: align(c), padding: dense ? '7px 12px 7px 0' : '11px 16px 11px 0',
        paddingLeft: ci ? 16 : 0, borderBottom: '1px solid var(--nx-divider)',
        verticalAlign: 'middle',
        fontFamily: c.mono ? 'var(--nx-mono)' : 'inherit',
        fontVariantNumeric: c.mono ? 'tabular-nums' : 'normal',
        color: c.muted ? 'var(--nx-text-sec)' : 'inherit',
        whiteSpace: c.wrap ? 'normal' : 'nowrap'
      }
    }, typeof c.cell === 'function' ? c.cell(r, ri) : r[c.key]))))));
}
