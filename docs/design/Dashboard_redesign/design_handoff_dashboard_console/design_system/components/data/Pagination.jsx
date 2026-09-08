const React = window.React;

function navBtn(label, disabled, onClick) {
  return React.createElement('button', {
    key: label, onClick: disabled ? undefined : onClick, disabled,
    style: {
      height: 27, padding: '0 9px', border: '1px solid transparent', borderRadius: 'var(--nx-radius-ctl)',
      background: 'transparent', fontFamily: 'var(--nx-font)', fontSize: 11.5, fontWeight: 600,
      color: disabled ? 'var(--nx-text-meta)' : 'var(--nx-text-sec)',
      cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1
    }
  }, label);
}

export function Pagination({ page = 1, pages = 1, onChange, total, style }) {
  return React.createElement('div', {
    style: Object.assign({ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 12 }, style)
  },
    total !== undefined ? React.createElement('span', { style: { fontSize: 'var(--fs-micro)', color: 'var(--nx-text-meta)', fontVariantNumeric: 'tabular-nums' } }, total) : null,
    React.createElement('span', { style: { flex: 1 } }),
    navBtn('Zurück', page <= 1, function () { onChange && onChange(page - 1); }),
    React.createElement('span', { style: { fontSize: 'var(--fs-micro)', color: 'var(--nx-text-sec)', fontVariantNumeric: 'tabular-nums' } }, page + ' / ' + pages),
    navBtn('Weiter', page >= pages, function () { onChange && onChange(page + 1); }));
}
