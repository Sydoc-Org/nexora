# Watchdog Run-Modes Usage Comment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single `.EXAMPLE` block inside the existing `<# #>` comment-based-help header of `tools/autopilot/watchdog.ps1` showing the two runnable invocation forms: single-shot for Task Scheduler (default `-IntervalSeconds 0`) and foreground loop (`-IntervalSeconds 120`). Zero logic change; pure comment addition.

**Architecture:** `watchdog.ps1` already has a `<# #>` comment-based-help block (lines 2–22) with `.SYNOPSIS`, `.DESCRIPTION` (including a prose "Modes:" sub-block), and `.NOTES`. A single `.EXAMPLE` block with two command lines is inserted between `.DESCRIPTION` and `.NOTES`, matching the only house-style precedent in the repo (`bootstrap.ps1` lines 17–21). No second `<# #>` block is introduced — PowerShell only parses the first one.

**Tech Stack:** PowerShell 7 comment-based help (`.EXAMPLE` keyword inside `<# #>`). No Python, Flask, Jinja, SQL, Babel string, migration, or test harness involved.

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.63`. Remote-session policy: stop at `git commit`; do not push, do not open a PR.
- **SQL hook bypass:** The INT `SchemaMigrations` table has stale CRLF checksums for migrations 0001–0003. The `sql-migrate-int` pre-commit hook therefore fails on every Windows commit on this branch. Since this is a docs-only change with no `.sql` files touched, commit using `SQL_SYNC_SKIP=1` — never `--no-verify`.
- **Anchor-on-snippets rule:** All insertion points are quoted verbatim from the live file, not identified by line number (line numbers shift with edits).
- **No migration / i18n / test harness:** `babel.cfg` extracts only `nx_lib/**.py`, root `*.py`, and `templates/**.html` — `.ps1` files are out of scope. There is no pytest or Playwright test for `watchdog.ps1`. The verifiable acceptance check is a PowerShell parse-and-render one-liner (Task 1, steps 3–4).
- **deploy.yml already covers this:** `tools` appears in the robocopy `/XD` exclude list in `.github/workflows/deploy.yml`. No `deploy.yml` change is needed; `watchdog.ps1` never ships to prod.
- **House style** (verified from `bootstrap.ps1` lines 17–21 — the only `.EXAMPLE` in the repo):
  - `.EXAMPLE` keyword: column 0, no leading spaces — identical to `.SYNOPSIS`, `.DESCRIPTION`, and `.NOTES`. (The 2-space indent in earlier drafts was wrong; all section keywords in `bootstrap.ps1` sit at column 0.)
  - Command lines beneath the keyword: 2-space indent, relative `.\scriptname.ps1` path, named params in `-Param value` form.
  - Multiple invocations in one `.EXAMPLE` block: plain newline between them, no label, no blank line between keyword and first command line.
  - **One blank line** between the last example command and the following `.NOTES` keyword (`bootstrap.ps1` line 20 is blank before `.NOTES` on line 21).

---

## Decisions locked in

| Decision | Rationale |
|---|---|
| One `.EXAMPLE` block, two command lines | Matches `bootstrap.ps1` precedent exactly (two invocations, one block); `Get-Help -Examples` renders them together, idiomatic for closely related invocations |
| Placed between `.DESCRIPTION` and `.NOTES` | PowerShell comment-based-help convention: what it is → how to run it → caveats |
| Blank line before `.NOTES` | Required by house style: `bootstrap.ps1` line 20 is blank before `.NOTES` on line 21 — the new_string includes it |
| `.EXAMPLE` keyword at column 0, not indented | All section keywords in `bootstrap.ps1` (`bootstrap.ps1` lines 2, 5, 17, 21) are at column 0; only content lines carry the 2-space indent |
| Relative `.\watchdog.ps1` path, not full `pwsh -File C:\…` | Matches house style from `bootstrap.ps1`; the full-path Task Scheduler invocation is already in the autopilot spec doc |
| No CHANGELOG.md entry | `autopilot`/`watchdog`/`n8n` have zero prior CHANGELOG entries; a comment-only dev-tooling clarification does not meet the bar |
| No README.md update | `tools/autopilot/README.md` line 42 already reads "(single-shot for Task Scheduler, or a foreground loop)" — both modes are covered; the `.EXAMPLE` block is additive and consistent |

---

# PHASE 1 — Insert .EXAMPLE block

### Task 1 — Edit watchdog.ps1 and verify

- [ ] **Confirm the current state.** Open `C:\dev\nexora\tools\autopilot\watchdog.ps1`. Verify the `<# #>` block contains `.SYNOPSIS`, `.DESCRIPTION`, and `.NOTES` but no `.EXAMPLE` keyword anywhere in the file.

- [ ] **Insert the `.EXAMPLE` block** using the Edit tool with the following exact old/new strings.

  **old_string** (the `.NOTES` block and closing `#>` — quoted verbatim from the live file):

  ```
  .NOTES
    A restart does NOT resume a crashed execution; lock.ps1's self-heal + start-n8n.ps1's
    boot-time lock clear handle the orphaned-run case. The watchdog only guarantees n8n is back
    up to poll again.
  #>
  ```

  **new_string** (`.EXAMPLE` block inserted immediately before `.NOTES`, with one blank line between the last example command and `.NOTES` — matching `bootstrap.ps1` style exactly):

  ```
  .EXAMPLE
    .\watchdog.ps1
    .\watchdog.ps1 -IntervalSeconds 120

  .NOTES
    A restart does NOT resume a crashed execution; lock.ps1's self-heal + start-n8n.ps1's
    boot-time lock clear handle the orphaned-run case. The watchdog only guarantees n8n is back
    up to poll again.
  #>
  ```

  The first command (`.\watchdog.ps1` with no flag) uses the default `-IntervalSeconds 0` — single check and exit, the Task Scheduler mode. The second (`-IntervalSeconds 120`) runs the foreground loop, checking every 120 seconds until Ctrl-C.

  After the edit the full comment-based-help block should read:

  ```powershell
  #requires -Version 7
  <#
  .SYNOPSIS
    Keep n8n alive for unattended (away-mode) autopilot: if the editor port is down, relaunch it
    via start-n8n.ps1. Run once (for Task Scheduler) or as a foreground loop.
  .DESCRIPTION
    n8n can die (OOM, a crashed long execution, a host hiccup). While it is down the 2-minute
    poll never fires and the queue stalls silently. This watchdog detects that and restarts n8n
    with the REQUIRED autopilot env (start-n8n.ps1 clears any leaked lock on boot).

    Modes:
      -IntervalSeconds 0   (default) single check + exit - wire to Task Scheduler every N minutes.
      -IntervalSeconds 120          loop forever, checking every 120s (a foreground watcher).

    Notifications are best-effort and OPTIONAL: if AUTOPILOT_TG_TOKEN + AUTOPILOT_TG_CHAT are set,
    a restart pings Telegram; otherwise it only logs (the n8n Telegram credential lives inside n8n
    and is not reachable from here).
  .EXAMPLE
    .\watchdog.ps1
    .\watchdog.ps1 -IntervalSeconds 120

  .NOTES
    A restart does NOT resume a crashed execution; lock.ps1's self-heal + start-n8n.ps1's
    boot-time lock clear handle the orphaned-run case. The watchdog only guarantees n8n is back
    up to poll again.
  #>
  ```

- [ ] **Verify parse correctness.** Run from the repo root (`C:\dev\nexora`):

  ```powershell
  pwsh -NoProfile -Command {
    $errs = @()
    [System.Management.Automation.Language.Parser]::ParseFile(
      'tools\autopilot\watchdog.ps1', [ref]$null, [ref]$errs
    ) | Out-Null
    if ($errs.Count) { $errs | Format-List; exit 1 }
    'PARSE OK'
  }
  ```

  Expected output: `PARSE OK` with no error text.

- [ ] **Verify help renders both examples.** Run:

  ```powershell
  pwsh -NoProfile -Command "Get-Help -Full .\tools\autopilot\watchdog.ps1"
  ```

  Confirm the output contains an `EXAMPLES` section listing both:
  - `.\watchdog.ps1`
  - `.\watchdog.ps1 -IntervalSeconds 120`

- [ ] **Commit** with the SQL hook bypass (PowerShell / pwsh syntax):

  ```powershell
  $env:SQL_SYNC_SKIP = '1'
  git add tools/autopilot/watchdog.ps1
  git commit -m @'
  docs(autopilot): add .EXAMPLE run-mode usage to watchdog.ps1

  Inserts a single .EXAMPLE block (two command lines) inside the existing
  comment-based-help <# #> header: .\watchdog.ps1 for Task Scheduler
  single-shot mode (default -IntervalSeconds 0, check once and exit) and
  .\watchdog.ps1 -IntervalSeconds 120 for the foreground-loop mode.
  Keyword at column 0 and blank line before .NOTES both match the
  bootstrap.ps1 house-style precedent. Zero logic change; comment only.

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  '@
  $env:SQL_SYNC_SKIP = ''
  ```

  Restore `$env:SQL_SYNC_SKIP` to empty immediately after the commit so the env is clean for subsequent commands.

  _Remote-session policy: stop here. Do not push. Do not open a PR._

---

## Gotchas & notes

- **Do not add a second `<# #>` block.** PowerShell's comment-based-help parser reads only the first `<# #>` block it finds. All `.EXAMPLE` content must go inside the single existing block. A second block below `param()` would be silently ignored by `Get-Help`.

- **The closing `#>` is load-bearing.** If it is accidentally absorbed into the comment body (e.g. indented or preceded by a non-comment character), PowerShell will silently swallow the entire `param()` block and all runtime logic as comment text, making the script a no-op. The `Parser::ParseFile` step (Task 1, step 3) catches this immediately.

- **`.EXAMPLE` keyword is at column 0, not indented.** All section keywords (`.SYNOPSIS`, `.DESCRIPTION`, `.EXAMPLE`, `.NOTES`) sit at column 0 inside the `<# #>` block in `bootstrap.ps1`. Only the content lines beneath each keyword carry the 2-space indent. Do not indent the `.EXAMPLE` keyword itself.

- **Blank line before `.NOTES` is required by house style.** `bootstrap.ps1` line 20 is blank before `.NOTES` on line 21. The new_string above includes that blank line. Removing it would diverge from the only house-style precedent.

- **The prose "Modes:" sub-block in `.DESCRIPTION` stays untouched.** It describes semantics; `.EXAMPLE` shows runnable commands. They coexist cleanly: `Get-Help watchdog.ps1 -Examples` surfaces only `.EXAMPLE`; `Get-Help watchdog.ps1 -Full` shows both.

- **`.\watchdog.ps1` in the examples assumes CWD = `tools\autopilot\`.** For interactive terminal use this is the correct convention (mirrors `bootstrap.ps1`). For Task Scheduler, the operator sets "Start in" to `C:\dev\nexora\tools\autopilot\` or uses the full path.

- **`SQL_SYNC_SKIP=1`, not `--no-verify`.** The pre-commit hook that blocks is `sql-migrate-int` checking INT `SchemaMigrations` CRLF checksums. `SQL_SYNC_SKIP=1` bypasses only that hook's SQL check path; all other pre-commit hooks (line-ending normaliser, etc.) still run. This is the established project convention for non-SQL commits on this branch.
