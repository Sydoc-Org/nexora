"""E2E for the reporting metrics-registry (semantic layer, Slice 1).

TestAdmin holds reporting.metrics.manage (sql/test/seed.sql grants every
permission), so /reporting/metrics renders and a 'count' metric can be
registered through the form and appears in the registry list. The builder's
Metrics well is asserted present; an aggregated data run is not checked here
because the statistics DB is absent in TEST (see test_reporting.py).
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, path, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}{path}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_metrics_admin_add_and_list(nexora_server, page):
    _login(page, nexora_server, "/reporting/metrics")
    expect(page.locator('[data-testid="reporting-metrics-admin"]')).to_be_visible()

    page.fill('[data-testid="rpm-code"]', "e2e_metric")
    page.select_option('[data-testid="rpm-source"]', index=0)
    page.fill('[data-testid="rpm-label"]', "E2E Metric")
    page.fill('[data-testid="rpm-label-de"]', "E2E Metrik")
    # 'count' needs no base field (the form disables it for count).
    page.select_option("#rpmAggregation", "count")
    page.locator('[data-testid="rpm-save"]').click()
    expect(page.locator('[data-testid="rpm-msg"]')).to_contain_text("Saved")
    expect(page.locator('[data-testid="reporting-metrics-rows"]')).to_contain_text("e2e_metric")
    # The German label round-trips through save -> list -> edit form.
    page.locator('[data-testid="reporting-metrics-rows"] tr', has_text="e2e_metric").get_by_text(
        "Edit"
    ).click()
    expect(page.locator('[data-testid="rpm-label-de"]')).to_have_value("E2E Metrik")
    page.screenshot(path="var/screenshots/reporting_metrics_admin.png")

    # Clean up the registered row so it doesn't leak into other e2e runs.
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    rows = page.request.get(f"{nexora_server}/api/reporting/admin/metrics").json()["rows"]
    mid = next(r["id"] for r in rows if r["code"] == "e2e_metric")
    page.request.delete(
        f"{nexora_server}/api/reporting/admin/metrics/{mid}",
        headers={"X-CSRFToken": token, "Content-Type": "application/json"},
    )


@pytest.mark.flaky_e2e
def test_metrics_well_present_in_builder(nexora_server, page):
    _login(page, nexora_server, "/reporting?tab=advanced")
    expect(page.locator('[data-testid="reporting-page"]')).to_be_visible()
    # The well's <ul> is empty (and therefore zero-height) until a metric is
    # added, so assert it is present in the DOM rather than visibly sized; the
    # "+ Add metric" control is the visible proof the metrics well renders.
    expect(page.locator('[data-testid="reporting-well-metrics"]')).to_be_attached()
    expect(page.locator('[data-testid="reporting-add-metric"]')).to_be_visible()
