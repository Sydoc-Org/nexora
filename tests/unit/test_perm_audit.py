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
            "LKTR": ("ElektroMaterial", None),
        },
        profiles={
            10: ("priveraUser", "PRVR"),
            12: ("ISS User", None),
            2: ("globalAdmin", None),
            # -- reporting-source cases (#332) --
            20: ("Privera User", "PRVR"),  # holds one of its own and one of LKTR's
            21: ("ISS Supervisor", "SSIX"),  # a Generali source, same tenant
            22: ("Sydoc User", None),  # a source but no reporting.view
        },
        codes=codes,
        profile_grants={
            10: {"dashboard.view", "process.privera.02_InitialScan.view"},
            12: {"generali.dashboard.view"},
            2: (set(codes) - {"tenant.ms02.view"}) | {"reporting.view"},
            20: {
                "reporting.view",
                "reporting.source.privera_invoice.use",
                "reporting.source.em_invoice.use",
                "reporting.source.workitems.use",  # owner unknown -> never flagged
            },
            21: {"reporting.view", "reporting.source.generali_documents.use"},
            22: {"reporting.source.mediamarkt_batches.use"},  # no reporting.view
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
        sources={
            "reporting.source.privera_invoice.use": "Privera — Rechnungseingang",
            "reporting.source.em_invoice.use": "Elektro-Material — Verrechnung",
            "reporting.source.generali_documents.use": "Generali — Documents",
            "reporting.source.mediamarkt_batches.use": "MediaMarkt — Batches",
            "reporting.source.workitems.use": "Workitems (Octo)",
        },
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


def test_dormant_source_grant_is_flagged_only_without_reporting_view():
    """#332: a source grant with no reporting.view does nothing -- until it does."""
    mod = _load()
    out = mod.audit(_data(mod))
    dormant = "\n".join(out["Dormant reporting-source grants"])
    assert "Sydoc User" in dormant and "mediamarkt_batches" in dormant
    # Everyone else holding a source also holds reporting.view.
    assert "Privera User" not in dormant
    assert "ISS Supervisor" not in dormant
    assert "globalAdmin" not in dormant


def test_source_of_another_customer_is_flagged():
    mod = _load()
    out = mod.audit(_data(mod))
    foreign = "\n".join(out["Reporting sources of another customer"])
    assert "Privera User" in foreign
    assert "em_invoice" in foreign and "LKTR" in foreign
    assert "privera_invoice" not in foreign  # its own


def test_source_rules_stay_quiet_where_they_should():
    mod = _load()
    out = mod.audit(_data(mod))
    foreign = "\n".join(out["Reporting sources of another customer"])
    # Same tenant: ISS reads Generali sources by design (legacy tenant map).
    assert "ISS Supervisor" not in foreign
    # Unknown owner is not the same as safe, but it must not raise a finding.
    assert "workitems" not in foreign
    # Staff profiles hold everything on purpose.
    assert "globalAdmin" not in foreign


def test_source_owner_reads_the_label_prefix():
    mod = _load()
    obl = {
        "cmps": "CMPS",
        "compass": "CMPS",
        "lktr": "LKTR",
        "elektromaterial": "LKTR",
        "prvr": "PRVR",
        "privera": "PRVR",
        "sydc": "SYDC",
        "sydoc ag": "SYDC",
    }
    # The org name and the label rarely agree exactly; both directions matter.
    assert mod.source_owner("Privera \u2014 Posteingang", obl) == "PRVR"
    assert mod.source_owner("Compass Group \u2014 Verrechnung", obl) == "CMPS"
    assert mod.source_owner("Sydoc \u2014 Project Hours", obl) == "SYDC"
    # The hyphen inside "Elektro-Material" must not be read as the separator.
    assert mod.source_owner("Elektro-Material \u2014 Verrechnung", obl) == "LKTR"
    # Only an em/en dash separates; a hyphen does not, however it is spaced.
    # Without this the name above splits at its own hyphen and resolves to
    # whatever "Elektro" happens to match.
    assert mod.source_owner("Elektro-Material - Verrechnung", obl) is None
    assert mod.source_owner("Privera-Posteingang", obl) is None
    # No customer in the label, or a customer with no Organizations row.
    assert mod.source_owner("Workitems (Octo)", obl) is None
    assert mod.source_owner("Field extraction quality", obl) is None
    assert mod.source_owner("MediaMarkt \u2014 Batches", obl) is None
    assert mod.source_owner("", obl) is None
