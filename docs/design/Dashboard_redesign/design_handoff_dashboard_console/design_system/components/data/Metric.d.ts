/**
 * One KPI cell: uppercase label, mono value, direction-aware delta, sparkline.
 * Always used inside KpiStrip — never on its own in a card.
 */
export interface MetricProps {
  label: string;
  value: string | number;
  /** Pre-formatted delta, e.g. "+12%" or "−1.5h" */
  delta?: string;
  /** good = green, bad = accent; direction-aware, not sign-aware (less backlog is good) */
  deltaTone?: 'good' | 'bad' | 'neutral';
  /** Comparison text after the delta */
  deltaNote?: string;
  spark?: number[];
  sparkColor?: string;
  loading?: boolean;
  style?: React.CSSProperties;
}
export function Metric(props: MetricProps): JSX.Element;
