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
    # Either seeded metrics render as measure chips, or the explicit empty
    # state shows — assert one of the two concretely (not just non-empty).
    measure_list = page.get_by_test_id("rs-measure-list")
    chips = measure_list.locator("button.reporting-simple-choice")
    empty = measure_list.locator("p.reporting-simple-empty")
    assert chips.count() > 0 or empty.count() > 0


def test_wizard_category_breakdown_to_result_cards(nexora_server, page):
    # Full wizard -> result run over a seeded table source + count metric:
    # measure chip pins the source, category breakdown, no date field (table
    # source), Show result renders the grand-total stat card + the chart/table.
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_users', kind: 'curated', label: 'Wizard Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 10});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_user_count', sourceId: 'wiz_users', label: 'Wizard user count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Wizard user count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        run = page.get_by_test_id("rs-wizard-run")
        expect(run).to_be_visible()
        run.click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        stat = page.get_by_test_id("rs-stat-card")
        expect(stat).to_be_visible()
        expect(stat).to_contain_text("Wizard user count")
        # The seeded TEST DB always has at least the admin user.
        value = page.locator("#rsStatValue").inner_text()
        assert value.strip() not in ("", "–", "0")  # noqa: RUF001 — fmtNumber's null dash
        expect(page.get_by_test_id("rs-table-toggle")).to_be_visible()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )
