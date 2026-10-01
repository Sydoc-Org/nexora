# Handoff: Sydoc Controlling (option 1a)

## Overview
Sydoc Controlling (`templates/controlling.html`, new) is the third of Sydoc's own books, next to Sydoc Finance and Sydoc BPS. It replaces the hand-filled controlling workbook (one sheet per client plus an Overview tab): per **client stream** and month, the hours booked in BPS × an hourly rate = **cost**, set against what was invoiced in Bexio (excl. VAT) = **margin**.

Audience: Sydoc management, **Global Admin only**. Desktop first; must not break at phone width (16px gutter, no horizontal page scroll, wide tables scroll inside their own container).

The page reuses the approved Finance/BPS system unchanged: the ink band, the period headline, the month picker, the ledger rows, statement lines, comparison bars, orange share bars, drill-down table styling and Finance's drift note. Nothing below introduces a new visual language; where a piece is new (margin bar, flags, heatmap, small multiples, rates drawer) it is built from existing tokens and the existing chip (`.nx-label`) and button styles.

## About the design file
`Sydoc Controlling.dc.html` is a **design reference built in HTML** (a Design Component prototype; open it in a browser with `support.js` next to it). It is not production code. Recreate it as:

- `templates/controlling.html` + `templates/js/_controlling_js.html` (shim with translated strings and Jinja data, as `_finance_js.html`)
- `static/css/controlling.css` (`nx-ctl-*` classes)
- `static/js/controlling.js` (behaviour; uses `window.NX`, `API_PREFIX`, `NXSydoc.initPicker`)
- the shared `nx-sydoc-*` band / picker / `nx-track` classes in `nexora-ui.css` and the `_sydoc.html` macros (`brand`, `headline`, `picker_open/close`, `year_switch`), unchanged.

Turn **1a** is the design. All numbers, invoice numbers and names are **sample data** (September 2025 is the brief's example month; the timeline runs Jan 2025 – Oct 2026 with "today" = 1 Oct 2026).

**Tweaks** (the prototype's toolbar) switch: theme light/dark, desktop/phone frame, scenario (live · loading · Bexio failed · BPS failed · empty month), client blocks one-open / independent, and whether the viewer can edit rates. The month states closed / open / running are reached through the picker: Sep 2025 (default) is closed, **Sep 2026 is open**, **Oct 2026 is running**.

In the prototype every colour is written as `var(--nx-token, light-hex)`, so the token mapping is in the markup. Dark mode is applied by setting the same tokens to their `html.dark` values.

## Fidelity
**High fidelity.** Layout, type sizes, spacing, colours and interactions are final intent. Hex values below are light theme; dark uses the existing `html.dark` tokens.

---

## Shell
- Unchanged app shell. `body.nx-app.nx-sydoc` (orange active bar, `.nx-main` top padding 36px).
- New sidebar item after Sydoc BPS: icon **`fa-scale-balanced`**, label "Sydoc Controlling", `active_page == 'controlling'`, gated by the new `controlling.view` permission (Global Admin; `Enterprise Admin` through the 0106 trigger, like `finance.view`).

## 1. Ink band — `.nx-sydoc-band.nx-sydoc-band--flush`
Same as Finance (padding `22px 30px 0`, jump index flush at the bottom).
- **Row 1:** `sydoc.brand(_("Controlling"))` → mark + "Sydoc internal" + muted "Controlling". Actions, all `.nx-sydoc-btn--ghost`: **Excel** (`fa-file-excel`, `/api/controlling/export.xlsx?month=`), **Print** (`fa-print`), **Rates** (`fa-coins`, opens the rates drawer; only with `controlling.rates.edit`). No close button: see *Month states*.
- **Row 2:** `sydoc.headline(_("Sydoc Controlling"), "controlling", month_name, year, prev, next, …, "ctl-picker")`. Hint line by state:
  - open: "BPS hours × rate against what was invoiced in Bexio, each compared with the month before."
  - closed: "Figures as frozen at the close. Bexio is read live; where an invoice has changed since, the client says so."
  - running: "This month is still running: hours grow until it ends, and its invoices are dated next month."
- **Stats** (`.nx-sydoc-stats`): **Status** = lock + "Closed {dd.mm.yyyy} by {who}" / green dot "Open · live" / amber dot "Running" (Finance's markup). **Rate** = "85 CHF/h" + 12px/500 `#9ca3af` "valid since Jan 2025" (+ " · 1 override" when a stream override applies that month).
- **Jump index** `.nx-ctl-jump` (= `.nx-fin-jump` without tiles): Summary · Clients `10` · Hours by task · Volumes · Trend. Items 44px, 12px/500 `#d1d5db`, padding `0 9px`, hover white + 2px `--nx-sydoc` underline; the count is mono 11px/600 `--nx-sydoc-ink-muted`. One row, scrolls sideways (no wrap), as Finance.

## Period picker
`sydoc.picker_open("ctl-picker", _("Choose month"), …)` + `year_switch` + the 3×4 grid + Finance's legend, **identical to Finance** (440px, cells 62px, Closed / Open / Running states, selected cell ink). Range: Jan 2025 (first BPS history month) → current month. A pick navigates to `?month=YYYY-MM`. Default month = previous calendar month, as Finance.

## 2. Month summary — `#ctl-summary.nx-ctl-summary`
- margin-top 24px, top and bottom border `--nx-border`. Grid `repeat(auto-fit, minmax(min(100%, 196px), 1fr))`; cells padding `16px 12px 16px 20px`, `border-left: 1px solid --nx-divider` (first cell none).
- Cell: eyebrow (10px/700/.09em uppercase `--nx-sydoc-quiet`), value row (prefix "CHF" 11.5px/600 quiet · integer **26px/600/−.9px tabular** · decimals 15px quiet · optional suffix 14px/600), delta row 11.5px (trend icon + "+3.2%" in gain/loss, then "vs. Aug 1'198.0 h" quiet), optional caption 11px quiet.
- Five cells: **Total hours** · **Cost** (CHF) · **Invoiced excl. VAT** (CHF; caption "not counted: 1 without invoice, 1 draft, 1 EUR, 1 not linked, 1 unassigned") · **Margin** (CHF + %, signed; caption "6 of 10 streams") · **Documents**.
- **Delta colour:** hours and cost up = `--nx-loss`, down = `--nx-gain`; invoiced, margin and documents up = gain. Margin's delta is in CHF ("+418"), the others in %.
- Running month: Invoiced and Margin show "—" with "invoices are dated in November 2026". Never a silent 0.

## 3. Margin by client (the hero) — `#ctl-clients`
- Group header = Finance's `.nx-fin-group` (12px/700 uppercase quiet + mono count + rule) plus a right meta 11px quiet "Bexio invoices dated in October 2025 · 85 CHF/h".
- Table `.nx-ctl-margin`, inside `overflow-x:auto` with `min-width:1080px`. Grid `minmax(190px,1fr) 84px 112px 124px 112px 210px 70px 118px 14px`, column-gap 12px.
  - Head: eyebrows Stream · Hours · Cost · Invoiced excl. VAT · incl. VAT · Margin CHF · Margin % · vs. {prev month} (numbers right-aligned), bottom border `--nx-border`.
  - Row: an `<a href="#ctl-c-{key}">`, min-height 52px, bottom border `--nx-divider`, hover `--nx-alt`. Clicking opens that client's block below and scrolls to it.
    - Stream: name 13px/600 + sub 11px quiet (Bexio contact, plus project where one contact holds several streams: "Privera AG · Posteingang", "Xpert Consulting AG · ZHAW").
    - Hours mono 13px/600; Cost mono 13px (+ 10.5px quiet "at 72 CHF/h" when an override applies); Invoiced mono 13px; incl. VAT mono 12.5px quiet.
    - **Margin CHF:** a **diverging bar** then the value. Track 96×8px `--nx-divider`, radius 2; a 1px zero tick `--nx-border-strong` (top/bottom −3px) at 50%; the fill grows right from the centre for a profit (`--nx-text`) and left for a loss (`--nx-loss`), width = |margin| ÷ largest |margin| of the month × 50%. Value mono 14px/600, signed ("+2'121.90", "−1'571.90"), loss in `--nx-loss`.
    - Margin % mono 12.5px/600, same colour rule.
    - vs. prev: BPS's two-line delta (icon + "+418.20" 12.5px/600 gain/loss; "Aug +3'409.25" 10.5px quiet).
  - **Total row:** border-top `--nx-border-strong`, min-height 54px, 700 weight; under "Total" 11px quiet "6 of 10 streams in the margin". Hours, cost: all streams. Invoiced, incl. VAT, margin, %: **only streams with an issued CHF invoice** (as Finance: drafts and foreign currency are never summed).
- **Flags** — replace the three margin cells with one cell (`grid-column: span 3`, right-aligned): a quiet 11.5px text + an `.nx-label` chip.
  | Case | Invoiced cells | Chip | Text |
  |---|---|---|---|
  | no invoice | — | `--amber` "No invoice" | "nothing dated October 2025" |
  | draft only | amount in `--nx-text-meta` | `--gray` "Draft" | "+757.90 if issued as drafted" |
  | foreign currency | "EUR 2'797.20" in `--nx-text-meta` | `--blue` "EUR" | "not converted, not in totals" |
  | contact not linked | — | `--gray --nodot` "Not linked" | "Link the Bexio contact" (600, `--nx-sydoc-ink-text`, links to the fix) |
  | running month | — | `--gray --nodot` "Not invoiced yet" | "dated in November 2026" |
  | source failed | — | `--red` "Bexio unavailable" / "BPS unavailable" | reason |
- **Incomplete source** (Privera streams Jan–Oct 2025): a 7×7 ring (`1.5px solid --nx-warning`, radius 99) before the hours value, `title` + `aria-label` "BPS has fewer hours than the controlling workbook for this month".
- **Live data moved** (closed month, Bexio differs from the snapshot): `fa-code-compare` 10px `--nx-warning` before the invoiced value, `title` "Live data moved: Bexio now differs from the close".
- **Unassigned invoices** (`.nx-ctl-unassigned`, one per invoice, under the table): same grid, margin-top 10px, min-height 48px, `1px dashed --nx-border-strong`, radius 8px. Warning icon `--nx-warning`, `--amber` chip "Unassigned", "RE-26797 · Privera AG · Bexio project “Archivdigitalisierung Q3” is not mapped to a stream", the amount in the Invoiced column, and "Not in the totals · Map the Bexio project to a stream" (link 600 `--nx-sydoc-ink-text`).
- Legend under the table (margin-top 12px, 11px quiet, gap `6px 18px`): ring = BPS incomplete · compare icon = live data moved · "Cost = BPS hours × rate. Totals count issued CHF invoices only; drafts, EUR and unlinked streams stay out."

## 4. Per-client blocks — `.nx-ctl-client`
Divider (Finance's `.nx-fin-divider`, margin-top 38px): eyebrow "Per client" + 11px note "hours by task, the Bexio lines and the difference" + rule + "Expand all / Collapse all" (`.nx-fin-more` style, 11.5px/600 `--nx-sydoc-ink-text`).

One `<section id="ctl-c-{key}">` per stream, in this order: Elektro-Material · Compass Group · Privera Posteingang · Privera Rechnungseingang · Privera Neuzugänge · Frigemo · ZHAW · BFH · Bucherer · MediaMarkt. Bottom border `--nx-border`.

- **Header (always visible)** — a full-width `<button aria-expanded>`, padding 18px 0, hover `--nx-alt`, the ledger grid (`260px | 1fr`, gap 48px):
  - left: client 18px/700/−.02em + title 13px/500 quiet on the same baseline ("Privera  Posteingang", "ZHAW  via Xpert").
  - right, right-aligned: the flag / marker chips (left-aligned, flexible), then three fixed cells with eyebrows above values: **Hours** (84px, mono 14px/600) · **Margin CHF** (158px, mono 14px/600 + % 12px; a flagged stream shows "—" + the flag word) · **vs. {prev}** (104px, BPS delta line), then `fa-chevron-down` 11px `--nx-text-meta` (rotates 180° when open, 150ms).
- **Open/close:** default **one open at a time** (opening one closes the other); "Expand all" opens every block; hero rows open their block. Print expands all. On page load all are collapsed (the prototype opens Privera Posteingang to show the detail).
- **Detail** (padding-bottom 30px), the ledger grid:
  - **Identity column:** meta 11px quiet "BPS · Privera › Posteingang" and "Bexio · Privera AG · project Posteingang"; state pills (margin-top 10px): `--indigo --nodot` lock "Closed" / `--green` "Live" / `--amber` "Running", plus `--amber` "live data moved", `--amber` ring "BPS incomplete"; a 2×2 fact grid (margin-top 16px): Rate "85 CHF/h" (" · override") and Volume "16'362 documents"; note 11.5px/1.5 quiet (incomplete-source text, the Xpert / EUR / not-linked explanations); for a not-linked stream the ink button "Link the Bexio contact →" (Finance's `.nx-fin-bpsbtn`).
  - **Statement column**, four parts, each under a `.nx-fin-divider` (eyebrow + note + rule, margin-top 30px):
    - **a. Aufwendungen nach Tätigkeit** — note "BPS hours × 85 CHF/h". Grid `minmax(0,1fr) 84px 112px 84px 150px`: Tätigkeit 13px/500 · Hours mono 14px/600 (2 decimals) · CHF mono 13px · {prev} h mono 12.5px quiet ("·" when 0) · Change = Finance comparison bar (56×6px, ink fill, orange prev tick) + Finance delta text (neutral ink, "▲ +4%" / "▼ −3%" / "▲ New" / "Unchanged"). Rows padding 9px 0, divider borders. Total row "Total Aufwendungen" 700.
    - **b. Debitor-Positionen** — note "Bexio · invoices dated in October 2025". Per invoice: head (padding-bottom 8px, border `--nx-border`): number mono 13px/600, title 13px `--nx-text-sec`, date 12px quiet, status chip (Finance's tones: Paid green, Open blue, Partly paid amber, Draft gray, Cancelled gray, Unpaid red), right: ghost sm "PDF" (`fa-file-pdf`, Finance's PDF route). Lines grid `minmax(0,1fr) 92px 92px 112px`: Text 12.5px/1.45 (wraps) · Quantity · Unit price · Total {currency}, mono, rows 7px. Footer right-aligned: Total excl. VAT (700) · VAT 8.1% (quiet) · Total incl. VAT (quiet). A draft invoice renders its lines in `--nx-text-meta`. Closed month with drift: Finance's `.nx-fin-drift` `<details>` "The live data has moved since the close: 1 figure differs" (At close / Live now / Difference) with the note "The margin uses the invoice as it was at the close. The lines above are live: the invoice was corrected in Bexio afterwards."
    - **c. Differenz** — the block's punchline. margin-top 24px, padding-top 12px, **border-top 1px solid `--nx-text`** (a statement total rule). "Differenz" 13px/700 · formula mono 11.5px quiet "28'036.70 − 25'914.80" · right: value **mono 22px/600/−.6px** signed, % mono 13px/600, delta (icon + CHF, then "Aug +x" 11px quiet). Loss in `--nx-loss`. Flagged streams show a 12.5px quiet sentence instead ("No invoice yet: CHF 7'777.50 of cost is not covered.", "Draft only: +757.90 if issued as drafted. Counted once it is issued.", "Invoiced in EUR (EUR 2'797.20). Not converted, so the difference stays open.", "Unknown until the Bexio contact is linked.", "Open until October is invoiced.").
    - **d. Unit figures** — note "16'362 documents in September". Finance statement lines unchanged (`minmax(0,1fr) 150px 110px 170px`, value mono 17px/600, prev 13px quiet, comparison bar + neutral delta): Seconds per document (1 decimal) · Documents per hour (1 decimal) · Invoiced CHF per document (2 decimals, "—" without an issued CHF invoice). The unit follows the stream: dossiers (Neuzugänge), batches (MediaMarkt).

## 5. Hours by task — `#ctl-tasks`
- Group header "Hours by task" + mono "9 tasks" + rule + meta "all clients · FTE = hours ÷ 176 h".
- Matrix `.nx-ctl-matrix` in `overflow-x:auto`, `min-width:1060px`. Grid `150px repeat(10, minmax(72px,1fr)) 84px`. First column **sticky** (`left:0`, background `--nx-page`), like `.nx-fin-matrix`.
  - Head: 10px/700/.07em uppercase quiet, the streams' short labels (Elektro-Material, Compass, Posteingang, Rechnungen, Neuzugänge, Frigemo, ZHAW, BFH, Bucherer, MediaMarkt; full name in `title`), wrapping allowed, right-aligned; "Total" with a left border.
  - Rows = every task the month has, sorted by total desc. Cells padding 8px, mono 12px right, **heat tint** `rgba(227,99,63, .06 + .5·√(h ÷ largest cell))`, a 1px inset `--nx-page` gap between cells, "·" in `--nx-text-meta` when 0, `title` "{stream} · {task} · {h} h". Row total 700 with left border.
  - Total row (700, top border) and **FTE** row (quiet; = hours ÷ 176, 2 decimals; the grand FTE in ink 700). The 176 h per FTE is a constant in `nx_lib/controlling.py` for now.
- Legend: four tint swatches + "Tint is hours relative to the largest cell · “·” no hours booked · hover a cell for its exact hours".

## 6. Document volumes — `#ctl-volumes`
- Group header + mono total + meta "from the Sydoc Finance figures" (each stream's primary Finance measure, so the numbers match the Finance page).
- Grid `minmax(150px,230px) minmax(0,1fr) 96px 78px 96px 90px` in `overflow-x:auto` (`min-width:620px`): Stream · Share (6px track, `--nx-sydoc` fill relative to the largest stream, then % mono 11.5px quiet) · {month} mono 13px/600 · Unit 11.5px quiet · {prev} mono quiet · Change (Finance's neutral delta). Total row with the note "units differ per stream, summed as in the workbook".

## 7. Trend — `#ctl-trend`
Small multiples, not a stacked chart: ten streams with mixed signs do not stack readably.
- Group header + "22" + meta "Jan 2025 – Oct 2026 · hover a month for its values, click to open it".
- All three charts share one column layout: a **72px label column** (10px/700 uppercase quiet: "Margin", "Hours", "Documents", gap 10px) and then one flex:1 column per month, gap 4px, so a month's margin bar, hours bar, documents bar and axis letter line up vertically.
- **Total margin** (15px/700 + 11px quiet "streams with an issued CHF invoice · bars below zero in red"): 170px high, one column per month (flex:1, gap 4px), bar inset 18% each side, radius 2px, from a zero line `--nx-border-strong`: profit `--nx-text`, loss `--nx-loss`, the **selected month in `--nx-sydoc`**. The running month shows a 22px dashed outline instead of a bar.
- Two **secondary strips** on the same columns (34px each, margin-top 10px / 6px, bars 64% wide, `--nx-border-strong`, selected month orange): **Hours** and **Documents**. No dual axis.
- X axis: month initial 10.5px quiet (selected month 700 `--nx-sydoc-ink-text`), a 6px warning ring under the incomplete months, the year under each January.
- **Hover** (one month across all charts): column background `--nx-divider`, and a tooltip (`#111318`, radius 10px, 11.5px, min-width 210px): month + state, Margin (+%), Invoiced, Cost, Hours, Documents, and a note in `#f6b19c` ("Privera: BPS has fewer hours than the workbook" / "4 streams not in the margin"). Positioned inside the chart area (left = (month + .5) ÷ 22), 14px right of the column; flips to the left past month 14. Click a month = navigate to it.
- **Margin per stream** (divider + note "each tile on its own scale · outlined: BPS incomplete · gap: no comparable invoice"): grid `repeat(auto-fill, minmax(min(100%,218px),1fr))`, gap `24px 28px`. Tile: name 12.5px/600 + the hovered (or selected) month's label 10.5px quiet + value mono 12.5px/600 (or "no invoice" / "draft" / "EUR" / "running"); a 58px chart with its own zero line, gap 2px, same bar colours; **incomplete months as unavailable**: no fill, `1px dashed --nx-text-meta` outline, whatever the sign; months without a comparable invoice show a 3px `--nx-text-meta` dot at zero; the selected month has a 12% orange column tint. Footer 10px quiet "Jan 25 · max ±4.6k · Oct 26". MediaMarkt (not linked) shows "Margin unknown: Bexio contact not linked".
- Chart.js is not needed: these are plain flex bars (as the BPS mockup); if Chart.js is used for the total, match the styling above.

## 8. Rates drawer — `.nx-ctl-rates`
- Opened by the band's Rates button. Overlay `rgba(17,19,24,.45)`; panel fixed to the right, full height, `width:min(560px,100%)`, `--nx-card`, shadow `-24px 0 64px rgba(16,24,40,.22), 0 0 0 1px rgba(16,24,40,.06)`. Esc / overlay click closes; focus trapped, returns to the Rates button. Slide-in 150ms `--nx-ease`, none with reduced motion.
- Head (picker head style): "Rates" 15px/700 + 12px quiet "Cost is BPS hours × the rate valid in that month." + close.
- **Default rate**: eyebrow + rule + ghost sm "Add rate". Grid `76px 82px 82px minmax(0,1fr) 28px`: CHF/h (mono 13.5px/600) · From · To ("open" in `--nx-gain`) · Changed "M. Keller · 06.01.2025" (11.5px quiet) · edit (`fa-pen`, 28px).
- **Per-stream overrides**: same, grid `minmax(0,1fr) 64px 72px 72px 28px`, the stream (600) with "changed by · when" under it.
- **Add / edit** is an inline row: rate input (right-aligned, 32px), From / To `type="month"` (To empty = open-ended), a stream `<select>` for overrides, Cancel (ghost) + **Save** (ink `#111318`, white, 32px, radius 8). Validate: rate > 0, From ≤ To, no overlapping periods for the same scope (show the conflict inline, `--nx-danger` 11.5px).
- Footnote (`fa-circle-info`, 11.5px quiet): "A change applies to open and running months straight away. Closed months keep the rate they were closed with. An override replaces the default rate for its stream and period."

---

## States (never a silent 0)
- **Month states** come from the existing `dbo.FinanceMonthClose`: a month Finance has closed is **closed** here too, and its controlling payload (hours per stream × task, rate, invoiced amounts per stream) is snapshotted with it. *Assumption — confirm:* Controlling has no close button of its own.
  - closed: hours, cost and invoiced amounts from the snapshot; Bexio lines, status and PDF read live. Where the live invoice total differs from the snapshot: the compare icon in the hero, the amber "live data moved" chip/pill, and Finance's drift `<details>` in Debitor-Positionen.
  - open: everything live.
  - running: hours live and growing; all streams "Not invoiced yet".
- **Loading**: the band renders from Jinja at once; summary values, hero rows, block summaries, matrix, volumes and trend show the `nx-skel` shimmer (`skeleton-shimmer` lines as Finance). Each section fetches on its own.
- **A source failed** (per section): Finance's `.nx-fin-error` (red tint, message, mono detail, Retry `nx-btn--secondary nx-btn--sm`) at the top of the section. Bexio down → hours and cost still shown, invoiced and margin "—" with a `--red` "Bexio unavailable" flag, Debitor-Positionen shows the error. BPS down → invoices shown, hours / cost / margin "—", matrix replaced by the error. In a closed month a Bexio failure only affects the live parts (lines, status, drift check); the snapshot figures stay.
- **Empty month**: summary "—" with "nothing booked in …"; the client area shows one line (`fa-inbox` + "Nothing recorded for … : no BPS hours are booked and no Bexio invoice is dated in …"); matrix and volumes say so in one line.
- **Dark mode**: band `#0b0d12` (`--nx-sydoc-band`), everything below on the existing dark tokens. Heat tint, orange bars and the tooltip are unchanged in dark.
- **Phone (≤600px)**: Finance/BPS rules for the band (headline 28px, band padding 18px, stats wrap). Summary cells wrap to one or two columns. Hero table, block tables, matrix and volumes scroll inside their own container; the matrix keeps its sticky first column. The ledger grid goes to one column under 1180px (Finance's breakpoint); the block header's summary cells wrap under the name. Rates drawer full width.
- **Print**: as Finance (no band actions / arrows / jump index, headline 20px black, every block expanded, hover tooltip and trend strips hidden, tables not scrolled).

## Formatting
Swiss: thousands with an apostrophe, two decimals for CHF ("CHF 34'001.70"), one decimal for hours in summaries and the matrix ("1'234.5 h"), two in the task tables (BPS precision), dates `dd.mm.yyyy`, signed values with a true minus "−". UI language English; the workbook terms stay German: *Aufwendungen nach Tätigkeit*, *Debitor-Positionen*, *Differenz*, *Tätigkeit*, task names.

## Design tokens
No new colours. Add to `nexora-ui.css`:
```
--nx-sydoc-quiet: #6b7280;  /* dark: #94a3b8 — quiet text below the band (finance.css's --nx-fin-quiet, promoted so all three pages share it) */
```
Used: `--nx-sydoc*`, `--nx-gain/--nx-loss` (deltas, loss bars), `--nx-warning` (incomplete ring, drift icon, unassigned icon), `--nx-l-*` chips, `--nx-text`, `--nx-text-sec`, `--nx-text-meta`, `--nx-border(-strong)`, `--nx-divider`, `--nx-alt`, `--nx-page`, `--nx-card`. Heat tint `rgba(227,99,63,a)` = `--nx-sydoc` at alpha.

## New classes (`static/css/controlling.css`)
`nx-ctl-jump` · `nx-ctl-summary`, `__cell`, `__value`, `__delta` · `nx-ctl-margin` (hero), `__row`, `__total`, `__flag`, `nx-ctl-mbar` (diverging bar), `nx-ctl-ring` (incomplete marker) · `nx-ctl-unassigned` · `nx-ctl-client`, `__head`, `__sum`, `__detail`, `nx-ctl-tasks`, `nx-ctl-lines` (invoice lines), `nx-ctl-diff` · `nx-ctl-matrix` · `nx-ctl-vol` · `nx-ctl-trend`, `__col`, `__strip`, `__tip`, `nx-ctl-tile` · `nx-ctl-rates`, `__row`, `__form`. Reuse as is: `nx-sydoc-*`, `nx-track`, `nx-label*`, `nx-btn*`, `nx-fin-group`, `nx-fin-divider`, `nx-fin-line*`/`nx-fin-cmp`/`nx-fin-delta` (move these three to `nexora-ui.css` as `nx-sydoc-line*` if you prefer not to load finance.css), `nx-fin-drift`, `nx-fin-error`, `nx-fin-more`, `nx-fin-bpsbtn`.

## Data
- **Streams** (`nx_lib/controlling.py`, a `Stream` spec like Finance's `Section`): key, label, nav label, BPS customer (+ package filter for the three Privera streams and ZHAW/BFH under Aveniq), Bexio contact(s) + project ids, Finance section + measure for the document count, document unit.
- **Hours**: `bps_projects` grouped by stream × task for the month (all tasks, not only billable).
- **Invoices**: `nx_lib/bexio.py` as the Finance panel (month M → invoices dated M + 1, `INVOICE_MONTH_OFFSET`), matched to a stream by contact **and Bexio project**. New mapping table `dbo.ControllingBexioProjects` (project id → stream); a linked contact's invoice with an unmapped project = "unassigned".
- **Rates**: new `dbo.ControllingRates` (Scope = NULL for default or a stream key, RateChf, ValidFrom, ValidTo NULL, ChangedBy, ChangedAt). Permission `controlling.rates.edit` (Global Admin).
- **Incomplete source**: a per stream × month flag. Simplest: a static set in the spec (Privera streams, Jan–Oct 2025); better, `dbo.ControllingWorkbookHours` with the workbook totals so the page can say how many hours are missing.
- **Trend**: one request returning, per month since Jan 2025, totals plus per-stream margin and state (closed months from snapshots, so it stays cheap).
- **API**: `/api/controlling/summary?month=`, `/api/controlling/section/<key>?month=` (clients, tasks, volumes), `/api/controlling/trend`, `/api/controlling/rates` (GET/POST/PUT), `/api/controlling/export.xlsx?month=`.

## Interactions
Month headline → picker; prev/next and picker are navigations (`?month=`). Client-side only: open blocks, expand all, trend hover, rates drawer. Hero row → opens and scrolls to its block (`scroll-margin-top: 20px`). Keep `nx-rise` entrances; reduced motion respected.

## State (client-side)
- URL: `month=YYYY-MM` (source of truth, as Finance).
- Server-rendered into the shim: month list with close state (picker), `closed` info (when, who), the stream spec (keys, labels, nav labels), rate summary for the band, permissions (`canEditRates`).
- Fetched per section: summary + clients (`/api/controlling/section/clients`), tasks, volumes, trend; each with its own loading / error state.
- UI: `openBlocks` (Set of stream keys; one-open mode keeps at most one), `hoverMonth` (trend, null when the pointer leaves), `ratesDrawer {open, form: null | {scope, idx, rate, from, to}}`, picker `{open, viewYear}`.

## Assets
- `assets/sydoc-mark.png` = `static/images/sydoc-mark.png` (already in nexora; the band mark).
- `assets/default-icon.png` = `static/images/default-icon.png` (sidebar avatar, shell only).
- Icons: Font Awesome 6.4.2 (already loaded): `fa-scale-balanced` (new sidebar item), `fa-file-excel`, `fa-print`, `fa-coins`, `fa-chevron-left/right/down`, `fa-lock`, `fa-xmark`, `fa-arrow-trend-up/down`, `fa-minus`, `fa-code-compare`, `fa-triangle-exclamation`, `fa-file-pdf`, `fa-pen`, `fa-plus`, `fa-circle-info`, `fa-inbox`, `fa-arrow-right`.
- No client logos, no images.

## Files in this bundle
- `Sydoc Controlling.dc.html` — the prototype, turn **1a**. Open in a browser with `support.js` next to it. Its Tweaks switch theme, phone frame, the loading / failed / empty states, one-open vs independent blocks, and the rate-editor permission.
- `support.js` — runtime needed to open the prototype.
- `assets/` — images used by the prototype.
- `ISSUE.md` — ready-to-paste issue text.
- The approved Finance and BPS prototypes this page follows are already in the repo: `docs/design/design_handoff_sydoc_finance_bps/`.

## Files to touch in nexora
- New: `templates/controlling.html`, `templates/js/_controlling_js.html`, `static/css/controlling.css`, `static/js/controlling.js`, `nx_lib/controlling.py` (stream spec, month arithmetic reused from `finance.py`, payload, snapshot), `nx_lib/views/controlling.py` (page, section APIs, trend, rates, export), `docs/howto/controlling.md`.
- Migrations (`sql/_migrations/NexoraDB/`, claim the numbers in the issue): permissions `controlling.view` + `controlling.rates.edit` (Global Admin), `dbo.ControllingRates`, `dbo.ControllingBexioProjects`, the controlling payload in the Finance month snapshot (or `dbo.ControllingMonthClose`).
- `templates/_header.html` — sidebar item after Sydoc BPS.
- `static/css/nexora-ui.css` — `--nx-sydoc-quiet` (both themes); optionally move `nx-fin-line*`, `nx-fin-cmp`, `nx-fin-delta`, `nx-fin-drift`, `nx-fin-error` here as shared `nx-sydoc-*`.
- `nx_lib/finance.py` / `views/finance.py` — close also snapshots the controlling payload (if that assumption holds).
- `translations/{de,fr,it}`, `tests/unit/test_controlling.py`, `tests/integration/test_controlling_routes.py`, `tests/e2e` (data-testids: `controlling-band`, `controlling-month-prev/next`, `controlling-period-button`, `controlling-summary`, `controlling-margin`, `controlling-client-<key>`, `controlling-matrix`, `controlling-trend`, `controlling-rates`), `CHANGELOG.md`, `CLAUDE.md` (one line under Sydoc BPS).

## Open points
1. Is a controlling month closed together with Finance's close (assumed), or separately?
2. Hours per FTE: 176 h assumed (42 h × 4.2 weeks). Fixed constant or per month?
3. Should hours be coloured like cost (up = red, assumed) or stay neutral?
