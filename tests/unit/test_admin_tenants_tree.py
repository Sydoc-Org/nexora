"""build_tenant_tree (views/admin/tenants.py) -- the pure assembly behind the
admin tenants overview. Fed plain rows, no Flask, no DB."""

import types

from nx_lib.views.admin.tenants import _process_customer_key, build_tenant_tree


def _tenant(code="ms02", org="PDBS", client="ms02", name="Mobscn", active=True):
    return types.SimpleNamespace(
        code=code, display_name=name, organization_code=org, client_code=client, active=active
    )


ORGS = [
    {"organizationcode": "PDBS", "organization": "Praesidialdepartement"},
    {"organizationcode": "PRVR", "organization": "Privera"},
]
USERS = [
    {
        "userID": 1,
        "username": "anna",
        "fullname": "Anna A",
        "organizationCode": "PDBS",
        "profile": "globalAdmin",
    },
    {
        "userID": 2,
        "username": "bob",
        "fullname": None,
        "organizationCode": "PRVR",
        "profile": "user",
    },
    {
        "userID": 3,
        "username": "orphan",
        "fullname": None,
        "organizationCode": None,
        "profile": None,
    },
    {
        "userID": 4,
        "username": "carl",
        "fullname": "Carl C",
        "organizationCode": "PRVR",
        "profile": "user",
    },
    {
        "userID": 5,
        "username": "dora",
        "fullname": None,
        "organizationCode": "PRVR",
        "profile": None,
    },
]
CLIENTS = [
    {
        "ClientCode": "default",
        "DisplayName": "Default",
        "Dialect": "tsql",
        "RuntimeEngineKey": "e",
        "IsActive": True,
    },
    {
        "ClientCode": "ms02",
        "DisplayName": "Mobscn",
        "Dialect": "postgres",
        "RuntimeEngineKey": "p",
        "IsActive": True,
    },
]
SOURCES = [
    {"client": "default", "process": "privera.02_Posteingang", "table": "dbo.P", "field_count": 3},
    {"client": "default", "process": "compass.01_Invoice", "table": "dbo.C", "field_count": 1},
    {
        "client": "ms02",
        "process": "sydoc.05_PDBS",
        "table": 'public."DossierStatistik"',
        "field_count": 6,
    },
]
PAGES = {
    "ms02": [{"key": "workitems", "page_type": "custom", "url": "/workitems", "label": "workitems"}]
}


def _tree(tenants=None, loaded=frozenset({"default", "ms02"})):
    return build_tenant_tree(
        tenants=[_tenant()] if tenants is None else tenants,
        organizations=ORGS,
        users=USERS,
        clients=CLIENTS,
        loaded_codes=set(loaded),
        sources=SOURCES,
        pages=PAGES,
    )


def test_tenant_card_joins_all_four_sides():
    card = _tree()["tenants"][0]
    assert card["tenant"].code == "ms02"
    assert card["organization"]["organizationcode"] == "PDBS"
    assert [u["username"] for u in card["organization"]["users"]] == ["anna"]
    assert card["organization"]["profiles"] == [{"name": "globalAdmin", "count": 1}]
    assert card["client"]["ClientCode"] == "ms02"
    assert card["client"]["loaded"] is True
    assert [s["process"] for s in card["client"]["processes"]] == ["sydoc.05_PDBS"]
    assert card["pages"] == PAGES["ms02"]


def test_orphans_are_whatever_no_tenant_points_at():
    tree = _tree()
    assert [o["organizationcode"] for o in tree["orphan_organizations"]] == ["PRVR"]
    assert [c["ClientCode"] for c in tree["orphan_clients"]] == ["default"]
    # the shared connection carries its sources, sorted by process name
    assert [s["process"] for s in tree["orphan_clients"][0]["processes"]] == [
        "compass.01_Invoice",
        "privera.02_Posteingang",
    ]


def test_named_after_hint_uses_the_customer_half_of_the_process_name():
    assert _process_customer_key("Privera.02_Posteingang") == "privera"
    assert _process_customer_key("") == ""
    tree = _tree()
    privera = tree["orphan_organizations"][0]
    assert [s["process"] for s in privera["named_sources"]] == ["privera.02_Posteingang"]


def test_profiles_are_counted_per_organization_and_skip_unassigned():
    privera = _tree()["orphan_organizations"][0]
    assert privera["profiles"] == [{"name": "user", "count": 2}]  # dora has no profile


def test_dangling_fk_renders_as_missing_not_crash():
    card = _tree(tenants=[_tenant(org="GONE", client="nope")])["tenants"][0]
    assert card["organization"] is None
    assert card["client"] is None
    assert card["pages"] == PAGES["ms02"]


def test_not_loaded_is_reported():
    tree = _tree(loaded=frozenset())
    assert tree["tenants"][0]["client"]["loaded"] is False


def test_no_tenants_means_everything_is_orphaned():
    tree = _tree(tenants=[])
    assert tree["tenants"] == []
    assert len(tree["orphan_organizations"]) == 2
    assert len(tree["orphan_clients"]) == 2
