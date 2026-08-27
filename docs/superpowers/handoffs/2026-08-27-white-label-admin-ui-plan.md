> **Newer handoff same day:** see
> [`2026-08-27-reporting-dashboard-mask-resize-delete-label.md`](2026-08-27-reporting-dashboard-mask-resize-delete-label.md)
> for unrelated dashboard-UI work done later on 2026-08-27. `/reset-session` may not pick this
> file by date alone — pass the explicit path for whichever session you mean to resume.

# Handoff — white-label + admin onboarding UI (#98 phase 4) planned; ready to execute

**Date:** 2026-08-27 · **Branch:** `v3.2.3.1` (main checkout, no worktree) · **3 commits this
session; 28 commits ahead of `origin/v3.2.3.1`, unpushed** · commit-only (owner pushes) · tree
carries CRLF-only dump dirt that is not this session's — see Gotchas #2.

**This session's commits** (oldest → newest):

- `28adb01e` — `docs(plans): add white-label and admin onboarding UI plan`
- `7a9d79a0` — `docs(handoff): white-label admin UI planned, ready to execute`
- *(this file's update)* — `0076` checksum drift diagnosed and re-blessed; Gotchas #1 closed

**Prior handoff:**
[`2026-08-26-post-merge-cleanup-resume-restructure-plan.md`](2026-08-26-post-merge-cleanup-resume-restructure-plan.md)
— it pointed at the #98 phases 2–3 plan, which a peer session has since executed and merged
(`d0415388`). This handoff picks up the phase-4 work that plan deferred.

## TL;DR

- Issue **#98 phase 4** (the white-label surface itself: client registry, admin onboarding UI,
  per-customer branding) is now **specced and planned**. Nothing implemented yet.
- The planning run's main finding: **`ClientCode` and `Organizations` are two different axes**, and
  the phases 2–3 handoff's phrase "per-client branding" conflates them. Verified on INT —
  `ClientCode` ∈ {`default`, `ms02`} is *which runtime DB*; `Organizations` ∈ {PRVR, LKTR, SSIX,
  DMEO, SYDC} is *the customer*, already carried by `Users.organizationCode`. Privera,
  ElektroMaterial and Compass all ride `default`. **Branding attaches to the Organization; runtime
  config attaches to the Client.** Getting this backwards is the main way the implementation can go
  wrong.
- Consequence that makes the feature worth building: a customer riding the shared `default` runtime
  can be onboarded **with no env edit and no deploy**.
- The doc-field restructure (phases 2–3) merged into `v3.2.3.1` as `d0415388` while this session was
  running — a peer owned that merge. `nx_lib/mapping_config.py` and migrations `0074`–`0078` are now
  on the branch, and the plan builds directly on them.

## What shipped

| File | What |
|---|---|
| `docs/superpowers/specs/2026-08-27-white-label-admin-ui-design.md` | Design spec — the two axes with the live INT evidence, the five-step cost of onboarding a customer today, 9 locked decisions, the data model, the admin surface, out-of-scope list, owner actions. |
| `docs/superpowers/plans/2026-08-27-white-label-admin-ui.md` | Implementation plan — 3 phases, 12 tasks, test-first steps, paste-ready conventional-commit message per task, gotchas. |

Both in commit `28adb01e`. Every file path, symbol and quoted snippet in the plan was
Grep-verified verbatim against `v3.2.3.1` HEAD `d0415388` (20 snippet anchors, all OK).

**Decisions the owner made in-session** (front-loaded, one batch):

| Question | Answer |
|---|---|
| Plan scope | All three parts, phased |
| Branding reach | Per client, **in-app only** — login page, error pages and report emails stay Nexora-branded |
| Secrets | *"not sure"* → planner locked **D3**: secrets stay in `env/{ENV}.env`, `dbo.Clients.SecretRef` holds only the env-key prefix. No crypto surface, nothing sensitive in DB backups; the one manual env step only hits a customer bringing their own DB. Upgrade path (an `EncryptedSecret` column preferred when set) is written into the spec. |
| Extras | Write the design spec first; **do not** file the phase-4 GitHub issue yet |

**Plan shape** (each phase ships alone):

- **PHASE A** — migration `0079` creates + seeds `dbo.Clients`; `nx_lib/clients.py::_build_clients()`
  reads it. Public surface (`CLIENTS`, `octo_creds_for_domain`, `non_default_clients`) unchanged.
  Tasks 1–2.
- **PHASE B** — migration `0080` seeds five admin permissions; `/admin/clients` and
  `/admin/processes` pages (read then write); process creation auto-provisions its
  `workitems.filter.process.<name>` permission; every write calls `invalidate_mapping_config()`.
  Tasks 3–8.
- **PHASE C** — migration `0081` adds nullable `BrandName`/`BrandAccentHex`/`BrandLogoFile` to
  `dbo.Organizations`; new `nx_lib/branding.py` cached registry; a context processor beside
  `_inject_ui_prefs`; the header's accent fallback and logo/wordmark read it. Tasks 9–12.

## Next steps (ordered)

1. `/execute-plan` on `docs/superpowers/plans/2026-08-27-white-label-admin-ui.md` — start at
   **Task 1** (migration `0079`). **Re-check migration numbering first**: `ls
   sql/_migrations/NexoraDB/ | tail -3` must end at `0078`, and `python scripts/db-migrate.py --env
   INT --dry-run` must report `up-to-date` — it does as of this handoff (see Gotchas #1).
2. Work in a fresh worktree: `git worktree add .claude/worktrees/white-label -b feat/white-label
   v3.2.3.1`, then copy the gitignored env files in (`Copy-Item C:\dev\nexora\env\*.env
   <worktree>\env\`) — the pre-commit hook needs `env/INT.env` and the tests need `env/TEST.env`.
3. Owner: push the unpushed commits on `v3.2.3.1` (28 as of this handoff).
4. Optional: file the phase-4 GitHub issue linking the spec + plan (the #98 handoff asked for one;
   the owner chose spec-first instead this session).

## Gotchas & notes

1. **`0076_seed_column_types.sql` checksum drift — FIXED this session, no action needed.** It
   surfaced as *"1 migration(s) edited after being applied … Migrations are immutable"* and blocked
   the `sql-migrate-int` pre-commit hook. Diagnosed as **pure line-ending drift, zero content
   change**: the recorded checksum
   `8ca77fee853a0efe53b444dd2f1e41eede9efcaae992d708613b9e27e1aaa02a` is the sha256 of the file's
   **CRLF** bytes, while git normalized the working copy to **LF** during the
   `feat/docfield-restructure` merge (`d0415388`). Verified by re-hashing the CRLF form and matching
   it exactly against `dbo.SchemaMigrations`, then resolved with the tool's own documented escape
   hatch, `python scripts/db-migrate.py --env INT --rebless`. `--dry-run` now reports `up-to-date`
   for both NexoraDB and GeneraliDB. **PROD is unaffected** — it has not applied `0076` yet, so it
   will hash the LF file on the next deploy and record a matching checksum.
   *If this class of drift reappears:* re-hash before reaching for `--rebless` — it is only safe once
   you have proven the content is byte-identical modulo line endings.
2. **Nine `sql/NexoraDB/Tables/*.sql` files show as modified but `git diff` is empty.** Byte-compared:
   the committed blobs are LF, the working-tree files are CRLF (17 CRLF vs 17 LF on
   `dbo.FieldAliases.sql`, 469 vs 452 bytes). The re-dump written by the pre-commit hook is
   line-ending-only drift, content-identical. **Left uncommitted on purpose** — it is not this
   session's change, and `git diff` normalization hides it, so do not "fix" it by staging.
   `git update-index --refresh` does not clear it.
3. **The two axes.** Re-read the spec's "two axes" section before writing any code. `ClientCode` is
   a runtime source (2 rows, changes ~never); an Organization is a customer (5 rows today, 10–50
   soon). Nothing parses the `privera.` prefix in process names and the plan does not start.
4. **Config fields are interpolated into SQL, not parameterised.** `ProcessSources.TableName` /
   `TableAlias` / `JoinCondition` and `ProcessFieldMappings.ColumnName` reach the query builders as
   text. Plan Task 7 validates the identifier-shaped ones and **deliberately keeps the free-form SQL
   fragment columns out of the admin UI** (`JoinCondition`, `TimeFilter`, `SuggestionTimeFilter`,
   `ExtraCondition` stay migration-only). Do not "finish the job" without a separate decision.
5. **`CLIENTS` is built at import time and stays that way** (plan D6). A client added through
   `/admin/clients` needs an app-pool recycle. This is intentional — `workitem_sources.py` imports
   the dict object itself, so a TTL would not help it anyway.
6. **CSP is PROD-only.** Inline `onclick=` works on INT and is silently dropped on PROD.
   `tests/unit/test_no_inline_event_handlers.py` is the guard; the sanctioned pattern is the
   `page_header` macro's `data-nx-click="{{ act.onclick }}"` plus delegation in the JS partial.
7. **`session["organizationcode"]` is all lowercase** (set in `nx_lib/views/auth.py` at both login
   paths) while the DB column is `Users.organizationCode`. Plan Task 10 depends on the lowercase key.
8. **`var/branding/` needs no deploy-exclude change** — `var` is already in `deploy.yml`'s `/XD`
   list, so the mirror neither copies nor purges it, and it is inside `var\` so no new SYAPP01
   Defender exclusion applies. The plan adds **no** new top-level files or directories.
9. **A peer session was live on this branch** during this session — it completed the
   `feat/docfield-restructure` merge (`d0415388`, two conflicts in `CHANGELOG.md`/`CLAUDE.md`) and
   deleted the branch while this planning run was reading the repo. Run `ListAgents` and check
   `git log -5` before assuming exclusive checkout.

## Untracked / left for owner

- The nine CRLF-drifted `sql/NexoraDB/Tables/*.sql` files (Gotchas #2) — deliberately not staged.
- No GitHub issue was filed for phase 4 (owner's choice this session).
- Nothing else untracked; the scratchpad queries used for the INT recon live outside the repo.

## How to verify

```powershell
git log --oneline -2                       # 28adb01e on top of d0415388
git show --stat 28adb01e                   # 2 files, 617 insertions, docs only
python scripts/db-migrate.py --env INT --dry-run    # up-to-date (0076 drift re-blessed)
C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/unit/test_clients.py tests/unit/test_mapping_config.py -q --no-cov
gh issue view 98 --json labels -q '.labels[].name'  # enhancement + inprogress
```

Nothing was implemented this session, so no suite changed state. The one repo-state change beyond
the three doc commits is the `0076` checksum re-bless on INT (Gotchas #1) — a `dbo.SchemaMigrations`
row update, no schema or data change.

## Resuming in a fresh session

Run `/reset-session docs/superpowers/handoffs/2026-08-27-white-label-admin-ui-plan.md` (passing the
explicit path is the safe form — bare `/reset-session` picks by date and this repo regularly has
several handoffs per day), then read
`docs/superpowers/specs/2026-08-27-white-label-admin-ui-design.md` **before**
`/execute-plan docs/superpowers/plans/2026-08-27-white-label-admin-ui.md`. The spec's "two axes"
section is the context the plan assumes and does not repeat.
