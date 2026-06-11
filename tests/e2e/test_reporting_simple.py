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
