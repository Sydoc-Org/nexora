# Handoff — Permission-gated doc-fields (Validation User) — PLAN written, ready to execute

**Date:** 2026-07-13 (late afternoon) · **Branch:** `feature/2.5.64` · **+3 unpushed at handoff-write time** (pr115 handoff `1995473`, plan `cd73a8a`, this handoff) · **commit-only (remote session — owner pushes)**
**Prior handoff:** `2026-07-13-pr115-ship-ci-speedups.md` (same day — PR #115 shipped + CI speedups)

## TL;DR

- A **complete, adversarially-sanity-checked implementation plan** is written and committed
  (`cd73a8a`): `docs/superpowers/plans/2026-07-13-docfield-permission-gating.md`. **No code changed
  this session** — planning only.
- Feature: add a new searchable doc-field **"Validation User"** and make doc-fields
  **permission-aware** — fields flagged sensitive are hidden (name AND value) from users without one
  new shared permission `workitems.filter.documentfields.sensitive`, enforced **server-side at every
  surface**: search dropdown, values API, search filtering, detail panel, CSV export.
- **The `/write-plan` multi-agent workflow was rate-limited** (account session limit, resets 5pm
  Zurich) — all 5 agents died. The plan was instead authored from a **full single-session recon of
  every doc-field code path plus inline red-team**; **every file/symbol/snippet anchor was Grep/Read
  verified** against the live repo. Quality is plan-grade, just not multi-agent-cross-checked.
- **Next: `/execute-plan`** (subagent-driven, 8 tasks / 6 phases). No worktree — work was done
  directly on `feature/2.5.64`.

## This session's commit

```
cd73a8a  docs(plans): add docfield-permission-gating implementation plan   (this session)
```
(`1995473` = the prior pr115 handoff, still unpushed. `604e6c9` = last pushed commit / origin tip.)

## What the plan covers (so you don't re-derive it)

The feature has two field namespaces and the plan gates both:
1. **Doc-field SEARCH** keys off `dbo.SearchConfig.col_<FieldKey>` (default→StatisticsDB, ms02→PG
   `DossierStatistik`). Surfaces: `api_config_fields` (`/api/config/fields` dropdown list),
   `api_docfield_values` (`/api/docfield_values` autocomplete), the two doc-field pre-fetch blocks in
   `_get_workitems_data`.
2. **Octo EXTRACTION fields** key off `octo.get_extensions_urls_fields` `field_mapping` target keys
   (`fields` dict + `field_sources` list from `field_locations.extract_field_locations`). Surfaces:
   `get_media_info` `_suppress` closure (detail panel) + `export_workitems_csv`.

Design (locked decisions in the plan):
- Sensitivity is **data-driven**: new `dbo.Search_Field_Labels.IsSensitive BIT` flag, one shared perm
  `workitems.filter.documentfields.sensitive`. Migration **`0035`** adds `col_validationuser`, the
  `IsSensitive` flag, a `validationuser` label row (EN/DE/FR/IT) flagged sensitive, and seeds+grants
  the permission (0018 grant pattern).
- Two cached readers `get_sensitive_field_keys()` (exact FieldKey, for search) /
  `get_sensitive_field_tokens()` (normalized FieldKey+labels, for fuzzy Octo-name matching) + pure,
  unit-tested strip helpers. Enforcement is post-cache; `api_config_fields` cache key gets a `_s{0|1}`
  perm-state suffix (no cross-user leak).

Plan tasks: **P1** migration 0035 · **P2** helpers (unit-first) · **P3** dropdown + values API +
search resolution · **P4** detail panel + CSV export · **P5** changelog/CLAUDE.md · **P6** live INT
browser verify.

## Next steps (ordered)

1. **`/execute-plan`** → runs `docs/superpowers/plans/2026-07-13-docfield-permission-gating.md`
   task-by-task (subagent-driven). Re-verify migration `0035` is the free number first (dir tops out
   at `0034`).
2. **Owner actions baked into the plan** (executor cannot do these — they're in the plan's "Owner
   actions" section): (a) **map the field to its real source column** — `0035` leaves
   `col_validationuser` NULL; owner runs `UPDATE dbo.SearchConfig SET col_validationuser='<RealCol>'
   WHERE ProcessName=… AND ClientCode=…` (until then the field never surfaces, harmless); (b) confirm
   the Octo extraction target-key normalizes to `validationuser`/a seeded label or add the spelling;
   (c) grant the perm to the right non-admin profiles; (d) PROD rollout via deploy or
   `db-migrate.py --env PROD`.

## Gotchas & notes (READ before executing)

- **Test DB has NO `SearchConfig` / `Search_Field_Labels` table** (verified — absent from
  `sql/test/schema.sql`). So enforcement **logic** is proven by **pure unit tests**; **wiring** by
  monkeypatching the `wv.*` seams. The values-API gate is observable in CI via the "blocked → `[]`
  BEFORE the absent-table query, vs un-blocked → 500 on the missing table" trick (in the plan). Do
  **not** add those tables to the test schema for this feature — out of scope, the seams cover it.
- **wv-local `has_permission` trap:** in-body perm checks resolve `nx_lib.views.workitems.has_permission`
  — tests must `monkeypatch.setattr(wv, "has_permission", …)`, not the security module. Same for the
  new module-level helpers (`wv.get_sensitive_field_keys`, `wv.get_valid_search_columns`, …).
- **Cache poisoning is already solved and must stay solved:** `media_info_{wid}` caches the full
  fields dict; the sensitive strip runs **inside `_suppress` post-cache** (like confidence/location).
  Never strip before a cache write.
- **`api_config_fields` is login-gated only** (no doc-field perm) — it was the sneaky field-NAME leak;
  the plan's P3 closes it with `_s{0|1}` cache key + option filtering.
- **`field_sources` (not just `fields`) carries the value + highlight location** → the panel strip
  removes both, or the overlay leaks.
- **i18n: NO pybabel cycle** — doc-field labels are DB-driven (`Search_Field_Labels` 4-language
  columns), not `gettext`. No new `_()` strings in this feature.
- **`page_visibility()` needs no entry** (it holds page-level perms only; filter-level perms aren't in
  it — consistent with existing `workitems.filter.*`).
- **Sequencing:** builds on this branch's already-committed pdbsUser work — migration `0034` and
  case-insensitive `has_permission` are prerequisites (the new perm code relies on both). No conflict.
- **The `/write-plan` workflow itself is rate-limited until ~5pm Zurich.** If you want the full
  multi-agent treatment (dual drafts + red-team) as a cross-check, re-run `/write-plan` after the
  reset and diff against this plan — optional; the committed plan is complete and self-contained.

## Untracked / left for owner

- Working tree clean. Nothing untracked left behind. All unpushed commits (`1995473`, `cd73a8a`, this
  handoff) are the owner's to push.
- Scratchpad workflow transcript at
  `…/subagents/workflows/wf_80d31ae1-301` — the rate-limited run's dead agent logs; ignore/discard.

## How to verify

```powershell
# From C:\dev\nexora (feature/2.5.64):
git log --oneline 1995473..HEAD          # this session's plan commit + this handoff
git status --porcelain                    # empty
# The plan is the deliverable — open it:
#   docs/superpowers/plans/2026-07-13-docfield-permission-gating.md
# No tests run this session (planning only). Executor's per-task tests are in the plan.
```

## Resuming in a fresh session

Run `/reset-session` (the `var/handoff-pending` flag points here), then `/execute-plan`. **Two
handoffs share today's date** — if the flag is gone, target this file explicitly:
`/reset-session docs/superpowers/handoffs/2026-07-13-docfield-permission-gating-plan.md`.
The plan to execute: `docs/superpowers/plans/2026-07-13-docfield-permission-gating.md`.
