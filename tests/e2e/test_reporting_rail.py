"""e2e: the Console sources rail shows one card per database."""

import json

from playwright.sync_api import expect

from tests.e2e.test_reporting_simple import _login

_FIELD = {
    "field": "ForDate",
    "label": "Date",
    "type": "date",
    "grainable": True,
    "filterable": True,
}

SOURCES = [
    {
        "id": "docprocessing",
        "label": "Document Processing",
        "kind": "curated",
        "engine": "statistics",
        "processes": [],
        "fields": [_FIELD],
    },
    {
        "id": "generali_attendance",
        "label": "Generali — Attendance",
        "kind": "curated",
        "engine": "generali",
        "processes": [],
        "fields": [_FIELD],
    },
    {
        "id": "generali_documents",
        "label": "Generali — Documents",
        "kind": "curated",
        "engine": "generali",
        "processes": [],
        "fields": [_FIELD],
    },
    {
        "id": "generali_projects",
        "label": "Generali — Project Management",
        "kind": "curated",
        "engine": "generali",
        "processes": [],
        "fields": [_FIELD],
    },
]


def test_rail_groups_sources_by_engine_when_health_probe_is_down(nexora_server, page):
    """With the health probe unavailable (database unreachable) the rail must
    still collapse the three Generali table sources into ONE card, keyed on
    the engine, instead of falling back to one card per source label."""
    _login(page, nexora_server)
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(SOURCES)),
    )
    page.route(
        "**/api/reporting/sources/health",
        lambda r: r.fulfill(status=503, content_type="application/json", body="{}"),
    )
    page.goto(f"{nexora_server}/reporting")

    cards = page.get_by_test_id("rc-source")
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("Statistics")
    expect(cards.nth(1)).to_contain_text("Generali")
