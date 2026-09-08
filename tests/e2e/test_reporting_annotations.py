"""e2e: chart annotations on the Simple tab (#284)."""

import json

from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


# Same stub catalog shape tests/e2e/test_reporting_simple.py uses (WIZ_STUB_*):
# the Simple pane fetches sources + measures at page load, and mountChart's
# metric labels come from that catalog.
STUB_SOURCES = [
    {
        "id": "stub_src",
        "label": "Stub source",
        "kind": "curated",
        "processes": [],
        "fields": [
            {
                "field": "import_date",
                "label": "Import date",
                "type": "date",
                "grainable": True,
                "filterable": True,
            },
        ],
    }
]
STUB_METRICS = {"stub_src": [{"code": "stub_count", "label": "Stub count", "aggregation": "count"}]}


def _definition():
    return {
        "schemaVersion": 1,
        "source": "stub_src",
        "visualization": "chart",
        "chartType": "bar",
        "title": "e2e annotated",
        "columns": [{"field": "import_date", "grain": "month"}],
        "metrics": [{"metric": "stub_count"}],
        "filters": [],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 100,
    }


def _json(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def _stub_report(page, owned=True):
    """Register BEFORE goto: library list, catalogs and the report detail all
    fetch as soon as the Simple pane mounts. A non-owned report is listed with
    visibility 'shared' so the library files it under rs-group-shared."""
    row = {
        "id": 4242,
        "name": "e2e annotated",
        "ownerName": "Admin",
        "updatedAt": "2026-07-01T00:00:00Z",
        "visibility": "private" if owned else "shared",
        "owned": owned,
        "kind": "chart",
    }
    page.route("**/api/reporting/sources", lambda r: _json(r, STUB_SOURCES))
    page.route("**/api/reporting/measures", lambda r: _json(r, STUB_METRICS))
    page.route("**/api/reporting/reports", lambda r: _json(r, [row]))
    page.route(
        "**/api/reporting/reports/4242",
        lambda r: _json(
            r, {"name": row["name"], "definition": _definition(), "owned": owned, "canEdit": owned}
        ),
    )
    page.route(
        "**/api/reporting/run",
        lambda r: _json(
            r,
            {
                "columns": [
                    {"field": "import_date", "header": "Import date"},
                    {"field": "stub_count", "header": "Stub count"},
                ],
                "rows": [["2026-06-01", 10], ["2026-07-01", 14], ["2026-08-01", 9]],
                "truncated": False,
                "rowCount": 3,
                "sql": None,
                "params": [],
                "resolvedDates": [],
            },
        ),
    )


def _stub_annotations(page, store):
    def handler(route):
        req = route.request
        if req.method == "GET":
            _json(route, list(store))
        elif req.method == "POST":
            body = req.post_data_json
            store.append(
                {
                    "id": len(store) + 1,
                    "bucket": body["bucket"],
                    "text": body["text"],
                    "author": "Admin",
                    "createdAt": None,
                }
            )
            _json(route, {"id": store[-1]["id"], "ok": True})
        elif req.method == "DELETE":
            aid = int(req.url.rsplit("/", 1)[1])
            store[:] = [a for a in store if a["id"] != aid]
            _json(route, {"ok": True})

    # Two patterns: Playwright's glob match requires the trailing "**" to sit
    # after a "/" to act as a recursive wildcard, so a single
    # ".../annotations**" pattern matches the bare collection URL but not
    # ".../annotations/<id>" (DELETE) -- register both explicitly. Registered
    # AFTER _stub_report so Playwright (last-registered wins) never hands
    # these to the detail stub.
    page.route("**/api/reporting/reports/4242/annotations", handler)
    page.route("**/api/reporting/reports/4242/annotations/*", handler)


def test_owner_adds_and_deletes_annotation(nexora_server, page):
    _login(page, nexora_server)
    store = []
    _stub_report(page)
    _stub_annotations(page, store)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("e2e annotated").click()
    expect(page.get_by_test_id("rs-chart-card")).to_be_visible()

    add = page.get_by_test_id("rs-annotation-add")
    expect(add).to_be_visible()
    add.click()
    expect(page.get_by_test_id("rs-annotation-pop")).to_be_visible()
    page.get_by_test_id("rs-annotation-bucket-select").select_option("2026-07-01")
    page.get_by_test_id("rs-annotation-text").fill("Mailroom outage")
    page.get_by_test_id("rs-annotation-save").click()

    expect(page.get_by_test_id("rs-annotation-pop")).to_be_hidden()
    row = page.get_by_test_id("rs-annotation-row")
    expect(row).to_have_count(1)
    expect(row).to_contain_text("2026-07-01")
    expect(row).to_contain_text("Mailroom outage")
    assert store and store[0]["bucket"] == "2026-07-01"
    # The marker rides the chart as a tagged dataset.
    n = page.evaluate("window.RS.state.chart.data.datasets.filter(d => d._nxAnnotations).length")
    assert n == 1

    page.get_by_test_id("rs-annotation-delete").click()
    expect(page.get_by_test_id("rs-annotation-row")).to_have_count(0)
    assert store == []


def test_viewer_sees_list_but_no_add(nexora_server, page):
    _login(page, nexora_server)
    store = [
        {
            "id": 7,
            "bucket": "2026-06-01",
            "text": "New client",
            "author": "Owner",
            "createdAt": None,
        }
    ]
    _stub_report(page, owned=False)
    _stub_annotations(page, store)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-shared").get_by_text("e2e annotated").click()
    expect(page.get_by_test_id("rs-chart-card")).to_be_visible()
    expect(page.get_by_test_id("rs-annotation-row")).to_have_count(1)
    expect(page.get_by_test_id("rs-annotation-add")).to_be_hidden()
    expect(page.get_by_test_id("rs-annotation-delete")).to_have_count(0)
