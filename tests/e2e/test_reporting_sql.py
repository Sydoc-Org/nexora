"""E2E smoke for the Reporting live-SQL tab.

TestAdmin holds reporting.sql.run (sql/test/seed.sql), so the SQL tab enables.
The statistics DB is absent in TEST, so a real run returns 503 — only the UI
flow (toggle, editor, acknowledgment) is asserted here, mirroring
tests/e2e/test_reporting.py which does not assert data rows either.
"""

import pytest
from playwright.sync_api import expect
from sqlalchemy import text

from nx_lib.db import engine_nexora_db


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")


def _clear_sql_ack(username="admin@test.local"):
    """Remove any prior live-SQL acknowledgment for this user.

    This test asserts the *first-use* acknowledgment modal appears, so it needs
    the user to start un-acked. A sibling e2e test (test_reporting_save) records
    an ack for the same admin via the API, and pytest collects it earlier
    (alphabetical file order), so without this reset the modal would already be
    dismissed and the assertion would fail. Also guards against a stale ack left
    in NEXORA_TEST by a previous run. Runs in the pytest process
    (ENVIRONMENT=TEST), which shares the database with the browser subprocess.
    """
    with engine_nexora_db.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM ReportingSqlAck WHERE UserID IN "
                "(SELECT userid FROM Users WHERE username = :u)"
            ),
            {"u": username},
        )


@pytest.mark.flaky_e2e
def test_sql_tab_enables_and_acknowledges(nexora_server, page):
    _clear_sql_ack()
    _login(page, nexora_server)
    sql_btn = page.locator('[data-testid="reporting-mode-sql"]')
    expect(sql_btn).to_be_enabled()
    sql_btn.click()
    editor = page.locator('[data-testid="reporting-sql-editor"]')
    expect(editor).to_be_visible()
    editor.fill("SELECT 1 AS one")
    page.locator('[data-testid="reporting-run"]').click()
    accept = page.locator('[data-testid="reporting-sql-ack-accept"]')
    expect(accept).to_be_visible()
    accept.click()
    expect(page.locator('[data-testid="reporting-sql-ack"]')).to_be_hidden()
    page.screenshot(path="var/screenshots/reporting_sql_smoke.png")


@pytest.mark.flaky_e2e
def test_sql_run_shows_loading_indicator(nexora_server, page):
    """Run injects the pulsing indicator into the results area while the query
    is in flight; the response (a 503 error here — no Statistics DB in TEST)
    replaces it, and Run is re-enabled. The injected node is latched via the
    MutationObserver addedNodes records, immune to fast replacement."""
    _login(page, nexora_server)
    # Pre-acknowledge via API so Run fires the fetch immediately (no modal in
    # the way), then reload so the page bootstraps with acknowledged=true.
    page.evaluate("""() => fetch('/api/reporting/sql/ack', {
        method: 'POST',
        headers: {'Content-Type': 'application/json',
                  'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
        body: '{}'
    })""")
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.locator('[data-testid="reporting-mode-sql"]').click()
    editor = page.locator('[data-testid="reporting-sql-editor"]')
    expect(editor).to_be_visible()
    editor.fill("SELECT 1 AS one")
    page.evaluate("""() => {
        window.__runLoadingWasSeen = false;
        const wrap = document.getElementById('rpResults');
        const obs = new MutationObserver((muts) => {
            for (const m of muts) {
                for (const n of m.addedNodes) {
                    if (n.nodeType === 1 && n.getAttribute &&
                        n.getAttribute('data-testid') === 'reporting-run-loading') {
                        window.__runLoadingWasSeen = true;
                        obs.disconnect();
                        return;
                    }
                }
            }
        });
        obs.observe(wrap, { childList: true });
    }""")
    run_btn = page.locator('[data-testid="reporting-run"]')
    run_btn.click()
    # 503 from the unconfigured sandbox -> error paragraph replaces the loader.
    expect(page.locator("#rpResults .reporting-error")).to_be_visible()
    expect(run_btn).to_be_enabled()
    assert page.evaluate(
        "() => window.__runLoadingWasSeen"
    ), "the run-loading node was never injected into rpResults"
    page.screenshot(path="var/screenshots/reporting_advanced_run_loading.png")
