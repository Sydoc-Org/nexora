"""Guards for where the Graph mail sender gets its credentials.

`nx_lib/mail.py` binds GRAPH_* at import time from `nx_lib.config`, which in
turn resolves `env/{ENVIRONMENT}.env`. That indirection is easy to get wrong in
a way nothing notices until a mail goes out from the wrong mailbox -- or does
not go out at all, because the key was only ever added to the committed
`.example` and never to the server's real file (see `scripts/env-sync.py`).

These tests use tmp files and monkeypatched module attributes rather than the
real `env/*.env`, so they run in CI where those secret files do not exist.
"""

import pytest

from nx_lib import mail
from nx_lib.config import _load_env_files

# Everything nx_lib/mail.py imports from config, plus the recipient the outage
# monitor mails. A new mail-related key belongs in this list and in every
# env/*.env.example at the same time.
MAIL_KEYS = (
    "GRAPH_TENANT_ID",
    "GRAPH_CLIENT_ID",
    "GRAPH_USERNAME",
    "GRAPH_PASSWORD",
    "GRAPH_CLIENT_SECRET",
)


def _write(path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")


def test_mail_credentials_come_from_the_selected_environment(tmp_path, monkeypatch):
    """The whole point of ENVIRONMENT: INT must not pick up PROD's mailbox
    because the root .env happened to define one."""
    _write(tmp_path / "env" / "INT.env", GRAPH_USERNAME="int-mailbox")
    _write(tmp_path / ".env", GRAPH_USERNAME="root-fallback-mailbox")

    for key in MAIL_KEYS:
        monkeypatch.delenv(key, raising=False)
    _load_env_files(tmp_path, "INT")

    import os

    assert os.environ["GRAPH_USERNAME"] == "int-mailbox", (
        "the env-specific file lost to the root .env; mail would be sent from "
        "whatever mailbox the fallback names"
    )


def test_process_environment_still_overrides_the_env_file(tmp_path, monkeypatch):
    """Operators override a single key on the box (or in a Task Scheduler
    action) without editing the file. That has to keep working for mail, since
    it is how a one-off run is pointed at a different mailbox."""
    _write(tmp_path / "env" / "INT.env", GRAPH_USERNAME="from-file")
    monkeypatch.setenv("GRAPH_USERNAME", "from-process-env")

    _load_env_files(tmp_path, "INT")

    import os

    assert os.environ["GRAPH_USERNAME"] == "from-process-env"


@pytest.mark.parametrize("env_name", ["INT", "PROD", "STAGING", "TEST"])
def test_every_environment_example_declares_the_mail_keys(env_name):
    """`env-sync.py` diffs the server's real file against the committed
    `.example`, so a key missing from the example is invisible to it -- the
    server silently lacks it and mail fails at runtime with an unset-credential
    error. The example is the authoritative key list; keep it complete."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "env" / f"{env_name}.env.example"
    declared = {
        line.split("=", 1)[0].strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = [k for k in MAIL_KEYS if k not in declared]
    assert not missing, (
        f"{example.name} does not declare {missing}; env-sync.py cannot warn "
        f"when the server is missing them and mail will fail at send time"
    )


def test_sending_without_graph_configured_fails_loudly(monkeypatch):
    """An unconfigured environment must raise, not quietly return success --
    a silent no-op would let a scheduled report report itself as delivered."""
    monkeypatch.setattr(mail, "GRAPH_TENANT_ID", None)

    with pytest.raises(mail.MailError, match="not configured"):
        mail.send_mail("someone@example.com", "subject", "<p>body</p>")


def test_send_mail_does_not_reach_the_network_when_unconfigured(monkeypatch):
    """Belt and braces on the guard above: the tenant check has to happen
    before any HTTP call, so an unconfigured box cannot hit Graph at all."""
    monkeypatch.setattr(mail, "GRAPH_TENANT_ID", None)

    def _explode(*a, **kw):  # pragma: no cover - only runs if the guard fails
        raise AssertionError("send_mail issued an HTTP request while unconfigured")

    monkeypatch.setattr(mail.requests, "post", _explode)

    with pytest.raises(mail.MailError):
        mail.send_mail("someone@example.com", "subject", "<p>body</p>")
