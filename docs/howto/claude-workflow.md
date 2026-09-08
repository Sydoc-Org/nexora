# Working with Claude Code on nexora

How to get efficient, high-quality results from Claude Code (and similar coding agents) on this repo. The governing constraint is the **context window**: model quality degrades as it fills, so most of this is about keeping context lean and the feedback loop tight. Based on Anthropic's [Claude Code best practices](https://code.claude.com/docs/en/best-practices).

## Token discipline (keep context lean)

- **Explore with subagents / GitNexus, not the main thread.** To answer "where/how is X done", dispatch a subagent (*"use a subagent to find …"*) or use the GitNexus tools (`gitnexus_query`, `gitnexus_context`). They read many files in a *separate* context and return a short summary, instead of pulling whole files into your conversation. This is the single biggest lever.
- **Targeted tests while iterating.** Run `pytest <path>::<test> -q` for what you changed. Pushing runs no tests locally; CI's fast tier (unit + integration) gates every PR and merge, and the Playwright e2e suite runs nightly on `main` or on demand. Before running the suite locally, run `python scripts/test_db_reset.py` to avoid stale test-DB state (it drops every user object in `NEXORA_TEST` before re-applying `sql/test/schema.sql` + `seed.sql`, so a table a parallel branch's migration left behind can't wedge it). Don't dump the whole suite's output into context during development.
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
- **Slash commands for the repetitive chores:** `/nx-i18n` (Babel extract→update→compile for de/fr/it) and `/nx-migrate <Db> <desc>` (scaffold the next migration file), `/nx-perm-audit [PROD|INT]` (read-only anomaly audit of the live permission grants: cross-org access, profile/org mismatches, customers with admin codes, override noise, dead codes — `scripts/perm-audit.py`).
- **Close the verification loop.** End every change with a check Claude can read: `ruff`, targeted `pytest`, and for UI — restart the dev server (Jinja caches templates per process) and screenshot via Playwright to `var/screenshots/`. *"If you can't verify it, don't ship it."*
- **Writer/Reviewer with worktrees.** Implement in one worktree (created under `.claude/worktrees/`); review the diff in a *fresh* session or with the `/code-review` skill before merging, so the reviewer isn't biased toward code it just wrote.
- **Git policy.** Feature branches allow stage/commit/push; `main` allows no modifying git ops (PR instead). Never `--no-verify`; if the SQL hook can't reach INT (e.g. a fresh worktree without `env/INT.env`), use `SQL_SYNC_SKIP=1 git commit`.

## Session handoff loop (fresh context per batch)

The cheapest context is a fresh one. Instead of letting a long session degrade into auto-compact,
close each batch of work with a handoff document and restart clean — state crosses the session
boundary as **docs in the repo**, not conversation tokens:

1. **The agent hands off, unprompted.** When a batch is done (committed, tests green, nothing
   queued) or the conversation is getting heavy, the agent runs `/handoff-session-state`: writes a
   zero-context handoff to `docs/superpowers/handoffs/`, commits it (commit-only), writes the
   handoff's path into the gitignored flag file `var/handoff-pending`, and ends with a "type
   `/clear`" prompt.
2. **You clear and relaunch.** `/clear` (or exit and start `claude` again). The usual session-start
   hooks run (statusline, auto-pick brief, …).
3. **The new session auto-resumes.** A SessionStart hook
   (`.claude/helpers/check-handoff-pending.ps1`, wired in `.claude/settings.json`, matcher
   `startup|clear`) sees the flag and injects a two-line pointer; the fresh session invokes
   `/reset-session` — loads the handoff, deletes the flag, orients, front-loads its questions via
   AskUserQuestion, then runs the next batch to completion.

The next session starts at the fixed session-start floor (see the budget table above) plus one
handoff file, instead of dragging a long history behind it. If the first message of the new session
starts unrelated work, the agent leaves the flag in place — the pointer simply reappears next
session (or `/reset-session` can be run manually later).

## Plays (nexora-specific)

Concrete recurring workflows, ranked by payoff. Scale figures are from the 2.5.63 tree.

1. **Read-less navigation of the fat view files.** `reporting.py` (~2.2k lines), `workitems.py`, `dashboard.py` are each 1.5k–2.2k lines — reading one whole costs ~6–12k tokens (`generali.py` and `admin.py` were split into `nx_lib/views/generali/` and `nx_lib/views/admin/` packages of 8 submodules each, phase 0+1 beautification). Locate with `gitnexus_context` / `gitnexus_query` (or a subagent), then `Read` only the relevant span with `offset`/`limit`. **Never read these whole.**
2. **UI change → screenshot-verify loop.** Edit template/partial → **restart the dev server** (Jinja caches templates per process) → `nx -u -b --loginas:<user>` → drive Playwright → screenshot to `var/screenshots/` → compare to intent → iterate. Use `/nx-ui-verify`. For the nexora-ui rollout to Reporting, fan out one page at a time with before/after shots.
3. **i18n delta sweep.** ~1,077 strings, kept at 0 fuzzy. After any text change, `/nx-i18n`, fill only the new msgids across de/fr/it, gate on `test_translations.py`. Every feature lands with its translations done.
4. **Schema change, INT-first.** `/nx-migrate <Db> <desc>` → idempotent SQL → commit auto-applies to INT → `db-migrate.py --env INT --mark-applied` if prototyped in SSMS → changelog → `SQL_SYNC_SKIP=1` when a worktree can't reach INT.
5. **Coverage ratchet.** Per-module targets live in `tests/unit/test_coverage_thresholds.py` (`MIN_COVERAGE`); `fail_under` is 0 by design. Target a module, write tests, `pytest --cov`, raise that module's entry (upward only). Use `/nx-cover`.
6. **Writer/Reviewer pre-merge.** Implement in a worktree → `/code-review` on the diff in a fresh context → fix → merge.

**Refactor candidate:** `reporting.py` (~2.2k lines) — lift the ~810-line AI cluster first; `nx_lib/reporting/runner.py` back-imports symbols from it, so check callers with `gitnexus_impact` before moving anything.

## External MCP integrations (optional)

These connect Claude to the systems nexora actually talks to. Both are **user-scope** (`claude mcp add -s user`) — per-developer, credentials kept local and never committed. Each adds only a handful of tools (unlike the removed claude-flow server).

### Read-only SQL Server (Statistics / Octopus runtime DBs)

The app-owned schemas (`NexoraDB`, `GeneraliDB`) are already in the repo as per-object DDL under `sql/`. A read-only MSSQL MCP **complements** that by giving Claude live read access to the **untracked runtime DBs** — `StatisticsDB` (`sydoc_stat`, where reporting queries run) and `OctoDB` — using the `db_datareader` RO logins already provisioned for the reporting sandbox.

Server: [trainerroad/mcp-sqlserver](https://github.com/trainerroad/mcp-sqlserver) (read-only, `ApplicationIntent=ReadOnly`, write-blocking, schema caching). Build per its README to `~/.claude/mcp-sqlserver/dist/index.js`, then register against the Statistics DB with the reporting RO login (substitute the values from `env/INT.env`):

```
claude mcp add mssql-stats -s user ^
  -e SQLSERVER_HOST=<DB_SERVER_PRD> ^
  -e SQLSERVER_DATABASE=sydoc_stat ^
  -e SQLSERVER_AUTH_MODE=sql ^
  -e SQLSERVER_USER=<DB_REPORTING_RO_USER> ^
  -e SQLSERVER_PASSWORD=<DB_REPORTING_RO_PWD> ^
  -e SQLSERVER_ENCRYPT=true ^
  -- node "%USERPROFILE%/.claude/mcp-sqlserver/dist/index.js"
```

Add a second `mssql-octo` entry pointing at the Octopus DB with `DB_REPORTING_OCTO_RO_USER` / `DB_REPORTING_OCTO_RO_PWD`. **Rules:** RO login only — never the app write user; keep it read-only; the credentials come from `env/INT.env` and must not be pasted anywhere committed.

### Confluence + Jira (official Atlassian MCP)

nexora's docs are authored in git and mirrored read-only to Confluence (see `docs/howto/confluence-sync.md`) — use the MCP for *reading* Confluence/Jira content that lives outside the mirrored docs. The official remote MCP (GA Feb 2026, Claude launch partner) reads/writes Confluence + Jira over OAuth and respects your account's permissions:

```
claude mcp add atlassian -s user -- npx -y mcp-remote@latest https://mcp.atlassian.com/v1/sse
```

First use opens a browser OAuth flow. As a remote OAuth server it may be unavailable in headless / cron / remote-agent runs — it's for interactive sessions.

### GitHub

Use the `gh` CLI (already installed + authenticated) rather than a GitHub MCP — it's more context-efficient for PRs, issues, and Actions.

## See also

- `docs/howto/confluence-sync.md` — git → Confluence docs mirror (publish set, token rotation)
- `docs/howto/nx.md` — the `nx` dev-server CLI (`-u`, `-b --loginas:`, `--doctor`)
- `docs/howto/babel.md` — translations
- `docs/howto/db-migrations.md` — schema migrations (2.5.63+)
