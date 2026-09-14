"""IS_PROD must be true for STAGING too: staging is a public, prod-shaped host
(CSP, /nexora prefix, filesystem sessions, /dev/* lockout) -- #338.

Evaluated in a subprocess: nx_lib.config is import-time state and reimporting
it in-process would upset the rest of the suite."""

import os
import subprocess
import sys

import pytest


def _is_prod_for(value):
    out = subprocess.run(
        [sys.executable, "-c", "import nx_lib.config as c; print(c.IS_PROD)"],
        env={**os.environ, "ENVIRONMENT": value},
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip() == "True"


@pytest.mark.parametrize("value", ["PROD", "STAGING"])
def test_prod_and_staging_are_prod_shaped(value):
    assert _is_prod_for(value) is True


@pytest.mark.parametrize("value", ["INT", "TEST"])
def test_int_and_test_are_not(value):
    assert _is_prod_for(value) is False
