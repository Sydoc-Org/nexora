# Handoff — Reporting AI Assistant Phase 1: implemented, reviewed, pushed

- **Date:** 2026-06-03
- **Branch:** `feature/2.5.63` — **pushed to origin** (this session's git mode was
  *commit + push*, explicitly authorized). `origin/feature/2.5.63` is at `1839277`.
  The **handoff commit itself is NOT pushed** (per the `/hcc` rule) — push it yourself
  with your next action if you want it on the remote.
- **Feature commits (all on origin):** `1724896` → `2437ec3` (13 AI-feature commits) plus
  `1839277` (a pre-existing e2e test-isolation fix surfaced by the push gate). Run
  `git log --oneline 24ce02b..1839277` for the full stack.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-03-ai-phase1-plan-and-workflow-commands-handoff.md`
- **Plan (source of truth):** `docs/superpowers/plans/2026-06-03-reporting-ai-phase1.md`

## TL;DR

- **Built the entire Reporting AI Phase-1 feature** from the plan — all 7 tasks —
  using subagent-driven development: a fresh implementer per task + two-stage review
  (spec compliance → code quality) after each, with the controller fixing every
  reviewer finding before moving on.
- An **"Ask AI" mode** on the Reporting page turns a natural-language question into
  **read-only T-SQL placed in the SQL editor** (no auto-run). Server-side,
  provider-agnostic (`AI_PROVIDER=anthropic|azure|none`), **schema-only egress**
  (the model never sees result rows), every draft self-validated through the existing
  sqlglot gate, audited to `dbo.ReportingAiAudit`. Ships **disabled** (`AI_PROVIDER=none`
  → route 503s, tab hidden) until a provider key is provisioned.
- **Pushed** on `feature/2.5.63`. The push initially failed the **pre-push gate** on an
  e2e test — root-caused to a **pre-existing test-isolation bug (not the AI feature)**,
  fixed, and re-pushed green.
- Verified: **170 reporting tests + 7 translation tests + the full pre-push suite all
  pass; ruff clean; no new dependency; egress contract traced and confirmed.**

## What shipped

| File(s) | Change |
|---|---|
| `sql/_migrations/NexoraDB/0013_create_reporting_ai_audit.sql` | NEW — `dbo.ReportingAiAudit` (schema-only audit: prompt + generated SQL, never rows). Applied to **INT**. |
| `sql/_migrations/NexoraDB/0014_seed_reporting_ai_permissions.sql` | NEW — `reporting.ai.use` + `reporting.ai.sql`, seeded to every `admin.view` profile. Applied to **INT**. |
| `nx_lib/reporting/ai.py` + `tests/unit/test_reporting_ai.py` | NEW — provider-agnostic client (Anthropic/Azure, injectable HTTP transport), parses JSON/fenced replies, self-validates via `sandbox.validate_select`. 9 tests. |
| `nx_lib/reporting/ai_schema.py` + `tests/unit/test_reporting_ai_schema.py` | NEW — bounded/logged schema serializer from RO `INFORMATION_SCHEMA` + curated catalogs; **owns/closes its RO connections**. 4 tests. |
| `nx_lib/views/reporting.py` + `tests/integration/test_reporting_ai_routes.py` | MOD — `_ai_config`/`_accessible_sql_targets`/`_ai_schema_text`/`_audit_ai` + `POST /api/reporting/ai/ask` (gated `reporting.ai.use`+`reporting.ai.sql`, rate-limited, audited) + `ai_enabled` template flag. 5 tests. |
| `templates/reporting.html`, `templates/js/_reporting_ai_js.html`, `static/css/reporting.css` | NEW/MOD — gated "Ask AI" mode button + panel; only action is **Insert into SQL editor** (+ Copy); hides field/wells sidebars in AI mode (symmetric with SQL mode). |
| `env/{INT,PROD,STAGING,TEST}.env.example` | MOD — sanitised `AI_*` keys. |
| `CHANGELOG.md`, `docs/howto/reporting.md`, `CLAUDE.md` | MOD — documented perms/route/env/table/egress guarantee. |
| `messages.pot`, `translations/{de,fr,it}/…/messages.po` + `.mo` | MOD — de/fr/it for all new strings (translation gate green). |
| `tests/e2e/test_reporting_sql.py` | MOD — **pre-existing fix** (not AI): clears the admin's stale SQL ack at test start so the first-use modal is exercised regardless of test order. |

## Owner actions / next steps

1. **Decide the AI provider** (Azure OpenAI vs Anthropic) — the ups/downs table is at the
   top of the plan. The build is **not blocked** on this (provider-agnostic; default
   `none`). Azure = tenant-resident (compliance default); Anthropic = best T-SQL quality
   but data leaves the tenant (needs zero-retention terms). Phase-1 egress either way is
   the question + schema metadata only.
2. **To enable it in any environment:** set `AI_PROVIDER` + the matching key/endpoint in
   that env's `env/<ENV>.env`, **apply migrations `0013`/`0014` to that DB**
   (`python scripts/db-migrate.py --env PROD` — admins are auto-granted the perms by
   `0014`), and restart. Until then the route 503s and the tab is hidden.
3. **Push the handoff commit** (this file) if you want it on origin — everything else is
   already pushed. **No PR was opened** (a `→ main` PR is an owner action).
4. **(Carried, unchanged from prior handoffs)** Provision the two RO SQL logins
   (`DB_REPORTING_RO_*`, `DB_REPORTING_OCTO_RO_*`); wire the scheduled-reports Windows
   Task Scheduler task. These pre-date the AI work.

## Gotchas & notes

1. **The pre-push hook runs the FULL suite, including Playwright e2e.** `git commit` only
   runs the light hooks; **e2e runs only on `git push`**. e2e needs a freshly reset TEST
   DB — run `python scripts/test_db_reset.py` before pushing (it applies
   `sql/test/schema.sql` + `seed.sql`; it does **NOT** apply `sql/_migrations/`, so
   `reporting.ai.*` perms are absent in TEST → the AI panel does not render there).
   Stale `dbo.ReportingSqlAck` rows persist across runs and break order-dependent e2e
   tests. `--no-verify` is forbidden by CLAUDE.md.
2. **The e2e fix (`1839277`) is unrelated to the AI feature.** `test_reporting_save` acks
   `admin@test.local`; pytest collects it before `test_reporting_sql`, which expected the
   user un-acked. It only surfaced now because this is the **first push since those e2e
   tests were added** (prior reporting sessions were commit-only; their "663 backend
   tests" excluded e2e). Fixed by clearing the ack at the start of `test_reporting_sql`.
3. **Egress contract** was explicitly traced: the provider request body contains only the
   system prompt + the user's question + schema metadata; the response returns
   `{sql, explanation, valid, target, model}` (no rows); API keys live only in request
   headers (never logged/returned/audited). The drafted SQL is **never executed** in this
   path — running still goes through the unchanged gated `/api/reporting/sql/run`.
4. **No new dependency** (`requests` + `sqlglot` already present); **no `deploy.yml`
   change** (all runtime files under already-synced dirs; `docs/` is excluded); **no CSP
   change** (provider call is server-side).
5. The migrations are applied to **INT only**. `dbo.ReportingAiAudit` and the perms do not
   exist in PROD or TEST yet (TEST builds from seed.sql, not migrations).

## How to verify

```powershell
git -C C:\dev\nexora log --oneline 24ce02b..1839277      # the pushed feature stack
# Reporting + translation suites (fast):
python -m pytest tests/unit/test_reporting_*.py tests/integration/test_reporting_routes.py `
  tests/integration/test_reporting_ai_routes.py tests/unit/test_translations.py `
  -o addopts="" -p no:cacheprovider -q
# E2E (needs a reset TEST DB + a free port 8765):
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_sql.py tests/e2e/test_reporting_save.py `
  -o addopts="" -p no:cacheprovider -q
```

Browser smoke (admin has the perms on INT): `nx -u -b --loginas:ben.streich`, open
`/reporting`, click **Ask AI** → panel shows; with `AI_PROVIDER=none`, **Ask** returns
"The AI assistant is not configured" (503). Screenshots from this session are in
`var/screenshots/reporting_ai_0*.png`.

## Resuming in a fresh session

The feature is **complete and pushed**; there's no remaining build work. A fresh session's
job is one of the **owner actions** above — most likely: pick a provider, set
`AI_PROVIDER` + the key in `env/<ENV>.env`, apply `0013`/`0014` to that DB, and do a live
end-to-end test (ask a question → valid T-SQL appears → Insert → run via the gated path →
confirm a `dbo.ReportingAiAudit` row). The plan
(`docs/superpowers/plans/2026-06-03-reporting-ai-phase1.md`) documents the contract; this
handoff is the state of record.
