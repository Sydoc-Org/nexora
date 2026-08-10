"""Dashboard "Signed in as <name>" must HTML-escape the user-controlled
display name (security audit #193, finding 9).

The note used to wrap the whole gettext result in |safe, so a fullname like
`<img src=x onerror=...>` rendered as live HTML (stored/self XSS, executable
because the CSP allows 'unsafe-inline'). The name is now escaped with |e while
only the literal <strong></strong> stays markup.
"""

from pathlib import Path

from flask import render_template_string

# The exact name-substitution expression used by templates/dashboard.html:
# literal tags stay markup (|safe), only the user name is escaped (|e).
_SIGNIN_EXPR = (
    '{{ _("Signed in as %(name)s",' ' name="<strong>"|safe ~ fullname|e ~ "</strong>"|safe)|safe }}'
)

_PAYLOAD = "<img src=x onerror=alert(1)>"


def test_signin_expression_escapes_fullname(app):
    with app.test_request_context():
        out = render_template_string(_SIGNIN_EXPR, fullname=_PAYLOAD)
    assert "<strong>" in out  # the literal bold tag is preserved
    assert "<img" not in out  # the payload is NOT rendered as a live tag
    assert "&lt;img" in out  # ... it is HTML-escaped


def test_dashboard_template_uses_escaped_name():
    """Pin the fix in the real template so the vulnerable shape can't return."""
    src = Path("templates/dashboard.html").read_text(encoding="utf-8")
    assert "fullname|e" in src
    assert 'fullname ~ "</strong>"|safe' not in src  # old, unescaped shape
