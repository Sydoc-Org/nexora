// SVG chart stand-ins for the UI kit. In the app these are Chart.js canvases;
// the geometry, colours and axis treatment here are the spec they follow.
function axisTicks(max, steps) {
  const out = [];
  for (let i = 0; i <= steps; i++) out.push(Math.round((max / steps) * i));
  return out;
}

function LineChart({ series, labels, width = 1136, height = 290, roundTo = 500, everyOther = true }) {
  const padL = 46, padB = 24, padT = 10;
  const all = series.reduce((a, s) => a.concat(s.values), []);
  const max = Math.ceil(Math.max.apply(null, all) / roundTo) * roundTo;
  const plotW = width - padL, plotH = height - padB - padT;
  const x = (i, n) => padL + (n > 1 ? (plotW / (n - 1)) * i : 0);
  const y = (v) => padT + (1 - v / max) * plotH;
  const ticks = axisTicks(max, 4);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="none" style={{ display: 'block' }}>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={padL} x2={width} y1={y(t)} y2={y(t)} stroke="var(--nx-divider)" strokeWidth="1" />
          <text x={padL - 8} y={y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--nx-text-meta)" fontFamily="var(--nx-mono)">{t.toLocaleString('en-US')}</text>
        </g>
      ))}
      {labels.map((l, i) => (everyOther && i % 2 ? null : (
        <text key={i} x={x(i, labels.length)} y={height - 6} textAnchor="middle" fontSize="10" fill="var(--nx-text-meta)" fontFamily="var(--nx-mono)">{l}</text>
      )))}
      {series.map((s, si) => {
        const d = s.values.map((v, i) => (i ? 'L' : 'M') + x(i, s.values.length).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ');
        return (
          <g key={si}>
            {series.length === 1 ? <path d={d + ` L${width} ${y(0)} L${padL} ${y(0)} Z`} fill={s.color} fillOpacity="0.10" /> : null}
            <path d={d} fill="none" stroke={s.color} strokeWidth={series.length === 1 ? 2 : 1.6}
              strokeDasharray={s.dash === 'dashed' ? '6 4' : s.dash === 'dotted' ? '2 3' : undefined}
              strokeLinejoin="round" />
          </g>
        );
      })}
    </svg>
  );
}

function BarChart({ values, labels, width = 1136, height = 290, roundTo = 35, color = 'var(--nx-series-1)' }) {
  const padL = 46, padB = 24, padT = 10;
  const max = Math.ceil(Math.max.apply(null, values) / roundTo) * roundTo;
  const plotW = width - padL, plotH = height - padB - padT;
  const bw = plotW / values.length;
  const y = (v) => padT + (1 - v / max) * plotH;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="none" style={{ display: 'block' }}>
      {axisTicks(max, 4).map((t, i) => (
        <g key={i}>
          <line x1={padL} x2={width} y1={y(t)} y2={y(t)} stroke="var(--nx-divider)" strokeWidth="1" />
          <text x={padL - 8} y={y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--nx-text-meta)" fontFamily="var(--nx-mono)">{t}</text>
        </g>
      ))}
      {values.map((v, i) => (
        <rect key={i} x={padL + i * bw + bw * 0.18} y={y(v)} width={bw * 0.64} height={Math.max(plotH - (y(v) - padT), 1)} fill={color} rx="2" />
      ))}
      {labels.map((l, i) => (i % 2 ? null : (
        <text key={i} x={padL + i * bw + bw / 2} y={height - 6} textAnchor="middle" fontSize="10" fill="var(--nx-text-meta)" fontFamily="var(--nx-mono)">{l}</text>
      )))}
    </svg>
  );
}

window.NexoraKitCharts = { LineChart, BarChart };
