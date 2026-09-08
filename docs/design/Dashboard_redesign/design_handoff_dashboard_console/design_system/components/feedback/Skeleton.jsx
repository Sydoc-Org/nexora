const React = window.React;

export function Skeleton({ width = '100%', height = 13, radius = 6, style }) {
  return React.createElement('span', {
    style: Object.assign({
      display: 'inline-block', width, height, borderRadius: radius,
      background: 'linear-gradient(90deg, color-mix(in srgb, var(--nx-text) 9%, transparent) 25%, color-mix(in srgb, var(--nx-accent) 20%, transparent) 50%, color-mix(in srgb, var(--nx-text) 9%, transparent) 75%)',
      backgroundSize: '200% 100%', animation: 'nx-skel-shimmer 1.6s ease-in-out infinite'
    }, style)
  });
}
