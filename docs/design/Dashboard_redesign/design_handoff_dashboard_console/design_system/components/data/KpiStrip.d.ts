/**
 * The signature element of the slim system: KPIs as one borderless strip
 * divided by hairlines, closed by a rule underneath. Replaces the four
 * `.nx-card .nx-stat` boxes of the legacy pages.
 * @startingPoint section="Data" subtitle="Borderless four-up KPI strip" viewport="1140x140"
 */
export interface KpiStripProps {
  /** One entry per KPI — same shape as MetricProps */
  items?: Array<{ label: string; value: string | number; delta?: string; deltaTone?: 'good' | 'bad' | 'neutral'; deltaNote?: string; spark?: number[]; sparkColor?: string }>;
  /** Defaults to the item count, capped at 4 */
  columns?: number;
  loading?: boolean;
  style?: React.CSSProperties;
}
export function KpiStrip(props: KpiStripProps): JSX.Element;
