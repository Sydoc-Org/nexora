"""api_get_media_info exposes field_sources, permission-suppressed.

Granular gating:
  .view.fields                  -> see the values at all (else field_sources=[]).
  .view.images + .source_location -> see WHERE on the page (box `locations`);
      location needs images too because boxes are drawn over the page image.
  .view.confidence              -> see the `confidence` score.
The route also returns a `source_location_visible` flag (false when the location
perm is absent) so the viewer can hide the "no source location" badge.
"""

import nx_lib.views.workitems as w

SOURCES = [
    {
        "key": "Doc number",
        "label": "Doc number",
        "value": "INV-1",
        "locations": [{"page": 0, "rect": {"left": 749, "top": 473, "width": 347, "height": 50}}],
        "confidence": 0.95,
    },
    {"key": "VAT rate", "label": "VAT rate", "value": "7.7", "locations": []},
]


def _patch(monkeypatch, perms):
    monkeypatch.setattr(w, "get_domain_for_workitem", lambda wid, client_hint=None: "d")
    monkeypatch.setattr(w, "get_workitemdata_param", lambda wid, dom: ("wd", "doc1"))
    monkeypatch.setattr(
        w,
        "get_extensions_urls_fields",
        lambda *a, **k: ([".jpg"], ["u0"], {"Doc number": "INV-1", "VAT rate": "7.7"}, SOURCES, []),
    )
    monkeypatch.setattr(w, "has_permission", lambda code: code in perms)
    w.cache.delete("media_info_123")
    w.cache.delete("media_data_123")


def _get(client):
    with client.session_transaction() as s:
        s["userid"], s["username"] = "1", "tester"
    return client.get("/api/get_media_info/123")


ALL = {
    "workitems.details.view",
    "workitems.details.view.images",
    "workitems.details.view.fields",
    "workitems.details.view.confidence",
    "workitems.details.view.source_location",
}


def test_media_info_includes_field_sources(client, monkeypatch):
    _patch(monkeypatch, ALL)
    r = _get(client)
    assert r.status_code == 200
    assert r.get_json()["field_sources"] == SOURCES
    assert r.get_json()["source_location_visible"] is True


def test_field_sources_empty_without_fields_perm(client, monkeypatch):
    _patch(monkeypatch, {"workitems.details.view", "workitems.details.view.images"})
    assert _get(client).get_json()["field_sources"] == []


def test_locations_stripped_without_images_perm(client, monkeypatch):
    _patch(monkeypatch, {"workitems.details.view", "workitems.details.view.fields"})
    srcs = _get(client).get_json()["field_sources"]
    # values preserved, boxes removed
    assert [s["value"] for s in srcs] == ["INV-1", "7.7"]
    assert all(s["locations"] == [] for s in srcs)


def test_locations_stripped_without_source_location_perm(client, monkeypatch):
    # images + fields + confidence, but NOT source_location -> boxes removed,
    # values + confidence kept; the badge-suppressing flag goes false.
    _patch(monkeypatch, ALL - {"workitems.details.view.source_location"})
    body = _get(client).get_json()
    srcs = body["field_sources"]
    assert all(s["locations"] == [] for s in srcs)
    assert srcs[0].get("confidence") == 0.95
    assert [s["value"] for s in srcs] == ["INV-1", "7.7"]
    assert body["source_location_visible"] is False


def test_confidence_stripped_without_confidence_perm(client, monkeypatch):
    # images + fields + source_location, but NOT confidence -> confidence removed,
    # boxes kept.
    _patch(monkeypatch, ALL - {"workitems.details.view.confidence"})
    srcs = _get(client).get_json()["field_sources"]
    assert all("confidence" not in s for s in srcs)
    assert srcs[0]["locations"] == SOURCES[0]["locations"]
