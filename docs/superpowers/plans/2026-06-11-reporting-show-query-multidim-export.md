# Reporting: Show Query, Multi-Breakdowns, Rich Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the executed SQL on every report run, let the Simple wizard pick up to three breakdowns (e.g. *doc count by document source per month over the last 3 months*), and upgrade export beyond bare tables: styled XLSX with the chart embedded, a chart-PNG button on Simple, and server-rendered charts inline in scheduled e-mails.

**Architecture:** Backend already produces parameterized `(sql, params)` and already GROUP-BYs any number of dimensions — Phase 1 echoes the SQL in the run response, adds the missing multi-dim tests, upgrades `rows_to_xlsx`, introduces a matplotlib renderer (`nx_lib/reporting/chart_render.py`), and teaches `send_mail` inline images. Phase 2 is frontend: show-query panels, wizard multi-select breakdowns, client-side series pivoting for 2-dim charts, and export wiring. Spec: `docs/superpowers/specs/2026-06-11-reporting-show-query-multidim-export-design.md`.

**Tech Stack:** Flask, pyodbc/SQLAlchemy, openpyxl 3.1.5 + pillow 11.3.0 (already present), **matplotlib (new dependency)**, Microsoft Graph sendMail, Jinja2 + vanilla ES5 IIFE, Chart.js 4.5.1, Flask-Babel, pytest + Playwright.

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.63`.
- **SEQUENCING — do not skip:** the *Simple-guide improvements* plan
  (`docs/superpowers/plans/2026-06-11-reporting-simple-guide-improvements.md`) was mid-flight
  when this plan was written (its Tasks 6–11 open). **Phase 1 (Tasks 1–6) may start
  immediately** — it touches only files that plan never edits. **Phase 2 (Tasks 7–10) is
  blocked** until that plan's commits for Tasks 6–8 are on the branch (check
  `git log --oneline -15` for `Adjust-in-wizard`, `exit-to-library`, `name modal` commits).
  Phase 2 builds on its deliverables (`wizardStateFromDefinition()`, the chart-type
  switcher, `chartCardNote()`).
- **Anchor on quoted code, not line numbers.** The in-flight plan shifts lines in every
  Simple-pane file. All anchors below are function names + quoted snippets.
- **Jinja template cache:** nexora caches templates for the process lifetime. Restart the
  dev server (`nx -u`) after every template edit before browser-verifying.
- **E2E constraint:** the TEST env has **no Statistics DB** — e2e must use admin-seeded
  `table`-provider sources (the seeding pattern lives at
  `tests/e2e/test_reporting_simple.py:63-128`). Anything docprocessing-only is
  browser-verified on INT instead.
- **Pre-commit hook** auto-runs `db-migrate --env INT` + sync check; on the known
  CRLF-checksum complaint use the documented escape hatch `SQL_SYNC_SKIP=1 git commit ...`.
- **i18n:** every new `{{ _("...") }}` / `_("...")` string must go through the pybabel
  cycle (Task 11) or `tests/unit/test_translations.py` fails.
- **No migrations needed anywhere in this plan** (no schema change; SQL visibility is
  un-gated by decision; `reporting.export` already gates export).
- Key verified facts: `_prepare_run()` returns `(columns, sql, params, engine)`
  (`nx_lib/views/reporting.py`, docstring at the function head); `rows_to_xlsx(columns,
  rows, *, title)` lives in `nx_lib/reporting/export.py:20`; `send_mail(to, subject,
  html_body, attachments=None)` in `nx_lib/mail.py:50` builds a Graph `sendMail` payload;
  the scheduled runner is `ops/run_scheduled_reports.py` (`_process()` at line 58);
  `.github/workflows/deploy.yml:18` pip-installs `requirements.txt` on PROD, so the new
  matplotlib dependency deploys automatically.

### Decisions locked in (owner, 2026-06-11)

| # | Question | Decision |
|---|----------|----------|
| 1 | SQL visibility | Everyone who can run reports — no new permission, no migration. Accepted: SQL text reveals the caller's own process scope and per-process `additionalCondition` clauses. |
| 2 | Wizard breakdowns | Up to **three**, at most one date breakdown. Chart shows dims 1–2 (axis + series); 3 dims → table only + note. |
| 3 | Export upgrades | XLSX title block + embedded chart; Simple chart-PNG button; matplotlib charts inline in scheduled mails (and inside scheduled XLSX). PDF **not** selected. |

---

# PHASE 1 — Backend (safe immediately; zero overlap with in-flight plan)

### Task 1: Close the multi-dimension GROUP BY test gap

The SQL builders already handle N dimensions but nothing proves it. These tests pin the
exact shapes the wizard will generate in Phase 2.

**Files:**
- Test: `tests/unit/test_reporting_query.py` (docprocessing builder)
- Test: `tests/unit/test_reporting_table_query.py` (generic table builder)

- [ ] **Step 1: Read the existing aggregate tests** in `tests/unit/test_reporting_query.py`
  (`test_docprocessing_aggregate_wraps_union`, `test_aggregate_groups_by_month_grain_dim`)
  and copy their fixture setup (process configs, field→column maps, resolved metrics)
  exactly — the new tests below reuse those helpers verbatim; adapt names if the file's
  helpers differ.

- [ ] **Step 2: Add the 2-dim and grain+category tests** to `tests/unit/test_reporting_query.py`:

```python
def test_aggregate_groups_by_two_category_dims():
    """Two categorical dimensions emit GROUP BY on both aliases."""
    rd = _aggregate_rd(columns=[{"field": "docsource"}, {"field": "doctype"}])
    sql, params = build_table_query(
        rd, _PROCESS_CONFIGS, _FIELD_COL_MAPS, row_cap=100,
        resolved_metrics=_RESOLVED_DOC_COUNT)
    assert "GROUP BY [docsource], [doctype]" in sql
    assert sql.count("[docsource]") >= 2  # projected and grouped


def test_aggregate_groups_by_month_grain_plus_category():
    """The wizard's 'per month by export date, by docsource' shape:
    date-grain dim first, category second."""
    rd = _aggregate_rd(columns=[
        {"field": "exportdate", "grain": "month"},
        {"field": "docsource"},
    ])
    sql, params = build_table_query(
        rd, _PROCESS_CONFIGS, _FIELD_COL_MAPS, row_cap=100,
        resolved_metrics=_RESOLVED_DOC_COUNT)
    assert "GROUP BY [exportdate], [docsource]" in sql
    assert "DATEFROMPARTS" in sql  # month truncation applied to the date dim
```

(`_aggregate_rd`, `_PROCESS_CONFIGS`, `_FIELD_COL_MAPS`, `_RESOLVED_DOC_COUNT` stand for
the file's existing fixture helpers from Step 1 — use whatever the neighbouring aggregate
tests use, including the source/filters boilerplate they pass. The *assertions* are the
contract; keep them as written, adjusting only the field names to ones the fixtures map.)

- [ ] **Step 3: Add the 3-dim test** to `tests/unit/test_reporting_table_query.py`, modeled
  on its existing aggregate test fixtures:

```python
def test_generic_aggregate_three_dims():
    """Three dimensions GROUP BY all three, in definition order."""
    rd = _generic_rd(columns=[
        {"field": "colA"}, {"field": "colB"}, {"field": "colC"},
    ])
    sql, params = build_generic_query(
        rd, "dbo.SomeTable", _CATALOG_COLUMNS, row_cap=100,
        resolved_metrics=_RESOLVED_METRIC)
    assert "GROUP BY [colA], [colB], [colC]" in sql
```

- [ ] **Step 4: Run the new tests**

```powershell
python -m pytest tests/unit/test_reporting_query.py tests/unit/test_reporting_table_query.py -v
```
Expected: all PASS (this documents existing behavior; a FAIL is a real finding — stop and
investigate before proceeding).

- [ ] **Step 5: Commit**

```powershell
git add tests/unit/test_reporting_query.py tests/unit/test_reporting_table_query.py
git commit -m "test(reporting): pin multi-dimension GROUP BY shapes (2-dim, grain+category, 3-dim)"
```

---

### Task 2: Echo `sql` + `params` from `/api/reporting/run`

**Files:**
- Modify: `nx_lib/views/reporting.py` (`api_run()`)
- Test: `tests/integration/test_reporting_routes.py`

- [ ] **Step 1: Write the failing integration test.** In
  `tests/integration/test_reporting_routes.py`, find the existing happy-path test that POSTs
  `/api/reporting/run` (reuse its login/session + definition fixture) and add beside it:

```python
def test_run_response_includes_sql_and_params(client_with_reporting_perms, table_source_definition):
    resp = client_with_reporting_perms.post(
        "/api/reporting/run", json=table_source_definition)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "sql" in body and body["sql"].lstrip().upper().startswith("SELECT")
    assert "params" in body and isinstance(body["params"], list)
```

(`client_with_reporting_perms` / `table_source_definition` stand for the file's existing
fixtures — reuse whatever the neighbouring run-endpoint test uses.)

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/integration/test_reporting_routes.py::test_run_response_includes_sql_and_params -v
```
Expected: FAIL — `'sql' in body` is False.

- [ ] **Step 3: Add the keys in `api_run()`.** In `nx_lib/views/reporting.py`, the
  function already does `columns, sql, params, engine = _prepare_run(rd)` and later builds
  the response dict (`{"columns": ..., "rows": ..., "rowCount": ..., "truncated": ...}`).
  Add to that dict, immediately after `"truncated"`:

```python
        "sql": sql,
        "params": [_json_safe(p) for p in params],
```

where `_json_safe` is the module's existing row-value serializer (the same helper the
`rows` already pass through — search the module for how row cells are made
JSON-serializable; `tests/unit/test_reporting_json_safe.py` tests it). If rows are
serialized inline rather than via a helper, apply the identical conversion expression to
each param.

- [ ] **Step 4: Run the test, verify it passes**

```powershell
python -m pytest tests/integration/test_reporting_routes.py -v
```
Expected: all PASS (the new test plus no regressions in the file).

- [ ] **Step 5: Commit**

```powershell
git add nx_lib/views/reporting.py tests/integration/test_reporting_routes.py
git commit -m "feat(reporting): include executed SQL and bind params in run response"
```

---

### Task 3: `rows_to_xlsx` — title block, styled header, optional embedded chart

**Files:**
- Modify: `nx_lib/reporting/export.py` (`rows_to_xlsx`, currently line 20)
- Test: `tests/unit/test_reporting_export.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/unit/test_reporting_export.py`
  (reuse its existing openpyxl round-trip helpers/imports):

```python
import io
import zipfile

from openpyxl import load_workbook

# 1x1 transparent PNG (smallest valid PNG, 67 bytes)
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f0300050001ff5ccc59000000004945"
    "4e44ae426082")


def test_xlsx_has_title_block_and_styled_header():
    data = rows_to_xlsx(
        [{"field": "a", "header": "A"}], [[1]], title="My Report")
    wb = load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A1"].value == "My Report"
    assert ws["A1"].font.bold
    assert "rows" in str(ws["A2"].value)          # generated/meta line
    # header row sits below the title block, is bold, panes frozen under it
    header_cell = next(c for row in ws.iter_rows() for c in row if c.value == "A")
    assert header_cell.font.bold
    assert ws.freeze_panes is not None


def test_xlsx_embeds_chart_png():
    data = rows_to_xlsx(
        [{"field": "a", "header": "A"}], [[1]],
        title="With Chart", chart_png=_TINY_PNG)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        media = [n for n in z.namelist() if n.startswith("xl/media/")]
    assert media, "chart image not embedded in workbook"


def test_xlsx_without_chart_has_no_media():
    data = rows_to_xlsx([{"field": "a", "header": "A"}], [[1]], title="Plain")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert not [n for n in z.namelist() if n.startswith("xl/media/")]
```

- [ ] **Step 2: Run them, watch the new ones fail**

```powershell
python -m pytest tests/unit/test_reporting_export.py -v
```
Expected: the three new tests FAIL (`unexpected keyword argument 'chart_png'` /
title-cell assertion); existing tests still PASS.

- [ ] **Step 3: Implement.** Rework `rows_to_xlsx` in `nx_lib/reporting/export.py`
  (keep the existing sheet-title sanitization and cell pass-through logic — only the layout
  changes):

```python
def rows_to_xlsx(columns, rows, *, title, chart_png=None, generated_at=None):
    """Return .xlsx bytes: bold title, meta line, optional chart image, then
    a styled header row and the data.

    columns: [{field, header}] — header falls back to field when None/empty.
    rows: iterable of row sequences aligned to columns.
    title: report title; also the worksheet title (sanitized as before).
    chart_png: optional PNG bytes rendered above the data table.
    generated_at: optional datetime for the meta line (defaults to utcnow).
    """
    from datetime import datetime, timezone

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = _sanitize_sheet_title(title)   # keep the module's existing logic

    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    stamp = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    row_list = [list(r) for r in rows]
    ws["A2"] = f"Generated {stamp} — {len(row_list)} rows"
    ws["A2"].font = Font(size=10, color="6B7280")

    header_row = 4
    if chart_png:
        import io as _io

        from openpyxl.drawing.image import Image as XlsxImage

        img = XlsxImage(_io.BytesIO(chart_png))
        # scale to ~640px wide, keep aspect
        if img.width and img.width > 640:
            ratio = 640.0 / img.width
            img.width, img.height = 640, int(img.height * ratio)
        ws.add_image(img, "A4")
        header_row = 4 + max(1, int((img.height or 300) / 20)) + 1

    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="EEF2FF")
    for i, col in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=i,
                       value=(col.get("header") or col.get("field")))
        cell.font = header_font
        cell.fill = header_fill
        ws.column_dimensions[get_column_letter(i)].width = 18
    for r_off, row in enumerate(row_list, start=1):
        for c_off, val in enumerate(row, start=1):
            ws.cell(row=header_row + r_off, column=c_off, value=_cell_safe(val))
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

Preserve the module's existing imports/structure and its current cell-value pass-through
(shown here as `_cell_safe` — keep whatever the function does today for cell values, and
keep `_sanitize_sheet_title` as the existing inline sanitization). **Note `rows` may be a
generator today** — the meta line needs the count, hence materializing `row_list` first;
verify callers don't rely on streaming (they don't: both callers pass lists).

- [ ] **Step 4: Fix any existing layout-coupled tests.** Existing tests in
  `tests/unit/test_reporting_export.py` that assert the header at row 1 must be updated to
  the new layout (header at row 4 without chart). Update assertions, don't weaken them.

- [ ] **Step 5: Run the whole export test file**

```powershell
python -m pytest tests/unit/test_reporting_export.py tests/unit/test_reporting_schedule.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add nx_lib/reporting/export.py tests/unit/test_reporting_export.py
git commit -m "feat(reporting): styled XLSX export with title block and optional embedded chart"
```

---

### Task 4: Server-side chart renderer (`chart_render.py`) + matplotlib dependency

**Files:**
- Create: `nx_lib/reporting/chart_render.py`
- Modify: `requirements.txt`
- Test: `tests/unit/test_reporting_chart_render.py` (new)

- [ ] **Step 1: Install + pin matplotlib**

```powershell
.\venv\Scripts\pip install matplotlib
.\venv\Scripts\pip show matplotlib
```

Add to `requirements.txt` (alphabetical position), pinned to the exact version `pip show`
reported, e.g.:

```
matplotlib==<version from pip show>
```

- [ ] **Step 2: Write the failing tests.** Create `tests/unit/test_reporting_chart_render.py`:

```python
"""chart_render renders report rows to PNG bytes for mails/exports."""

from nx_lib.reporting.chart_render import render_chart_png

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _defn(columns, chart_type=None):
    d = {"source": "x", "metrics": [{"metric": "doc_count"}], "columns": columns}
    if chart_type:
        d["chartType"] = chart_type
    return d


def test_one_dim_bar_returns_png():
    png = render_chart_png(
        _defn([{"field": "docsource"}]),
        [{"field": "docsource"}, {"field": "doc_count"}],
        [["Scan", 10], ["Mail", 4]])
    assert png and png[:8] == _PNG_MAGIC


def test_two_dims_pivots_to_series_png():
    png = render_chart_png(
        _defn([{"field": "exportdate", "grain": "month"}, {"field": "docsource"}]),
        [{"field": "exportdate"}, {"field": "docsource"}, {"field": "doc_count"}],
        [["2026-04-01", "Scan", 10], ["2026-04-01", "Mail", 4],
         ["2026-05-01", "Scan", 12], ["2026-05-01", "Mail", 6]])
    assert png and png[:8] == _PNG_MAGIC


def test_no_dims_returns_none():
    assert render_chart_png(_defn([]), [{"field": "doc_count"}], [[42]]) is None


def test_three_dims_returns_none():
    cols = [{"field": "a"}, {"field": "b"}, {"field": "c"}]
    assert render_chart_png(
        _defn(cols),
        cols + [{"field": "doc_count"}],
        [["x", "y", "z", 1]]) is None


def test_empty_rows_returns_none():
    assert render_chart_png(
        _defn([{"field": "docsource"}]),
        [{"field": "docsource"}, {"field": "doc_count"}], []) is None
```

- [ ] **Step 3: Run them, watch them fail** (`ModuleNotFoundError: chart_render`)

```powershell
python -m pytest tests/unit/test_reporting_chart_render.py -v
```

- [ ] **Step 4: Implement.** Create `nx_lib/reporting/chart_render.py`:

```python
"""Server-side chart rendering (matplotlib/Agg) for scheduled mails and XLSX.

Mirrors the web charts' shapes and caps: one dimension -> bar/line/pie on that
dimension; two dimensions -> first dim is the X axis, second becomes series
(grouped bars or one line per series); three or more dimensions, no metrics,
or no rows -> None (callers fall back to a chartless artifact). Caps mirror
the frontend: 50 X values, 12 series.
"""

import io
import os

# Service accounts (IIS app pool, Task Scheduler) have no writable HOME; the
# font cache must land inside var/ (already in the Defender exclusion). Must
# be set before the first matplotlib import.
_MPL_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "var", "mpl-cache")
os.makedirs(_MPL_CACHE, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", _MPL_CACHE)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MAX_X = 50
MAX_SERIES = 12

# Same 12 colors as the web charts (SIMPLE_PALETTE / ReportingViz).
_PALETTE = ["#4338ca", "#2563eb", "#0891b2", "#059669", "#65a30d", "#ca8a04",
            "#dc2626", "#db2777", "#7c3aed", "#0d9488", "#ea580c", "#4f46e5"]


def _label(v):
    s = "" if v is None else str(v)
    return s[:10] if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-" else s


def render_chart_png(definition, columns, rows, *, width=8.0, height=4.5, dpi=110):
    """Render `rows` (aligned to `columns`) as a PNG per `definition`.

    Returns PNG bytes, or None when the result shape has no sensible chart.
    """
    dims = list(definition.get("columns") or [])
    metrics = list(definition.get("metrics") or [])
    if not metrics or not rows or not 1 <= len(dims) <= 2:
        return None
    metric_idx = len(columns) - len(metrics)
    chart_type = definition.get("chartType") or (
        "line" if dims[0].get("grain") else "bar")

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    try:
        if len(dims) == 1:
            data = [(_label(r[0]), float(r[metric_idx] or 0))
                    for r in rows[:MAX_X]]
            labels = [d[0] for d in data]
            values = [d[1] for d in data]
            if chart_type == "pie" and len(labels) <= MAX_SERIES:
                ax.pie(values, labels=labels,
                       colors=_PALETTE[: len(labels)], autopct="%1.0f%%")
            elif chart_type == "line":
                ax.plot(labels, values, color=_PALETTE[0], marker="o")
            else:
                ax.bar(labels, values, color=_PALETTE[0])
        else:
            # pivot: x = dim1 (row order), series = dim2 (12 largest by total)
            x_order, series_tot, cell = [], {}, {}
            for r in rows:
                x, s = _label(r[0]), _label(r[1])
                v = float(r[metric_idx] or 0)
                if x not in cell:
                    x_order.append(x)
                    cell[x] = {}
                cell[x][s] = cell[x].get(s, 0) + v
                series_tot[s] = series_tot.get(s, 0) + v
            x_order = x_order[:MAX_X]
            series = sorted(series_tot, key=series_tot.get, reverse=True)[:MAX_SERIES]
            n = max(len(series), 1)
            for i, s in enumerate(series):
                vals = [cell[x].get(s, 0) for x in x_order]
                color = _PALETTE[i % len(_PALETTE)]
                if chart_type == "line":
                    ax.plot(x_order, vals, label=s, color=color, marker="o")
                else:
                    xs = [j + (i - n / 2) * (0.8 / n) + 0.4 / n
                          for j in range(len(x_order))]
                    ax.bar(xs, vals, width=0.8 / n, label=s, color=color)
            if chart_type != "line":
                ax.set_xticks(range(len(x_order)))
                ax.set_xticklabels(x_order)
            ax.legend(fontsize=8)
        if chart_type != "pie":
            ax.tick_params(axis="x", labelrotation=45, labelsize=8)
            ax.tick_params(axis="y", labelsize=8)
            ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)
```

- [ ] **Step 5: Run the tests, verify they pass**

```powershell
python -m pytest tests/unit/test_reporting_chart_render.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add nx_lib/reporting/chart_render.py tests/unit/test_reporting_chart_render.py requirements.txt
git commit -m "feat(reporting): server-side matplotlib chart renderer for mails and exports"
```

---

### Task 5: `send_mail` inline-image support

**Files:**
- Modify: `nx_lib/mail.py`
- Test: `tests/unit/test_mail_message.py` (new)

- [ ] **Step 1: Extract a pure message builder + write its failing tests.** Create
  `tests/unit/test_mail_message.py`:

```python
"""_build_message assembles the Graph sendMail payload."""

import base64

from nx_lib.mail import _build_message


def test_basic_message_shape():
    m = _build_message("a@b.ch", "Subj", "<p>hi</p>")
    assert m["subject"] == "Subj"
    assert m["body"] == {"contentType": "HTML", "content": "<p>hi</p>"}
    assert m["toRecipients"] == [{"emailAddress": {"address": "a@b.ch"}}]


def test_inline_image_attachment():
    m = _build_message(
        ["a@b.ch"], "S", '<img src="cid:chart">',
        inline_images=[("chart", b"\x89PNG", "image/png")])
    att = m["attachments"][0]
    assert att["isInline"] is True
    assert att["contentId"] == "chart"
    assert att["@odata.type"] == "#microsoft.graph.fileAttachment"
    assert base64.b64decode(att["contentBytes"]) == b"\x89PNG"


def test_file_and_inline_attachments_combine():
    m = _build_message(
        ["a@b.ch"], "S", "x",
        attachments=[("r.xlsx", b"PK", "application/zip")],
        inline_images=[("chart", b"\x89PNG", "image/png")])
    names = [a.get("name") for a in m["attachments"]]
    assert "r.xlsx" in names
    assert sum(1 for a in m["attachments"] if a.get("isInline")) == 1
```

- [ ] **Step 2: Run, watch fail** (`ImportError: _build_message`)

```powershell
python -m pytest tests/unit/test_mail_message.py -v
```

- [ ] **Step 3: Implement.** In `nx_lib/mail.py`, pull the message-dict construction out of
  `send_mail` into `_build_message` and add `inline_images`:

```python
def _build_message(to, subject, html_body, attachments=None, inline_images=None):
    """Build the Graph sendMail message dict.

    attachments: [(filename, bytes, content_type)] — regular file attachments.
    inline_images: [(content_id, bytes, content_type)] — referenced from the
        HTML body as <img src="cid:content_id">.
    """
    if isinstance(to, str):
        to = [to]
    message = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html_body},
        "toRecipients": [{"emailAddress": {"address": a}} for a in to],
    }
    entries = []
    for (name, data, content_type) in attachments or []:
        entries.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": name,
            "contentType": content_type,
            "contentBytes": base64.b64encode(data).decode("ascii"),
        })
    for (cid, data, content_type) in inline_images or []:
        entries.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": cid,
            "contentType": content_type,
            "contentBytes": base64.b64encode(data).decode("ascii"),
            "isInline": True,
            "contentId": cid,
        })
    if entries:
        message["attachments"] = entries
    return message


def send_mail(to, subject, html_body, attachments=None, inline_images=None):
    """Send an HTML mail with optional attachments and inline images.

    to: an address or list of addresses. attachments: list of
    (filename, bytes, content_type). inline_images: list of
    (content_id, bytes, content_type), shown via <img src="cid:...">.
    Raises MailError on failure.
    """
    token = _acquire_token()
    message = _build_message(to, subject, html_body, attachments, inline_images)
    ...  # the existing requests.post(...) block, unchanged
```

(Keep the existing `requests.post` / error handling exactly as it is — only the dict
construction moves.)

- [ ] **Step 4: Run the new tests + anything that imports mail**

```powershell
python -m pytest tests/unit/test_mail_message.py tests/unit/test_reporting_schedule.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add nx_lib/mail.py tests/unit/test_mail_message.py
git commit -m "feat(mail): inline-image (cid) support in send_mail via extracted _build_message"
```

---

### Task 6: Scheduled mails embed the chart (body + XLSX)

**Files:**
- Modify: `ops/run_scheduled_reports.py` (`_process()`, line 58)

- [ ] **Step 1: Wire the renderer into `_process()`.** In `ops/run_scheduled_reports.py`,
  add the import next to the other `nx_lib.reporting` imports:

```python
from nx_lib.reporting.chart_render import render_chart_png
```

then rework `_process()` between `columns, rows = execute_definition(...)` and
`send_mail(...)`:

```python
    png = None
    try:
        png = render_chart_png(definition, columns, rows)
    except Exception as e:  # the mail must go out even if the garnish fails
        app.logger.warning(f"schedule {row.ScheduleID}: chart render failed: {e}")
    fmt = (row.Format or "xlsx").lower()
    if fmt == "csv":
        data, mime, ext = rows_to_csv(columns, rows), "text/csv", ".csv"
    else:
        data, mime, ext = (
            rows_to_xlsx(columns, rows, title=row.Name or "Report", chart_png=png),
            _XLSX_MIME,
            ".xlsx",
        )
    recipients = parse_recipients(row.Recipients)
    if dry_run:
        print(
            f"[dry-run] schedule {row.ScheduleID} '{row.Name}' -> {recipients} "
            f"({len(rows)} rows, {fmt}, chart={'yes' if png else 'no'})"
        )
        return
    subject = f"nexora report: {row.Name}"
    body = (
        f"<p>Attached is your scheduled report "
        f"<strong>{html.escape(row.Name or 'Report')}</strong> "
        f"({len(rows)} rows), generated {now:%Y-%m-%d %H:%M} UTC.</p>"
    )
    inline = None
    if png:
        body += '<p><img src="cid:report-chart" alt="Report chart" style="max-width:640px"></p>'
        inline = [("report-chart", png, "image/png")]
    send_mail(recipients, subject, body,
              [(_safe_name(row.Name) + ext, data, mime)], inline_images=inline)
```

(Everything after — `compute_next_run`, the UPDATE — stays unchanged. Note `rows` from
`execute_definition` is a list, so `len(rows)` and the double use are fine.)

- [ ] **Step 2: Dry-run against INT** (needs at least one enabled schedule; if none is due,
  temporarily check the query by creating a schedule in the UI first):

```powershell
$env:ENVIRONMENT = "INT"; python ops/run_scheduled_reports.py --dry-run
```
Expected: `[dry-run] schedule ... chart=yes` for a report with 1–2 breakdowns, `chart=no`
for a totals-only report. (Restore `$env:ENVIRONMENT` afterwards if it was set differently.)

- [ ] **Step 3: Run the schedule unit suite** (guards `compute_next_run` etc. didn't move)

```powershell
python -m pytest tests/unit/test_reporting_schedule.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add ops/run_scheduled_reports.py
git commit -m "feat(reporting): scheduled mails embed a server-rendered chart inline and in the XLSX"
```

---

# PHASE 2 — Frontend (BLOCKED until the simple-guide plan's Tasks 6–8 are committed)

> Verify before starting: `git log --oneline -15` must show the in-flight plan's
> Adjust-in-wizard (Task 6), Back/exit (Task 7) and name-modal (Task 8) commits, and
> `git status` must be clean of `templates/js/_reporting_simple_js.html`.

### Task 7: "Show query" panels (Simple + Advanced)

**Files:**
- Modify: `templates/_reporting_simple.html` (result view)
- Modify: `templates/js/_reporting_simple_js.html`
- Modify: `templates/reporting.html` (Advanced results area)
- Modify: `templates/js/_reporting_js.html`
- Modify: `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Simple markup.** In `templates/_reporting_simple.html`, inside the result
  view, after the table card, add:

```html
      <div class="nx-card nx-card--pad reporting-sqlview" id="rsSqlView" hidden data-testid="rs-sql-view">
        <div class="reporting-sqlview-bar">
          <span>{{ _("Query sent to the database") }}</span>
          <button type="button" id="rsSqlCopy" class="reporting-link" data-testid="rs-sql-copy">{{ _("Copy") }}</button>
        </div>
        <pre id="rsSqlText"></pre>
        <p id="rsSqlParams" class="reporting-sqlview-params"></p>
      </div>
```

and in the result actions bar (next to the export button, before the exit ✕), add:

```html
        <button type="button" id="rsShowSql" class="reporting-link" hidden
                data-testid="rs-show-sql">{{ _("Show query") }}</button>
```

- [ ] **Step 2: Simple JS.** In `templates/js/_reporting_simple_js.html`:
  - Where the run response is consumed (in `runCurrent()`, after the JSON is parsed and
    `state.current` is in scope), stash the echo:

```js
    state.current.sql = data.sql || null;
    state.current.params = data.params || [];
```

  - Next to the other result-view resets (where `rsChartCard` etc. are hidden on a new
    run/error), hide the panel and toggle the button:

```js
    el('rsSqlView').hidden = true;
    el('rsShowSql').hidden = !state.current.sql;
    el('rsShowSql').textContent = I18N.showQuery;
```

  - Add to the `I18N` map (trailing-comma the previous entry):

```js
    showQuery: {{ _("Show query")|tojson }},
    hideQuery: {{ _("Hide query")|tojson }},
    sqlParamsLabel: {{ _("Parameters")|tojson }},
    copied: {{ _("Copied")|tojson }}
```

  - Near the other listeners:

```js
  el('rsShowSql').addEventListener('click', function () {
    var cur = state.current;
    if (!cur || !cur.sql) return;
    var view = el('rsSqlView');
    view.hidden = !view.hidden;
    this.textContent = view.hidden ? I18N.showQuery : I18N.hideQuery;
    if (!view.hidden) {
      el('rsSqlText').textContent = cur.sql;
      el('rsSqlParams').textContent = (cur.params || []).length
        ? I18N.sqlParamsLabel + ': ' + cur.params.map(function (p, i) {
            return (i + 1) + " = '" + String(p) + "'";
          }).join(', ')
        : '';
    }
  });
  el('rsSqlCopy').addEventListener('click', function () {
    var cur = state.current;
    if (!cur || !cur.sql) return;
    var text = cur.sql + '\n-- params: ' + JSON.stringify(cur.params || []);
    var btn = this;
    navigator.clipboard.writeText(text).then(function () {
      var prev = btn.textContent;
      btn.textContent = I18N.copied;
      setTimeout(function () { btn.textContent = prev; }, 1200);
    });
  });
```

- [ ] **Step 3: Advanced.** Mirror the same pattern in the Advanced pane:
  - `templates/reporting.html`: the same `reporting-sqlview` card (ids `rpSqlView`,
    `rpSqlText`, `rpSqlParams`, `rpSqlViewCopy`, test ids `reporting-sql-view` /
    `reporting-sql-view-copy`) after the results grid container, and a
    `<button id="rpShowSql" class="reporting-link" hidden data-testid="reporting-show-sql">{{ _("Show query") }}</button>`
    in the results toolbar (next to the export controls).
  - `templates/js/_reporting_js.html`: in `renderResults()` stash `data.sql`/`data.params`
    on the state object the results renderer uses; hide/show `rpShowSql` exactly as Simple
    does (`hidden = !sql`); add the same two listeners with the `rp*` ids. Note: SQL-kind
    sandbox runs get no `sql` key from `/api/reporting/sql/run`, so the button stays hidden
    there — intended (the editor already shows the query).

- [ ] **Step 4: CSS.** Append to `static/css/reporting.css` (shared section, used by both
  panes):

```css
.reporting-sqlview { margin-top: 12px; }
.reporting-sqlview-bar { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 13px; margin-bottom: 6px; }
.reporting-sqlview pre { font-family: ui-monospace, Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; max-height: 240px; overflow: auto; margin: 0; }
.reporting-sqlview-params { font-size: 12px; color: #6b7280; margin: 6px 0 0; }
```

- [ ] **Step 5: e2e test.** Append to `tests/e2e/test_reporting_simple.py` (table-source
  seeding fixture as in its neighbours):

```python
def test_show_query_reveals_sql(page, seeded_simple_source):
    """A result offers Show query, revealing the executed SELECT."""
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-wizard-run").click()
    show = page.get_by_test_id("rs-show-sql")
    expect(show).to_be_visible()
    show.click()
    expect(page.get_by_test_id("rs-sql-view")).to_be_visible()
    expect(page.locator("#rsSqlText")).to_contain_text("SELECT")
```

(Adapt the wizard-walk clicks to the file's then-current helpers — the in-flight plan may
have added a Continue step by the time this runs; see Task 8 note.)

- [ ] **Step 6: Restart + run**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py::test_show_query_reveals_sql -v
```
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html templates/reporting.html templates/js/_reporting_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): Show query panel on Simple and Advanced results"
```

---

### Task 8: Wizard — up to three breakdowns

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (breakdown step, `wizardDefinition()`, `wizardStateFromDefinition()`, summary)
- Modify: `templates/_reporting_simple.html` (breakdown step Continue button)
- Test: `tests/e2e/test_reporting_simple.py`

**Interaction change:** the breakdown step's buttons stop auto-advancing. They become
toggle chips (multi-select, max 3, at most one date); a **Continue** button advances.
"None — just the total" stays exclusive (picking it clears others and vice versa).
**Existing e2e tests that click one breakdown and expect auto-advance must be updated to
also click Continue** — sweep the file for `rs-breakdown-list` usages.

- [ ] **Step 1: State shape.** In `templates/js/_reporting_simple_js.html`, change the wizard
  state initialization in `startWizard()` from `breakdown: ...` to:

```js
    breakdowns: [],   // [{kind:'date'|'category', field}], max 3, <=1 date
```

and sweep the file for every `state.wiz.breakdown` read (renderBreakdownStep, summary
renderer, `wizardDefinition`, `reopenWizard`/step-restore logic from the in-flight Task 6)
— each becomes array logic per the steps below. Keep a temporary
`grep -n "wiz.breakdown" templates/js/_reporting_simple_js.html` checklist; the task is
done only when every hit is migrated.

- [ ] **Step 2: Markup.** In `templates/_reporting_simple.html`, inside the breakdown step,
  after the breakdown list element add:

```html
        <p class="reporting-simple-hint">{{ _("Pick up to three — the first is the chart axis, the second becomes the colored series.") }}</p>
        <button type="button" id="rsBreakdownNext" class="nx-btn nx-btn--primary" data-testid="rs-breakdown-next">{{ _("Continue") }}</button>
```

- [ ] **Step 3: Toggle-chip behavior.** In `renderBreakdownStep()`, where each choice button
  currently sets `state.wiz.breakdown = {...}` and advances, replace with toggle logic
  (same for the date option, category options, and none-option — shown here once;
  `bd` is the breakdown the clicked button represents, `{kind:'none'}` for the
  total-only chip):

```js
      var toggleBreakdown = function (bd, btn) {
        var w = state.wiz;
        if (bd.kind === 'none') {            // exclusive with everything
          w.breakdowns = [];
          markSelections();
          return;
        }
        var idx = w.breakdowns.findIndex(function (b) {
          return b.kind === bd.kind && (!b.field || !bd.field || b.field.field === bd.field.field);
        });
        if (idx !== -1) { w.breakdowns.splice(idx, 1); markSelections(); return; }
        if (bd.kind === 'date') {            // at most one date pick
          w.breakdowns = w.breakdowns.filter(function (b) { return b.kind !== 'date'; });
        }
        if (w.breakdowns.length >= 3) return; // cap: ignore a 4th pick
        w.breakdowns.push(bd);
        markSelections();
      };
```

`markSelections()` re-applies the `is-selected` class on every chip from
`state.wiz.breakdowns` (and marks the none-chip selected when the array is empty) —
implement it next to the render loop, reusing the step's existing selected-state idiom from
the in-flight Task 6 work. Show the grain `<select>` (`rsGrain`) whenever a date breakdown
is in the array, hide otherwise. Wire `rsBreakdownNext` to the step-advance call the chips
used to make.

- [ ] **Step 4: Definition emission.** In `wizardDefinition()`, replace the single-breakdown
  branch with (preserving the function's existing filter/scope/rowLimit emission):

```js
    var columns = [], sort = [];
    var bds = (w.breakdowns || []).slice();
    bds.sort(function (a, b) {               // date first: it is the chart axis
      return (a.kind === 'date' ? 0 : 1) - (b.kind === 'date' ? 0 : 1);
    });
    bds.slice(0, 3).forEach(function (b) {
      if (b.kind === 'date') {
        columns.push({ field: b.field.field, grain: el('rsGrain').value || 'month' });
        sort.push({ field: b.field.field, dir: 'asc' });
      } else {
        columns.push({ field: b.field.field });
      }
    });
    if (!sort.length && columns.length) {
      sort.push({ field: w.measure.code, dir: 'desc' });
    }
```

- [ ] **Step 5: Reverse-mapper.** In `wizardStateFromDefinition()` (in-flight Task 6
  deliverable), replace the `if (cols.length > 1) return null;` gate and the single-column
  mapping with:

```js
    if (cols.length > 3) return null;
    var breakdowns = [], grain = null, dateSeen = false;
    for (var ci = 0; ci < cols.length; ci++) {
      var f = (src.fields || []).find(function (x) { return x.field === cols[ci].field; });
      if (!f) return null;
      if (cols[ci].grain) {
        if (!f.grainable || dateSeen) return null;
        dateSeen = true;
        breakdowns.push({ kind: 'date', field: f });
        grain = cols[ci].grain;
      } else {
        breakdowns.push({ kind: 'category', field: f });
      }
    }
```

and return `breakdowns: breakdowns` in the `wiz` object instead of `breakdown`.

- [ ] **Step 6: Summary step.** Where the summary renders the breakdown choice, list all of
  them joined by " → " (`state.wiz.breakdowns.map(function (b) { return b.field.label; }).join(' → ')`),
  falling back to the existing "just the total" wording when the array is empty.

- [ ] **Step 7: e2e.** Update existing breakdown-clicking tests to add
  `page.get_by_test_id("rs-breakdown-next").click()` after their pick, then append:

```python
def test_wizard_two_breakdowns(page, seeded_simple_source):
    """Two category breakdowns produce a 3-column grouped result."""
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_role("button").first.click()
    chips = page.get_by_test_id("rs-breakdown-list").get_by_role("button")
    chips.nth(0).click()
    chips.nth(1).click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    headers = page.locator("#rsTable thead th")
    expect(headers).to_have_count(3)   # dim1, dim2, metric
```

(Adapt the table locator to the Simple result table's real id/test-id; the seeded table
source must expose at least two string fields — extend the seeding fixture's column list if
it only maps one.)

- [ ] **Step 8: Restart server, run the Simple e2e file**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v
```
Expected: all PASS (including the updated older tests).

- [ ] **Step 9: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): wizard supports up to three breakdowns (date + categories)"
```

---

### Task 9: Multi-series charts (2 dims → series; 3 dims → note)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`mountChart()`, `renderChart()`, chart tools)
- Modify: `templates/_reporting_simple.html` (stacked-bar button)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Pivot in `mountChart()`.** After the existing no-chart guards (`!dims`,
  `!rows.length`, `!window.Chart` — in-flight Task 3/4 shapes), add the dimension branch
  before the existing single-dim labels/datasets construction:

```js
    if (dims >= 3) { chartCardNote(I18N.noChartThreeDims); return; }
    if (dims === 2) {
      var metricIdx = columns.length - (def.metrics || []).length;
      var xOrder = [], cell = {}, seriesTot = {};
      rows.forEach(function (r) {
        var x = String(r[0] == null ? '' : r[0]).slice(0, isDate ? 10 : 200);
        var s = String(r[1] == null ? '' : r[1]);
        var v = Number(r[metricIdx]) || 0;
        if (!cell[x]) { xOrder.push(x); cell[x] = {}; }
        cell[x][s] = (cell[x][s] || 0) + v;
        seriesTot[s] = (seriesTot[s] || 0) + v;
      });
      if (xOrder.length > 50) { chartCardNote(I18N.noChartTooManyPoints); return; }
      var series = Object.keys(seriesTot).sort(function (a, b) {
        return seriesTot[b] - seriesTot[a];
      });
      if (series.length > 12) {
        el('rsChartNote').textContent =
          I18N.chartSeriesCapped.replace('{shown}', '12').replace('{n}', String(series.length));
        el('rsChartNote').hidden = false;
        series = series.slice(0, 12);
      }
      state.chartData = {
        labels: xOrder,
        datasets: series.map(function (s, i) {
          return {
            label: s,
            data: xOrder.map(function (x) { return cell[x][s] || 0; }),
            borderColor: SIMPLE_PALETTE[i % SIMPLE_PALETTE.length],
            backgroundColor: SIMPLE_PALETTE[i % SIMPLE_PALETTE.length],
            tension: .25
          };
        }),
        multiSeries: true
      };
      el('rsChartCard').hidden = false;
      el('rsChartTools').hidden = false;
      renderChart(def.chartType || (isDate ? 'line' : 'bar'));
      return;
    }
```

Set `multiSeries: false` in the existing single-dim `state.chartData` assignment.

- [ ] **Step 2: Stacked option + per-series button visibility.** In
  `templates/_reporting_simple.html`'s chart tools, add after the line button:

```html
          <button type="button" class="reporting-chartbtn" data-type="stacked" hidden title="{{ _('Stacked bar chart') }}" aria-label="{{ _('Stacked bar chart') }}" data-testid="rs-chart-stacked"><i class="fas fa-layer-group" aria-hidden="true"></i></button>
```

In `renderChart(type)`:

```js
    var multi = !!d.multiSeries;
    if (multi && (type === 'pie' || type === 'doughnut')) type = 'bar';
    var stacked = type === 'stacked';
    var chartJsType = stacked ? 'bar' : type;
```

use `chartJsType` in the `new Chart(...)` call, and extend its options with:

```js
      options: { responsive: true, maintainAspectRatio: false,
                 scales: (chartJsType === 'pie' || chartJsType === 'doughnut') ? {}
                   : { x: { stacked: stacked }, y: { stacked: stacked } },
                 plugins: { legend: { display: multi || circular || d.datasets.length > 1 } } }
```

after the chart mounts, set button visibility (pie/doughnut hidden for multi-series,
stacked shown only then) and the testability hook:

```js
    el('rsChartTools').querySelector('[data-type="pie"]').hidden = multi;
    el('rsChartTools').querySelector('[data-type="doughnut"]').hidden = multi;
    el('rsChartTools').querySelector('[data-type="stacked"]').hidden = !multi;
    el('rsChartCanvas').dataset.series = String(d.datasets.length);
```

(The existing circular-palette branch applies only when `!multi` — guard it.)

- [ ] **Step 3: i18n keys.** Add to the `I18N` map:

```js
    noChartThreeDims: {{ _("Charts support up to two breakdowns — the table shows all of them.")|tojson }},
    chartSeriesCapped: {{ _("Showing the {shown} largest of {n} series.")|tojson }}
```

- [ ] **Step 4: e2e.** Append:

```python
def test_two_breakdown_chart_has_series(page, seeded_simple_source):
    """A two-breakdown result charts with one dataset per second-dim value."""
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_role("button").first.click()
    chips = page.get_by_test_id("rs-breakdown-list").get_by_role("button")
    chips.nth(0).click()
    chips.nth(1).click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    canvas = page.locator("#rsChartCanvas")
    expect(canvas).to_be_visible()
    series = int(canvas.get_attribute("data-series"))
    assert series >= 2
    expect(page.get_by_test_id("rs-chart-stacked")).to_be_visible()
    expect(page.get_by_test_id("rs-chart-pie")).to_be_hidden()
```

- [ ] **Step 5: Restart server, run**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): multi-series charts for two breakdowns with stacked option"
```

---

### Task 10: Chart PNG button on Simple + chart-in-XLSX wiring

**Files:**
- Modify: `templates/_reporting_simple.html` (chart tools)
- Modify: `templates/js/_reporting_simple_js.html` (PNG helper, export body)
- Modify: `templates/js/_reporting_viz_js.html` (`chartPngDataUrl` accessor)
- Modify: `templates/js/_reporting_js.html` (`exportGridRows()`)
- Modify: `nx_lib/views/reporting.py` (`api_export()`, `api_export_grid()`, `_serialize_export()`)
- Test: `tests/integration/test_reporting_routes.py`, `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Integration test first.** Append to
  `tests/integration/test_reporting_routes.py` next to its existing export tests:

```python
_TINY_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
                 "2mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==")


def test_export_xlsx_embeds_chart_image(client_with_reporting_perms, table_source_definition):
    body = dict(table_source_definition,
                format="xlsx",
                chartImage="data:image/png;base64," + _TINY_PNG_B64)
    resp = client_with_reporting_perms.post("/api/reporting/export", json=body)
    assert resp.status_code == 200
    assert resp.data[:2] == b"PK"
    import io, zipfile
    with zipfile.ZipFile(io.BytesIO(resp.data)) as z:
        assert [n for n in z.namelist() if n.startswith("xl/media/")]


def test_export_ignores_garbage_chart_image(client_with_reporting_perms, table_source_definition):
    body = dict(table_source_definition, format="xlsx", chartImage="data:image/png;base64,@@@not-b64@@@")
    resp = client_with_reporting_perms.post("/api/reporting/export", json=body)
    assert resp.status_code == 200       # export still succeeds, chartless
    assert resp.data[:2] == b"PK"
```

Run, watch the first FAIL (no media in zip).

- [ ] **Step 2: Backend.** In `nx_lib/views/reporting.py`:
  - Add a parser near `_serialize_export()`:

```python
_CHART_IMAGE_PREFIX = "data:image/png;base64,"
_CHART_IMAGE_MAX = 2_000_000  # bytes, decoded


def _parse_chart_image(value):
    """Decode a client-supplied chart data-URL; None on anything dubious."""
    if not isinstance(value, str) or not value.startswith(_CHART_IMAGE_PREFIX):
        return None
    try:
        raw = base64.b64decode(value[len(_CHART_IMAGE_PREFIX):], validate=True)
    except Exception:
        return None
    if len(raw) > _CHART_IMAGE_MAX or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return raw
```

(`import base64` at the top if not already imported.)
  - In `api_export()`: pop the key before validation/preparation —
    `chart_png = _parse_chart_image(rd.pop("chartImage", None))` — and pass
    `chart_png=chart_png` through `_serialize_export(...)`.
  - In `api_export_grid()`: same pop + pass-through.
  - In `_serialize_export()`: accept `chart_png=None` and forward it to
    `rows_to_xlsx(..., chart_png=chart_png)` in the xlsx branch only.

Run Step 1's tests again — PASS.

- [ ] **Step 3: Simple PNG button + export wiring.** In
  `templates/_reporting_simple.html` chart tools, after the stacked button:

```html
          <button type="button" class="reporting-chartbtn" id="rsChartPng" title="{{ _('Download chart as image') }}" aria-label="{{ _('Download chart as image') }}" data-testid="rs-chart-png"><i class="fas fa-download" aria-hidden="true"></i></button>
```

In `templates/js/_reporting_simple_js.html`, next to `renderChart()`:

```js
  function chartPngDataUrl() {
    if (!state.chart) return null;
    var src = el('rsChartCanvas');
    var c = document.createElement('canvas');
    c.width = src.width; c.height = src.height;
    var ctx = c.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(src, 0, 0);
    return c.toDataURL('image/png');
  }
  el('rsChartPng').addEventListener('click', function () {
    var url = chartPngDataUrl();
    if (!url) return;
    var a = document.createElement('a');
    a.href = url;
    a.download = ((state.current && state.current.name) || 'report') + '-chart.png';
    a.click();
  });
```

In the `#rsExport` click handler, where the POST body is assembled from
`state.current.def`, add (xlsx only):

```js
    if (fmt === 'xlsx') {
      var png = chartPngDataUrl();
      if (png) body.chartImage = png;
    }
```

(`fmt` is whatever the handler already calls its format value; the body object already
carries the definition + `format`.)

- [ ] **Step 4: Advanced wiring.** In `templates/js/_reporting_viz_js.html`, next to
  `exportChartPng` (which already builds the white-background canvas), expose the data-URL
  on the `ReportingViz` API object:

```js
    chartPngDataUrl: function () {
      if (!lastChartCanvas) return null;
      var c = document.createElement('canvas');
      c.width = lastChartCanvas.width; c.height = lastChartCanvas.height;
      var ctx = c.getContext('2d');
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(lastChartCanvas, 0, 0);
      return c.toDataURL('image/png');
    },
```

(refactor `exportChartPng` to call it). In `templates/js/_reporting_js.html`
`exportGridRows()`, when format is xlsx:

```js
    var png = window.ReportingViz && ReportingViz.chartPngDataUrl();
    if (png && exportFormat() === 'xlsx') body.chartImage = png;
```

and the same two lines in `exportPivot()`'s body assembly.

- [ ] **Step 5: e2e download test.** Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_chart_png_download(page, seeded_simple_source):
    """The chart toolbar offers a PNG download of the current chart."""
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-chart-card")).to_be_visible()
    with page.expect_download() as dl:
        page.get_by_test_id("rs-chart-png").click()
    assert dl.value.suggested_filename.endswith("-chart.png")
```

- [ ] **Step 6: Restart server, run everything touched**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/integration/test_reporting_routes.py tests/e2e/test_reporting_simple.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html templates/js/_reporting_viz_js.html templates/js/_reporting_js.html nx_lib/views/reporting.py tests/integration/test_reporting_routes.py tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): chart PNG download on Simple and chart embedding in XLSX export"
```

---

# PHASE 3 — Chores

### Task 11: i18n — translate the new strings (de/fr/it)

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

New msgids from Tasks 7–10 (reuse existing entries if a msgid already exists — check
`messages.pot` first; "Continue" in particular may already be translated):

| msgid | de | fr | it |
|---|---|---|---|
| `Show query` | `SQL anzeigen` | `Afficher la requête` | `Mostra query` |
| `Hide query` | `SQL ausblenden` | `Masquer la requête` | `Nascondi query` |
| `Query sent to the database` | `An die Datenbank gesendete Abfrage` | `Requête envoyée à la base de données` | `Query inviata al database` |
| `Copy` | `Kopieren` | `Copier` | `Copia` |
| `Copied` | `Kopiert` | `Copié` | `Copiato` |
| `Parameters` | `Parameter` | `Paramètres` | `Parametri` |
| `Pick up to three — the first is the chart axis, the second becomes the colored series.` | `Wählen Sie bis zu drei — die erste ist die Diagrammachse, die zweite wird zur farbigen Serie.` | `Choisissez-en jusqu'à trois — la première est l'axe du graphique, la deuxième devient la série colorée.` | `Scegli fino a tre — la prima è l'asse del grafico, la seconda diventa la serie colorata.` |
| `Continue` | `Weiter` | `Continuer` | `Continua` |
| `Charts support up to two breakdowns — the table shows all of them.` | `Diagramme unterstützen bis zu zwei Aufschlüsselungen — die Tabelle zeigt alle.` | `Les graphiques prennent en charge jusqu'à deux ventilations — le tableau les montre toutes.` | `I grafici supportano fino a due suddivisioni — la tabella le mostra tutte.` |
| `Showing the {shown} largest of {n} series.` | `Die {shown} grössten von {n} Serien werden angezeigt.` | `Affichage des {shown} plus grandes séries sur {n}.` | `Mostrate le {shown} serie più grandi su {n}.` |
| `Stacked bar chart` | `Gestapeltes Balkendiagramm` | `Graphique à barres empilées` | `Grafico a barre impilate` |
| `Download chart as image` | `Diagramm als Bild herunterladen` | `Télécharger le graphique en image` | `Scarica il grafico come immagine` |

- [ ] **Step 1: Extract + update**

```powershell
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step 2: Fill in the translations** above in each locale's `messages.po`
  (set msgstr, remove any `#, fuzzy` markers on these entries).

- [ ] **Step 3: Compile + test**

```powershell
pybabel compile -d translations
python -m pytest tests/unit/test_translations.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add messages.pot translations
git commit -m "chore(i18n): translate show-query, multi-breakdown and chart-export strings (de/fr/it)"
```

---

### Task 12: Docs + changelog

**Files:**
- Modify: `docs/howto/reporting.md`
- Modify: `CHANGELOG.md` (`[Unreleased]`)

- [ ] **Step 1: `docs/howto/reporting.md`:**
  - Simple-tab wizard bullet: change the breakdown sentence to say up to **three**
    breakdowns can be combined (at most one date), the first being the chart axis and the
    second the colored series; charts cap at 50 axis values and the 12 largest series; a
    third breakdown shows in the table only.
  - Result-view bullet: mention the **Show query** toggle (executed SQL + bind parameters,
    visible to anyone who can run the report) and the chart-toolbar **PNG download**.
  - Export section: XLSX now carries a title block, generation timestamp and — when a chart
    is on screen — the chart image above the data; CSV unchanged.
  - Scheduled reports section: mails embed a server-rendered chart of the report (when it
    has 1–2 breakdowns) inline in the body and inside the attached XLSX; rendering failures
    degrade to the previous chartless mail.
- [ ] **Step 2: `CHANGELOG.md`** under `[Unreleased]`:

```markdown
### Added
- Reporting: "Show query" on Simple and Advanced results — reveals the executed SQL and bind parameters, with copy.
- Reporting Simple wizard: up to three breakdowns (at most one date); two-breakdown results chart as multi-series with a stacked-bar option.
- Reporting: XLSX exports gain a title block and embed the on-screen chart; Simple gets a chart-PNG download button.
- Reporting: scheduled report mails embed a server-rendered chart (matplotlib) inline and in the attached XLSX.

### Changed
- Reporting: XLSX export layout — title and metadata block above a styled, frozen header row.
```

- [ ] **Step 3: Commit**

```powershell
git add docs/howto/reporting.md CHANGELOG.md
git commit -m "docs(reporting): document show-query, multi-breakdowns and rich export"
```

---

### Task 13: Full verification + INT walkthrough

- [ ] **Step 1: Full suite**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/ -v
```
Expected: all green.

- [ ] **Step 2: Browser walkthrough on INT** (restart first — template cache):

```powershell
nx -u -b --loginas:admin
```

Capture to `var/screenshots/` (send to the user if remote):
1. The owner's reference report — Document count, breakdowns *export date (per month)* +
   *Document Source*, range last 3 months: multi-series chart (`rich-01-two-breakdowns.png`)
2. Same result stacked (`rich-02-stacked.png`)
3. Show query panel open with SQL + params (`rich-03-show-query.png`)
4. Three breakdowns: table + "charts support up to two" note (`rich-04-three-dims-note.png`)
5. Downloaded XLSX opened — title block + embedded chart (`rich-05-xlsx-chart.png`)
6. Chart PNG download (`rich-06-chart-png.png`)

- [ ] **Step 3: Scheduled-mail check on INT:** create a schedule on the reference report,
  then:

```powershell
$env:ENVIRONMENT = "INT"; python ops/run_scheduled_reports.py --once
```

Verify the received mail: chart inline in the body, XLSX attachment with the chart inside.
(Restore the prior `ENVIRONMENT` value if it was set.)

- [ ] **Step 4: PROD readiness notes** (no action here, just confirm):
  - matplotlib installs via `deploy.yml` line 18 (`pip install -r requirements.txt`) — no
    manual step.
  - `var/mpl-cache` self-creates at first import and sits inside the existing
    `D:\sydoc\nexora\var` Defender exclusion.

- [ ] **Step 5: Clean tree + summary**

```powershell
git status
git log --oneline -15
```

Do not push and do not open a PR if this is a remote session (owner reviews locally first).

---

## Self-review (done at plan time)

- **Spec coverage:** show-the-query → T2 (backend) + T7 (UI); multi-category breakdowns →
  T1 (test gap) + T8 (wizard) + T9 (charts); export upgrades → T3 (XLSX) + T4 (renderer) +
  T5 (mail) + T6 (scheduler) + T10 (buttons/wiring); chores → T11–T13. PDF deliberately
  absent (owner deselected it).
- **Type consistency:** `rows_to_xlsx(..., chart_png=None, generated_at=None)` defined in
  T3, consumed in T6 (runner) and T10 (`_serialize_export`); `render_chart_png(definition,
  columns, rows)` defined in T4, consumed in T6; `_build_message(..., inline_images)` defined
  in T5, consumed via `send_mail(..., inline_images=...)` in T6; `chartPngDataUrl()` defined
  in T10 Simple JS and as `ReportingViz.chartPngDataUrl()` for Advanced; `state.wiz.breakdowns`
  array introduced in T8 and read by T9's chart pivot via the emitted definition (`dims`
  count), not directly.
- **Known caveats accepted:** breakdown step gains a Continue click (existing e2e updated in
  T8); XLSX layout change breaks layout-coupled assertions (updated deliberately in T3 Step 4);
  matplotlib e-mail charts are not pixel-identical to the web charts (accepted in spec);
  3-dim results never chart (correctness over cleverness for distinct-count metrics).
- **Fixture placeholders:** T1/T2/T10 test snippets reference the host files' existing
  fixtures by intent (`_aggregate_rd`, `client_with_reporting_perms`, …) with explicit
  instructions to adapt names — same convention the in-flight simple-guide plan uses.
