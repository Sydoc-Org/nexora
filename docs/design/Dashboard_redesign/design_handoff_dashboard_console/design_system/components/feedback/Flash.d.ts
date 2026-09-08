/** Inline page message (saved, failed, maintenance). Never a floating toast. */
export interface FlashProps {
  tone?: 'success' | 'error' | 'info' | 'warn';
  children?: React.ReactNode;
  onDismiss?: () => void;
  style?: React.CSSProperties;
}
export function Flash(props: FlashProps): JSX.Element;
