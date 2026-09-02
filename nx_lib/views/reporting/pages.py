"""Reporting: guide + builder page routes (beautify-phase-2a, Task 3).

``/reporting`` (the builder page) and ``/reporting/guide`` (the in-app user
guide, authored in git as docs/howto/reporting-guide.md). Split out of
``nx_lib/views/reporting/__init__.py`` — see that module's docstring for the
package's overall shape.
"""

import re

from flask import current_app, render_template, session
from markdown_it import MarkdownIt

from ...config import REPO_ROOT
from ...reporting.ai import EFFORT_AGENT, supports_effort
from ...security import has_permission, page_visibility, require_permission
from .ai import _ai_config

# The user guide is authored in git as docs/howto/reporting-guide.md and
# served in-app here (English only; the Confluence mirror stays for the team).
# The deploy workflow copies this one docs file onto the server — see the
# "Sync to deploy folder" step in .github/workflows/deploy.yml.
_GUIDE_MD = REPO_ROOT / "docs" / "howto" / "reporting-guide.md"


def _guide_render(md_text):
    """reporting-guide.md -> (html, toc list of {slug, title}). Pure.

    Drops the H1 (the page chrome carries the title), unwraps links to other
    .md files (their targets are not routable in-app), and stamps slug ids on
    <h2> headings so the on-page TOC can anchor-link them.
    """
    lines = md_text.splitlines()
    body = [ln for i, ln in enumerate(lines) if not (ln.startswith("# ") and i < 5)]
    text = re.sub(r"\[([^\]]+)\]\([^)\s]*\.md\)", r"\1", "\n".join(body))
    html = MarkdownIt("commonmark").enable(["table", "strikethrough"]).render(text)
    toc = []

    def _anchor(match):
        title = re.sub(r"<[^>]+>", "", match.group(1))
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        toc.append({"slug": slug, "title": title})
        return f'<h2 id="{slug}">{match.group(1)}</h2>'

    return re.sub(r"<h2>(.*?)</h2>", _anchor, html), toc


@require_permission("reporting.view")
def reporting_guide():
    try:
        guide_html, guide_toc = _guide_render(_GUIDE_MD.read_text(encoding="utf-8"))
    except OSError:
        current_app.logger.error("reporting guide source missing: %s", _GUIDE_MD)
        guide_html, guide_toc = None, []
    return render_template(
        "reporting_guide.html",
        guide_html=guide_html,
        guide_toc=guide_toc,
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        page_visibility=page_visibility(),
    )


def _ai_effort_enabled():
    """True when the configured model honours an effort level (composer gate)."""
    cfg = _ai_config()
    return supports_effort(cfg.get("provider"), cfg.get("model"))


@require_permission("reporting.view")
def reporting():
    return render_template(
        "reporting.html",
        logged_in_user=session.get("username", "Unknown"),
        userid=session.get("userid", "Unknown"),
        fullname=session.get("fullname"),
        page_visibility=page_visibility(),
        ai_enabled=has_permission("reporting.ai.use"),
        ai_caption_enabled=has_permission("reporting.ai.explain_data"),
        # The composer only offers Quick/Balanced/Deep when the configured
        # model can actually honour it (GPT-5 family, Claude Opus/Sonnet 5).
        ai_effort_enabled=_ai_effort_enabled(),
        ai_effort_default=EFFORT_AGENT,
        details_images_perm=has_permission("workitems.details.view.images"),
        details_audit_perm=has_permission("workitems.details.view.audit"),
        details_fields_perm=has_permission("workitems.details.view.fields"),
    )


def register_routes(app):
    app.add_url_rule("/reporting", endpoint="reporting", view_func=reporting)
    app.add_url_rule("/reporting/guide", endpoint="reporting_guide", view_func=reporting_guide)
