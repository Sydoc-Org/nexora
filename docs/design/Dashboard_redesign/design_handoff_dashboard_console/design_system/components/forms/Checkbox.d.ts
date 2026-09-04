/** Checkbox with the accent fill. Supports the indeterminate state used by scope pickers. */
export interface CheckboxProps {
  label?: React.ReactNode;
  checked?: boolean;
  /** "some but not all children selected" */
  indeterminate?: boolean;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
  style?: React.CSSProperties;
}
export function Checkbox(props: CheckboxProps): JSX.Element;
