/**
 * Legend for multi-series line charts. The swatch repeats the series' own line
 * style, so a colour-blind reader can still match line to label.
 */
export interface SeriesLegendProps {
  items?: Array<{ name: string; color: string; dash?: 'solid' | 'dashed' | 'dotted' | 'double'; count?: number | string }>;
  style?: React.CSSProperties;
}
export function SeriesLegend(props: SeriesLegendProps): JSX.Element;
