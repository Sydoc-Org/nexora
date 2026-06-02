# nx_lib/reporting/catalog.py
"""Field catalog for curated reporting sources.

`build_catalog` is the pure merge of FieldMetadata rows, localized label rows,
and a per-field availability map (which processes expose the field). The DB
fetch (`fetch_docprocessing_catalog`) is a thin wrapper that mirrors
dashboard.dashboard_field_metadata and feeds build_catalog.
"""

from ..db import engine_nexora_db

_LANG_COLS = {"de": "GermanLabel", "fr": "FrenchLabel", "it": "ItalianLabel"}


def build_catalog(meta_rows, label_rows, availability, *, lang_col):
    """Merge metadata + labels + availability into a sorted list of field dicts.

    Each entry: {field, label, type, aggregable, sortable, filterable, processes}.
    A field is only included if it appears in `availability` (i.e. at least one
    permitted process exposes it). Filterable = appears in availability (every
    exposed field can be filtered in phase 1).
    """
    labels = {}
    for r in label_rows:
        labels[r.FieldKey] = getattr(r, lang_col, None) or r.EnglishLabel

    out = []
    for r in meta_rows:
        fk = r.FieldKey
        if fk not in availability:
            continue
        out.append(
            {
                "field": fk,
                "label": labels.get(fk) or fk.replace("_", " ").title(),
                "type": r.DataType,
                "aggregable": bool(r.Aggregable),
                "sortable": bool(r.Sortable),
                "filterable": True,
                "processes": sorted(availability[fk]),
            }
        )
    out.sort(key=lambda e: e["label"])
    return out


def lang_col_for(locale_str):
    """Return the FieldMetadata label column name for a locale string."""
    return _LANG_COLS.get(locale_str, "EnglishLabel")


def fetch_docprocessing_catalog(allowed_processes, locale_str):
    """Load the docprocessing field catalog for the given allowed processes.

    Returns build_catalog(...) output. Mirrors the dashboard field_metadata
    query: FieldMetadata (+ Search_Field_Labels) joined to per-process
    SearchConfig.col_* availability. `processname`/`status` are always available
    for any allowed process.
    """
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT FieldKey, DataType, Aggregable, Sortable FROM FieldMetadata")
        meta_rows = cur.fetchall()
        cur.execute(
            "SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel "
            "FROM Search_Field_Labels"
        )
        label_rows = cur.fetchall()

        cur.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cur.description if c[0].startswith("col_")]
        if not cols:
            return build_catalog(meta_rows, label_rows, {}, lang_col=lang_col_for(locale_str))
        select_cols = ", ".join(cols)
        cur.execute(f"SELECT ProcessName, {select_cols} FROM SearchConfig")
        availability = {}
        allowed = set(allowed_processes)
        for row in cur.fetchall():
            if row.ProcessName not in allowed:
                continue
            for i, col in enumerate(cols):
                if row[i + 1]:
                    availability.setdefault(col[len("col_") :], []).append(row.ProcessName)
        for fk in ("processname", "status"):
            availability[fk] = list(allowed_processes)

        return build_catalog(meta_rows, label_rows, availability, lang_col=lang_col_for(locale_str))
    finally:
        if conn:
            conn.close()
