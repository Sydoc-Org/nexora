"""The shared workitem-detail panel partial is included on its consumer pages
and exposes window.NexoraWorkitemDetail.render. Include-presence is asserted on
the /prepared_documents register render (gate-and-mocked, deterministically 200)
so a 500-fallback can never make the assertion pass vacuously.

Since #191 shim-ified templates/js/_workitem_detail_panel_js.html, the panel's
behaviour (loadDetailData, attachLightbox, ...) lives in
static/js/workitem_detail_panel.js -- the page's inline HTML only carries the
i18n data + the <script src> that loads it. So markers that used to live in
the page's own HTML response are asserted against the static file instead;
the page-response assertions instead confirm the shim's script tag rendered.
"""

from pathlib import Path

import pytest

STATIC_JS = (
    Path(__file__).resolve().parents[2] / "static" / "js" / "workitem_detail_panel.js"
).read_text(encoding="utf-8")


@pytest.fixture()
def workitems_all_perms(monkeypatch):
    monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)
    yield


def test_detail_panel_partial_present_on_workitems(user_client, workitems_all_perms):
    # The include lives in the template body (before any data fetch); a 500-fallback
    # would render 500.html WITHOUT the marker, so assert unconditionally — that makes
    # the 'expect fail' run fail loudly and a later regression fail loudly too.
    resp = user_client.get("/workitems")
    assert b"workitem_detail_panel.js" in resp.data
    assert "NexoraWorkitemDetail" in STATIC_JS


def test_detail_panel_exposes_loader_and_source_helpers(user_client, workitems_all_perms):
    resp = user_client.get("/workitems")
    assert b"workitem_detail_panel.js" in resp.data
    for marker in (
        "loadDetailData",
        "buildSourceDetailsHtml",
        "function allSources",
        "get_media_info",
    ):
        assert marker in STATIC_JS


def test_detail_panel_exposes_lightbox_attach(user_client, workitems_all_perms):
    resp = user_client.get("/workitems")
    assert b"workitem_detail_panel.js" in resp.data
    assert "attachLightbox" in STATIC_JS


def test_detail_panel_collaboration_removed(user_client, workitems_all_perms):
    """Collaboration (comments/tags/priority/assignment) was pruned from the shared
    panel partial in both the editable and read-only rendering branches. Asserted on
    the static behaviour file (the panel is built client-side)."""
    assert "buildCollaborationMarkup" not in STATIC_JS
    assert "buildReadonlyCommentsMarkup" not in STATIC_JS
    assert "attachLightbox" in STATIC_JS
    assert "loadHistory" in STATIC_JS
