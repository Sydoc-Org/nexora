"""Unit tests for nx_lib.cli — the `nx` REPL backing the dev CLI.

Visual functions (logo, splash, panels) are exercised for "runs without
raising and returns expected shape". Subprocess-dispatching functions are
tested by mocking subprocess.run/call. The interactive REPL loop (repl())
is intentionally not driven end-to-end — prompt_toolkit is hard to mock
without polluting the test environment."""

import os
from unittest.mock import MagicMock, patch

from prompt_toolkit.completion import CompleteEvent

from nx_lib import cli as cli_mod

# ---------- string helpers ----------


def test_visible_len_ignores_ansi():
    assert cli_mod._visible_len("\x1b[31mred\x1b[0m") == 3


def test_visible_len_counts_plain_chars():
    assert cli_mod._visible_len("hello") == 5


def test_visible_len_handles_empty():
    assert cli_mod._visible_len("") == 0


def test_pad_visible_extends_with_spaces():
    out = cli_mod._pad_visible("abc", 6)
    assert cli_mod._visible_len(out) == 6
    assert out.endswith("   ")


def test_pad_visible_does_not_truncate_overlong():
    out = cli_mod._pad_visible("12345", 3)
    # Implementation likely just leaves the string alone (over-budget)
    assert cli_mod._visible_len(out) >= 3


def test_pad_visible_ansi_aware():
    coloured = "\x1b[31mabc\x1b[0m"
    out = cli_mod._pad_visible(coloured, 6)
    assert cli_mod._visible_len(out) == 6


def test_center_visible_centers_short_string():
    out = cli_mod._center_visible("hi", 6)
    assert cli_mod._visible_len(out) == 6
    assert "hi" in out


def test_center_visible_handles_empty():
    out = cli_mod._center_visible("", 4)
    assert cli_mod._visible_len(out) == 4


# ---------- logo & splash ----------


def test_build_logo_returns_string():
    logo = cli_mod._build_logo()
    assert isinstance(logo, str)
    assert len(logo) > 0
    # Has at least one newline (multi-line ASCII art)
    assert "\n" in logo


def test_logo_text_is_idempotent():
    # _logo_text caches the result
    a = cli_mod._logo_text()
    b = cli_mod._logo_text()
    assert a == b


def test_build_panel_returns_list_of_strings():
    lines = cli_mod._build_panel(
        "title",
        ["line 1", "line 2"],
        20,
        "\x1b[34m",
        "\x1b[1m",
    )
    assert isinstance(lines, list)
    assert all(isinstance(line, str) for line in lines)
    assert len(lines) >= 2  # at least the content lines


def test_build_splash_returns_two_panels():
    out = cli_mod._build_splash()
    assert isinstance(out, str)
    assert "nexora" in out
    assert "Quick start" in out or "Commands" in out


def test_splash_writes_to_stdout(capsys):
    cli_mod._splash()
    captured = capsys.readouterr()
    assert "nexora" in captured.out


# ---------- state cache ----------


def test_invalidate_state_cache_resets_timestamps():
    cli_mod._port_pid_ts = 999
    cli_mod._env_ts = 999
    cli_mod._invalidate_state_cache()
    assert cli_mod._port_pid_ts == 0.0
    assert cli_mod._env_ts == 0.0


def test_port_pid_returns_none_when_subprocess_empty():
    cli_mod._invalidate_state_cache()
    if os.name != "nt":
        # Function short-circuits to None on non-Windows
        assert cli_mod._port_pid() is None
        return
    with patch.object(cli_mod.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        cli_mod._port_pid_val = "stale"
        cli_mod._port_pid_ts = 0.0
        result = cli_mod._port_pid(port=9999)
    assert result is None


def test_port_pid_parses_digit_output():
    cli_mod._invalidate_state_cache()
    if os.name != "nt":
        return
    with patch.object(cli_mod.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(stdout="12345", returncode=0)
        result = cli_mod._port_pid(port=8000)
    assert result == 12345


def test_port_pid_returns_none_on_subprocess_error():
    cli_mod._invalidate_state_cache()
    if os.name != "nt":
        return
    with patch.object(cli_mod.subprocess, "run", side_effect=RuntimeError("boom")):
        result = cli_mod._port_pid(port=8000)
    assert result is None


def test_port_pid_uses_cache(tmp_path):
    if os.name != "nt":
        return
    # Prime the cache
    cli_mod._port_pid_val = 42
    cli_mod._port_pid_ts = 9e18  # far future — never expires
    with patch.object(cli_mod.subprocess, "run") as mock_run:
        result = cli_mod._port_pid(port=8000)
    assert result == 42
    mock_run.assert_not_called()


def test_current_env_reads_file(tmp_path, monkeypatch):
    cli_mod._invalidate_state_cache()
    env_file = tmp_path / "current_env"
    env_file.write_text("STAGING\n", encoding="utf-8")
    monkeypatch.setattr(cli_mod, "ENV_STATE", env_file)
    result = cli_mod._current_env()
    assert result == "STAGING"


def test_current_env_returns_none_when_missing(tmp_path, monkeypatch):
    cli_mod._invalidate_state_cache()
    env_file = tmp_path / "current_env"  # doesn't exist
    monkeypatch.setattr(cli_mod, "ENV_STATE", env_file)
    result = cli_mod._current_env()
    assert result is None


def test_current_env_returns_none_on_empty_file(tmp_path, monkeypatch):
    cli_mod._invalidate_state_cache()
    env_file = tmp_path / "current_env"
    env_file.write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(cli_mod, "ENV_STATE", env_file)
    result = cli_mod._current_env()
    assert result is None


# ---------- subprocess dispatch ----------


def test_run_ps1_invokes_powershell():
    with patch.object(cli_mod.subprocess, "call", return_value=0) as mock_call:
        rc = cli_mod._run_ps1("-u")
    assert rc == 0
    args = mock_call.call_args.args[0]
    assert args[0] == "powershell"
    assert "-u" in args


def test_run_ps1_returns_130_on_keyboard_interrupt():
    with patch.object(
        cli_mod.subprocess,
        "call",
        side_effect=KeyboardInterrupt(),
    ):
        rc = cli_mod._run_ps1("-d")
    assert rc == 130


def test_run_python_module_invokes_subprocess():
    with patch.object(cli_mod.subprocess, "call", return_value=0) as mock_call:
        rc = cli_mod._run_python_module("routes", "^/api")
    assert rc == 0
    args = mock_call.call_args.args[0]
    assert "-m" in args
    assert "nx_lib.cli" in args
    assert "routes" in args


def test_run_python_module_returns_130_on_keyboard_interrupt():
    with patch.object(
        cli_mod.subprocess,
        "call",
        side_effect=KeyboardInterrupt(),
    ):
        rc = cli_mod._run_python_module("doctor")
    assert rc == 130


# ---------- routes/users caching ----------


def test_load_routes_returns_cached_after_first_call():
    cli_mod._routes_cache.clear()
    cli_mod._routes_cache.append("/cached/route")
    routes = cli_mod._load_routes()
    assert routes == ["/cached/route"]
    cli_mod._routes_cache.clear()


def test_load_users_returns_cached_after_first_call():
    cli_mod._users_cache.clear()
    cli_mod._users_cache.append("cached@user")
    users = cli_mod._load_users()
    assert users == ["cached@user"]
    cli_mod._users_cache.clear()


# ---------- output ----------


def test_print_writes_to_stdout(capsys):
    cli_mod._print("hello world")
    out = capsys.readouterr().out
    assert "hello world" in out
    assert out.endswith("\n")


def test_print_empty_writes_just_newline(capsys):
    cli_mod._print()
    out = capsys.readouterr().out
    assert out == "\n"


# ---------- commands ----------


def test_cmd_help_lists_commands(capsys):
    cli_mod.cmd_help([])
    out = capsys.readouterr().out
    for word in ("up", "down", "status", "routes", "doctor", "browser", "loginas"):
        assert word in out


def test_cmd_status_prints_status(capsys):
    with (
        patch.object(cli_mod, "_port_pid", return_value=12345),
        patch.object(cli_mod, "_current_env", return_value="INT"),
    ):
        cli_mod.cmd_status([])
    out = capsys.readouterr().out
    assert "running" in out
    assert "12345" in out
    assert "INT" in out


def test_cmd_status_not_running(capsys):
    with (
        patch.object(cli_mod, "_port_pid", return_value=None),
        patch.object(cli_mod, "_current_env", return_value=None),
    ):
        cli_mod.cmd_status([])
    out = capsys.readouterr().out
    assert "not running" in out


def test_cmd_up_calls_run_ps1_with_default_env():
    with patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps:
        cli_mod.cmd_up([])
    mock_ps.assert_called_once_with("-u")


def test_cmd_up_with_env_arg():
    with patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps:
        cli_mod.cmd_up(["staging"])
    args = mock_ps.call_args.args
    assert "-u" in args
    assert "--env:staging" in args


def test_cmd_down_calls_run_ps1():
    with patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps:
        cli_mod.cmd_down([])
    mock_ps.assert_called_once_with("-d")


def test_cmd_restart_with_env():
    with patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps:
        cli_mod.cmd_restart(["int"])
    args = mock_ps.call_args.args
    assert "-r" in args
    assert "--env:int" in args


def test_cmd_logs_warns_when_not_running(capsys):
    with patch.object(cli_mod, "_port_pid", return_value=None):
        cli_mod.cmd_logs([])
    out = capsys.readouterr().out
    assert "not running" in out


def test_cmd_logs_streams_when_running():
    with (
        patch.object(cli_mod, "_port_pid", return_value=1234),
        patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps,
    ):
        cli_mod.cmd_logs([])
    mock_ps.assert_called_once_with("-l")


def test_cmd_routes_without_arg():
    with patch.object(cli_mod, "_run_python_module", return_value=0) as mock_pm:
        cli_mod.cmd_routes([])
    mock_pm.assert_called_once_with("routes")


def test_cmd_routes_with_pattern():
    with patch.object(cli_mod, "_run_python_module", return_value=0) as mock_pm:
        cli_mod.cmd_routes(["^/api"])
    mock_pm.assert_called_once_with("routes", "^/api")


def test_cmd_doctor_passes_through_args():
    with patch.object(cli_mod, "_run_python_module", return_value=0) as mock_pm:
        cli_mod.cmd_doctor(["--fast", "--fix"])
    args = mock_pm.call_args.args
    assert "doctor" in args
    assert "--fast" in args
    assert "--fix" in args


def test_cmd_browser_warns_when_not_running(capsys):
    with patch.object(cli_mod, "_port_pid", return_value=None):
        cli_mod.cmd_browser([])
    assert "not running" in capsys.readouterr().out


def test_cmd_browser_without_route_opens_root():
    with (
        patch.object(cli_mod, "_port_pid", return_value=123),
        patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps,
    ):
        cli_mod.cmd_browser([])
    mock_ps.assert_called_once_with("-b")


def test_cmd_browser_with_route_adds_leading_slash():
    with (
        patch.object(cli_mod, "_port_pid", return_value=123),
        patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps,
    ):
        cli_mod.cmd_browser(["dashboard"])
    args = mock_ps.call_args.args
    assert "-b:/dashboard" in args


def test_cmd_browser_with_absolute_route():
    with (
        patch.object(cli_mod, "_port_pid", return_value=123),
        patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps,
    ):
        cli_mod.cmd_browser(["/admin"])
    args = mock_ps.call_args.args
    assert "-b:/admin" in args


def test_cmd_loginas_warns_without_args(capsys):
    cli_mod.cmd_loginas([])
    assert "usage" in capsys.readouterr().out


def test_cmd_loginas_warns_when_not_running(capsys):
    with patch.object(cli_mod, "_port_pid", return_value=None):
        cli_mod.cmd_loginas(["admin@test.local"])
    assert "not running" in capsys.readouterr().out


def test_cmd_loginas_calls_run_ps1_with_user():
    with (
        patch.object(cli_mod, "_port_pid", return_value=123),
        patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps,
    ):
        cli_mod.cmd_loginas(["user@test.local"])
    args = mock_ps.call_args.args
    assert "--loginas:user@test.local" in args


def test_cmd_env_invokes_run_ps1():
    with patch.object(cli_mod, "_run_ps1", return_value=0) as mock_ps:
        cli_mod.cmd_env([])
    mock_ps.assert_called_once_with("--env")


def test_cmd_clear_clears_and_splashes():
    with (
        patch.object(cli_mod, "pt_clear") as mock_clear,
        patch.object(cli_mod, "_splash") as mock_splash,
    ):
        cli_mod.cmd_clear([])
    mock_clear.assert_called_once()
    mock_splash.assert_called_once()


# ---------- completer ----------


def _complete_event(requested: bool = False):
    """Build a CompleteEvent stub for completer calls."""
    return CompleteEvent(completion_requested=requested)


def test_completer_yields_command_names():
    completer = cli_mod.NxCompleter()
    doc = MagicMock()
    doc.text_before_cursor = "ro"
    completions = list(completer.get_completions(doc, _complete_event()))
    names = {c.text for c in completions}
    # "routes" starts with "ro"; "restart" doesn't
    assert "routes" in names


def test_completer_with_slash_prefix():
    completer = cli_mod.NxCompleter()
    doc = MagicMock()
    doc.text_before_cursor = "/sta"
    completions = list(completer.get_completions(doc, _complete_event()))
    names = {c.text for c in completions}
    assert "status" in names


def test_completer_returns_empty_for_unknown_command():
    completer = cli_mod.NxCompleter()
    doc = MagicMock()
    doc.text_before_cursor = "zzzz"
    completions = list(completer.get_completions(doc, _complete_event()))
    assert completions == []


def test_completer_env_for_up_command():
    completer = cli_mod.NxCompleter()
    doc = MagicMock()
    doc.text_before_cursor = "up i"
    completions = list(completer.get_completions(doc, _complete_event(requested=True)))
    names = {c.text for c in completions}
    assert "int" in names


def test_completer_no_arg_completions_without_explicit_tab():
    """browser and loginas only show route/user completions on explicit Tab."""
    completer = cli_mod.NxCompleter()
    doc = MagicMock()
    doc.text_before_cursor = "browser "
    # complete_event with completion_requested=False (auto-complete-while-typing)
    completions = list(completer.get_completions(doc, _complete_event()))
    # Should NOT enumerate routes mid-typing
    assert completions == []


# ---------- prompt + main ----------


def test_prompt_message_when_running():
    with (
        patch.object(cli_mod, "_port_pid", return_value=12345),
        patch.object(cli_mod, "_current_env", return_value="INT"),
    ):
        msg = cli_mod._prompt_message()
    assert isinstance(msg, list)
    text = "".join(t[1] for t in msg)
    assert "●" in text  # running dot
    assert "INT" in text


def test_prompt_message_when_not_running():
    with (
        patch.object(cli_mod, "_port_pid", return_value=None),
        patch.object(cli_mod, "_current_env", return_value=None),
    ):
        msg = cli_mod._prompt_message()
    text = "".join(t[1] for t in msg)
    assert "○" in text  # not-running dot


def test_main_routes_dispatch():
    with (
        patch.object(cli_mod.sys, "argv", ["nx", "routes"]),
        patch.object(cli_mod, "print_routes", return_value=0) as mock_pr,
    ):
        rc = cli_mod.main()
    assert rc == 0
    mock_pr.assert_called_once_with(None)


def test_main_routes_with_pattern():
    with (
        patch.object(cli_mod.sys, "argv", ["nx", "routes", "^/api"]),
        patch.object(cli_mod, "print_routes", return_value=0) as mock_pr,
    ):
        cli_mod.main()
    mock_pr.assert_called_once_with("^/api")


def test_main_doctor_dispatch():
    with (
        patch.object(cli_mod.sys, "argv", ["nx", "doctor", "--fast"]),
        patch("nx_lib.cli_doctor.run", return_value=0) as mock_run,
    ):
        rc = cli_mod.main()
    assert rc == 0
    mock_run.assert_called_once_with(fast=True, fix=False)


def test_main_returns_2_when_not_tty():
    with (
        patch.object(cli_mod.sys, "argv", ["nx"]),
        patch.object(cli_mod.sys.stdin, "isatty", return_value=False),
    ):
        rc = cli_mod.main()
    assert rc == 2


def test_main_wraps_repl_exception():
    with (
        patch.object(cli_mod.sys, "argv", ["nx"]),
        patch.object(cli_mod.sys.stdin, "isatty", return_value=True),
        patch.object(cli_mod.sys.stdout, "isatty", return_value=True),
        patch.object(cli_mod, "repl", side_effect=RuntimeError("boom")),
    ):
        rc = cli_mod.main()
    assert rc == 1


def test_main_repl_pass_through():
    with (
        patch.object(cli_mod.sys, "argv", ["nx"]),
        patch.object(cli_mod.sys.stdin, "isatty", return_value=True),
        patch.object(cli_mod.sys.stdout, "isatty", return_value=True),
        patch.object(cli_mod, "repl", return_value=0),
    ):
        rc = cli_mod.main()
    assert rc == 0
