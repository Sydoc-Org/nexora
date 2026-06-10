"""e2e: the Simple/Advanced tabs and the Simple library (Spec 2)."""

from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


def test_default_tab_is_simple(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    expect(page.get_by_test_id("reporting-simple")).to_be_visible()
    expect(page.get_by_test_id("reporting-field-panel")).to_be_hidden()


def test_tab_param_overrides_to_advanced(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    expect(page.get_by_test_id("reporting-simple")).to_be_hidden()


def test_tab_choice_sticks_across_reload(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.get_by_test_id("reporting-tab-advanced").click()
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    page.goto(f"{nexora_server}/reporting")  # no ?tab param: localStorage wins
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    expect(page.get_by_test_id("reporting-simple")).to_be_hidden()


def test_library_groups_and_hides_sql_kind(nexora_server, page):
    _login(page, nexora_server)
    # Seed one table report + one sql-kind report via the API from the page
    # context (cookies + CSRF available in-page).
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const mk = (name, definition) => fetch('/api/reporting/reports', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({name, definition})
          });
          await mk('e2e simple lib', {schemaVersion: 1, source: 'docprocessing',
            visualization: 'table', title: 'e2e simple lib',
            columns: [{field: 'processname'}], filters: [], sort: [],
            scope: {clients: [], processes: []}, rowLimit: 100});
          await mk('e2e sql hidden', {kind: 'sql', target: 'statistics',
            sql: 'SELECT 1 AS x', title: 'e2e sql hidden'});
        }"""
    )
    # ?tab=simple: the seeding visit persisted 'advanced' to localStorage.
    page.goto(f"{nexora_server}/reporting?tab=simple")
    expect(page.get_by_test_id("rs-group-mine")).to_contain_text("e2e simple lib")
    expect(page.get_by_test_id("reporting-simple")).not_to_contain_text("e2e sql hidden")


def test_wizard_opens_and_lists_measures_or_empty_state(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.get_by_test_id("rs-new-report").click()
    expect(page.get_by_test_id("rs-wizard")).to_be_visible()
    # Either seeded metrics render as measure chips, or the empty state shows.
    expect(page.get_by_test_id("rs-measure-list")).not_to_be_empty()
