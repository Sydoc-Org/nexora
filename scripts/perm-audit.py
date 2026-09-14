"""perm-audit.py -- read-only anomaly audit of the nexora permission model.

    python scripts/perm-audit.py --env PROD      # default
    python scripts/perm-audit.py --env INT

Prints a markdown report to stdout and never writes to the database. Effective
permissions come from dbo.spGetUserPermissions, so the audit sees exactly what
the app sees. Works on both the legacy catalogue shape (PROD, pre-#238) and the
process.<client>.<name>.view shape (INT). Rules live in ``audit()``; the DB
snapshot is a plain dataclass so the rules are unit-testable without a server.
"""

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Vendor staff may legitimately hold every customer-scoped code.
STAFF_ORGS = {"SYDC"}
STAFF_PROFILES = {"enterpriseAdmin", "globalAdmin", "Enterprise Admin", "Global Admin"}

# ponytail: mirrors migrations 0089-0104; delete once PROD carries Organizations.TenantCode.
_LEGACY_TENANT_OF_ORG = {
    "GNRL": "generali",
    "SSIX": "generali",
    "PDBS": "ms02",
    "SYDC": "sydoc",
    "CMPS": "sydoc",
    "LKTR": "sydoc",
    "PRVR": "sydoc",
}

_PROCESS_RE = re.compile(
    r"^(?:process\.(?P<a>[^.]+\.[^.]+)\.view"
    r"|(?:workitems|dashboard)\.filter\.process\.(?P<b>[^.]+\.[^.]+)"
    r"|reporting\.scope\.process\.(?P<c>[^.]+\.[^.]+))$"
)
_TENANT_RE = re.compile(r"^tenant\.([^.]+)\.")
# Built at runtime from the profile name / dbo.ReportingSources.Permission: never a literal in code.
_DYNAMIC_RE = re.compile(r"^(admin\.assign\.user\.accessprofile|reporting\.source)\.")

# A curated reporting source names its customer in front of an em dash --
# "Privera — Posteingang", "Compass Group — Verrechnung". That prefix is the
# only place the ownership is written down: nothing in dbo.ReportingSources
# records an OrganizationCode. The dash must be an em/en dash with spaces
# around it, never a plain hyphen -- "Elektro-Material" carries one inside
# the name itself.
# Spelled as escapes rather than pasted in: ruff reads a bare em dash in source
# as a mistyped hyphen (RUF001), which is a fair warning everywhere but here.
_DASHES = "\u2014\u2013"  # em dash, en dash
_SOURCE_OWNER_RE = re.compile(rf"^(.+?)\s+[{_DASHES}]\s+")


@dataclass
class Snapshot:
    orgs: dict  # code -> (name, tenant_code | None)
    profiles: dict  # access_id -> (name, org_code | None)
    codes: list  # every catalogue code
    profile_grants: dict  # access_id -> set(code)  (allow rows only)
    profile_deny_rows: int
    overrides: list  # (user_id, code, effect)
    users: list  # (user_id, username, access_id, org_code)
    effective: dict  # user_id -> set(code) from spGetUserPermissions
    process_org: dict  # "<client>.<name>" -> org_code
    corpus: str  # nx_lib + templates + static/js concatenated
    # permission code -> label, from dbo.ReportingSources. Defaulted so a
    # database without that table (or an older caller) still audits.
    sources: dict = field(default_factory=dict)


def code_owner(code: str, process_org: dict, org_by_label: dict):
    """Which org or tenant a code belongs to; None for global codes."""
    m = _PROCESS_RE.match(code)
    if m:
        key = m.group("a") or m.group("b") or m.group("c")
        prefix = key.split(".")[0].lower()
        return ("org", process_org.get(key) or org_by_label.get(prefix) or prefix)
    m = _TENANT_RE.match(code)
    if m:
        return ("tenant", m.group(1))
    if code.startswith("generali."):
        return ("tenant", "generali")
    if code.startswith("admin.view.mobscn."):
        return ("tenant", "ms02")
    if code.startswith("invoices.view."):
        x = code.rsplit(".", 1)[1].lower()
        return ("org", org_by_label.get(x) or x)
    return None


def _slug(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (v or "").lower())


def source_owner(label: str, org_by_label: dict):
    """Which org a reporting source belongs to, read off its label prefix.

    None when the label names no customer ("Workitems (Octo)") or names one with
    no Organizations row (Bucherer, Frigemo, Aveniq, MediaMarkt). None means
    *unknown*, never *safe* -- callers must not raise a finding on it.

    Prefix matching runs both ways because neither side is canonical: the org is
    "Compass" where the source says "Compass Group", and the org is "sydoc AG"
    where the source says "Sydoc". Guarded at 5 characters so a four-letter org
    code cannot swallow an unrelated name.
    """
    m = _SOURCE_OWNER_RE.match(label or "")
    if not m:
        return None
    name = _slug(m.group(1))
    if not name:
        return None
    for key, org in org_by_label.items():
        k = _slug(key)
        if not k:
            continue
        if (
            k == name
            or (len(k) >= 5 and name.startswith(k))
            or (len(name) >= 5 and k.startswith(name))
        ):
            return org
    return None


def audit(s: Snapshot) -> dict:
    out = {
        k: []
        for k in (
            "Cross-organization grants",
            "Profile does not match organization",
            "Customers holding admin codes",
            "Dormant reporting-source grants",
            "Reporting sources of another customer",
            "Override noise",
            "Housekeeping",
        )
    }
    org_by_label = {}
    for code, (name, _) in s.orgs.items():
        org_by_label[code.lower()] = code
        if name:
            org_by_label[name.lower()] = code

    def tenant_of(org):
        return (s.orgs.get(org) or (None, None))[1] or _LEGACY_TENANT_OF_ORG.get(org)

    # The vendor's own tenant, derived rather than written down: every customer
    # served directly by sydoc lands in it, so two orgs sharing it are unrelated
    # to each other. Used by the reporting-source rules below.
    vendor_tenant = next((t for o in STAFF_ORGS if (t := tenant_of(o))), None)

    for uid, username, access_id, org in s.users:
        pname, porg = s.profiles.get(access_id, (None, None))
        who = f"**{username}** ({org} / {pname or 'no profile'})"
        staff = org in STAFF_ORGS or pname in STAFF_PROFILES
        home = {(org or "").lower(), (s.orgs.get(org) or ("",))[0].lower()}
        home_tenant = tenant_of(org)
        held = sorted(s.effective.get(uid, set()))

        if not staff:
            foreign = []
            for code in held:
                owner = code_owner(code, s.process_org, org_by_label)
                if owner is None:
                    continue
                kind, label = owner
                if (kind == "org" and label.lower() not in home) or (
                    kind == "tenant" and label != home_tenant
                ):
                    foreign.append(code)
            if foreign:
                out["Cross-organization grants"].append(f"- {who}: " + ", ".join(foreign))
            admin = [c for c in held if c.startswith("admin.")]
            if admin:
                out["Customers holding admin codes"].append(f"- {who}: " + ", ".join(admin))

        if pname:
            expected = porg
            if not expected:
                label = re.sub(r"\s*(user|supervisor|admin)$", "", pname.lower()).strip()
                expected = org_by_label.get(label)
            if expected and expected != org:
                out["Profile does not match organization"].append(
                    f"- {who}: profile belongs to {expected}"
                )
        else:
            out["Housekeeping"].append(f"- {who}: accessid {access_id} matches no profile")

    # Reporting-source grants are audited per *profile*, not per user: that is
    # the grain somebody actually clicks, and both faults below are properties of
    # the profile rather than of whoever happens to sit in it.
    for aid, (pname, porg) in sorted(s.profiles.items(), key=lambda kv: kv[1][0] or ""):
        grants = s.profile_grants.get(aid, set())
        held = sorted(c for c in grants if c in s.sources)
        if not held:
            continue

        # A source grant without reporting.view does nothing today, which is
        # exactly what makes it dangerous: it is invisible in use, and it goes
        # live the moment somebody grants reporting.view for an unrelated reason.
        if "reporting.view" not in grants:
            out["Dormant reporting-source grants"].append(
                f"- **{pname}**: holds "
                + ", ".join(f"`{c}`" for c in held)
                + " without `reporting.view` -- dormant now, live the moment anyone"
                + " grants that profile reporting access"
            )

        # The table provider applies no row scoping, so the source permission is
        # the whole gate. A customer profile holding another customer's source is
        # therefore the real cross-tenant case, not a tidiness question.
        if porg and pname not in STAFF_PROFILES:
            foreign = []
            for code in held:
                owner = source_owner(s.sources[code], org_by_label)
                if owner is None or owner == porg:
                    continue
                owner_tenant, profile_tenant = tenant_of(owner), tenant_of(porg)
                # Sharing a tenant is only evidence of a shared product, and only
                # outside the vendor's own tenant. ISS and Generali sit in the
                # generali tenant and read each other's sources by design. But
                # Privera, Compass and Elektro-Material all sit in *sydoc* --
                # that says they are the vendor's customers, not that they are
                # one another's, so it must not excuse anything.
                if (
                    owner_tenant is not None
                    and owner_tenant == profile_tenant
                    and owner_tenant != vendor_tenant
                ):
                    continue
                foreign.append(f"`{code}` (belongs to {owner})")
            if foreign:
                out["Reporting sources of another customer"].append(
                    f"- **{pname}** ({porg}): " + ", ".join(foreign)
                )

    grants_of_user = {uid: s.profile_grants.get(aid, set()) for uid, _, aid, _ in s.users}
    name_of_user = {uid: u for uid, u, _, _ in s.users}
    for uid, code, effect in s.overrides:
        base = grants_of_user.get(uid, set())
        if effect == "A" and code in base:
            out["Override noise"].append(
                f"- **{name_of_user.get(uid, uid)}**: redundant allow `{code}` (profile grants it)"
            )
        if effect == "D" and code not in base:
            out["Override noise"].append(
                f"- **{name_of_user.get(uid, uid)}**: no-op deny `{code}` (profile never grants it)"
            )

    if s.profile_deny_rows:
        out["Housekeeping"].append(
            f"- {s.profile_deny_rows} profile-level deny rows: no effect, a missing row already denies (#238 migration 0086 drops them)"
        )
    users_per_profile = {}
    for _, _, aid, _ in s.users:
        users_per_profile[aid] = users_per_profile.get(aid, 0) + 1
    empty = sorted(n for aid, (n, _) in s.profiles.items() if not users_per_profile.get(aid))
    if empty:
        out["Housekeeping"].append("- Profiles with no users: " + ", ".join(empty))
    held_somewhere = set().union(*s.profile_grants.values()) if s.profile_grants else set()
    held_somewhere |= {c for _, c, e in s.overrides if e == "A"}
    unheld = sorted(c for c in s.codes if c not in held_somewhere)
    if unheld:
        out["Housekeeping"].append("- Codes nobody holds: " + ", ".join(unheld))
    unref = sorted(
        c
        for c in s.codes
        if not (_PROCESS_RE.match(c) or _TENANT_RE.match(c) or _DYNAMIC_RE.match(c))
        and c not in s.corpus
    )
    if unref:
        out["Housekeeping"].append(
            "- Codes not referenced in nx_lib/templates/static (may be built dynamically): "
            + ", ".join(unref)
        )
    return out


def render(env: str, server: str, s: Snapshot, out: dict) -> str:
    lines = [
        f"# Permission audit - {env} ({server}) - {date.today().isoformat()}",
        "",
        f"users {len(s.users)} | profiles {len(s.profiles)} | codes {len(s.codes)} | "
        f"overrides {len(s.overrides)} | profile-deny rows {s.profile_deny_rows}",
        "",
    ]
    any_finding = False
    for section, items in out.items():
        if not items:
            continue
        any_finding = True
        lines += [f"## {section} ({len(items)})", *items, ""]
    if not any_finding:
        lines.append("No anomalies.")
    return "\n".join(lines)


# ---- DB side -----------------------------------------------------------------


def _load_db_migrate():
    spec = importlib.util.spec_from_file_location("_dbm", REPO_ROOT / "scripts" / "db-migrate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def snapshot(cur) -> Snapshot:
    def rows(sql, *args):
        cur.execute(sql, *args)
        return cur.fetchall()

    def has_col(table, col):
        return rows(f"SELECT COL_LENGTH('dbo.{table}', '{col}')")[0][0] is not None

    prof_org = "OrganizationCode" if has_col("AccessProfile", "OrganizationCode") else "NULL"
    profiles = {
        r[0]: (r[1], r[2])
        for r in rows(f"SELECT AccessID, Name, {prof_org} FROM dbo.AccessProfile")
    }
    codes = [r[0] for r in rows("SELECT Code FROM dbo.Permission ORDER BY Code")]
    effect_col = has_col("AccessProfilePermission", "Effect")
    grants = {}
    for aid, code in rows(
        "SELECT ap.AccessID, p.Code FROM dbo.AccessProfilePermission ap JOIN dbo.Permission p ON p.PermissionID = ap.PermissionID"
        + (" WHERE ap.Effect = 'A'" if effect_col else "")
    ):
        grants.setdefault(aid, set()).add(code)
    deny_rows = (
        rows("SELECT COUNT(*) FROM dbo.AccessProfilePermission WHERE Effect = 'D'")[0][0]
        if effect_col
        else 0
    )
    overrides = [
        tuple(r)
        for r in rows(
            "SELECT uo.UserID, p.Code, uo.Effect FROM dbo.UserPermissionOverride uo JOIN dbo.Permission p ON p.PermissionID = uo.PermissionID"
        )
    ]
    users = [
        tuple(r)
        for r in rows(
            "SELECT userID, username, accessid, organizationCode FROM dbo.Users ORDER BY username"
        )
    ]
    tenant_col = "TenantCode" if has_col("Organizations", "TenantCode") else "NULL"
    orgs = {
        r[0]: (r[1], r[2])
        for r in rows(f"SELECT organizationcode, Organization, {tenant_col} FROM dbo.Organizations")
    }
    ps_org = "OrganizationCode" if has_col("ProcessSources", "OrganizationCode") else "NULL"
    process_org = {
        r[0]: r[1] for r in rows(f"SELECT ProcessName, {ps_org} FROM dbo.ProcessSources") if r[1]
    }
    sources = {}
    if rows("SELECT OBJECT_ID('dbo.ReportingSources')")[0][0] is not None:
        sources = {
            r[0]: r[1]
            for r in rows("SELECT Permission, Label FROM dbo.ReportingSources WHERE Enabled = 1")
        }
    effective = {}
    for uid, *_ in users:
        effective[uid] = {r[0] for r in rows("EXEC dbo.spGetUserPermissions ?", uid)}
    corpus = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for pattern in ("nx_lib/**/*.py", "templates/**/*.html", "static/js/*.js")
        for p in REPO_ROOT.glob(pattern)
    )
    return Snapshot(
        orgs,
        profiles,
        codes,
        grants,
        deny_rows,
        overrides,
        users,
        effective,
        process_org,
        corpus,
        sources,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read-only anomaly audit of the nexora permission model."
    )
    ap.add_argument("--env", default="PROD", help="env file to load (default PROD)")
    args = ap.parse_args()
    dbm = _load_db_migrate()
    cfg = dbm.load_nexora_config(args.env)
    if not (cfg.DB_SERVER_PRD and cfg.DB_UID and cfg.DB_PWD):
        sys.stderr.write("Missing DB_SERVER_PRD / DB_UID / DB_PWD in env\n")
        return 2
    cn = dbm.connect(cfg.DB_SERVER_PRD, cfg.DB_NEXORA or "nexora", cfg.DB_UID, cfg.DB_PWD)
    s = snapshot(cn.cursor())
    print(render(args.env, cfg.DB_SERVER_PRD, s, audit(s)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
