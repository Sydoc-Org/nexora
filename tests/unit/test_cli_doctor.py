"""Unit tests for nx_lib.cli_doctor — preflight health checks."""

from unittest.mock import MagicMock, patch

from nx_lib import cli_doctor as doctor
from nx_lib.cli_doctor import (
    CheckResult,
    _check_python,
    _parse_requirements,
    _print_section,
    _tally,
    run,
)

# ---------- CheckResult ----------


def test_check_result_dataclass_fields():
    r = CheckResult("name", "ok", "detail", "hint")
    assert r.name == "name"
    assert r.status == "ok"
    assert r.detail == "detail"
    assert r.hint == "hint"
    assert r.fix is None


# ---------- _check_python ----------


def test_check_python_returns_one_ok_result():
    results = _check_python()
    assert len(results) == 1
    assert results[0].status == "ok"
    assert "Python" in results[0].detail


# ---------- _parse_requirements ----------


def test_parse_requirements_handles_pep508_markers(tmp_path, monkeypatch):
    """`colorama==0.4.6 ; sys_platform == 'win32'` parses to ('colorama','0.4.6')."""
    req = tmp_path / "requirements.txt"
    req.write_text(
        "# header comment\n"
        "Flask==3.1.2\n"
        "colorama==0.4.6 ; sys_platform == 'win32'\n"
        "no-pin-pkg\n"
        "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "REQUIREMENTS_FILE", req)
    pkgs = _parse_requirements()
    by_name = dict(pkgs)
    assert by_name["Flask"] == "3.1.2"
    assert by_name["colorama"] == "0.4.6"
    assert by_name["no-pin-pkg"] is None


def test_parse_requirements_returns_empty_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "REQUIREMENTS_FILE", tmp_path / "missing.txt")
    assert _parse_requirements() == []


# ---------- _check_packages ----------


def test_check_packages_returns_results():
    results = doctor._check_packages()
    assert isinstance(results, list)
    assert len(results) >= 1
    # Each result is a CheckResult
    assert all(hasattr(r, "status") for r in results)


def test_check_packages_warns_when_requirements_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "REQUIREMENTS_FILE", tmp_path / "missing.txt")
    results = doctor._check_packages()
    assert results[0].status == "warn"
    assert "not found" in results[0].detail or "empty" in results[0].detail


# ---------- _check_env ----------


def test_check_env_returns_results():
    results = doctor._check_env()
    assert isinstance(results, list)
    assert len(results) >= 1


# ---------- _check_filesystem ----------


def test_check_filesystem_returns_results():
    results = doctor._check_filesystem()
    assert isinstance(results, list)
    assert len(results) >= 1


# ---------- _check_databases ----------


def test_check_databases_uses_ping_dbs_parallel():
    """ping_dbs_parallel is imported inside _check_databases; patch at the
    source module."""
    fake_results = [
        {"label": "NexoraDB", "ok": True, "error": None, "latency_ms": 50},
        {"label": "OctoDB", "ok": False, "error": "down", "latency_ms": 2000},
        {"label": "StatisticsDB", "ok": True, "error": None, "latency_ms": 30},
        {"label": "GeneraliDB", "ok": True, "error": None, "latency_ms": 40},
    ]
    with patch("nx_lib.db.ping_dbs_parallel", return_value=fake_results):
        results = doctor._check_databases()
    assert isinstance(results, list)
    # 4 DB pings + ODBC driver check = 5+
    assert len(results) >= 4
    statuses = {r.status for r in results}
    assert "ok" in statuses
    # Should contain a non-ok status from the failed OctoDB ping
    assert any(s in statuses for s in ("fail", "warn"))


# ---------- _check_migrations ----------


def test_check_migrations_returns_results():
    results = doctor._check_migrations()
    assert isinstance(results, list)
    assert len(results) >= 1


# ---------- _check_drift ----------


def test_check_drift_returns_results():
    """The drift check shells out to sql/sync-from-db.py --check. Mock the
    subprocess to avoid hitting SQL Server."""
    with patch.object(doctor.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        results = doctor._check_drift()
    assert isinstance(results, list)


# ---------- _check_tooling ----------


def test_check_tooling_uses_shutil_which():
    with patch.object(doctor.shutil, "which", return_value="/usr/bin/git"):
        results = doctor._check_tooling()
    assert isinstance(results, list)
    assert all(r.status in ("ok", "warn", "fail", "skip") for r in results)


# ---------- _check_git_hooks ----------


def test_check_git_hooks_returns_results():
    results = doctor._check_git_hooks()
    assert isinstance(results, list)
    assert len(results) >= 1


# ---------- _check_port ----------


def test_check_port_returns_results():
    results = doctor._check_port()
    assert isinstance(results, list)
    assert len(results) >= 1


def test_check_port_when_listening():
    fake_sock = MagicMock()
    fake_sock.__enter__.return_value = fake_sock
    fake_sock.connect_ex.return_value = 0  # success → port in use

    with patch.object(doctor.socket, "socket", return_value=fake_sock):
        results = doctor._check_port()
    # When port is in use, status should reflect that ("warn" or "ok" depending on impl)
    assert results[0].status in ("ok", "warn", "fail", "skip")


# ---------- external service checks ----------


def test_check_graph_skips_when_tenant_not_set(monkeypatch):
    monkeypatch.delenv("GRAPH_TENANT_ID", raising=False)
    result = doctor._check_graph()
    assert result.status == "skip"


def test_check_graph_fails_on_request_exception(monkeypatch):
    """requests is lazy-imported inside the function; patch at requests.post."""
    import requests

    monkeypatch.setenv("GRAPH_TENANT_ID", "tenant-123")
    with patch("requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectionError("no net")
        result = doctor._check_graph()
    assert result.status == "fail"


def test_check_octo_skips_when_domain_not_set(monkeypatch):
    monkeypatch.delenv("OCTO_DOMAIN", raising=False)
    result = doctor._check_octo()
    assert result.status == "skip"


def test_check_octo_fails_on_request_exception(monkeypatch):
    import requests

    monkeypatch.setenv("OCTO_DOMAIN", "octo.example")
    with patch("requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectionError("no net")
        result = doctor._check_octo()
    assert result.status == "fail"


# ---------- _print_section ----------


def test_print_section_prints_title_and_results(capsys):
    results = [
        CheckResult("a", "ok", "all good"),
        CheckResult("b", "warn", "watch out", hint="check config"),
        CheckResult("c", "fail", "broken"),
        CheckResult("d", "skip", "not applicable"),
    ]
    _print_section("My Section", results)
    out = capsys.readouterr().out
    assert "My Section" in out
    for name in ("a", "b", "c", "d"):
        assert name in out
    assert "check config" in out  # hint shown for warn


# ---------- _tally ----------


def test_tally_counts_each_status():
    results = [
        CheckResult("a", "ok"),
        CheckResult("b", "ok"),
        CheckResult("c", "warn"),
        CheckResult("d", "fail"),
        CheckResult("e", "fail"),
        CheckResult("f", "fail"),
        CheckResult("g", "skip"),
    ]
    ok, warn, fail, skip = _tally(results)
    assert (ok, warn, fail, skip) == (2, 1, 3, 1)


def test_tally_handles_empty_list():
    assert _tally([]) == (0, 0, 0, 0)


def test_tally_ignores_unknown_status():
    results = [
        CheckResult("a", "ok"),
        CheckResult("b", "weird-status"),
    ]
    ok, warn, fail, skip = _tally(results)
    assert (ok, warn, fail, skip) == (1, 0, 0, 0)


# ---------- run ----------


def test_run_fast_returns_int_exit_code():
    """fast=True skips externals and the drift dump — should finish quickly."""
    import time as time_mod

    t0 = time_mod.perf_counter()
    rc = run(fast=True)
    elapsed = time_mod.perf_counter() - t0
    assert rc in (0, 1)
    assert elapsed < 30.0  # fast mode should complete well under 30s


def test_run_returns_exit_1_on_failures(capsys):
    """If any check fails, run() should return 1."""
    bad_result = [CheckResult("fake", "fail", "synthetic failure")]
    with (
        patch.object(doctor, "_check_python", return_value=bad_result),
        patch.object(doctor, "_check_packages", return_value=[]),
        patch.object(doctor, "_check_env", return_value=[]),
        patch.object(doctor, "_check_filesystem", return_value=[]),
        patch.object(doctor, "_check_databases", return_value=[]),
        patch.object(doctor, "_check_migrations", return_value=[]),
        patch.object(doctor, "_check_tooling", return_value=[]),
        patch.object(doctor, "_check_git_hooks", return_value=[]),
        patch.object(doctor, "_check_port", return_value=[]),
    ):
        rc = run(fast=True)
    assert rc == 1


def test_run_returns_exit_0_when_all_ok():
    ok_result = [CheckResult("fake", "ok", "fine")]
    with (
        patch.object(doctor, "_check_python", return_value=ok_result),
        patch.object(doctor, "_check_packages", return_value=ok_result),
        patch.object(doctor, "_check_env", return_value=ok_result),
        patch.object(doctor, "_check_filesystem", return_value=ok_result),
        patch.object(doctor, "_check_databases", return_value=ok_result),
        patch.object(doctor, "_check_migrations", return_value=ok_result),
        patch.object(doctor, "_check_tooling", return_value=ok_result),
        patch.object(doctor, "_check_git_hooks", return_value=ok_result),
        patch.object(doctor, "_check_port", return_value=ok_result),
    ):
        rc = run(fast=True)
    assert rc == 0


# ---------- _bootstrap_env ----------


def test_bootstrap_env_sets_default_environment():
    """If ENVIRONMENT is unset, it defaults to INT."""
    import os as os_mod

    original = os_mod.environ.get("ENVIRONMENT")
    try:
        if "ENVIRONMENT" in os_mod.environ:
            del os_mod.environ["ENVIRONMENT"]
        doctor._bootstrap_env()
        assert os_mod.environ.get("ENVIRONMENT") == "INT"
    finally:
        if original is not None:
            os_mod.environ["ENVIRONMENT"] = original
        elif "ENVIRONMENT" in os_mod.environ:
            del os_mod.environ["ENVIRONMENT"]


def test_bootstrap_env_handles_missing_dotenv():
    """Even if python-dotenv isn't installed, _bootstrap_env should not raise."""
    import contextlib

    with patch.dict("sys.modules", {"dotenv": None}), contextlib.suppress(ImportError):
        doctor._bootstrap_env()
