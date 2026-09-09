const React = window.React;

const TONES = {
  gray:   ['var(--nx-l-gray)', 'var(--nx-l-gray-fg)'],
  green:  ['var(--nx-l-green)', 'var(--nx-l-green-fg)'],
  amber:  ['var(--nx-l-amber)', 'var(--nx-l-amber-fg)'],
  red:    ['var(--nx-l-red)', 'var(--nx-l-red-fg)'],
  blue:   ['var(--nx-l-blue)', 'var(--nx-l-blue-fg)'],
  indigo: ['var(--nx-l-indigo)', 'var(--nx-l-indigo-fg)']
};

export function Label({ children, tone = 'gray', dot = true, style }) {
  const [bg, fg] = TONES[tone] || TONES.gray;
  return React.createElement('span', {
    style: Object.assign({
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '2px 9px', borderRadius: 'var(--nx-radius-pill)',
      fontSize: 11.5, fontWeight: 500, lineHeight: 1.6, background: bg, color: fg
    }, style)
  },
    dot ? React.createElement('span', { style: { width: 6, height: 6, borderRadius: '50%', background: 'currentColor', opacity: 0.85, flexShrink: 0 } }) : null,
    children);
}
