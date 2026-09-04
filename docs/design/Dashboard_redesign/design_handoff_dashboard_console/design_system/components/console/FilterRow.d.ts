/**
 * The one filter line of a slim page: no card, no background — controls sit
 * directly on the page above a hairline. Scope controls left, range/view
 * controls right.
 * @startingPoint section="Layout" subtitle="Borderless filter line" viewport="700x110"
 */
export interface FilterRowProps {
  /** Uppercase micro-label in front of the first control, e.g. "Prozess" */
  label?: string;
  children?: React.ReactNode;
  right?: React.ReactNode;
  style?: React.CSSProperties;
}
export function FilterRow(props: FilterRowProps): JSX.Element;
