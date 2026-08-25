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


class _Resp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status_code=202, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"access_token": "stub-token"}
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture
def graph(monkeypatch):
    """Configure Graph and capture every POST instead of making one.

    Returns the call list: [(url, kwargs), ...] in order -- the token request
    first, then sendMail.
    """
    for name in MAIL_KEYS:
        monkeypatch.setattr(mail, name, f"stub-{name.lower()}", raising=False)

    calls = []

    def _post(url, **kwargs):
        calls.append((url, kwargs))
        return _Resp(202) if "sendMail" in url else _Resp(200)

    monkeypatch.setattr(mail.requests, "post", _post)
    return calls


def test_send_mail_posts_to_graph_with_the_bearer_token(graph):
    """The happy path end to end: acquire a token, then send with it."""
    assert mail.send_mail("someone@example.com", "Subject", "<p>hello</p>") is True

    token_url, _ = graph[0]
    send_url, send_kwargs = graph[1]
    assert "oauth2/v2.0/token" in token_url
    assert send_url.endswith("/me/sendMail")
    assert send_kwargs["headers"]["Authorization"] == "Bearer stub-token"


def test_send_mail_addresses_every_recipient(graph):
    """A list of recipients has to survive into the Graph payload; a bare
    string is normalised to a one-element list."""
    mail.send_mail(["a@example.com", "b@example.com"], "s", "<p>b</p>")
    message = graph[1][1]["json"]["message"]
    assert [r["emailAddress"]["address"] for r in message["toRecipients"]] == [
        "a@example.com",
        "b@example.com",
    ]

    graph.clear()
    mail.send_mail("solo@example.com", "s", "<p>b</p>")
    message = graph[1][1]["json"]["message"]
    assert [r["emailAddress"]["address"] for r in message["toRecipients"]] == ["solo@example.com"]


def test_send_mail_carries_attachments_and_inline_images(graph):
    """Scheduled reports attach a file; the branded mails reference an inline
    logo by content id. Both ride on the same message."""
    mail.send_mail(
        "someone@example.com",
        "s",
        '<p><img src="cid:logo"></p>',
        attachments=[("report.csv", b"a,b\n1,2\n", "text/csv")],
        inline_images=[("logo", b"\x89PNG", "image/png")],
    )
    attachments = graph[1][1]["json"]["message"]["attachments"]
    by_name = {a.get("name") or a.get("contentId"): a for a in attachments}

    assert "report.csv" in by_name, f"attachment missing, got {list(by_name)}"
    inline = [a for a in attachments if a.get("isInline")]
    assert inline, "the inline image was not marked isInline; it renders as an attachment"
    assert inline[0]["contentId"] == "logo", (
        "the inline image's contentId must match the cid: in the HTML body or "
        "the <img> renders broken"
    )


def test_send_mail_raises_when_graph_rejects_the_send(monkeypatch):
    """A non-2xx from sendMail must surface. The scheduled-report runner
    reports delivery based on this return value."""
    for name in MAIL_KEYS:
        monkeypatch.setattr(mail, name, "stub", raising=False)

    def _post(url, **kwargs):
        if "sendMail" in url:
            return _Resp(403, text="Forbidden: mailbox not licensed")
        return _Resp(200)

    monkeypatch.setattr(mail.requests, "post", _post)

    with pytest.raises(mail.MailError, match="403"):
        mail.send_mail("someone@example.com", "s", "<p>b</p>")


def test_send_mail_raises_when_the_token_request_fails(monkeypatch):
    """Bad or expired credentials must fail loudly rather than sending
    unauthenticated."""
    for name in MAIL_KEYS:
        monkeypatch.setattr(mail, name, "stub", raising=False)
    monkeypatch.setattr(
        mail.requests,
        "post",
        lambda url, **kw: _Resp(401, payload={"error": "invalid_grant"}, text="invalid_grant"),
    )

    with pytest.raises(mail.MailError, match="token"):
        mail.send_mail("someone@example.com", "s", "<p>b</p>")


def test_send_mail_does_not_reach_the_network_when_unconfigured(monkeypatch):
    """Belt and braces on the guard above: the tenant check has to happen
    before any HTTP call, so an unconfigured box cannot hit Graph at all."""
    monkeypatch.setattr(mail, "GRAPH_TENANT_ID", None)

    def _explode(*a, **kw):  # pragma: no cover - only runs if the guard fails
        raise AssertionError("send_mail issued an HTTP request while unconfigured")

    monkeypatch.setattr(mail.requests, "post", _explode)

    with pytest.raises(mail.MailError):
        mail.send_mail("someone@example.com", "subject", "<p>body</p>")
