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
        "permission": "reporting.source.docprocessing",
        "engine": "statistics",
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
        "label": "Live SQL — Octopus",
        "permission": "reporting.sql.target.octopus",
        "engine": "octo_ro",
        "target": "octopus",
    },
}


def get_source(source_id):
    """Return the source descriptor dict, or None if unknown."""
    return _SOURCES.get(source_id)


def list_accessible_sources(permissions):
    """Return source descriptors the holder of `permissions` (a set) may use."""
    return [s for s in _SOURCES.values() if s["permission"] in permissions]
