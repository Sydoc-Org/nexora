"""Template lint: no root-relative URLs hand-built in templates.

On PROD nexora is served under the /nexora URL prefix — nx_lib/__init__.py
wires PrefixMiddleware(app.wsgi_app, prefix="/nexora") when ENVIRONMENT=PROD.
Server-side url_for() is prefix-aware (the middleware sets SCRIPT_NAME), but a
hand-written root-relative URL in a template escapes the prefix and lands on
the IIS ROOT site (C:\\inetpub\\wwwroot) -> 404.0 StaticFile. The Recent
Validations card shipped exactly that (2026-07-13). No test environment wires
the prefix, so this source lint is the only possible regression guard.

Allowed idioms (never matched below):
- server-rendered: {{ url_for(...) }}  (SCRIPT_NAME-aware)
- client-side:     const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";
                   then `${API_PREFIX}workitems?...` or API_PREFIX + url.slice(1)
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "templates"
# JS lifted out of the Jinja partials (#191) left this lint's original scope;
# it needs the same guard, and more so -- a .js file cannot fall back on
# url_for() at all, API_PREFIX is its only option.
STATIC_JS = REPO_ROOT / "static" / "js"

BAD_PATTERNS = [
    # JS navigation with a root-relative literal (any quote style);
    # '${API_PREFIX}...', a.url and "{{ url_for(...) }}" values don't match.
    # (?!/) exempts protocol-relative //.
    re.compile(r"location\.href\s*=\s*['\"`]/(?!/)"),
    # literal href/src/action attributes with a root-relative value
    re.compile(r"""\b(?:href|src|action)=["']/(?!/)"""),
    # Direct fetch of a root-relative literal.
    re.compile(r"""\bfetch\(\s*['\"`]/(?!/)"""),
    # A bare-"/" API_PREFIX fallback silently breaks under the PROD prefix.
    re.compile(r"""window\.API_PREFIX\s*\|\|\s*["']/["']"""),
]


def _offenders():
    found = []
    for tpl in sorted(TEMPLATES.rglob("*.html")) + sorted(STATIC_JS.rglob("*.js")):
        text = tpl.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            found.extend(
                f"{tpl.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
                for rx in BAD_PATTERNS
                if rx.search(line)
            )
    return found


def test_no_root_relative_urls_in_templates():
    offenders = _offenders()
    assert offenders == [], (
        "Root-relative URL(s) escape the /nexora prefix on PROD and 404 on the "
        "IIS root site. Use API_PREFIX (JS partials) or url_for() (Jinja):\n" + "\n".join(offenders)
    )


def test_no_jinja_syntax_in_static_js():
    """static/js/*.js is served raw -- Jinja there ships {{ ... }} to the browser.

    Translated strings and url_for() values belong in the paired inline shim
    under templates/js/ (#191), which is what babel.cfg extracts from.
    """
    offenders = [
        f"{js.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
        for js in sorted(STATIC_JS.rglob("*.js"))
        for lineno, line in enumerate(js.read_text(encoding="utf-8").splitlines(), start=1)
        if "{{" in line or "{%" in line
    ]
    assert offenders == [], (
        "Jinja syntax in a static .js file is never rendered. Move the value into "
        "the inline shim in templates/js/ and read it from window:\n" + "\n".join(offenders)
    )
