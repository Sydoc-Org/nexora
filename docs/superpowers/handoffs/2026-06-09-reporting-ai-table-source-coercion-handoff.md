# Handoff — Reporting AI: coerce table-source drafts + e2e fix (already pushed)

- **Date:** 2026-06-09
- **Branch:** `feature/2.5.63`. Git mode this session: **push allowed** (user opted in).
  **Feature commits ARE pushed to origin.** Only this handoff commit is local-only
  (hcc never pushes); owner pushes it + opens the PR.
- **Feature commits (this session, both pushed):**
  - `d4aa286` fix(reporting): coerce AI-drafted table-source report definitions
  - `db2c9fd` fix(reporting): assert metrics-well list is attached, not visible (e2e)
  - This handoff commit is the latest (local-only).
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-09-reporting-semantic-slice1-complete-handoff.md`
- **Memory updated:** `project_reporting_phase3` (the "208" was already-fixed; the real
  residual is now mitigated; PROD RO logins + AI creds now provisioned by owner).

## TL;DR

- The slice1 handoff's **"run_sql 208s bug" was a stale note** — the literal SQL-208
  ("invalid object name", agent passing a source id as a table name) was already fixed by
  `534e2a3` (in the branch). No work needed there.
- Fixed the **real residual**: Surface A ("Build a report") and the Surface C agent's
  `build_definition` tool bounced *near-valid* drafts for curated **table** sources
  because the small model used column **labels** ("Date") instead of **keys** (`ForDate`)
  and omitted `schemaVersion`/`title`. New `schema.coerce_definition` repairs those before
  validation. (`d4aa286`)
- The pre-push gate (full `tests/` incl. Playwright e2e) **caught a latent Slice-1 e2e**
  on its first-ever live run: `test_metrics_well_present_in_builder` asserted
  `to_be_visible` on the empty (zero-height) `#rpWellMetrics` `<ul>`. Changed to
  `to_be_attached`. (`db2c9fd`)
- **Owner did the PROD ops mid-session:** provisioned both RO `db_datareader` logins on
  PROD + copied the Azure AI creds INT→PROD + mirrored `env/STAGING.env`. So the only
  remaining PROD dep is the migrations, which auto-apply on the next deploy.

## What shipped (this session)

### `d4aa286` — coerce AI-drafted table-source definitions
| File | Change |
|------|--------|
| `nx_lib/reporting/schema.py` | **new** `coerce_definition(rd, catalog, *, default_title, default_row_limit, max_row_limit)` — whitelist-safe in-place repair: resolves a `field` given as a human **label** back to its catalog **key** (columns / filters / sort / chart axes), backfills the column `header` from the label, and fills `schemaVersion` / `visualization` / a synthesized `title` / a default-or-clamped `rowLimit`. Only swaps a label that maps to exactly one field; no-op for already-valid drafts. |
| `nx_lib/views/reporting.py` | import `coerce_definition`; call it inside the shared `_validate_definition_for_user` gate (before validation) with `default_title=source.label`, `DEFAULT_ROW_LIMIT`, `MAX_ROW_LIMIT`. Mutating in place propagates to what each surface returns/applies (Surface A's `result.definition`; the agent's `build_definition` trace `args`). The human `/run` builder path is **untouched** (it calls `validate_report_definition` directly). |
| `tests/unit/test_reporting_schema.py` | 21 new `coerce_definition` unit tests (label→key, header backfill, case-insensitive, ambiguous-label skip, scalar defaults, clamp, non-dict passthrough, in-place identity, coerce+validate end-to-end). |
| `tests/integration/test_reporting_ai_routes.py` | 1 wiring test driving the real `_validate_definition_for_user` (source + perm mocked) — proves a label/missing-field table-source draft is coerced + accepted. |
| `docs/design/reporting-ai-assistant.md` | new "Tolerant repair (server-side safety net)" bullet under Surface A. |
| `CHANGELOG.md` | new `### Fixed` entry (top). |

### `db2c9fd` — Slice-1 e2e assertion fix
| File | Change |
|------|--------|
| `tests/e2e/test_reporting_metrics.py` | `test_metrics_well_present_in_builder`: empty `#rpWellMetrics` `<ul>` is zero-height → assert `to_be_attached` instead of `to_be_visible`; the "+ Add metric" button stays the visible proof. UI unchanged. |

## Verification

```powershell
# from C:\dev\nexora on feature/2.5.63
git log --oneline -4
.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_schema.py tests/integration/test_reporting_ai_routes.py -q --no-cov
#   -> 76 passed
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q
#   -> 828 passed, 24 skipped   (806 baseline + 22 new)
# e2e (needs the gate's own server; reset NEXORA_TEST first):
.venv\Scripts\python.exe scripts\test_db_reset.py
.venv\Scripts\python.exe -m pytest tests/e2e/test_reporting_metrics.py --no-cov -o addopts=""
#   -> 2 passed
```

The push already ran the **full pre-push gate green** ("Test suite (pre-push gate)...Passed";
914 passed after the e2e fix), so origin has `d4aa286` + `db2c9fd`.

## Owner actions / next steps

1. **Commit the in-progress Generali PDQM migration left in the working tree** (NOT mine —
   left uncommitted on purpose): `sql/_migrations/GeneraliDB/0002_insert_pdqmmapping_adressverifikation_qstat27.sql`
   + its `CHANGELOG.md` "Generali PDQM mapping seed" Added entry. Committing it makes the
   pre-commit hook **auto-apply `0002` to INT GeneraliDB** — review first.
2. **Push this handoff commit** (feature commits are already on origin).
3. **Open the PR `feature/2.5.63` → `main`.** Deploy auto-applies pending migrations
   (`0015`/`0016`/`0017` for NexoraDB; `0002` for GeneraliDB once committed) to PROD.
4. **PROD reporting-AI deps — mostly DONE this session by owner:** RO `db_datareader`
   logins provisioned on `DB_SERVER_PRD`; Azure AI creds copied INT→PROD; `env/STAGING.env`
   mirrors PROD. **Remaining = just the migrations on the next deploy.** Note: INT + PROD
   now share ONE Azure `gpt-4o-mini` deployment → shared TPM/RPM quota (fine for now; split
   if it bites). `AI_DAILY_LIMIT` stays per-env (separate DBs).

## Gotchas & notes

- **`coerce_definition` only runs on AI-drafted definitions** (Surface A + the agent's
  build_definition), via `_validate_definition_for_user`. The human builder `/run` path is
  deliberately strict (calls `validate_report_definition` directly). Don't "DRY" them
  together — the asymmetry is the point (tolerant with the model, strict with the wire).
- **The "208" rabbit hole:** the backlog item was already closed by `534e2a3`. Two prior
  handoffs (06-04) describe it as SQL-error-208; the slice1 handoff's "is slow / 208s" was
  a mis-paraphrase. If a future backlog lists it again, it's done.
- **Empty wells read as not-visible to Playwright.** `Columns`/`Filters` wells are also
  empty `<ul>`s — any future "well visible" e2e should assert `to_be_attached` (or target
  the well's header / button), not `to_be_visible`, until the well has rows.
- **gitlint:** body mandatory (B6), every body line ≤100 chars (B1). Used `git commit -F`
  with a temp file outside the repo; PowerShell here-strings don't survive the Bash tool.
- **Pre-commit hooks passed cleanly** (ruff, ruff-format, `sql-migrate-int`, `sql-sync-check`,
  gitlint) — no `SQL_SYNC_SKIP=1` needed this checkout.

## Resuming in a fresh session

This session's feature work is complete, tested (828 backend green + e2e green), committed
**and pushed** (`d4aa286`, `db2c9fd`). The realistic next moves: (1) owner commits the
pending Generali PDQM `0002` migration + PR→main → deploy applies all pending migrations to
PROD; (2) then the next reporting feature — **Slice 2 (conformed dimensions)** per the
slice1 handoff's roadmap. Memory pointers: `project_reporting_phase3`,
`project_reporting_semantic_slice1`, `project_prepush_gate_e2e`,
`project_int_migration_crlf_drift`.
