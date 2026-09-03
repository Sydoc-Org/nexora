"""Pure validators behind the tenant management page (views/admin/tenant_manage.py)."""

from werkzeug.routing import Map, Rule

from nx_lib.views.admin.tenant_manage import (
    mountable_endpoints,
    validate_page_payload,
    validate_tenant_payload,
)

MOUNTABLE = ["dashboard", "workitems_overview"]


def test_tenant_payload_ok():
    data = {
        "TenantCode": "acme",
        "DisplayName": "Acme",
        "ClientCode": "default",
        "organizations": ["ACME", "acm2"],
    }
    assert validate_tenant_payload(data, require_code=True) == []


def test_tenant_payload_rejects_bad_code_missing_name_and_bad_orgs(app):
    with app.test_request_context("/"):
        errors = validate_tenant_payload(
            {
                "TenantCode": "Bad Code!",
                "DisplayName": "",
                "ClientCode": "",
                "organizations": "ACME",
            },
            require_code=True,
        )
    assert len(errors) == 4  # code, name, connection, organizations


def test_tenant_payload_code_optional_on_edit():
    data = {"DisplayName": "Acme", "ClientCode": "default", "organizations": []}
    assert validate_tenant_payload(data, require_code=False) == []


def test_page_payload_ok_and_defaults():
    data = {
        "PageKey": "dashboard",
        "endpoint": "dashboard",
        "label": "Dashboard",
        "SortOrder": "10",
    }
    assert validate_page_payload(data, MOUNTABLE) == []


def test_page_payload_rejects_unmountable_endpoint_and_bad_icon(app):
    data = {
        "PageKey": "x",
        "endpoint": "api_secret",
        "label": "X",
        "icon": "chart-line",
        "active": "has space",
        "SortOrder": "ten",
    }
    with app.test_request_context("/"):
        errors = validate_page_payload(data, MOUNTABLE)
    assert len(errors) == 4  # endpoint, icon, active, sort order


def test_mountable_endpoints_are_argless_get_pages_only():
    m = Map(
        [
            Rule("/dashboard", endpoint="dashboard", methods=["GET"]),
            Rule("/api/x", endpoint="api_x", methods=["GET"]),
            Rule("/w/<int:i>", endpoint="workitem_detail", methods=["GET"]),
            Rule("/post", endpoint="post_only", methods=["POST"]),
            Rule("/static/<path:f>", endpoint="static", methods=["GET"]),
            Rule("/t/<c>/<p>", endpoint="tenant_page", methods=["GET"]),
            Rule("/reporting", endpoint="reporting", methods=["GET"]),
        ]
    )
    assert mountable_endpoints(m) == ["dashboard", "reporting"]
