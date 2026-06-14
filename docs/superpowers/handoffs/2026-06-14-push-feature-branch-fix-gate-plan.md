# Handoff — Plan written: push feature/2.5.63 through the pre-push gate

**Date:** 2026-06-14 (evening) · **Branch:** `feature/2.5.63` · **175 commits unpushed** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-14-autopilot-live-and-reporting-reskin.md`
**The plan this handoff hands off:** `docs/superpowers/plans/2026-06-14-push-feature-branch-fix-gate.md`

## TL;DR

- Wrote (didn't execute) a **fully-grounded implementation plan** to get `feature/2.5.63` through the
  pre-push gate and pushed. This is the executable form of the "owner: translate the 54 strings, then
  push" item the prior handoff left open.
- The gate is **RED right now**: `test_translations` fails — **48 untranslated + 6 fuzzy msgids in
  each of de/fr/it** (54 gaps per locale), plus stale `.mo`. The plan fills all of them (with the
  actual translations in tables), fixes the `requirements-confluence.txt` deploy `/XF` gap, resets
  `NEXORA_TEST`, then pushes.
- Built by a 7-agent planning workflow (explore → dual drafts → adversarial red-team → merge).
  **Fable 5 was unavailable platform-wide, so agents ran on Sonnet.** Every file/symbol/command anchor
  was re-verified against the live repo before commit.

## This session's commits (oldest→newest, after prior handoff `e2360d7`)

```
17d334a docs(plans): add push-feature-branch-fix-gate plan
```
(That's the only commit this session — pure plan authoring. The reporting/autopilot commits above it
in `git log` belong to the prior handoff.)

## What shipped

| File | Commit | What |
|---|---|---|
| `docs/superpowers/plans/2026-06-14-push-feature-branch-fix-gate.md` (new) | `17d334a` | 5-phase, 9-task runbook to fix the i18n gate failures + deploy-exclusion gap and push |

## Next steps (ordered) — for `/execute-plan` or a human

Resume at **`docs/superpowers/plans/2026-06-14-push-feature-branch-fix-gate.md`**, top. The plan's
phases:

1. **Phase 1 / Task 1** — run `python -m pytest tests/unit/test_translations.py -v`, confirm 6 RED.
2. **Phase 2 / Tasks 2–4** — `pybabel update`; fill the 48 untranslated msgstr + de-fuzz the 6 fuzzy
   (the plan has the exact de/fr/it translations in tables); `pybabel compile`; re-run green (7/7).
3. **Phase 3 / Task 5** — add `requirements-confluence.txt` to the `/XF` line in `deploy.yml`.
4. **Phase 4 / Tasks 6–7** — verify `env/TEST.env`; stage the 6 `.po`/`.mo` + `deploy.yml`; commit
   with `SQL_SYNC_SKIP=1` (CRLF drift).
5. **Phase 5 / Tasks 8–9** — `python scripts/test_db_reset.py`, then `git push origin feature/2.5.63`.

## Gotchas & notes (READ)

- **Gate is RED now** — do not push until Phase 2 is green. The failing tests are
  `test_all_strings_translated[de|fr|it]` and `test_mo_files_up_to_date[de|fr|it]`.
- **SQL hooks are `stages: [pre-commit]` only** (verified `.pre-commit-config.yaml` lines 63/70) — they
  do NOT run at push. So `SQL_SYNC_SKIP=1` is needed for the **commit**, not the push. The push gate is
  just `branch-name-guard` + `pytest-pre-push` (full suite incl. e2e, `--reruns 2 --only-rerun
  flaky_e2e`).
- **Fuzzy entries need TWO edits**: replace the wrong `msgstr` AND delete the `#, fuzzy` line.
  `test_all_strings_translated` checks `"fuzzy" in msg.flags`.
- **Durable `*.sql eol=lf` CRLF fix is deliberately NOT in this plan** — the red-team confirmed 74 of
  93 tracked SQL files check out CRLF; adding the rule without a controlled `git add --renormalize sql/`
  pass would silently stage a 74-file diff. Left to Owner actions in the plan.
- **`requirements-confluence.txt`** (root) is the only deploy `/XF` gap; `sql/requirements.txt` is
  already covered by `/XD sql`.
- **INTSQL01 (INT DB) has recurring transient outages** — can fail e2e at push even though SQL hooks
  don't run there (the test app queries INT). Check `Test-NetConnection INTSQL01 -Port 1433` first.
- **Remote/commit-only:** the plan's terminal action IS a push, but per remote policy the **owner**
  runs the actual `git push` after reviewing — `/execute-plan` should stop at the commit and surface
  the push command unless explicitly cleared to push (the autopilot lane has auto-push gated on the
  gate). No PR — owner opens it.

## Untracked / left for owner

- Nothing uncommitted this session. The plan is committed; no code changed.
- The translations themselves are not yet applied — that's Phase 2 of the plan.

## How to verify

```powershell
# the plan exists and is committed:
git log --oneline -1                      # -> 17d334a docs(plans): add push-feature-branch-fix-gate plan
# confirm the gate is still red (the work the plan addresses):
python -m pytest tests/unit/test_translations.py -v   # expect 1 passed, 6 failed
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). **Several handoffs share today's
date** — if the flag is gone, run `/reset-session docs/superpowers/handoffs/2026-06-14-push-feature-branch-fix-gate-plan.md`
to target this file. Then open the plan at
`docs/superpowers/plans/2026-06-14-push-feature-branch-fix-gate.md` and run `/execute-plan` (or work it
task-by-task). No worktree — execution runs on `feature/2.5.63` directly (it must, to push that
branch's commits).
