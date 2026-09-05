"""One-off: rename permission codes per docs/superpowers/specs/2026-09-01-permission-structure-design.md
Appendix A. --emit-sql prints migration 0088; --apply rewrites literals in the tree. Deleted after use (#238)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWEEP_DIRS = [
    "nx_lib",
    "templates",
    "static/js",
    "tests",
    "sql/test",
    "docs/howto",
    "docs/design",
    "CLAUDE.md",
    "README.md",
    "CONTRIBUTING.md",
]
SKIP_PARTS = {"__pycache__", "superpowers"}

# old -> (new, description). "=" as new keeps the code and rewrites the description.
MAPPING: dict[str, tuple[str, str]] = {
    # admin
    "admin.view": ("=", "View the admin area"),
    "admin.view.users": ("admin.users.view", "View users"),
    "admin.create.user": ("admin.users.add", "Add users"),
    "admin.edit.user": ("admin.users.edit", "Edit users"),
    "admin.delete.user": ("admin.users.delete", "Delete users"),
    "admin.edit.user.override": (
        "admin.users.overrides.edit",
        "Edit per-user permission overrides",
    ),
    "admin.view.accessprofiles.useroverrides": (
        "admin.profiles.view",
        "View access profiles and the permissions grid",
    ),
    "admin.edit.accessprofile": ("admin.profiles.edit", "Edit access profiles and their grants"),
    "admin.view.organizations": ("admin.organizations.view", "View organizations"),
    "admin.add.organization": ("admin.organizations.add", "Add organizations"),
    "admin.edit.organization": ("admin.organizations.edit", "Edit organizations"),
    "admin.delete.organization": ("admin.organizations.delete", "Delete organizations"),
    "admin.edit.organization.branding": (
        "admin.organizations.branding.edit",
        "Edit organization branding",
    ),
    "admin.view.clients": ("admin.clients.view", "View the client registry"),
    "admin.edit.clients": ("admin.clients.edit", "Edit the client registry"),
    "admin.view.processes": ("admin.processes.view", "View process source mappings"),
    "admin.edit.processes": ("admin.processes.edit", "Edit process source mappings (high trust)"),
    "admin.view.active.sessions": ("admin.sessions.view", "View active sessions"),
    "admin.view.system.logs": ("admin.logs.view", "View system logs"),
    "admin.status.view": ("=", "View the system status page"),
    "admin.maintenance.view": ("=", "View the maintenance page"),
    "admin.maintenance.edit": ("=", "Edit and release maintenance periods"),
    "admin.maintenance.bypass": ("=", "Bypass the maintenance lockout"),
    "admin.restart": ("admin.server.restart", "Restart the local dev server (dev only)"),
    # workitems
    "workitems.view": ("=", "View the workitems page"),
    "workitems.details.view": ("=", "View workitem details"),
    "workitems.details.view.audit": (
        "workitems.details.audit.view",
        "View the workitem audit trail",
    ),
    "workitems.details.view.fields": ("workitems.details.fields.view", "View extracted fields"),
    "workitems.details.view.images": ("workitems.details.images.view", "View document images"),
    "workitems.details.view.confidence": (
        "workitems.details.confidence.view",
        "View extraction confidence scores",
    ),
    "workitems.details.view.source_location": (
        "workitems.details.sources.view",
        "View where values were found on the page (needs images.view)",
    ),
    "workitems.filter.datetime": ("workitems.filter.date.view", "Filter by date"),
    "workitems.filter.status": ("workitems.filter.status.view", "Filter by status"),
    "workitems.filter.status.deleted": (
        "workitems.filter.deleted.view",
        "Filter for deleted workitems (internal; needs status.view)",
    ),
    "workitems.filter.stage": ("workitems.filter.stage.view", "Filter by process stage"),
    "workitems.filter.workitemid": ("workitems.filter.id.view", "Search by workitem id"),
    "workitems.filter.documentfields": (
        "workitems.filter.docfields.view",
        "Filter by document fields",
    ),
    "workitems.filter.documentfields.sensitive": (
        "workitems.filter.docfields.sensitive.view",
        "Filter by sensitive document fields (needs docfields.view)",
    ),
    "workitems.import.workitem": ("workitems.import.run", "Import a workitem"),
    "workitems.import.preparedaudit": (
        "workitems.prepared.view",
        "View the prepared-documents import and audit page",
    ),
    # dashboard, api, jd
    "dashboard.view": ("=", "View the dashboard"),
    "api.docs.view": ("=", "View the in-app API documentation"),
    "jd.view": ("=", "View the JD page"),
    # reporting
    "reporting.view": ("=", "View the reporting page"),
    "reporting.export": ("=", "Export reports to Excel"),
    "reporting.schedule": ("=", "Schedule reports for email delivery"),
    "reporting.sql.run": ("=", "Run live read-only SQL in the sandbox"),
    "reporting.sql.target.octopus": (
        "reporting.sql.target.octopus.use",
        "Target the Octo runtime DB in the sandbox",
    ),
    "reporting.ai.use": ("=", "Use the AI assistant"),
    "reporting.ai.sql": ("reporting.ai.sql.use", "Receive AI-drafted SQL (needs sql.run)"),
    "reporting.ai.explain_data": (
        "reporting.ai.explain.use",
        "Let the AI run queries and explain results (data egress; needs sql.run)",
    ),
    "reporting.admin.sources": ("reporting.sources.manage", "Manage the data-source registry"),
    "reporting.sources.schema": (
        "reporting.sources.schema.view",
        "Browse tables and columns of a source",
    ),
    "reporting.semantic.admin": (
        "reporting.metrics.manage",
        "Manage the canonical metrics registry",
    ),
    "reporting.source.docprocessing": (
        "reporting.source.docprocessing.use",
        "Use the Document Processing source",
    ),
    "reporting.source.workitems": (
        "reporting.source.workitems.use",
        "Use the Workitems (Octo) source",
    ),
    "reporting.source.generali.pdqm": (
        "reporting.source.generali_pdqm.use",
        "Use the Generali PDQM source",
    ),
    # tenant.ms02 (already in grammar; description only)
    "tenant.ms02.view": ("=", "View the MS02 pilot tenant pages"),
    "tenant.ms02.edit": ("=", "Edit the MS02 pilot tenant data"),
    # generali -> tenant.generali
    "generali.dashboard.view": ("tenant.generali.view", "View the Generali dashboard"),
    "generali.documentlist.view": (
        "tenant.generali.documents.view",
        "View the Generali document list",
    ),
    "generali.importstatus.view": (
        "tenant.generali.importstatus.view",
        "View the Generali import status",
    ),
    "generali.additionalservices.view": (
        "tenant.generali.attendance.view",
        "View the attendance page (Zusätzliche Leistungen)",
    ),
}

_SCOPE_TXT = {
    ".org": " for the own organization",
    ".all": " for every organization",
    ".pastdeadline": " past the deadline",
}
_GENERALI = {
    "attendance": ("attendance records", ("add", "edit", "delete"), True),
    "baseservices": ("base service records", ("add", "edit", "delete"), True),
    "pdqm": ("PDQM records", ("add", "edit", "delete"), True),
    "projectmanagement": ("project management records", ("add", "edit", "delete"), True),
    "reporting": ("reporting records", ("add", "edit", "delete"), False),
}
for _obj, (_noun, _actions, _add_scoped) in _GENERALI.items():
    if _obj != "attendance":  # attendance.view comes from additionalservices.view above
        MAPPING[f"generali.{_obj}.view"] = (
            f"tenant.generali.{_obj}.view",
            f"View the Generali {_noun} page",
        )
    MAPPING[f"generali.{_obj}.add"] = (f"tenant.generali.{_obj}.add", f"Add own {_noun}")
    MAPPING[f"generali.{_obj}.add.bypass.deadline"] = (
        f"tenant.generali.{_obj}.add.pastdeadline",
        f"Add {_noun} past the deadline",
    )
    for _action in _actions:
        for _old, _new in ((".organizational", ".org"), (".transorganizational", ".all")):
            if _action == "add" and not _add_scoped:
                continue
            MAPPING[f"generali.{_obj}.{_action}{_old}"] = (
                f"tenant.generali.{_obj}.{_action}{_new}",
                f"{_action.capitalize()} {_noun}{_SCOPE_TXT[_new]}",
            )


def resolved() -> list[tuple[str, str, str]]:
    return [(old, old if new == "=" else new, desc) for old, (new, desc) in MAPPING.items()]


def emit_sql() -> str:
    rows = ",\n".join(
        f"    (N'{o}', N'{n}', N'{d.replace(chr(39), chr(39) * 2)}')" for o, n, d in resolved()
    )
    return f"""-- 0088_permission_rename.sql (#238 phase 3) -- generated by scripts/rename_permissions.py --emit-sql
-- Renames codes to <area>.<object>.<action>[.<scope>] and rewrites descriptions.
-- Grants ride on PermissionID. Data-driven: codes absent on this server are skipped.
DECLARE @map TABLE (OldCode SYSNAME PRIMARY KEY, NewCode SYSNAME, NewDescription NVARCHAR(200));
INSERT INTO @map VALUES
{rows};
-- A concurrent worktree can land a same-named permission before this rename
-- applies (e.g. #255's tenant-platform work seeding 'tenant.generali.view'
-- ahead of #238 -- spec decision D3: this migration owns the code, the
-- tenant platform finds it in place). Merge such a duplicate's grants onto
-- the row this migration is about to rename into that code, then retire the
-- duplicate, so the rename below never collides on the UNIQUE(Code).
DECLARE @dups TABLE (DupPermID INT PRIMARY KEY, CanonicalPermID INT);
INSERT INTO @dups (DupPermID, CanonicalPermID)
SELECT p.PermissionID, o.PermissionID
FROM @map m
JOIN dbo.Permission p ON p.Code = m.NewCode
JOIN dbo.Permission o ON o.Code = m.OldCode
WHERE m.OldCode <> m.NewCode AND o.PermissionID <> p.PermissionID;
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, d.CanonicalPermID
FROM dbo.AccessProfilePermission ap
JOIN @dups d ON d.DupPermID = ap.PermissionID
WHERE NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x
                  WHERE x.AccessID = ap.AccessID AND x.PermissionID = d.CanonicalPermID);
INSERT INTO dbo.UserPermissionOverride (UserID, PermissionID, Effect)
SELECT o2.UserID, d.CanonicalPermID, o2.Effect
FROM dbo.UserPermissionOverride o2
JOIN @dups d ON d.DupPermID = o2.PermissionID
WHERE NOT EXISTS (SELECT 1 FROM dbo.UserPermissionOverride x
                  WHERE x.UserID = o2.UserID AND x.PermissionID = d.CanonicalPermID);
DELETE ap FROM dbo.AccessProfilePermission ap JOIN @dups d ON d.DupPermID = ap.PermissionID;
DELETE o2 FROM dbo.UserPermissionOverride o2 JOIN @dups d ON d.DupPermID = o2.PermissionID;
DELETE p FROM dbo.Permission p JOIN @dups d ON d.DupPermID = p.PermissionID;
IF EXISTS (SELECT 1 FROM @map m JOIN dbo.Permission p ON p.Code = m.NewCode
           JOIN dbo.Permission o ON o.Code = m.OldCode WHERE m.OldCode <> m.NewCode AND o.PermissionID <> p.PermissionID)
    THROW 50088, 'permission rename target already exists with a different PermissionID', 1;
UPDATE p SET p.Code = m.NewCode, p.Description = m.NewDescription
FROM dbo.Permission p JOIN @map m ON m.OldCode = p.Code;
UPDATE r SET r.Permission = m.NewCode
FROM dbo.ReportingSources r JOIN @map m ON m.OldCode = r.Permission;
INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.permissions.edit', 'Edit the permission catalogue (descriptions, add, delete)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'admin.permissions.edit');
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, np.PermissionID
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission hp ON hp.PermissionID = ap.PermissionID AND hp.Code = 'admin.profiles.edit'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'admin.permissions.edit'
  AND NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID);
GO
"""


def apply() -> None:
    pairs = sorted(((o, n) for o, n, _ in resolved() if o != n), key=lambda p: -len(p[0]))
    patterns = [
        (re.compile(rf"(?<![A-Za-z0-9_.]){re.escape(o)}(?![A-Za-z0-9_.])"), n) for o, n in pairs
    ]
    for entry in SWEEP_DIRS:
        base = ROOT / entry
        files = (
            [base]
            if base.is_file()
            else [p for p in base.rglob("*") if p.is_file() and not (SKIP_PARTS & set(p.parts))]
        )
        for f in files:
            if f.suffix not in {".py", ".html", ".js", ".sql", ".md"}:
                continue
            text = f.read_text(encoding="utf-8")
            new, hits = text, 0
            for rx, n in patterns:
                new, k = rx.subn(n, new)
                hits += k
            if hits:
                f.write_bytes(new.encode("utf-8"))  # binary write keeps LF/CRLF as-is
                print(f"{hits:4d}  {f.relative_to(ROOT)}")


if __name__ == "__main__":
    if "--emit-sql" in sys.argv:
        sys.stdout.write(emit_sql())
    elif "--apply" in sys.argv:
        apply()
    else:
        sys.exit("usage: rename_permissions.py --emit-sql | --apply")
