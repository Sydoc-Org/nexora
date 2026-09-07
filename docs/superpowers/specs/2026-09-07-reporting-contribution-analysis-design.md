# Contribution analysis ("Why did it move?") — design

**Date:** 2026-09-07 · **Status:** approved design, plan pending · **Branch:** `feat/reporting-contribution-analysis`

## Goal

When the Simple tab's KPI band shows a delta chip (this period vs. the shifted
prior window), the user can click **Why?** and see *what drove the change*:
for each of up to three dimensions (process first, then the source's
categorical columns), the values ranked by their contribution to the delta,
with current, prior, delta and share of the total change.

This is the first slice of the "Insight" track chosen in brainstorming
(contribution analysis → chart annotations → anomaly radar → Eddard weekly
card). The maths lives in a Flask-free helper so the later Eddard card can
reuse it without HTTP.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Trigger | Click the **Total** delta chip on the Simple KPI band (also rendered on dashboard KPI cards). Compares current vs. the **existing** shifted prior window from `shifted_definition_for_comparison`. No new inputs. |
| Dimensions | **Auto**: `processname` if the source has it, then string-typed catalog columns in catalog order, skipping `workitem_id` and any field pinned by an `eq` filter, **cap three**. |
| Where computed | **Server**, new endpoint `POST /api/reporting/contribution`, pure helper `nx_lib/reporting/contribution.py`. |
| Metric | The report's **first** metric only (same rule as alert schedules' `total_definition`). |
| UI surface | The drill slide-over shell, one tab per dimension, signed horizontal bars. Rows click through to drill-through. Simple tab + dashboard KPI cards; **Advanced untouched**. |
| Permissions | **None new.** Every query goes through `_prepare_run`, so grants, source permission and process scope equal the report's own. |

Out of scope, deliberately: user-picked dimensions, comparing two arbitrary
periods, composition without a comparison window, Advanced tab, AI narration
of the drawer (Eddard can call the helper later), multi-metric decomposition.

## 1. Endpoint

`POST /api/reporting/contribution` — body is the **Simple definition** exactly
as sent to `/api/reporting/run` (relative-date tokens intact). Guarded by
`reporting.view` (the same guard as `api_run`) and the same rate limit.

Validation, in order:

1. Body is a JSON object with a non-empty `metrics` list → else **400**
   "This report has no measure to explain."
2. `shifted_definition_for_comparison(rd)` returns a window → else **400**
   "No comparison window — the report needs exactly one relative-date filter."
3. `_prepare_run` raises `PermissionError` → **403**; definition errors → **400**
   with `detail`, as `api_run` does.

Response `200`:

```json
{
  "priorStart": "2026-07-01", "priorEnd": "2026-07-31",
  "metric": "doc_count", "metricLabel": "Documents",
  "isRatio": false,
  "currentTotal": 1240, "priorTotal": 980,
  "dimensions": [
    {
      "field": "processname", "label": "Process",
      "rows": [
        { "value": "clientA.inbound", "current": 400, "prior": 250, "delta": 150, "share": 0.58 },
        { "value": "(empty)",         "current": 12,  "prior": 30,  "delta": -18, "share": -0.07 },
        { "value": "(other)",         "current": 90,  "prior": 80,  "delta": 10,  "share": 0.04 }
      ]
    }
  ],
  "skipped": ["doctype"]
}
```

- `dimensions` is ordered as picked. A dimension whose query raised is
  dropped, its field appended to `skipped`, and a warning logged — the drawer
  never 500s because one column is unqueryable.
- `share` is `delta / (currentTotal − priorTotal)`; when the total delta is
  `0` or the metric is a ratio (`isRatio: true`, see §2) every `share` is
  `null` and the UI hides the share column.
- Totals are computed from the **first** dimension's un-folded rows on the
  server, not re-queried, so `currentTotal` always equals the KPI band's Total
  for the same definition. (`_prepare_run` builds the grouped query; the helper
  sums.)

## 2. Helper — `nx_lib/reporting/contribution.py` (Flask-free)

```python
def pick_dimensions(catalog_fields, filters, *, cap=3) -> list[dict]
def contribution_rows(current_rows, prior_rows, *, field, metric, top=8) -> list[dict]
def is_ratio_metric(metric_def) -> bool
```

- **`pick_dimensions`** — `catalog_fields` is the list the catalog endpoint
  already returns (`field`, `label`, `type`). Rule: `processname` first if
  present; then every `type == "string"` field in catalog order; drop
  `workitem_id`; drop any field that has an `eq` filter in `filters` (a pinned
  value has a single row and explains nothing); truncate to `cap`.
- **`contribution_rows`** — full outer join of the two grouped result sets on
  the dimension value (`None` → `"(empty)"`), `delta = current − prior`,
  sort by `abs(delta)` desc, keep `top`, fold the remainder into one
  `"(other)"` row (sums of current/prior/delta). Missing side counts as `0`.
  `share` is filled by the caller once the total delta is known.
- **`is_ratio_metric`** — `True` when the metric's aggregation is `avg`,
  `min`, `max` or any distinct-count; a share of an average is meaningless,
  so ratio metrics get delta only. Reads the resolved metric from
  `semantic.py` (same lookup `api_run` uses); unknown → `False`.

The view layer (`nx_lib/views/reporting/run.py`, next to `api_run`) does the
I/O: for each picked dimension it deep-copies the definition with
`columns = [{"field": dim}]`, `metrics = [first metric]`, no `sort`, no
`forecast`, `rowLimit = MAX_ROW_LIMIT`; runs it once as-is and once through
the shifted copy; hands both row lists to the helper. Up to **six** queries
per call — all grouped aggregates with a date filter, the same cost class as
the KPI band's own comparison run.

## 3. UI

- **Trigger.** In `static/js/reporting_simple_result.js`, `deltaChipHtml` for
  the Total tile renders a `<button class="reporting-delta-chip" …>` instead
  of a span, with `aria-label` "Why did this change?". Avg and Peak chips stay
  spans. The Total tile on dashboard KPI cards is the same renderer, so it gets
  the button for free; a card without a comparison never renders a chip.
- **Drawer.** New `static/js/reporting_contribution.js` (behaviour) + strings
  in the shim `templates/js/_reporting_contribution_js.html`. On click it
  POSTs the current Simple definition (the one `runCurrent` built, tokens
  intact) to the endpoint, opens the `ReportingDrill` slide-over shell with a
  loading state, then renders:
  - a header line "Documents · 980 → 1 240 (+260, +26.5 %) · prior 1 Jul – 31 Jul"
  - one tab per dimension (`label`), first tab active
  - a list per tab: value on the left, a horizontal signed bar scaled to the
    tab's largest `|delta|` in the middle (directional colours, identical to
    the chips — never "good/bad"), and "prior → current  Δ  share %" on the
    right. `(other)` renders muted, without a bar.
  - a footer note when `skipped` is non-empty: "Not shown: doctype".
- **Row click** calls `ReportingDrill.open` with the same synthetic drill
  definition drill-through builds for a category click (`eq` value, or
  `is_null` for `(empty)`) on the **current** window. `(other)` is not
  clickable.
- **Empty states.** 400 → the drawer shows the server message. Zero
  dimensions → "This source has no columns to break the change down by."
- CSS additions in `static/css/reporting.css` (`.reporting-contrib-*`), no new
  library, no Chart.js — bars are plain `div`s so they work inside the drawer
  without a canvas.

## 4. Permissions & safety

- No new permission code. The endpoint's guard and every generated query are
  the report's own (`_prepare_run`), so a user sees exactly the values they
  could already reach through drill-through.
- Rate limit: same decorator value as `api_run`.
- Definition validation is the existing validator; no new SQL construction
  outside `query.py`.

## 5. Testing

- **Unit (TDD)** `tests/unit/test_reporting_contribution.py`: dimension pick
  (order, `eq` skip, `workitem_id` skip, cap), join with missing sides, null →
  `(empty)`, `(other)` fold sums, sort by `|delta|`, ratio-metric detection.
- **Integration** `tests/integration/test_reporting_contribution_api.py`:
  endpoint on the TEST-seeded table source — 400 without a token filter, 400
  without metrics, 200 shape, `currentTotal` equals the run endpoint's summed
  metric for the same definition.
- **Playwright** `tests/e2e/test_reporting_contribution.py`: Simple tab,
  `page.route` stub for the endpoint registered **before** `page.goto`
  (metrics fetch happens at `rp:tabshown`), click the Total chip, assert tabs
  and a bar row, click a row and assert the drill drawer opens.
- **INT walkthrough** with a screenshot in `var/screenshots/` before the
  handoff — confirmation, never the only verification.

## 6. Docs & chores

- `docs/howto/reporting.md`: new `### Contribution analysis` under "What the
  page does", after Drill-through; the endpoint in the route table.
- `docs/howto/reporting-guide.md` + `templates/_reporting_help.html`: one
  paragraph "Click the arrow on the total to see what drove the change"
  (the `reporting-help-sync` hook enforces the pair).
- `CHANGELOG.md` `[Unreleased]` → Added.
- i18n cycle for the new msgids (de/fr/it).
- No migration, no env key, no deploy exclude.

## See also

- `docs/howto/reporting.md` → "Comparison & delta chips", "Drill-through"
- `nx_lib/reporting/tokens.py` → `shifted_definition_for_comparison`
- `templates/js/_reporting_drill_js.html` → `window.ReportingDrill`
