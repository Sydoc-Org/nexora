"""E2E test fixtures. Starts nx_main.py in a subprocess so Playwright can drive
a real browser against a real Flask server."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# A free port per run, so parallel checkouts/worktrees (and a gate run next to
# a live session) never fight over one; NEXORA_E2E_PORT pins it when you need
# to attach a browser by hand.
E2E_PORT = int(os.environ.get("NEXORA_E2E_PORT") or _free_port())
E2E_BASE_URL = f"http://localhost:{E2E_PORT}"

# Number of automatic retries for flaky browser tests. E2E flakes come from
# real timing (network-idle waits, TOTP window roll-over, server warm-up), so a
# small retry budget keeps the suite green without masking genuine breakage.
E2E_RERUNS = 2
E2E_RERUNS_DELAY = 1


def pytest_collection_modifyitems(config, items):
    """Apply pytest-rerunfailures reruns to every E2E test.

    Scoped by directory, not by the flaky_e2e marker: E2E flakes come from
    real timing (network-idle waits, TOTP roll-over, server warm-up), which
    affects every browser test, and 40+ tests had silently drifted out of the
    net because their authors forgot the decorator. Unit/integration tests
    are untouched and still fail fast and loud. The flaky_e2e marker remains
    registered as documentation only.

    (The gates' old ``--reruns 2 --only-rerun flaky_e2e`` CLI flags never
    retried anything: --only-rerun is an error-text regex, and no traceback
    ever contains the string "flaky_e2e".)
    """
    e2e_dir = Path(__file__).parent
    for item in items:
        if e2e_dir in item.path.parents:
            item.add_marker(pytest.mark.flaky(reruns=E2E_RERUNS, reruns_delay=E2E_RERUNS_DELAY))


@pytest.fixture(autouse=True)
def _e2e_page_setup(request):
    """Tune Playwright page behaviour for this app's CDN-heavy pages.

    Two adjustments, applied to every test that uses a browser page:

    1. Shorter timeouts. The 30s default wedges the suite (and the pre-push
       gate) for 30s per bad selector; 8s surfaces genuine breakage quickly.
    2. domcontentloaded navigation. Every page pulls tailwind, font-awesome
       and google-fonts from external CDNs, so waiting for the "load" event is
       flaky (it blocks on those fetches). We default page.goto to wait only
       for the DOM to parse; element assertions then auto-wait for the CDN
       styles to apply.
    """
    if "page" in request.fixturenames:
        page = request.getfixturevalue("page")
        page.set_default_timeout(8000)
        page.set_default_navigation_timeout(15000)

        _orig_goto = page.goto

        def _goto(url, **kwargs):
            kwargs.setdefault("wait_until", "domcontentloaded")
            return _orig_goto(url, **kwargs)

        page.goto = _goto
    yield


def _port_is_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_http(url, timeout_s=30):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except URLError:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def seed_user_ids():
    """Map seed username -> userid from NEXORA_TEST.

    User ids come from an IDENTITY reseed in sql/test/seed.sql, so query them
    rather than hard-coding. Runs in the pytest process (ENVIRONMENT=TEST is set
    by the root conftest), independent of the browser subprocess.
    """
    from sqlalchemy import text

    from nx_lib.db import engine_nexora_db

    with engine_nexora_db.connect() as conn:
        rows = conn.execute(text("SELECT username, userid FROM Users")).fetchall()
    return dict(rows)


@pytest.fixture(scope="session")
def nexora_server():
    """Start nx_main on E2E_PORT for the duration of the test session."""
    if _port_is_open(E2E_PORT):
        raise RuntimeError(
            f"Port {E2E_PORT} already in use. Stop the other process or change E2E_PORT."
        )

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["ENVIRONMENT"] = "TEST"
    env["FLASK_RUN_PORT"] = str(E2E_PORT)
    # Disable rate limiting for the browser session — a long E2E run issues
    # many requests and would otherwise trip /login's "10 per minute" limit.
    env["NEXORA_DISABLE_RATELIMIT"] = "1"

    # Stream the server's stdout/stderr to a log file rather than an unread
    # PIPE: a long E2E run's request volume fills an undrained PIPE's ~64KB OS
    # buffer, and the server then blocks on write — wedging every subsequent
    # request. A file sink drains freely and keeps the log for post-mortem on
    # startup failure.
    log_dir = repo_root / "var" / "test-results"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "e2e-server.log"
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: SIM115

    proc = subprocess.Popen(
        [sys.executable, "nx_main.py"],
        cwd=repo_root,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    try:
        if not _wait_for_http(f"{E2E_BASE_URL}/login", timeout_s=30):
            proc.terminate()
            proc.wait(timeout=5)
            log_file.flush()
            out = log_path.read_text(encoding="utf-8", errors="replace")
            raise RuntimeError(f"nx_main did not become reachable in 30s. Output:\n{out}")
        yield E2E_BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log_file.close()
