"""Tests for scripts/env-sync.py's three-way comparison.

The point of the script is catching a key that the repo declares but the server
never got (the SUPPORT_MAIL / issue #166 case), so that is what these pin down.

The second half is about *not* crying wolf (#313). The same alarm used to fire
on 11 keys that all had a code default equal to what the example ships, so
their absence from the server changed nothing. An alarm wrong 11 times out of
11 gets skimmed past, and then the real one is missed too -- which is what
happened while diagnosing #297. So the classification, and the conservative
rules behind it, are pinned here.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "env-sync.py"


@pytest.fixture(scope="module")
def env_sync():
    """Import the hyphenated script by path — it is not an importable module name."""
    spec = importlib.util.spec_from_file_location("env_sync", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_key_declared_in_example_but_absent_on_server_is_flagged(env_sync):
    """The whole reason the script exists."""
    f = env_sync.diff_envs(
        example={"DB_UID": "x", "SUPPORT_MAIL": "support@sydoc.ch"},
        local={"DB_UID": "x", "SUPPORT_MAIL": "a@b.ch"},
        remote={"DB_UID": "x"},
    )
    assert f["missing_on_server"] == ["SUPPORT_MAIL"]


def test_blank_example_default_is_opt_in_not_a_missing_key(env_sync):
    """`ANTHROPIC_API_KEY=` absent on the server is normal, not the deploy bug.

    Without this split the one line that matters drowns in twenty that do not.
    """
    f = env_sync.diff_envs(
        example={"ANTHROPIC_API_KEY": "", "SUPPORT_MAIL": "support@sydoc.ch"},
        local={},
        remote={},
    )
    assert f["missing_on_server"] == ["SUPPORT_MAIL"]
    assert f["missing_on_server_optional"] == ["ANTHROPIC_API_KEY"]


def test_whitespace_only_example_default_counts_as_opt_in(env_sync):
    f = env_sync.diff_envs(example={"K": "   "}, local={}, remote={})
    assert f["missing_on_server"] == []
    assert f["missing_on_server_optional"] == ["K"]


def test_differing_values_are_reported_but_are_not_the_deploy_bug(env_sync):
    """Dev and PROD legitimately hold different secrets, and PROD lags dev until
    its deploy lands — so a value difference is shown, never treated as missing."""
    f = env_sync.diff_envs(
        example={"DB_PWD": ""}, local={"DB_PWD": "new"}, remote={"DB_PWD": "old"}
    )
    assert f["value_differs"] == ["DB_PWD"]
    assert f["missing_on_server"] == []


def test_identical_files_report_nothing(env_sync):
    same = {"A": "1", "B": "2"}
    f = env_sync.diff_envs(example=same, local=dict(same), remote=dict(same))
    assert not any(f.values())


def test_server_only_key_is_reported_not_silently_dropped(env_sync):
    """Server-only values are why --push is dangerous; they must be visible."""
    f = env_sync.diff_envs(example={"A": ""}, local={"A": "1"}, remote={"A": "1", "LEGACY": "z"})
    assert f["undeclared_on_server"] == ["LEGACY"]


def test_absent_server_file_does_not_invent_findings(env_sync):
    f = env_sync.diff_envs(example={"A": ""}, local={"A": "1"}, remote=None)
    assert f["missing_on_server"] == []
    assert f["undeclared_on_server"] == []


def test_fingerprint_never_leaks_the_secret(env_sync):
    secret = "hunter2-super-secret"
    fp = env_sync.fingerprint(secret)
    assert secret not in fp
    assert fp.startswith("#")


def test_fingerprints_differ_for_different_secrets(env_sync):
    assert env_sync.fingerprint("a") != env_sync.fingerprint("b")


def test_fingerprint_distinguishes_empty_from_missing(env_sync):
    """'set but blank' and 'not present' are different problems."""
    assert env_sync.fingerprint("") != env_sync.fingerprint(None)


def test_read_env_returns_none_for_missing_file(env_sync, tmp_path):
    assert env_sync.read_env(tmp_path / "nope.env") is None


def test_read_env_parses_a_real_file(env_sync, tmp_path):
    p = tmp_path / "x.env"
    p.write_text("# comment\nA=1\nB=two words\n", encoding="utf-8")
    assert env_sync.read_env(p) == {"A": "1", "B": "two words"}


# --------------------------------------------------------------------------
# #313: a missing key only matters when the code has no default for it.
# --------------------------------------------------------------------------


def test_missing_key_with_no_code_default_is_still_actionable(env_sync):
    """The SUPPORT_MAIL case must survive the fix -- this is the whole point of
    the script, and #313 only narrows what counts, never widens it."""
    f = env_sync.diff_envs(
        example={"SUPPORT_MAIL": "support@sydoc.ch"},
        local={"SUPPORT_MAIL": "support@sydoc.ch"},
        remote={},
        defaults={"OUTAGE_SITE_URL": "https://x/"},
    )
    assert f["missing_on_server"] == ["SUPPORT_MAIL"]
    assert f["missing_on_server_defaulted"] == []


def test_missing_key_defaulted_to_the_example_value_is_not_actionable(env_sync):
    """The 11 false positives. The server behaves identically without the key,
    so calling it ACTION NEEDED is simply untrue."""
    f = env_sync.diff_envs(
        example={"OUTAGE_SITE_URL": "https://nexora.sydoc.ch/nexora/"},
        local={},
        remote={},
        defaults={"OUTAGE_SITE_URL": "https://nexora.sydoc.ch/nexora/"},
    )
    assert f["missing_on_server"] == []
    assert f["missing_on_server_defaulted"] == ["OUTAGE_SITE_URL"]
    assert f["missing_on_server_default_differs"] == []


def test_a_default_that_contradicts_the_example_is_its_own_warning(env_sync):
    """Not noise: PROD runs on the code default while the repo advertises
    something else. Someone has to reconcile the two."""
    f = env_sync.diff_envs(
        example={"AI_TIMEOUT_S": "120"},
        local={},
        remote={},
        defaults={"AI_TIMEOUT_S": 90},
    )
    assert f["missing_on_server"] == []
    assert f["missing_on_server_defaulted"] == []
    assert f["missing_on_server_default_differs"] == ["AI_TIMEOUT_S"]


def test_numeric_and_string_defaults_compare_equal(env_sync):
    """`AI_AGENT_BUDGET_S` defaults to the int 180; the example ships the text
    "180". Those are the same setting and must not be reported as a conflict."""
    f = env_sync.diff_envs(
        example={"AI_AGENT_BUDGET_S": "180"},
        local={},
        remote={},
        defaults={"AI_AGENT_BUDGET_S": 180},
    )
    assert f["missing_on_server_defaulted"] == ["AI_AGENT_BUDGET_S"]


def test_omitting_defaults_keeps_the_old_behaviour(env_sync):
    """Callers that pass no defaults get exactly what they got before, so the
    pure function stays usable without a repo to scan."""
    f = env_sync.diff_envs(example={"OUTAGE_SITE_URL": "https://x/"}, local={}, remote={})
    assert f["missing_on_server"] == ["OUTAGE_SITE_URL"]


# --------------------------------------------------------------------------
# Alias defaults: MS02_STATS_DB_PORT falls back to MS02_DB_PORT.
# --------------------------------------------------------------------------


def test_alias_default_follows_the_base_keys_own_default(env_sync):
    defaults = {
        "MS02_STATS_DB_PORT": ("alias", "MS02_DB_PORT"),
        "MS02_DB_PORT": "5432",
    }
    assert env_sync.resolve_default("MS02_STATS_DB_PORT", defaults, {}) == "5432"


def test_alias_default_prefers_what_the_server_actually_sets(env_sync):
    """Resolving to the literal would be wrong the moment somebody sets the base
    key on the server: the derived key inherits *that*, not the source default.
    """
    defaults = {
        "MS02_STATS_DB_PORT": ("alias", "MS02_DB_PORT"),
        "MS02_DB_PORT": "5432",
    }
    resolved = env_sync.resolve_default("MS02_STATS_DB_PORT", defaults, {"MS02_DB_PORT": "6000"})
    assert resolved == "6000"


def test_alias_cycle_terminates(env_sync):
    """Defensive: a mutual fallback must not hang the script."""
    defaults = {"A": ("alias", "B"), "B": ("alias", "A")}
    assert env_sync.resolve_default("A", defaults, {}) is None


# --------------------------------------------------------------------------
# The source scan itself. Reading this wrong in the permissive direction would
# silence a real alarm, so the conservative cases matter most.
# --------------------------------------------------------------------------


def test_scan_reads_a_plain_default(env_sync):
    found = env_sync._defaults_in_source('import os\nX = os.environ.get("K", "v")\n', "t.py")
    assert found["K"] == ["v"]


def test_scan_reads_the_or_idiom(env_sync):
    """`os.environ.get("K") or 120` passes no default argument but plainly has
    one -- three of the eleven keys are written this way."""
    found = env_sync._defaults_in_source('import os\nX = int(os.environ.get("K") or 120)\n', "t.py")
    assert found["K"] == [120]


def test_scan_treats_a_bare_read_as_having_no_default(env_sync):
    found = env_sync._defaults_in_source('import os\nX = os.environ.get("K")\n', "t.py")
    assert found["K"] == [env_sync.NO_DEFAULT]


def test_scan_treats_subscript_access_as_having_no_default(env_sync):
    """`os.environ["K"]` raises when the key is absent, so the key is required
    by definition."""
    found = env_sync._defaults_in_source('import os\nX = os.environ["K"]\n', "t.py")
    assert found["K"] == [env_sync.NO_DEFAULT]


def test_scan_handles_getenv_too(env_sync):
    found = env_sync._defaults_in_source('import os\nX = os.getenv("K", "v")\n', "t.py")
    assert found["K"] == ["v"]


def test_a_key_read_once_without_a_default_is_not_defaulted(env_sync, tmp_path):
    """The conservative rule. One call site passing no default still gets None,
    so the key genuinely matters even though another site defaults it. Getting
    this backwards would silence a real missing-key bug."""
    (tmp_path / "nx_lib").mkdir()
    (tmp_path / "nx_lib" / "a.py").write_text(
        'import os\nX = os.environ.get("K", "v")\n', encoding="utf-8"
    )
    (tmp_path / "nx_lib" / "b.py").write_text(
        'import os\nY = os.environ.get("K")\n', encoding="utf-8"
    )
    assert "K" not in env_sync.code_defaults(tmp_path)


def test_conflicting_defaults_are_not_treated_as_defaulted(env_sync, tmp_path):
    """Two different fallbacks for one key means the effective value depends on
    which module ran -- ambiguous is not safe to wave through."""
    (tmp_path / "nx_lib").mkdir()
    (tmp_path / "nx_lib" / "a.py").write_text(
        'import os\nX = os.environ.get("K", "one")\n', encoding="utf-8"
    )
    (tmp_path / "nx_lib" / "b.py").write_text(
        'import os\nY = os.environ.get("K", "two")\n', encoding="utf-8"
    )
    assert "K" not in env_sync.code_defaults(tmp_path)


def test_a_file_that_does_not_parse_does_not_break_the_scan(env_sync, tmp_path):
    (tmp_path / "nx_lib").mkdir()
    (tmp_path / "nx_lib" / "broken.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / "nx_lib" / "ok.py").write_text(
        'import os\nX = os.environ.get("K", "v")\n', encoding="utf-8"
    )
    assert env_sync.code_defaults(tmp_path)["K"] == "v"


# --------------------------------------------------------------------------
# Against the real repository -- the claim the issue actually makes.
# --------------------------------------------------------------------------

# Every key #313 listed, with the value env/PROD.env.example ships for it.
ELEVEN_FALSE_POSITIVES = (
    "AI_AGENT_BUDGET_S",
    "AI_DAILY_LIMIT",
    "AI_TIMEOUT_S",
    "AZURE_OPENAI_API_VERSION",
    "DB_ODBC_DRIVER",
    "MS02_DB_PORT",
    "MS02_DB_SSLMODE",
    "MS02_DOCFIELDS_DB_PORT",
    "MS02_STATS_DB_NAME",
    "MS02_STATS_DB_PORT",
    "OUTAGE_SITE_URL",
)


def test_every_key_the_issue_listed_is_detected_as_defaulted(env_sync):
    """If a scan regression drops one of these, the false alarm comes straight
    back -- and silently, because the output merely gets louder again."""
    defaults = env_sync.code_defaults()
    missing = [k for k in ELEVEN_FALSE_POSITIVES if k not in defaults]
    assert not missing, f"no code default found for {missing}"


def test_the_detected_defaults_match_what_the_example_ships(env_sync):
    """The classification only lands in the quiet bucket when the two agree, so
    pin the agreement rather than trusting the bucket."""
    example = env_sync.read_env(env_sync.LOCAL_ENV_DIR / "PROD.env.example")
    assert example, "env/PROD.env.example is missing"
    defaults = env_sync.code_defaults()
    for key in ELEVEN_FALSE_POSITIVES:
        resolved = env_sync.resolve_default(key, defaults, {})
        assert resolved is not None, f"{key} resolved to nothing"
        assert resolved.strip() == str(example.get(key) or "").strip(), (
            f"{key}: code falls back to {resolved!r} but the example ships "
            f"{example.get(key)!r} -- one of the two has drifted"
        )


def test_keys_that_carry_real_credentials_are_never_defaulted(env_sync):
    """A secret must never look defaulted, or its absence stops being reported.
    These are exactly the keys whose absence breaks production silently."""
    defaults = env_sync.code_defaults()
    for key in ("DB_UID", "DB_PWD", "FLASK_SECRET_KEY", "SUPPORT_MAIL"):
        assert key not in defaults, f"{key} looks defaulted -- it must stay actionable"
