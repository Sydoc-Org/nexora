"""Template lint: the sidebar shell and the site footer are mutually exclusive.

`_small_footer.html` is a marketing footer — a 96px sydoc logo and six links to
sydoc.ch public pages. It belongs on the surfaces a logged-out visitor sees,
which have no sidebar to hold anything. On an app page it is redundant chrome:
the sidebar already carries navigation, and since the profile dropdown gained
the version + build stamp there is nothing functional left in it.

It drifted the other way once already — 22 templates included it, the 12 newest
(reporting, admin, prepared_documents) did not, and nobody noticed. Stating the
rule as an invariant rather than a list is what keeps it from drifting back one
page at a time.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "templates"

SHELL = "_header.html"
FOOTER = "_small_footer.html"


def _pages():
    for path in TEMPLATES.rglob("*.html"):
        # archive/ is retired markup kept for reference, not served.
        if "archive" in path.parts:
            continue
        yield path, path.read_text(encoding="utf-8")


def test_no_template_has_both_shell_and_footer():
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p, text in _pages()
        if f"include '{SHELL}'" in text and FOOTER in text
    ]
    assert offenders == [], (
        "These templates render both the sidebar shell and the marketing footer. "
        "A page has one or the other: sidebar for app pages, footer for the "
        "logged-out surfaces.\n  " + "\n  ".join(offenders)
    )


def test_footer_still_used_by_the_logged_out_surfaces():
    # The counterpart guard: deleting the footer everywhere is also wrong. Login
    # and the error pages are the reason it exists.
    users = {p.name for p, text in _pages() if FOOTER in text and p.name != FOOTER}
    assert {
        "index.html",
        "_error_base.html",
    } <= users, f"Login and/or the error pages lost the footer; still used by: {sorted(users)}"
