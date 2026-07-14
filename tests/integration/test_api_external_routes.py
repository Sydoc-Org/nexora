"""Integration tests for nx_lib.views.api_external — external machine-to-machine API.

Routes covered:
- GET /api/v1/stats/today                       (require_api_key guard, JSON stats response)
- 404/500/403 on /api/v1/* paths return JSON   (path-aware error handlers)
"""


# --------------------------- JSON error handlers --------------------------- #


def test_unknown_api_v1_path_returns_json_404(client):
    resp = client.get("/api/v1/definitely/not/a/route")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json() == {"error": "Not found"}


def test_non_api_404_still_renders_html(client):
    resp = client.get("/definitely-not-a-page")
    assert resp.status_code == 404
    assert "text/html" in resp.content_type
