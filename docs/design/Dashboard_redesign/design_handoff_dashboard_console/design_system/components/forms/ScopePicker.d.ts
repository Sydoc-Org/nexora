/**
 * Client/process multi-select — the standard scope control of every nexora
 * screen (dashboard, workitems, reporting). Groups are clients; items are
 * processes with today's count.
 * @startingPoint section="Forms" subtitle="Client / process scope filter" viewport="700x150"
 */
export interface ScopePickerProps {
  groups?: Array<{ name: string; items: Array<{ id: string; name: string; count?: number | string }> }>;
  selected?: string[];
  onChange?: (ids: string[]) => void;
  /** Override the computed button text */
  summary?: string;
  width?: number;
  style?: React.CSSProperties;
}
export function ScopePicker(props: ScopePickerProps): JSX.Element;
