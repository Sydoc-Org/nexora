/** Native select with nexora chrome and a drawn chevron. */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  /** Strings, or {label, value} pairs */
  options?: Array<string | { label: string; value: string }>;
  size?: 'md' | 'lg';
  style?: React.CSSProperties;
}
export function Select(props: SelectProps): JSX.Element;
