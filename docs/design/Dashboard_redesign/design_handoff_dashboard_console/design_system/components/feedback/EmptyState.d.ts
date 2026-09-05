/**
 * Nothing-here state. The slim version drops the gradient art tile of
 * `.nx-empty__art` — a muted glyph and one line of type.
 */
export interface EmptyStateProps {
  icon?: string;
  title: string;
  hint?: string;
  action?: React.ReactNode;
  style?: React.CSSProperties;
}
export function EmptyState(props: EmptyStateProps): JSX.Element;
