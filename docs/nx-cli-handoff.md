**nx CLI — handoff**

Status snapshot for picking up the nx CLI work in a new session.
Branch at time of writing: `2.5.58`. Date: 2026-05-12.

---

**What's done (this session)**

The single-purpose `nx.ps1` script has been turned into a multi-functional CLI with both one-shot (`nx <flags>`) and interactive (`nx` alone) modes.

- `nx -b[:<route>]` — bare opens root; `nx -b:/admin/users` opens that route. With `--loginas:<user>`, the CLI opens `/dev/login/<user>`, waits 1.5s, then navigates to the target (dev_login does not honor `?next=`).
- `nx --routes[:<regex>]` — lists Flask routes from `nx_main:app`. Regex (case-insensitive) filters both rule path and endpoint name. Shows methods, path, endpoint, and `file:line` of the real view (via `inspect.unwrap`, so `@require_permission` doesn't mask the location). Honors `--env:staging`. Suppresses third-party UserWarning noise.
- `nx` (no args) → interactive TUI in `nx_lib/cli.py` (prompt_toolkit). Splash logo from `static/images/nexora-logo.png`, then a REPL with tab-completion, arrow-key history, autosuggest from history, and a live bottom status bar.
- Parsing: both `-b` and `--routes` accept **only** the colon form (`-b:`, `--routes:`). Space-separated args (`nx -b /admin`) are rejected.
- `-r` is still `--restart`. `--routes` has no short flag (was briefly `-r`, then reverted at user's request).

---

**Files changed / created**

| Path | Status | What it does |
|---|---|---|
| `nx.ps1` | modified | Zero-arg dispatch to `python -m nx_lib.cli`; flag parser; help text; `Show-Routes` was removed and replaced by routes living in the Python CLI module (the one-shot `--routes:` form still works via embedded Python). |
| `nx_lib/cli.py` | new | prompt_toolkit REPL. Logo renderer (Pillow → Unicode `▀` half-blocks, 24-bit color, alpha-keyed for transparency). Command dispatch shells back to `nx.ps1` for process lifecycle. |
| `requirements.txt` | modified | Added `prompt_toolkit==3.0.51`. Pillow was already present. |
| `logs/system/logo_cache.txt` | runtime cache | Rendered logo art. Auto-rebuilt when `nexora-logo.png` mtime is newer. |
| `logs/system/cli_history.txt` | runtime data | REPL command history. |

Note: the embedded Python in `nx.ps1` (`Show-Routes` function) still exists for the one-shot `nx --routes:...` flow. It is the source of truth for route listing — the REPL's `routes` command shells back to `nx.ps1 --routes:<pat>` so the formatting and unwrap logic stay in one place. If you refactor, consider moving the route-listing logic from `nx.ps1` into `nx_lib/cli.py` and having `nx.ps1` call into Python for both modes.

---

**Architecture**

```
nx.ps1   ──┬─ args empty?  ──► python -m nx_lib.cli   (interactive REPL)
           │
           └─ args present  ──► flag parser ──► Start-App / Stop-App / Watch-Logs / Open-Browser / Show-Routes / Show-CurrentEnv
                                                 │                                                   │
                                                 └─ launches python nx_main.py                       └─ embedded Python imports nx_main:app, dumps url_map
```

```
nx_lib/cli.py
  splash:        Pillow load PNG → alpha-key whites → crop bbox → resize to 70 cols → composite over black → emit half-blocks
  state:         _port_pid (Get-NetTCPConnection via subprocess), _current_env (reads logs/system/current_env)
  commands:      start/stop/restart/logs/status/routes/open/loginas/env/env:<x>/clear/help/exit
                 → all shell out to powershell -File nx.ps1 <flags>
  completion:    NxCompleter — first word from COMMAND_HELP; arg-aware for open/loginas/start/restart
  data sources:  routes lazy-loaded from nx_main:app.url_map; users lazy-loaded from dbo.Users
```

---

**How to test**

1. `nx --help` — confirm new help text mentions interactive mode.
2. `nx --routes:^/admin` — confirm regex filtering + file:line column work, and no flask_limiter warning.
3. `nx -b:/admin/users` — confirm browser opens the right path.
4. `nx` — confirm splash renders, prompt appears, `help` works, Tab on `open ` lists routes, Tab on `loginas ` lists users from DB, `status` shows live PID/env, `exit` returns to PowerShell cleanly.
5. `nx -u` from inside the REPL via `start` — confirm subprocess streams output and `status` flips to running.

---

**Open ideas (not implemented)**

These came up during the recommendation phase but weren't picked. Worth considering if the CLI gets more use.

- `nx --perms <user>` — call `dbo.spGetUserPermissions` and print the permission codes.
- `nx --sql` / `nx --sql:tail` — open or tail `environment_transfer_queries.tmp.sql`.
- `nx --babel`, `nx --babel:compile`, `nx --babel:check` — wrap the three-step `pybabel` recipe from `howtobabel.txt`.
- `nx --csv [today|YYYYMMDDHH]` — tail the per-request CSV log (different stream than stderr).
- `nx --slow [N]` — top-N slowest requests from today's CSV.
- `nx --health` — `GET /` and report status + ms.
- `nx --clean-sessions`, `nx --clean-logs --days N` — wrap the existing PowerShell cleanup scripts.
- `nx --tunnel` / `nx --tunnel:stop` — start/stop ngrok via `ngrok.yaml`; guard on hostname == `SYAPP01`.
- `nx --play <spec>`, `nx --shot <route>` — Playwright runners; auto-start nexora; screenshots into `screenshots/`.
- `nx --db <nexora|octo|stats|mobscan|generali>` — launch `sqlcmd` with the matching env-var lookup.
- `nx --shell` — `python -i` with the Flask app context pushed.

In the REPL specifically: a `tail-logs` background pane (live log stream above the prompt) would be very claude-code-like but adds significant complexity.

---

**Known issues / things to verify**

- **`app.py` does not exist on disk** but `git status` shows `M app.py` (mid-refactor to `nx_main.py` + `nx_lib/views/`). The CLI uses `nx_main` directly, so it's fine. Be aware when the refactor lands that `nx.ps1` still references `$AppPy = nx_main.py` (already updated, good).
- The logo render takes ~300–600 ms cold (Pillow + PNG decode). Cached art is ~16 lines. If you regenerate the logo PNG, the cache invalidates automatically by mtime.
- Logo uses 24-bit color. Windows Terminal / PS7: perfect. Legacy conhost on older builds: muted. Win11 is fine.
- `prompt_toolkit` REPL needs a real TTY. Piping into `nx` returns exit code 2 with a friendly message — by design.
- DB lookup for `loginas` autocomplete fires on first Tab in that context and caches for the session. If `INT` DB is down, autocomplete silently returns an empty list — typed usernames still work.
- Subprocess invocation uses `powershell -NoProfile -ExecutionPolicy Bypass -File nx.ps1`. If you ever set an execution policy to `AllSigned`, this still works because of `-ExecutionPolicy Bypass`.
- The REPL's `routes` command shells back to `nx.ps1` which re-imports `nx_main` each time (300–600 ms). If you list routes frequently, consider moving the route renderer into `nx_lib/cli.py` to reuse the already-loaded `app`.
- `start` from inside the REPL clears the route cache so a subsequent `routes` reflects any newly registered endpoints.

---

**Extension recipes**

Quick pointers if you want to add to the CLI:

- **New command in REPL** — add a `cmd_xxx(args: list[str])` function in `nx_lib/cli.py`, register it in the `COMMANDS` dict, add a one-line entry in `COMMAND_HELP` for autocomplete metadata, and add a row to `cmd_help`.
- **New one-shot flag** — add a regex match before the `switch` in `nx.ps1`'s parser, or a new entry in the `switch -Exact` block. Add validation under the `if ($envOverride)` block if it should be env-restricted. Add an `'action'` case to the bottom switch.
- **Context-aware autocomplete** — extend `NxCompleter.get_completions`. The pattern: branch on the first word, yield `Completion(value, start_position=-len(tail), display=...)`.
- **Change the splash** — set `LOGO_WIDTH` in `nx_lib/cli.py`. Delete `logs/system/logo_cache.txt` to force a re-render. Tweak `BG_THRESHOLD` (currently 14) if alpha-keying leaves halos.
- **Change the prompt** — `session.prompt([("class:prompt", "nexora › ")])` — swap the text or the style class.
- **Move route listing fully into Python** — port the embedded `Show-Routes` body in `nx.ps1` into a function in `nx_lib/cli.py`, expose it via a `--routes` arg on `python -m nx_lib.cli`, and shell to that from `nx.ps1` so both modes share one implementation.

---

**Conversation context worth carrying over**

- User preferences: AskUserQuestion for choices, no auto-commits, terse responses with bold sections (not headers), batch-execute long plans with review at the end.
- The user is mid-refactor splitting `app.py` (5800 lines) into `nx_main.py` + `nx_lib/` package modules. Don't bake assumptions about where view functions live; use `inspect.unwrap` + `getsourcefile`.
- Flask template cache: nexora caches Jinja templates for the process lifetime. Restart after template edits.
- DB SQL changes go in `environment_transfer_queries.tmp.sql` with a `--claudes new sql statement:` header. The user runs that file manually on INT and PROD.
- `nx -u -b --loginas:<user>` is the standard "drive a Playwright test" combo.
