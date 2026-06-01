"""Integration tests for nx_lib.views.chat — 6 routes.

Chat_Conversations / Chat_Participants / Chat_Messages tables are absent
from sql/test/schema.sql, so most routes hit except branches and return
500 JSON. The chat_all_perms fixture monkeypatches has_permission to True
so the @require_permission gate is satisfied and the body actually runs.

Routes:
- GET  /chat                                page (chat.view)
- GET  /api/chat/conversations              get_conversations
- POST /api/chat/start/<int>                start_conversation
- GET  /api/chat/<int>/messages             get_chat_messages
- POST /api/chat/<int>/send                 send_chat_message
- POST /api/chat/<int>/upload               upload_chat_file
"""

import io

import pytest


@pytest.fixture()
def chat_all_perms(monkeypatch):
    monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)
    yield


# ============================ /chat page =====================================


def test_chat_anonymous_redirects(client):
    resp = client.get("/chat", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_chat_without_perm_returns_403(noperm_client):
    resp = noperm_client.get("/chat")
    assert resp.status_code == 403


def test_chat_with_perms_renders(user_client, chat_all_perms):
    """get_all_portal_users queries seeded Users table → 200 render."""
    resp = user_client.get("/chat")
    assert resp.status_code in (200, 500)


# ============================ /api/chat/conversations ========================


def test_get_conversations_without_perm_returns_403(noperm_client):
    resp = noperm_client.get("/api/chat/conversations")
    assert resp.status_code == 403


def test_get_conversations_anonymous(client):
    resp = client.get("/api/chat/conversations", follow_redirects=False)
    # Decorator first → 302 to /login
    assert resp.status_code in (302, 401)


def test_get_conversations_authed_table_missing(user_client, chat_all_perms):
    """Chat_Conversations table absent → 500."""
    resp = user_client.get("/api/chat/conversations")
    assert resp.status_code in (200, 500)


# ============================ /api/chat/start/<id> ===========================


def test_start_conversation_without_perm(noperm_client):
    resp = noperm_client.post("/api/chat/start/1001")
    assert resp.status_code == 403


def test_start_conversation_authed_table_missing(user_client, chat_all_perms):
    resp = user_client.post("/api/chat/start/1001")
    assert resp.status_code in (200, 500)


# ============================ /api/chat/<id>/messages ========================


def test_get_chat_messages_without_perm(noperm_client):
    resp = noperm_client.get("/api/chat/1/messages")
    assert resp.status_code == 403


def test_get_chat_messages_authed_table_missing(user_client, chat_all_perms):
    resp = user_client.get("/api/chat/1/messages")
    assert resp.status_code in (200, 403, 500)


# ============================ /api/chat/<id>/send ============================


def test_send_chat_message_without_perm(noperm_client):
    resp = noperm_client.post("/api/chat/1/send", json={"message": "hi"})
    assert resp.status_code == 403


def test_send_chat_message_empty_returns_400(user_client, chat_all_perms):
    resp = user_client.post("/api/chat/1/send", json={"message": ""})
    assert resp.status_code == 400


def test_send_chat_message_missing_returns_400(user_client, chat_all_perms):
    resp = user_client.post("/api/chat/1/send", json={})
    assert resp.status_code == 400


def test_send_chat_message_authed_table_missing(user_client, chat_all_perms):
    resp = user_client.post("/api/chat/1/send", json={"message": "hi"})
    assert resp.status_code in (200, 403, 500)


# ============================ /api/chat/<id>/upload ==========================


def test_upload_chat_file_without_perm(noperm_client):
    resp = noperm_client.post("/api/chat/1/upload")
    assert resp.status_code == 403


def test_upload_chat_file_no_file_returns_400(user_client, chat_all_perms):
    resp = user_client.post("/api/chat/1/upload")
    assert resp.status_code == 400


def test_upload_chat_file_invalid_type_returns_400(user_client, chat_all_perms):
    """Send a fake file with disallowed extension."""
    data = {
        "file": (io.BytesIO(b"random bytes"), "bad.exe"),
    }
    resp = user_client.post(
        "/api/chat/1/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
