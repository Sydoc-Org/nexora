"""build_tenant_tree (views/admin/tenants.py) -- the pure assembly behind the
organization-centric admin tenants overview. Fed plain rows, no Flask, no DB."""

import types

from nx_lib.views.admin.tenants import build_tenant_tree


def _tenant(code="ms02", org="PDBS", client="ms02", name="Mobscn", active=True):
    return types.SimpleNamespace(
        code=code, display_name=name, organization_code=org, client_code=client, active=active
    )


def _org(code, name, tenant=None, client=None):
    return {
        "organizationcode": code,
        "organization": name,
        "tenant_code": tenant,
        "client_code": client,
    }


def _user(uid, username, org, profile, fullname=None):
    return {
        "userID": uid,
        "username": username,
        "fullname": fullname,
        "organizationCode": org,
        "profile": profile,
    }


def _client(code, name, dialect="tsql"):
    return {
        "ClientCode": code,
        "DisplayName": name,
        "Dialect": dialect,
        "RuntimeEngineKey": "e",
        "IsActive": True,
    }


def _source(client, process, org, table="dbo.T", fields=1):
    return {
        "client": client,
        "process": process,
        "table": table,
        "field_count": fields,
        "organization": org,
    }


ORGS = [
    _org("PDBS", "Praesidialdepartement", tenant="ms02", client="ms02"),
    _org("PRVR", "Privera", client="default"),
    _org("LKTR", "ElektroMaterial"),
]
USERS = [
    _user(1, "anna", "PDBS", "pdbsUser", "Anna A"),
    _user(2, "bob", "PRVR", "priveraUser"),
    _user(3, "orphan", None, None),
    _user(4, "carl", "PRVR", "priveraUser", "Carl C"),
    _user(5, "dora", "PRVR", "globalAdmin"),
]
CLIENTS = [
    _client("default", "Default"),
    _client("ms02", "Mobscn", "postgres"),
    _client("spare", "Spare"),
]
SOURCES = [
    _source("default", "privera.02_Posteingang", "PRVR", fields=3),
    _source("default", "compass.01_Invoice", None),
    _source("ms02", "sydoc.05_PDBS", "PDBS", table='public."DossierStatistik"', fields=6),
]
PAGES = {
    "ms02": [{"key": "workitems", "page_type": "custom", "url": "/workitems", "label": "workitems"}]
}
PROFILES = [
    {"AccessID": 1, "Name": "globalAdmin", "OrganizationCode": None},
    {"AccessID": 2, "Name": "pdbsUser", "OrganizationCode": "PDBS"},
    {"AccessID": 3, "Name": "priveraUser", "OrganizationCode": "PRVR"},
    {"AccessID": 4, "Name": "priveraAdmin", "OrganizationCode": "PRVR"},
]


def _tree(tenants=None, organizations=ORGS, loaded=frozenset({"default", "ms02"})):
    return build_tenant_tree(
        tenants=[_tenant()] if tenants is None else tenants,
        organizations=organizations,
        users=USERS,
        clients=CLIENTS,
        loaded_codes=set(loaded),
        sources=SOURCES,
        pages=PAGES,
        profiles=PROFILES,
    )


def test_tenant_card_lists_its_organizations_with_all_four_boxes():
    card = _tree()["tenants"][0]
    assert card["tenant"].code == "ms02"
    (org,) = card["organizations"]
    assert org["organizationcode"] == "PDBS"
    assert [u["username"] for u in org["users"]] == ["anna"]
    assert org["profiles_in_use"] == [{"name": "pdbsUser", "count": 1}]
    assert org["bound_profiles"] == ["pdbsUser"]
    assert org["client"]["ClientCode"] == "ms02" and org["client"]["loaded"] is True
    assert [s["process"] for s in org["sources"]] == ["sydoc.05_PDBS"]
    assert card["pages"] == PAGES["ms02"]


def test_membership_comes_from_organizations_tenant_code():
    two = [*ORGS, _org("SSIX", "ISS", tenant="ms02", client="ms02")]
    card = _tree(organizations=two)["tenants"][0]
    assert [o["organizationcode"] for o in card["organizations"]] == ["SSIX", "PDBS"]  # by name


def test_legacy_tenants_organization_code_is_a_fallback_only():
    legacy = [dict(o, tenant_code=None) for o in ORGS]  # nobody re-pointed yet
    tree = _tree(organizations=legacy)
    assert [o["organizationcode"] for o in tree["tenants"][0]["organizations"]] == ["PDBS"]
    assert "PDBS" not in [o["organizationcode"] for o in tree["orphan_organizations"]]


def test_orphans_are_organizations_without_tenant_and_connections_nobody_rides():
    tree = _tree()
    assert [o["organizationcode"] for o in tree["orphan_organizations"]] == ["LKTR", "PRVR"]
    assert [c["ClientCode"] for c in tree["orphan_clients"]] == ["spare"]
    privera = tree["orphan_organizations"][1]
    assert privera["client"]["ClientCode"] == "default"
    assert [s["process"] for s in privera["sources"]] == ["privera.02_Posteingang"]
    # an organization with no connection renders the gap, not a crash
    assert tree["orphan_organizations"][0]["client"] is None


def test_unassigned_sources_hang_off_their_connection():
    default = _tree()["orphan_organizations"][1]["client"]
    assert [s["process"] for s in default["unassigned_sources"]] == ["compass.01_Invoice"]


def test_profiles_bound_vs_in_use_and_global_list():
    tree = _tree()
    privera = tree["orphan_organizations"][1]
    assert privera["bound_profiles"] == ["priveraAdmin", "priveraUser"]  # defined for the org
    assert privera["profiles_in_use"] == [  # what its users actually hold, globals included
        {"name": "globalAdmin", "count": 1},
        {"name": "priveraUser", "count": 2},
    ]
    assert tree["global_profiles"] == ["globalAdmin"]


def test_not_loaded_is_reported():
    org = _tree(loaded=frozenset())["tenants"][0]["organizations"][0]
    assert org["client"]["loaded"] is False


def test_no_tenants_means_every_organization_is_orphaned():
    tree = _tree(tenants=[])
    assert tree["tenants"] == []
    assert len(tree["orphan_organizations"]) == 3
