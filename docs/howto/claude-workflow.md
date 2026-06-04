# Working with Claude Code on nexora

How to get efficient, high-quality results from Claude Code (and similar coding agents) on this repo. The governing constraint is the **context window**: model quality degrades as it fills, so most of this is about keeping context lean and the feedback loop tight. Based on Anthropic's [Claude Code best practices](https://code.claude.com/docs/en/best-practices).

## Token discipline (keep context lean)

- **Explore with subagents / GitNexus, not the main thread.** To answer "where/how is X done", dispatch a subagent (*"use a subagent to find …"*) or use the GitNexus tools (`gitnexus_query`, `gitnexus_context`). They read many files in a *separate* context and return a short summary, instead of pulling whole files into your conversation. This is the single biggest lever.
- **Targeted tests while iterating.** Run `pytest <path>::<test> -q` for what you changed. The full suite + Playwright e2e is the **pre-push** gate (`scripts/git-hooks/pre-push`); run `python scripts/test_db_reset.py` first to avoid stale test-DB state. Don't dump the whole suite's output into context during development.
- **`/clear` between unrelated tasks; `/compact <focus>` within one.** A clean session with a sharp prompt beats a long, polluted one. Use `/btw` for side questions that shouldn't enter history.
- **Lean CLAUDE.md.** It loads every session *and* propagates into every subagent, so every line is paid many times over. Keep only what changes behavior; move sometimes-relevant detail into `docs/` or a skill.
- **One browser MCP at a time.** Playwright covers routine UI work (`nx -u -b --loginas:`); enable chrome-devtools only when you need perf / a11y / Lighthouse.

### Session-start budget (measured 2026-06)

Every session loads a fixed overhead before you type a word. Approximate token costs:

| Injection | ~tokens | Notes |
|---|---|---|
| project `CLAUDE.md` | ~4,000 | move sometimes-relevant detail into docs/skills |
| `MEMORY.md` index | ~2,200 | prune stale memories periodically |
| `using-superpowers` skill | ~1,350 | session-start hook |
| `plugin-finder` skill | ~1,350 | session-start hook |
| `auto-pick` brief | ~700 | the full 47 KB catalog only loads on demand |
| claude-flow MCP tool names | ~4,500 | **removed** in the `.claude` cleanup |

Disabling the auto-pick / plugin-finder / superpowers session-start injection reclaims a further ~3–4k tokens/session if you don't rely on them.

## Advanced workflow

- **Explore → Plan → Code → Commit.** For any change spanning more than one file, enter plan mode first (`Esc`), let Claude read and produce a plan (open it in your editor with `Ctrl+G`), then implement and verify against the plan. Skip planning only for one-sentence diffs.
- **Use the `nexora-feature` skill** when adding a page/route/permission — it enumerates the file constellation (route, page template + paired JS partial, permission wiring, migration, i18n, changelog, docs, deploy excludes) so nothing is missed.
- **Slash commands for the repetitive chores:** `/nx-i18n` (Babel extract→update→compile for de/fr/it) and `/nx-migrate <Db> <desc>` (scaffold the next migration file).
- **Close the verification loop.** End every change with a check Claude can read: `ruff`, targeted `pytest`, and for UI — restart the dev server (Jinja caches templates per process) and screenshot via Playwright to `var/screenshots/`. *"If you can't verify it, don't ship it."*
- **Writer/Reviewer with worktrees.** Implement in one worktree (created under `.claude/worktrees/`); review the diff in a *fresh* session or with the `/code-review` skill before merging, so the reviewer isn't biased toward code it just wrote.
- **Git policy.** Feature branches allow stage/commit/push; `main` allows no modifying git ops (PR instead). Never `--no-verify`; if the SQL hook can't reach INT (e.g. a fresh worktree without `env/INT.env`), use `SQL_SYNC_SKIP=1 git commit`.

## Plays (nexora-specific)

Concrete recurring workflows, ranked by payoff. Scale figures are from the 2.5.63 tree.

1. **Read-less navigation of the fat view files.** `nx_lib/views/generali.py` (~3.4k lines), `reporting.py` (~2.2k), `admin.py`, `workitems.py`, `dashboard.py` are each 1.5k–3.4k lines — reading one whole costs ~6–12k tokens. Locate with `gitnexus_context` / `gitnexus_query` (or a subagent), then `Read` only the relevant span with `offset`/`limit`. **Never read these whole.**
2. **UI change → screenshot-verify loop.** Edit template/partial → **restart the dev server** (Jinja caches templates per process) → `nx -u -b --loginas:<user>` → drive Playwright → screenshot to `var/screenshots/` → compare to intent → iterate. Use `/nx-ui-verify`. For the nexora-ui rollout to Reporting, fan out one page at a time with before/after shots.
3. **i18n delta sweep.** ~1,077 strings, kept at 0 fuzzy. After any text change, `/nx-i18n`, fill only the new msgids across de/fr/it, gate on `test_translations.py`. Every feature lands with its translations done.
4. **Schema change, INT-first.** `/nx-migrate <Db> <desc>` → idempotent SQL → commit auto-applies to INT → `db-migrate.py --env INT --mark-applied` if prototyped in SSMS → changelog → `SQL_SYNC_SKIP=1` when a worktree can't reach INT.
5. **Coverage ratchet.** Per-module targets live in `tests/unit/test_coverage_thresholds.py` (`MIN_COVERAGE`); `fail_under` is 0 by design. Target a module, write tests, `pytest --cov`, raise that module's entry (upward only). Use `/nx-cover`.
6. **Writer/Reviewer pre-merge.** Implement in a worktree → `/code-review` on the diff in a fresh context → fix → merge.

**Refactor candidate:** `nx_lib/views/generali.py` (~3.4k lines) — `gitnexus_impact` → plan mode → split into a `nx_lib/views/generali/` package → gate on the generali e2e tests.

## See also

- `docs/howto/nx.md` — the `nx` dev-server CLI (`-u`, `-b --loginas:`, `--doctor`)
- `docs/howto/babel.md` — translations
- `docs/howto/db-migrations.md` — schema migrations (2.5.63+)
