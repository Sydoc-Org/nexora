# Reporting "Editorial Ledger" Reskin — Design

**Date:** 2026-07-15 · **Status:** approved by owner (brainstorm w/ visual companion, 3 rounds of mockups)
**Scope:** the main Reporting page only — Simple tab (library + wizard + ask-AI), Advanced tab
(builder + SQL sandbox), results/chart/table, show-query, drill drawer, AI surfaces.
**Out of scope:** `reporting_sources.html`, `reporting_metrics.html` (admin pages), every other app page.

## Why

The 2026-07-14 "flagship UI polish" plan executed correctly but was locked to "no new visual
identity" (its D-design) — the page still looks like every other nexora page. The owner wants
Reporting to have its **own data-workspace identity**. Direction was chosen visually from three
candidates (Mission Control / Analyst's Desk / Data Console), then two blend leans; the locked
result is **"Editorial Ledger": Analyst's-Desk layout and typography on a cool neutral canvas**
(the warm-paper variant was explicitly rejected in favor of the Data Console's background).

## Locked identity (owner-approved mockup: `.superpowers/brainstorm/1427-1784100466/content/blend-final.html`)

- **Canvas:** page background `#fcfcfc`, masthead band `#fff`, cool-gray hairlines (`#e4e4e7`-ish
  via tokens where available). No beige/warm tones anywhere.
- **Chrome reduction:** result/library cards lose heavy borders/shadows; separation via 1px
  hairline rules. One **2px ink rule** (`#18181b`) tops the chart block — the signature editorial
  detail.
- **Typography:** serif masthead via **system serif stack** (Georgia/Charter/serif — no webfont,
  no new asset) for the page title and section titles ONLY. **All data is mono**
  (`ui-monospace` stack): KPI numerals, table cells (right-aligned, tabular figures), metadata.
  Uppercase letter-spaced captions (`DOSSIERS`, `ERROR RATE` style) label the KPI band.
- **Charts:** single-series → ink-navy `#312e81` bars/lines with brand indigo `#4f46e5` on the
  peak value. Multi-series keeps the existing categorical palette. Pie slice borders stay `#fff`
  (chart PNG export forces white background — inherited constraint, do not change).
- **Numbers:** existing app-locale `fmtNumber` stands (2026-07-14 D14). No forced Swiss grouping —
  the mockup's `48'112` is what an en/de-CH viewer would see, not a new convention.
- **The one loud element:** the Run button keeps the brand gradient. Nothing else glows.

## Surfaces

| Surface | Treatment |
|---|---|
| Masthead | White band, serif "Reporting", muted context line (report name · source), timing badge right-aligned, gradient Run button. Existing `nx-page-head` markup restyled via scoped classes — not replaced. |
| Simple tab library | Ledger tiles: hairline separation, serif report names, mono metadata. |
| Simple wizard + ask-AI | Editorial treatment in place: uppercase tracked step labels, mono values, hairlines. No flow/step changes. |
| Advanced builder | Restyle in place — chip-like selects, mono values. No layout re-architecture. |
| Results (both tabs) | KPI band → chart/table block under the 2px ink rule → persistent query footer. |
| Drill drawer, AI surfaces | Canvas + typography treatment only; no structural change. |

## New elements (features, not just CSS)

1. **KPI stat band** above results, computed **client-side from the returned rows only**: total of
   the measure, row/bucket count, avg per bucket. **No "vs prior period" delta in v1** — it would
   need a second query; explicitly deferred. Labels via gettext.
2. **Timing badge** "N rows · M ms" in the masthead (right-aligned, per the mockup): row count
   from the run response, elapsed measured client-side around the fetch.
3. **Persistent query footer**: one-line peek of the existing `sqlDisplay` field (shipped
   2026-07-14, WS1); click expands the existing show-query panel. No new SQL machinery.

## Dark mode

**Minimal adaptation** (owner choice — no designed "ink edition"): today's dark treatment stays;
each new element (canvas tint, KPI band, footer, single-series chart color) gets an `html.dark`
override so nothing reads broken. Existing dark-mode SQL palette from 2026-07-14 untouched.

## Hard constraints (inherited, all still binding)

- **Never rename** a `.reporting-*` class; preserve every `id`/`name`/`data-testid` (11 e2e files
  select by them). New classes are additive under a `.reporting-ledger-*` namespace.
- `static/css/reporting.css` edited **in place, append-wins** (unlayered, historical layers). No
  new stylesheet. `static/css/nexora-ui.css` untouched (app-wide).
- `.reporting-admin*` rules shared with admin pages — untouched.
- `.nx-rise*` fill-mode stays `backwards` (stacking-context trap).
- Every new user-facing string through the app i18n mechanisms; the reporting i18n lint guard
  (`tests/unit/test_reporting_i18n_lint.py`) will fail hardcoded English — full pybabel de/fr/it
  cycle once, late.
- PROD `/nexora` prefix: any new hand-built URL in JS partials uses the `API_PREFIX` idiom.

## Error handling

No new error paths. KPI band and timing badge render only on a successful run (absent otherwise —
they derive from the response). Query footer hidden when `sqlDisplay` is null (inliner degrade
path from WS1 keeps working).

## Testing

- Existing e2e suites are the regression net (selectors untouched by design).
- New targeted e2e (network-stub pattern, `_stub_run_ok`): KPI band values from a stubbed run
  response; timing badge present after run; footer click expands show-query.
- Live browser pass on INT + screenshots to `var/screenshots/` (remote-session rule) at the end.

## Non-changes

No migrations, no new permissions, no `deploy.yml` change (only already-deployed dirs touched),
no new dependencies, no font assets, admin pages untouched.

## Deferred / follow-ups

- "vs prior period" KPI delta (needs a second query — own mini-plan if wanted).
- Designed dark "ink edition".
- The 2026-07-14 plan's still-open owner actions (Beta badge removal, confirm() modals, locale
  dates) are independent of this reskin.
