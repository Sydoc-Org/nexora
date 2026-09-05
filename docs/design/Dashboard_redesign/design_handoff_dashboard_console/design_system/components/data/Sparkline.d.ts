/** Axis-free trend line for a KPI cell. 120x36 by default. */
export interface SparklineProps {
  values?: number[];
  /** Stroke colour — a --nx-series-* token or the KPI's own semantic colour */
  color?: string;
  /** Explicit area fill; by default the stroke colour at 14% */
  fill?: string;
  width?: number;
  height?: number;
  strokeWidth?: number;
  style?: React.CSSProperties;
}
export function Sparkline(props: SparklineProps): JSX.Element;
