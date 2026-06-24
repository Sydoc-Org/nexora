# Two-Breakdown Chart Cap Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the Simple report builder, a two-breakdown chart (two `group by`s) wrongly shows *"Too many data points to chart — choose a coarser granularity or a shorter time range"* when the raw cross-product exceeds 50 rows, even though the pivot collapses to far fewer x-axis points. Scope the pre-pivot 50-row guard so it only fires for single-dimension charts; two-dim charts then reach the already-correct post-pivot x-axis/series caps that mirror the server renderer.

**Architecture:** The Simple-pane client renderer `mountChart(def, columns, rows)` in `templates/js/_reporting_simple_js.html` (vanilla ES5 IIFE + Chart.js) runs a pre-pivot guard `if (rows.length > 50) {` **before** the `if (dims === 2) {` pivot block. For two dims the raw `rows` are the `(dim1 × dim2)` cross-product (e.g. 12 months × 8 sources = 96 rows), so when the first column is a date the guard bails with `I18N.noChartTooManyPoints` even though the pivoted X axis is only ~12 points. The `dims === 2` branch already contains the CORRECT post-pivot guard `if (xOrder.length > 50) { chartCardNote(I18N.noChartTooManyPoints); return; }` and a 12-series cap `if (series.length > 12) {`. The server renderer `render_chart_png` in `nx_lib/reporting/chart_render.py` is the authoritative precedent: `MAX_X = 50` / `MAX_SERIES = 12` are applied **after** pivoting (`x_order = x_order[:MAX_X]`, top-12 series by total) with NO pre-pivot row cutoff. The fix makes the client mirror that ordering by gating the pre-pivot guard with `dims === 1`.

**Tech Stack:** Flask + Jinja2 (process-cached templates), vanilla ES5 IIFE client JS, Chart.js, matplotlib server-side PNG (`chart_render.py`), SQL Server, pytest (unit) + Playwright (e2e).

## Context an engineer needs (read first)

- **Branch:** work on `feature/2.5.63` (already checked out). Two-breakdown charting is itself an unreleased feature on this branch, so this fixes a bug in unreleased work — a `### Fixed` changelog bullet (not a regression note) is the correct category.
- **Anchor on snippets, NEVER line numbers.** Reporting JS shifts every line as in-flight plans land. Every edit below quotes the exact text to find. VERIFIED: the in-flight drill-through plan (`docs/superpowers/plans/2026-06-11-reporting-drill-through.md`) stashes `state.chartData.rawX = xOrder;` / `state.chartData.rawSeries = series;` **inside** the `dims === 2` block — it does NOT touch the pre-pivot guard above it. This one-line guard fix is therefore orthogonal and should land first/independently; whichever PR lands second re-anchors on the quoted snippet.
- **Template process-cache:** Jinja templates are cached for the process lifetime. After editing the `.html`, RESTART the dev server (`nx -u`) before browser-verifying or you will see stale HTML.
- **e2e TEST-cardinality constraint:** the bug needs REAL cardinality (>50 pivoted-then-capped x-points) to reproduce. The TEST `dbo.Users` is intentionally tiny (the existing test puts Locale first = 1 distinct X, Username second = 3 distinct series, to guarantee `>= 2` series). It CANNOT exceed 50 pivoted x-points, so an e2e here CANNOT red-first reproduce the bug. The authoritative characterization is the server-side unit test (the server is already correct and is the spec the client must match).
- **No true red-first automated test exists for the client bug.** The JS guard is not directly unit-testable, the server is already correct (green characterization), and TEST cardinality can't repro in e2e. The genuine proof of the user-visible fix is the **manual browser smoke step (Task 5)** — treat it as a hard gate, not optional.
- **i18n cycle:** NONE needed. `noChartTooManyPoints`, `chartFirst50`, `chartSeriesCapped`, `noChartThreeDims`, `noChartLib`, `noChartTotalOnly` already exist in the same file. No new msgid → no pybabel extract/update/compile.
- **Migrations needed: NO.** Pure client-JS guard scope change plus tests + a changelog bullet. No schema, no data, no new permission, no deploy-exclude (`/XF` / `/XD`) change.
- **Commit hatch:** commit with `$env:SQL_SYNC_SKIP="1"; git commit ...; Remove-Item Env:SQL_SYNC_SKIP` (known INT `SchemaMigrations` CRLF checksum drift makes the `sql-migrate-int` pre-commit hook fail). gitlint caps the commit SUBJECT at 72 chars; bodies wrap ≤100. Remote policy: STOP at commit — no push, no PR.
- **Commit message wiring (IMPORTANT):** use `git commit -m '<subject>' -m '<body>'` (two `-m` flags = subject + body paragraph). Do NOT use `git commit -F -` — nothing is piped to stdin in the non-interactive harness, so it hangs or commits an empty message. The bodies below contain no single quotes; if you ever need one, switch that one commit to a here-string pipe (`@'...'@ | git commit -F -`, closing `'@` at column 0).

### Decisions locked in

| Decision | Choice |
|---|---|
| Fix shape | Scope the pre-pivot guard to single-dim: `if (rows.length > 50) {` → `if (dims === 1 && rows.length > 50) {`, with an explanatory comment. One-line behavior change. |
| Rejected alternative | Draft B's helper extraction (server `_pivot_two_dims` + client `pivotTwoDims`) — scope creep. The extracted server helper is never imported by the ES5 client (zero parity gain) and refactoring the PNG renderer risks output drift on a one-line bug. Deferred follow-up only if a future change actually shares pivot logic. |
| New i18n string | NONE — all keys already exist. |
| SQL migration / permission / deploy-exclude | NONE. |
| CHANGELOG | APPEND one bullet under the EXISTING `### Fixed` subsection of `## [Unreleased]` (verified at the top of the file; a separate later-release `### Fixed` exists further down — do NOT touch it, do NOT create a duplicate header). |
| Authoritative regression | Server unit test in `tests/unit/test_reporting_chart_render.py` characterizing cap-after-pivot. Server is already correct → GREEN from start, not red-first. |
| e2e | SMOKE / no-note assertion appended to existing `test_two_breakdown_chart_has_series`; redundant with the pre-existing canvas-visible check (a text-pin documenting intent), NOT independent coverage and NOT red-first. |
| e2e seed columns | `username` / `locale` on `dbo.Users` (verified in the existing test). NEVER invent `Name` or `Format` (`Name` belongs to `dbo.Reports`, not `Users`). |
| Server renderer | NOT edited — precedent only, already correct. |
| Advanced-mode `mountChart` (`_reporting_viz_js.html`) | NOT touched — separate manual X/Y picker, no two-dim pivot, no `rows.length > 50` guard. Unaffected. |

# PHASE 1 — Characterize the correct (server) behavior

### Task 1: Add a server characterization test proving caps apply post-pivot

This locks the invariant the client must match: >50 raw rows that pivot to ≤50 x-points still render a PNG. The server never had the pre-pivot bug, so this is GREEN-from-start characterization, not red-first.

- [ ] Open `C:\dev\nexora\tests\unit\test_reporting_chart_render.py`. Confirm the helpers/anchors are present: `_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"`, `def _defn(columns, chart_type=None):`, and `def test_two_dims_pivots_to_series_png():` (it ends with `assert png and png[:8] == _PNG_MAGIC`).
- [ ] Directly AFTER the `test_two_dims_pivots_to_series_png` function (anchor on its closing `assert png and png[:8] == _PNG_MAGIC`), add a new test feeding 60 raw rows (30 consecutive months × 2 sources) that pivot to 30 x-points — over the 50 raw threshold but under `MAX_X=50`. Use REAL ISO dates via month rollover (no `2027-13-01`-style invalid months):

```python
def test_two_dims_over_50_raw_rows_pivot_below_max_x_renders():
    # 30 consecutive months x 2 sources = 60 raw rows -> 30 pivoted x-points
    # (<= MAX_X=50). The server caps AFTER pivoting (MAX_X / MAX_SERIES), so
    # this must still render a PNG. This locks the invariant the Simple-builder
    # client mountChart must match: its pre-pivot >50-row guard wrongly bailed
    # on the 60 raw rows even though they collapse to 30 x-points.
    rows = []
    for i in range(30):
        y, mo = 2025 + (i // 12), (i % 12) + 1
        month = f"{y}-{mo:02d}-01"
        rows.append([month, "Scan", 10 + i])
        rows.append([month, "Mail", 4 + i])
    png = render_chart_png(
        _defn([{"field": "exportdate", "grain": "month"}, {"field": "docsource"}]),
        [{"field": "exportdate"}, {"field": "docsource"}, {"field": "doc_count"}],
        rows,
    )
    assert png and png[:8] == _PNG_MAGIC
```

- [ ] Run only this test and confirm GREEN (server already correct):

```powershell
.\venv\Scripts\python.exe -m pytest tests/unit/test_reporting_chart_render.py::test_two_dims_over_50_raw_rows_pivot_below_max_x_renders -q
```

- [ ] Run the full chart-render unit module to confirm no collateral:

```powershell
.\venv\Scripts\python.exe -m pytest tests/unit/test_reporting_chart_render.py -q
```

- [ ] Commit:

```powershell
$env:SQL_SYNC_SKIP="1"; git add tests/unit/test_reporting_chart_render.py; git commit -m 'test(reporting): characterize chart cap applies after pivot' -m 'Add a server unit test that feeds 60 raw rows (30 months x 2 sources) which pivot to 30 x-points, asserting render_chart_png still emits a PNG. The server caps after pivoting (MAX_X=50, MAX_SERIES=12), so >50 raw rows that collapse below MAX_X must render. This locks the invariant the Simple builder client must match (its pre-pivot >50-row guard wrongly bailed).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
```

# PHASE 2 — Fix the client guard

### Task 2: Scope the pre-pivot guard to single-dimension charts

The one-line behavioral fix.

- [ ] Open `C:\dev\nexora\templates\js\_reporting_simple_js.html`. Inside `mountChart(def, columns, rows)`, locate this exact pre-pivot guard. It sits AFTER `var isDate = !!firstCol.grain || /date/.test(firstCol.field);` and BEFORE `if (dims === 2) {`:

```javascript
    if (rows.length > 50) {
      if (isDate) { chartCardNote(I18N.noChartTooManyPoints); return; }
      el('rsChartNote').textContent = I18N.chartFirst50.replace('{n}', String(rows.length));
      el('rsChartNote').hidden = false;
      rows = rows.slice(0, 50);
    }
```

- [ ] Replace ONLY the `if (rows.length > 50) {` line with a `dims === 1`-scoped guard plus an explanatory comment, leaving the guard body and closing `}` unchanged:

```javascript
    // Single-dim only: here rows.length IS the x-point count, so the raw-row
    // cap is correct. For dims===2 the rows are the (dim1 x dim2) cross-product
    // (e.g. 12 months x 8 sources = 96 rows) that the pivot below collapses to
    // far fewer x-points, so two-dim is judged AFTER pivoting by the xOrder>50
    // guard + 12-series cap (mirrors render_chart_png MAX_X / MAX_SERIES).
    if (dims === 1 && rows.length > 50) {
      if (isDate) { chartCardNote(I18N.noChartTooManyPoints); return; }
      el('rsChartNote').textContent = I18N.chartFirst50.replace('{n}', String(rows.length));
      el('rsChartNote').hidden = false;
      rows = rows.slice(0, 50);
    }
```

- [ ] Verify the `dims === 2` branch downstream is untouched and still owns the correct caps — confirm both `if (xOrder.length > 50) { chartCardNote(I18N.noChartTooManyPoints); return; }` and `if (series.length > 12) {` still exist inside `if (dims === 2) {`.
- [ ] Commit:

```powershell
$env:SQL_SYNC_SKIP="1"; git add templates/js/_reporting_simple_js.html; git commit -m 'fix(reporting): two-breakdown chart no longer hits too-many-points cap' -m 'The Simple-builder mountChart ran a pre-pivot rows.length > 50 guard before the dims===2 pivot. For two breakdowns the raw rows are the (dim1 x dim2) cross-product (e.g. 12 months x 8 sources = 96 rows), so the guard fired "Too many data points to chart" even though the pivot collapses to far fewer x-axis points. Scope the guard to dims === 1; two-dim results now flow to the existing post-pivot xOrder>50 guard + 12-series cap, mirroring the server render_chart_png (MAX_X=50 / MAX_SERIES=12 applied after pivot).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
```

# PHASE 3 — e2e smoke + CHANGELOG + browser verify

### Task 3: Add a no-too-many-points-note smoke assertion to the e2e

This is a redundant text-pin (documents intent), NOT independent coverage and NOT red-first. The pre-existing `expect(canvas).to_be_visible()` already catches a regression because `chartCardNote()` sets `rsChartCanvas.hidden = true` when the note fires. TEST cardinality also cannot exceed 50 pivoted x-points. Keep it cheap and use Playwright's auto-waiting idiom.

- [ ] Open `C:\dev\nexora\tests\e2e\test_reporting_simple.py`. Find `def test_two_breakdown_chart_has_series(page, nexora_server):` by name. Confirm its seeding uses verified columns `username` + `locale` on `dbo.Users` (NOT `Name`, NOT `Format`) and that inside the `try:` block it does `canvas = page.locator("#rsChartCanvas")`, `expect(canvas).to_be_visible()`, `series = int(canvas.get_attribute("data-series"))`, `assert series >= 2`, then `expect(page.get_by_test_id("rs-chart-stacked")).to_be_visible()`.
- [ ] Insert a no-note smoke assertion immediately AFTER `assert series >= 2` (anchor on that line), using a `has_text`-filtered locator with auto-waiting `to_have_count(0)`:

```python
        # Smoke text-pin (NOT red-first, NOT independent coverage): the canvas
        # being visible already proves mountChart did not bail with the
        # too-many-points note (chartCardNote hides the canvas). TEST cardinality
        # can't exceed 50 pivoted x-points, so this just pins the exact note text.
        too_many = page.locator(
            "#rsChartNote",
            has_text="Too many data points to chart",
        )
        expect(too_many).to_have_count(0)
```

- [ ] Keep the existing `expect(page.get_by_test_id("rs-chart-stacked")).to_be_visible()`, `expect(page.get_by_test_id("rs-chart-pie")).to_be_hidden()`, and the `finally:` cleanup (the two `DELETE`s) unchanged.
- [ ] Run only this e2e (requires a running TEST server / Playwright harness per `docs/howto/nx.md`):

```powershell
.\venv\Scripts\python.exe -m pytest tests/e2e/test_reporting_simple.py::test_two_breakdown_chart_has_series -q
```

- [ ] If TEST state is stale (order-dependent e2e), reset first then re-run:

```powershell
.\venv\Scripts\python.exe scripts/test_db_reset.py
```

- [ ] Commit:

```powershell
$env:SQL_SYNC_SKIP="1"; git add tests/e2e/test_reporting_simple.py; git commit -m 'test(reporting): smoke-assert two-breakdown chart shows no over-cap note' -m 'Extend test_two_breakdown_chart_has_series with a no-note smoke check: the two-dim chart must not surface the pre-pivot "Too many data points to chart" note. This is a redundant text-pin (the pre-existing canvas-visible check already catches a regression, since chartCardNote hides the canvas) and TEST cardinality cannot exceed 50 pivoted x-points, so it is not red-first; the authoritative regression is the server unit test characterizing cap-after-pivot.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
```

### Task 4: Append the CHANGELOG Fixed bullet (append, do NOT create a subsection)

- [ ] Open `C:\dev\nexora\CHANGELOG.md`. Confirm the EXISTING `### Fixed` subsection under `## [Unreleased]` by locating `### Fixed` followed by `- Reporting AI: prompts now require a date \`grain\` ...`. (A second `### Fixed` exists much further down in a later dated release — do NOT touch it, do NOT add a duplicate header.)
- [ ] Locate the LAST Reporting AI Fixed bullet in that `[Unreleased]` subsection (it is immediately followed by a blank line then a `**Scheduled reports now support metric definitions.**` bullet):

```markdown
- Reporting AI: sources without registered metrics are marked "cannot aggregate" in the grounding; failure messages surface the gate error instead of the model's explanation.
```

- [ ] Append a new bullet directly after that line (still inside the same `### Fixed` subsection, before the blank line that precedes the `**Scheduled reports...**` bullet):

```markdown
- Reporting Simple: two-breakdown results now chart correctly — the pre-pivot >50-row guard was firing on the (dim1 × dim2) cross-product (e.g. 12 months × 8 sources = 96 raw rows) and wrongly reporting "too many data points", even though the pivot collapses to far fewer x-axis points. The guard is now scoped to single-dimension charts; two-dim charts use the existing post-pivot x-axis cap and 12-series cap (matching the server renderer).
```

- [ ] Commit:

```powershell
$env:SQL_SYNC_SKIP="1"; git add CHANGELOG.md; git commit -m 'docs(changelog): note two-breakdown chart cap fix under Unreleased' -m 'Append a Fixed bullet to the existing [Unreleased] > Fixed subsection describing the Simple-builder two-breakdown chart guard scoping.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
```

### Task 5: Browser-verify the fix — HARD GATE (restart server first)

This is the only proof the user-visible fix works (no automated test goes red on the client bug). Do not skip.

- [ ] Restart the dev server so the edited Jinja template is reloaded (templates are process-cached). Use a verified user — reuse whatever account the e2e `_login(page, nexora_server)` resolves to rather than hardcoding an unverified name; if unsure, check `docs/howto/nx.md` / the `--loginas` examples:

```powershell
nx -u -b --loginas:<verified-user>
```

- [ ] In the browser, open `/reporting?tab=simple`, build a Simple report with TWO breakdowns where the first dimension is a date with a fine grain over a range that yields a `(dim1 × dim2)` cross-product exceeding 50 raw rows but ≤50 pivoted x-points. PASS criterion: the chart renders multi-series WITHOUT the "Too many data points to chart" note. Also confirm a single-dim chart with >50 rows still shows its existing first-50 / too-many behavior (unchanged).
- [ ] If running remotely, capture a screenshot to `var/screenshots/` and send it via SendUserFile (remote-frontend policy). No commit needed for this step.

# PHASE 4 — Final verification

### Task 6: Run the affected suites and stop

- [ ] Run the server unit module and the e2e test together:

```powershell
.\venv\Scripts\python.exe -m pytest tests/unit/test_reporting_chart_render.py tests/e2e/test_reporting_simple.py::test_two_breakdown_chart_has_series -q
```

- [ ] Confirm `git status` is clean and `git log --oneline -4` shows the four commits (test, fix, e2e, changelog).
- [ ] STOP. Do not push, do not open a PR (remote policy). The user pushes after local review.

## Gotchas & notes

- **Commit messages use `-m '<subject>' -m '<body>'`, never `git commit -F -`.** In the non-interactive harness nothing is piped to stdin, so `-F -` hangs or commits empty. The bodies above contain no single quotes.
- **Do NOT create a second `### Fixed` subsection.** One already exists under `## [Unreleased]`. The recon brief's "create it" instruction is stale/wrong — appending is correct. A duplicate header would render two Fixed sections in the same release.
- **Anchor on the quoted `if (rows.length > 50) {` snippet, never a line number.** The `dims === 2` pivot block is concurrently targeted by the drill-through plan (`state.chartData.rawX = xOrder;` / `rawSeries`), but that edit is INSIDE the block — the guard sits above it, so this lands cleanly and independently. Whichever lands second re-anchors on the snippet.
- **Restart the dev server before browser-verifying.** Jinja caches templates for the process lifetime — without a restart the browser shows the OLD `.html`.
- **e2e is a redundant smoke text-pin, not red-first and not independent coverage.** `chartCardNote()` hides `#rsChartCanvas`, so the pre-existing `expect(canvas).to_be_visible()` already fails on regression. TEST `dbo.Users` cardinality (Locale = 1 distinct X, Username = 3 series) cannot generate >50 pivoted-then-capped x-points. The server unit test (Task 1) is the authoritative invariant; Task 5's manual smoke is the real user-visible proof.
- **Unit-test dates must be valid ISO months.** Use the `y, mo = 2025 + (i // 12), (i % 12) + 1` rollover; do NOT emit `2027-13-01`-style months (they only survive because `_label()` does pure string slicing, and would mislead a future reader).
- **Use verified seed columns only.** `dbo.Users` has `username` and `locale` (both used by the existing two-breakdown e2e). There is NO `Name` column on `Users` (`Name` belongs to `dbo.Reports`) and NO `Format` column. Never invent them — a bad column 500s the source query.
- **No server change.** `nx_lib/reporting/chart_render.py` is precedent-only (already applies `x_order = x_order[:MAX_X]` and top-12 series after the pivot). Editing it risks PNG output drift on a one-line bug. `templates/js/_reporting_viz_js.html` (Advanced mode) has no two-dim pivot and no `rows.length > 50` guard — unaffected.
- **Commit hatch + remote policy.** Always wrap commits in `$env:SQL_SYNC_SKIP="1"; ...; Remove-Item Env:SQL_SYNC_SKIP` (INT SchemaMigrations CRLF drift). gitlint subject ≤72 chars (all four subjects above comply). Stop at commit — no push, no PR.
- **Rejected scope creep (deferred follow-up).** Draft B's shared pivot-helper extraction (`_pivot_two_dims` server + `pivotTwoDims` client) is NOT done here: the extracted server helper is never imported by the ES5 client (zero parity gain) and refactoring the PNG renderer risks output drift on a one-line bug. Revisit only if a future change genuinely shares pivot logic.
