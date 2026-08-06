"""Unit tests for the /reporting/guide markdown rendering helper."""

import re
from pathlib import Path

from nx_lib.views.reporting import _GUIDE_MD, _guide_render

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_guide_file_exists_and_path_points_into_repo():
    assert _GUIDE_MD == REPO_ROOT / "docs" / "howto" / "reporting-guide.md"
    assert _GUIDE_MD.is_file()


def test_real_guide_renders_with_toc_and_anchors():
    html, toc = _guide_render(_GUIDE_MD.read_text(encoding="utf-8"))
    assert toc, "guide has h2 sections, TOC must not be empty"
    slugs = [t["slug"] for t in toc]
    assert len(slugs) == len(set(slugs)), "h2 slugs must be unique"
    for slug in slugs:
        assert f'<h2 id="{slug}">' in html
    # The H1 is stripped (page chrome shows the title instead).
    assert "<h1" not in html
    # Tables from the guide survive the commonmark+table render.
    assert "<table>" in html


def test_md_cross_links_are_unwrapped():
    html, _ = _guide_render(
        "# T\n\n## A\n\nsee [`reporting.md`](reporting.md) and"
        " [design](../design/reporting-ai-assistant.md).\n"
    )
    assert "reporting.md)" not in html
    assert 'href="reporting.md"' not in html
    assert "../design/" not in html
    # The link text itself must survive.
    assert "reporting.md" in re.sub(r"<[^>]+>", "", html)
    assert "design" in html


def test_h1_only_stripped_near_top():
    html, _ = _guide_render("# Title\n\n## Section\n\nbody\n")
    assert "Title</h1>" not in html
    assert '<h2 id="section">Section</h2>' in html
