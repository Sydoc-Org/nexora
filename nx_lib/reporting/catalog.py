# nx_lib/reporting/catalog.py
"""Field catalog for curated reporting sources.

`build_catalog` derives the catalog from the per-field availability map (which
processes expose each field) and localized label rows, with FieldMetadata as
*optional* enrichment for type/aggregable/sortable. The DB fetch
(`fetch_docprocessing_catalog`) is a thin wrapper that loads the mapping_config
#98 registry's availability + labels (required) plus FieldMetadata (optional;
FieldMetadata does not exist on every environment -- see D10, untouched by
this whole plan).
"""

from types import SimpleNamespace

from flask import current_app
from flask_babel import gettext as _

from .. import mapping_config
from ..db import engine_nexora_db

_LANG_COLS = {"de": "GermanLabel", "fr": "FrenchLabel", "it": "ItalianLabel"}

# Synthetic date fields, derived from ProcessSources (not ProcessFieldMappings).
# field_key -> the ProcessSource attribute holding its date expression.
_DATE_FIELDS = (("import_date", "import_column"), ("export_date", "export_column"))

# Synthetic workitem-id field, derived from ProcessSource.workitem_column.
# One canonical field key; the actual column name varies per process
# (WorkItem / WorkitemID / WID ...).
_WORKITEM_FIELD = "workitem_id"


def date_availability(sources, allowed_processes):
    """{date_field: [process, ...]} for processes (in scope) whose
    ProcessSource import_column/export_column is non-null. Pure: `sources` are
    mapping_config.ProcessSource rows (or any object exposing .process /
    .import_column / .export_column)."""
    allowed = set(allowed_processes)
    out = {}
    for s in sources:
        if s.process not in allowed:
            continue
        for field, attr in _DATE_FIELDS:
            if getattr(s, attr):
                out.setdefault(field, []).append(s.process)
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


def workitem_availability(sources, allowed_processes):
    """[process, ...] (in scope) whose ProcessSource.workitem_column is
    non-null. Pure: `sources` are mapping_config.ProcessSource rows (or any
    object exposing .process / .workitem_column)."""
    allowed = set(allowed_processes)
    return [s.process for s in sources if s.process in allowed and s.workitem_column]


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


# Tables whose absence is already reported this process. FieldMetadata has never
# been created in any environment (the widget engine that owned it was removed
# in 2.5.65 -- see nx_lib/views/dashboard.py), so the miss is permanent and
# firing a WARNING per reporting request buried the log in thousands of
# identical lines a day. Report each table once, with the driver's message so a
# *new* cause (permission revoked, column dropped) is distinguishable from the
# expected "table does not exist".
_WARNED_TABLES = set()


def _warn_once(table, exc):
    """Log an optional catalog table's absence once per process."""
    if table in _WARNED_TABLES:
        return
    _WARNED_TABLES.add(table)
    current_app.logger.warning(
        "reporting catalog: %s unavailable (%s) -- catalog falls back to "
        "defaults; not logged again this process",
        table,
        str(exc).strip().replace(chr(10), " ")[:200],
    )


def fetch_docprocessing_catalog(allowed_processes, locale_str):
    """Load the docprocessing field catalog for the given allowed processes.

    Returns build_catalog(...) output. The mapping_config #98 registry's
    ProcessFieldMappings availability is the source of truth for the field
    set (required -- a registry load failure raises rather than silently
    returning an empty catalog, same fail-loud contract as
    nx_lib/views/dashboard.py's `_statconfig_sources`); FieldLabels (labels)
    and FieldMetadata (type/aggregable/sortable enrichment) are optional -- a
    missing table/registry or query error for either yields empty rows rather
    than a 500. `processname` is always available for any allowed process
    (synthesized by the query builder as a constant per subquery). `status`
    is NOT injected here — the registry has no status field mapping, so the
    query builder cannot resolve it.
    """
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()

        # Optional enrichment: FieldMetadata may not exist on every environment.
        try:
            cur.execute("SELECT FieldKey, DataType, Aggregable, Sortable FROM FieldMetadata")
            meta_rows = cur.fetchall()
        except Exception as exc:
            _warn_once("FieldMetadata", exc)
            meta_rows = []
    finally:
        if conn:
            conn.close()

    # Required: the registry drives the availability map (the field set). A
    # load failure must surface as an error here, never be silently reshaped
    # into an empty catalog that looks like "no fields configured".
    if mapping_config.registry() is None:
        raise RuntimeError("mapping_config registry unavailable")

    # Optional: localized labels.
    label_dict = mapping_config.labels() or {}
    label_rows = [
        SimpleNamespace(
            FieldKey=key,
            EnglishLabel=meta.get("en"),
            GermanLabel=meta.get("de"),
            FrenchLabel=meta.get("fr"),
            ItalianLabel=meta.get("it"),
        )
        for key, meta in label_dict.items()
    ]

    # Scope to the 'default' client only (same convention as the workitems
    # doc-field search path, e.g. get_workitems_data's default docfield
    # pre-fetch: `ClientCode = 'default'`). Without this filter, an 'ms02'
    # ProcessFieldMappings row for a process that ALSO has a 'default' row
    # (e.g. 'sydoc.05_PDBS') would contribute its field mappings into this
    # catalog too -- a field that only exists for MS02 would show up as
    # "available" in the default docprocessing source's catalog, even though
    # the default runner (StatisticsDB) can't resolve it.
    availability = {}
    allowed = set(allowed_processes)
    for m in mapping_config.mappings_for("default", allowed_processes):
        if m.process not in allowed:
            continue
        availability.setdefault(m.field_key, []).append(m.process)
    availability["processname"] = list(allowed_processes)

    catalog = build_catalog(meta_rows, label_rows, availability, lang_col=lang_col_for(locale_str))

    # Synthetic fields from ProcessSources (a different table from
    # ProcessFieldMappings): import_date / export_date as first-class date
    # fields, workitem_id from workitem_column. Non-ms02 clients only, same
    # scope as the legacy Statconfig read.
    if mapping_config.registry() is None:
        current_app.logger.warning("reporting catalog: ProcessSources unavailable")
        sources = []
    else:
        sources = [
            s
            for s in mapping_config.sources_for(None, allowed_processes)
            if (s.client or "default") != "ms02"
        ]
    date_avail = date_availability(sources, allowed_processes)
    catalog += date_catalog_entries(
        date_avail, {"import_date": _("Import date"), "export_date": _("Export date")}
    )
    if date_avail:
        # Shared time axis for date-anchored measures (imported/exported/
        # backlog): each measure buckets its OWN date onto this axis. Only
        # valid together with anchored metrics — _prepare_run enforces.
        catalog.append(
            {
                "field": "activity_date",
                "label": _("Date"),
                "type": "date",
                "aggregable": False,
                "sortable": True,
                "filterable": True,
                "grainable": True,
                "processes": sorted({p for ps in date_avail.values() for p in ps}),
            }
        )
    catalog += workitem_catalog_entries(
        workitem_availability(sources, allowed_processes), _("Workitem ID")
    )
    catalog.sort(key=lambda e: e["label"])
    return catalog
