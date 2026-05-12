"""Interactive nexora dev CLI.

Launched by `nx` with no arguments. Renders the nexora logo, then drops into
a prompt_toolkit REPL with arrow-key navigation, tab autocomplete, history,
and a live status bar. One-shot use (`nx -u`, `nx --routes:^/api`, etc.)
still goes through nx.ps1 directly.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import clear as pt_clear
from prompt_toolkit.styles import Style


APP_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = APP_DIR / "logs" / "system"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGO_PNG = APP_DIR / "static" / "images" / "nexora-logo.png"
LOGO_CACHE = LOG_DIR / "logo_cache.txt"
HISTORY_FILE = LOG_DIR / "cli_history.txt"
ENV_STATE = LOG_DIR / "current_env"
NX_PS1 = APP_DIR / "nx.ps1"

LOGO_WIDTH = 70
BG_RGB = (0, 0, 0)
BG_THRESHOLD = 14


# ── logo rendering ─────────────────────────────────────────────────────────

def _render_logo(png_path: Path, width: int) -> str:
    from PIL import Image

    img = Image.open(png_path).convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0 or (r > 235 and g > 235 and b > 235):
                px[x, y] = (0, 0, 0, 0)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size

    new_w = width
    new_h = max(2, round(h * new_w / w))
    if new_h % 2:
        new_h += 1
    img = img.resize((new_w, new_h), Image.LANCZOS)
    composite = Image.new("RGB", img.size, BG_RGB)
    composite.paste(img, mask=img.split()[3])
    cpx = composite.load()

    def is_bg(rgb):
        return (
            rgb[0] < BG_THRESHOLD
            and rgb[1] < BG_THRESHOLD
            and rgb[2] < BG_THRESHOLD
        )

    lines: list[str] = []
    for y in range(0, new_h, 2):
        out: list[str] = []
        last_fg = None
        last_bg = None
        for x in range(new_w):
            top = cpx[x, y]
            bot = cpx[x, y + 1]
            top_bg = is_bg(top)
            bot_bg = is_bg(bot)
            if top_bg and bot_bg:
                if last_fg is not None or last_bg is not None:
                    out.append("\x1b[0m")
                    last_fg = last_bg = None
                out.append(" ")
                continue
            if top_bg:
                if last_bg is not None:
                    out.append("\x1b[49m")
                    last_bg = None
                if bot != last_fg:
                    out.append(f"\x1b[38;2;{bot[0]};{bot[1]};{bot[2]}m")
                    last_fg = bot
                out.append("▄")
                continue
            if bot_bg:
                if last_bg is not None:
                    out.append("\x1b[49m")
                    last_bg = None
                if top != last_fg:
                    out.append(f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m")
                    last_fg = top
                out.append("▀")
                continue
            if bot != last_bg:
                out.append(f"\x1b[48;2;{bot[0]};{bot[1]};{bot[2]}m")
                last_bg = bot
            if top != last_fg:
                out.append(f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m")
                last_fg = top
            out.append("▀")
        out.append("\x1b[0m")
        lines.append("".join(out))
    return "\n".join(lines)


def _logo_text() -> str:
    if not LOGO_PNG.exists():
        return ""
    try:
        if (
            LOGO_CACHE.exists()
            and LOGO_CACHE.stat().st_mtime >= LOGO_PNG.stat().st_mtime
        ):
            return LOGO_CACHE.read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        rendered = _render_logo(LOGO_PNG, LOGO_WIDTH)
    except Exception as exc:
        return f"  [logo render failed: {exc}]"
    try:
        LOGO_CACHE.write_text(rendered, encoding="utf-8")
    except OSError:
        pass
    return rendered


# ── state helpers ──────────────────────────────────────────────────────────

def _port_pid(port: int = 8000) -> int | None:
    if os.name != "nt":
        return None
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
        return int(out) if out.isdigit() else None
    except Exception:
        return None


def _current_env() -> str | None:
    if ENV_STATE.exists():
        try:
            return ENV_STATE.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


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


def cmd_stop(_args: list[str]) -> None:
    _run_ps1("-d")


def cmd_restart(args: list[str]) -> None:
    extra = [f"--env:{args[0].lower()}"] if args else []
    _run_ps1("-r", *extra)
    _routes_cache.clear()


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

def _splash() -> None:
    logo = _logo_text()
    if logo:
        sys.stdout.write(logo + "\n")
    _print()
    _print(
        f"  {C_BOLD}{C_CYAN}nexora dev CLI{C_OFF}   "
        f"{C_DIM}· interactive · type `help` or `?`{C_OFF}"
    )
    _print()


def _bottom_toolbar():
    pid = _port_pid()
    env = _current_env() or "—"
    if pid:
        return HTML(
            f' <style fg="ansigreen">●</style> running   '
            f'pid <b>{pid}</b>   env <b>{env}</b>   port 8000 '
        )
    return HTML(
        f' <style fg="ansiyellow">○</style> stopped   '
        f'env <b>{env}</b> '
    )


def repl() -> int:
    _splash()
    style = Style.from_dict(
        {
            "prompt": "ansicyan bold",
            "completion-menu.completion": "bg:#1a1a1a #cccccc",
            "completion-menu.completion.current": "bg:#5a3eff #ffffff bold",
            "completion-menu.meta.completion": "bg:#1a1a1a #888888",
            "completion-menu.meta.completion.current": "bg:#5a3eff #dddddd",
            "bottom-toolbar": "bg:#262626 #cccccc",
        }
    )
    session: PromptSession = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=NxCompleter(),
        complete_while_typing=True,
        bottom_toolbar=_bottom_toolbar,
        style=style,
    )
    while True:
        try:
            line = session.prompt([("class:prompt", "nexora › ")]).strip()
        except KeyboardInterrupt:
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
