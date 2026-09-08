/**
 * Action control. Secondary is the default on slim pages — primary is reserved
 * for the one committing action in a view.
 * @startingPoint section="Core" subtitle="Buttons in every variant and size" viewport="700x150"
 */
export interface ButtonProps {
  children?: React.ReactNode;
  /** secondary = default page action; primary = the single committing action; tint = accent-soft; ghost = toolbar */
  variant?: 'primary' | 'secondary' | 'ghost' | 'tint' | 'danger';
  /** md (29px) matches slim filter rows, lg (33px) matches the reporting console */
  size?: 'sm' | 'md' | 'lg';
  /** Font Awesome class, e.g. "fas fa-rotate" */
  icon?: string;
  iconRight?: string;
  disabled?: boolean;
  href?: string;
  onClick?: (e: React.MouseEvent) => void;
  style?: React.CSSProperties;
}
export function Button(props: ButtonProps): JSX.Element;
