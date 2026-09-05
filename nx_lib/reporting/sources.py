# nx_lib/reporting/sources.py
"""Registry of reporting data sources.

Phase 1 ships one curated source: `docprocessing` (Document Processing stats).
Sources are code-defined for now; a DB-backed registry can replace this later.
Each source: {id, kind, label, permission, engine}. `engine` is a key resolved
to a real SQLAlchemy engine in the view layer (keeps this module DB-free for
unit tests).
"""

DEFAULT_ROW_LIMIT = 5000
MAX_ROW_LIMIT = 50000
SQL_ROW_CAP = 50000  # row ceiling for live-SQL results (after the ritual gate)
SQL_TIMEOUT_S = 30  # per-query statement timeout for sandboxed SQL

_SOURCES = {
    "docprocessing": {
        "id": "docprocessing",
        "kind": "curated",
        "label": "Document Processing",
        "permission": "reporting.source.docprocessing.use",
        "engine": "statistics",
        "provider": "docprocessing",
    },
    "sql_statistics": {
        "id": "sql_statistics",
        "kind": "sql",
        "label": "Live SQL — Statistics",
        "permission": "reporting.sql.run",
        "engine": "statistics_ro",
        "target": "statistics",
    },
    "sql_octopus": {
        "id": "sql_octopus",
        "kind": "sql",
        "label": "Live SQL — Octo",
        "permission": "reporting.sql.target.octopus.use",
        "engine": "octo_ro",
        "target": "octopus",
    },
}


def code_sources():
    """The code-defined default source descriptors (a fresh copy of each)."""
    return [dict(s) for s in _SOURCES.values()]


def merge_sources(defaults, db_rows):
    """Overlay DB registry rows on the code defaults; drop disabled; sort.

    `defaults` is code_sources(); `db_rows` are dicts keyed by `code` (with any
    of label/permission/kind/engine/target/provider/baseObject/columns/enabled/
    sortOrder, None meaning "leave the default"). A db row whose code is unknown
    registers a brand-new source. Returns the effective, enabled, sorted list.
    """
    eff = {s["id"]: dict(s) for s in defaults}
    for row in db_rows:
        code = row.get("code")
        if not code:
            continue
        base = eff.get(code, {"id": code})
        for k, v in row.items():
            if k == "code" or v is None:
                continue
            base[k] = v
        base["id"] = code
        eff[code] = base
    out = [s for s in eff.values() if s.get("enabled", True)]
    out.sort(key=lambda s: (s.get("sortOrder", 100), s.get("label", "")))
    return out


def accessible(sources, permissions):
    """Filter effective `sources` to those the holder of `permissions` may use."""
    return [s for s in sources if s.get("permission") in permissions]
