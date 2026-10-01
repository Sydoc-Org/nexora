"""Staging and INT keep a login "forever" (#437, IP-restricted at the ngrok
edge); PROD and TEST keep 24 hours, which the PROD cleanup jobs depend on.

Evaluated in a subprocess, like test_is_prod_flag.py: nx_lib.config is
import-time state."""

import os
import subprocess
import sys
from datetime import timedelta

import pytest


def _lifetime_for(value):
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import nx_lib.config as c; print(c.SESSION_LIFETIME.total_seconds())",
        ],
        env={**os.environ, "ENVIRONMENT": value},
        capture_output=True,
        text=True,
        check=True,
    )
    return timedelta(seconds=float(out.stdout.strip()))


@pytest.mark.parametrize("value", ["INT", "STAGING"])
def test_staging_and_int_sessions_are_long_lived(value):
    assert _lifetime_for(value) >= timedelta(days=3650)


@pytest.mark.parametrize("value", ["PROD", "TEST"])
def test_prod_and_test_keep_24_hours(value):
    assert _lifetime_for(value) == timedelta(hours=24)
