"""Admin tenant management (#256 phase 2): create/edit tenants, decide which
organizations belong to them, and mount pages.

What is editable here:
  - the ``dbo.Tenants`` row (display name, data connection, active flag);
  - membership -- ``Organizations.TenantCode`` for every organization (0090);
  - ``dbo.TenantPages`` rows of type ``custom`` (an existing endpoint mounted
    into the tenant's sidebar group), plus the active/draft switch and removal
    for any page.

What stays migration-only, on purpose: ``TenantEntities`` / ``TenantFields``
and the ``list``/``crud`` pages built on them -- those carry SQL identifiers
that the query builders interpolate, and the registry's identifier validation
is the single gate for them today. The page shows them read-only.

Every write invalidates the cached tenant registry, so the sidebar and the
overview follow within the request (the 60 s TTL is for reads that missed
the invalidation, e.g. another process).
"""

import json
import re

from flask import current_app, jsonify, render_template, request, session, url_for
from flask_babel import gettext as _
from werkzeug.routing import BuildError

from ...db import engine_nexora_db
from ...security import has_permission, page_visibility, require_permission
from ...tenant.registry import invalidate_tenant_config, provision_tenant_permissions

_TENANT_CODE_RE = re.compile(r"^[a-z0-9_]{2,50}$")
_ORG_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,5}$")
_PAGE_KEY_RE = re.compile(r"^[a-z0-9_.-]{1,100}$")
_ICON_RE = re.compile(r"^fa-[a-z0-9-]{1,40}$")
_ACTIVE_RE = re.compile(r"^[A-Za-z0-9_-]{0,60}$")
_DEFAULT_ICON = "fa-arrow-up-right-from-square"
# Endpoints that never make sense as a sidebar mount: JSON APIs, static files,
# dev-only helpers, the generated tenant pages themselves, auth plumbing.
_UNMOUNTABLE_PREFIXES = ("api_", "static", "dev_", "tenant_", "login", "logout", "auth")


def _rows(cursor, sql, params=()):
    cursor.execute(sql, params)
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]


def mountable_endpoints(url_map):
    """Endpoint names a custom tenant page may point at: GET routes that take
    no URL arguments (``url_for(endpoint)`` must build without kwargs, which is
    what the nav resolver calls), minus the families that are never pages."""
    names = set()
    for rule in url_map.iter_rules():
        if rule.arguments or "GET" not in (rule.methods or ()):
            continue
        ep = rule.endpoint
        if ep.startswith(_UNMOUNTABLE_PREFIXES) or "." in ep:
            continue
        names.add(ep)
    return sorted(names)


def validate_tenant_payload(data, *, require_code):
    """Error messages for a tenant add/edit payload; [] when valid. The
    referential check (organizations exist) happens against the DB in the
    endpoint -- this is the shape check."""
    errors = []
    code = (data.get("TenantCode") or "").strip()
    if (require_code or code) and not _TENANT_CODE_RE.match(code):
        errors.append(_("Tenant code must be 2-50 lowercase letters, digits or underscores."))
    name = (data.get("DisplayName") or "").strip()
    if not name or len(name) > 100:
        errors.append(_("Display name is required (max. 100 characters)."))
    orgs = data.get("organizations") or []
    if not isinstance(orgs, list) or any(
        not isinstance(o, str) or not _ORG_CODE_RE.match(o) for o in orgs
    ):
        errors.append(_("Organizations must be a list of organization codes."))
    return errors


def validate_page_payload(data, mountable):
    """Error messages for a custom-page payload; [] when valid. ``mountable``
    is the endpoint allow-list from mountable_endpoints()."""
    errors = []
    key = (data.get("PageKey") or "").strip()
    if not _PAGE_KEY_RE.match(key):
        errors.append(_("Page key must be 1-100 lowercase letters, digits, '.', '_' or '-'."))
    endpoint = (data.get("endpoint") or "").strip()
    if endpoint not in mountable:
        errors.append(_("Endpoint is not a mountable page."))
    label = (data.get("label") or "").strip()
    if not label or len(label) > 100:
        errors.append(_("Label is required (max. 100 characters)."))
    icon = (data.get("icon") or "").strip()
    if icon and not _ICON_RE.match(icon):
        errors.append(_("Icon must be a Font Awesome class like fa-chart-line."))
    active = (data.get("active") or "").strip()
    if not _ACTIVE_RE.match(active):
        errors.append(_("Active marker may only contain letters, digits, '_' or '-'."))
    try:
        int(data.get("SortOrder") or 100)
    except (TypeError, ValueError):
        errors.append(_("Sort order must be a number."))
    return errors


# endpoint -> active-marker suffix for pages that take a ?tenant= scope
_SCOPED_ENDPOINTS = {"dashboard": "dashboard", "workitems_overview": "workitems"}


def _layout_json(data, tenant_code):
    layout = {
        "endpoint": (data.get("endpoint") or "").strip(),
        "label": (data.get("label") or "").strip(),
        "icon": (data.get("icon") or "").strip() or _DEFAULT_ICON,
    }
    active = (data.get("active") or "").strip()
    if active:
        layout["active"] = active
    marker = _SCOPED_ENDPOINTS.get(layout["endpoint"])
    if marker:
        # 0097/0098: a mounted Dashboard or Workitems page opens the page scoped
        # to this tenant and owns its active marker -- the shape the seed
        # migrations give existing rows.
        layout["query"] = {"tenant": tenant_code}
        layout["active"] = f"tenant_{tenant_code}_{marker}"
    return json.dumps(layout)


def _error(errors, status=400):
    return jsonify({"success": False, "message": " ".join(str(e) for e in errors)}), status


def _missing_organizations(cursor, org_codes):
    """How many of ``org_codes`` have no dbo.Organizations row. Checked before
    any write so a typo answers 400, not an FK error."""
    if not org_codes:
        return 0
    marks = ",".join("?" * len(org_codes))
    cursor.execute(
        f"SELECT COUNT(*) FROM Organizations WHERE organizationcode IN ({marks})", org_codes
    )
    return len(org_codes) - cursor.fetchone()[0]


def _set_memberships(cursor, code, org_codes):
    """Organizations.TenantCode := code for the given organizations, NULL for
    every organization that used to belong to this tenant and is not listed."""
    if org_codes:
        marks = ",".join("?" * len(org_codes))
        cursor.execute(
            f"UPDATE Organizations SET TenantCode = ? WHERE organizationcode IN ({marks})",
            [code, *org_codes],
        )
        cursor.execute(
            f"UPDATE Organizations SET TenantCode = NULL WHERE TenantCode = ? "
            f"AND organizationcode NOT IN ({marks})",
            [code, *org_codes],
        )
    else:
        cursor.execute("UPDATE Organizations SET TenantCode = NULL WHERE TenantCode = ?", (code,))


# -------------------------------------------------------------------- page --


@require_permission("admin.tenants.view")
def admin_tenants_manage_view():
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        tenants = _rows(
            cursor,
            "SELECT TenantCode, DisplayName, IsActive FROM Tenants ORDER BY DisplayName",
        )
        organizations = _rows(
            cursor,
            "SELECT organizationcode, organization, TenantCode FROM organizations ORDER BY organization",
        )
        pages = _rows(
            cursor,
            "SELECT TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status "
            "FROM TenantPages ORDER BY TenantCode, SortOrder, PageKey",
        )
        for p in pages:
            try:
                p["layout"] = json.loads(p["LayoutJSON"]) if p["LayoutJSON"] else {}
            except ValueError:
                p["layout"] = {}
        for t in tenants:
            t["organizations"] = [o for o in organizations if o["TenantCode"] == t["TenantCode"]]
            t["pages"] = [p for p in pages if p["TenantCode"] == t["TenantCode"]]
            t["IsActive"] = bool(t["IsActive"])

        return render_template(
            "admin/tenants_manage.html",
            tenants=tenants,
            organizations=organizations,
            endpoints=mountable_endpoints(current_app.url_map),
            can_edit=has_permission("admin.tenants.edit"),
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to render tenant management: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# -------------------------------------------------------------- tenants --


@require_permission("admin.tenants.edit")
def api_admin_tenants_add():
    data = request.get_json() or {}
    errors = validate_tenant_payload(data, require_code=True)
    if errors:
        return _error(errors)
    code = data["TenantCode"].strip()
    org_codes = [o.upper() for o in (data.get("organizations") or [])]
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Tenants WHERE TenantCode = ?", (code,))
        if cursor.fetchone():
            return _error([_("Tenant already exists.")], 409)
        missing = _missing_organizations(cursor, org_codes)
        if missing:
            return _error([_("%(n)d organization code(s) do not exist.", n=missing)])
        cursor.execute(
            "INSERT INTO Tenants (TenantCode, DisplayName, IsActive) VALUES (?, ?, ?)",
            (code, data["DisplayName"].strip(), 1 if data.get("IsActive", True) else 0),
        )
        _set_memberships(cursor, code, org_codes)
        provision_tenant_permissions(cursor, code)
        conn.commit()
        invalidate_tenant_config()
        return jsonify(
            {
                "success": True,
                "message": _(
                    "Tenant created. Users of its organizations see it right away; grant "
                    "tenant.%(code)s.view under Access Control to let other staff in.",
                    code=code,
                ),
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error adding tenant {code}: {e}")
        return _error([_("An error occurred.")], 500)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.tenants.edit")
def api_admin_tenants_edit(tenantcode):
    data = request.get_json() or {}
    errors = validate_tenant_payload(data, require_code=False)
    if errors:
        return _error(errors)
    org_codes = [o.upper() for o in (data.get("organizations") or [])]
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        missing = _missing_organizations(cursor, org_codes)
        if missing:
            return _error([_("%(n)d organization code(s) do not exist.", n=missing)])
        cursor.execute(
            "UPDATE Tenants SET DisplayName = ?, IsActive = ? WHERE TenantCode = ?",
            (data["DisplayName"].strip(), 1 if data.get("IsActive", True) else 0, tenantcode),
        )
        if cursor.rowcount == 0:
            return _error([_("Tenant not found.")], 404)
        _set_memberships(cursor, tenantcode, org_codes)
        conn.commit()
        invalidate_tenant_config()
        return jsonify({"success": True, "message": _("Tenant updated.")})
    except Exception as e:
        current_app.logger.error(f"Error editing tenant {tenantcode}: {e}")
        return _error([_("An error occurred.")], 500)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.tenants.edit")
def api_admin_tenants_delete(tenantcode):
    """Refused (409) while organizations still belong to the tenant. Otherwise
    removes the tenant with its page/entity/field descriptors; the
    tenant.<code>.* permission rows stay (harmless, and grants may reference
    them)."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Organizations WHERE TenantCode = ?", (tenantcode,))
        n = (cursor.fetchone() or [0])[0]
        if n:
            return _error(
                [_("%(n)d organization(s) still belong to this tenant. Move them first.", n=n)],
                409,
            )
        cursor.execute("DELETE FROM TenantFields WHERE TenantCode = ?", (tenantcode,))
        cursor.execute("DELETE FROM TenantPages WHERE TenantCode = ?", (tenantcode,))
        cursor.execute("DELETE FROM TenantEntities WHERE TenantCode = ?", (tenantcode,))
        cursor.execute("DELETE FROM Tenants WHERE TenantCode = ?", (tenantcode,))
        deleted = cursor.rowcount
        conn.commit()
        invalidate_tenant_config()
        if deleted == 0:
            return _error([_("Tenant not found.")], 404)
        return jsonify({"success": True, "message": _("Tenant deleted.")})
    except Exception as e:
        current_app.logger.error(f"Error deleting tenant {tenantcode}: {e}")
        return _error([_("An error occurred.")], 500)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ---------------------------------------------------------------- pages --


@require_permission("admin.tenants.edit")
def api_admin_tenant_page_add(tenantcode):
    data = request.get_json() or {}
    mountable = mountable_endpoints(current_app.url_map)
    errors = validate_page_payload(data, mountable)
    if errors:
        return _error(errors)
    try:
        url_for(data["endpoint"].strip())
    except BuildError:
        return _error([_("Endpoint is not a mountable page.")])
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Tenants WHERE TenantCode = ?", (tenantcode,))
        if not cursor.fetchone():
            return _error([_("Tenant not found.")], 404)
        cursor.execute(
            "INSERT INTO TenantPages (TenantCode, PageKey, PageType, EntityKey, LayoutJSON, "
            "SortOrder, Status) VALUES (?, ?, 'custom', NULL, ?, ?, 'active')",
            (
                tenantcode,
                data["PageKey"].strip(),
                _layout_json(data, tenantcode),
                int(data.get("SortOrder") or 100),
            ),
        )
        conn.commit()
        invalidate_tenant_config()
        return jsonify({"success": True, "message": _("Page added.")})
    except Exception as e:
        if "PK_TenantPages" in str(e):
            return _error([_("A page with this key already exists.")], 409)
        current_app.logger.error(f"Error adding page to tenant {tenantcode}: {e}")
        return _error([_("An error occurred.")], 500)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.tenants.edit")
def api_admin_tenant_page_status(tenantcode, pagekey):
    data = request.get_json() or {}
    status = data.get("Status")
    if status not in ("active", "draft"):
        return _error([_("Status must be 'active' or 'draft'.")])
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE TenantPages SET Status = ? WHERE TenantCode = ? AND PageKey = ?",
            (status, tenantcode, pagekey),
        )
        conn.commit()
        invalidate_tenant_config()
        if cursor.rowcount == 0:
            return _error([_("Page not found.")], 404)
        return jsonify({"success": True, "message": _("Page updated.")})
    except Exception as e:
        current_app.logger.error(f"Error updating page {tenantcode}/{pagekey}: {e}")
        return _error([_("An error occurred.")], 500)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.tenants.edit")
def api_admin_tenant_page_delete(tenantcode, pagekey):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM TenantPages WHERE TenantCode = ? AND PageKey = ?", (tenantcode, pagekey)
        )
        conn.commit()
        invalidate_tenant_config()
        if cursor.rowcount == 0:
            return _error([_("Page not found.")], 404)
        return jsonify({"success": True, "message": _("Page removed.")})
    except Exception as e:
        current_app.logger.error(f"Error deleting page {tenantcode}/{pagekey}: {e}")
        return _error([_("An error occurred.")], 500)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule(
        "/admin/tenants/manage",
        endpoint="admin_tenants_manage_view",
        view_func=admin_tenants_manage_view,
    )
    app.add_url_rule(
        "/admin/tenants/add",
        endpoint="api_admin_tenants_add",
        view_func=api_admin_tenants_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/tenants/edit/<tenantcode>",
        endpoint="api_admin_tenants_edit",
        view_func=api_admin_tenants_edit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/tenants/delete/<tenantcode>",
        endpoint="api_admin_tenants_delete",
        view_func=api_admin_tenants_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/admin/tenants/<tenantcode>/pages/add",
        endpoint="api_admin_tenant_page_add",
        view_func=api_admin_tenant_page_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/tenants/<tenantcode>/pages/<pagekey>/status",
        endpoint="api_admin_tenant_page_status",
        view_func=api_admin_tenant_page_status,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/tenants/<tenantcode>/pages/<pagekey>",
        endpoint="api_admin_tenant_page_delete",
        view_func=api_admin_tenant_page_delete,
        methods=["DELETE"],
    )
