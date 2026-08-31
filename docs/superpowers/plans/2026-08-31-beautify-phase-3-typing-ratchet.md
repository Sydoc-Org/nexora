# Beautification Phase 3 — typing and lint ratchet — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Violation counts are from the 2026-08-31 lint/typing audit against `v3.2.4.1` — **re-measure every count before fixing**; Phases 1-2 rewrite the worst offenders and the numbers will have dropped.

**Prerequisite:** Phase 2a merged (the view packages exist — 46% of the typing debt lived in `views/`). Shared context: the Phase 0+1 plan. Phase 0's Task 8 already landed `RET/C4/PIE`, `warn_return_any`, and mypy-in-CI. **Migrations needed: NO.**

**Goal:** Move mypy from "syntax check with two knobs below default" to a real type gate, module by module, and finish the ruff quality families — each step a ratchet that CI then holds.

---

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | `check_untyped_defs = true` globally is the centerpiece (69 errors / 26 files at audit time) — it checks the bodies nexora actually has. | Biggest real-bug catcher per error fixed; mypy itself suggests it in the current run's notes. |
| D2 | `disallow_untyped_defs` arrives per-module via `[[tool.mypy.overrides]]`, starting with already-clean small modules; never a big-bang flip (was 748 errors repo-wide). | The overrides list IS the ratchet — a touched module gets added, never removed. |
| D3 | `PLR2004` magic values and the `PLR09xx` complexity metrics are NOT adopted. | 94 + 129 findings of mostly noise; complexity is being fixed structurally by the splits, not by thresholds. |
| D4 | The single `PLR0124` comparison-with-itself hit is investigated as a **possible real bug** before any mechanical fix. | It is the one genuine bug-smell in the PL family. |

### Task 1: Re-measure

- [ ] Run the audit commands fresh: `ruff check nx_lib --select PERF,PL --statistics`; `mypy nx_lib --check-untyped-defs` (count); `mypy nx_lib --strict-optional` (count — the config comment claiming ~12 sites is old).
- [ ] Record the new baseline in the commit body of Task 2. No commit for this task.

### Task 2: check_untyped_defs

- [ ] `pyproject.toml [tool.mypy]`: `check_untyped_defs = true`. Fix the fallout module-by-module (audit-time: 69 errors / 26 files), batched into reviewable commits (~5 modules each).
- [ ] Every fix that changes behavior (not just annotations) gets its own test first.
- [ ] Commits: `types: enable check_untyped_defs and fix <modules>`.

### Task 3: strict_optional

- [ ] Flip `strict_optional = true` (currently explicitly `false`); fix the sites (re-measured in Task 1). Delete the stale config comment.
- [ ] Commit: `types: enable strict_optional`.

### Task 4: ruff PL cherry-pick + PERF

- [ ] Add `PLW1510` (subprocess-run-without-check), `PLR1714`, `PLR1730`, `PLR0124` to the select list; fix (5 of 6 were unsafe-autofixable; PLR0124 per D4 — investigate, then fix or document).
- [ ] Add `PERF` (13× PERF401 + 2× PERF403 at audit time — manual loop→comprehension rewrites, concentrated in `hooks.py`, `views/auth.py`, admin, `reporting/query.py`).
- [ ] Commit: `lint: adopt PL cherry-picks and PERF rules`.

### Task 5: disallow_untyped_defs ratchet

- [ ] Add `[[tool.mypy.overrides]]` with `disallow_untyped_defs = true` for every module that is ALREADY clean under it (find them: run with the flag, list error-free modules).
- [ ] Annotate 3-5 small high-traffic modules to grow the list (`db.py`, `clients.py`, `mapping_config.py`, `branding.py` are natural starts — small, contract-heavy).
- [ ] Document the ratchet rule in `CONTRIBUTING.md`: "a module added to the overrides list never leaves it; new modules ship typed."
- [ ] Commit: `types: begin the per-module disallow_untyped_defs ratchet`.

### Task 6: CI + docs wrap-up

- [ ] Confirm `deploy.yml`'s mypy step (from Phase 0) still covers `nx_lib nx_main.py`; extend to `scripts/` if Task 2-5 typed them. `CHANGELOG.md` entry. Full gate green.
- [ ] Commit: `ci(types): finish the phase 3 ratchet wiring`.

## Gotchas & notes

- `warn_unused_ignores = true` is already on — expect stale `# type: ignore`s to ERROR as flags tighten; delete them in the same commit as the flag flip.
- `ignore_missing_imports = true` stays — third-party stub chasing (pyodbc, flask-*) is explicitly out of scope.
- Tests (`tests/`, camelCase fixtures) and `scripts/` stay un-typechecked unless trivially clean — the value is in `nx_lib`.
- If a needed annotation reveals an actual type confusion (it will, that's the point), fix the bug with a test, not the annotation around it.
