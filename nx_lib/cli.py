"""Interactive nexora dev CLI.

Launched by `nx` with no arguments. Renders the nexora logo, then drops into
a prompt_toolkit REPL with arrow-key navigation, tab autocomplete, history,
and a live status bar. One-shot use (`nx -u`, `nx --routes:^/api`, etc.)
still goes through nx.ps1 directly.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

_NX_VERSION = "2.5.58"

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory, ThreadedHistory
from prompt_toolkit.shortcuts import clear as pt_clear
from prompt_toolkit.styles import Style


APP_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = APP_DIR / "logs" / "system"
LOG_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = LOG_DIR / "cli_history.txt"
ENV_STATE = LOG_DIR / "current_env"
NX_PS1 = APP_DIR / "nx.ps1"


# ── logo (pixel-art black hole, no PIL) ────────────────────────────────────

_LOGO_TEXT: str | None = None


def _build_logo() -> str:
    """Pixel-art nexora mark: inner violet disc + ring around it. Pure Python, ~1ms."""
    import math

    W, H = 32, 13
    cx = (W - 1) / 2.0
    cy = (H - 1) / 2.0

    # Color palette (24-bit RGB) — nexora violet, lighter highlight, dim edge
    INNER       = "\x1b[38;2;138;110;255m"   # core violet (brand)
    INNER_EDGE  = "\x1b[38;2;100;78;200m"    # disc edge
    RING_BRIGHT = "\x1b[38;2;205;180;255m"   # main ring (lighter violet)
    RING_EDGE   = "\x1b[38;2;110;88;195m"    # ring edge
    HALO        = "\x1b[38;2;55;48;110m"     # outer halo
    RESET       = "\x1b[0m"

    rows: list[str] = []
    for y in range(H):
        parts: list[str] = []
        last_ansi: str | None = None
        for x in range(W):
            dx = (x - cx) * 0.52  # squish x — char cells are ~2:1 tall
            dy = y - cy
            d = math.hypot(dx, dy)

            ansi: str | None = None
            glyph = " "

            if d > 6.6:
                ansi = None                              # empty
            elif d > 6.0:
                ansi, glyph = HALO, "░"                  # faint halo
            elif d > 5.3:
                ansi, glyph = RING_EDGE, "▓"             # ring outer edge
            elif d > 4.3:
                ansi, glyph = RING_BRIGHT, "█"           # main ring
            elif d > 3.9:
                ansi, glyph = RING_EDGE, "▓"             # ring inner edge
            elif d > 2.8:
                ansi = None                              # gap between disc and ring
            elif d > 2.2:
                ansi, glyph = INNER_EDGE, "▓"            # disc outer edge
            else:
                ansi, glyph = INNER, "█"                 # core disc

            if ansi is None:
                if last_ansi is not None:
                    parts.append(RESET)
                    last_ansi = None
                parts.append(" ")
                continue

            if ansi != last_ansi:
                parts.append(ansi)
                last_ansi = ansi
            parts.append(glyph)

        if last_ansi is not None:
            parts.append(RESET)
        rows.append("".join(parts))
    return "\n".join(rows)


def _logo_text() -> str:
    global _LOGO_TEXT
    if _LOGO_TEXT is None:
        try:
            _LOGO_TEXT = _build_logo()
        except Exception:
            _LOGO_TEXT = ""
    return _LOGO_TEXT


# ── boxed-panel layout helpers (Claude-Code-style cage) ────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


def _pad_visible(s: str, width: int) -> str:
    pad = max(0, width - _visible_len(s))
    return s + "\x1b[0m" + " " * pad


def _center_visible(s: str, width: int) -> str:
    vlen = _visible_len(s)
    if vlen >= width:
        return s
    left = (width - vlen) // 2
    right = width - vlen - left
    return " " * left + s + "\x1b[0m" + " " * right


def _build_panel(
    title: str,
    inner_lines: list[str],
    inner_width: int,
    border_color: str,
    title_color: str,
) -> list[str]:
    """Render a Claude-Code-style panel: rounded corners, dashed border, inline title."""
    OFF = "\x1b[0m"
    title_visible = _visible_len(title)
    dashes_n = max(0, inner_width - 4 - title_visible)
    top = (
        f"{border_color}╭╴{OFF} "
        f"{title_color}{title}{OFF}"
        f" {border_color}╶{'╌' * dashes_n}╮{OFF}"
    )
    bottom = f"{border_color}╰{'╌' * inner_width}╯{OFF}"
    rows = [
        f"{border_color}│{OFF}{_pad_visible(ln, inner_width)}{border_color}│{OFF}"
        for ln in inner_lines
    ]
    return [top] + rows + [bottom]


# ── state helpers (TTL-cached so bottom toolbar stays snappy) ──────────────

_STATE_TTL = 3.0
_port_pid_ts: float = 0.0
_port_pid_val: int | None = None
_env_ts: float = 0.0
_env_val: str | None = None


def _invalidate_state_cache() -> None:
    """Force the next _port_pid / _current_env to hit disk/PowerShell."""
    global _port_pid_ts, _env_ts
    _port_pid_ts = 0.0
    _env_ts = 0.0


def _port_pid(port: int = 8000) -> int | None:
    global _port_pid_ts, _port_pid_val
    if os.name != "nt":
        return None
    now = time.monotonic()
    if now - _port_pid_ts < _STATE_TTL:
        return _port_pid_val
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-NetTCPConnection -LocalPort {port} -State Listen "
                f"-ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess",
            ],
            capture_output=True,
            text=True,
            timeout=4,
        ).stdout.strip()
        _port_pid_val = int(out) if out.isdigit() else None
    except Exception:
        _port_pid_val = None
    _port_pid_ts = now
    return _port_pid_val


def _current_env() -> str | None:
    global _env_ts, _env_val
    now = time.monotonic()
    if now - _env_ts < _STATE_TTL:
        return _env_val
    val: str | None = None
    if ENV_STATE.exists():
        try:
            val = ENV_STATE.read_text(encoding="utf-8").strip() or None
        except OSError:
            val = None
    _env_val = val
    _env_ts = now
    return val


# ── ps1 dispatch ───────────────────────────────────────────────────────────

def _run_ps1(*args: str) -> int:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(NX_PS1),
        *args,
    ]
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 130


# ── route + user caches ────────────────────────────────────────────────────

_routes_cache: list[str] = []
_users_cache: list[str] = []
_app_loaded = False


def _ensure_app():
    global _app_loaded
    if _app_loaded:
        return
    import warnings

    warnings.filterwarnings("ignore")
    os.environ.setdefault("ENVIRONMENT", "INT")
    try:
        from nx_main import app  # noqa: F401
        _app_loaded = True
    except Exception:
        _app_loaded = False


def _load_routes() -> list[str]:
    if _routes_cache:
        return _routes_cache
    _ensure_app()
    try:
        from nx_main import app

        _routes_cache.extend(
            sorted(
                {
                    r.rule
                    for r in app.url_map.iter_rules()
                    if not r.rule.startswith("/static")
                }
            )
        )
    except Exception:
        pass
    return _routes_cache


def _prewarm_caches() -> None:
    """Eagerly load routes + users on a daemon thread so the first Tab
    after `open ` / `loginas ` doesn't freeze importing Flask or hitting the DB."""
    try:
        _load_routes()
    except Exception:
        pass
    try:
        _load_users()
    except Exception:
        pass


def _load_users() -> list[str]:
    if _users_cache:
        return _users_cache
    os.environ.setdefault("ENVIRONMENT", "INT")
    try:
        from nx_lib.db import engineNexoraDB

        conn = engineNexoraDB.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT username FROM Users WHERE username IS NOT NULL ORDER BY username"
            )
            for (name,) in cur.fetchall():
                if name:
                    _users_cache.append(name)
        finally:
            conn.close()
    except Exception:
        pass
    return _users_cache


# ── output helpers ─────────────────────────────────────────────────────────

def _print(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


C_DIM = "\x1b[90m"
C_CYAN = "\x1b[36m"
C_GREEN = "\x1b[32m"
C_YELLOW = "\x1b[33m"
C_RED = "\x1b[31m"
C_BOLD = "\x1b[1m"
C_OFF = "\x1b[0m"


# ── commands ───────────────────────────────────────────────────────────────

def cmd_help(_args: list[str]) -> None:
    rows = [
        ("start [env]",       "Start nexora (env: int | staging, default int)"),
        ("stop",               "Stop nexora"),
        ("restart [env]",      "Restart nexora"),
        ("status",             "Show running status"),
        ("logs",               "Stream live logs (Ctrl+C returns to prompt)"),
        ("routes [regex]",     "List Flask routes, optional regex filter"),
        ("open [route]",       "Open browser (tab-completes route paths)"),
        ("loginas <user>",     "Open browser logged in as <user> (tab-completes users)"),
        ("env",                "Show current env"),
        ("env:int | env:staging", "Switch env (starts/restarts nexora)"),
        ("clear / cls",        "Clear screen + redraw splash"),
        ("help / ?",           "This help"),
        ("exit / quit / q",    "Leave the nexora CLI"),
    ]
    _print()
    _print(f"  {C_DIM}Commands:{C_OFF}")
    for cmd, desc in rows:
        _print(f"    {C_CYAN}{cmd:<24}{C_OFF}  {desc}")
    _print()
    _print(
        f"  {C_DIM}Slash prefix optional (`/help`). Tab for autocomplete. "
        f"↑/↓ for history.{C_OFF}"
    )
    _print()


def cmd_status(_args: list[str]) -> None:
    pid = _port_pid()
    env = _current_env() or "?"
    if pid:
        _print(
            f"  {C_GREEN}●{C_OFF}  running   "
            f"pid {C_BOLD}{pid}{C_OFF}   env {C_BOLD}{env}{C_OFF}   port 8000"
        )
    else:
        _print(
            f"  {C_YELLOW}○{C_OFF}  not running   "
            f"{C_DIM}(last env: {env}){C_OFF}"
        )


def cmd_start(args: list[str]) -> None:
    extra = [f"--env:{args[0].lower()}"] if args else []
    _run_ps1("-u", *extra)
    _routes_cache.clear()
    _invalidate_state_cache()


def cmd_stop(_args: list[str]) -> None:
    _run_ps1("-d")
    _invalidate_state_cache()


def cmd_restart(args: list[str]) -> None:
    extra = [f"--env:{args[0].lower()}"] if args else []
    _run_ps1("-r", *extra)
    _routes_cache.clear()
    _invalidate_state_cache()


def cmd_logs(_args: list[str]) -> None:
    if not _port_pid():
        _print(f"  {C_RED}✗{C_OFF}  nexora is not running")
        return
    try:
        _run_ps1("-l")
    except KeyboardInterrupt:
        pass


def cmd_routes(args: list[str]) -> None:
    if args:
        _run_ps1(f"--routes:{args[0]}")
    else:
        _run_ps1("--routes")


def cmd_open(args: list[str]) -> None:
    if not _port_pid():
        _print(f"  {C_RED}✗{C_OFF}  nexora is not running — use `start` first")
        return
    if not args:
        _run_ps1("-b")
        return
    route = args[0]
    if not route.startswith("/"):
        route = "/" + route
    _run_ps1(f"-b:{route}")


def cmd_loginas(args: list[str]) -> None:
    if not args:
        _print(f"  {C_RED}✗{C_OFF}  usage: loginas <username>")
        return
    if not _port_pid():
        _print(f"  {C_RED}✗{C_OFF}  nexora is not running — use `start` first")
        return
    _run_ps1(f"--loginas:{args[0]}")


def cmd_env(_args: list[str]) -> None:
    _run_ps1("--env")


def cmd_clear(_args: list[str]) -> None:
    pt_clear()
    _splash()


COMMANDS: dict[str, Callable[[list[str]], None]] = {
    "help":    cmd_help,
    "?":       cmd_help,
    "status":  cmd_status,
    "start":   cmd_start,
    "stop":    cmd_stop,
    "restart": cmd_restart,
    "logs":    cmd_logs,
    "routes":  cmd_routes,
    "open":    cmd_open,
    "loginas": cmd_loginas,
    "env":     cmd_env,
    "clear":   cmd_clear,
    "cls":     cmd_clear,
}

EXIT_WORDS = {"exit", "quit", "q", ":q"}

COMMAND_HELP: dict[str, str] = {
    "help":    "show command list",
    "?":       "show command list",
    "status":  "show running status",
    "start":   "start nexora",
    "stop":    "stop nexora",
    "restart": "restart nexora",
    "logs":    "stream live logs",
    "routes":  "list Flask routes",
    "open":    "open browser to a route",
    "loginas": "open browser as user",
    "env":     "show current env",
    "env:int":     "switch to INT env",
    "env:staging": "switch to STAGING env",
    "clear":   "clear screen",
    "cls":     "clear screen",
    "exit":    "leave nx",
    "quit":    "leave nx",
}


# ── completion ─────────────────────────────────────────────────────────────

class NxCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        stripped = text.lstrip("/")

        # First word — command names. Tiny list, safe to show while typing.
        if " " not in stripped:
            word = stripped.lower()
            for name in sorted(COMMAND_HELP.keys()):
                if name.startswith(word):
                    yield Completion(
                        name,
                        start_position=-len(stripped),
                        display=name,
                        display_meta=COMMAND_HELP[name],
                    )
            return

        # Arguments — routes/users can be hundreds of entries. Defer to
        # explicit Tab so the popup doesn't re-render on each keystroke.
        if not complete_event.completion_requested:
            return

        head, _, tail = stripped.partition(" ")
        head = head.lower()
        if head == "open":
            for route in _load_routes():
                if tail.lower() in route.lower():
                    yield Completion(route, start_position=-len(tail), display=route)
        elif head == "loginas":
            for user in _load_users():
                if tail.lower() in user.lower():
                    yield Completion(user, start_position=-len(tail), display=user)
        elif head in ("start", "restart"):
            for envname in ("int", "staging"):
                if envname.startswith(tail.lower()):
                    yield Completion(envname, start_position=-len(tail), display=envname)


# ── splash + repl ──────────────────────────────────────────────────────────

def _build_splash() -> str:
    BORDER = "\x1b[38;2;100;88;160m"     # dim violet for box edges
    TITLE  = "\x1b[1;38;2;205;180;255m"  # bold light violet for panel titles
    BRIGHT = "\x1b[1;38;2;230;225;255m"  # bold near-white emphasis
    DIM    = "\x1b[38;2;125;120;160m"    # dim gray-violet helper text
    CMD    = "\x1b[38;2;180;160;240m"    # command word
    DESC   = "\x1b[38;2;160;160;180m"    # command description
    OFF    = "\x1b[0m"

    # ── LEFT: logo cage ─────────────────────────────────────────────────
    LEFT_INNER = 44
    logo_lines = _logo_text().split("\n")
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    env = _current_env() or "INT"

    left_lines: list[str] = [""]
    if user:
        left_lines.append(_center_visible(f"{BRIGHT}Welcome back, {user}!{OFF}", LEFT_INNER))
    left_lines.append("")
    for ln in logo_lines:
        left_lines.append(_center_visible(ln, LEFT_INNER))
    left_lines.append("")
    left_lines.append(_center_visible(f"{BRIGHT}nexora{OFF} {DIM}·{OFF} {BRIGHT}{env}{OFF}", LEFT_INNER))
    left_lines.append(_center_visible(f"{DIM}powered by sydoc{OFF}", LEFT_INNER))
    left_lines.append("")

    # ── RIGHT: quick start ──────────────────────────────────────────────
    RIGHT_INNER = 40
    cmds = [
        ("start",          "start nexora"),
        ("status",         "show running status"),
        ("open <route>",   "open in browser"),
        ("loginas <user>", "login & open"),
        ("routes [regex]", "list endpoints"),
        ("logs",           "stream logs"),
        ("help",           "all commands"),
    ]
    right_lines: list[str] = [""]
    for cmd, desc in cmds:
        right_lines.append(f"  {CMD}{cmd:<16}{OFF}  {DESC}{desc}{OFF}")
    right_lines.append("")
    right_lines.append(f"  {DIM}Tab to autocomplete{OFF}")
    right_lines.append(f"  {DIM}↑/↓ to walk history{OFF}")
    right_lines.append(f"  {DIM}Ctrl+C ×2 to exit{OFF}")
    right_lines.append("")

    left = _build_panel(
        f"nexora dev CLI v{_NX_VERSION}", left_lines, LEFT_INNER, BORDER, TITLE
    )
    right = _build_panel("Quick start", right_lines, RIGHT_INNER, BORDER, TITLE)

    # Match heights for side-by-side stacking
    max_h = max(len(left), len(right))
    blank_left = " " * (LEFT_INNER + 2)
    blank_right = " " * (RIGHT_INNER + 2)
    while len(left) < max_h:
        left.append(blank_left)
    while len(right) < max_h:
        right.append(blank_right)

    return "\n".join(f"{l}  {r}" for l, r in zip(left, right))


def _splash() -> None:
    sys.stdout.write(_build_splash())
    sys.stdout.write("\n\n")
    sys.stdout.flush()


def _prompt_message() -> list[tuple[str, str]]:
    """Build the prompt prefix. Called once per command iteration (not per keystroke)
    so it stays cheap and shows current status without any per-keystroke work."""
    pid = _port_pid()
    env = _current_env() or "—"
    dot_class = "class:status-on" if pid else "class:status-off"
    dot = "●" if pid else "○"
    return [
        (dot_class, f" {dot} "),
        ("class:env-label", f"{env} "),
        ("class:prompt", "nexora › "),
    ]


def repl() -> int:
    import threading

    _splash()
    threading.Thread(target=_prewarm_caches, daemon=True, name="nx-prewarm").start()
    style = Style.from_dict(
        {
            "prompt": "ansicyan bold",
            "status-on": "ansigreen bold",
            "status-off": "ansiyellow",
            "env-label": "ansibrightblack",
            "completion-menu.completion": "bg:#1a1a1a #cccccc",
            "completion-menu.completion.current": "bg:#5a3eff #ffffff bold",
            "completion-menu.meta.completion": "bg:#1a1a1a #888888",
            "completion-menu.meta.completion.current": "bg:#5a3eff #dddddd",
        }
    )
    session: PromptSession = PromptSession(
        history=ThreadedHistory(FileHistory(str(HISTORY_FILE))),
        auto_suggest=AutoSuggestFromHistory(),
        completer=NxCompleter(),
        complete_while_typing=True,
        style=style,
    )
    ctrl_c_pending = False
    while True:
        try:
            line = session.prompt(_prompt_message()).strip()
            ctrl_c_pending = False
        except KeyboardInterrupt:
            if ctrl_c_pending:
                _print()
                return 0
            ctrl_c_pending = True
            _print(f"  {C_DIM}(press Ctrl+C again to exit){C_OFF}")
            continue
        except EOFError:
            _print()
            return 0
        if not line:
            continue
        raw = line.lstrip("/").strip()
        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in EXIT_WORDS:
            return 0
        if cmd.startswith("env:"):
            value = cmd.split(":", 1)[1]
            if not value:
                _print(f"  {C_RED}✗{C_OFF}  usage: env:int  |  env:staging")
                continue
            if _port_pid():
                _run_ps1("-r", f"--env:{value}")
            else:
                _run_ps1("-u", f"--env:{value}")
            _routes_cache.clear()
            _invalidate_state_cache()
            continue
        handler = COMMANDS.get(cmd)
        if not handler:
            _print(
                f"  {C_RED}✗{C_OFF}  unknown command: {cmd}   "
                f"{C_DIM}(try `help`){C_OFF}"
            )
            continue
        try:
            handler(args)
        except KeyboardInterrupt:
            _print()


def main() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stderr.write(
            "nx interactive mode needs a real terminal "
            "(stdin/stdout are not a TTY).\n"
        )
        return 2
    try:
        return repl()
    except Exception as exc:
        sys.stderr.write(f"nx cli error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
