/** Status pill (GitHub-style dot + text). Carries state, never decoration. */
export interface LabelProps {
  children?: React.ReactNode;
  tone?: 'gray' | 'green' | 'amber' | 'red' | 'blue' | 'indigo';
  /** Leading dot; drop it when the label sits in a dense table cell */
  dot?: boolean;
  style?: React.CSSProperties;
}
export function Label(props: LabelProps): JSX.Element;
