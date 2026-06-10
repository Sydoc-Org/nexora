# nx_lib/reporting/catalog.py
"""Field catalog for curated reporting sources.

`build_catalog` derives the catalog from the per-field availability map (which
processes expose each `col_*` of SearchConfig) and localized label rows, with
FieldMetadata as *optional* enrichment for type/aggregable/sortable. The DB
fetch (`fetch_docprocessing_catalog`) is a thin wrapper that loads SearchConfig
availability (required) plus Search_Field_Labels and FieldMetadata (optional;
FieldMetadata does not exist on every environment).
"""

from flask import current_app
from flask_babel import gettext as _

from ..db import engine_nexora_db

_LANG_COLS = {"de": "GermanLabel", "fr": "FrenchLabel", "it": "ItalianLabel"}

# Synthetic date fields, derived from Statconfig (not SearchConfig.col_*).
# field_key -> the Statconfig column attribute holding its date expression.
_DATE_FIELDS = (("import_date", "ImportColumn"), ("export_date", "ExportColumn"))

# Synthetic workitem-id field, derived from Statconfig.WorkitemColumn
# (migration 0020). One canonical field key; the actual column name varies
# per process (WorkItem / WorkitemID / WID ...).
_WORKITEM_FIELD = "workitem_id"


def date_availability(statconfig_rows, allowed_processes):
    """{date_field: [process, ...]} for processes (in scope) whose Statconfig
    Import/Export column is non-null. Pure: rows are objects with ProcessName +
    ImportColumn/ExportColumn (or dicts with those keys)."""
    allowed = set(allowed_processes)
    out = {}
    for r in statconfig_rows:
        proc = r["ProcessName"] if isinstance(r, dict) else r.ProcessName
        if proc not in allowed:
            continue
        for field, attr in _DATE_FIELDS:
            val = r[attr] if isinstance(r, dict) else getattr(r, attr)
            if val:
                out.setdefault(field, []).append(proc)
    return out


def date_catalog_entries(date_avail, labels):
    """Catalog entries for the synthetic date fields. `labels` maps field_key ->
    localized label. Sorted by label; processes sorted for stable output."""
    entries = []
    for field, _attr in _DATE_FIELDS:
        procs = date_avail.get(field)
        if not procs:
            continue
        entries.append(
            {
                "field": field,
                "label": labels.get(field, field),
                "type": "date",
                "aggregable": False,
                "sortable": True,
                "filterable": True,
                "grainable": True,
                "processes": sorted(procs),
            }
        )
    entries.sort(key=lambda e: e["label"])
    return entries


def workitem_availability(statconfig_rows, allowed_processes):
    """[process, ...] (in scope) whose Statconfig WorkitemColumn is non-null.

    Pure: rows are objects or dicts with ProcessName + WorkitemColumn. A row
    without the attribute (pre-0020 Statconfig) counts as unavailable rather
    than raising, so un-migrated environments simply lack the field."""
    allowed = set(allowed_processes)
    out = []
    for r in statconfig_rows:
        proc = r["ProcessName"] if isinstance(r, dict) else r.ProcessName
        if proc not in allowed:
            continue
        val = r.get("WorkitemColumn") if isinstance(r, dict) else getattr(r, "WorkitemColumn", None)
        if val:
            out.append(proc)
    return out


def workitem_catalog_entries(processes, label):
    """Catalog entries (empty or one) for the synthetic workitem_id field."""
    if not processes:
        return []
    return [
        {
            "field": _WORKITEM_FIELD,
            "label": label,
            "type": "string",
            "aggregable": False,
            "sortable": True,
            "filterable": True,
            "grainable": False,
            "processes": sorted(processes),
        }
    ]


def build_catalog(meta_rows, label_rows, availability, *, lang_col):
    """Merge availability + labels + optional metadata into a sorted field list.

    Each entry: {field, label, type, aggregable, sortable, filterable, processes}.
    The field set is defined by `availability` (the col_* a permitted process
    exposes), NOT by FieldMetadata: a field present in `availability` always
    appears (with defaults when no FieldMetadata row backs it), and a field with
    only a FieldMetadata row but no availability is excluded. FieldMetadata, when
    present, enriches type/aggregable/sortable. Filterable is always True (every
    exposed field can be filtered in phase 1).
    """
    labels = {}
    for r in label_rows:
        labels[r.FieldKey] = getattr(r, lang_col, None) or r.EnglishLabel

    meta_by_key = {r.FieldKey: r for r in meta_rows}

    out = []
    for fk in availability:
        meta = meta_by_key.get(fk)
        out.append(
            {
                "field": fk,
                "label": labels.get(fk) or fk.replace("_", " ").title(),
                "type": meta.DataType if meta else "string",
                "aggregable": bool(meta.Aggregable) if meta else False,
                "sortable": bool(meta.Sortable) if meta else True,
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

    Returns build_catalog(...) output. SearchConfig availability is the source of
    truth for the field set; Search_Field_Labels (labels) and FieldMetadata
    (type/aggregable/sortable enrichment) are optional — a missing table or query
    error for either yields empty rows rather than a 500. `processname` is always
    available for any allowed process (synthesized by the query builder as a
    constant per subquery). `status` is NOT injected here — SearchConfig has no
    col_status column, so the query builder cannot resolve it.
    """
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()

        # Optional enrichment: FieldMetadata may not exist on every environment.
        try:
            cur.execute("SELECT FieldKey, DataType, Aggregable, Sortable FROM FieldMetadata")
            meta_rows = cur.fetchall()
        except Exception:
            current_app.logger.warning("reporting catalog: FieldMetadata unavailable")
            meta_rows = []

        # Optional: localized labels.
        try:
            cur.execute(
                "SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel "
                "FROM Search_Field_Labels"
            )
            label_rows = cur.fetchall()
        except Exception:
            current_app.logger.warning("reporting catalog: Search_Field_Labels unavailable")
            label_rows = []

        # Required: SearchConfig drives the availability map (the field set).
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
        availability["processname"] = list(allowed_processes)

        catalog = build_catalog(
            meta_rows, label_rows, availability, lang_col=lang_col_for(locale_str)
        )

        # Synthetic fields from Statconfig (a different table from SearchConfig):
        # import_date / export_date as first-class date fields, workitem_id from
        # WorkitemColumn. SELECT * so a pre-0020 Statconfig (no WorkitemColumn)
        # still yields the date fields; the helpers read attributes defensively.
        try:
            cur.execute("SELECT * FROM Statconfig")
            statconfig_rows = cur.fetchall()
        except Exception:
            current_app.logger.warning("reporting catalog: Statconfig unavailable")
            statconfig_rows = []
        date_avail = date_availability(statconfig_rows, allowed_processes)
        catalog += date_catalog_entries(
            date_avail, {"import_date": _("Import date"), "export_date": _("Export date")}
        )
        catalog += workitem_catalog_entries(
            workitem_availability(statconfig_rows, allowed_processes), _("Workitem ID")
        )
        catalog.sort(key=lambda e: e["label"])
        return catalog
    finally:
        if conn:
            conn.close()
