"""api_get_media_info exposes field_sources, permission-suppressed.

field highlighting needs BOTH workitems.details.view.images (to see the page
image the boxes are drawn over) and .view.fields (to see the values). Without
fields perm: field_sources is empty. Without images perm: values stay but the
box locations are stripped.
"""

import nx_lib.views.workitems as w

SOURCES = [
    {
        "key": "Doc number",
        "label": "Doc number",
        "value": "INV-1",
        "locations": [{"page": 0, "rect": {"left": 749, "top": 473, "width": 347, "height": 50}}],
    },
    {"key": "VAT rate", "label": "VAT rate", "value": "7.7", "locations": []},
]


def _patch(monkeypatch, perms):
    monkeypatch.setattr(w, "get_domain_for_workitem", lambda wid: "d")
    monkeypatch.setattr(w, "get_workitemdata_param", lambda wid, dom: ("wd", "doc1"))
    monkeypatch.setattr(
        w,
        "get_extensions_urls_fields",
        lambda *a, **k: ([".jpg"], ["u0"], {"Doc number": "INV-1", "VAT rate": "7.7"}, SOURCES),
    )
    monkeypatch.setattr(w, "has_permission", lambda code: code in perms)
    w.cache.delete("media_info_123")
    w.cache.delete("media_data_123")


def _get(client):
    with client.session_transaction() as s:
        s["userid"], s["username"] = "1", "tester"
    return client.get("/api/get_media_info/123")


ALL = {"workitems.details.view", "workitems.details.view.images", "workitems.details.view.fields"}


def test_media_info_includes_field_sources(client, monkeypatch):
    _patch(monkeypatch, ALL)
    r = _get(client)
    assert r.status_code == 200
    assert r.get_json()["field_sources"] == SOURCES


def test_field_sources_empty_without_fields_perm(client, monkeypatch):
    _patch(monkeypatch, {"workitems.details.view", "workitems.details.view.images"})
    assert _get(client).get_json()["field_sources"] == []


def test_locations_stripped_without_images_perm(client, monkeypatch):
    _patch(monkeypatch, {"workitems.details.view", "workitems.details.view.fields"})
    srcs = _get(client).get_json()["field_sources"]
    # values preserved, boxes removed
    assert [s["value"] for s in srcs] == ["INV-1", "7.7"]
    assert all(s["locations"] == [] for s in srcs)
