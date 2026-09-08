/** On/off toggle for settings and schedule rows. */
export interface SwitchProps {
  checked?: boolean;
  onChange?: () => void;
  label?: React.ReactNode;
  disabled?: boolean;
  style?: React.CSSProperties;
}
export function Switch(props: SwitchProps): JSX.Element;
