"""Terms of Service and Privacy Policy pages.

Both are deliberately public. A privacy notice readable only after signing in
cannot inform the decision to sign in, and both are linked from the footer of
the login and 2FA screens, where there is no session to gate on. They render no
user data, so there is nothing for the absent session to protect.
"""


def test_terms_is_reachable_signed_out(client):
    resp = client.get("/terms")
    assert resp.status_code == 200
    assert "Terms of Service" in resp.get_data(as_text=True)


def test_privacy_is_reachable_signed_out(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert "Privacy Policy" in resp.get_data(as_text=True)


def test_both_pages_carry_the_draft_notice(client):
    """The pages ship as a skeleton for legal review. Until someone writes the
    real text, saying so on the page is the difference between an unfinished
    draft and a document that looks binding."""
    for path in ("/terms", "/privacy"):
        body = client.get(path).get_data(as_text=True)
        assert "legal-draft-notice" in body, path
        assert "not yet in force" in body, path


def test_pages_render_no_user_data(client):
    """Public routes: nothing about any account may appear."""
    for path in ("/terms", "/privacy"):
        body = client.get(path).get_data(as_text=True)
        for probe in ("@test.local", "organizationCode", "userid"):
            assert probe not in body, f"{probe} leaked into {path}"


def test_privacy_lists_what_is_actually_stored(client):
    """The factual section was read off the schema; if the schema changes and
    this list does not, the policy becomes wrong rather than merely vague."""
    body = client.get("/privacy").get_data(as_text=True)
    assert "Active sessions" in body
    assert "eight days" in body, "session retention no longer stated"
    assert "Request log" in body


def test_login_page_links_to_both(client):
    """Reachable before signing in is the whole point -- the footer carries them
    on the login screen, not only from inside the app."""
    body = client.get("/login").get_data(as_text=True)
    assert 'data-testid="footer-terms"' in body
    assert 'data-testid="footer-privacy"' in body


def test_pages_survive_a_dark_theme_preference(client):
    """The block is theme-only by design; it must still be present, or a dark
    -mode user gets a white page mid-flow."""
    for path in ("/terms", "/privacy"):
        body = client.get(path).get_data(as_text=True)
        assert "nexora-ui-prefs" in body, path
        assert "prefers-color-scheme" in body, path
