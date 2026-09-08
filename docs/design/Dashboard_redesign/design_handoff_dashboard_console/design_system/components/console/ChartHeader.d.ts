/** Title + tabular meta + right-hand controls above a full-width chart. */
export interface ChartHeaderProps {
  title: string;
  /** Peak/period readout, e.g. "14 Tage · Spitze 2,650" */
  meta?: string;
  right?: React.ReactNode;
  style?: React.CSSProperties;
}
export function ChartHeader(props: ChartHeaderProps): JSX.Element;
