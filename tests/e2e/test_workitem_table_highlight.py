"""E2E for the workitems table / line-item source-highlight scaffolding.

The TEST database has no workitem rows (no Octopus), so the data path
(expand -> grid + cell boxes -> click-to-locate) can't be exercised here — that
is covered by the unit tests (test_table_locations, test_media_info_table_sources)
and manual browser verification (incl. a live XSS-escaping check). These tests
guard that the table-cell box + line-item grid styles shipped and the workitems
page still renders without regression.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_table_highlight_css_rules_present(nexora_server, page):
    """The dashed cell-box variant and the line-item grid styles must be in the
    loaded source-highlight.css (regression guard for the table feature)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    selectors = page.evaluate(
        """() => {
            const out = [];
            for (const sheet of document.styleSheets) {
                let rules;
                try { rules = sheet.cssRules; } catch (e) { continue; }
                if (!rules) continue;
                for (const r of rules) { if (r.selectorText) out.push(r.selectorText); }
            }
            return out.join(' | ');
        }"""
    )
    assert ".src-hl-box--cell" in selectors
    assert ".src-table-grid" in selectors


@pytest.mark.flaky_e2e
def test_workitems_page_renders_with_table_feature(nexora_server, page):
    """The workitems page (which now also loads the table grid JS) still renders
    its core chrome — the overlay layer + toggle remain wired."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    expect(page.locator("#imageModal #srcHlLayer")).to_be_attached()
    expect(page.locator('[data-testid="workitems-src-toggle"]')).to_be_attached()
