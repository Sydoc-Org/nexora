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
        assert "support.helpdesk@sydoc.ch" in body, lang
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


def test_privacy_covers_sensitive_data_transfers_abroad_and_cookies(client):
    """The gaps found in review (2026-09-24): health data in insurance
    documents, disclosure to the USA (ngrok, the font/script CDNs), and the
    sign-in cookie -- in both language versions."""
    de = client.get("/privacy?lang=de").get_data(as_text=True)
    en = client.get("/privacy?lang=en").get_data(as_text=True)
    for needle in (
        "Besonders schützenswerte",
        "Gesundheitsangaben",
        "USA",
        "Google Fonts",
        "Cookies und Speicher im Browser",
        "Data Privacy Framework",
    ):
        assert needle in de, needle
    for needle in (
        "Sensitive data",
        "health information",
        "USA",
        "Google Fonts",
        "Cookies and browser storage",
        "Data Privacy Framework",
    ):
        assert needle in en, needle


def test_privacy_describes_the_request_log_as_the_code_writes_it(client):
    """Review 2026-09-29: the log row carries the IP address, the session id and
    the query parameters (nx_lib/hooks.py), and free-text search values are
    redacted before they are written. The page has to say both, in both
    languages -- and the redaction it promises has to exist."""
    from nx_lib.hooks import LOG_REDACTED_ARGS

    assert {"search", "q", "docvalue"} <= LOG_REDACTED_ARGS
    de = client.get("/privacy?lang=de").get_data(as_text=True)
    en = client.get("/privacy?lang=en").get_data(as_text=True)
    de_log = de[de.index("Zugriffsprotokoll: für jeden") :].split("</li>")[0]
    en_log = en[en.index("Request log: for each") :].split("</li>")[0]
    assert "IP-Adresse" in de_log and "Sitzungskennung" in de_log and "Suchbegriffe" in de_log
    assert "IP address" in en_log and "session identifier" in en_log and "Search terms" in en_log


def test_privacy_names_every_third_party_host_the_pages_load(client):
    """Every CDN a page loads receives the visitor's IP address. Tailwind now
    comes from jsDelivr on every page, so Tailwind Labs is no recipient and
    must not be named as one (2026-09-29)."""
    body = client.get("/privacy").get_data(as_text=True)
    assert "cdn.jsdelivr.net/npm/@tailwindcss/browser" in body
    assert "cdn.tailwindcss.com" not in body
    for lang in ("de", "en"):
        text = client.get(f"/privacy?lang={lang}").get_data(as_text=True)
        for provider in ("Google Fonts", "cdnjs", "jsDelivr"):
            assert provider in text, (lang, provider)
        assert "Tailwind Labs" not in text, lang


def test_privacy_mentions_the_data_it_used_to_leave_out(client):
    """Profile picture, last sign-in, failed-attempt lock and feedback mail are
    all stored or sent; the inventory lists them."""
    de = client.get("/privacy?lang=de").get_data(as_text=True)
    en = client.get("/privacy?lang=en").get_data(as_text=True)
    for needle in (
        "Profilbild",
        "letzten Anmeldung",
        "fehlgeschlagener Anmeldeversuche",
        "Feedback-Formular",
    ):
        assert needle in de, needle
    for needle in ("profile picture", "last sign-in", "failed sign-in attempts", "feedback form"):
        assert needle in en, needle


def test_privacy_names_the_ai_provider_and_the_transfer_bases(client):
    """Answers of 2026-09-29: the assistant runs on Anthropic's Claude; the page
    names it and says what each US transfer relies on (Swiss-U.S. DPF for
    Google, Cloudflare and ngrok -- checked on their own pages that day)."""
    de = client.get("/privacy?lang=de").get_data(as_text=True)
    en = client.get("/privacy?lang=en").get_data(as_text=True)
    for body in (de, en):
        assert "Anthropic" in body and "Claude" in body
        assert "Swiss-U.S. Data Privacy Framework" in body
    assert "eigenen Servern von Sydoc in der Schweiz" in de
    assert "Sydoc's own servers in Switzerland" in en


def test_legal_text_keeps_paragraph_spacing_and_bullets(client):
    """The Tailwind preflight zeroes both; the page puts them back."""
    body = client.get("/privacy").get_data(as_text=True)
    assert ".legal-text p { margin:" in body
    assert "list-style: disc" in body


def test_draft_pages_ask_not_to_be_indexed(client):
    """Dev and staging are on the internet; an unapproved legal text should not
    turn up in a search engine under Sydoc's name."""
    for path in ("/terms", "/privacy"):
        assert '<meta name="robots" content="noindex">' in client.get(path).get_data(
            as_text=True
        ), path


def test_terms_name_the_court_of_the_seat(client):
    """Baar has no court of its own; jurisdiction is Zug."""
    assert "Gerichtsstand ist Zug" in client.get("/terms?lang=de").get_data(as_text=True)
    assert "jurisdiction is Zug" in client.get("/terms?lang=en").get_data(as_text=True)
