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
    page.goto(f"{base}/reporting")
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
