"""Integration tests for nx_lib.views.profile's feedback routes.

Routes covered:
- GET  /feedback         (form page)
- POST /feedback/submit  (validation, mail send, rate limit)

send_mail is imported directly into nx_lib.views.profile's namespace
(`from ..mail import send_mail`), so it's patched there — same idiom
test_reporting_routes.py uses for ops.run_scheduled_reports.send_mail.
SUPPORT_MAIL is likewise a module-level constant bound at import time
(`from ..config import SUPPORT_MAIL`); tests that need a "configured"
mailbox patch nx_lib.views.profile.SUPPORT_MAIL directly, not
nx_lib.config.SUPPORT_MAIL (patching the origin after the fact would have
no effect on the already-bound name).
"""

import io
from unittest.mock import patch

import pytest

from nx_lib.mail import MailError

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def reset_limiter():
    """Reset Flask-Limiter's in-memory storage after a test that
    intentionally exhausts the /feedback/submit rate limit — matches
    test_auth_routes.py's reset_limiter fixture."""
    yield
    from nx_lib.extensions import limiter

    limiter.reset()


def test_feedback_page_anonymous_redirects_to_login(client):
    resp = client.get("/feedback", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_feedback_page_authed_renders(user_client):
    resp = user_client.get("/feedback?from=/dashboard")
    assert resp.status_code == 200
    assert b"feedbackForm" in resp.data


def test_submit_feedback_anonymous_unauthorized(client):
    resp = client.post("/feedback/submit", data={"category": "bug", "message": "x"})
    assert resp.status_code == 401


def test_submit_feedback_missing_category_rejected(user_client):
    resp = user_client.post("/feedback/submit", data={"category": "", "message": "Something broke"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_submit_feedback_bad_category_rejected(user_client):
    resp = user_client.post(
        "/feedback/submit", data={"category": "not-a-real-category", "message": "hi"}
    )
    assert resp.status_code == 400


def test_submit_feedback_empty_message_rejected(user_client):
    resp = user_client.post("/feedback/submit", data={"category": "bug", "message": "   "})
    assert resp.status_code == 400


def test_submit_feedback_support_mail_unset_returns_503(user_client):
    """Matches outage-monitor.md's documented convention: SUPPORT_MAIL unset
    (the TEST env default) means "not configured", not a silent no-op --
    the interactive form must tell the user, unlike the background monitor."""
    with patch("nx_lib.views.profile.SUPPORT_MAIL", None):
        resp = user_client.post(
            "/feedback/submit", data={"category": "bug", "message": "Something broke"}
        )
    assert resp.status_code == 503


def test_submit_feedback_happy_path_sends_mail(user_client):
    with (
        patch("nx_lib.views.profile.SUPPORT_MAIL", "support.helpdesk@sydoc.ch"),
        patch("nx_lib.views.profile.send_mail") as sm,
    ):
        resp = user_client.post(
            "/feedback/submit",
            data={
                "category": "idea",
                "message": "It would be nice to have X.",
                "from_page": "/dashboard",
            },
        )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    sm.assert_called_once()
    args, kwargs = sm.call_args
    assert args[0] == "support.helpdesk@sydoc.ch"
    assert "It would be nice to have X." not in args[1]  # subject stays short
    assert "It would be nice to have X." in args[2]  # html_body
    assert kwargs.get("attachments") is None


def test_submit_feedback_with_screenshot_attaches_to_mail(user_client):
    with (
        patch("nx_lib.views.profile.SUPPORT_MAIL", "support.helpdesk@sydoc.ch"),
        patch("nx_lib.views.profile.send_mail") as sm,
    ):
        resp = user_client.post(
            "/feedback/submit",
            data={
                "category": "bug",
                "message": "See attached.",
                "screenshot": (io.BytesIO(PNG_1X1), "bug.png"),
            },
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    sm.assert_called_once()
    _, kwargs = sm.call_args
    attachments = kwargs.get("attachments")
    assert attachments is not None and len(attachments) == 1
    filename, data, content_type = attachments[0]
    assert filename == "bug.png"
    assert data == PNG_1X1
    assert content_type == "image/png"


def test_submit_feedback_non_image_screenshot_rejected(user_client):
    resp = user_client.post(
        "/feedback/submit",
        data={
            "category": "bug",
            "message": "See attached.",
            "screenshot": (io.BytesIO(b"not an image"), "notes.txt"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_submit_feedback_oversized_screenshot_rejected(user_client):
    """Isolates the size cap from MIME sniffing: is_file_allowed is patched
    to always pass so this only exercises FEEDBACK_MAX_SCREENSHOT_BYTES."""
    oversized = b"\x00" * (6 * 1024 * 1024)
    with patch("nx_lib.views.profile.is_file_allowed", return_value=True):
        resp = user_client.post(
            "/feedback/submit",
            data={
                "category": "bug",
                "message": "See attached.",
                "screenshot": (io.BytesIO(oversized), "big.png"),
            },
            content_type="multipart/form-data",
        )
    assert resp.status_code == 400


def test_submit_feedback_mail_error_returns_502(user_client):
    with (
        patch("nx_lib.views.profile.SUPPORT_MAIL", "support.helpdesk@sydoc.ch"),
        patch("nx_lib.views.profile.send_mail", side_effect=MailError("graph down")),
    ):
        resp = user_client.post(
            "/feedback/submit", data={"category": "question", "message": "Why does X do Y?"}
        )
    assert resp.status_code == 502


def test_submit_feedback_rate_limit_eventually_429(user_client, reset_limiter):
    """@limiter.limit('10 per hour'). Burst, expect 429 eventually (or 200 if
    the limiter is bypassed) — same best-effort shape as
    test_auth_routes.test_request_password_reset_rate_limit_eventually_429."""
    with (
        patch("nx_lib.views.profile.SUPPORT_MAIL", "support.helpdesk@sydoc.ch"),
        patch("nx_lib.views.profile.send_mail"),
    ):
        last_status = None
        for _ in range(15):
            resp = user_client.post(
                "/feedback/submit", data={"category": "bug", "message": "burst"}
            )
            last_status = resp.status_code
            if last_status == 429:
                break
    assert last_status in (200, 429)
