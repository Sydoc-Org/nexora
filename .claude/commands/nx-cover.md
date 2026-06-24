---
description: Raise test coverage for a nexora module and ratchet its per-module threshold
argument-hint: "<module path, e.g. nx_lib/reporting/sandbox.py>"
---

Raise coverage for a target module and ratchet its threshold upward. Per-module targets live in `tests/unit/test_coverage_thresholds.py` (the `MIN_COVERAGE` dict) — `fail_under` in `pyproject.toml` is intentionally `0`, so `MIN_COVERAGE` is the real source of truth and the gate.

Target module: $ARGUMENTS

Steps:

1. **Read the module** — prefer a subagent or `gitnexus_context` so a large module doesn't flood context. Identify the uncovered branches/functions.
2. **Write targeted tests** under `tests/`, following the existing layout (unit vs route vs e2e) and fixtures in `tests/conftest.py`. Avoid mocks where a real fixture works.
3. **Measure:** `pytest --cov=nx_lib --cov-report=term-missing tests/` (scope to the relevant test files while iterating). Read the module's new coverage %.
4. **Ratchet:** raise that module's entry in `MIN_COVERAGE` to the new floor. **Upward only** — never lower a threshold without team sign-off.
5. **Commit** with a conventional `test(...)` message; add a `CHANGELOG.md` entry if notable. The full suite + Playwright e2e run at the pre-push gate — run `python scripts/test_db_reset.py` first if you trigger e2e locally (avoids stale test-DB state).
