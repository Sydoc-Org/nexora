# Handoff — Reporting AI Assistant: enabled & live-verified on INT (Azure)

- **Date:** 2026-06-03
- **Branch:** `feature/2.5.63`. Git mode this session was **commit + push** (explicitly chosen).
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-03-ai-phase1-implementation-complete-handoff.md`
- **Plan (feature source of truth):** `docs/superpowers/plans/2026-06-03-reporting-ai-phase1.md`

## TL;DR

- The Reporting AI assistant (built in the prior session) is now **enabled and
  verified end-to-end on INT** using **Azure OpenAI**. A real natural-language
  question produced valid read-only T-SQL, landed in the SQL editor, and was
  audited — all through the live provider.
- **This session changed no tracked files.** Enabling the assistant was pure
  configuration in `env/INT.env` (gitignored). The only code-repo artifact is
  **this handoff**.
- **Highest-value next step is unchanged and now concretely motivated:** provision
  the two **read-only SQL logins**. Without them the assistant has no live schema
  and drafts a placeholder table name (`FROM FIELDS`) that won't run.

## What was configured (INT only, all in gitignored `env/INT.env`)

| Key | Value |
|---|---|
| `AI_PROVIDER` | `azure` |
| `AZURE_OPENAI_ENDPOINT` | `https://sydoc-ai-services.services.ai.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o-mini` (audited as the "model") |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` |
| `AZURE_OPENAI_KEY` | (secret; in `env/INT.env`, never committed) |

Notes on the Azure side (discovered live):
- The user first created a **standalone Azure OpenAI resource** `azureopenainexora`
  but it has **zero model deployments** — it is unused/empty. Ignore or delete it.
- The working deployment lives under an **Azure AI Foundry / AI Services** resource
  **`sydoc-ai-services`**. nexora's classic client path
  (`{endpoint}/openai/deployments/{name}/chat/completions?api-version=…`) works
  against the `services.ai.azure.com` host (also against the `.openai.azure.com`
  and `.cognitiveservices.azure.com` aliases — all three were probed OK).
- Azure OpenAI is **billed separately** from the user's Claude Max plan (Max gives
  no API access). Per-token on the Azure subscription; the test cost a fraction of
  a cent.

## How it was verified (live, on INT)

1. Restarted nexora (`bin\nx.ps1 -r`) so `config.py` reloaded `env/INT.env`.
2. `nx`/Playwright as `ben.streich` → `/reporting` → **Ask AI** tab renders
   (so `reporting.ai.use` is active for admins on INT).
3. Asked *"Top 10 subcategories by total quantity"* → `gpt-4o-mini` returned a
   valid read-only `SELECT TOP (10) …`, passed the sqlglot gate (Insert button
   shown), **Insert into SQL editor** switched to SQL mode with the query loaded.
4. `dbo.ReportingAiAudit` row **Id 1**: `provider=azure`, `model=gpt-4o-mini`,
   `GateVerdict=valid`, `Status=ok`, `TokensIn/Out=228/53`, `DurationMs=741`,
   prompt = the question only (no result rows — egress contract holds).

Screenshots: `var/screenshots/reporting_ai_live_0{1..4}_*.png`.

## Owner actions / next steps

1. **Provision the two read-only SQL logins** (`DB_REPORTING_RO_USER/PWD`,
   `DB_REPORTING_OCTO_RO_USER/PWD`) and set them in `env/INT.env`, then restart.
   This is what makes AI-drafted SQL **runnable**: with them, `_ai_schema_text()`
   serializes real `INFORMATION_SCHEMA` table/column names from Statistics +
   Octopus, instead of only the curated catalog. Until then the model has no real
   table to put in `FROM` (it guessed `FIELDS`). These RO logins also unblock the
   plain SQL sandbox + scheduled reports (pre-dates the AI work).
2. **Rotate the Azure key.** The live `sydoc-ai-services` key was pasted into the
   session chat transcript. Regenerate it (KEY 1/KEY 2 swap) in the portal and
   update the one line in `env/INT.env`.
3. **Enable in other environments** when desired: set the same `AI_*` keys in
   `env/<ENV>.env`, **apply migrations `0013`/`0014` to that DB**
   (`python scripts/db-migrate.py --env PROD`), restart. Migrations are currently
   **INT-only**; PROD/STAGING/TEST do not have `ReportingAiAudit` or the perms.
4. **Cost controls** (optional): the assistant has no per-user/day budget cap in
   Phase 1; consider one if usage grows. Each ask is a few hundred tokens.

## Gotchas

1. **No tracked changes this session** — `git status` was clean throughout; the
   provider config is gitignored. `docs/` is excluded from `deploy.yml`, so this
   handoff needs no exclude entry.
2. **`AI_MODEL` is ignored when `AI_PROVIDER=azure`** — the model is the deployment
   name (`AZURE_OPENAI_DEPLOYMENT`). The `env/INT.env` line was commented to avoid
   confusion.
3. **The data-plane `GET /openai/deployments` list API returns `[]`** even when
   deployments exist (it's deprecated / doesn't reflect Foundry-created
   deployments). Validate a deployment by actually calling
   `…/chat/completions`, not by listing.
4. **Pushing runs the full e2e gate.** Reset TEST first
   (`python scripts/test_db_reset.py`); TEST builds from `seed.sql`, not
   migrations, so the AI perms are absent there and no e2e exercises the AI panel.

## Resuming in a fresh session

The feature is built, enabled on INT, and live-verified. The next meaningful work
is **operational, not code**: provision the RO SQL logins (item 1) so the
assistant produces runnable SQL, rotate the Azure key (item 2), and decide whether
to enable PROD/STAGING (item 3). No build work remains for Phase 1.
