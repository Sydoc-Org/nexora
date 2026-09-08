"""Pure-rule tests for scripts/perm-audit.py (loaded by path: the name is hyphenated)."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "perm_audit_under_test", REPO_ROOT / "scripts" / "perm-audit.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _data(mod):
    codes = [
        "generali.dashboard.view",
        "process.privera.02_InitialScan.view",
        "workitems.filter.process.compass.01_Invoice_SAP",
        "admin.users.view",
        "dashboard.view",
        "tenant.ms02.view",
    ]
    return mod.Snapshot(
        orgs={
            "PRVR": ("Privera", None),
            "GNRL": ("Generali", "generali"),
            "SSIX": ("ISS", None),  # no TenantCode row -> legacy map says generali
            "SYDC": ("sydoc AG", "sydoc"),
        },
        profiles={10: ("priveraUser", "PRVR"), 12: ("ISS User", None), 2: ("globalAdmin", None)},
        codes=codes,
        profile_grants={
            10: {"dashboard.view", "process.privera.02_InitialScan.view"},
            12: {"generali.dashboard.view"},
            2: set(codes) - {"tenant.ms02.view"},
        },
        profile_deny_rows=3,
        overrides=[
            (1, "dashboard.view", "A"),  # redundant: profile already grants it
            (1, "tenant.ms02.view", "D"),  # no-op: profile never grants it
            (2, "generali.dashboard.view", "A"),
        ],
        users=[
            # id, username, accessid, org
            (1, "priv.one", 10, "PRVR"),
            (2, "priv.two", 10, "PRVR"),
            (3, "iss.one", 12, "SSIX"),
            (4, "ben", 2, "SYDC"),
            (5, "lost", 99, "PRVR"),
            (6, "priv.iss", 12, "PRVR"),
        ],
        effective={
            1: {"dashboard.view", "process.privera.02_InitialScan.view"},
            2: {
                "dashboard.view",
                "generali.dashboard.view",
                "admin.users.view",
                "workitems.filter.process.compass.01_Invoice_SAP",
            },
            3: {"generali.dashboard.view"},
            4: set(codes),
            5: set(),
            6: {"generali.dashboard.view"},
        },
        process_org={"privera.02_InitialScan": "PRVR"},
        corpus="dashboard.view admin.users.view",
    )


def test_cross_org_flags_customer_not_staff_nor_legacy_tenant_member():
    mod = _load()
    out = mod.audit(_data(mod))
    cross = "\n".join(out["Cross-organization grants"])
    assert "priv.two" in cross and "generali.dashboard.view" in cross
    assert "compass.01_Invoice_SAP" in cross  # process owned by an org that is not PRVR
    assert "priv.one" not in cross  # own process only
    assert "iss.one" not in cross  # ISS sits in generali via the legacy map
    assert "ben" not in cross  # SYDC is staff


def test_profile_org_mismatch_and_customer_admin():
    mod = _load()
    out = mod.audit(_data(mod))
    assert any(
        "priv.iss" in line and "ISS User" in line
        for line in out["Profile does not match organization"]
    )
    admin = "\n".join(out["Customers holding admin codes"])
    assert "priv.two" in admin and "ben" not in admin


def test_override_noise_and_housekeeping():
    mod = _load()
    out = mod.audit(_data(mod))
    noise = "\n".join(out["Override noise"])
    assert "priv.one" in noise and "redundant" in noise and "no-op" in noise
    house = "\n".join(out["Housekeeping"])
    assert "lost" in house  # unknown profile 99
    assert "3 profile-level deny rows" in house
    assert "tenant.ms02.view" in house  # nobody holds it via profile or allow override
    assert "generali.dashboard.view" in house  # not in corpus
    assert (
        "process.privera.02_InitialScan.view" not in house.split("not referenced")[-1]
    )  # family, matched by pattern


def test_code_owner():
    mod = _load()
    org_by_label = {"prvr": "PRVR", "privera": "PRVR"}
    assert mod.code_owner("process.privera.02_InitialScan.view", {}, org_by_label) == (
        "org",
        "PRVR",
    )
    assert mod.code_owner("reporting.scope.process.compass.01_Invoice_SAP", {}, org_by_label) == (
        "org",
        "compass",
    )
    assert mod.code_owner("tenant.ms02.edit", {}, org_by_label) == ("tenant", "ms02")
    assert mod.code_owner("generali.pdqm.view", {}, org_by_label) == ("tenant", "generali")
    assert mod.code_owner("admin.view.mobscn.processmanagement", {}, org_by_label) == (
        "tenant",
        "ms02",
    )
    assert mod.code_owner("dashboard.view", {}, org_by_label) is None
