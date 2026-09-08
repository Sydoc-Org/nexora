/**
 * Small bordered switch for mutually exclusive *parameters* — time ranges,
 * densities, layouts. For switching what a panel shows, use UnderlineTabs.
 */
export interface SegmentedControlProps {
  options?: Array<string | { label: string; value: string }>;
  value?: string;
  onChange?: (value: string) => void;
  size?: 'md' | 'lg';
  style?: React.CSSProperties;
}
export function SegmentedControl(props: SegmentedControlProps): JSX.Element;
