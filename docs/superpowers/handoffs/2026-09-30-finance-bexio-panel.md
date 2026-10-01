# Handoff: Finance "Invoiced in Bexio" panel in PR #426 (#423)

**Date:** 2026-09-30 · **Branch:** `feat/423-finance-bexio` (cut from `main` @ `84b5fc9c`), main
checkout, no worktree · code **pushed**, PR #426 open, CI green, live on `dev-nexora.sydoc.ch` ·
this handoff is commit-only (remote), so the branch is 1 ahead of origin after it · issue #423
stays open until the PR merges.

**Prior handoff:** [`2026-09-29-sydoc-finance-page-shipped.md`](2026-09-29-sydoc-finance-page-shipped.md)

## This session's commits

- `3d323e27` feat(finance): show what was invoiced in Bexio beside the figures (#423). 31 files.
- `0f55f409` test(finance): commit Bexio link cleanup on its own connection (#423). Fixes the one
  CI failure of the first run.

## TL;DR

- The owner asked what Bexio could add to `/finance`. Of the four ideas, they approved **1
  (reconciliation)** and **2 (amounts from Bexio)**. They ruled out **3/4 (drafting invoices in
  Bexio)** until they know how invoicing is done and their boss approves it. Prices are calculated
  in Bexio; nexora keeps none.
- `/finance` now has a read-only **"Invoiced in Bexio"** panel above the sections. For billed month
  M it lists invoices dated in **M + 1**, per Finance client, with status, amount excl. VAT, total,
  lines on demand and the PDF. It flags clients with no linked contact, no invoice or only a draft.
  Contacts are linked to clients from the panel (`finance.month.edit`, `dbo.FinanceBexioContacts`,
  migration `0141`, applied on INT).
- **Blocked on a token:** the `BEXIO_PAT` in `env/INT.env` gets 401 on every endpoint. It is in
  date (issued 2026-05-28, expires 2026-11-27), so it was most likely revoked. The owner will create
  a new PAT **tomorrow (2026-10-01)**.

## What shipped

| area | files | commit |
|---|---|---|
| Read-only Bexio client: search/GET only, 5-min cache, `BexioError`, pure window/normalize/reconcile | `nx_lib/bexio.py` | `3d323e27` |
| Routes: `GET /api/finance/bexio?month=[&fresh=1]`, `GET …/invoice/<id>`, `GET …/invoice/<id>/pdf`, `POST …/link`, `POST …/unlink` | `nx_lib/views/finance_bexio.py`, `nx_lib/__init__.py` | `3d323e27` |
| Client list for the panel (`billed_clients()`, Sydoc services excluded) | `nx_lib/finance.py` | `3d323e27` |
| Panel shell, strings, behaviour, styles | `templates/finance.html`, `templates/js/_finance_js.html`, `static/js/finance_bexio.js`, `static/css/finance.css` | `3d323e27` |
| `BEXIO_PAT` config + env templates | `nx_lib/config.py`, `env/*.env.example` | `3d323e27` |
| Link table (PK ContactId, index on Client) + test-schema mirror | `sql/_migrations/NexoraDB/0141_finance_bexio_contacts.sql`, `sql/test/schema.sql` | `3d323e27` |
| Read-only token check | `scripts/bexio-probe.py` | `3d323e27` |
| Tests | `tests/unit/test_bexio.py` (35, module at 100%, added to `MIN_COVERAGE`), `tests/integration/test_finance_bexio_routes.py` | `3d323e27`, `0f55f409` |
| de/fr/it (44 msgids) | `messages.pot`, `translations/*` | `3d323e27` |
| Docs | `docs/howto/finance.md` ("Invoiced in Bexio" section, files table), `docs/howto/outage-monitor.md` + `ops/outage_monitor.py` (stale "nothing calls Bexio" notes), `CLAUDE.md`, `CHANGELOG.md` | `3d323e27` |

## Next steps

1. **The owner brings a new PAT** (developer.bexio.com/pat, or office.bexio.com, then Settings,
   Security, Personal Access Tokens; **not** "My apps / Create new app", which is OAuth). It needs
   invoice and contact read scopes, is shown only once, and lasts 6 months.
2. They put it in `env/INT.env` locally **and** in the dev folder's `env\INT.env` on SYAPP01, by
   hand; deploys never copy env files. Restart the app, since the token is read at import.
3. Run `.venv\Scripts\python.exe scripts\bexio-probe.py INT`. The invoice and contact lines must be
   `ok`. Never print the token.
4. Open `/finance?month=2026-08` on dev. **Confirm the M+1 assumption** against real invoices. If
   it's wrong, change `INVOICE_MONTH_OFFSET` in `nx_lib/bexio.py`.
5. **Check that contact search accepts `criteria: "in"` on `id`.** This was never tested against the
   real API. If it doesn't, names fall back to `#<id>`, which is logged and not fatal, and
   `contact_names` needs another query.
6. Link each client's contacts once from the "other invoices" list. Then merge PR #426 to staging.
   STAGING/PROD need their own PAT in their env files (`scripts/env-sync.py` lists the key).

## Gotchas & notes

- **Real Bexio was never called with a working token.** Every field name and status id
  (7 draft, 8 open, 9 paid, 16 partial, 19 cancelled, 31 unpaid) comes from the retired invoices
  code plus Bexio's documented API. Excl. VAT is computed as `total - total_taxes`, and the Bexio
  link is `office.bexio.com/index.php/kb_invoice/show/id/<id>`. Verify both on first real data.
- UI was checked against a **stubbed** Bexio: the scratchpad script patched `nx_lib.bexio`
  functions before importing `nx_main` and served on :8010. The test links on INT (contact ids
  910001–910004) were removed afterwards.
- `/finance` already scrolls sideways on a phone, with or without the panel. That is pre-existing
  and was not fixed.
- The per-object DDL dump `sql/NexoraDB/Tables/dbo.FinanceBexioContacts.sql` is **missing**: there
  is no mssql-scripter here. The next `sql/sync-from-db.py` run adds it. Commits used
  `SQL_SYNC_SKIP=1` and the venv on PATH (mypy hook).
- The `db_conn` test fixture is a SQLAlchemy connection inside a rolled-back transaction. Cleanup of
  rows that routes commit needs its own `raw_connection()` (that was the first CI failure).

## Untracked / left for owner

- `.claude/worktrees/` is untracked and predates this session. It was left alone.

## How to verify

```
ENVIRONMENT=TEST .venv/Scripts/python.exe -m pytest tests/unit/test_bexio.py tests/unit/test_translations.py tests/unit/test_finance.py -q
.venv\Scripts\python.exe scripts\bexio-probe.py INT
gh pr checks 426
```

The full local unit suite currently has 9 failures and 6 errors in db, security, maintenance,
ms02-config and workitem-source tests. `main` has the same ones on this box (placeholder
`TEST.env`), and CI is green (3,040 passed).

## Resuming in a fresh session

`/reset-session` picks this file up (the only 2026-09-30 handoff). Start at **Next steps 1**: ask
whether the new PAT is in place, then run the probe.
