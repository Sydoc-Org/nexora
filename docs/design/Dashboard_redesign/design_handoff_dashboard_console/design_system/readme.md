# nexora design system — "slim"

nexora is sydoc's document-processing platform: documents arrive from scanners,
mailboxes and client systems, run through named processes (`02_Posteingang`,
`03_Invoice_New`, …), get extracted and validated, and are reported on. The
users are operations staff who watch throughput and backlog all day, plus
administrators who configure tenants, processes and schedules.

The application is a Flask + Jinja app (`templates/*.html`, `static/css/*.css`,
Chart.js 4.5.1, Font Awesome 6.4.2), themed entirely through `--nx-*` CSS
custom properties with dark mode, five accent presets, density, radius, motion
and contrast preferences written pre-paint from stored user prefs.

**This design system encodes the target look for the whole app: the "slim"
direction.** The Reporting console was migrated first (its own special case);
the Dashboard redesign that produced this system is next. Every future page
follows what is in here.

## The one rule

Boxes become rules. A page is a single white surface; structure comes from
hairlines, whitespace and type — not from stacked cards with borders and
shadows. Cards survive only where content genuinely floats above the page:
dropdown menus, modals, drawers.

Concretely:
- Page content: no `border`, no `border-radius`, no `box-shadow`. Sections are
  separated by `border-top: 1px solid var(--nx-border)` (`SectionRule`).
- KPIs: one borderless grid divided by `1px solid var(--nx-divider)` hairlines,
  closed by a rule underneath (`KpiStrip`) — never four cards with icon chips.
- Filters: controls sit directly on the page above a hairline (`FilterRow`) —
  not in a bordered `.nx-filter` panel.
- Charts: full content width, no frame; the title row carries the tabs.
- Tables: no wrapper card; the header rule and row dividers do the framing.
- Shadow means floating. Nothing in the page flow carries one.

## Content fundamentals

The product speaks German (de/fr/it are translated via Babel; `translations/`).
Copy is short, factual and operational — labels, not sentences:

- Nouns for headings: "Rückstand", "Verlauf 14 Tage", "Zufluss gegen Abfluss".
- Imperative for actions: "Aktualisieren", "Auswahl validieren", "Speichern".
- Numbers carry their unit or comparison inline: "1,247 offen · +48 seit
  gestern", "14 Tage · Spitze 2,650", "+12% vs. gestern".
- Time is always explicit and formatted `dd.MM.yyyy HH:mm` or `HH:mm:ss`.
- Process and document identifiers are shown verbatim in mono
  (`02_Posteingang`, `DOC-882314`) — never prettified.
- Address the user informally in second person only where a preference is
  personal ("Gilt nur für dein Konto"). Otherwise the UI states facts about the
  system, not about the user.
- No marketing subtitles. The legacy "Here's a real-time overview of your
  document processing activity." line is exactly what the slim system removes:
  the header's second line is context (user, last sign-in, record count).
- No emoji anywhere. Status is carried by a dot, a label pill, or a colour.

## Visual foundations

**Type.** Schibsted Grotesk (400–800) is the UI face, Inter the fallback and the
face of pages not yet migrated; both load from Google Fonts. Every figure a user
compares runs in the mono stack with `font-variant-numeric: tabular-nums`. The
scale is deliberately short: 10px uppercase eyebrow (700, .09em) · 11/11.5px
meta · 12.5px controls (600) · 13px body · 15px section title (700, −.02em) ·
22px page title (600, −.5px) · 32px KPI value (mono, 600, −1.4px).

**Colour.** Two greys for surface (`#f9fafb` page, `#ffffff` content), two line
weights (`#e5e7eb` rule, `#f3f4f6` hairline), three text greys (`#1f2937`,
`#6b7280`, `#9ca3af`). Amber `#d97706` is the default accent for the operations
surfaces; indigo, emerald, sky and rose remain as user-selectable themes and
every component reads `--nx-accent`, never a literal. Status: green `#059669`,
amber `#d97706`, red `#dc2626`. Charts use four separable hues
(`--nx-series-1..4`: amber, violet, cyan, pink), each paired with its own line
style so the legend still works without colour.

**Layout.** Content maxes at 1180px inside a 1600px page frame, 22–40px side
inset, 44px top inset. One vertical rhythm: 14px between rows, 18px before a new
titled section, 30px inside a KPI cell. Controls are one height per surface —
29px on slim pages, 33px in the console — and a row never mixes the two. Grid
and flex with `gap` everywhere; no margin stacking.

**Backgrounds.** Flat. No gradients on page surfaces, no imagery, no texture.
The brand gradient (`--nx-brand-grad`, amber → orange 135°) appears in exactly
two places: the 36–44px page-head icon chip and the 3px active-nav bar. The
optional "aurora" and "grid" page backdrops are user preferences, not design
defaults.

**Borders & radii.** 1px everywhere; `--nx-border-strong` only on hover.
8px on controls, 10px on raised surfaces, 12px on icon chips, pill on dots and
status labels. All radii multiply `--nx-radius-scale` so the user's corner
preference keeps working.

**Elevation.** `--nx-shadow-menu` (`0 8px 24px rgba(16,24,40,.12)`) on
dropdowns, `--nx-shadow-pop` on modals, `--nx-shadow-brand` glow under the
gradient icon chip. Everything else: none.

**States.** Hover darkens the border (`--nx-border-strong`) or tints the
background (`--nx-alt`); table rows additionally get an inset 2px accent rail on
the left. Focus is a 3px `--nx-accent-soft` ring plus an accent border — never
an outline suppression without a replacement. Press states are not animated.
Disabled is `opacity: .5` plus `cursor: not-allowed`.

**Motion.** One entrance (`nx-rise`: 6px up, 0.6s, `cubic-bezier(.4,0,.2,1)`,
staggered 95ms) and 150ms colour/border transitions. The nav rail expands in
280ms. No bounces, no parallax, no attention loops. Everything respects
`prefers-reduced-motion` and the in-app motion toggle.

**Transparency & blur.** Only in token form (`--nx-accent-soft`,
`color-mix` tints). No frosted glass.

## Iconography

Font Awesome 6.4.2 Solid, loaded from CDN (`fas fa-*`), is the only icon set —
there is no custom SVG icon library in the codebase and none should be drawn.
Icons are monochrome, sized 10–13px next to text and 15–18px in the gradient
page chip, and always paired with a label except in the nav rail and toolbar
icon buttons (which carry `aria-label`/`title`). Recurring glyphs:
`fa-gauge-high` dashboard, `fa-list-check` workitems, `fa-chart-line` reporting,
`fa-file-lines` documents, `fa-sliders` appearance, `fa-rotate` refresh,
`fa-chevron-down` disclosure, `fa-magnifying-glass` search, `fa-download` export,
`fa-ellipsis-vertical` row menu. Unicode is used for one thing: the minus sign
in negative deltas (−38%, U+2212), so figures align. No emoji.

**Marks.** `assets/nexora-logo.gif` (the animated product mark, shown at 38px in
the nav rail) and `assets/sydoc-logo.png` (the company mark, footers and auth
pages), both copied from `static/images/`. No mark was drawn for this system.

## Index

| Path | What |
|---|---|
| `styles.css` | the entry point consumers link — imports only |
| `tokens/` | colors, typography, spacing, elevation, motion, themes, base reset |
| `components/core/` | Button, IconButton, Label, CountPill, PageHead, SectionRule |
| `components/forms/` | Input, Select, Field, Checkbox, Switch, ScopePicker |
| `components/console/` | FilterRow, SegmentedControl, UnderlineTabs, ChartHeader, SeriesLegend |
| `components/data/` | KpiStrip, Metric, Sparkline, DataTable, Pagination |
| `components/feedback/` | EmptyState, Flash, Skeleton |
| `ui_kits/nexora_app/` | one reference screen (the slim Dashboard) built from the kit, plus the nav rail |
| `guidelines/` | the specimen cards shown in the Design System tab |
| `assets/` | nexora and sydoc marks, favicon |
| `ds-fallback.js` | lets the cards and UI kit render standalone before the platform bundle exists |

### Component inventory and where it comes from

Every component maps to something that already exists in the app, restyled to
the slim rules — nothing was invented:

| Component | Source in the codebase |
|---|---|
| Button, IconButton | `.nx-btn`, `.rc-btn` (the gradient CTA is retired) |
| Label | `.nx-label` + `--nx-l-*` pastels |
| CountPill | `.nx-count-pill` (flat accent numeral instead of gradient text) |
| PageHead | `.nx-page-head` / `.rc-topbar` merged into one row |
| SectionRule | replaces `.nx-card` / `.rc-card` as the page-content container |
| Input, Select, Field, Checkbox, Switch | `.nx-input`, `.nx-select`, `.nx-field`, the custom checkbox chrome, `.rc-tog` |
| ScopePicker | `.nx-scope*` + `_process_multiselect_js.html` |
| FilterRow | replaces `.nx-filter` |
| SegmentedControl | `.rc-layout-toggle` |
| UnderlineTabs | `.nx-tabs` / `.nx-tab` |
| ChartHeader, SeriesLegend | `.rs-chart-title` and the Dashboard backlog legend |
| KpiStrip, Metric, Sparkline | `.nx-stat` + `.rs-kpi-row`, rebuilt borderless |
| DataTable, Pagination | `.nx-table`, `.nx-pagination` |
| EmptyState, Flash, Skeleton | `.nx-empty`, `.nx-flash`, `.nx-skel` |

Intentional additions: none. Deliberate omissions: the Reporting console's own
specialised parts (schema browser, ERD, report wizard, drill drawer, chat) and
the admin surfaces — they are large enough to deserve their own pass.

## Migrating a page

1. Delete the card wrappers. Each former card becomes a `SectionRule`.
2. Collapse the page header to one row: icon chip, title, one meta line, live
   status, actions. Drop the subtitle paragraph.
3. Move all filters into one `FilterRow` and give it a single control height.
4. Turn stat cards into one `KpiStrip` with deltas and sparklines; drop the
   icon chips.
5. Let charts span the full content width; move any view switch into
   `UnderlineTabs` in the chart header and any parameter switch into a
   `SegmentedControl` on the right of the filter row.
6. Replace hardcoded hexes with `--nx-*` tokens and check light, dark, compact
   and the amber/indigo accents.

## Sources

- Local codebase: the `nexora` folder attached to this project (Flask app —
  `templates/`, `static/css/`, `nx_lib/`, `ops/backlog_history/`).
- Token and component values were read from `static/css/nexora-ui.css`,
  `reporting-console.css`, `dashboard.css` and `_header.css`.
- The slim direction comes from the Dashboard redesign in this project
  (`Dashboard Redesign.dc.html`, option 1a) and the shipped Reporting console
  (`docs/design/design_handoff_reporting_console` in the repo).
