"""api_get_media_info exposes table_sources, permission-suppressed.

Table/line-item highlighting reuses the same two perms as scalar fields:
workitems.details.view.images (page image the boxes are drawn over) and
.view.fields (the cell values). Without fields perm: table_sources is empty.
Without images perm: cell values stay but every cell's box locations are stripped.
"""

import nx_lib.views.workitems as w

TABLES = [
    {
        "title": "TabVat",
        "columns": ["TabNetAmount", "TabVatRate"],
        "rows": [
            [
                {
                    "col": "TabNetAmount",
                    "value": "236.82",
                    "locations": [
                        {"page": 1, "rect": {"left": 851, "top": 2407, "width": 543, "height": 544}}
                    ],
                    "confidence": 0.0,
                },
                {"col": "TabVatRate", "value": "7.7", "locations": []},
            ]
        ],
    }
]


def _patch(monkeypatch, perms):
    monkeypatch.setattr(w, "get_domain_for_workitem", lambda wid: "d")
    monkeypatch.setattr(w, "get_workitemdata_param", lambda wid, dom: ("wd", "doc1"))
    monkeypatch.setattr(
        w,
        "get_extensions_urls_fields",
        lambda *a, **k: ([".jpg"], ["u0", "u1"], {"x": "y"}, [], TABLES),
    )
    monkeypatch.setattr(w, "has_permission", lambda code: code in perms)


# A dedicated workitem id no other test caches, so this file is immune to a
# stale media_info_* cache entry left by another test (cache writes happen in a
# request context; test-side cache mutation does not reliably reach it). The
# route stores the full payload and applies _suppress per-request, so all three
# perm cases stay correct even if these tests share one cached entry.
WID = 980123


def _get(client):
    with client.session_transaction() as s:
        s["userid"], s["username"] = "1", "tester"
    return client.get(f"/api/get_media_info/{WID}")


ALL = {"workitems.details.view", "workitems.details.view.images", "workitems.details.view.fields"}


def test_media_info_includes_table_sources(client, monkeypatch):
    _patch(monkeypatch, ALL)
    r = _get(client)
    assert r.status_code == 200
    assert r.get_json()["table_sources"] == TABLES


def test_table_sources_empty_without_fields_perm(client, monkeypatch):
    _patch(monkeypatch, {"workitems.details.view", "workitems.details.view.images"})
    assert _get(client).get_json()["table_sources"] == []


def test_table_cell_locations_stripped_without_images_perm(client, monkeypatch):
    _patch(monkeypatch, {"workitems.details.view", "workitems.details.view.fields"})
    tables = _get(client).get_json()["table_sources"]
    cells = [c for t in tables for row in t["rows"] for c in row]
    # values preserved, every cell box removed
    assert [c["value"] for c in cells] == ["236.82", "7.7"]
    assert all(c["locations"] == [] for c in cells)
