"""Microsoft Graph mail sender (reused by the scheduled-report runner).

Acquires a token via the ROPC flow with the same GRAPH_* credentials the
password-reset mail uses, then POSTs to /me/sendMail with optional base64
attachments. Kept dependency-light so the Task-Scheduler runner can import it.
"""

import base64

import requests

from .config import (
    GRAPH_CLIENT_ID,
    GRAPH_CLIENT_SECRET,
    GRAPH_PASSWORD,
    GRAPH_TENANT_ID,
    GRAPH_USERNAME,
)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"


class MailError(RuntimeError):
    """Raised when a Graph token or sendMail call fails."""


def _acquire_token():
    if not GRAPH_TENANT_ID:
        raise MailError("Graph is not configured (GRAPH_TENANT_ID unset)")
    resp = requests.post(
        _TOKEN_URL.format(tenant=GRAPH_TENANT_ID),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": GRAPH_CLIENT_ID,
            "username": GRAPH_USERNAME,
            "password": GRAPH_PASSWORD,
            "grant_type": "password",
            "scope": "Mail.Send",
            "client_secret": GRAPH_CLIENT_SECRET,
        },
        timeout=15,
    )
    try:
        return resp.json()["access_token"]
    except Exception as e:
        raise MailError(f"Graph token error: {resp.status_code} {resp.text[:200]}") from e


def _build_message(to, subject, html_body, attachments=None, inline_images=None):
    """Build the Graph sendMail message dict.

    attachments: [(filename, bytes, content_type)] — regular file attachments.
    inline_images: [(content_id, bytes, content_type)] — referenced from the
        HTML body as <img src="cid:content_id">.
    """
    if isinstance(to, str):
        to = [to]
    message = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html_body},
        "toRecipients": [{"emailAddress": {"address": a}} for a in to],
    }
    entries = []
    for name, data, content_type in attachments or []:
        entries.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentType": content_type,
                "contentBytes": base64.b64encode(data).decode("ascii"),
            }
        )
    for cid, data, content_type in inline_images or []:
        entries.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": cid,
                "contentType": content_type,
                "contentBytes": base64.b64encode(data).decode("ascii"),
                "isInline": True,
                "contentId": cid,
            }
        )
    if entries:
        message["attachments"] = entries
    return message


def send_mail(to, subject, html_body, attachments=None, inline_images=None):
    """Send an HTML mail with optional attachments and inline images.

    to: an address or list of addresses. attachments: list of
    (filename, bytes, content_type). inline_images: list of
    (content_id, bytes, content_type), shown via <img src="cid:...">.
    Raises MailError on failure.
    """
    token = _acquire_token()
    message = _build_message(to, subject, html_body, attachments, inline_images)
    resp = requests.post(
        _SENDMAIL_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"message": message, "saveToSentItems": False},
        timeout=30,
    )
    if resp.status_code >= 300:
        raise MailError(f"Graph sendMail failed: {resp.status_code} {resp.text[:200]}")
    return True
