/** Label + mono number in a bordered pill — result counts, selection counts. */
export interface CountPillProps {
  label: string;
  value: string | number;
  style?: React.CSSProperties;
}
export function CountPill(props: CountPillProps): JSX.Element;
