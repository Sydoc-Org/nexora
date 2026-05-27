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
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory, ThreadedHistory
from prompt_toolkit.shortcuts import clear as pt_clear
from prompt_toolkit.styles import Style

_NX_VERSION = "2.5.60"

APP_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = APP_DIR / "logs" / "system"
LOG_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = LOG_DIR / "cli_history.txt"
ENV_STATE = LOG_DIR / "current_env"
NX_PS1 = APP_DIR / "nx.ps1"


# ── logo (pixel-art black hole, no PIL) ────────────────────────────────────

_LOGO_TEXT: str | None = None


def _build_logo() -> str:
    """3D nexora mark: violet sphere wrapped by a tilted annular ring.

    Renders a true 3D scene at 32×26 pixels (13 char rows × 2 vertical sub-pixels
    via Unicode half-blocks). The sphere is shaded with frontal Lambert + Phong
    specular; the ring is a flat annulus tilted ~28° from edge-on. Depth-correct
    compositing means the ring's near arc draws *over* the lower half of the
    sphere while the far arc is hidden *behind* the sphere's upper half — the
    classic Saturn / Interstellar accretion-disc look.
    """
    import math

    W, H = 32, 26
    cx = (W - 1) / 2.0
    cy = (H - 1) / 2.0

    # ── Scene parameters (sized to fill the 32×26 pixel grid) ──────────────
    R_SPHERE = 6.2
    R_RING_IN = 8.5
    R_RING_OUT = 14.6

    # Elevation angle of camera above the ring's plane (in radians).
    # 0   = ring viewed perfectly edge-on (becomes a horizontal line)
    # π/2 = ring viewed face-on (the old flat-halo look)
    # 36° = enough tilt that the ring projects ~8.6 px vertically — clearly
    #       extending above & below the 6.2-px sphere — but still low enough
    #       to read as frontal, not bird's-eye.
    ALPHA = math.radians(36.0)
    SIN_A = math.sin(ALPHA)
    COS_A = math.cos(ALPHA)
    COT_A = COS_A / SIN_A

    # Frontal lighting, very slight upward tilt (so the spec highlight sits
    # a touch above sphere centre — feels alive rather than flat).
    LX, LY, LZ = 0.0, 0.14, 0.990  # math-y is +up; light is from above-front

    # ── Palettes ───────────────────────────────────────────────────────────
    # Sphere reads as the black-hole core: deep, mostly dark, with brand
    # violet lighting only in the brightest 25% — keeps it visibly distinct
    # from the luminous ring.
    SPHERE_DARK = (6, 4, 20)
    SPHERE_BASE = (38, 26, 92)
    SPHERE_LIGHT = (140, 115, 230)

    # Ring is the accretion disc: full brand violet, glowing white at peak.
    RING_DARK = (55, 38, 130)
    RING_BASE = (180, 148, 252)
    RING_LIGHT = (252, 244, 255)

    def lerp(a, b, t):
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        return (
            int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t),
        )

    # ── Sphere shading: matte dark mass (event horizon), limb-darkened ─────
    def shade_sphere(sx_n, sy_n):
        r2 = sx_n * sx_n + sy_n * sy_n
        if r2 >= 1.0:
            return SPHERE_DARK
        nz = math.sqrt(1.0 - r2)
        nl = sx_n * LX + sy_n * LY + nz * LZ
        # Compressed diffuse range — even the brightest sphere point stays
        # noticeably darker than the surrounding ring, so the ring dominates.
        diff = 0.06 if nl < 0.0 else 0.08 + 0.55 * nl  # peak ≈ 0.63 (vs. ring peak ≈ 1.0)
        if diff >= 0.45:
            col = lerp(SPHERE_BASE, SPHERE_LIGHT, (diff - 0.45) / 0.18)
        else:
            col = lerp(SPHERE_DARK, SPHERE_BASE, diff / 0.45)
        return col

    # ── Ring shading: radial glow + atmospheric dim on the far half ─────────
    def shade_ring(r_obj, near_side):
        mid = (R_RING_IN + R_RING_OUT) * 0.5
        half = (R_RING_OUT - R_RING_IN) * 0.5
        # Soft falloff: 1.0 at mid-ring, 0 at inner/outer edges
        t = 1.0 - abs(r_obj - mid) / half
        if t < 0.0:
            t = 0.0
        t = t**0.55  # gentler curve, more luminous body
        if t >= 0.7:
            col = lerp(RING_BASE, RING_LIGHT, (t - 0.7) / 0.3)
        else:
            col = lerp(RING_DARK, RING_BASE, t / 0.7)
        # Far side (behind sphere when not occluded): subtle atmospheric dim
        if not near_side:
            col = lerp(col, RING_DARK, 0.35)
        return col

    # ── Rasterise the scene into a pixel buffer ────────────────────────────
    pixels: list[list[tuple[int, int, int] | None]] = [[None] * W for _ in range(H)]
    R_S2 = R_SPHERE * R_SPHERE
    R_RI2 = R_RING_IN * R_RING_IN
    R_RO2 = R_RING_OUT * R_RING_OUT
    for y in range(H):
        for x in range(W):
            sx = x - cx
            my = -(y - cy)  # math y (+up); image y grows downward

            # — Sphere coverage / depth at this pixel —
            sphere_depth = None
            sphere_col = None
            r_sph_sq = sx * sx + my * my
            if r_sph_sq <= R_S2:
                sphere_depth = math.sqrt(R_S2 - r_sph_sq)
                sphere_col = shade_sphere(sx / R_SPHERE, my / R_SPHERE)

            # — Ring coverage / depth at this pixel —
            # A flat annulus tilted by ALPHA around the X axis projects to an
            # annular ellipse. Pre-image radius in the ring's own plane:
            #     r_obj² = sx² + (my / sin α)²
            # Depth of the projected point on the ring:
            #     z = -my · cot α   (front side when my < 0 in math-y)
            ring_depth = None
            ring_col = None
            r_obj_sq = sx * sx + (my / SIN_A) ** 2
            if R_RI2 <= r_obj_sq <= R_RO2:
                r_obj = math.sqrt(r_obj_sq)
                ring_depth = -my * COT_A
                ring_col = shade_ring(r_obj, near_side=(my <= 0))

            # — Composite: painter's algorithm by depth —
            if sphere_col is not None and ring_col is not None:
                pixels[y][x] = ring_col if ring_depth > sphere_depth else sphere_col
            elif sphere_col is not None:
                pixels[y][x] = sphere_col
            elif ring_col is not None:
                pixels[y][x] = ring_col

    # 2. Pair rows into half-block character rows
    OFF = "\x1b[0m"
    rows: list[str] = []
    for py in range(0, H, 2):
        parts: list[str] = []
        last_fg: tuple[int, int, int] | None = None
        last_bg: tuple[int, int, int] | None = None
        last_mode: str | None = None  # 'full', 'top', 'bot', 'empty'
        for x in range(W):
            top = pixels[py][x] if py < H else None
            bot = pixels[py + 1][x] if py + 1 < H else None
            if top is None and bot is None:
                if last_mode != "empty":
                    parts.append(OFF)
                    last_fg = last_bg = None
                    last_mode = "empty"
                parts.append(" ")
            elif top is not None and bot is not None:
                if last_mode != "full" or top != last_fg or bot != last_bg:
                    parts.append(
                        f"\x1b[38;2;{top[0]};{top[1]};{top[2]};" f"48;2;{bot[0]};{bot[1]};{bot[2]}m"
                    )
                    last_fg, last_bg, last_mode = top, bot, "full"
                parts.append("▀")
            elif top is not None:
                # Top half coloured, bottom is terminal default — need explicit bg reset
                if last_mode != "top" or top != last_fg:
                    parts.append(f"{OFF}\x1b[38;2;{top[0]};{top[1]};{top[2]}m")
                    last_fg, last_bg, last_mode = top, None, "top"
                parts.append("▀")
            else:  # bot is not None
                if last_mode != "bot" or bot != last_fg:
                    parts.append(f"{OFF}\x1b[38;2;{bot[0]};{bot[1]};{bot[2]}m")
                    last_fg, last_bg, last_mode = bot, None, "bot"
                parts.append("▄")
        parts.append(OFF)
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
    return [top, *rows, bottom]


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
            sorted({r.rule for r in app.url_map.iter_rules() if not r.rule.startswith("/static")})
        )
    except Exception:
        pass
    return _routes_cache


def print_routes(pattern: str | None = None) -> int:
    """Print Flask routes (methods, rule, endpoint, source location).

    Single source of truth for both one-shot `nx --routes` and the REPL
    `routes` command. Returns a process exit code so it can be wired into
    `main()` as a subcommand.
    """
    import inspect
    import warnings

    warnings.filterwarnings("ignore")

    regex = None
    if pattern:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            sys.stderr.write(f"invalid regex '{pattern}': {exc}\n")
            return 2

    os.environ.setdefault("ENVIRONMENT", "INT")
    try:
        from nx_main import app
    except Exception as exc:
        sys.stderr.write(f"failed to import nx_main: {exc}\n")
        return 1

    root = os.getcwd()

    def origin(endpoint: str) -> str:
        fn = app.view_functions.get(endpoint)
        if not fn:
            return ""
        try:
            fn = inspect.unwrap(fn)
            src = inspect.getsourcefile(fn) or ""
            line = inspect.getsourcelines(fn)[1]
        except (OSError, TypeError, ValueError):
            return ""
        if not src:
            return ""
        try:
            rel = os.path.relpath(src, root)
            if not rel.startswith(".."):
                src = rel
        except ValueError:
            pass
        return f"{src}:{line}"

    rules = sorted(app.url_map.iter_rules(), key=lambda r: r.rule)
    rows: list[tuple[str, str, str, str]] = []
    total = 0
    for rule in rules:
        total += 1
        if regex and not regex.search(rule.rule) and not regex.search(rule.endpoint):
            continue
        methods = ",".join(sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS")))
        rows.append((methods, rule.rule, rule.endpoint, origin(rule.endpoint)))

    mw = max((len(r[0]) for r in rows), default=6)
    rw = max((len(r[1]) for r in rows), default=4)
    ew = max((len(r[2]) for r in rows), default=8)

    for methods, rule_path, endpoint, where in rows:
        print(f"{methods:<{mw}}  {rule_path:<{rw}}  {endpoint:<{ew}}  {where}")

    print()
    if pattern:
        print(f"{len(rows)} of {total} routes matching /{pattern}/i")
    else:
        print(f"{total} routes total")
    return 0


def _run_python_module(*args: str) -> int:
    """Spawn `python -m nx_lib.cli <args>` as a fresh subprocess.

    Used by REPL commands that need a clean process (e.g. `routes` so the
    Flask import sees current env vars, and so output streams cleanly back
    to the parent terminal)."""
    cmd = [sys.executable, "-m", "nx_lib.cli", *args]
    try:
        return subprocess.call(cmd, cwd=str(APP_DIR))
    except KeyboardInterrupt:
        return 130


def _prewarm_caches() -> None:
    """Eagerly load routes + users on a daemon thread so the first Tab
    after `browser ` / `loginas ` doesn't freeze importing Flask or hitting the DB."""
    with suppress(Exception):
        _load_routes()
    with suppress(Exception):
        _load_users()


def _load_users() -> list[str]:
    if _users_cache:
        return _users_cache
    os.environ.setdefault("ENVIRONMENT", "INT")
    try:
        from nx_lib.db import engine_nexora_db

        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT username FROM Users WHERE username IS NOT NULL ORDER BY username")
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
        ("up [env]", "Start nexora (env: int | staging, default int)"),
        ("down", "Stop nexora"),
        ("restart [env]", "Restart nexora"),
        ("status", "Show running status"),
        ("logs", "Stream live logs (Ctrl+C returns to prompt)"),
        ("routes [regex]", "List Flask routes, optional regex filter"),
        ("doctor [--fast] [--fix]", "Preflight checks (env, DBs, migrations, services)"),
        ("browser [route]", "Open browser (tab-completes route paths)"),
        ("loginas <user>", "Open browser logged in as <user> (tab-completes users)"),
        ("env", "Show current env"),
        ("env:int | env:staging", "Switch env (starts/restarts nexora)"),
        ("clear / cls", "Clear screen + redraw splash"),
        ("help / ?", "This help"),
        ("exit / quit / q", "Leave the nexora CLI"),
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
        _print(f"  {C_YELLOW}○{C_OFF}  not running   " f"{C_DIM}(last env: {env}){C_OFF}")


def cmd_up(args: list[str]) -> None:
    extra = [f"--env:{args[0].lower()}"] if args else []
    _run_ps1("-u", *extra)
    _routes_cache.clear()
    _invalidate_state_cache()


def cmd_down(_args: list[str]) -> None:
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
    with suppress(KeyboardInterrupt):
        _run_ps1("-l")


def cmd_routes(args: list[str]) -> None:
    # Fresh subprocess so output streams cleanly and Flask import sees the
    # current ENVIRONMENT value at call time. Goes straight to the Python
    # implementation in `print_routes()`, no PowerShell roundtrip.
    if args:
        _run_python_module("routes", args[0])
    else:
        _run_python_module("routes")


def cmd_doctor(args: list[str]) -> None:
    # Fresh subprocess: doctor imports heavy modules (sqlalchemy, requests)
    # and we don't want them sticking around in the REPL process. Args pass
    # through verbatim so `doctor --fast --fix` works.
    _run_python_module("doctor", *args)
    _invalidate_state_cache()


def cmd_browser(args: list[str]) -> None:
    if not _port_pid():
        _print(f"  {C_RED}✗{C_OFF}  nexora is not running — use `up` first")
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
        _print(f"  {C_RED}✗{C_OFF}  nexora is not running — use `up` first")
        return
    _run_ps1(f"--loginas:{args[0]}")


def cmd_env(_args: list[str]) -> None:
    _run_ps1("--env")


def cmd_clear(_args: list[str]) -> None:
    pt_clear()
    _splash()


COMMANDS: dict[str, Callable[[list[str]], None]] = {
    "help": cmd_help,
    "?": cmd_help,
    "status": cmd_status,
    "up": cmd_up,
    "down": cmd_down,
    "restart": cmd_restart,
    "logs": cmd_logs,
    "routes": cmd_routes,
    "doctor": cmd_doctor,
    "browser": cmd_browser,
    "loginas": cmd_loginas,
    "env": cmd_env,
    "clear": cmd_clear,
    "cls": cmd_clear,
}

EXIT_WORDS = {"exit", "quit", "q", ":q"}

COMMAND_HELP: dict[str, str] = {
    "help": "show command list",
    "?": "show command list",
    "status": "show running status",
    "up": "start nexora",
    "down": "stop nexora",
    "restart": "restart nexora",
    "logs": "stream live logs",
    "routes": "list Flask routes",
    "doctor": "preflight env + service checks",
    "browser": "open browser to a route",
    "loginas": "open browser as user",
    "env": "show current env",
    "env:int": "switch to INT env",
    "env:staging": "switch to STAGING env",
    "clear": "clear screen",
    "cls": "clear screen",
    "exit": "leave nx",
    "quit": "leave nx",
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
        if head == "browser":
            for route in _load_routes():
                if tail.lower() in route.lower():
                    yield Completion(route, start_position=-len(tail), display=route)
        elif head == "loginas":
            for user in _load_users():
                if tail.lower() in user.lower():
                    yield Completion(user, start_position=-len(tail), display=user)
        elif head in ("up", "restart"):
            for envname in ("int", "staging"):
                if envname.startswith(tail.lower()):
                    yield Completion(envname, start_position=-len(tail), display=envname)


# ── splash + repl ──────────────────────────────────────────────────────────


def _build_splash() -> str:
    BORDER = "\x1b[38;2;100;88;160m"  # dim violet for box edges
    TITLE = "\x1b[1;38;2;205;180;255m"  # bold light violet for panel titles
    BRIGHT = "\x1b[1;38;2;230;225;255m"  # bold near-white emphasis
    DIM = "\x1b[38;2;125;120;160m"  # dim gray-violet helper text
    CMD = "\x1b[38;2;180;160;240m"  # command word
    DESC = "\x1b[38;2;160;160;180m"  # command description
    OFF = "\x1b[0m"

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
    left_lines.append(
        _center_visible(f"{BRIGHT}nexora{OFF} {DIM}·{OFF} {BRIGHT}{env}{OFF}", LEFT_INNER)
    )
    left_lines.append(_center_visible(f"{DIM}powered by sydoc{OFF}", LEFT_INNER))
    left_lines.append("")

    # ── RIGHT: quick start ──────────────────────────────────────────────
    RIGHT_INNER = 40
    cmds = [
        ("up", "start nexora"),
        ("status", "show running status"),
        ("browser <route>", "open in browser"),
        ("loginas <user>", "login & open"),
        ("routes [regex]", "list endpoints"),
        ("doctor", "preflight checks"),
        ("logs", "stream logs"),
        ("help", "all commands"),
    ]
    examples = [
        ("browser /admin", "browse to a route"),
        ("loginas marymue", "switch session"),
        ("routes ^/api", "regex filter"),
        ("env:staging", "swap env on-the-fly"),
    ]

    right_lines: list[str] = [""]
    right_lines.append(f"  {BRIGHT}Commands{OFF}")
    right_lines.append("")
    for cmd, desc in cmds:
        right_lines.append(f"  {CMD}{cmd:<16}{OFF}  {DESC}{desc}{OFF}")
    right_lines.append("")
    right_lines.append(f"  {BRIGHT}Examples{OFF}")
    right_lines.append("")
    for cmd, desc in examples:
        right_lines.append(f"  {CMD}{cmd:<17}{OFF}  {DESC}{desc}{OFF}")
    right_lines.append("")
    right_lines.append(f"  {DIM}Tab to autocomplete · ↑/↓ history{OFF}")
    right_lines.append(f"  {DIM}Ctrl+C ×2 to exit{OFF}")
    right_lines.append("")

    # Pad inner content so both panels close at the same line (no orphan gap below
    # the shorter panel's bottom border). Doing this *before* _build_panel keeps the
    # rounded ╰ borders aligned.
    max_inner = max(len(left_lines), len(right_lines))
    while len(left_lines) < max_inner:
        left_lines.append("")
    while len(right_lines) < max_inner:
        right_lines.append("")

    left = _build_panel(f"nexora dev CLI v{_NX_VERSION}", left_lines, LEFT_INNER, BORDER, TITLE)
    right = _build_panel("Quick start", right_lines, RIGHT_INNER, BORDER, TITLE)

    return "\n".join(f"{lt}  {rt}" for lt, rt in zip(left, right, strict=False))


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
            _print(f"  {C_RED}✗{C_OFF}  unknown command: {cmd}   " f"{C_DIM}(try `help`){C_OFF}")
            continue
        try:
            handler(args)
        except KeyboardInterrupt:
            _print()


def main() -> int:
    # One-shot subcommands (invoked by nx.ps1 or directly via `python -m nx_lib.cli`):
    #   routes [<regex>]              List Flask routes, optional regex filter.
    #   doctor [--fast] [--fix]       Run preflight health checks.
    if len(sys.argv) > 1 and sys.argv[1] == "routes":
        pattern = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
        return print_routes(pattern)
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        from . import cli_doctor

        rest = sys.argv[2:]
        return cli_doctor.run(fast="--fast" in rest, fix="--fix" in rest)

    # Default: interactive REPL.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stderr.write(
            "nx interactive mode needs a real terminal " "(stdin/stdout are not a TTY).\n"
        )
        return 2
    try:
        return repl()
    except Exception as exc:
        sys.stderr.write(f"nx cli error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
