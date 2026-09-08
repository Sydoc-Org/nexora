/** Uppercase micro-label above a control, with hint/error line below. */
export interface FieldProps {
  label?: string;
  hint?: string;
  error?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export function Field(props: FieldProps): JSX.Element;
