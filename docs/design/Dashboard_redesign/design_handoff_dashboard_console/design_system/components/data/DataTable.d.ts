/**
 * Dense list table with no wrapper card: the header rule and row dividers do
 * the framing. Hovered rows get an accent rail.
 * @startingPoint section="Data" subtitle="Frameless dense table" viewport="1140x260"
 */
export interface DataTableColumn {
  key?: string;
  header: React.ReactNode;
  align?: 'left' | 'right' | 'center';
  /** Render numbers/IDs in the mono stack with tabular figures */
  mono?: boolean;
  muted?: boolean;
  wrap?: boolean;
  /** Custom cell renderer; receives the row */
  cell?: (row: any, index: number) => React.ReactNode;
}
export interface DataTableProps {
  columns?: DataTableColumn[];
  rows?: any[];
  onRowClick?: (row: any, index: number) => void;
  dense?: boolean;
  style?: React.CSSProperties;
}
export function DataTable(props: DataTableProps): JSX.Element;
