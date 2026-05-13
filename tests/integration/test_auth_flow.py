"""Integration tests for the auth flow — Flask test client against NEXORA_TEST."""


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    # Sanity-check: the response body contains a form
    assert b"<form" in resp.data.lower()


def test_login_valid_creds_and_2fa(client, totp_for):
    # Step 1: post creds — seed users all have InitReset=1 and twoFA=1,
    # so a valid login redirects (302) straight to /verify_2fa.
    resp = client.post(
        "/login",
        data={"username": "user@test.local", "password": "Test1234!"},
        follow_redirects=False,
    )
    assert resp.status_code == 302, f"login redirect failed: {resp.status_code} {resp.data[:200]!r}"
    assert "/verify_2fa" in resp.headers.get("Location", "")

    # Step 2: post the current TOTP code; verify_2fa redirects on success.
    code = totp_for("user@test.local")
    resp = client.post("/verify_2fa", data={"code": code}, follow_redirects=False)
    assert resp.status_code == 302, f"2FA submit failed: {resp.status_code} {resp.data[:200]!r}"

    # Session is now fully populated.
    with client.session_transaction() as sess:
        assert sess.get("username") == "user@test.local"


def test_login_bad_password_rejected(client):
    resp = client.post(
        "/login",
        data={"username": "user@test.local", "password": "wrong-password"},
        follow_redirects=False,
    )
    # /login re-renders index.html with 401 on bad creds.
    assert resp.status_code == 401

    with client.session_transaction() as sess:
        assert "username" not in sess


def test_login_unknown_user_rejected(client):
    resp = client.post(
        "/login",
        data={"username": "nobody@nowhere.local", "password": "anything"},
        follow_redirects=False,
    )
    assert resp.status_code == 401

    with client.session_transaction() as sess:
        assert "username" not in sess
