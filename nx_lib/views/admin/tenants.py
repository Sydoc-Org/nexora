"""Admin tenants overview (#256 read-only phase, organization-centric since #257).

    Tenant
      └─ Organization ─┬─ Users
                       ├─ Access profiles (bound to the organization; NULL = global)
                       ├─ Data connections (derived: what its process configurations ride)
                       └─ Process configurations (ProcessSources.OrganizationCode)

One card per ``dbo.Tenants`` row listing the organizations that belong to it
(``Organizations.TenantCode``, migration 0090) and, per organization, the four
boxes above -- everything the other admin pages show in isolation, joined. A
trailing section lists the organizations no tenant owns and the connections no
organization rides, so nothing is invisible just because it is not wired up yet.

Reads go through the cached registries the rest of the app uses
(``nx_lib/tenant/registry.py``, ``nx_lib/mapping_config.py``,
``nx_lib/clients.py::CLIENTS``) plus the plain listing queries the Customers,
Data Connections and Access Control pages already run. Writes belong to those
pages -- this one links out to them.
"""

from flask import current_app, render_template, session
from flask_babel import get_locale

from ... import clients as clients_registry
from ... import mapping_config
from ...db import engine_nexora_db
from ...security import has_permission, page_visibility, require_permission
from ...tenant.registry import pages_for
from ...tenant.registry import registry as tenant_registry
from ..tenant import _tenant_nav_page


def _rows(cursor, sql):
    cursor.execute(sql)
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]


def build_tenant_tree(
    tenants, organizations, users, clients, loaded_codes, sources, pages, profiles
):
    """Assemble the overview from plain rows -- Flask-free so it is testable.

    tenants        objects with .code/.display_name/.active (the registry's Tenant dataclass)
    organizations  [{organizationcode, organization, tenant_code}]
    users          [{userID, username, fullname, organizationCode, profile}]
    clients        [{ClientCode, DisplayName, Dialect, RuntimeEngineKey, IsActive}]
    loaded_codes   set of ClientCodes the running CLIENTS registry holds
    sources        [{client, process, table, field_count, organization}]
    pages          {tenant_code: [{key, page_type, url, label}]}
    profiles       [{AccessID, Name, OrganizationCode}] -- every access profile

    Returns {"tenants", "orphan_organizations", "orphan_clients", "global_profiles"}.
    Missing rows never crash the page: a tenant with no organizations, an
    organization whose connection row is gone, a profile bound to a deleted
    organization -- each renders as the gap it is.
    """
    users_by_org: dict = {}
    for u in users:
        users_by_org.setdefault(u.get("organizationCode"), []).append(u)

    sources_by_org: dict = {}
    unassigned_by_client: dict = {}
    for s in sorted(sources, key=lambda s: (s["client"], s["process"])):
        if s.get("organization"):
            sources_by_org.setdefault(s["organization"], []).append(s)
        else:
            unassigned_by_client.setdefault(s["client"], []).append(s)

    bound_profiles: dict = {}
    for p in profiles:
        if p.get("OrganizationCode"):
            bound_profiles.setdefault(p["OrganizationCode"], []).append(p["Name"])
    global_profiles = sorted(
        (p["Name"] for p in profiles if not p.get("OrganizationCode")), key=str.lower
    )

    conns = {
        c["ClientCode"]: {
            **c,
            "loaded": c["ClientCode"] in loaded_codes,
            "unassigned_sources": unassigned_by_client.get(c["ClientCode"], []),
        }
        for c in clients
    }

    orgs = {}
    for o in organizations:
        code = o["organizationcode"]
        org_users = users_by_org.get(code, [])
        org_sources = sources_by_org.get(code, [])
        in_use: dict = {}
        for u in org_users:
            if u.get("profile"):
                in_use[u["profile"]] = in_use.get(u["profile"], 0) + 1
        orgs[code] = {
            **o,
            "users": org_users,
            "profiles_in_use": [
                {"name": n, "count": in_use[n]} for n in sorted(in_use, key=str.lower)
            ],
            "bound_profiles": sorted(bound_profiles.get(code, []), key=str.lower),
            "sources": org_sources,
            # 0096: an organization rides whatever connections its process
            # configurations read from -- nothing is stored on the row itself.
            "clients": [
                conns.get(c) or {"ClientCode": c, "DisplayName": None, "missing": True}
                for c in sorted({s["client"] for s in org_sources})
            ],
        }

    def _org_sort_key(code):
        return (orgs[code]["organization"] or code).lower()

    claimed_orgs, cards = set(), []
    for t in sorted(tenants, key=lambda t: (t.display_name or t.code).lower()):
        member_codes = sorted(
            (c for c in orgs if orgs[c].get("tenant_code") == t.code), key=_org_sort_key
        )
        claimed_orgs.update(member_codes)
        cards.append(
            {
                "tenant": t,
                "organizations": [orgs[c] for c in member_codes],
                "pages": pages.get(t.code, []),
            }
        )

    used_clients = {c["ClientCode"] for o in orgs.values() for c in o["clients"]}
    return {
        "tenants": cards,
        "orphan_organizations": [
            orgs[c] for c in sorted(orgs, key=_org_sort_key) if c not in claimed_orgs
        ],
        "orphan_clients": [conns[k] for k in sorted(conns) if k not in used_clients],
        "global_profiles": global_profiles,
    }


def _source_rows(reg):
    """mapping_config registry -> the flat source rows build_tenant_tree wants."""
    if reg is None:
        return []
    counts: dict = {}
    for m in reg.mappings:
        counts[(m.client, m.process)] = counts.get((m.client, m.process), 0) + 1
    return [
        {
            "client": client,
            "process": process,
            "table": src.table,
            "field_count": counts.get((client, process), 0),
            "organization": getattr(src, "organization", None),
        }
        for (client, process), src in reg.sources.items()
    ]


def _page_rows(reg):
    """{tenant_code: [nav entries]} via the same resolver the sidebar uses, so
    a page whose endpoint does not resolve is dropped here too, never 500s."""
    if reg is None:
        return {}
    locale = get_locale() or "en"
    return {
        code: [
            entry
            for p in pages_for(code)
            if (entry := _tenant_nav_page(code, p, locale)) is not None
        ]
        for code in reg.tenants
    }


@require_permission("admin.view.organizations")
def admin_tenants_view():
    """Gated like Customers: the page lists users by organization. The data-
    connection and process-configuration boxes additionally hide behind the
    permissions their own pages use, so this overview never shows someone
    more than the pages it links to would."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        organizations = _rows(
            cursor,
            "SELECT organizationcode, organization, TenantCode AS tenant_code FROM organizations",
        )
        users = _rows(
            cursor,
            "SELECT u.userID, u.username, u.Fullname AS fullname, u.organizationCode, "
            "ap.Name AS profile FROM Users u "
            "LEFT JOIN AccessProfile ap ON ap.AccessID = u.accessid "
            "ORDER BY u.Fullname, u.username",
        )
        try:
            clients = _rows(
                cursor,
                "SELECT ClientCode, DisplayName, Dialect, RuntimeEngineKey, IsActive "
                "FROM dbo.Clients ORDER BY ClientCode",
            )
        except Exception as e:  # dbo.Clients absent (TEST): every connection box shows the gap
            current_app.logger.warning(f"dbo.Clients unavailable for the tenants overview: {e}")
            clients = []
        profiles = _rows(cursor, "SELECT AccessID, Name, OrganizationCode FROM AccessProfile")

        treg = tenant_registry()
        mreg = mapping_config.registry()
        tree = build_tenant_tree(
            tenants=list(treg.tenants.values()) if treg else [],
            organizations=organizations,
            users=users,
            clients=clients,
            loaded_codes=set(clients_registry.CLIENTS),
            sources=_source_rows(mreg),
            pages=_page_rows(treg),
            profiles=profiles,
        )
        return render_template(
            "admin/tenants.html",
            tree=tree,
            tenant_registry_available=treg is not None,
            mapping_config_available=mreg is not None,
            can_view_clients=has_permission("admin.view.clients"),
            can_view_processes=has_permission("admin.view.processes"),
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to build tenants overview: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule("/admin/tenants", endpoint="admin_tenants_view", view_func=admin_tenants_view)
