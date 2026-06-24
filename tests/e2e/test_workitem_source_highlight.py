"""E2E for the workitems source-highlight scaffolding.

The TEST database has no workitem rows (no Octopus), so the data path
(expand -> toggle -> boxes) can't be exercised here — that is covered by the
unit tests (test_field_locations, test_media_info_field_sources) and manual
browser verification. These tests guard that the overlay markup and CSS are
wired into the page and didn't regress.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_source_highlight_css_linked(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    links = page.locator('link[rel="stylesheet"][href*="source-highlight.css"]')
    assert links.count() >= 1


@pytest.mark.flaky_e2e
def test_lightbox_has_toggle_and_overlay_layer(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    # #imageModal is always present (hidden) — its toggle + overlay layer must exist.
    expect(page.locator("#imageModal #srcHlLayer")).to_be_attached()
    toggle = page.locator('[data-testid="workitems-src-toggle"]')
    expect(toggle).to_be_attached()
    # Toggle starts hidden until a document with locations is opened.
    assert toggle.get_attribute("hidden") is not None
