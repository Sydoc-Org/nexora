/** Row counter + prev/next under a DataTable. No border, no card footer. */
export interface PaginationProps {
  page?: number;
  pages?: number;
  onChange?: (page: number) => void;
  /** Free text on the left, e.g. "1–50 von 1,247" */
  total?: string;
  style?: React.CSSProperties;
}
export function Pagination(props: PaginationProps): JSX.Element;
