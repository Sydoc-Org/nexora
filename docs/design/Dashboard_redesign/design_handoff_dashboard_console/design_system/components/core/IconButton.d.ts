/** Square icon-only control for toolbars, kebab menus and card headers. */
export interface IconButtonProps {
  /** Font Awesome class */
  icon: string;
  /** Accessible name — also the tooltip */
  label: string;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'ghost' | 'outline';
  active?: boolean;
  onClick?: (e: React.MouseEvent) => void;
  style?: React.CSSProperties;
}
export function IconButton(props: IconButtonProps): JSX.Element;
