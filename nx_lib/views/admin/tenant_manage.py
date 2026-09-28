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
from flask_babel import get_locale
from flask_babel import gettext as _
from werkzeug.routing import BuildError

from ... import clients as clients_registry
from ... import mapping_config
from ...db import engine_nexora_db
from ...security import has_permission, page_visibility, require_permission
from ...tenant.registry import (
    entity_for,
    fields_for,
    invalidate_tenant_config,
    provision_tenant_permissions,
)

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


def _tenant_client_codes(organizations):
    """{organization code: [client code, ...]} from the process-source registry.

    A tenant has no data connection of its own -- it inherits whatever its
    organizations' process sources point at, which is why this is derived
    rather than stored. Returns {} when the registry failed to load, so the
    column degrades to "no data connection" instead of raising.
    """
    reg = mapping_config.registry()
    if reg is None:
        return {}
    by_org: dict[str, list[str]] = {}
    for src in reg.sources.values():
        if not src.organization:
            continue
        codes = by_org.setdefault(src.organization, [])
        if src.client not in codes:
            codes.append(src.client)
    return {org: sorted(codes) for org, codes in by_org.items()}


def _connection_state(codes):
    """(label, state) for the Data connection cell.

    "Configured" is the dbo.Clients row; "loaded" is whether the runtime
    registry actually holds it. The two disagree whenever a client's env keys
    are missing, and that gap is the whole point of the column.
    """
    if not codes:
        return None, "none"
    loaded = [c for c in codes if c in clients_registry.CLIENTS]
    missing = [c for c in codes if c not in clients_registry.CLIENTS]
    if missing:
        return ", ".join(missing), "unloaded"
    return ", ".join(loaded), "loaded"


def _client_rows(cursor, clients_by_org, organizations):
    """dbo.Clients for the Data connections section, each row told which
    organizations actually use it (derived from their process sources) and
    whether the runtime loaded it."""
    try:
        rows = _rows(
            cursor,
            "SELECT ClientCode, DisplayName, Dialect, RuntimeEngineKey, StatsEngineKey, "
            "StatsDialect, DocfieldsEngineKey, DocfieldsDialect, OctoDomain, SecretRef, "
            "IsActive FROM dbo.Clients ORDER BY ClientCode",
        )
    except Exception as e:  # dbo.Clients absent (TEST): the section renders empty
        current_app.logger.warning(f"dbo.Clients unavailable for Manage tenants: {e}")
        return []
    names = {o["organizationcode"]: o["organization"] for o in organizations}
    for c in rows:
        c["loaded"] = c["ClientCode"] in clients_registry.CLIENTS
        c["used_by"] = sorted(
            names.get(org, org) for org, codes in clients_by_org.items() if c["ClientCode"] in codes
        )
    return rows


def _tenant_issues(tenants, orphan_orgs):
    """The Needs-attention list: each issue is one row with its own fix link.

    Three checks, all derived from data already on the page -- an organization
    belonging to no tenant, a tenant nobody can actually open (no profile holds
    ``tenant.<code>.view``), and a tenant with no organizations at all.
    """
    issues = []
    if orphan_orgs:
        issues.append(
            {
                "icon": "fa-building",
                "text": _(
                    "%(n)d organization(s) are not in a tenant",
                    n=len(orphan_orgs),
                ),
                "detail": ", ".join(o["organization"] for o in orphan_orgs),
                "action": _("Assign"),
                "href": url_for("admin_organizations_view"),
            }
        )
    for t in tenants:
        if not t["viewer_profiles"]:
            issues.append(
                {
                    "icon": "fa-key",
                    "text": _("Nobody holds tenant.%(code)s.view", code=t["TenantCode"]),
                    "detail": _(
                        "%(n)d page(s) are mounted but no user can open them", n=len(t["pages"])
                    ),
                    "action": _("Grant access"),
                    "href": url_for("admin_permissions"),
                }
            )
        if not t["organizations"]:
            issues.append(
                {
                    "icon": "fa-city",
                    "text": _("%(name)s has no organizations", name=t["DisplayName"]),
                    "detail": _("Its members cannot be resolved until one is assigned"),
                    "action": _("Add organizations"),
                    "href": url_for("admin_tenants_manage_view"),
                }
            )
    return issues


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
        # Users per organization, and which profiles hold each tenant's view
        # permission -- both feed the merged page's columns and its issue list.
        users_by_org = {
            r["organizationCode"]: r["n"]
            for r in _rows(
                cursor,
                "SELECT organizationCode, COUNT(*) AS n FROM Users "
                "WHERE organizationCode IS NOT NULL GROUP BY organizationCode",
            )
        }
        viewers_by_tenant: dict[str, list[str]] = {}
        for r in _rows(
            cursor,
            "SELECT p.Code, ap.Name FROM AccessProfilePermission app "
            "JOIN Permission p ON p.PermissionID = app.PermissionID "
            "JOIN AccessProfile ap ON ap.AccessID = app.AccessID "
            "WHERE p.Code LIKE 'tenant.%.view'",
        ):
            viewers_by_tenant.setdefault(r["Code"].split(".")[1], []).append(r["Name"])

        clients_by_org = _tenant_client_codes(organizations)

        for t in tenants:
            code = t["TenantCode"]
            t["organizations"] = [o for o in organizations if o["TenantCode"] == code]
            t["pages"] = [p for p in pages if p["TenantCode"] == code]
            t["IsActive"] = bool(t["IsActive"])
            t["user_count"] = sum(
                users_by_org.get(o["organizationcode"], 0) for o in t["organizations"]
            )
            t["viewer_profiles"] = viewers_by_tenant.get(code, [])
            t["pages_active"] = sum(1 for p in t["pages"] if p["Status"] == "active")
            codes = sorted(
                {
                    c
                    for o in t["organizations"]
                    for c in clients_by_org.get(o["organizationcode"], [])
                }
            )
            t["connection"], t["connection_state"] = _connection_state(codes)

        orphan_orgs = [o for o in organizations if not o["TenantCode"]]

        return render_template(
            "admin/tenants_manage.html",
            tenants=tenants,
            organizations=organizations,
            orphan_orgs=orphan_orgs,
            issues=_tenant_issues(tenants, orphan_orgs),
            kpis={
                "tenants": len(tenants),
                "tenants_active": sum(1 for t in tenants if t["IsActive"]),
                "organizations": len(organizations),
                "orphan_orgs": len(orphan_orgs),
                "users": sum(t["user_count"] for t in tenants),
                "orgs_in_tenants": sum(len(t["organizations"]) for t in tenants),
                "pages": len(pages),
                "pages_draft": sum(1 for p in pages if p["Status"] != "active"),
            },
            clients=_client_rows(cursor, clients_by_org, organizations),
            engine_keys=clients_registry._ENGINE_KEYS,
            endpoints=mountable_endpoints(current_app.url_map),
            can_edit=has_permission("admin.tenants.edit"),
            can_edit_clients=has_permission("admin.clients.edit"),
            show_clients=has_permission("admin.clients.view"),
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


# ----------------------------------------------------------- page preview --

# Sample cells for the member preview. They are synthetic on purpose: the
# preview answers "what shape of page do members get" -- the columns, the
# filter row, the Add/Export buttons -- and reading three example rows out of
# a tenant's source table would cross an engine and a permission boundary for
# decoration. Only the *structure* is real.
_PREVIEW_VALUES = {
    "identifier": ("10241", "10238", "10231", "10225"),
    "date": ("12.03.2026", "09.03.2026", "27.02.2026", "21.02.2026"),
    "money": ("1248.00", "310.50", "4902.15", "87.90"),
    "count": ("12", "3", "48", "7"),
}
# Widths for the text placeholders, so the mock reads like prose rather than a
# grid of identical grey bars.
_PREVIEW_WIDTHS = (86, 64, 74, 58)
# Mirrors templates/tenant/page.html: these roles get a text filter input.
_FILTERABLE_ROLES = ("identifier", "text", "category")


def _preview_cell(role, row, col=0):
    """One mock cell. Numeric-ish roles print a value, the rest stay grey --
    inventing plausible *words* for a text column would read as live data.
    The value series is rotated per column so two identifier columns do not
    print the same four numbers side by side."""
    values = _PREVIEW_VALUES.get(role)
    if values:
        value = values[(row + col) % len(values)]
        return {"kind": "num" if role in ("money", "count") else "mono", "value": value}
    if role in ("category", "flag"):
        return {"kind": "pill"}
    if role == "person":
        return {"kind": "person"}
    return {"kind": "bar", "width": _PREVIEW_WIDTHS[row]}


def _label_of(labels, lang, fallback):
    return labels.get(lang) or labels.get("en") or fallback


# A ``custom`` page mounts an existing nexora endpoint. We cannot render its
# markup here, but we do know roughly what shape of screen each family is, and
# a dashed "unknown" box for the 13 of 14 pages that are mounts would be a
# worse preview than the one it replaced. First keyword wins, so the order is
# the priority order: "import-status" is a list, not a status dashboard.
_SHAPE_KEYWORDS = (
    ("dashboard", ("dashboard", "overview", "home", "start")),
    ("report", ("report", "statistic", "analytic", "pdqm", "kpi", "chart")),
    ("list", ("workitem", "document", "list", "prepared", "import", "status", "search", "job")),
    ("cards", ("service", "management", "project", "setting", "profile", "admin")),
)


def _custom_shape(page_key, endpoint):
    hay = f"{page_key} {endpoint}".lower()
    for shape, words in _SHAPE_KEYWORDS:
        if any(w in hay for w in words):
            return shape
    return "list"


def _endpoint_path(endpoint):
    """The URL the sidebar entry points at -- real information, unlike the
    mock body next to it, so it is worth showing."""
    if not endpoint:
        return None
    try:
        return url_for(endpoint)
    except (BuildError, ValueError):
        return None


def _page_preview(tenantcode, page, can_edit):
    """The member-preview spec for one mounted page.

    ``custom`` pages point at an arbitrary endpoint whose markup we cannot
    know, so they preview as the frame only. Generated ``list``/``crud`` pages
    do have a descriptor, and the preview is built from the same entity and
    field rows the real page renders from -- same columns, same filter row,
    same actions -- so what the admin sees here is what a member gets.
    """
    layout = page.get("layout") or {}
    label = layout.get("label") or page["PageKey"]
    spec = {
        "kind": page["PageType"],
        "title": label,
        "subtitle": None,
        "endpoint": layout.get("endpoint") or "",
        "shape": None,
        "path": None,
        "source": None,
        "actions": [],
        "filters": [],
        "columns": [],
        "extra_columns": 0,
        "rows": [],
        "row_actions": False,
    }
    if page["PageType"] == "custom" or not page.get("EntityKey"):
        spec["shape"] = _custom_shape(page["PageKey"], spec["endpoint"])
        spec["path"] = _endpoint_path(spec["endpoint"])
        return spec

    lang = str(get_locale() or "en")
    entity = entity_for(tenantcode, page["EntityKey"])
    if entity is None:
        return spec
    fields = [f for f in fields_for(tenantcode, page["EntityKey"]) if f.visible]
    spec["subtitle"] = _label_of(entity.labels, lang, entity.key)
    spec["source"] = entity.source_object

    is_crud = page["PageType"] == "crud"
    if is_crud and can_edit:
        spec["actions"].append({"label": _("Add"), "icon": "fa-plus", "primary": True})
    spec["actions"].append({"label": _("Export"), "icon": "fa-file-export", "primary": False})

    # The id column is always filterable, then the text-ish fields, then the
    # first date field as a from/to pair -- the exact set the real page builds.
    filters = [entity.id_column]
    filters += [
        _label_of(f.labels, lang, f.column) for f in fields if f.semantic_role in _FILTERABLE_ROLES
    ]
    first_date = next((f for f in fields if f.semantic_role == "date"), None)
    if first_date:
        date_label = _label_of(first_date.labels, lang, first_date.column)
        filters += [f"{date_label} ({_('from')})", f"{date_label} ({_('to')})"]
    spec["filters"] = filters[:4]

    shown = fields[:3]
    spec["extra_columns"] = max(0, len(fields) - len(shown))
    spec["columns"] = [entity.id_column] + [_label_of(f.labels, lang, f.column) for f in shown]
    spec["rows"] = [
        [_preview_cell("identifier", r)]
        + [_preview_cell(f.semantic_role, r, c) for c, f in enumerate(shown, start=1)]
        for r in range(4)
    ]
    spec["row_actions"] = is_crud and can_edit
    return spec


@require_permission("admin.tenants.view")
def admin_tenant_detail_view(tenantcode):
    """One tenant: its organizations, its mounted pages, and who can open it.

    Routed rather than a panel (``/admin/tenants/detail/<code>``) so the tab is
    part of the URL and survives a reload, and so Manage tenants can link
    straight at a tenant's Access tab from its issue list.
    """
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        tenant = _rows(
            cursor,
            "SELECT TenantCode, DisplayName, IsActive FROM Tenants WHERE TenantCode = ?",
            (tenantcode,),
        )
        if not tenant:
            return render_template("handlers/404.html"), 404
        tenant = tenant[0]
        tenant["IsActive"] = bool(tenant["IsActive"])

        organizations = _rows(
            cursor,
            "SELECT organizationcode, organization, TenantCode FROM organizations "
            "WHERE TenantCode = ? ORDER BY organization",
            (tenantcode,),
        )
        all_organizations = _rows(
            cursor,
            "SELECT organizationcode, organization, TenantCode FROM organizations ORDER BY organization",
        )
        pages = _rows(
            cursor,
            "SELECT TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status "
            "FROM TenantPages WHERE TenantCode = ? ORDER BY SortOrder, PageKey",
            (tenantcode,),
        )
        can_edit = has_permission("admin.tenants.edit")
        for p in pages:
            try:
                p["layout"] = json.loads(p["LayoutJSON"]) if p["LayoutJSON"] else {}
            except ValueError:
                p["layout"] = {}
            p["preview"] = _page_preview(tenantcode, p, can_edit)

        users_by_org = {
            r["organizationCode"]: r["n"]
            for r in _rows(
                cursor,
                "SELECT organizationCode, COUNT(*) AS n FROM Users "
                "WHERE organizationCode IS NOT NULL GROUP BY organizationCode",
            )
        }
        profiles_by_org: dict[str, list[str]] = {}
        for r in _rows(
            cursor, "SELECT AccessID, Name, OrganizationCode FROM AccessProfile ORDER BY Name"
        ):
            if r["OrganizationCode"]:
                profiles_by_org.setdefault(r["OrganizationCode"], []).append(r["Name"])

        # Who can actually open this tenant: profiles holding tenant.<code>.view,
        # with how many users sit on each. An empty list is the Access tab's warning.
        viewers = _rows(
            cursor,
            "SELECT ap.Name, ap.OrganizationCode, "
            "(SELECT COUNT(*) FROM Users u WHERE u.accessid = ap.AccessID) AS user_count "
            "FROM AccessProfilePermission app "
            "JOIN Permission p ON p.PermissionID = app.PermissionID "
            "JOIN AccessProfile ap ON ap.AccessID = app.AccessID "
            "WHERE p.Code = ? ORDER BY ap.Name",
            (f"tenant.{tenantcode}.view",),
        )

        clients_by_org = _tenant_client_codes(all_organizations)
        reg = mapping_config.registry()
        processes_by_org: dict[str, int] = {}
        if reg is not None:
            for src in reg.sources.values():
                if src.organization:
                    processes_by_org[src.organization] = (
                        processes_by_org.get(src.organization, 0) + 1
                    )

        for o in organizations:
            code = o["organizationcode"]
            o["user_count"] = users_by_org.get(code, 0)
            o["profiles"] = profiles_by_org.get(code, [])
            o["process_count"] = processes_by_org.get(code, 0)
            o["connection"], o["connection_state"] = _connection_state(clients_by_org.get(code, []))

        tenant["organizations"] = organizations
        tenant["pages"] = pages
        tenant["user_count"] = sum(o["user_count"] for o in organizations)

        return render_template(
            "admin/tenant_detail.html",
            tenant=tenant,
            organizations=organizations,
            all_organizations=all_organizations,
            pages=pages,
            viewers=viewers,
            endpoints=mountable_endpoints(current_app.url_map),
            can_edit=can_edit,
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to render tenant detail for {tenantcode}: {e}")
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


@require_permission("admin.tenants.edit")
def api_admin_tenant_pages_reorder(tenantcode):
    """Persist the order a tenant's pages appear in for its members.

    The payload is the full list of page keys in their new order; SortOrder is
    rewritten as 10, 20, 30 ... so a later single-page move has room to land
    between two neighbours without renumbering everything again.

    Keys are checked against the tenant's own rows before anything is written:
    a key from another tenant (or a made-up one) fails the whole request rather
    than silently reordering a subset.
    """
    data = request.get_json() or {}
    order = data.get("order")
    if not isinstance(order, list) or not all(isinstance(k, str) for k in order):
        return _error([_("Order must be a list of page keys.")])

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT PageKey FROM TenantPages WHERE TenantCode = ?", (tenantcode,))
        known = {r[0] for r in cursor.fetchall()}
        if not known:
            return _error([_("Tenant not found.")], 404)
        if set(order) != known:
            return _error([_("The page list does not match this tenant's pages.")])

        for position, key in enumerate(order, start=1):
            cursor.execute(
                "UPDATE TenantPages SET SortOrder = ? WHERE TenantCode = ? AND PageKey = ?",
                (position * 10, tenantcode, key),
            )
        conn.commit()
        invalidate_tenant_config()
        return jsonify({"success": True, "message": _("Page order saved.")})
    except Exception as e:
        current_app.logger.error(f"Error reordering pages of tenant {tenantcode}: {e}")
        if conn:
            conn.rollback()
        return _error([_("Could not save the page order.")], 500)
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
        "/admin/tenants/detail/<tenantcode>",
        endpoint="admin_tenant_detail_view",
        view_func=admin_tenant_detail_view,
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
        "/admin/tenants/<tenantcode>/pages/reorder",
        endpoint="api_admin_tenant_pages_reorder",
        view_func=api_admin_tenant_pages_reorder,
        methods=["POST"],
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
