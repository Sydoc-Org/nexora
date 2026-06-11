# Handoff — Git → Confluence docs sync: spec + 10-task plan (PLAN ONLY)

- **Date:** 2026-06-11
- **Branch:** `feat/confluence-docs-sync` in worktree `.claude/worktrees/confluence-docs-sync`,
  branched off `feature/2.5.63` (@ `ee07d40`). **1 commit ahead of `feature/2.5.63`, no
  upstream / never pushed** — commit-only (remote); the owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-11-ai-fixes-plan-staging-migrations.md`
  (16-task AI-fixes plan + STAGING unblocked — **separate workstream on `feature/2.5.63`,
  still pending execution too**).
- **This session's commits (oldest → newest):**
  - `8715434` docs(docs-sync): spec and plan for git-to-Confluence mirror

---

## TL;DR

1. **Planned (NOT implemented)** a one-way git → Confluence mirror: `docs/howto/*`,
   `docs/design/*`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md` auto-publish to the
   `nexora` space on push to `main`; old hand-written pages get archived; space goes
   read-only for humans. Owner picked all four scope/strategy options via AskUserQuestion.
2. **Spec:** `docs/superpowers/specs/2026-06-11-confluence-docs-sync-design.md`.
   **Plan:** `docs/superpowers/plans/2026-06-11-confluence-docs-sync.md` (10 TDD tasks,
   complete code inline, self-contained for a zero-context session).
3. Tooling researched via a 5-agent workflow (repo scan, tooling comparison, Confluence
   Cloud API deep-dive, docs-as-code pitfalls, adversarial cross-check): engine is
   **`markdown-to-confluence==0.6.1`** (hunyadi/md2conf) + a ~100-line custom reconcile
   (label `git-managed`, archive orphans via v1 `POST /content/archive`).
4. Owner explicitly chose **stop at planning** — implementation happens in a later session.

---

## Key design decisions (full rationale in the spec)

| Decision | Choice |
|---|---|
| Publish set | `docs/howto/*` + `docs/design/*` + README/CONTRIBUTING/CHANGELOG (NOT superpowers/, releases/, CLAUDE.md) |
| Old Confluence content | Archived on bootstrap (recoverable via UI), no reverse import |
| Ownership model | Full space mirror; "Confluence pages are disposable render artifacts" — title-matched, no page-ID maps; renames = new page + archive old |
| Trigger | New workflow `.github/workflows/confluence-docs.yml`, push to `main` + path filter + `workflow_dispatch`, `concurrency: confluence-sync` |
| Engine | md2conf as library/CLI; mark (no Windows binaries), all marketplace Actions (Docker = Linux-only), Telefonica CLI (Node 18), Sphinx builder (table gaps) all eliminated |
| Auth | Dedicated bot + **unscoped** API token, basic auth at site URL (scoped tokens can't safely reach the 4 v1-only endpoints: archive, label add, attachment, space perms) |
| Secrets | Runner-side file `C:\sydoc\runner-secrets\CONFLUENCE.env` (repo uses zero GitHub secrets — kept that way) + local `env/CONFLUENCE.env` |

## What shipped

| File | Commit | What |
|------|--------|------|
| `docs/superpowers/specs/2026-06-11-confluence-docs-sync-design.md` | `8715434` | Design: scope, tooling verdict, components (driver/creds/workflow/tests/runbook), tree, read-only enforcement, risks, rollout |
| `docs/superpowers/plans/2026-06-11-confluence-docs-sync.md` | `8715434` | 10 tasks: deps+CLI spike → CHANGELOG dup fix → staging/titles → conversion golden tests → REST client → reconcile → main() → CI workflow → docs → live bootstrap |

No code, no tests, no migrations this session. Pure planning.

## Next steps (ordered)

1. **Owner: review spec + plan** (both in commit `8715434`).
2. **Owner prerequisites before plan Task 10 (live):** create Confluence bot account +
   unscoped API token (≤365-day expiry — rotation runbook is plan Task 9); verify the
   Atlassian plan tier is Standard+ (archiving); provision
   `C:\sydoc\runner-secrets\CONFLUENCE.env` on SYAPP01 + local `env/CONFLUENCE.env`.
3. **Execute the plan** in this worktree, Tasks 1–9 need no credentials; Task 10 is the
   owner-gated live bootstrap. Subagent-driven execution recommended
   (`superpowers:subagent-driven-development`). Start at Task 1 (dependency + md2conf CLI
   spike — its findings may adjust flag-name constants used in Tasks 4/7).
4. **Owner: push + PR** when implemented (or push the plan-only branch earlier if wanted).

## Gotchas & notes

- **Pre-existing bug found by the docs scan:** `CHANGELOG.md` has a duplicate `### Fixed`
  heading under `[Unreleased]` (~lines 318 + 438) — plan Task 2 fixes it; it would break
  Confluence anchors/TOC otherwise.
- **Open verification carried in the plan (Task 10 Step 1):** whether md2conf renders the
  staged root `README.md` into the homepage body; spec §4.1 documents the fallback (direct
  v2 `PUT /pages/323944774`).
- **Archive, never trash:** v1 archive endpoint is the only archive path (no v2
  equivalent); trashing would also hit open md2conf bug #275 (crash on `trashed` status).
- md2conf flag names (`--root-page`, `--keep-hierarchy`, `--heading-anchors`,
  `--generated-by`, `--local`) are research-sourced — Task 1's spike pins them against
  `--help`; adjust constants if they differ.
- Commits in this clone still need the `SQL_SYNC_SKIP=1` prefix (INT CRLF drift); gitlint
  enforces ≤72-char imperative subject + non-empty body.
- The worktree branches off `feature/2.5.63`, not `main` — the docs corpus the plan's
  tests pin (e.g. `docs/howto/reporting.md`) only exists there.
- Session memory `project_confluence_docs_sync.md` (user-level auto-memory) mirrors the
  state for cross-session recall.

## Untracked / left for owner

- Nothing uncommitted in the worktree (`git status` clean).
- `var/handoff-pending` (gitignored) points at this file for `/reset-session`.
- The **main checkout** (`C:\dev\nexora`) had uncommitted `CHANGELOG.md` +
  `docs/howto/reporting.md` modifications at session start — untouched by this session,
  they belong to the AI-fixes workstream.

## How to verify

```powershell
cd C:\dev\nexora\.claude\worktrees\confluence-docs-sync
git log --oneline feature/2.5.63..HEAD          # exactly: 8715434
git show --stat 8715434                          # 2 files, ~1584 insertions
```

No test suite changes this session — nothing new to run.

## Resuming in a fresh session

- `/reset-session` loads this handoff (note: a second 2026-06-11 handoff exists for the
  AI-fixes workstream; it carries a forward-pointer banner to this file. To target one
  explicitly: `/reset-session docs/superpowers/handoffs/2026-06-11-confluence-docs-sync-plan.md`).
- Read the spec, then execute the plan task-by-task from Task 1. The plan is
  self-contained — no conversation context needed.
