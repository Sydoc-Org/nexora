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

_SOURCES = {
    "docprocessing": {
        "id": "docprocessing",
        "kind": "curated",
        "label": "Document Processing",
        "permission": "reporting.source.docprocessing",
        "engine": "statistics",
    },
}


def get_source(source_id):
    """Return the source descriptor dict, or None if unknown."""
    return _SOURCES.get(source_id)


def list_accessible_sources(permissions):
    """Return source descriptors the holder of `permissions` (a set) may use."""
    return [s for s in _SOURCES.values() if s["permission"] in permissions]
