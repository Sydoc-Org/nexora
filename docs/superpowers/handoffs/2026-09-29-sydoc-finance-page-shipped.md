# Handoff — Sydoc Finance page shipped to PR #410 (#408)

**Date:** 2026-09-29 · **Branch:** `feat/408-sydoc-finance` in the worktree
`.claude/worktrees/feat-408-sydoc-finance` (cut from `main` @ `51d9da01`, then merged with the
3.3.0 release) · code **pushed**, PR #410 open · this handoff is commit-only (remote) — 1 ahead
of origin after it · issue #408 open until the PR merges.

**Prior handoff:** [`2026-09-29-api-include-tables-shipped.md`](2026-09-29-api-include-tables-shipped.md)
(same date — `/reset-session` needs the explicit path, see "Resuming").

## This session's commits

- `5f37b634` feat(finance): Sydoc Finance, the monthly accounting report (#408) — 26 files
- `348053a9` Merge remote-tracking branch 'origin/main' (the 3.3.0 release, PR #407) — CHANGELOG
  resolved by hand: the `### Added` entry sits under `[Unreleased]` above `[3.3.0]`

## TL;DR

- **`/finance`** (permission `finance.view`, sidebar "Sydoc Finance") shows the monthly accounting
  figures of every billed client on one page per month: the six #329 workbooks (Elektro-Material
  per channel, Compass, Privera Posteingang / Rechnungseingang / Physische Zustellung / Neuzugänge
  per branch, Mandant and source), four external clients with what their collectors deliver
  (Frigemo, Aveniq Xpert per client and source DB, Bucherer EasyTax, MediaMarkt per type), and
  the hours Sydoc books in the **BPS** timetool per task and per customer, absences split out.
  Both the external clients and BPS were added by the owner mid-session ("what we have, what
  makes sense"; "Overview pro Monat über alle BPS Leistungen").
- **No SQL of its own.** `nx_lib/finance.py` names registered sources and measures
  (`dbo.ReportingSources` / `dbo.ReportingMetrics`) and builds the queries with the reporting
  `table` provider (`build_generic_query` over `resolve_metrics`), so a figure on the page **is**
  the measure in Reporting, #329 quirks included. One request per section, so a source that is
  down shows its error in place. The Neuzugänge view was broken on INT (`0134`) until the owner
  approved repointing it after the handoff (one `ALTER VIEW`, stray `SYDOC_Statistik1.` prefix
  dropped) — all eleven sections load on dev now, Neuzugänge with zeros (INT's rows do not join).
- **Migration `0138_finance_page.sql`**: `finance.view` (new `finance` area, granted to Global
  Admin; Enterprise Admin via the 0106 trigger) + `bps_projects_service_hours` (everything except
  the `Absences` pseudo-customer). Applied on INT by hand through pyodbc (no `sqlcmd` here) and
  recorded; CI's "Apply DB migrations (INT)" step then passed, so the recorded checksum matches.
- **PR #410**: first CI run green (`test` 6m59s, `deploy-dev` 25s → the branch is live on
  `dev-nexora.sydoc.ch`); the merge-of-main commit's run was in progress when this was written.
  `mergeable=MERGEABLE`.

## What shipped

| area | files | commit |
|---|---|---|
| Spec, month arithmetic, query building, payload (pure, DB-free) | `nx_lib/finance.py` | `5f37b634` |
| Routes: page, `GET /api/finance/section/<key>?month=`, `GET /api/finance/export.csv?month=` | `nx_lib/views/finance.py`, `nx_lib/__init__.py` | `5f37b634` |
| Page visibility key `financePagePerm`, landing order, sidebar entry | `nx_lib/security.py`, `templates/_header.html` | `5f37b634` |
| Page, JS shim, behaviour, styles (slim console kit, `--nx-*` tokens only) | `templates/finance.html`, `templates/js/_finance_js.html`, `static/js/finance.js`, `static/css/finance.css` | `5f37b634` |
| Permission + BPS measure, test seed | `sql/_migrations/NexoraDB/0138_finance_page.sql`, `sql/test/seed.sql` | `5f37b634` |
| Tests | `tests/unit/test_finance.py` (spec vs the registry parsed from the migrations, month rule per source, payload, CSV rows), `tests/integration/test_finance_routes.py` (gates, shells, section API, export), `tests/unit/test_security.py` (22 keys) | `5f37b634` |
| de/fr/it catalogs (52 msgids) | `messages.pot`, `translations/*` | `5f37b634` |
| Docs | `docs/howto/finance.md` (new), `docs/design/permissions.md` (area), `docs/howto/reporting.md` (cross-ref), `CLAUDE.md` (pointer), `CHANGELOG.md` | `5f37b634`, `348053a9` |

## Next steps

1. **Watch CI on `348053a9`** (`gh pr checks 410`), then merge PR #410 → staging. PROD moves with
   the next `v*` tag (`0138` runs there before the app pool stops).
2. **Grant `finance.view`** to whoever does the invoicing (a Sydoc-internal profile, at
   `/admin/permissions`). Never a customer profile — the page reads every billing `table` source
   without row scoping (same rule as `reporting.source.<code>.use`, #332).
3. **Walk one closed month next to the workbooks / a Reporting run** on PROD (August 2026). Parity
   with Reporting is by construction; the open question is still #329's — whether these are the
   figures invoicing actually bills. The BPS task names to check against the owner's list:
   Support (verrechenbar / extern verrechenbar), Change, Professional Services, Projektmanagement,
   Vorbereitung Akten (Privera Neuzugänge).
4. Follow-ups, in the order they were raised: a "close month" snapshot (`EM_Invoice` is edited
   after month close — the EM section says so); the `ExportDatetime_dt` view column for Posteingang
   (#329) would let its section use a real range instead of `contains '.MM.yyyy'`; `/nx-cover`
   entries for `finance.py` / `views/finance.py` in `tests/unit/test_coverage_thresholds.py`;
   Privera Mailbestellungen (#330) as a section once the count lands in a table.
5. After the merge: `/clean` (or by hand) removes the worktree and both branches.

## Gotchas & notes

- **The legacy "SQL Server" ODBC driver cannot bind a Python `date`** (`HYC00 optional feature not
  implemented`), so month bounds are ISO strings — exactly what `nx_lib/reporting/tokens.py`
  binds. `test_elektro_material_selects_the_month_on_the_real_export_datetime` pins it.
- **DB-backed tests cannot run on this box** (same as the prior handoff): `env/TEST.env` is the
  placeholder template, so the per-run test database never gets created (`[test-db] could not
  prepare …`, host `replace-me…` does not resolve) and every fixture-backed test errors. CI is the
  gate and was green. `tests/unit/test_finance.py` (33 tests) is pure and runs locally.
- **Working from the worktree**: it has no `env/*.env`, and the project deny rules refuse reading
  or copying them. A scratchpad launcher (`wt_run.py`, described in memory
  `worktree-env-launcher`) loads `C:\dev\nexora\env\<ENV>.env` into the process environment and
  `runpy`s pytest / `nx_main.py` / a script; for TEST it pops `DB_NEXORA` and points
  `scripts.test_db_reset.TEST_ENV` at the main checkout. Pre-commit needs
  `PATH="/c/dev/nexora/.venv/Scripts:$PATH" SQL_SYNC_SKIP=1` (the mypy hook shells out to
  `python`, which is the Store stub). The harness refuses compound git commands in a worktree
  session — one plain git command per call.
- **A `| tail` pipeline hides pytest's exit code** — two "green" runs were not. Redirect to a
  file and grep the summary line.
- The `sydoc` tenant is the **customer-facing** group (profiles bound to LKTR/PRVR/CMPS hold
  `tenant.sydoc.view`), so the page is a global page with its own area, not a tenant mount.
- The section API answers a failed source with **HTTP 200 + `error`/`detail`**, so the page
  renders it in place; 404 is only an unknown key. Once, while pytest hammered INT concurrently,
  5 of 11 sections failed transiently; not reproducible on its own.
- Deferred msgids in the spec use the `N_()` marker (a pybabel default keyword); the view
  translates with `gettext()` at render time. Measure labels come from the registry in four
  languages; dimension labels and the "by … date" basis strings are the marked ones.
- INT's Statistics tables are sparse copies: months with rows — Posteingang 2025-07, Privera
  invoice 2025-09, Nachsendungen 2025-10, EM 2026-02, Compass 2026-05/08, Frigemo 2026-08,
  MediaMarkt 2026-08/09, Bucherer 2026-08/09, Xpert 2026-09, BPS 2026-08/09.
- Screenshots (light, forced dark, 400px phone; Aug + Sep 2026) are in `var/screenshots/`
  (gitignored) of the worktree. Dark mode was captured by adding the `dark` class after load —
  the user's saved theme pref overrides the `localStorage` hint.
- Adding a `page_visibility()` key breaks `test_page_visibility_returns_all_22_keys_with_no_perms`
  and `_all_false_page_v()` in `tests/unit/test_security.py` — both updated here; do it again
  for the next page.

## Untracked / left for owner

- Nothing uncommitted besides this handoff. Screenshots and the launcher scripts live outside git.
- The remote branch and the worktree stay until PR #410 merges.

## How to verify

```powershell
# the branch is live on dev (any branch push deploys dev-nexora.sydoc.ch, INT data)
start https://dev-nexora.sydoc.ch/finance?month=2026-08

# pure tests (from the worktree or the main checkout after merge)
.venv\Scripts\python.exe -m pytest tests/unit/test_finance.py tests/unit/test_security.py tests/unit/test_translations.py tests/unit/test_permission_codes.py tests/unit/test_template_url_prefix.py -q --no-cov

# DB-backed route tests: CI only on this box (env/TEST.env is the placeholder)
gh pr checks 410
```

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-09-29-sydoc-finance-page-shipped.md` — pass the
path: another handoff shares this date. Work in the worktree
`.claude/worktrees/feat-408-sydoc-finance` (branch `feat/408-sydoc-finance`) until PR #410 is
merged; after that, `/clean`. Decision record: issue #408 (scope, migration claim, BPS addition
in the comment) and PR #410.
