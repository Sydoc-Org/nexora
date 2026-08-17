# nx — the nexora dev CLI

`nx` is the developer entry point for running and inspecting the local nexora
app. It has two modes:

- **One-shot** — `nx <command> [options]` does one thing and exits
  (`nx -u`, `nx --routes:^/api`, `nx --doctor`).
- **Interactive** — `nx` with no arguments launches a TUI (splash + REPL) with
  tab-completion, history, and a live status bar.

Under the hood, nexora runs on **`http://127.0.0.1:8000`** and `nx` finds a
running instance by looking for whatever process is listening on port 8000.

## Wiring

The CLI lives at `bin/nx.ps1`. It is normally invoked through a thin wrapper
function in your PowerShell profile so you can type `nx` from anywhere:

```powershell
# in $PROFILE (Microsoft.PowerShell_profile.ps1)
function nx {
    foreach ($a in $args) {
        if ($a -eq '-md' -or $a -eq '--maindir') {
            Set-Location -LiteralPath "C:\dev\nexora"
            return
        }
    }
    & "C:\dev\nexora\bin\nx.ps1" @args
}
```

The wrapper exists for one reason: a child script can't change the **parent
shell's** working directory, so `-md` / `--maindir` (cd into the repo) has to be
handled by the function itself. Everything else is forwarded straight to
`bin/nx.ps1`. Without the wrapper you can always call `.\bin\nx.ps1 <args>`
directly — only `-md` won't move your shell.

> **Per-clone setup:** `bin/nx.ps1` sets `$Python` to a specific interpreter
> path near the top of the file. On a fresh clone, point it at your own venv or
> system Python (`.venv\Scripts\python.exe` after `bootstrap.ps1`).

## One-shot commands

| Command | Does |
|---|---|
| `-u`, `--up` | Start nexora (INT by default) |
| `-d`, `--down` | Stop the port-8000 instance |
| `--down-all` | Stop **all** nexora instances, whatever port they run on (matches `nx_main.py` processes, so it also catches instances started outside `nx`) |
| `-r`, `--restart` | Stop then start |
| `-s`, `--status` | Show running status (PID, env, port) + any in-flight autopilot build |
| `-l`, `--logs` | Stream live logs (requires a running instance) |
| `-md`, `--maindir` | cd into the nexora project directory *(needs the profile wrapper)* |
| `--routes[:<regex>]` | List Flask routes, optionally filtered by regex |
| `--doctor` | Run preflight health checks (env, DBs, migrations, services) |

With no command, `nx` defaults to `--status` (or opens the browser if `-b` /
`--loginas` was given). When an autopilot build is in progress, `status` also prints `autopilot: #<n> <title>  -- building <elapsed> (<phase>)`.

## Options

| Option | Does |
|---|---|
| `-?`, `--help` | Show built-in help |
| `-v`, `--verbose` | Stream logs after start/restart *(only with `-u` / `-r`)* |
| `-b`, `--browser[:<route>]` | Open the browser; bare `-b` opens `/`, `-b:/admin` opens that path |
| `--loginas:<username>` | Open the browser logged in as an INT user *(implies `-b`)* |
| `--port:<n>` | Target a specific instance's port *(only with `-u` / `-r` / `-d`; used by the in-app restart button so a `--no-conflict` instance restarts itself)* |
| `--env` | Print the current env (running instance's env, else `.env` default) |
| `--env:<int\|staging>` | Switch env file *(only with `-u` / `-r` / `--routes`; `prod` is rejected)* |
| `--no-conflict` | Start on the **first free port from 8001 up**, with separate log/state files — an extra nexora runs without touching anything already listening (e.g. an instance a Claude session is testing against). Only valid with `-u` / `-r`; since the port is dynamic, stop extra instances with `--down-all` |
| `--fast` | Skip external-service checks + schema drift *(only with `--doctor`)* |
| `--fix` | Auto-repair fixable warnings *(only with `--doctor`)* |

Flag forms are strict: `-b` and `--routes` accept **only** the colon form
(`-b:/admin`, `--routes:admin`). Space-separated values (`nx -b /admin`) are
rejected.

## Examples

```powershell
nx -u                                # start (INT)
nx -u -v                             # start and stream logs
nx -u -b                             # start and open the browser at /
nx -b:/admin/users                   # open a route (instance already running)
nx -u -b:/admin --loginas:marymue    # start, log in as marymue, land on /admin
nx --routes                          # list every Flask route
nx --routes:admin                    # routes matching /admin/i (path or endpoint)
nx --routes:^/api                    # routes whose path starts with /api
nx --doctor                          # full preflight
nx --doctor --fast                   # skip externals + drift (fast, offline-friendly)
nx --doctor --fix                    # auto-repair fixable findings
nx --env                             # show current env
nx -u --env:staging                  # start against STAGING
nx -u -b --no-conflict               # extra instance on the next free port (8000 untouched)
nx --down-all                        # stop every nexora instance (any port)
nx -r --verbose                      # restart and stream logs
nx -l                                # tail live logs (Ctrl+C stops watching; app keeps running)
nx -md                               # cd into C:\dev\nexora
```

### Driving a Playwright test

The canonical "start the app and log in as a user for browser testing" combo:

```powershell
nx -u -b --loginas:<username>
```

This starts nexora, opens `/dev/login/<username>` (a dev-only login shortcut on
INT), waits ~1.5 s, then navigates to the target route if one was given with
`-b:<route>`. Screenshot artifacts belong in `var/screenshots/`, never the repo
root.

## Interactive mode

Run `nx` with no arguments to get the TUI: a rendered nexora logo, a quick-start
panel, and a REPL prompt that shows live status (`●` running / `○` stopped, env,
port 8000).

REPL commands (the leading slash is optional — `up` and `/up` both work):

| Command | Does |
|---|---|
| `up [env]` | Start nexora (`env` = `int` \| `staging`) |
| `down` | Stop nexora |
| `restart [env]` | Restart nexora |
| `status` | Show running status + in-flight autopilot build |
| `logs` | Stream live logs (Ctrl+C returns to the prompt) |
| `routes [regex]` | List Flask routes, optional regex filter |
| `doctor [--fast] [--fix]` | Preflight checks |
| `browser [route]` | Open the browser (Tab completes route paths) |
| `loginas <user>` | Open the browser as `<user>` (Tab completes usernames from the DB) |
| `env` | Show current env |
| `env:int` / `env:staging` | Switch env (starts or restarts nexora) |
| `clear` / `cls` | Clear the screen and redraw the splash |
| `help` / `?` | Command list |
| `exit` / `quit` / `q` | Leave the CLI |

Niceties:

- **Tab** autocompletes commands, route paths (`browser `), usernames
  (`loginas `, sourced from `dbo.Users`), and env names (`up `/`restart `).
- **↑/↓** browse history; history is persisted to
  `var/logs/system/cli_history.txt`.
- Type-ahead **autosuggest** from history (accept with →).
- **Ctrl+C** once shows a hint; twice exits.

Interactive mode needs a real terminal — piping into `nx` exits with code 2 and
a friendly message. Username autocomplete fires on the first Tab and caches for
the session; if the INT DB is unreachable it silently returns nothing and you
can still type usernames by hand.

## doctor

`nx --doctor` is a traffic-light preflight that reports the health of every
layer the app depends on:

- **Python** interpreter version
- **Packages** — installed versions vs `requirements.txt`
- **Environment** — `.env` + `env/<ENV>.env` presence and required keys
- **Filesystem** — `var/logs/`, `var/session/` writable; translation `.mo`
  compile state
- **Databases** — pings all four engines (NexoraDB, OctoDB, StatisticsDB,
  GeneraliDB) and checks the ODBC driver
- **Migrations** — pending schema migrations for the current env
- **Schema dump** — drift between the per-object SQL files and INT
- **Tooling** — `sqlcmd`, `mssql-scripter`, `git`, `pybabel`, `powershell` on PATH
- **Git hooks** — `pre-commit`, `commit-msg`, `pre-push` installed
- **Port** — whether 8000 is in use
- **External services** — Microsoft Graph, Octo token/auth checks

Failed checks print a `→ hint` line. Modifiers:

- `--fast` skips the schema-drift dump and the external-service calls — good when
  offline or you only need a local sanity check.
- `--fix` runs safe auto-repairs after the report (e.g. `pip install -r
  requirements.txt`, create missing dirs, install git hooks), then tells you to
  re-run to confirm.

Exit codes: **0** when there are no failures (warnings are fine), **1** when at
least one check fails — so `nx --doctor` is usable as a CI/pre-flight gate.

## Notes

- nexora binds **port 8000** by default; `nx` identifies the instance by that
  listening port, so starting it outside `nx` still shows up in `status` (env
  may read `?` if `nx` didn't write the env-state file). `--no-conflict`
  instances get whatever free port the scan picked; only `--down-all` can
  target them afterwards.
- `nx -u` writes the chosen env to `var/logs/system/current_env`; stdout/stderr
  go to `app_stdout.log` / `app_stderr.log` in the same folder (rotated at 10 MB;
  `--no-conflict` instances use port-suffixed variants like `app_stderr.<port>.log`).
- `prod` is intentionally **not** a valid `--env:` target from the CLI.
- The route lister resolves each endpoint to `file:line` via `inspect.unwrap`,
  so decorators like `@require_permission` don't mask the real view location.

## Where the code lives

| Path | Role |
|---|---|
| `bin/nx.ps1` | Process lifecycle (start/stop/restart/logs/status/browser), flag parsing, help |
| `nx_lib/cli.py` | Interactive REPL, splash/logo, `routes` lister (`print_routes`) |
| `nx_lib/cli_doctor.py` | `doctor` checks and `--fix` repairs |

One-shot `--routes` and `--doctor` shell from `bin/nx.ps1` into
`python -m nx_lib.cli routes|doctor`, so the route/check logic has a single
source of truth shared by both modes.
