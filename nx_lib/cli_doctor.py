"""nx doctor — preflight health check for the nexora dev environment.

Reports the status of every layer the running app depends on: Python and
its third-party packages, the .env files, filesystem dirs, all four SQL
Server engines, the migrations table, schema drift, on-PATH tooling, git
hooks, port 8000, and the external services nexora talks to (Microsoft
Graph, Octopus, Bexio).

Invoked via the nx CLI:
    nx --doctor                  full check (incl. external services)
    nx --doctor --fast           local-only, also skips schema-drift dump
    nx --doctor --fix            run safe auto-repairs after reporting
    nx --doctor --fast --fix     combine

Exit codes: 0 = no failures (warnings ok); 1 = at least one ✗.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .config import PATHS

APP_DIR = Path(__file__).resolve().parent.parent
ENV_DIR = APP_DIR / "env"
LOG_DIR = PATHS.logs
SESSION_DIR = PATHS.session
TRANSLATIONS_DIR = APP_DIR / "translations"
REQUIREMENTS_FILE = APP_DIR / "requirements.txt"
GIT_HOOKS_DIR = APP_DIR / ".git" / "hooks"
PRE_COMMIT_CONFIG = APP_DIR / ".pre-commit-config.yaml"
MIGRATE_SCRIPT = APP_DIR / "scripts" / "db-migrate.py"
SYNC_SCRIPT = APP_DIR / "sql" / "sync-from-db.py"
BOOTSTRAP_SCRIPT = APP_DIR / "bootstrap.ps1"

# ANSI colours (mirror nx_lib/cli.py)
C_DIM = "\x1b[90m"
C_GREEN = "\x1b[32m"
C_YELLOW = "\x1b[33m"
C_RED = "\x1b[31m"
C_BOLD = "\x1b[1m"
C_OFF = "\x1b[0m"


@dataclass
class CheckResult:
    name: str
    status: str  # "ok" | "warn" | "fail" | "skip"
    detail: str = ""
    hint: str | None = None
    fix: Callable[[], CheckResult | None] | None = None


# ── env bootstrap ──────────────────────────────────────────────────────────


def _bootstrap_env() -> None:
    """Mirror nx_lib.config's dotenv loading without importing the module
    (which would fail if any of its top-level reads break)."""
    os.environ.setdefault("ENVIRONMENT", "INT")
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Repo-root .env is the environment-selector (sets ENVIRONMENT=…); the
    # real secrets file lives in env/<ENV>.env (PR 8 layout) with a
    # legacy root-level fallback for one release.
    load_dotenv(APP_DIR / ".env")
    env_name = os.environ["ENVIRONMENT"]
    primary = ENV_DIR / f"{env_name}.env"
    legacy = APP_DIR / f"{env_name}.env"
    if primary.exists():
        load_dotenv(primary)
    elif legacy.exists():
        load_dotenv(legacy)


# ── individual checks ──────────────────────────────────────────────────────


def _check_python() -> list[CheckResult]:
    label = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return [CheckResult("interpreter", "ok", label)]


def _parse_requirements() -> list[tuple[str, str | None]]:
    pkgs: list[tuple[str, str | None]] = []
    if not REQUIREMENTS_FILE.exists():
        return pkgs
    for raw in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        # Strip end-of-line comment, then PEP 508 environment marker
        # ("colorama==0.4.6 ; sys_platform == 'win32'") so the second
        # `==` inside the marker isn't mistaken for a version pin.
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        if "==" in line:
            name, ver = line.split("==", 1)
        else:
            name, ver = line, None
        pkgs.append((name.strip(), ver.strip() if ver else None))
    return pkgs


def _check_packages() -> list[CheckResult]:
    from importlib.metadata import PackageNotFoundError, version

    pkgs = _parse_requirements()
    if not pkgs:
        return [CheckResult("requirements.txt", "warn", "not found or empty")]

    missing: list[str] = []
    mismatched: list[tuple[str, str, str]] = []
    for name, expected in pkgs:
        try:
            actual = version(name)
        except PackageNotFoundError:
            missing.append(name)
            continue
        if expected and actual != expected:
            mismatched.append((name, expected, actual))

    def _fix_pip() -> CheckResult:
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            return CheckResult("packages", "ok", "all required packages installed")
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or exc.stdout or "").strip().splitlines()
            return CheckResult(
                "packages",
                "fail",
                tail[-1][:140] if tail else "pip install failed",
            )
        except subprocess.TimeoutExpired:
            return CheckResult("packages", "fail", "pip install timed out")

    if missing:
        preview = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
        return [
            CheckResult(
                "packages",
                "fail",
                f"{len(missing)} missing: {preview}",
                hint=f"pip install -r {REQUIREMENTS_FILE.name}",
                fix=_fix_pip,
            )
        ]
    if mismatched:
        preview = ", ".join(f"{n}({a}≠{e})" for n, e, a in mismatched[:3])
        more = "..." if len(mismatched) > 3 else ""
        return [
            CheckResult(
                "packages",
                "warn",
                f"{len(mismatched)} version drift: {preview}{more}",
                hint=f"pip install -r {REQUIREMENTS_FILE.name} --upgrade",
            )
        ]
    return [CheckResult("packages", "ok", f"{len(pkgs)} packages match requirements")]


def _check_env() -> list[CheckResult]:
    results: list[CheckResult] = []
    env_name = os.environ.get("ENVIRONMENT", "INT")
    env_file_primary = ENV_DIR / f"{env_name}.env"
    env_file_legacy = APP_DIR / f"{env_name}.env"
    base_env = APP_DIR / ".env"

    if base_env.exists():
        results.append(CheckResult(".env", "ok", "present"))
    else:
        results.append(CheckResult(".env", "warn", "absent (only env/<ENV>.env strictly needed)"))

    if env_file_primary.exists():
        env_file: Path | None = env_file_primary
        env_label = f"env/{env_name}.env"
        env_status = "ok"
        env_suffix = ""
    elif env_file_legacy.exists():
        env_file = env_file_legacy
        env_label = f"{env_name}.env"
        env_status = "warn"
        env_suffix = " (legacy root location; move into env/)"
    else:
        env_file = None
        env_label = f"env/{env_name}.env"
        env_status = "fail"
        env_suffix = ""

    if env_file is None:
        results.append(
            CheckResult(
                env_label,
                "fail",
                "missing",
                hint=(
                    f"Copy env/{env_name}.env.example to env/{env_name}.env "
                    "and fill in real secrets."
                ),
            )
        )
        return results  # everything below depends on env having loaded

    keys = [
        line.split("=", 1)[0].strip()
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    ]
    results.append(CheckResult(env_label, env_status, f"{len(keys)} keys{env_suffix}"))

    required = [
        "FLASK_SECRET_KEY",
        "DB_UID",
        "DB_PWD",
        "DB_SERVER_PRD",
        "DB_NEXORA",
        "DB_STATISTICS",
        "DB_OCTO_RUNTIME",
        "GRAPH_TENANT_ID",
        "GRAPH_CLIENT_ID",
        "OCTO_CLIENT_ID",
        "OCTO_DOMAIN",
        "BEXIO_PAT",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        results.append(
            CheckResult(
                "env keys",
                "fail",
                f"{len(missing)} unset: {', '.join(missing)}",
                hint=f"Add the missing keys to {env_name}.env.",
            )
        )
    else:
        results.append(CheckResult("env keys", "ok", f"all {len(required)} required keys set"))
    return results


def _check_filesystem() -> list[CheckResult]:
    results: list[CheckResult] = []
    for d, label in [(LOG_DIR, "logs/"), (SESSION_DIR, "session/")]:
        if not d.exists():

            def _make(target=d) -> CheckResult:
                try:
                    target.mkdir(parents=True, exist_ok=True)
                    return CheckResult(target.name + "/", "ok", "created")
                except OSError as exc:
                    return CheckResult(target.name + "/", "fail", str(exc))

            results.append(
                CheckResult(
                    label,
                    "warn",
                    "missing",
                    hint=f"mkdir {d}",
                    fix=_make,
                )
            )
            continue
        try:
            probe = d / ".nx_doctor_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            results.append(CheckResult(label, "ok", "writable"))
        except OSError as exc:
            results.append(CheckResult(label, "fail", f"not writable: {exc}"))

    if TRANSLATIONS_DIR.exists():
        compiled: list[str] = []
        stale: list[str] = []
        for sub in sorted(TRANSLATIONS_DIR.iterdir()):
            if not sub.is_dir():
                continue
            po = sub / "LC_MESSAGES" / "messages.po"
            mo = sub / "LC_MESSAGES" / "messages.mo"
            if not mo.exists():
                stale.append(f"{sub.name} (.mo missing)")
            elif po.exists() and po.stat().st_mtime > mo.stat().st_mtime:
                stale.append(f"{sub.name} (.po newer)")
            else:
                compiled.append(sub.name)
        if stale:
            results.append(
                CheckResult(
                    "translations",
                    "warn",
                    f"stale: {', '.join(stale)}; ok: {', '.join(compiled) or 'none'}",
                    hint="pybabel compile -d translations",
                )
            )
        elif compiled:
            results.append(CheckResult("translations", "ok", f"compiled for {', '.join(compiled)}"))
        else:
            results.append(CheckResult("translations", "warn", "no locales found"))
    return results


def _check_databases() -> list[CheckResult]:
    try:
        from .db import (
            engine_generali_db,
            engine_ms02_docfields_pg,
            engine_ms02_pg,
            engine_ms02_stats_pg,
            engine_nexora_db,
            engine_octo_db,
            engine_statistics_db,
            ping_dbs_parallel,
        )
    except Exception as exc:
        return [
            CheckResult(
                "DB engines",
                "fail",
                f"cannot import nx_lib.db: {exc}",
                hint="Check env keys and pyodbc install.",
            )
        ]

    targets = [
        (engine_nexora_db, "NexoraDB"),
        (engine_octo_db, "OctoDB"),
        (engine_statistics_db, "StatisticsDB"),
        (engine_generali_db, "GeneraliDB"),
        *([(engine_ms02_pg, "MS02 (PG)")] if engine_ms02_pg is not None else []),
        *([(engine_ms02_stats_pg, "MS02 stats (PG)")] if engine_ms02_stats_pg is not None else []),
        *(
            [(engine_ms02_docfields_pg, "MS02 docfields (PG)")]
            if engine_ms02_docfields_pg is not None
            else []
        ),
    ]
    pings = ping_dbs_parallel(targets, timeout_s=3.0)
    pings_by_label = {p["label"]: p for p in pings}
    results: list[CheckResult] = []
    for _, label in targets:
        p = pings_by_label.get(label)
        if not p:
            results.append(CheckResult(label, "fail", "no result"))
            continue
        if p["ok"]:
            results.append(CheckResult(label, "ok", f"{p['latency_ms']} ms"))
        else:
            results.append(
                CheckResult(
                    label,
                    "fail",
                    p["error"],
                    hint="Check DB_SERVER_PRD reachability + VPN.",
                )
            )

    try:
        import pyodbc

        drivers = pyodbc.drivers()
        if any("SQL Server" in d for d in drivers):
            results.append(
                CheckResult(
                    "ODBC driver",
                    "ok",
                    f"SQL Server driver installed ({len(drivers)} total)",
                )
            )
        else:
            results.append(
                CheckResult(
                    "ODBC driver",
                    "fail",
                    f"no SQL Server driver in {drivers!r}",
                    hint="Install ODBC Driver for SQL Server.",
                )
            )
    except Exception as exc:
        results.append(CheckResult("ODBC driver", "fail", str(exc)))
    return results


def _check_migrations() -> list[CheckResult]:
    if not MIGRATE_SCRIPT.exists():
        return [CheckResult("schema migrations", "skip", "scripts/db-migrate.py not found")]
    cmd = [
        sys.executable,
        str(MIGRATE_SCRIPT),
        "--env",
        os.environ.get("ENVIRONMENT", "INT"),
        "--check",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(APP_DIR),
        )
    except subprocess.TimeoutExpired:
        return [CheckResult("schema migrations", "fail", "migrate --check timed out")]

    if proc.returncode == 0:
        return [CheckResult("schema migrations", "ok", "all applied")]
    if proc.returncode == 1:
        msg = "pending migrations"
        for line in (proc.stderr or "").splitlines():
            s = line.strip()
            if "unapplied" in s:
                msg = s.lstrip("[migrate]").strip()
                break
        env = os.environ.get("ENVIRONMENT", "INT")
        return [
            CheckResult(
                "schema migrations",
                "warn",
                msg,
                hint=f"python scripts/db-migrate.py --env {env}",
            )
        ]
    last = (proc.stderr or proc.stdout or "").strip().splitlines()
    return [
        CheckResult(
            "schema migrations",
            "fail",
            last[-1][:140] if last else f"exit {proc.returncode}",
        )
    ]


def _check_drift() -> list[CheckResult]:
    if not SYNC_SCRIPT.exists():
        return [CheckResult("schema dump", "skip", "sql/sync-from-db.py not found")]
    if not (shutil.which("mssql-scripter") or shutil.which("mssql-scripter.exe")):
        return [
            CheckResult(
                "schema dump",
                "skip",
                "mssql-scripter not on PATH",
                hint="pip install -r sql/requirements.txt",
            )
        ]
    cmd = [sys.executable, str(SYNC_SCRIPT), "--check"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(APP_DIR),
        )
    except subprocess.TimeoutExpired:
        return [CheckResult("schema dump", "fail", "sync --check timed out")]
    if proc.returncode == 0:
        return [CheckResult("schema dump", "ok", "in sync with INT")]
    last = ((proc.stderr or proc.stdout) or "").strip().splitlines()
    return [
        CheckResult(
            "schema dump",
            "warn",
            last[-1][:140] if last else f"exit {proc.returncode}",
            hint="python sql/sync-from-db.py",
        )
    ]


_TOOL_HINTS = {
    "sqlcmd": "Install SQL Server Command Line Utilities (ships with SSMS).",
    "mssql-scripter": "pip install -r sql/requirements.txt",
    "git": "Install Git for Windows.",
    "pybabel": "Reinstall requirements (flask-babel installs pybabel).",
    "powershell": "Already shipped with Windows — check PATH.",
}


def _check_tooling() -> list[CheckResult]:
    results: list[CheckResult] = []
    for tool in ("sqlcmd", "mssql-scripter", "git", "pybabel", "powershell"):
        if shutil.which(tool) or shutil.which(tool + ".exe"):
            results.append(CheckResult(tool, "ok", "on PATH"))
        else:
            results.append(
                CheckResult(
                    tool,
                    "warn",
                    "not on PATH",
                    hint=_TOOL_HINTS.get(tool),
                )
            )
    return results


def _check_git_hooks() -> list[CheckResult]:
    if not GIT_HOOKS_DIR.exists():
        return [
            CheckResult(
                "hooks dir",
                "warn",
                ".git/hooks/ not found (not a git checkout?)",
            )
        ]
    if not PRE_COMMIT_CONFIG.exists():
        return [CheckResult("hooks", "skip", ".pre-commit-config.yaml not present")]

    # Hook types the repo's .pre-commit-config.yaml depends on. pre-commit
    # is mandatory; commit-msg drives gitlint; pre-push runs the test gate
    # and the branch-name guard. Each is a separate `pre-commit install`
    # invocation.
    required = ("pre-commit", "commit-msg", "pre-push")
    signature = b"File generated by pre-commit"

    def _install_all() -> CheckResult:
        # Prefer direct `pre-commit install` calls (fast, focused). Only
        # fall back to bootstrap.ps1 if the venv doesn't have pre-commit
        # yet, since bootstrap does a full uv sync first.
        pre_commit = APP_DIR / ".venv" / "Scripts" / "pre-commit.exe"
        if pre_commit.exists():
            steps = [
                [str(pre_commit), "install", "--install-hooks"],
                [str(pre_commit), "install", "--hook-type", "commit-msg"],
                [str(pre_commit), "install", "--hook-type", "pre-push"],
            ]
            try:
                for step in steps:
                    subprocess.run(step, check=True, capture_output=True, text=True, timeout=120)
                return CheckResult("git hooks", "ok", "installed via pre-commit")
            except subprocess.CalledProcessError as exc:
                tail = (exc.stderr or "").strip().splitlines()
                return CheckResult(
                    "git hooks",
                    "fail",
                    tail[-1][:140] if tail else "pre-commit install failed",
                )
            except subprocess.TimeoutExpired:
                return CheckResult("git hooks", "fail", "pre-commit install timed out")

        if not BOOTSTRAP_SCRIPT.exists():
            return CheckResult(
                "git hooks",
                "fail",
                "pre-commit not in .venv and bootstrap.ps1 missing — run `uv sync --extra dev`",
            )
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BOOTSTRAP_SCRIPT),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
            return CheckResult("git hooks", "ok", "bootstrap completed")
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or "").strip().splitlines()
            return CheckResult(
                "git hooks",
                "fail",
                tail[-1][:140] if tail else "bootstrap failed",
            )
        except subprocess.TimeoutExpired:
            return CheckResult("git hooks", "fail", "bootstrap timed out")

    install_hint = (
        ".\\bootstrap.ps1" if BOOTSTRAP_SCRIPT.exists() else "pre-commit install --install-hooks"
    )

    results: list[CheckResult] = []
    for hook in required:
        dst = GIT_HOOKS_DIR / hook
        if not dst.exists():
            results.append(
                CheckResult(
                    hook,
                    "warn",
                    "not installed",
                    hint=install_hint,
                    fix=_install_all,
                )
            )
            continue
        try:
            if signature in dst.read_bytes():
                results.append(CheckResult(hook, "ok", "pre-commit framework"))
            else:
                results.append(
                    CheckResult(
                        hook,
                        "warn",
                        "present but not from pre-commit (will be overwritten on install)",
                        hint=install_hint,
                        fix=_install_all,
                    )
                )
        except OSError as exc:
            results.append(CheckResult(hook, "fail", str(exc)))
    return results


def _check_port() -> list[CheckResult]:
    try:
        with socket.create_connection(("127.0.0.1", 8000), timeout=0.5):
            pass
        return [CheckResult("port 8000", "ok", "in use (nexora reachable)")]
    except OSError:
        return [CheckResult("port 8000", "ok", "free (no running instance)")]


# ── external services (skipped on --fast) ──────────────────────────────────


def _check_graph() -> CheckResult:
    import requests

    tenant = os.environ.get("GRAPH_TENANT_ID")
    if not tenant:
        return CheckResult("Microsoft Graph", "skip", "GRAPH_TENANT_ID not set")
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    body = {
        "client_id": os.environ.get("GRAPH_CLIENT_ID") or "",
        "scope": "https://graph.microsoft.com/.default",
        "username": os.environ.get("GRAPH_USERNAME") or "",
        "password": os.environ.get("GRAPH_PASSWORD") or "",
        "client_secret": os.environ.get("GRAPH_CLIENT_SECRET") or "",
        "grant_type": "password",
    }
    try:
        r = requests.post(url, data=body, timeout=8)
    except requests.RequestException as exc:
        return CheckResult("Microsoft Graph", "fail", str(exc)[:140])
    if r.ok and "access_token" in r.text:
        return CheckResult("Microsoft Graph", "ok", "token acquired")
    try:
        err = r.json().get("error_description") or r.json().get("error") or r.text
    except Exception:
        err = r.text
    err = (err.splitlines()[0] if isinstance(err, str) else str(err))[:140]
    return CheckResult("Microsoft Graph", "fail", f"{r.status_code}: {err}")


def _check_octo() -> CheckResult:
    import requests

    domain = os.environ.get("OCTO_DOMAIN")
    if not domain:
        return CheckResult("Octopus", "skip", "OCTO_DOMAIN not set")
    url = f"https://{domain}/auth/connect/token"
    body = {
        "grant_type": os.environ.get("OCTO_GRANT_TYPE") or "client_credentials",
        "client_id": os.environ.get("OCTO_CLIENT_ID") or "",
        "client_secret": os.environ.get("OCTO_CLIENT_SECRET") or "",
    }
    try:
        r = requests.post(url, data=body, timeout=8)
    except requests.RequestException as exc:
        return CheckResult("Octopus", "fail", str(exc)[:140])
    if r.ok and "access_token" in r.text:
        return CheckResult("Octopus", "ok", f"token acquired ({domain})")
    return CheckResult("Octopus", "fail", f"{r.status_code}: {r.text[:140]}")


def _check_bexio() -> CheckResult:
    import requests

    pat = os.environ.get("BEXIO_PAT")
    if not pat:
        return CheckResult("Bexio", "skip", "BEXIO_PAT not set")
    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/json"}
    try:
        r = requests.get(
            "https://api.bexio.com/2.0/company_profile",
            headers=headers,
            timeout=8,
        )
    except requests.RequestException as exc:
        return CheckResult("Bexio", "fail", str(exc)[:140])
    if r.ok:
        return CheckResult("Bexio", "ok", "PAT valid")
    return CheckResult("Bexio", "fail", f"{r.status_code}: {r.text[:140]}")


# ── rendering + orchestration ──────────────────────────────────────────────

_GLYPH = {
    "ok": f"{C_GREEN}✓{C_OFF}",
    "warn": f"{C_YELLOW}⚠{C_OFF}",
    "fail": f"{C_RED}✗{C_OFF}",
    "skip": f"{C_DIM}–{C_OFF}",
}


def _print_section(title: str, results: list[CheckResult]) -> None:
    sys.stdout.write(f"\n  {C_BOLD}{title}{C_OFF}\n")
    width = max((len(r.name) for r in results), default=0)
    for r in results:
        glyph = _GLYPH.get(r.status, "?")
        name = f"{r.name:<{width}}"
        if r.status == "ok" or r.status == "skip":
            sys.stdout.write(f"    {glyph}  {name}  {C_DIM}{r.detail}{C_OFF}\n")
        else:
            sys.stdout.write(f"    {glyph}  {name}  {r.detail}\n")
            if r.hint:
                sys.stdout.write(f"       {C_DIM}→ {r.hint}{C_OFF}\n")
    sys.stdout.flush()


def _tally(results: list[CheckResult]) -> tuple[int, int, int, int]:
    ok = warn = fail = skip = 0
    for r in results:
        if r.status == "ok":
            ok += 1
        elif r.status == "warn":
            warn += 1
        elif r.status == "fail":
            fail += 1
        elif r.status == "skip":
            skip += 1
    return ok, warn, fail, skip


def run(fast: bool = False, fix: bool = False) -> int:
    """Run all doctor checks and print a traffic-light report.

    fast=True skips schema-drift dump and external services (Graph / Octo / Bexio).
    fix=True attempts safe auto-repairs on fixable warnings/failures after
    the report is printed.

    Returns process exit code (0 if no failures, 1 otherwise).
    """
    _bootstrap_env()

    env_name = os.environ.get("ENVIRONMENT", "INT")
    sys.stdout.write(
        f"\n  {C_BOLD}nexora doctor{C_OFF}  "
        f"{C_DIM}·{C_OFF}  env {C_BOLD}{env_name}{C_OFF}  "
        f"{C_DIM}·{C_OFF}  {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    if fast:
        sys.stdout.write(f"  {C_DIM}(fast: externals + drift skipped){C_OFF}")
    sys.stdout.write("\n")

    sections: list[tuple[str, list[CheckResult]]] = [
        ("Python", _check_python()),
        ("Packages", _check_packages()),
        ("Environment", _check_env()),
        ("Filesystem", _check_filesystem()),
        ("Databases", _check_databases()),
        ("Migrations", _check_migrations()),
    ]

    if not fast:
        sections.append(("Schema dump", _check_drift()))
    else:
        sections.append(
            (
                "Schema dump",
                [
                    CheckResult("schema dump", "skip", "skipped (--fast)"),
                ],
            )
        )

    sections.append(("Tooling", _check_tooling()))
    sections.append(("Git hooks", _check_git_hooks()))
    sections.append(("Port", _check_port()))

    if not fast:
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="nx-doctor") as pool:
            futures = [
                pool.submit(_check_graph),
                pool.submit(_check_octo),
                pool.submit(_check_bexio),
            ]
            ext = [fut.result() for fut in as_completed(futures)]
        order = {"Microsoft Graph": 0, "Octopus": 1, "Bexio": 2}
        ext.sort(key=lambda r: order.get(r.name, 99))
        sections.append(("External services", ext))
    else:
        sections.append(
            (
                "External services",
                [
                    CheckResult("Microsoft Graph", "skip", "skipped (--fast)"),
                    CheckResult("Octopus", "skip", "skipped (--fast)"),
                    CheckResult("Bexio", "skip", "skipped (--fast)"),
                ],
            )
        )

    for title, results in sections:
        _print_section(title, results)

    all_results = [r for _, rs in sections for r in rs]
    ok, warn, fail, skip = _tally(all_results)

    sys.stdout.write(f"\n  {C_DIM}{'─' * 60}{C_OFF}\n")
    sys.stdout.write(
        f"  {C_GREEN}{ok} ok{C_OFF}  {C_DIM}·{C_OFF}  "
        f"{C_YELLOW}{warn} warn{C_OFF}  {C_DIM}·{C_OFF}  "
        f"{C_RED}{fail} fail{C_OFF}  {C_DIM}·{C_OFF}  "
        f"{C_DIM}{skip} skip{C_OFF}\n"
    )

    if fix:
        fixable = [r for r in all_results if r.fix and r.status in ("warn", "fail")]
        if not fixable:
            sys.stdout.write(f"\n  {C_DIM}--fix: nothing to repair.{C_OFF}\n")
        else:
            sys.stdout.write(
                f"\n  {C_BOLD}--fix{C_OFF}  " f"{C_DIM}attempting {len(fixable)} repair(s){C_OFF}\n"
            )
            seen: set[int] = set()
            for r in fixable:
                # De-dupe fixes that point at the same callable (e.g. multiple
                # hook entries both calling install-git-hooks.ps1).
                fid = id(r.fix)
                if fid in seen:
                    continue
                seen.add(fid)
                try:
                    res = r.fix()
                except Exception as exc:
                    res = CheckResult(r.name, "fail", f"fix raised: {exc}")
                if res is None:
                    res = CheckResult(r.name, "ok", "repaired")
                glyph = _GLYPH.get(res.status, "?")
                sys.stdout.write(f"    {glyph}  {res.name}  {res.detail}\n")
            sys.stdout.write(f"\n  {C_DIM}re-run `nx --doctor` to confirm.{C_OFF}\n")

    sys.stdout.flush()
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    fast = "--fast" in sys.argv
    fix = "--fix" in sys.argv
    sys.exit(run(fast=fast, fix=fix))
