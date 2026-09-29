"""nx_lib/permission_docs.py -- the derived half of the permission detail page.

The point of the module is that it cannot disagree with the code, so these
tests pin the derivation rather than any particular catalogue content: a route
map built here, and the real source tree for the scan.
"""

import pytest
from flask import Flask

from nx_lib import permission_docs
from nx_lib.security import require_any_permission, require_permission


@pytest.fixture
def app():
    """A throwaway app whose views carry the same decorators the real ones do."""
    application = Flask(__name__)

    @require_permission("admin.things.view")
    def things_page():
        return ""

    @require_permission("admin.things.edit")
    def things_save():
        return ""

    @require_permission("admin.things.view")
    def things_detail(thing):
        return ""

    @require_any_permission("admin.things.view", "admin.other.view")
    def things_either():
        return ""

    def unguarded():
        return ""

    application.add_url_rule("/admin/things", "things_page", things_page)
    application.add_url_rule("/api/admin/things/save", "things_save", things_save, methods=["POST"])
    application.add_url_rule("/admin/things/<thing>", "things_detail", things_detail)
    application.add_url_rule("/admin/either", "things_either", things_either)
    application.add_url_rule("/public", "unguarded", unguarded)
    return application


def _index(app):
    return permission_docs.routes_index(app.url_map, app.view_functions)


# --- route derivation ------------------------------------------------------


def test_routes_index_reads_the_decorator_not_a_hand_written_list(app):
    index = _index(app)
    rules = {r["rule"] for r in index["admin.things.view"]}
    assert rules == {"/admin/things", "/admin/things/<thing>", "/admin/either"}
    assert [r["rule"] for r in index["admin.things.edit"]] == ["/api/admin/things/save"]


def test_unguarded_routes_are_absent(app):
    assert all("/public" not in {r["rule"] for r in rs} for rs in _index(app).values())


def test_only_an_argument_free_html_get_counts_as_a_page(app):
    """`page` drives a clickable link and a screenshot, so it must exclude what
    cannot be opened: a rule with arguments, a POST, and an /api route."""
    by_rule = {r["rule"]: r for r in _index(app)["admin.things.view"]}
    assert by_rule["/admin/things"]["page"] is True
    assert by_rule["/admin/things/<thing>"]["page"] is False  # needs an argument
    save = _index(app)["admin.things.edit"][0]
    assert save["page"] is False  # POST, and under /api/


def test_api_get_is_not_a_page():
    application = Flask(__name__)

    @require_permission("workitems.view")
    def api_list():
        return ""

    application.add_url_rule("/api/workitems", "api_list", api_list)
    entry = permission_docs.routes_index(application.url_map, application.view_functions)[
        "workitems.view"
    ][0]
    assert entry["methods"] == ["GET"]
    assert entry["page"] is False


def test_any_of_names_the_alternatives(app):
    either = next(r for r in _index(app)["admin.things.view"] if r["rule"] == "/admin/either")
    assert either["any_of"] == ["admin.other.view", "admin.things.view"]
    # A route guarded by a single code must not claim alternatives.
    single = next(r for r in _index(app)["admin.things.view"] if r["rule"] == "/admin/things")
    assert single["any_of"] == []


def test_head_and_options_are_not_reported_as_methods(app):
    assert _index(app)["admin.things.view"][0]["methods"] == ["GET"]


# --- grammar ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "area", "object_label", "action", "scope"),
    [
        ("admin.tenants.view", "admin", "tenants", "view", ""),
        ("admin.view", "admin", "", "view", ""),
        ("workitems.add.pastdeadline", "workitems", "", "add", "pastdeadline"),
        ("reporting.shares.delete.all", "reporting", "shares", "delete", "all"),
        ("tenant.generali.documents.view", "tenant.generali", "documents", "view", ""),
    ],
)
def test_parse_splits_the_code(code, area, object_label, action, scope):
    g = permission_docs.parse(code)
    assert (g["area"], g["object_label"], g["action"], g["scope"]) == (
        area,
        object_label,
        action,
        scope,
    )


def test_an_area_level_code_does_not_list_its_own_gate_twice():
    """`reporting.export` sits on the area, so object.view and area.view are the
    same string -- it must be offered once, not twice."""
    assert permission_docs.parse("reporting.export")["gate_candidates"] == ["reporting.view"]


def test_a_view_code_is_not_its_own_gate():
    assert permission_docs.parse("admin.view")["gate_candidates"] == []
    assert permission_docs.parse("admin.tenants.view")["gate_candidates"] == ["admin.view"]


# --- source scan -----------------------------------------------------------


def test_usage_index_finds_a_template_check():
    """reporting.export is checked in a template, which is what "where does this
    show in the UI" is built from."""
    hits = permission_docs.usage_index().get("reporting.export", [])
    assert any(h["kind"] == "template" for h in hits)
    assert all(h["line"] > 0 and h["snippet"] for h in hits)


def test_usage_index_follows_page_visibility_indirection():
    """Templates read page_visibility flags rather than calling has_permission,
    so a literal-only scan reports "used nowhere" for exactly the codes that
    gate a page."""
    hits = permission_docs.usage_index().get("admin.tenants.view", [])
    templates = [h for h in hits if h["kind"] == "template"]
    assert templates, "expected the page_visibility flag to be followed into templates"
    assert any("adminTenantsPagePerm" in h["snippet"] for h in templates)


def test_visibility_keys_maps_flags_to_codes():
    keys = permission_docs.visibility_keys()
    assert keys["adminTenantsPagePerm"] == "admin.tenants.view"
    assert keys["workitemsPagePerm"] == "workitems.view"


def test_the_scan_does_not_index_its_own_vocabulary():
    """permission_docs.py names actions and scopes to build its regex; indexing
    those would make every code look used."""
    for hits in permission_docs.usage_index().values():
        assert all(h["file"] != "nx_lib/permission_docs.py" for h in hits)


def test_describe_separates_ui_from_code_usages(app):
    facts = permission_docs.describe("reporting.export", app.url_map, app.view_functions)
    assert all(u["kind"] == "template" for u in facts["ui_usages"])
    assert all(u["kind"] == "code" for u in facts["code_usages"])
    assert facts["unused"] is False


def test_describe_flags_a_code_nothing_uses(app):
    facts = permission_docs.describe("nosuch.thing.view", app.url_map, app.view_functions)
    assert facts["unused"] is True
    assert facts["routes"] == [] and facts["ui_usages"] == []


def test_screenshot_is_none_for_a_code_without_one():
    assert permission_docs.screenshot_for("nosuch.thing.view") is None


def test_screenshot_path_is_static_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(permission_docs, "_ROOT", tmp_path)
    shots = tmp_path / "static" / "img" / "permissions"
    shots.mkdir(parents=True)
    (shots / "admin.view.jpg").write_bytes(b"x")
    assert permission_docs.screenshot_for("admin.view") == "img/permissions/admin.view.jpg"
