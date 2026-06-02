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

E2E_PORT = 8765
E2E_BASE_URL = f"http://localhost:{E2E_PORT}"

# Number of automatic retries for flaky browser tests. E2E flakes come from
# real timing (network-idle waits, TOTP window roll-over, server warm-up), so a
# small retry budget keeps the suite green without masking genuine breakage.
E2E_RERUNS = 2
E2E_RERUNS_DELAY = 1


def pytest_collection_modifyitems(config, items):
    """Apply pytest-rerunfailures reruns to every flaky_e2e-marked test.

    The flaky_e2e marker was previously decorative (no --reruns in addopts).
    Scoping reruns here keeps them confined to E2E tests so unit/integration
    failures still fail fast and loud.
    """
    for item in items:
        if item.get_closest_marker("flaky_e2e"):
            item.add_marker(pytest.mark.flaky(reruns=E2E_RERUNS, reruns_delay=E2E_RERUNS_DELAY))


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

    proc = subprocess.Popen(
        [sys.executable, "nx_main.py"],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        if not _wait_for_http(f"{E2E_BASE_URL}/login", timeout_s=30):
            out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            proc.terminate()
            proc.wait(timeout=5)
            raise RuntimeError(f"nx_main did not become reachable in 30s. Output:\n{out}")
        yield E2E_BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
