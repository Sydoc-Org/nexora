"""Integration tests for nx_lib.views.bps -- page, summary, entries, CSV (#415).

Routes covered:
- GET /bps                      page (bps.view-gated)
- GET /api/bps/summary          hours per task/customer/package/person + per day
- GET /api/bps/entries          single bookings of one drill-down leaf
- GET /api/bps/export.csv       every booking of the period

The test tier seeds bps.view (TestAdmin holds every code) but not the
bps_projects source, so the unstubbed API answers with its in-place error;
the happy path stubs the registry and the executor like the Finance tests.
"""

import datetime as dt
from decimal import Decimal

import pytest

import nx_lib.views.bps as bv

FAKE_SOURCE = {
    "id": "bps_projects",
    "label": "BPS — Projektrapport",
    "engine": "statistics",
    "provider": "table",
    "baseObject": "dbo.BPS_ProjectReport",
    "columns": [
        {"field": "Datum", "type": "date", "grainable": True},
        {"field": "Kunde", "type": "string"},
        {"field": "Projektpaket", "type": "string"},
        {"field": "Aufgabe", "type": "string"},
        {"field": "Benutzer", "type": "string"},
        {"field": "Stunden", "type": "number"},
        {"field": "Beschreibung", "type": "string"},
    ],
}
DAY = dt.date(2026, 8, 4)


@pytest.fixture()
def fake_source(monkeypatch):
    calls = []

    def execute(engine, sql, params):
        calls.append((sql, params))
        if "GROUP BY [Aufgabe], [Kunde], [Projektpaket], [Benutzer]" in sql:
            return [
                ("Change", "ISS", "Hypotheken", "Anna  Muster", Decimal("1.5"), 2),
                ("Vacation", "Absences", "Absences", "Ben", Decimal("8.4"), 1),
            ]
        if "GROUP BY [Datum]" in sql:
            return [(DAY, "Change", "ISS", "Hypotheken", Decimal("1.5"))]
        return [
            (DAY, "ISS", "Hypotheken", "Change", "Anna  Muster", Decimal("1.5"), "CR &amp; test"),
            (DAY, "ISS", "Hypotheken", "Change", "Other Person", Decimal("0.5"), "x"),
        ]

    monkeypatch.setattr(
        bv, "_get_effective_source", lambda code: FAKE_SOURCE if code == "bps_projects" else None
    )
    monkeypatch.setattr(bv, "_CURATED_ENGINES", {"statistics": object()})
    monkeypatch.setattr(bv, "_execute", execute)
    return calls


def test_bps_anonymous_redirects_to_login(client):
    resp = client.get("/bps", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.parametrize(
    "path", ["/bps", "/api/bps/summary", "/api/bps/entries", "/api/bps/export.csv"]
)
def test_bps_needs_bps_view(user_client, path):
    assert user_client.get(path).status_code == 403


def test_bps_page_renders_and_is_in_the_sidebar(admin_client):
    resp = admin_client.get("/bps?from=2026-08-01&to=2026-08-31")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-testid="bps-title"' in html
    assert 'value="2026-08-01"' in html and 'value="2026-08-31"' in html
    assert 'href="/bps"' in admin_client.get("/dashboard").get_data(as_text=True)


def test_summary_reports_an_unregistered_source_in_place(admin_client):
    resp = admin_client.get("/api/bps/summary?from=2026-08-01&to=2026-08-31")
    assert resp.status_code == 200
    assert "bps_projects" in resp.get_json()["error"]


def test_summary_returns_rows_days_and_totals(admin_client, fake_source):
    body = admin_client.get("/api/bps/summary?from=2026-08-03&to=2026-08-05").get_json()
    assert body["error"] is None
    assert body["from"] == "2026-08-03" and len(body["days"]) == 3
    change = next(r for r in body["rows"] if r["task"] == "Change")
    assert change["person"] == "Anna Muster" and change["category"] == "billable"
    assert body["totals"]["billable"] == 1.5 and body["totals"]["absence"] == 8.4
    assert fake_source[0][1][:2] == ["2026-08-03", "2026-08-06"]


def test_entries_match_the_cleaned_person_name(admin_client, fake_source):
    """The tree shows 'Anna Muster'; the raw column holds 'Anna  Muster'."""
    body = admin_client.get(
        "/api/bps/entries?from=2026-08-01&to=2026-08-31&task=Change&customer=ISS&person=Anna%20Muster"
    ).get_json()
    assert [e["person"] for e in body["entries"]] == ["Anna Muster"]
    assert body["entries"][0]["comment"] == "CR & test"
    sql, params = fake_source[-1]
    assert "[Benutzer] = ?" not in sql
    assert params[2:] == ["Change", "ISS"]


def test_export_lists_every_booking_uncached(admin_client, fake_source):
    resp = admin_client.get("/api/bps/export.csv?from=2026-08-01&to=2026-08-31")
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-store"
    assert 'filename="sydoc-bps-2026-08-01_2026-08-31.csv"' in resp.headers["Content-Disposition"]
    lines = resp.get_data(as_text=True).strip().splitlines()
    assert len(lines) == 3
    assert "TOP (200000)" in fake_source[-1][0]
