/**
 * Top row of every slim page: gradient icon chip, title, one muted meta line,
 * live status on the right, then actions. Replaces the two-line
 * title+subtitle block of the legacy pages.
 * @startingPoint section="Layout" subtitle="Page top bar with live status" viewport="700x120"
 */
export interface PageHeadProps {
  /** Font Awesome class for the gradient chip, e.g. "fas fa-gauge-high" */
  icon?: string;
  title: string;
  /** One muted line — context, not marketing copy (user, last sign-in, record count) */
  meta?: string;
  /** Live/sync readout shown with a status dot */
  status?: string;
  statusTone?: 'ok' | 'warn' | 'error';
  actions?: React.ReactNode;
  style?: React.CSSProperties;
}
export function PageHead(props: PageHeadProps): JSX.Element;
