"""Admin tenants overview (#256, read-only phase): the connected picture.

One card per ``dbo.Tenants`` row, joining the four things the other admin pages
show in isolation -- the customer organization (and the users in it), the data
connection (``dbo.Clients`` + whether the running process actually loaded it),
that connection's document-field process sources, and the tenant's generated
pages. A trailing section lists the organizations and connections no tenant
points at, so nothing is invisible just because it is not a tenant yet.

Everything is read through the cached registries the rest of the app uses
(``nx_lib/tenant/registry.py``, ``nx_lib/mapping_config.py``,
``nx_lib/clients.py::CLIENTS``); the only raw SQL is the three plain listing
queries the Customers and Data Connections pages already run. Writes belong to
those pages -- this one links out to them.
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


def _process_customer_key(process_name):
    """The ``<customer>`` half of a ``<customer>.<process>`` process name --
    the shape ``_PROCESS_NAME_RE`` (views/admin/processes.py) enforces on
    every source. Nothing in the schema ties it to an organization, so the
    overview uses it only as a *named-after* hint, never as a join."""
    return (process_name or "").split(".", 1)[0].lower()


def build_tenant_tree(tenants, organizations, users, clients, loaded_codes, sources, pages):
    """Assemble the overview from plain rows -- Flask-free so it is testable.

    tenants        iterable of objects with .code/.display_name/.organization_code/
                   .client_code/.active (the tenant registry's Tenant dataclass)
    organizations  [{organizationcode, organization}]
    users          [{userID, username, fullname, organizationCode, profile}]
    clients        [{ClientCode, DisplayName, Dialect, RuntimeEngineKey, IsActive}]
    loaded_codes   set of ClientCodes the running CLIENTS registry holds
    sources        [{client, process, table, field_count}]
    pages          {tenant_code: [{key, page_type, url, label}]}

    Returns {"tenants": [...], "orphan_organizations": [...], "orphan_clients": [...]}.
    A tenant whose organization or client row is missing still renders, with
    that slot None -- a dangling FK is exactly what an overview should show.
    """
    users_by_org: dict = {}
    for u in users:
        users_by_org.setdefault(u.get("organizationCode"), []).append(u)

    sources_by_client: dict = {}
    for s in sources:
        sources_by_client.setdefault(s["client"], []).append(s)
    for lst in sources_by_client.values():
        lst.sort(key=lambda s: s["process"])

    orgs = {}
    for o in organizations:
        code = o["organizationcode"]
        name = o.get("organization") or ""
        # Soft link (see _process_customer_key): sources named after this
        # customer, across every connection. A hint for the reader, not data.
        named_after = [
            s
            for lst in sources_by_client.values()
            for s in lst
            if _process_customer_key(s["process"]) in {code.lower(), name.lower()}
        ]
        org_users = users_by_org.get(code, [])
        # Access profiles in use inside this organization (AccessProfile.Name
        # via Users.accessid), with headcount -- the fourth box of the picture.
        profile_counts: dict = {}
        for u in org_users:
            if u.get("profile"):
                profile_counts[u["profile"]] = profile_counts.get(u["profile"], 0) + 1
        orgs[code] = {
            **o,
            "users": org_users,
            "profiles": [
                {"name": n, "count": profile_counts[n]}
                for n in sorted(profile_counts, key=str.lower)
            ],
            "named_sources": sorted(named_after, key=lambda s: (s["client"], s["process"])),
        }

    conns = {}
    for c in clients:
        code = c["ClientCode"]
        conns[code] = {
            **c,
            "loaded": code in loaded_codes,
            "processes": sources_by_client.get(code, []),
        }

    used_orgs, used_clients, cards = set(), set(), []
    for t in sorted(tenants, key=lambda t: (t.display_name or t.code).lower()):
        used_orgs.add(t.organization_code)
        used_clients.add(t.client_code)
        cards.append(
            {
                "tenant": t,
                "organization": orgs.get(t.organization_code),
                "client": conns.get(t.client_code),
                "pages": pages.get(t.code, []),
            }
        )

    return {
        "tenants": cards,
        "orphan_organizations": [
            orgs[k]
            for k in sorted(orgs, key=lambda k: (orgs[k]["organization"] or k).lower())
            if k not in used_orgs
        ],
        "orphan_clients": [conns[k] for k in sorted(conns) if k not in used_clients],
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
        }
        for (client, process), src in reg.sources.items()
    ]


def _page_rows(reg):
    """{tenant_code: [nav entries]} via the same resolver the sidebar uses, so
    a page whose endpoint does not resolve is dropped here too, never 500s."""
    if reg is None:
        return {}
    locale = get_locale() or "en"
    out = {}
    for code in reg.tenants:
        out[code] = [
            entry
            for p in pages_for(code)
            if (entry := _tenant_nav_page(code, p, locale)) is not None
        ]
    return out


@require_permission("admin.view.organizations")
def admin_tenants_view():
    """Gated like Customers: the page lists users by organization. The data-
    connection and document-field columns additionally hide behind the
    permissions their own pages use, so this overview never shows someone
    more than the pages it links to would."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT organizationcode, organization FROM organizations")
        organizations = [
            dict(zip([c[0] for c in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT u.userID, u.username, u.Fullname AS fullname, u.organizationCode, "
            "ap.Name AS profile FROM Users u "
            "LEFT JOIN AccessProfile ap ON ap.AccessID = u.accessid "
            "ORDER BY u.Fullname, u.username"
        )
        users = [
            dict(zip([c[0] for c in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT ClientCode, DisplayName, Dialect, RuntimeEngineKey, IsActive "
            "FROM dbo.Clients ORDER BY ClientCode"
        )
        clients = [
            dict(zip([c[0] for c in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

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
