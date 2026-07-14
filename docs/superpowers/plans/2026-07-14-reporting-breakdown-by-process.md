# Reporting: Break Down by Process — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Executor model: Sonnet. Multi-agent planning run (explore → dual drafts → adversarial red-team → merge); **every file path, symbol, and quoted snippet below was Grep/Read-verified against the worktree at feature/2.5.64 HEAD (`c144516`) on 2026-07-14** — trust the anchors, but re-Grep before editing since line numbers drift (this plan quotes code, never line numbers).

**Goal:** The Simple-tab reporting wizard's "2. Break it down by…" step gets a **Process** dimension chip (in this deployment each Octo process = an actual Sydoc client, so this delivers per-client numbers), offered first, localized in all four languages, and working end-to-end: chip → chart/table → drill-through → CSV/XLSX export → save/share/schedule.

**Architecture:** The backend already supports this completely — `nx_lib/reporting/catalog.py` synthesizes `processname` into every user's catalog (`availability["processname"] = list(allowed_processes)`), `nx_lib/reporting/query.py` materializes it as a parameterized constant per UNION-ALL subquery (`? AS [processname]`) and the aggregate wrapper (`build_aggregate_sql` in `nx_lib/reporting/semantic.py`) groups over it, and the Advanced tab, drill-through smart columns, exports and scheduler all consume it today. The Simple wizard alone hides it, via **two** client-side exclusions in `renderBreakdownStep()` of `templates/js/_reporting_simple_js.html` (a leftover global filter from the original wizard commit `5ac43fa` plus the `processname: 1` entry in `DOCPROC_DIM_HIDE` from curation commit `a61baa8` — both hashes verified with `git log -S`). The fix is a curation change in that one JS partial (unhide + order first + raise the exactly-saturated 12-chip cap to 16 with headroom) plus one data-only migration seeding the DB-driven i18n label ("Process"/"Prozess"/"Processus"/"Processo") so every catalog surface stops falling back to the title-case default "Processname".

**Tech Stack:** Jinja2 JS partial (`templates/js/_reporting_simple_js.html`), Python 3.13 / Flask reporting pipeline (`nx_lib/reporting/*` — untouched except tests), SQL Server migration under `sql/_migrations/NexoraDB/`, pytest unit + Playwright e2e (route-stub pattern driving the real wizard DOM), DB-driven labels via `dbo.Search_Field_Labels` (no gettext).

---

## Context an engineer needs (read first)

- **Where you work:** the already-created worktree `.claude/worktrees/plan-reporting-breakdown-by-process` (absolute: `C:\dev\nexora\.claude\worktrees\plan-reporting-breakdown-by-process`) on branch `plan/reporting-breakdown-by-process`, based on `feature/2.5.64` at `c144516` (verified clean at that HEAD). It is merged back into `feature/2.5.64` after execution. **Commit per task on this branch. Do NOT `git push` and do NOT open a PR** — the owner reviews, merges and pushes (the pre-push hook runs the full suite incl. Playwright e2e; the owner runs it).
- **Python for tests:** the worktree has **no `.venv`** (verified). Run all test commands from the worktree root using the main clone's interpreter: `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The `.venv` is test-only; the dev server runs global Python.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Every step quotes the exact code to find; re-`Grep` it if it has moved.
- **TDD is the house rule** — with one honest exception: Task 1 is a *characterization pin* of behavior the backend already has (it should pass immediately; a failure means stop and investigate). Task 3's e2e tests are genuine RED→GREEN against the real wizard DOM.
- **TEST env has NO Statistics DB**, so the `docprocessing` source can never be *run* in e2e — but only `/api/reporting/run` needs that DB; chip **rendering** needs only the catalogs. The established pattern in `tests/e2e/test_reporting_simple.py` stubs the network: `_stub_catalogs(page)` registers `page.route("**/api/reporting/sources", …)` + `"**/api/reporting/metrics"` **before `page.goto`** (its comment: "MUST be registered before page.goto: the Simple pane fetches the metrics catalog in initOnce() at rp:tabshown (page load)"), and `_stub_run_ok(page, capture=…)` stubs `**/api/reporting/run` and records payloads. The curation branch fires on `w.source.id === 'docprocessing'`, so Task 3 stubs a source with exactly that id and drives the **real chips** (`btn.dataset.bdKind` / `btn.dataset.bdField` are real DOM attributes). Live docprocessing behavior is verified in the browser on INT (Task 6).
- **Jinja template cache is process-lifetime.** The e2e harness starts its own fresh server per run (fine), but before any *manual* browser check restart the dev server (`nx -u`).
- **Migrations needed: YES — one data-only migration, next free number `0037`** (directory currently tops out at `0036_index_field_mapping_validation_user.sql`; **re-list `sql/_migrations/NexoraDB/` at execution time** and bump if taken). Must be idempotent (`IF NOT EXISTS` guard) — the pre-commit hook auto-applies it to INT and may re-run it. `*.sql` is pinned to LF by `.gitattributes` — write it with the Write tool, not shell heredocs. The INSERT is **data, not DDL**, so `sql/sync-from-db.py --check` should report no dump drift; if the hook flags a regenerated `sql/NexoraDB/Tables/dbo.Search_Field_Labels.sql` anyway, `git add` it into the same commit. `SQL_SYNC_SKIP=1 git commit …` only for INT-unreachable flakes, **never** `--no-verify`. **Worktree env caveat (verified while committing this plan):** gitignored `env/*.env` files exist only in the main clone, so in this worktree the SQL hooks fail with "Missing DB_SERVER_PRD / DB_UID / DB_PWD in env". Before Task 2, copy the env files locally (`Copy-Item C:\dev\nexora\env\INT.env env\INT.env` — gitignored, safe) so the hook can actually apply `0037` to INT; only if INT itself is unreachable fall back to `SQL_SYNC_SKIP=1` and then run `C:\dev\nexora\.venv\Scripts\python scripts/db-migrate.py --env INT` from the main clone afterwards (Task 6's prereq depends on the label being live on INT).
- **i18n: NO pybabel cycle.** The chip label is DB-driven i18n (`Search_Field_Labels` four language columns, read unfiltered by `fetch_docprocessing_catalog` — the reporting catalog does not consult `IsSensitive`). This feature introduces **zero new `_()` msgids** — the docs/changelog edits are English-only files. If you deviate and add a `_()` string, you must run the full `/nx-i18n` extract→update→translate(de/fr/it, non-fuzzy)→compile cycle or `tests/unit/test_translations.py` fails.
- **Sequencing vs in-flight 2.5.64 work:** do NOT touch `templates/js/_reporting_drill_js.html` — drill-through just merged (`14a1e7b` + fix `c144516`) and the main clone has further uncommitted edits to it (plus `static/css/reporting.css` and `tests/integration/test_workitems_routes.py`). This plan touches none of those files, so the merge-back should be conflict-free; the owner reconciles ordering at merge time. Drill works with a processname series today with no changes (its `SMART_FIELDS = ['workitem_id', 'processname', 'import_date', 'export_date']` already leads with it).
- **No new permission.** Which process names a user can ever see is already bounded by the `reporting.scope.process.*` grants — `fetch_docprocessing_catalog` synthesizes availability from exactly that allow-set, and the effective scope drops out-of-grant processes server-side. `page_visibility()` untouched.
- **No `deploy.yml` changes** — the migration lives under `sql/` and docs under `docs/`, both already handled by the deploy pipeline.
- **gitlint:** conventional-commit title, imperative, ≤72 chars, no trailing period, non-empty body wrapped ≤100 chars. Commit with `git commit -F - <<'EOF' … EOF` via the Bash tool.
- **Commit trailer names the EXECUTING model.** Repo history stamps the model that actually ran the work (`git log` trailers show only `Claude Opus 4.8 <noreply@anthropic.com>` and `Claude Sonnet 5 <noreply@anthropic.com>`). The commit blocks below use `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` to match the declared executor; if a different model executes this plan, substitute its real name — never stamp a model that didn't run the work.
- **Pre-commit hooks** (`ruff`, `ruff-format`, `gitlint`, `sql-migrate-int`, `sql-sync-check`) run on every commit; the migration is auto-applied to INT at Task 2's commit.
- **Before running the e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py` (stale NEXORA_TEST state fails order-dependent e2e tests).

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Unhide = remove BOTH exclusions** in `renderBreakdownStep()`: the global `&& f.field !== 'processname'` in the `catFields` filter and the `processname: 1` entry in `DOCPROC_DIM_HIDE`. | Two independent gates exist (leftover from `5ac43fa` + added by `a61baa8`); removing only one leaves the chip hidden. Partial revert of `a61baa8`, whose "noise" classification is invalidated by the deployment context (process = client). |
| D2 | **`'processname'` goes FIRST in `DOCPROC_DIM_ORDER`.** | "Per client" is the headline ask; the original wizard shipped with processname at the front. |
| D3 | **Raise the chip cap `slice(0, 12)` → `slice(0, 16)`, for all sources, pinned by a dedicated e2e test.** | The docprocessing list is already saturated at exactly 12 chips (7 ordered + 5 alphabetical, per the user's screenshot). Unhiding alone puts an un-ordered chip at position 13 → sliced away → **the naive fix silently does nothing**; with processname ordered first, cap 12 would instead evict the 12th chip (Creditor Name). A cap of exactly 13 would be zero-slack — the *next* doc-field added to SearchConfig would silently re-create the same trap. 16 keeps headroom. The slice is unconditional (applies to every source), so table-provider sources with 13–16 string columns gain chips too — a deliberate, documented, and test-pinned side effect (see Gotchas + CHANGELOG). |
| D4 | **Label via migration `0037`** seeding `Search_Field_Labels` row `('processname', 'Process', 'Prozess', 'Processus', 'Processo', 0)`. | The 0035-established "labels are DB-driven i18n" pattern. Without it the chip reads the `fk.replace("_", " ").title()` fallback **"Processname"** (`build_catalog`: `"label": labels.get(fk) or fk.replace("_", " ").title()`). One row fixes the Simple chip, Advanced field panel, drill drawer header, and CSV header defaults at once. Translations lifted verbatim from the existing non-fuzzy `msgid "Process"` in the de/fr/it `.po` files (verified: "Prozess"/"Processus"/"Processo"). Rejected alternative: a gettext patch in `fetch_docprocessing_catalog` (code special-case, diverges from the docfield-label convention). |
| D5 | **Label text is "Process", not "Client".** | The wizard already shows a **"Client"** chip (a SearchConfig doc-field, visible in the user's screenshot) — two "Client" chips would collide semantically. Re-wording later is a data-only `UPDATE` (Owner action 1). |
| D6 | **Values stay raw process ids** (`compass.01_Invoice_SAP`-style) in chart axis/legend, table, drill header, CSV. | The projected value IS `cfg["process"]`. No friendly-name mapping exists anywhere (only `_humanize_process_id` in `nx_lib/reporting/ai_schema.py`, AI-prompt-only). New scope → Owner action 2, not this diff. |
| D7 | **Zero backend changes; two characterization unit tests** pin `? AS [processname]` + `GROUP BY [processname]` (one-dim) and `GROUP BY [doctype], [processname]` (two-dim, the "colored series" wizard shape) + per-subquery constant params. | Query builder, validator, runner, drill (`_scope_by_processname` supports eq/ne/in/not_in), export and scheduler all already handle it; the Advanced tab offers it in production. Only processname *filter* tests exist today — nothing asserts the aggregate group-by path. |
| D8 | **No AI prompt change.** | `serialize_sources_catalog` already feeds processname to every AI surface. The system prompt's process-words-to-scope steering (`'Process ids in "allowed scope.processes" follow <client>.<NN_Name>; …'` in `nx_lib/reporting/ai.py`, verified) is left alone — adding a "per client ⇒ group by processname" sentence is speculative tuning, YAGNI until the owner reports the AI misrouting such asks (Owner action 3 has the recipe). |
| D9 | **e2e proves the user-visible behavior, not an extracted helper.** Tests stub the catalogs and assert on the real breakdown-step DOM (`[data-bd-field="processname"]` chips) and on the serialized `/api/reporting/run` payload. | A window-exposed pure-function seam (à la `ReportingSqlFormat`) would stay green even if the render call-site were botched — the red-team killed that approach. The network-stub seam reaches `renderBreakdownStep()` without any Statistics DB, so no refactor is needed and the diff stays minimal. |

---

## Owner actions (not for the executor)

1. **Label wording (optional).** Shipped default is "Process"/"Prozess"/"Processus"/"Processo". If you prefer client-flavored wording (e.g. "Client / Process", "Mandant"), it is a data-only change — `UPDATE dbo.Search_Field_Labels SET EnglishLabel = '…', GermanLabel = '…', … WHERE FieldKey = 'processname';` on INT+PROD (or a follow-up migration). Beware: the wizard already has a **"Client"** doc-field chip — an identical label would create two same-named chips.
2. **Friendly display names for process VALUES (optional, new scope).** Everything shows raw ids (`compass.01_Invoice_SAP`). If you want "Compass — Invoice SAP"-style names in charts/exports, say the word — it needs its own plan (a label column on Statconfig or a JS prettifier mirroring `_humanize_process_id`; no mapping exists today).
3. **AI tuning (optional).** If Surface A/B keeps answering "documents per client" by narrowing `scope.processes` instead of grouping by `processname`, the fix is one steering sentence in each of `_SYSTEM_DEF` and `_AGENT_SYSTEM` in `nx_lib/reporting/ai.py` (next to the quoted scope-steering sentence), TDD-able via the existing prompt-substring-pin pattern in `tests/unit/test_reporting_ai_agentic.py` — deliberately not in this diff.
4. **PROD rollout:** migration `0037` reaches PROD automatically on the next deploy after merge to main — the deploy workflow applies migrations before mirroring code, so the chip can never ship without its label.
5. **Review, merge `plan/reporting-breakdown-by-process` back into `feature/2.5.64`, and push** (this session is commit-only). Reminder: the drill-through merge (`14a1e7b`) still owes its own live browser pass — Task 6's INT session is a convenient moment to do both, but this plan only claims verification of the Process chip.

---

# PHASE 1 — Pin the backend contract (no behavior change)

### Task 1: Characterization tests — aggregate SQL over `processname`

**Files:**
- Modify: `tests/unit/test_reporting_query.py` (append; fixtures `PROCESS_CONFIGS` / `FIELD_COL_MAPS` / `_rd` already exist at the top of the file, and `build_table_query` is imported at module top)

**Interfaces:**
- Consumes: `build_table_query(rd, process_configs, field_col_maps, row_cap=…, resolved_metrics=…)` from `nx_lib/reporting/query.py` (unchanged).
- Produces: a pinned contract the new wizard chip depends on — `? AS [processname]` projected per subquery, `GROUP BY [processname]` (and `GROUP BY [doctype], [processname]` for the two-breakdown series shape) in the aggregate wrapper, one bound constant per process config.

- [ ] **Step 1 — Write the tests.** Append to `tests/unit/test_reporting_query.py`, right after the existing `test_docprocessing_aggregate_wraps_union` (which pins the same shape for `doctype` and is the model — it asserts `sql.startswith("SELECT TOP (100) [doctype], COUNT(*) AS [doc_count] FROM (")`):

```python
def test_docprocessing_aggregate_groups_by_processname():
    # Pins the contract the Simple wizard's new per-process chip relies on:
    # processname is synthesized as a parameterized constant per UNION-ALL
    # subquery and grouped in the aggregate wrapper. Characterization test --
    # the backend supports this today (Advanced tab exercises it in prod);
    # only processname *filter* tests existed before.
    rd = _rd(
        columns=[{"field": "processname"}],
        filters=[],
        sort=[{"field": "doc_count", "dir": "desc"}],
    )
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql, params = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert sql.startswith("SELECT TOP (100) [processname], COUNT(*) AS [doc_count] FROM (")
    assert sql.rstrip().endswith("GROUP BY [processname] ORDER BY [doc_count] DESC")
    assert sql.count("? AS [processname]") == 2  # one bound constant per subquery
    assert params == ["acme.inv", "acme.hr"]


def test_docprocessing_aggregate_processname_as_second_dim():
    # Two-breakdown wizard shape: category axis + processname colored series.
    rd = _rd(columns=[{"field": "doctype"}, {"field": "processname"}], filters=[], sort=[])
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql, params = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=50, resolved_metrics=resolved
    )
    assert "GROUP BY [doctype], [processname]" in sql
    assert params == ["acme.inv", "acme.hr"]
```

- [ ] **Step 2 — Run, expect PASS immediately** (this is a pin, not a RED — if either FAILS, STOP: the backend assumption of this whole plan is wrong; investigate `build_table_query` / `build_aggregate_sql` before touching the frontend, and do not "fix" the test to match):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_query.py -k processname -q`
Expected: `5 passed` (the 3 pre-existing processname *filter* tests + these 2)

- [ ] **Step 3 — Run the whole file to prove no collateral damage:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_query.py -q`
Expected: all passed

- [ ] **Step 4 — Commit:**

```bash
git add tests/unit/test_reporting_query.py
git commit -F - <<'EOF'
test(reporting): pin processname group-by aggregate SQL contract

Characterization pins for the contract the Simple wizard's upcoming
per-process breakdown chip relies on: build_table_query projects
processname as a parameterized constant per UNION-ALL subquery
(? AS [processname], one param per process config) and the metric
wrapper groups over it -- GROUP BY [processname] one-dim, and
GROUP BY [doctype], [processname] as the second (series) dim.
Behavior already shipped (Advanced tab); only processname filter
tests existed before, nothing asserted the aggregate path.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — DB-driven label (migration)

### Task 2: Migration 0037 — localized "Process" label row

**Files:**
- Create: `sql/_migrations/NexoraDB/0037_reporting_processname_label.sql`
- (Only if the hook flags drift, which is not expected for a data-only INSERT) `git add` the regenerated `sql/NexoraDB/Tables/dbo.Search_Field_Labels.sql`

**Interfaces:**
- Produces: a `dbo.Search_Field_Labels` row `FieldKey='processname'` (EN "Process", DE "Prozess", FR "Processus", IT "Processo", `IsSensitive=0`). Consumed by `build_catalog` in `nx_lib/reporting/catalog.py` via `"label": labels.get(fk) or fk.replace("_", " ").title()` — so every catalog surface (Simple chip, Advanced field panel, drill header, CSV default header) shows the localized label instead of the "Processname" fallback.

Why this is safe for the workitems page: its doc-field dropdown is driven by SearchConfig `col_*` availability, and no `col_processname` column exists — `Search_Field_Labels` is only a lookup map there, so the new row can never surface a phantom workitems filter. The `FieldKey` must be exactly lowercase `processname` to match the catalog's availability key (`availability["processname"] = list(allowed_processes)` in `fetch_docprocessing_catalog`). Column list verified against `sql/NexoraDB/Tables/dbo.Search_Field_Labels.sql` (`FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive` — `IsSensitive` is NOT NULL with DEFAULT(0); set it explicitly anyway).

- [ ] **Step 1 — Re-verify the number is free:** list `sql/_migrations/NexoraDB/`; the directory currently tops out at `0036_index_field_mapping_validation_user.sql`. If `0037_*` exists, use the next integer and adjust the filename everywhere in this task.
- [ ] **Step 2 — Write the migration** (Write tool, LF):

```sql
-- 0037_reporting_processname_label.sql
-- Localized label for the reporting catalog's synthetic 'processname'
-- dimension (labels are DB-driven i18n via Search_Field_Labels; without a
-- row the catalog falls back to the title-cased key "Processname").
-- The Simple-tab wizard un-hides this dimension in the same release: each
-- Octo process corresponds to an actual client, so "break down by Process"
-- delivers per-client numbers. Deliberately NOT labeled "Client" -- a
-- 'client' doc-field chip already exists in the wizard.
-- Safe for the workitems doc-field UI: no col_processname exists in
-- SearchConfig, so this row can never surface a phantom search filter.

IF NOT EXISTS (SELECT 1 FROM dbo.Search_Field_Labels WHERE FieldKey = 'processname')
    INSERT INTO dbo.Search_Field_Labels (FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive)
    VALUES ('processname', 'Process', 'Prozess', 'Processus', 'Processo', 0);
GO
```

- [ ] **Step 3 — Commit** (the `sql-migrate-int` hook auto-applies it to INT; the INSERT is data-only so `sql-sync-check` should report no dump drift — if it does flag the Tables dump, `git add` it and re-commit):

```bash
git add sql/_migrations/NexoraDB/0037_reporting_processname_label.sql
git commit -F - <<'EOF'
feat(db): localized Process label for reporting processname (0037)

Seed dbo.Search_Field_Labels with FieldKey 'processname'
(Process/Prozess/Processus/Processo, IsSensitive 0) so the reporting
catalog's synthesized per-process dimension gets a proper DB-driven
i18n label on every surface (Simple wizard chip, Advanced field panel,
drill header, CSV headers) instead of the "Processname" title-case
fallback. Idempotent (IF NOT EXISTS); data-only, no DDL change.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

**Verify:** on INT (read-only), `SELECT EnglishLabel, GermanLabel FROM dbo.Search_Field_Labels WHERE FieldKey = 'processname'` → `Process | Prozess`.

---

# PHASE 3 — Un-hide the wizard chip (frontend, TDD)

### Task 3: e2e RED → curation change → GREEN

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (three surgical edits in the curation constants + `renderBreakdownStep()`)
- Test: `tests/e2e/test_reporting_simple.py` (three new tests + stub data + one stub helper, appended near the existing `WIZ_STUB_SOURCES` / `_stub_catalogs` block)

**Interfaces:**
- Consumes: existing e2e helpers in the same file — `_login(page, nexora_server)`, `_stub_run_ok(page, capture=None)` (stubs `**/api/reporting/run`, records `route.request.post_data_json` into `capture`), and the `_stub_catalogs` route-stub pattern (routes registered **before** `page.goto`).
- Produces: the wizard offers a `data-bd-field="processname"` category chip (first), which serializes through the untouched `wizardDefinition()` category branch (`columns.push({ field: b.field.field, header: b.field.label });`) into the run payload. The category-chip cap becomes 16 for every source.

- [ ] **Step 1 — Write the failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py` (after the existing `_stub_catalogs` block). The stub's source **id must be `'docprocessing'`** — the curation branch fires on `w.source.id === 'docprocessing'`. The 16 stub fields reproduce the saturated production chip list (1 date + 13 legit string candidates incl. processname + 2 noise fields), so the tests pin the unhide, the ordering, the surviving noise curation, and no-eviction; a separate 20-string-field stub pins the raised cap for generic sources. The `"None - just the total"` chip carries `data-bd-kind="none"` (verified), so `[data-bd-kind="category"]` counts are precise; date chips render before category chips (verified render order in `renderBreakdownStep()`):

```python
# ---------------------------------------------------------------------------
# Per-process (per-client) breakdown chip -- docprocessing wizard curation.
# TEST env has no Statistics DB, so the docprocessing catalog is stubbed
# (same pattern as _stub_catalogs; the id MUST be 'docprocessing' so the
# wizard's DOCPROC_DIM_ORDER/DOCPROC_DIM_HIDE curation branch fires).
# ---------------------------------------------------------------------------

DOCPROC_WIZ_FIELDS = [
    {"field": "import_date", "label": "Import date", "type": "date",
     "grainable": True, "filterable": True},
] + [
    {"field": f, "label": lbl, "type": "string", "grainable": False, "filterable": True}
    for f, lbl in [
        ("processname", "Process"),
        ("docsource", "Document Source"),
        ("doctype", "Document Type"),
        ("forwarding", "Forwarding"),
        ("ownernr", "Owner no."),
        ("propertynr", "Property No."),
        ("registered", "Registered"),
        ("tenancynr", "Tenancy no."),
        ("archiveboxno", "Archive-box No."),
        ("branch", "Branch"),
        ("client", "Client"),
        ("confidentiality", "Confidentiality"),
        ("crdname", "Creditor Name"),
        ("bankpk", "Bank PK"),          # DOCPROC_DIM_HIDE noise -- must stay hidden
        ("workitem_id", "Workitem ID"), # DOCPROC_DIM_HIDE noise -- must stay hidden
    ]
]
DOCPROC_WIZ_SOURCES = [{
    "id": "docprocessing", "label": "Document processing", "kind": "curated",
    "processes": ["acme.inv", "acme.hr"], "fields": DOCPROC_WIZ_FIELDS,
}]
DOCPROC_WIZ_METRICS = {
    "docprocessing": [{"code": "doc_count", "label": "Docproc count stub",
                       "aggregation": "count"}]
}

# 20 string fields: pins the category-chip cap (16) for generic sources.
CAP_WIZ_SOURCES = [{
    "id": "cap_src", "label": "Cap source", "kind": "curated", "processes": [],
    "fields": [
        {"field": "f%02d" % i, "label": "Field %02d" % i, "type": "string",
         "grainable": False, "filterable": True}
        for i in range(20)
    ],
}]
CAP_WIZ_METRICS = {
    "cap_src": [{"code": "cap_count", "label": "Cap count stub", "aggregation": "count"}]
}


def _stub_wiz_catalogs(page, sources, metrics):
    # MUST be registered before page.goto (catalogs are fetched at page load).
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(sources)
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(metrics)
        ),
    )


def test_wizard_docprocessing_offers_process_breakdown(nexora_server, page):
    """The per-process chip is offered FIRST and noise curation still applies."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, DOCPROC_WIZ_SOURCES, DOCPROC_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Docproc count stub").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    proc = bklist.locator('[data-bd-field="processname"]')
    expect(proc).to_be_visible()
    expect(proc).to_have_text("Process")  # label straight from the catalog entry
    # First CATEGORY chip (date chips render before category chips).
    first_cat = bklist.locator('[data-bd-kind="category"]').first
    assert first_cat.get_attribute("data-bd-field") == "processname"
    # All 13 candidates render (the 12 previously-visible business chips plus
    # Process): nothing is silently evicted by the cap, noise stays hidden.
    expect(bklist.locator('[data-bd-kind="category"]')).to_have_count(13)
    expect(bklist.locator('[data-bd-field="crdname"]')).to_be_visible()
    expect(bklist.locator('[data-bd-field="bankpk"]')).to_have_count(0)
    expect(bklist.locator('[data-bd-field="workitem_id"]')).to_have_count(0)


def test_wizard_process_breakdown_serializes_to_processname_column(nexora_server, page):
    """Selecting the Process chip emits columns=[{field:'processname',...}] in the run."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, DOCPROC_WIZ_SOURCES, DOCPROC_WIZ_METRICS)
    captured = []
    _stub_run_ok(page, capture=captured)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Docproc count stub").click()
    page.get_by_test_id("rs-breakdown-list").locator('[data-bd-field="processname"]').click()
    page.get_by_test_id("rs-breakdown-next").click()
    run = page.get_by_test_id("rs-wizard-run")  # renderTimeStep() unhides it; All time default
    expect(run).to_be_visible()
    run.click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    # runCurrent() also fires the zero-column grand-total clone; assert on the
    # payload that carries columns.
    with_cols = [p for p in captured if p.get("columns")]
    assert with_cols, f"no run payload carried columns: {captured}"
    assert with_cols[0]["columns"][0]["field"] == "processname"


def test_wizard_caps_category_chips_at_16(nexora_server, page):
    """The category-chip cap is 16 for EVERY source (raised from 12 with
    headroom, so the saturated docprocessing list absorbs the Process chip
    and the next doc-field addition cannot silently vanish again)."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, CAP_WIZ_SOURCES, CAP_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Cap count stub").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    expect(bklist.locator('[data-bd-kind="category"]')).to_have_count(16)
```

- [ ] **Step 2 — Reset the test DB, then run the new tests, expect RED** (test 1 fails at `expect(proc).to_be_visible()` with a 0-element locator; test 2 times out clicking the absent chip — e2e timeouts make RED slow, be patient; test 3 fails at `to_have_count(16)` with actual 12):

Run:
```
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest "tests/e2e/test_reporting_simple.py::test_wizard_docprocessing_offers_process_breakdown" "tests/e2e/test_reporting_simple.py::test_wizard_process_breakdown_serializes_to_processname_column" "tests/e2e/test_reporting_simple.py::test_wizard_caps_category_chips_at_16" -q
```
Expected: `3 failed`

- [ ] **Step 3 — Implement the three edits** in `templates/js/_reporting_simple_js.html`.

**Edit A** — the curation constants near the top of the IIFE. Find:

```js
  // Wizard category-dimension curation (docprocessing only). Preferred
  // business dimensions first, noise hidden; table sources are untouched.
  var DOCPROC_DIM_ORDER = ['docsource', 'doctype', 'forwarding', 'ownernr',
                           'propertynr', 'registered', 'tenancynr'];
  var DOCPROC_DIM_HIDE = { processname: 1, bankpk: 1, crdno: 1, docbarcode: 1,
                           docdate: 1, workitem_id: 1 };
```

Replace with (processname leads the order and leaves the hide map):

```js
  // Wizard category-dimension curation (docprocessing only). Process first
  // (each Octo process = an actual client, so this is the per-client
  // breakdown), then the preferred business dimensions; noise hidden;
  // table sources are untouched.
  var DOCPROC_DIM_ORDER = ['processname', 'docsource', 'doctype', 'forwarding',
                           'ownernr', 'propertynr', 'registered', 'tenancynr'];
  var DOCPROC_DIM_HIDE = { bankpk: 1, crdno: 1, docbarcode: 1,
                           docdate: 1, workitem_id: 1 };
```

**Edit B** — the leftover global exclusion inside `renderBreakdownStep()`. Find:

```js
    var catFields = fields.filter(function (f) {
      return f.type === 'string' && f.filterable && f.field !== 'processname';
    });
```

Replace with:

```js
    var catFields = fields.filter(function (f) {
      return f.type === 'string' && f.filterable;
    });
```

**Edit C** — the saturated chip cap, further down in `renderBreakdownStep()`. Find:

```js
    catFields.slice(0, 12).forEach(function (f) {
```

Replace with:

```js
    // Cap 16 = headroom over docprocessing's current 13 candidates (the 12
    // previously-visible chips + Process). An exactly-saturated cap silently
    // evicts the newest chip -- that trap is why this was raised from 12.
    // Keep slack when adding doc-fields; the cap is pinned by
    // test_wizard_caps_category_chips_at_16.
    catFields.slice(0, 16).forEach(function (f) {
```

**Careful:** there is another `slice(0, 12)` in this file — the chart **series** cap (`series = series.slice(0, 12);` near `I18N.chartSeriesCapped`, mirrored server-side by `chart_render.py`). Do NOT touch that one; the Edit C anchor above (`catFields.slice(0, 12).forEach`) is unique.

- [ ] **Step 4 — Run the new tests, expect GREEN** (the e2e fixture starts a fresh server, so no template-cache concern):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest "tests/e2e/test_reporting_simple.py::test_wizard_docprocessing_offers_process_breakdown" "tests/e2e/test_reporting_simple.py::test_wizard_process_breakdown_serializes_to_processname_column" "tests/e2e/test_reporting_simple.py::test_wizard_caps_category_chips_at_16" -q`
Expected: `3 passed`

- [ ] **Step 5 — Run the whole Simple e2e file to prove no collateral damage** (other wizard tests use non-docprocessing sources, so the curation change must not disturb them):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q`
Expected: all passed (40 = 37 existing + 3 new)

- [ ] **Step 6 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): offer per-process breakdown chip in Simple wizard

Un-hide the synthesized processname dimension in the wizard's
"Break it down by..." step: drop the leftover global exclusion in the
catFields filter (5ac43fa) and the DOCPROC_DIM_HIDE entry (a61baa8),
put processname first in DOCPROC_DIM_ORDER, and raise the category
chip cap from 12 to 16 -- the docprocessing list was exactly
saturated, so without the bump the new chip (or the Creditor Name
chip) would be sliced away; 16 leaves headroom so the next doc-field
cannot silently vanish either. The cap is shared by all sources, so
table sources with 13-16 string columns gain chips too (deliberate,
pinned by test). Each Octo process corresponds to an actual client
in this deployment, so the chip delivers per-client numbers. Backend
unchanged: the query builder already materializes processname per
UNION subquery and the Advanced tab has always offered it. e2e covers
chip presence/order, surviving noise curation, the cap, and
definition serialization via stubbed catalogs (TEST env has no
Statistics DB).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — Docs & changelog

### Task 4: Update the curation passage + changelog entry

**Files:**
- Modify: `docs/howto/reporting.md` (one stale passage)
- Modify: `CHANGELOG.md` (`[Unreleased]` → `### Added`)

**Interfaces:** none (docs only).

- [ ] **Step 1 — `docs/howto/reporting.md`.** Find (Simple-tab wizard section). **Note:** in the file, the final quoted line continues on the SAME physical line with ` The **"Limit to specific…` — match the block below as a substring (it is unique) and leave that trailing sentence in place after your replacement:

```
    The category list is curated for the Document Processing source — preferred
    business dimensions (Document Source, Document Type, Forwarding, Owner no.,
    Property No., Registered, Tenancy no.) come first and technical noise (process
    name, Bank PK, creditor no., barcode, document date, workitem id) is hidden;
    other sources list their catalog fields unfiltered.
```

Replace with:

```
    The category list is curated for the Document Processing source — **Process**
    leads (one value per Octo process; in this deployment each process corresponds
    to a client, so it delivers per-client numbers), then the preferred business
    dimensions (Document Source, Document Type, Forwarding, Owner no., Property
    No., Registered, Tenancy no.), and technical noise (Bank PK, creditor no.,
    barcode, document date, workitem id) is hidden; other sources list their
    catalog fields unfiltered (up to 16 category chips per source).
```

- [ ] **Step 2 — `CHANGELOG.md`.** Under `## [Unreleased]` → `### Added` (matching the existing "Reporting: …" entry style), add:

```
- Reporting: the Simple-tab wizard's "Break it down by…" step now offers a
  **Process** dimension — one value per Octo process (per client in this
  deployment), placed first in the curated list. Previously the dimension was
  hidden as noise; the label is DB-localized via `dbo.Search_Field_Labels`
  (migration `0037`). The wizard's category-chip cap rises from 12 to 16 for
  every source (the docprocessing list was exactly saturated at 12; table
  sources with 13–16 string columns now show chips that were previously
  truncated).
```

- [ ] **Step 3 — Commit:**

```bash
git add docs/howto/reporting.md CHANGELOG.md
git commit -F - <<'EOF'
docs(reporting): document the Process wizard dimension

Update the Simple-wizard curation passage in docs/howto/reporting.md
(processname moves from the hidden list to the head of the preferred
list; note the 16-chip cap) and add the changelog entry covering the
new chip, migration 0037, and the all-sources cap raise 12 -> 16.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — Full gate + live verification on INT

### Task 5: Full local test gate

**Files:** none (verification only).

- [ ] **Step 1 — Non-e2e tiers:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q`
Expected: all passed, 0 failed (the count grows by Task 1's two tests)

- [ ] **Step 2 — Translation guard** (proves the no-new-msgid claim):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_translations.py -q`
Expected: all passed

- [ ] **Step 3 — URL-prefix guard** (no new JS URLs were added, but the file was touched):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_template_url_prefix.py -q`
Expected: all passed

- [ ] **Step 4 — e2e tier for the touched surface:**

Run:
```
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q
```
Expected: all passed (40)

- [ ] **Step 5 — `git log --oneline -5`** and confirm the four commits from Tasks 1–4 are present, in order, on `plan/reporting-breakdown-by-process`. Nothing to commit in this task.

### Task 6: Live browser verification on INT (+ screenshots)

**Files:** none (verification only; screenshots go to `var/screenshots/`, never the repo root).

**Prereq:** migration `0037` was auto-applied to INT by Task 2's pre-commit hook — the chip label must read "Process" (or "Prozess" for a German-locale user), NOT "Processname". If it reads "Processname", the migration did not apply; stop and check `dbo.SchemaMigrations` / `python scripts/db-migrate.py --env INT`.

The wizard entry point is the **"New report"** button (`data-testid="rs-new-report"`, `id="rsNewReport"` in `templates/_reporting_simple.html`) — there is no "Build one with the wizard" control anywhere in the templates.

- [ ] **Step 1 — Restart the dev server with auto-login** (Jinja templates are process-cached; the server must pick up the edited partial): `nx -u -b --loginas:<a user with reporting.view + the docprocessing source grant + several reporting.scope.process.* grants — the owner's usual admin login qualifies>`.
- [ ] **Step 2 — Wizard chip:** Reporting → Simple tab → **"New report"** → pick the Document-Processing count measure → on "2. Break it down by…" verify the **Process** chip renders as the FIRST category chip (right after the "Over time" date chips) and all previously-visible chips (through "Creditor Name") are still present. Screenshot → `var/screenshots/reporting-process-chip-wizard.png`.
- [ ] **Step 3 — One-dim result:** select **Process**, Next, keep "All time", Show result. Verify the chart shows one bar per process (raw ids like `compass.01_Invoice_SAP` — expected, see D6) and the table view lists processes with counts, plus the grand-total card. Screenshot → `var/screenshots/reporting-process-breakdown-result.png`.
- [ ] **Step 4 — Two-dim series:** back into the wizard → "Over time (Export date)" (Week) as first breakdown + **Process** as second → run → colored series per process. Screenshot → `var/screenshots/reporting-process-series.png`.
- [ ] **Step 5 — Drill-through:** click one process bar/segment → the slide-over opens with underlying document rows for that process only, header reading `Process = <process id>`. (No drill code was changed; this proves composition.)
- [ ] **Step 6 — Composition check:** "Adjust in wizard", open "Limit to specific processes", untick one process, re-run → the unticked process disappears from the chart (scope narrows, breakdown groups the rest). Also confirm the Process chip shows **selected** on re-entry (the previously invisible-selection quirk, now visible).
- [ ] **Step 7 — Advanced tab + export spot-checks:** the Advanced field panel now labels the dimension "Process" (migration effect), not "Processname"; on the Simple result, export CSV → a `Process` column with raw process ids per row group.
- [ ] **Step 8 — If this is a remote session, SendUserFile the three screenshots** (remote frontend rule: send screenshots proactively).

---

## Gotchas & notes

- **The 12-chip saturation trap is the whole reason this plan has Edit C.** `catFields.slice(0, 12)` is already saturated at exactly 12 chips on INT (7 `DOCPROC_DIM_ORDER` fields + 5 alphabetical). A naive "remove the two exclusions" change puts an un-ordered "Processname" at alphabetical position 13 → sliced away → **no visible change at all**. With processname ordered first but the cap still 12, the previous 12th chip (Creditor Name) silently disappears instead. And a cap of exactly 13 would re-arm the same trap for the *next* doc-field added to SearchConfig — hence 16 with headroom, a code comment tying the cap to the candidate count, and two pins: `test_wizard_docprocessing_offers_process_breakdown` (all 13 candidates render) and `test_wizard_caps_category_chips_at_16` (the exact cap).
- **The cap raise applies to ALL sources, deliberately.** The `catFields.slice(0, …)` render loop runs unconditionally (the `if (w.source.id === 'docprocessing')` branch above it only filters/sorts), so a table-provider source with 13–16 string+filterable columns now shows chips that were previously truncated at 12. This is an accepted, documented side effect (CHANGELOG + howto note it; the cap test pins it with a generic non-docprocessing stub). If a table source's chip list ever gets noisy, curation for that source is a separate feature.
- **e2e strategy: drive the real DOM, don't extract a helper.** An earlier draft window-exposed a pure `curateCategoryFields()` for `page.evaluate` tests on the theory that TEST-env docprocessing is untestable — but only `/api/reporting/run` needs the Statistics DB; chip rendering needs only the catalogs, and the `_stub_catalogs` network-stub seam reaches `renderBreakdownStep()` end-to-end. Pure-function tests would stay green even if the render call-site were botched. If you ever DO need a JS-function seam here, the `window.ReportingSqlFormat` precedent exists — but it is not the right tool for asserting user-visible chips.
- **Two exclusions, one function.** The global `f.field !== 'processname'` (from wizard commit `5ac43fa`; it became a dead leftover when curation commit `a61baa8` took over) applies to ALL sources; `DOCPROC_DIM_HIDE` only to docprocessing. Removing the global filter means a *table-provider* source whose catalog happens to contain a field literally keyed `processname` now shows it as a chip too — correct and intended (table sources were never meant to be curated).
- **Commit trailer:** repo history stamps the model that actually ran the work (`Claude Opus 4.8` / `Claude Sonnet 5` are the only trailers in recent history). The blocks above use `Claude Sonnet 5` for the declared Sonnet executor — substitute the real name if a different model executes. Never copy a planning-model name into an execution commit.
- **Values are raw process ids everywhere** — chart axis/legend, server-side PNG, CSV/XLSX cells, drill grid and header. Friendly value names have NO existing mapping (only `_humanize_process_id` in `nx_lib/reporting/ai_schema.py`, AI-prompt-only) — new scope, Owner action 2.
- **Label collision caution:** the wizard shows a "Client" doc-field chip (SearchConfig field) — that is why the new label is "Process". Owner can re-word by data UPDATE (Owner action 1).
- **Free behavior fix:** `wizardStateFromDefinition` has always mapped a `processname` column into a wizard category breakdown, so AI/Advanced-built reports opened via "Adjust in wizard" carried an *invisible* selected breakdown. After un-hiding, that selection shows as a selected chip — benign, strictly better, needs no migration of saved reports (a processname breakdown serializes as an ordinary `columns` entry the validator has always accepted; sharing/scheduling re-validate against the same catalog).
- **Chart caps are fine and untouched:** the chart **series** cap (`series = series.slice(0, 12);` near `I18N.chartSeriesCapped`, mirrored server-side in `chart_render.py`) is a different `slice(0, 12)` in the same file — do not confuse it with Edit C's chip cap. INT's process count is far below both. Distinct-per-Y works too — processname is never a distinct metric's `base_field`.
- **Zero-dim grand total:** `runCurrent()` fires a zero-column clone (`totalDef.columns = []`) alongside any dimensioned run — that is why the serialization test filters captured payloads for `p.get("columns")`.
- **Theoretical drill edge (documented, not fixed):** a clicked empty/NULL segment value maps to `op: 'is_null'`, which `_scope_by_processname` rejects (`unsupported processname filter op` → HTTP 400). Unreachable for processname — the projected value is a bound non-NULL constant per subquery.
- **AI already grounded:** `serialize_sources_catalog` lists every catalog field incl. processname on Surfaces A/B/C; the system prompt only steers process *words* toward `scope.processes` (`'Process ids in "allowed scope.processes" follow <client>.<NN_Name>; …'` in `nx_lib/reporting/ai.py`). If "per client" asks keep getting scoped instead of grouped, the prompt fix is Owner action 3 — deliberately out of this diff.
- **`tests/integration/test_reporting_ai_routes.py` contains `"label": "Processname"`** inside a *mocked* catalog fixture — it does not read the DB, so migration 0037 does not affect it. Leave it alone.
- **Do not touch `templates/js/_reporting_drill_js.html`** — drill-through just merged (`14a1e7b`, fix `c144516`), the main clone has in-flight uncommitted edits to it, and it works with processname unchanged (`SMART_FIELDS` already leads with it). Its own live browser pass is still owner-owed (Owner action 5 reminder).
- **Historical rationale for the hide:** processname was lumped into "technical noise" by `a61baa8` without a functional justification (only `workitem_id` got one — grouping by a unique id is never a sensible breakdown). The deployment context (process = client) invalidates the noise classification; the query path was never removed.
