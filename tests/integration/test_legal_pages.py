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
    assert "Request log" in body


def test_privacy_retention_matches_what_the_code_deletes(client):
    """The retention periods on the page are promises. They must be the ones
    the prune jobs actually apply (ops/cleanup/prune_request_log.py,
    prune_active_sessions.py), in both language versions -- change the config
    and this fails until the text follows."""
    from nx_lib.config import REQUEST_LOG_RETENTION, SESSION_LIFETIME, SESSION_ROW_RETENTION_GRACE

    log_days = REQUEST_LOG_RETENTION.days
    session_days = (SESSION_LIFETIME + SESSION_ROW_RETENTION_GRACE).days
    de = client.get("/privacy?lang=de").get_data(as_text=True)
    en = client.get("/privacy?lang=en").get_data(as_text=True)
    assert f"Zugriffsprotokoll: {log_days} Tage" in de
    assert f"IP-Adresse: {session_days} Tage" in de
    assert f"Request log: {log_days} days" in en
    assert f"IP address: {session_days} days" in en


def test_legal_text_is_german_or_english_and_says_which_is_authoritative(client):
    """German (authoritative) and English only, decided 2026-09-24."""
    de = client.get("/terms?lang=de").get_data(as_text=True)
    en = client.get("/terms?lang=en").get_data(as_text=True)
    assert "Massgebend ist diese deutsche Fassung" in de and "Geltungsbereich" in de
    assert "The German version is authoritative" in en and "Scope" in en
    assert 'data-testid="legal-switch-en"' in de and 'data-testid="legal-switch-de"' in en


def test_legal_text_follows_the_ui_language_by_default(client):
    with client.session_transaction() as sess:
        sess["locale"] = "de"
    assert "Massgebend ist diese deutsche Fassung" in client.get("/privacy").get_data(as_text=True)
    with client.session_transaction() as sess:
        sess["locale"] = "fr"
    assert "The German version is authoritative" in client.get("/privacy").get_data(as_text=True)


def test_privacy_names_the_controller_and_the_contact(client):
    for lang in ("de", "en"):
        body = client.get(f"/privacy?lang={lang}").get_data(as_text=True)
        assert "Sydoc AG" in body and "CHE-112.467.492" in body and "6340 Baar" in body, lang
        assert "privacy@sydoc.ch" in body, lang
        # revDSG: a request for information is answered within 30 days.
        assert "30" in body, lang


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


def test_user_menu_puts_terms_and_privacy_under_help(user_client):
    """Management asked for them under Help in the profile menu (2026-09-24)."""
    body = user_client.get("/profile").get_data(as_text=True)
    help_at = body.index('data-testid="header-help-link"')
    assert (
        help_at
        < body.index('data-testid="header-terms-link"')
        < body.index('data-testid="header-privacy-link"')
    )


def test_draft_pages_are_off_on_prod(client, monkeypatch):
    """Draft until management signs it off: live on dev and staging for
    review, 404 on PROD with the menu and footer links hidden (#260)."""
    import nx_lib.config as config

    monkeypatch.setattr(config, "LEGAL_PAGES_LIVE", False)
    assert client.get("/terms").status_code == 404
    assert client.get("/privacy").status_code == 404
    body = client.get("/login").get_data(as_text=True)
    assert 'data-testid="footer-terms"' not in body
    assert 'data-testid="footer-privacy"' not in body
