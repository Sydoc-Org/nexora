const React = window.React;

function sparkPath(values, w, h, pad) {
  const min = Math.min.apply(null, values), max = Math.max.apply(null, values);
  const span = max - min || 1;
  const step = values.length > 1 ? w / (values.length - 1) : w;
  return values.map(function (v, i) {
    const x = i * step;
    const y = pad + (1 - (v - min) / span) * (h - pad * 2);
    return (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
  }).join(' ');
}

function spark(values, color, w, h) {
  if (!values || !values.length) return null;
  const d = sparkPath(values, w, h, 3);
  return React.createElement('svg', {
    viewBox: '0 0 ' + w + ' ' + h, height: h, preserveAspectRatio: 'none',
    style: { flex: '1 1 auto', minWidth: 0, width: '100%', maxWidth: w, opacity: 0.9, display: 'block' }
  },
    React.createElement('path', { d: d + ' L' + w + ' ' + h + ' L0 ' + h + ' Z', fill: color, fillOpacity: 0.14 }),
    React.createElement('path', { d: d, fill: 'none', stroke: color, strokeWidth: 1.6, strokeLinejoin: 'round' }));
}

export function Metric({ label, value, delta, deltaTone = 'neutral', deltaNote = 'vs. gestern', spark: values, sparkColor = 'var(--nx-series-1)', loading, style }) {
  const tone = deltaTone === 'good' ? 'var(--nx-success)' : deltaTone === 'bad' ? 'var(--nx-accent-hover)' : 'var(--nx-text-sec)';
  return React.createElement('div', { style: Object.assign({ padding: '18px 22px 16px', minWidth: 0, overflow: 'hidden' }, style) },
    React.createElement('p', { style: { margin: 0, fontSize: 'var(--fs-eyebrow)', fontWeight: 700, letterSpacing: 'var(--tracking-eyebrow)', textTransform: 'uppercase', color: 'var(--nx-text-meta)', minHeight: 26, lineHeight: 1.3 } }, label),
    React.createElement('div', { style: { display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12, marginTop: 12 } },
      React.createElement('div', null,
        React.createElement('div', {
          style: {
            fontFamily: 'var(--nx-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 'var(--fs-kpi)',
            fontWeight: 600, letterSpacing: 'var(--tracking-kpi)', lineHeight: 1, color: 'var(--nx-text)',
            opacity: loading ? 0.25 : 1
          }
        }, loading ? '—' : value),
        delta ? React.createElement('div', { style: { marginTop: 6, fontSize: 11, fontWeight: 600, color: tone, whiteSpace: 'nowrap' } },
          delta, deltaNote ? React.createElement('span', { style: { fontWeight: 400, color: 'var(--nx-text-meta)' } }, ' ' + deltaNote) : null) : null),
      spark(values, sparkColor, 96, 34)));
}
