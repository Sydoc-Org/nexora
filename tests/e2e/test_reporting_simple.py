"""e2e: the Simple/Advanced tabs and the Simple library (Spec 2)."""

import json
import re

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
        page.get_by_test_id("rs-breakdown-next").click()
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


STUB_AI_DEFINITION = {
    "schemaVersion": 1,
    "source": "docprocessing",
    "visualization": "table",
    "title": "stub ai report",
    "subtitle": None,
    "columns": [{"field": "processname"}],
    "filters": [{"field": "processname", "op": "eq", "value": "acme.inv"}],
    "sort": [],
    "scope": {"clients": [], "processes": []},
    "rowLimit": 100,
    "groupBy": [],
    "sql": None,
    "sqlTarget": None,
}


def _stub_ai_build(page, definition=None, delay_s=0.0):
    import json
    import time

    body = json.dumps(
        {
            "definition": definition or STUB_AI_DEFINITION,
            "explanation": "stubbed explanation",
            "valid": True,
            "error": None,
        }
    )

    def handler(route):
        if delay_s:
            time.sleep(delay_s)
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)


def test_ai_ask_shows_loading_then_result(nexora_server, page):
    """Loading indicator appears while AI request is in-flight and hides once
    the result is ready.  We verify appearance by injecting a JS latch that
    records whether rsAiLoading was ever un-hidden, then assert on end-state.
    """
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    # Inject a MutationObserver that sets window.__aiLoadingWasSeen = true
    # the first time rsAiLoading.hidden flips to false.
    page.evaluate("""() => {
        window.__aiLoadingWasSeen = false;
        const el = document.getElementById('rsAiLoading');
        if (!el) return;
        if (!el.hidden) { window.__aiLoadingWasSeen = true; return; }
        const obs = new MutationObserver(() => {
            if (!el.hidden) {
                window.__aiLoadingWasSeen = true;
                obs.disconnect();
            }
        });
        obs.observe(el, { attributes: true, attributeFilter: ['hidden'] });
    }""")

    _stub_ai_build(page, delay_s=0.8)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()

    # Wait for the result to finish loading (explanation text appears).
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-msg")).to_contain_text("stubbed explanation")

    # Loading indicator must be hidden again now that the result is rendered.
    expect(page.get_by_test_id("rs-ai-loading")).to_be_hidden()

    # MutationObserver must have recorded that rsAiLoading was shown during
    # the in-flight period.
    was_seen = page.evaluate("() => window.__aiLoadingWasSeen")
    assert was_seen, "rsAiLoading was never made visible during the AI request"


def test_saved_token_report_shows_resolved_range(nexora_server, page):
    # Seed an admin source backed by dbo.Reports (NexoraDB — always available in
    # TEST) with a grainable date column, so we can save + run a token report
    # without depending on external DBs (Octo/Generali/Statistics).
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
            code: 'tok_reports', kind: 'curated', label: 'Token Test Reports',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Reports',
            columns: [
              {field: 'Name', label: 'Name', type: 'string',
               filterable: true, sortable: true},
              {field: 'CreatedAt', label: 'Created', type: 'date',
               filterable: true, sortable: true, grainable: true}
            ],
            enabled: true, sortOrder: 50});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'tok_reports_count', sourceId: 'tok_reports',
            label: 'Token report count', aggregation: 'count', format: 'int'});
          const rpt = await post('/api/reporting/reports', {
            name: 'e2e token range report',
            definition: {
              schemaVersion: 1, source: 'tok_reports', visualization: 'table',
              title: 'e2e token range report',
              columns: [{field: 'Name'}],
              filters: [{field: 'CreatedAt', op: 'between',
                         value: {token: 'last_month'}}],
              sort: [], scope: {clients: [], processes: []}, rowLimit: 100}});
          return {src: src.id, met: met.id, rpt: rpt.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        # Open it from the library — the resolved-range line must appear regardless
        # of whether there are matching rows.
        page.get_by_test_id("rs-group-mine").get_by_text("e2e token range report").click()
        expect(page.get_by_test_id("rs-msg")).to_be_visible()
        expect(page.get_by_test_id("rs-msg")).to_contain_text("→")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              if (ids.rpt) await del('/api/reporting/reports/' + ids.rpt);
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_refine_sends_prior_context_and_replaces_result(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    seen = []

    def handler(route):
        payload = route.request.post_data_json
        seen.append(payload)
        # First call: return the base stub definition so it gets stored as the
        # prior; second call: return the refined title so the result updates.
        if len(seen) == 1:
            defn = STUB_AI_DEFINITION
            expl = "stubbed explanation"
        else:
            defn = dict(STUB_AI_DEFINITION, title="refined report")
            expl = "refined expl"
        body = json.dumps({"definition": defn, "explanation": expl, "valid": True, "error": None})
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-refine-bar")).to_be_visible()
    # The bar is pre-filled with the asked question.
    expect(page.get_by_test_id("rs-refine-input")).to_have_value("docs by process")

    page.get_by_test_id("rs-refine-input").fill("only acme please")
    page.get_by_test_id("rs-refine").click()
    expect(page.get_by_test_id("rs-result-title")).to_contain_text("refined report")
    assert seen[0].get("priorQuestion") is None
    assert seen[1]["priorQuestion"] == "docs by process"
    assert seen[1]["priorDefinition"]["title"] == "stub ai report"
    assert seen[1]["question"] == "only acme please"


def test_chips_edit_and_remove_rerun_without_ai(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    _stub_ai_build(page)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    chips = page.get_by_test_id("rs-chips")
    expect(chips).to_be_visible()
    # STUB_AI_DEFINITION has filters: [{field: "processname", op: "eq", value: "acme.inv"}]
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("processname eq acme.inv")

    # Edit the filter value in place; the run payload must carry the new value.
    run_payloads = []

    def _capture_run(route):
        run_payloads.append(route.request.post_data_json)
        route.continue_()

    page.route("**/api/reporting/run", _capture_run)
    chips.get_by_test_id("rs-chip").first.click()
    page.get_by_test_id("rs-chip-input").fill("acme.other")
    page.get_by_test_id("rs-chip-apply").click()
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("acme.other")
    assert any(
        p.get("filters") and p["filters"][0].get("value") == "acme.other" for p in run_payloads
    )

    # Remove the filter chip entirely -> "no filters" placeholder renders.
    chips.get_by_test_id("rs-chip-remove").first.click()
    expect(chips).to_contain_text("no filters")


def test_wizard_result_shows_chips_and_refine_bar(nexora_server, page):
    """After a wizard run, chips and refine bar appear (not just for AI-built results)."""
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
            code: 'wiz_chips', kind: 'curated', label: 'Wizard Chips',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 11});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_chips_count', sourceId: 'wiz_chips', label: 'Wizard chips count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Wizard chips count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()

        # Chips and refine bar are now visible for wizard results too.
        chips = page.locator("#rsChips")
        expect(chips).to_be_visible()
        expect(page.get_by_test_id("rs-refine-input")).to_be_visible()

        # The wizard adds no filters, so the "no filters" placeholder chip renders.
        expect(chips).to_contain_text("no filters")

        # The refine input starts empty for a wizard result (no aiQuestion).
        expect(page.get_by_test_id("rs-refine-input")).to_have_value("")

        # Stub the AI build endpoint so refine works without a live AI key.
        refined_def = dict(STUB_AI_DEFINITION, title="wizard refined report", source="wiz_chips")
        seen_payloads = []

        def _ai_handler(route):
            seen_payloads.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "definition": refined_def,
                        "explanation": "refined from wizard",
                        "valid": True,
                        "error": None,
                    }
                ),
            )

        page.route("**/api/reporting/ai/build", _ai_handler)

        # Refine: fill the input and submit — must send priorDefinition but NO priorQuestion.
        page.get_by_test_id("rs-refine-input").fill("only compass")
        page.get_by_test_id("rs-refine").click()
        expect(page.get_by_test_id("rs-result-title")).to_contain_text("wizard refined report")

        assert len(seen_payloads) == 1
        payload = seen_payloads[0]
        assert payload.get("priorDefinition") is not None, "priorDefinition must be sent"
        assert (
            "priorQuestion" not in payload or payload.get("priorQuestion") is None
        ), "priorQuestion must be absent for wizard result refine"
        assert payload["question"] == "only compass"
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


def test_adjust_wizard_button_round_trip(nexora_server, page):
    """Wizard-built result shows 'Adjust in wizard'; clicking it re-opens the
    walkthrough with the previous measure choice pre-selected; running again
    re-renders the result."""
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
            code: 'wiz_adjust', kind: 'curated', label: 'Wizard Adjust',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 12});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_adjust_count', sourceId: 'wiz_adjust', label: 'Wizard adjust count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        # Run the wizard once to get a wizard-built result.
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Wizard adjust count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()

        # The "Adjust in wizard" button must be visible for wizard-built results.
        adjust_btn = page.get_by_test_id("rs-adjust-wizard")
        expect(adjust_btn).to_be_visible()

        # Click it — the wizard view opens again.
        adjust_btn.click()
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()

        # The previous measure choice is still selected (is-selected class).
        expect(page.locator(".reporting-simple-choice.is-selected").first).to_be_visible()

        # Run again — the result re-renders successfully.
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()

        # The "Adjust in wizard" button is still present on the new result.
        expect(page.get_by_test_id("rs-adjust-wizard")).to_be_visible()
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


def test_total_only_result_explains_missing_chart(nexora_server, page):
    """A 'None — just the total' wizard run shows the number card plus a
    note explaining why there is no chart."""
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
            code: 'wiz_total_note', kind: 'curated', label: 'Wizard Total Note',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 14});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_total_note_count', sourceId: 'wiz_total_note', label: 'Total note count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Total note count").click()
        # pick "None — just the total" (the last button in breakdown list)
        page.get_by_test_id("rs-breakdown-list").get_by_role(
            "button", name=re.compile(r"just the total", re.I)
        ).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-stat-card")).to_be_visible()
        expect(page.get_by_test_id("rs-msg")).to_contain_text("single total")
        expect(page.get_by_test_id("rs-chart-card")).to_be_hidden()
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


def test_chart_type_switcher(nexora_server, page):
    """The result chart card offers bar/line/pie/doughnut switching."""
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
            code: 'wiz_chart_switch', kind: 'curated', label: 'Wizard Chart Switch',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 15});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_chart_switch_count', sourceId: 'wiz_chart_switch', label: 'Chart switch count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Chart switch count").click()
        # pick the first category breakdown (not 'just the total')
        page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-chart-card")).to_be_visible()
        expect(page.get_by_test_id("rs-chart-tools")).to_be_visible()
        page.get_by_test_id("rs-chart-pie").click()
        expect(page.get_by_test_id("rs-chart-pie")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#rsChartCanvas")).to_be_visible()
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


def test_saved_report_adjust_in_wizard(nexora_server, page):
    """A wizard-shaped SAVED report re-enters the wizard with choices restored,
    even in a fresh session (no in-memory wizard state)."""
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
            code: 'wiz_saved_adj', kind: 'curated', label: 'Wizard Saved Adjust',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 16});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_saved_adj_count', sourceId: 'wiz_saved_adj', label: 'Saved adjust count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        # Build + save via wizard
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Saved adjust count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        # Save the report: first click reveals the name input, second click saves
        page.get_by_test_id("rs-save").click()
        save_name_input = page.get_by_test_id("rs-save-name")
        expect(save_name_input).to_be_visible()
        save_name_input.fill("adjust-saved-e2e")
        page.get_by_test_id("rs-save").click()
        # Wait for the save confirmation message before navigating away
        expect(page.get_by_test_id("rs-msg")).to_be_visible()
        # Fresh page load wipes state.wiz
        page.goto(f"{nexora_server}/reporting?tab=simple")
        # Wait for library to load and report to appear
        expect(page.get_by_test_id("rs-group-mine").get_by_text("adjust-saved-e2e")).to_be_visible()
        page.get_by_test_id("rs-group-mine").get_by_text("adjust-saved-e2e").click()
        adjust = page.get_by_test_id("rs-adjust-wizard")
        expect(adjust).to_be_visible()
        adjust.click()
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        # The previously chosen measure renders pre-selected
        expect(page.locator(".reporting-simple-choice.is-selected").first).to_be_visible()
    finally:
        # Clean up metric + source
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )
        # Delete the saved report by name
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.evaluate(
            """async () => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const res = await fetch('/api/reporting/reports').then(r => r.json());
              const r = (res || []).find(x => x.name === 'adjust-saved-e2e');
              if (r) await fetch('/api/reporting/reports/' + r.id, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
            }"""
        )


def test_show_query_reveals_sql(nexora_server, page):
    """A result offers Show query, revealing the executed SELECT."""
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
            code: 'wiz_showsql', kind: 'curated', label: 'Show SQL Test',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 18});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_showsql_count', sourceId: 'wiz_showsql', label: 'Show SQL count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Show SQL count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        show = page.get_by_test_id("rs-show-sql")
        expect(show).to_be_visible()
        # Collapsed by default: the panel is hidden until the user expands it.
        sql_view = page.get_by_test_id("rs-sql-view")
        expect(sql_view).to_be_hidden()
        show.click()
        expect(sql_view).to_be_visible()
        expect(page.locator("#rsSqlText")).to_contain_text("SELECT")
        # Pretty-printed (multi-line) and token-highlighted.
        assert "\n" in page.locator("#rsSqlText").inner_text()
        assert page.locator("#rsSqlText span.sql-kw").count() > 0
        # Second click re-collapses.
        show.click()
        expect(sql_view).to_be_hidden()
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


def test_result_back_returns_to_wizard(nexora_server, page):
    """Back on a wizard-built result re-enters the wizard; X exits to library."""
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
            code: 'wiz_back_test', kind: 'curated', label: 'Wizard Back Test',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 17});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_back_count', sourceId: 'wiz_back_test', label: 'Back test count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Back test count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        # Back on a wizard result re-enters the wizard
        page.get_by_test_id("rs-back").click()
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        # X (wizard close) exits to library
        page.get_by_test_id("rs-wizard-close").click()
        expect(page.get_by_test_id("rs-library")).to_be_visible()
        # Now open a fresh wizard result and use rs-exit from the result bar
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Back test count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        page.get_by_test_id("rs-exit").click()
        expect(page.get_by_test_id("rs-library")).to_be_visible()
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


def test_wizard_two_breakdowns(nexora_server, page):
    """Two category breakdowns produce a 3-column grouped result."""
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
            code: 'wiz_two_bds', kind: 'curated', label: 'Wizard Two Breakdowns',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [
              {field: 'username', label: 'Username', type: 'string',
               filterable: true, sortable: true},
              {field: 'locale', label: 'Locale', type: 'string',
               filterable: true, sortable: true}
            ],
            enabled: true, sortOrder: 19});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_two_bds_count', sourceId: 'wiz_two_bds', label: 'Two-bd count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Two-bd count").click()
        bklist = page.get_by_test_id("rs-breakdown-list")
        bklist.get_by_text("Username", exact=True).click()
        bklist.get_by_text("Locale", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        # Table is hidden behind the toggle when there are metrics; reveal it.
        page.get_by_test_id("rs-table-toggle").click()
        headers = page.locator("#rsTableWrap table thead th")
        expect(headers).to_have_count(3)  # dim1, dim2, metric
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


def test_two_breakdown_chart_has_series(page, nexora_server):
    """A two-breakdown result charts with one dataset per second-dim value."""
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
            code: 'chart_two_bd', kind: 'curated', label: 'Chart Two Breakdown',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [
              {field: 'username', label: 'Username', type: 'string',
               filterable: true, sortable: true},
              {field: 'locale', label: 'Locale', type: 'string',
               filterable: true, sortable: true}
            ],
            enabled: true, sortOrder: 20});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'chart_two_bd_count', sourceId: 'chart_two_bd', label: 'Chart 2-bd count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Chart 2-bd count").click()
        bklist = page.get_by_test_id("rs-breakdown-list")
        # Locale first (X axis, 1 distinct value in TEST), Username second
        # (series dimension, 3 distinct values in TEST) — guarantees >= 2 series.
        bklist.get_by_text("Locale", exact=True).click()
        bklist.get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        canvas = page.locator("#rsChartCanvas")
        expect(canvas).to_be_visible()
        series = int(canvas.get_attribute("data-series"))
        assert series >= 2
        expect(page.get_by_test_id("rs-chart-stacked")).to_be_visible()
        expect(page.get_by_test_id("rs-chart-pie")).to_be_hidden()
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


def test_chart_png_download(page, nexora_server):
    """The chart toolbar PNG button downloads a .png file of the current chart."""
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
            code: 'chart_png_dl', kind: 'curated', label: 'Chart PNG Download',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [
              {field: 'locale', label: 'Locale', type: 'string',
               filterable: true, sortable: true}
            ],
            enabled: true, sortOrder: 21});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'chart_png_dl_count', sourceId: 'chart_png_dl', label: 'PNG dl count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("PNG dl count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Locale", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-chart-card")).to_be_visible()
        with page.expect_download() as dl:
            page.get_by_test_id("rs-chart-png").click()
        assert dl.value.suggested_filename.endswith("-chart.png")
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


def test_sqlformat_escapes_and_highlights(nexora_server, page):
    """ReportingSqlFormat.toHtml escapes every emitted piece (no raw HTML can
    reach innerHTML) and wraps tokens in classed spans."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    html = page.evaluate(
        "() => ReportingSqlFormat.toHtml(\"SELECT [a] FROM t WHERE x = '<script>' -- note\")"
    )
    assert "<script>" not in html  # escaped, not injected
    assert "&lt;script&gt;" in html
    assert '<span class="sql-kw">SELECT</span>' in html
    assert '<span class="sql-ident">[a]</span>' in html
    assert '<span class="sql-comment">-- note</span>' in html
    assert '<span class="sql-string">' in html


def test_sqlformat_marks_placeholders_and_numbers(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    html = page.evaluate(
        "() => ReportingSqlFormat.toHtml('SELECT TOP 100 * FROM t WHERE a >= ? AND b < ?')"
    )
    assert html.count('<span class="sql-param">?</span>') == 2
    assert '<span class="sql-number">100</span>' in html


def test_simple_truncation_note(nexora_server, page):
    """A library report with rowLimit:1 over dbo.Users triggers truncation; the
    rs-msg element must contain 'first 1'."""
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
            code: 'trunc_users', kind: 'curated', label: 'Truncation Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 30});
          const rpt = await post('/api/reporting/reports', {
            name: 'e2e trunc note',
            definition: {
              schemaVersion: 1, source: 'trunc_users', visualization: 'table',
              title: 'e2e trunc note',
              columns: [{field: 'username'}],
              filters: [], sort: [],
              scope: {clients: [], processes: []},
              rowLimit: 1}});
          return {src: src.id, rpt: rpt.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-group-mine").get_by_text("e2e trunc note").click()
        expect(page.locator("#rsResult table")).to_be_visible(timeout=15000)
        expect(page.get_by_test_id("rs-msg")).to_contain_text("first 1")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              if (ids.rpt) await del('/api/reporting/reports/' + ids.rpt);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_advanced_truncation_note_renders(nexora_server, page):
    """Advanced result view: when /api/reporting/run returns truncated=true and
    rowCount=5000, a .reporting-truncated-note element containing '5000' renders
    above the table."""
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
            code: 'trunc_adv', kind: 'curated', label: 'Truncation Advanced',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 31});
          return {src: src.id};
        }"""
    )
    try:
        # Stub /run to return a truncated response with synthetic data.
        stub_body = json.dumps(
            {
                "columns": [{"field": "username", "header": "Username"}],
                "rows": [["alice"]],
                "truncated": True,
                "rowCount": 5000,
                "sql": None,
                "params": [],
                "resolvedDates": [],
            }
        )

        def _stub_run(route):
            route.fulfill(status=200, content_type="application/json", body=stub_body)

        page.route("**/api/reporting/run", _stub_run)

        # Use applyDefinition to pre-populate the builder, then click Run.
        page.wait_for_selector("[data-testid='reporting-field-panel']", state="visible")
        page.evaluate(
            """() => {
              if (window.Reporting && window.Reporting.applyDefinition) {
                window.Reporting.applyDefinition({
                  schemaVersion: 1, source: 'trunc_adv', visualization: 'table',
                  title: 'trunc adv test',
                  columns: [{field: 'username'}],
                  filters: [], sort: [],
                  scope: {clients: [], processes: []}, rowLimit: 5000
                }, 'trunc adv test', null);
              }
            }"""
        )
        page.get_by_test_id("reporting-run").click()
        note = page.locator(".reporting-truncated-note")
        expect(note).to_be_visible()
        expect(note).to_contain_text("5000")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


# ---------------------------------------------------------------------------
# Task 7: This week / This quarter wizard presets + WIZ_TOKENS round-trip
# ---------------------------------------------------------------------------

WIZ_STUB_SOURCES = [
    {
        "id": "stub_src",
        "label": "Stub source",
        "kind": "curated",
        "processes": [],
        "fields": [
            {
                "field": "import_date",
                "label": "Import date",
                "type": "date",
                "grainable": True,
                "filterable": True,
            },
            {
                "field": "doctype",
                "label": "Doc type",
                "type": "string",
                "grainable": False,
                "filterable": True,
            },
        ],
    }
]
WIZ_STUB_METRICS = {
    "stub_src": [
        {"code": "stub_count", "label": "Stub count", "aggregation": "count"},
    ]
}


def _stub_catalogs(page):
    # MUST be registered before page.goto: the Simple pane fetches the metrics
    # catalog in initOnce() at rp:tabshown (page load), not at first wizard open.
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(WIZ_STUB_SOURCES)
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(WIZ_STUB_METRICS)
        ),
    )


def test_wizard_time_step_offers_week_and_quarter(nexora_server, page):
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-breakdown-next").click()
    tl = page.get_by_test_id("rs-time-list")
    expect(tl.get_by_text("This week", exact=True)).to_be_visible()
    expect(tl.get_by_text("This quarter", exact=True)).to_be_visible()


def test_adjust_in_wizard_maps_this_quarter(nexora_server, page):
    """A non-wizard def filtered on {token: this_quarter} keeps 'Adjust in wizard'."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    # Warm the sources cache (fetched lazily at first wizard open; the adjust
    # check reads state.sources/state.metricsBySource).
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-wizard-close").click()
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [{"field": "stub_count", "header": "Stub count"}],
                    "rows": [[7]],
                    "rowCount": 1,
                    "truncated": False,
                    "sql": "SELECT 7",
                    "params": [],
                }
            ),
        ),
    )
    _stub_ai_build(
        page,
        definition={
            "schemaVersion": 1,
            "source": "stub_src",
            "visualization": "table",
            "title": "quarter stub",
            "subtitle": None,
            "columns": [],
            "metrics": [{"metric": "stub_count"}],
            "filters": [
                {"field": "import_date", "op": "between", "value": {"token": "this_quarter"}}
            ],
            "sort": [],
            "scope": {"clients": [], "processes": []},
            "rowLimit": 5000,
        },
    )
    page.get_by_test_id("rs-ai-prompt").fill("total this quarter")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-adjust-wizard")).to_be_visible()


def test_wizard_back_steps_back_not_exit(nexora_server, page):
    """Back walks time -> breakdown -> measure -> library, preserving picks."""
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
            code: 'back_users', kind: 'curated', label: 'Back Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 31});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'back_user_count', sourceId: 'back_users', label: 'Back user count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Back user count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        expect(page.get_by_test_id("rs-wizard-run")).to_be_visible()

        back = page.get_by_test_id("rs-wizard-back")
        back.click()  # time step -> breakdown step
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        expect(page.get_by_test_id("rs-wizard-run")).to_be_hidden()
        expect(page.locator("#rsStepBreakdown")).to_be_visible()

        back.click()  # breakdown step -> measure step
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        expect(page.locator("#rsStepBreakdown")).to_be_hidden()

        back.click()  # measure step -> library
        expect(page.get_by_test_id("rs-wizard")).to_be_hidden()
        expect(page.get_by_test_id("rs-new-report")).to_be_visible()
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


def test_run_shows_loading_then_result(nexora_server, page):
    """The pulsing run indicator appears while /api/reporting/run is in flight
    and is hidden once the result cards render. Localhost runs are fast, so
    visibility is latched with a MutationObserver (same idiom as the AI test)."""
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
            code: 'wiz_runload', kind: 'curated', label: 'Run Load Test',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 19});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_runload_count', sourceId: 'wiz_runload', label: 'Run load count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.evaluate("""() => {
            window.__runLoadingWasSeen = false;
            const el = document.getElementById('rsRunLoading');
            if (!el) return;
            if (!el.hidden) { window.__runLoadingWasSeen = true; return; }
            const obs = new MutationObserver(() => {
                if (!el.hidden) {
                    window.__runLoadingWasSeen = true;
                    obs.disconnect();
                }
            });
            obs.observe(el, { attributes: true, attributeFilter: ['hidden'] });
        }""")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Run load count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        # rs-show-sql appears only after the MAIN run response is processed,
        # which is strictly after the indicator is hidden.
        expect(page.get_by_test_id("rs-show-sql")).to_be_visible()
        expect(page.get_by_test_id("rs-run-loading")).to_be_hidden()
        expect(page.get_by_test_id("rs-stat-card")).to_be_visible()
        assert page.evaluate(
            "() => window.__runLoadingWasSeen"
        ), "rsRunLoading never became visible during the report run"
        page.screenshot(path="var/screenshots/reporting_simple_run_loading.png")
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


def test_advanced_ai_ask_shows_loading(nexora_server, page):
    """The Advanced AI panel shows the pulsing indicator while a request is in
    flight and hides it when the draft arrives (today it only disables Ask)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.get_by_test_id("reporting-mode-ai").click()
    page.evaluate("""() => {
        window.__aiPanelLoadingWasSeen = false;
        const el = document.getElementById('rpAiLoading');
        if (!el) return;
        if (!el.hidden) { window.__aiPanelLoadingWasSeen = true; return; }
        const obs = new MutationObserver(() => {
            if (!el.hidden) {
                window.__aiPanelLoadingWasSeen = true;
                obs.disconnect();
            }
        });
        obs.observe(el, { attributes: true, attributeFilter: ['hidden'] });
    }""")
    _stub_ai_build(page, delay_s=0.8)
    page.get_by_test_id("reporting-ai-prompt").fill("docs by process")
    page.get_by_test_id("reporting-ai-ask").click()
    expect(page.get_by_test_id("reporting-ai-def-result")).to_be_visible()
    expect(page.get_by_test_id("reporting-ai-loading")).to_be_hidden()
    assert page.evaluate(
        "() => window.__aiPanelLoadingWasSeen"
    ), "rpAiLoading never became visible during the AI request"
    page.screenshot(path="var/screenshots/reporting_advanced_ai_loading.png")


def test_simple_export_csv(nexora_server, page):
    """The Simple export control downloads CSV when the format select says so."""
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
            code: 'csv_dl_users', kind: 'curated', label: 'CSV dl Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 32});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'csv_dl_count', sourceId: 'csv_dl_users', label: 'CSV dl count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("CSV dl count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        page.get_by_test_id("rs-export-format").select_option("csv")
        with page.expect_download() as dl:
            page.get_by_test_id("rs-export").click()
        assert dl.value.suggested_filename.endswith(".csv")
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
