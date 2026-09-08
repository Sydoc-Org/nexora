/** Single-line text input at filter-row height. */
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Font Awesome class rendered inside the field on the left */
  icon?: string;
  size?: 'md' | 'lg';
  invalid?: boolean;
  style?: React.CSSProperties;
}
export function Input(props: InputProps): JSX.Element;
