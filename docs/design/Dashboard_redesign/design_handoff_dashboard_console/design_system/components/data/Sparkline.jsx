const React = window.React;

function path(values, w, h, pad) {
  const min = Math.min.apply(null, values), max = Math.max.apply(null, values);
  const span = max - min || 1;
  const step = values.length > 1 ? w / (values.length - 1) : w;
  return values.map((v, i) => {
    const x = i * step;
    const y = pad + (1 - (v - min) / span) * (h - pad * 2);
    return (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
  }).join(' ');
}

export function Sparkline({ values = [], color = 'var(--nx-series-1)', fill, width = 120, height = 36, strokeWidth = 1.6, style }) {
  if (!values.length) return null;
  const d = path(values, width, height, 3);
  const area = d + ' L' + width + ' ' + height + ' L0 ' + height + ' Z';
  return React.createElement('svg', {
    viewBox: '0 0 ' + width + ' ' + height, width, height, preserveAspectRatio: 'none',
    style: Object.assign({ flex: 'none', opacity: 0.9, display: 'block' }, style)
  },
    React.createElement('path', { d: area, fill: fill || color, fillOpacity: fill ? 1 : 0.14 }),
    React.createElement('path', { d, fill: 'none', stroke: color, strokeWidth, strokeLinejoin: 'round' }));
}
