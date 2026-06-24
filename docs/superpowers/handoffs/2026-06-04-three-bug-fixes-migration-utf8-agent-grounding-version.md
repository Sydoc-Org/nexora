# Handoff — Three bug fixes: migration UTF-8, agent run_sql grounding, single-source version

- **Date:** 2026-06-04
- **Branch:** `feature/2.5.63`. Git mode: the user **authorized push this turn** — the branch
  is **pushed to origin**. **No PR opened** (owner opens it → `main`).
- **Feature commits (this arc):** `d1f0116`, `534e2a3`. This handoff commit is the latest.
  The immediately prior commit `a29cab9` is the **owner-actions** handoff (the first arc of
  this session — see below).
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-04-owner-actions-executed-int-handoff.md`
- **Memory updated:** `project_reporting_sqlcmd_utf8_bug` (→ FIXED), `project_reporting_phase3`
  (bug C → FIXED), `project_int_migration_crlf_drift` (EOL-matches-ledger nuance).

## TL;DR

This session had two arcs against the reachable INT box:

1. **Owner actions executed** (detailed in the prior handoff `a29cab9`): applied migration
   `0015` (`reporting.ai.explain_data`) to INT, provisioned the two reporting RO logins
   (reset their passwords to match `env/INT.env`), and **live-verified** the Agent
   explain-data path end-to-end (agent narrated a real count, "30 documents", via the RO
   login; audit `explainData:true`, `GateVerdict=final`).

2. **Three pre-existing bugs surfaced during that verification were fixed** (this handoff),
   TDD on every code change, **777 unit+integration tests green**, each live-verified:

   - **A — migration UTF-8 corruption** via sqlcmd's default codepage.
   - **B — stale hard-coded footer version**.
   - **C — explain-data agent looping `run_sql` against a source it can't reach**.

All three were committed locally, then **pushed** this turn at the user's request.

## Bug fixes (this arc)

### A — `db-migrate.py` corrupted non-ASCII UTF-8 via sqlcmd (`d1f0116`)

- **Root cause:** `apply_one` ran `sqlcmd -i <file>` **without a UTF-8 input codepage**, so
  sqlcmd read UTF-8 migration files in the host OEM/ANSI codepage and silently corrupted any
  non-ASCII text on INSERT. Migration `0011`'s correct em-dash (`\xe2\x80\x94`) was stored as
  the double-mojibake "Generali â€" PDQM Report" in `dbo.ReportingSources.Label` (visible in
  the Reporting source dropdown). Affects **any** Unicode in **any** migration, on INT and PROD.
- **Fix:** extracted `_sqlcmd_args` and added `-f 65001` (+ decode captured output as UTF-8).
  New migration `0016_fix_generali_pdqm_label_encoding.sql` repairs the stored label,
  written **codepage-safe via `NCHAR(0x2014)`** so it survives sqlcmd regardless of the runner.
  Applied to INT (label now correct UTF-8). Tests: `tests/unit/test_db_migrate.py`.
- **Live:** dropdown now reads "Generali — PDQM Report" (`var/screenshots/fix_reporting_label.png`).

### B — stale hard-coded footer version (`d1f0116`)

- `templates/_nexora_version.html` hard-coded `nexora 2.5.60` — a third copy of the version,
  drifted from `pyproject.toml`. Now single-sourced in **`nx_lib/version.py`** (`__version__`),
  injected app-wide via a **`nexora_version`** context processor (`nx_lib/hooks.py`), and
  consumed by the footer + the dev CLI (`nx_lib/cli.py`). Bumped **2.5.60 → 2.5.63** (the user
  chose this to match the branch); `pyproject.toml` updated; `tests/unit/test_version.py`
  enforces version.py == pyproject.
- **Live:** footer reads "nexora 2.5.63" (`var/screenshots/fix_footer_version.png`).

### C — explain-data agent ran `run_sql` against unreachable sources (`d1f0116` + `534e2a3`)

- **Root cause:** `run_sql` only targets the `statistics`/`octopus` RO engines. A curated
  `table`-provider source (e.g. Generali PDQM on GeneraliDB) has **no RO target**, but the
  agent bound `run_sql` unconditionally and drafted `SELECT … FROM <source id>` against a
  run_sql target → unrecoverable 208 "invalid object name", looping to `max_turns`.
- **First attempt (`d1f0116`, grounding):** marked curated sources **builder-only** in the
  schema serializer (`nx_lib/reporting/ai_schema.py`) + strengthened the explain suffix.
  **Live-tested: insufficient** — gpt-4o-mini ignored the nudge and kept drafting `run_sql`.
- **Real fix (`534e2a3`, structural):** the Agent client now sends the **active source**, and
  `api_ai_agent` binds `run_sql`/`compute_stats` **only when that source is run_sql-able**. A
  builder-only source confines the model to `build_definition` and reports `explainData=false`.
  The model is also told which source "this source" means. Two route tests added
  (builder-only skips the data tools; a run_sql-able source still binds them).
- **Live:** `run_sql` calls against Generali went **12 → 0** (audit Id 14/15: all
  `build_definition`, `explainData:false`). `var/screenshots/fix_agent_no_runsql_trace.png`.
- **Known limitation (NOT this bug, pre-existing):** gpt-4o-mini still can't reliably emit a
  *valid* `build_definition` via the agentic tool path for table sources — the trace shows
  schema-shape errors ("schemaVersion must be 1", "title is required") and key-vs-label
  mismatches (keys are `ForDate`/`ParentCategory`/`RecordDateTime`, labels "Date"/"Parent
  category"/"Recorded at"). The non-agentic **"Build a report"** mode (Surface A, dedicated
  JSON prompt + retry) handles these far better. A worthwhile separate follow-up if the Agent
  mode should fully answer table-source questions.

## Verification

```powershell
# from C:\dev\nexora on feature/2.5.63
git log --oneline -6
.venv\Scripts\python.exe scripts\test_db_reset.py            # reset NEXORA_TEST FIRST
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q --no-cov
#   -> 777 passed, 24 skipped   (do NOT prefix ENVIRONMENT=INT — conftest forces TEST;
#      an INT prefix makes the integration login fixture 401 with 24 setup ERRORs)
# new/changed tests of note:
#   tests/unit/test_db_migrate.py            (sqlcmd -f 65001)
#   tests/unit/test_version.py               (single-source version)
#   tests/unit/test_reporting_ai_schema.py   (builder-only marker)
#   tests/integration/test_reporting_ai_routes.py  (source-aware run_sql binding x2)
# screenshots: var/screenshots/{fix_reporting_label,fix_footer_version,fix_agent_no_runsql_trace,
#   verify_reporting_agent_docproc,...}.png
```

## Owner actions / next steps

1. **Open the PR `feature/2.5.63` → `main`** (already pushed; pre-push e2e gate ran green).
2. **PROD (before/with the deploy):**
   - `0015` + `0016` auto-apply on deploy via the **now-fixed** runner. **Verify PROD's `0011`
     label** — it has the same mojibake if `0011` ran there through the old runner; `0016`
     corrects it regardless (`NCHAR`). Verify PROD's `0001-0003` checksums (CRLF-drift caveat).
   - **Provision the two RO logins on PROD's `DB_SERVER_PRD`** (sysadmin, passwords matching
     `env/PROD.env`) — until then the explain-data `run_sql` path + SQL sandbox 503 on PROD.
3. **Grant `reporting.ai.explain_data`** to any non-admin who should narrate real numbers
   (admins auto-seeded by `0015`). Data-egress grant — keep deliberate.
4. **Optional follow-up:** improve agentic `build_definition` reliability for table sources
   (key-vs-label grounding / shape) so the Agent mode fully answers them, not just `run_sql`-able
   sources. Pre-existing gpt-4o-mini limitation, out of scope for the bug fixes here.

## Gotchas & notes

- **`SQL_SYNC_SKIP` was NOT needed** for any commit this session: on this checkout the
  working-tree EOLs (`0001-0003` CRLF, `0004+` LF) exactly match INT's ledger, so the
  `sql-migrate-int` hook passes clean (it auto-applied `0015`/`0016` to INT). See the updated
  `project_int_migration_crlf_drift` nuance.
- **Pre-commit will bite once or twice per commit:** `ruff` flagged `N812` (don't alias
  `__version__`), and `ruff-format` reformats + aborts on first stage — re-`git add` + re-commit.
- **ruflo junk files** keep appearing — 0-byte files named after tokens from edits (`FAIL`,
  `password`, `None`, `1`). Harmless; `rm` them before staging.
- **Agent sub-mode is now source-aware** (sends `source` in the POST body). Old clients that
  don't send it fall back to permissive binding (backward-compatible).
- **Dev server** was left running on `http://localhost:8000` (INT) during the session; stop
  with `nx -d`.

## Resuming in a fresh session

Both arcs are complete, tested (777 green), live-verified, committed, and **pushed**. The
realistic next work is the **owner PR → `main`**, gated on the **PROD migration apply
(`0015`+`0016`) + `0011` label/`0001-0003` checksum verification + RO-login provisioning on
PROD**. Memory pointers: `project_reporting_phase3`, `project_reporting_sqlcmd_utf8_bug`,
`project_int_migration_crlf_drift`, `project_branch_consolidation_2_5_63`.
