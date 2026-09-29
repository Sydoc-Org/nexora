"""The PROD CSP allows third-party scripts/styles by exact CDN path, not by
origin (security sweep 2026-09). Every CDN URL a template references must be
covered by config.CDN_SCRIPTS / CDN_STYLES, or PROD silently refuses to load
it -- bump a library version in a template and this test tells you to bump
the allowlist too."""

import re
from pathlib import Path

from nx_lib import config as cfg

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
CDN = r"https://(?:cdn\.tailwindcss\.com|cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net)[^\"'\s>]*"


def _covered(url, allow):
    url = url.split("?", 1)[0]
    return any(url == a or (a.endswith("/") and url.startswith(a)) for a in allow)


def _urls(tag):
    seen = set()
    for html in TEMPLATES.rglob("*.html"):
        for m in re.finditer(
            rf"<{tag}\b[^>]*?(?:src|href)=[\"']({CDN})", html.read_text(encoding="utf-8")
        ):
            seen.add(m.group(1))
    return seen


def test_every_cdn_script_is_allowlisted():
    missing = {u for u in _urls("script") if not _covered(u, cfg.CDN_SCRIPTS)}
    assert not missing, f"add to config.CDN_SCRIPTS: {sorted(missing)}"


def test_every_cdn_stylesheet_is_allowlisted():
    missing = {u for u in _urls("link") if not _covered(u, cfg.CDN_STYLES)}
    assert not missing, f"add to config.CDN_STYLES: {sorted(missing)}"


def test_csp_has_no_bare_cdn_origin():
    for directive in ("script-src", "style-src"):
        for src in cfg.CSP[directive]:
            # Google Fonts is CSS only
            if src == "https://fonts.googleapis.com":
                continue
            assert not re.fullmatch(
                r"https://[^/]+/?", src
            ), f"{directive} allows a whole origin: {src}"


def test_no_page_loads_tailwind_labs_cdn():
    """Every page loads Tailwind from jsDelivr; cdn.tailwindcss.com is Tailwind
    Labs' own host, and the privacy notice has no transfer basis for it (#260)."""
    offenders = [
        str(p.relative_to(TEMPLATES))
        for p in TEMPLATES.rglob("*.html")
        if re.search(r"<script\b[^>]*cdn\.tailwindcss\.com", p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"load Tailwind from jsDelivr instead: {offenders}"
    for directive in cfg.CSP.values():
        assert "https://cdn.tailwindcss.com" not in directive
