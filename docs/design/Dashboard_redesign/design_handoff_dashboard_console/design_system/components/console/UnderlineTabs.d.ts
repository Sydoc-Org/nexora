/**
 * View switch for one panel — an underline instead of a boxed toggle, so the
 * chart area keeps no frame at all.
 */
export interface UnderlineTabsProps {
  tabs?: Array<string | { label: string; value: string }>;
  value?: string;
  onChange?: (value: string) => void;
  style?: React.CSSProperties;
}
export function UnderlineTabs(props: UnderlineTabsProps): JSX.Element;
