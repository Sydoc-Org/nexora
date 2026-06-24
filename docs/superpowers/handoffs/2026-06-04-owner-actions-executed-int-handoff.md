# Handoff — Owner actions executed on INT (0015 applied, RO logins provisioned, explain-data live-verified)

- **Date:** 2026-06-04
- **Branch:** `feature/2.5.63`. Git mode: **commit-only** — no push, no PR (owner opens the PR).
  This session made **no code changes**; it executed operational owner actions + live verification
  and writes this handoff. The only commit is this doc.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-04-reporting-3e-agent-ui-confidence-auth-handoff.md`
- **Specs of record:** `docs/superpowers/plans/2026-06-03-reporting-ai-phase3.md` (Task 7 + 3e),
  `docs/design/reporting-ai-assistant.md` (§13-Q2 egress).

## TL;DR

The prior handoff (3e + Agent UI) was written on a **remote box where INT's SQL Server was
unreachable**, so its DB-gated owner actions were left open. **This session ran on a box where
INT is reachable**, so I executed them and verified the result live:

1. ✅ **Applied migration `0015`** (`reporting.ai.explain_data`) to INT — clean, no drift.
2. ✅ **Provisioned the two reporting RO logins** on INT (they existed but their passwords didn't
   match `env/INT.env`; I reset them to the env values; verified they connect **and are read-only**).
3. ✅ **Live-verified the Reporting Agent sub-mode end-to-end** on INT against the live Azure
   provider, including the **explain-data path producing a real number** ("30 documents").
4. ✅ **Auth pages** confirmed on-brand live (not just the offline harness).
5. ⚠️ **Workitem confidence overlay** — not live-demonstrable (no accessible workitem has the
   coordinate/confidence data; matches the documented `DigitalMailroom_sydoc`/`ELSY` caveat).
6. ✅ **102-test verification suite green** (the handoff's documented gate).

Also surfaced **three pre-existing bugs** during verification (findings A–C below) — documented,
**not fixed** (out of the named owner-action scope; A has deploy implications).

## Owner actions executed (state changes on INT)

### 1. Migration `0015` applied to INT
- `scripts/db-migrate.py --env INT --db NexoraDB` ran cleanly. The feared **CRLF ledger drift does
  NOT manifest on this checkout**: working-tree EOL happens to match INT's recorded checksums exactly
  (`0001-0003` are CRLF in the tree ↔ CRLF in the ledger; `0004-0014` LF ↔ LF). Dry-run showed only
  `0015` pending, **zero "mutated"** migrations.
- Result: `Permission` row `reporting.ai.explain_data` created; **seeded to 2 admin access-profiles**
  (Effect `A`); recorded in `dbo.SchemaMigrations`. Verified present.

### 2. RO logins provisioned on INT
- `NXR_SERVICE` (the app login) **is sysadmin on INT**, so provisioning was possible from here.
- Both logins (`nexora_reporting_ro` → `SYDOC_Statistik`, `nexora_reporting_octo_ro` →
  `RuntimeDatabase`) **already existed with `db_datareader`**, but their server passwords **did not
  match** `DB_REPORTING_RO_PWD` / `DB_REPORTING_OCTO_RO_PWD` in `env/INT.env` (connect failed 28000).
  I **reset both passwords to the env values** (`ALTER LOGIN`), mirroring
  `scripts/provision-reporting-ro-logins.sql`'s rotate path but with the real INT DB names.
- Verified: both RO engines now connect **and are read-only** (a `CREATE TABLE` probe is rejected).
  The one-shot script lived under gitignored `var/` and was deleted.

### 3. Live verification (screenshots in `var/screenshots/verify_*.png`, sent to owner)
- Logged in via the dev-only `/dev/login/ben.streich` route (admin).
- **Agent sub-mode UI** renders on the `nexora-ui` brand: Build / Write-SQL / **Agent** toggles,
  conversation thread, the **"How the agent worked" tool-step trace** (✓/✗ chips), follow-up input,
  "Insert into SQL editor". The hint reads the **explain-data variant** ("report the actual numbers
  from the data it fetched") — which only renders because the admin now holds
  `reporting.ai.explain_data` (from `0015`) **and** the RO login works → end-to-end proof of action 1+2.
- **Explain-data end-to-end:** asked "How many documents in total?" against the **Document
  Processing** source. The agent ran `validate_sql → run_sql → validate_sql → run_sql` and answered
  **"There are a total of 30 documents in the system."** Audit row `Surface='agent'`, `Status='ok'`,
  **`GateVerdict='final'`**, `GeneratedSql` carries **`"explainData": true`**. `run_sql` executed
  against the **provisioned RO login** (a real result, not a 503/login-fail).
- **Auth pages** live: the gradient top-accent login card + indigo→violet "Sign in" button + accent
  focus rings (`auth.css`), and the landing page brand CTA. 0 console errors.
- **Confidence overlay:** the accessible workitems report `Document Source: no source location`
  (no field coordinates), so the "Show sources" overlay correctly doesn't render. Not a regression —
  it's the known data caveat. Backed by 7 unit tests + last session's offline-harness verification.

## ⚠️ Findings surfaced during verification (pre-existing; NOT fixed)

**A. `db-migrate.py` corrupts non-ASCII UTF-8 via sqlcmd (deploy-relevant).**
Migration `0011`'s file contains the correct UTF-8 em-dash (`\xe2\x80\x94`) in the source label
`'Generali — PDQM Report'`, but `dbo.ReportingSources.Label` on INT holds the **double-mojibake**
`Generali â€" PDQM Report` (the 3 codepoints U+00E2 U+20AC U+201D). Root cause: `apply_one()` runs
`sqlcmd -i <file>` **without a UTF-8 input codepage**, so sqlcmd reads UTF-8 bytes as the OEM/ANSI
codepage and inserts the corrupted text. This affects **any** migration with accented/Unicode text
(de/fr strings, dashes, …) on **both INT and PROD**. The mojibake shows in the Reporting source
dropdown live.
- **Runner fix:** pass an input codepage to sqlcmd in `apply_one` — `-f 65001` (or `-f i:65001` for
  input-only). Re-test the existing migrations apply identically first.
- **Data fix:** a corrective migration is needed for the already-corrupted `0011` label. Write it
  **codepage-safe** (`UPDATE dbo.ReportingSources SET Label = N'Generali ' + NCHAR(0x2014) + N' PDQM
  Report' WHERE Code='generali_pdqm';`) so it survives sqlcmd regardless of the runner fix. Same row
  is corrupt on PROD if `0011` was applied there the same way — verify + correct both.

**B. Stale footer version.** The auth/landing footer shows `nexora 2.5.60`; the branch is `2.5.63`.
Hard-coded version string not bumped.

**C. Explain-data grounding gap for curated `table` sources.** For the `generali_pdqm` source the
agent's `run_sql` used the source **id** (`generali_pdqm`) as a table name → SQL Server error 208
"Invalid object name", and the loop hit `max_turns` with no validated answer (it degrades
gracefully in the UI: "stopped before producing a validated result — try rephrasing"). It works
correctly for the `docprocessing` SQL-sandbox source (finding 3 above). Possible follow-up: ground
the agent on the physical `BaseObject` for `table`-kind sources, or steer `table` sources to
`build_definition` rather than `run_sql`.

## Remaining owner actions

1. **Open the PR `feature/2.5.63` → `main`** (already pushed to origin at `acb9b37` — the prior
   handoff's "nothing pushed" is stale; local == origin).
2. **PROD, before/with the deploy** (`deploy.yml` auto-applies pending migrations to PROD, then
   mirrors code):
   - `0015` will auto-apply to PROD on deploy. **Verify PROD's `0001-0003` checksums** first (the
     CRLF drift caveat) so the PROD migration step doesn't abort.
   - **Provision the two RO logins on PROD's `DB_SERVER_PRD`** (sysadmin) with passwords matching
     `env/PROD.env`, via `scripts/provision-reporting-ro-logins.sql` (or the same rotate approach).
     Until then the explain-data `run_sql` path + SQL sandbox return 503 on PROD.
3. **Grant `reporting.ai.explain_data`** to any non-admin who should narrate real numbers (admins are
   auto-seeded). It is a **data-egress** grant — keep it deliberate.
4. **Decide on findings A–C** (A first — it silently corrupts Unicode in every migration and is live
   on the Reporting page).

## How to verify

```powershell
# from C:\dev\nexora on feature/2.5.63
git log --oneline -3
.venv\Scripts\python.exe scripts\test_db_reset.py          # reset NEXORA_TEST first
.venv\Scripts\python.exe -m pytest `
  tests/integration/test_reporting_ai_routes.py tests/unit/test_reporting_ai_agentic.py `
  tests/unit/test_reporting_ai_tools.py tests/unit/test_reporting_stats.py `
  tests/unit/test_field_locations.py tests/unit/test_media_info_field_sources.py `
  tests/unit/test_translations.py tests/unit/test_octo.py -q --no-cov   # 102 passed
# DO NOT prefix ENVIRONMENT=INT — conftest forces ENVIRONMENT=TEST; an INT prefix makes the
#   integration login fixture hit INT and 401 (24 setup ERRORs). Run it plain.
# screenshots: var/screenshots/verify_{reporting_agent_submode,reporting_agent_docproc,
#   reporting_agent_trace,auth_login_form_live,workitem_detail}.png
```

## Notes

- **Dev server left running** on `http://localhost:8000` (INT, PID from `nx -s`). Stop with `nx -d`.
- **No commit needed `SQL_SYNC_SKIP`** for this handoff doc commit (no SQL staged), but if you stage
  anything under `sql/_migrations/` on this Windows box, the prior CRLF-drift caveat may still bite —
  use `SQL_SYNC_SKIP=1 git commit` then.
- Memory updated: `project_reporting_phase3` (3e applied + live-verified on INT),
  `project_int_migration_crlf_drift` (drift doesn't manifest when working-tree EOL matches the
  ledger), and a new `project_reporting_sqlcmd_utf8_bug` (finding A).
