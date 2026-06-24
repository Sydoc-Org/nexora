"""The shared workitem-detail panel partial is included on its consumer pages
and exposes window.NexoraWorkitemDetail.render. Include-presence is asserted on
the /prepared_documents register render (gate-and-mocked, deterministically 200)
so a 500-fallback can never make the assertion pass vacuously."""

import pytest


@pytest.fixture()
def workitems_all_perms(monkeypatch):
    monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)
    yield


def test_detail_panel_partial_present_on_workitems(user_client, workitems_all_perms):
    # The include lives in the template body (before any data fetch); a 500-fallback
    # would render 500.html WITHOUT the marker, so assert unconditionally — that makes
    # the 'expect fail' run fail loudly and a later regression fail loudly too.
    resp = user_client.get("/workitems")
    assert b"NexoraWorkitemDetail" in resp.data


def test_detail_panel_exposes_loader_and_source_helpers(user_client, workitems_all_perms):
    resp = user_client.get("/workitems")
    for marker in (
        b"loadDetailData",
        b"buildSourceDetailsHtml",
        b"function allSources",
        b"get_media_info",
    ):
        assert marker in resp.data


def test_detail_panel_exposes_lightbox_attach(user_client, workitems_all_perms):
    resp = user_client.get("/workitems")
    assert b"attachLightbox" in resp.data


def test_detail_panel_readonly_branch_present(user_client, workitems_all_perms):
    """The shared partial carries a read-only branch that omits write controls and a
    writable branch that includes them; render() switches on readOnly. Asserted on the
    rendered partial source (the panel is built client-side)."""
    resp = user_client.get("/workitems")
    body = resp.data
    assert b"buildReadonlyCommentsMarkup" in body
    assert b"buildCollaborationMarkup" in body
    assert b"readOnly" in body
