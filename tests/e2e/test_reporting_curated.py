"""E2E: the seeded curated 'table' sources (A5 Generali, A6 Workitems) appear in
the builder's Source dropdown and populate their field list.

TestAdmin holds both source permissions. The field catalog comes from the
registry ColumnsJSON via /api/reporting/sources (no Generali/Octopus DB access),
so this works in TEST without those databases. Running them is not exercised here
(that needs the live databases).
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_curated_table_sources_listed(nexora_server, page):
    _login(page, nexora_server)
    src = page.locator('[data-testid="reporting-source-select"]')
    expect(src.locator("option", has_text="Generali — PDQM Report")).to_have_count(1)
    expect(src.locator("option", has_text="Workitems (Octopus)")).to_have_count(1)

    # Selecting the Generali source populates its field list from the registry.
    src.select_option(value="generali_pdqm")
    expect(page.locator('[data-testid="reporting-field-panel"]')).to_contain_text("Parent category")
    page.screenshot(path="var/screenshots/reporting_curated_sources.png")
