/**
 * A page section separated by a hairline rule instead of a card frame — the
 * core move of the slim system. Title, optional meta, optional right-hand
 * controls, optional uppercase eyebrow above the content.
 * @startingPoint section="Layout" subtitle="Hairline-separated section" viewport="700x160"
 */
export interface SectionRuleProps {
  title?: string;
  /** Small tabular figure next to the title, e.g. "1,247 offen · +48 seit gestern" */
  meta?: string;
  /** Legend, tabs or buttons pinned right of the title */
  right?: React.ReactNode;
  /** Uppercase micro-label directly above the content, e.g. "VERLAUF 14 TAGE" */
  eyebrow?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export function SectionRule(props: SectionRuleProps): JSX.Element;
