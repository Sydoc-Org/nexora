# tests/unit/test_reporting_catalog.py
"""Unit tests for nx_lib.reporting.catalog — pure row→catalog mapping."""

from unittest.mock import MagicMock

import pytest

import nx_lib.reporting.catalog as catalog_mod
from nx_lib import mapping_config
from nx_lib.mapping_config import FieldMapping, MappingRegistry, ProcessSource
from nx_lib.reporting.catalog import (
    build_catalog,
    date_availability,
    date_catalog_entries,
    fetch_docprocessing_catalog,
    workitem_availability,
    workitem_catalog_entries,
)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _source(client="default", process="p", table="dbo.T", **overrides):
    """A ProcessSource with sane defaults, only the fields under test set."""
    kw = {
        "client": client,
        "process": process,
        "table": table,
        "alias": None,
        "join_condition": None,
        "time_filter": None,
        "suggestion_time_filter": None,
        "export_column": None,
        "import_column": None,
        "workitem_column": None,
        "extra_condition": None,
        "id_column_type": None,
    }
    kw.update(overrides)
    return ProcessSource(**kw)


def test_date_availability_filters_nulls_and_scope():
    sources = [
        _source(
            process="compass.01_Invoice_SAP",
            import_column="ImportDate",
            export_column="UploadDatetime",
        ),
        _source(process="privera.03_Invoice_New", import_column="ImportTime", export_column=None),
        _source(process="other.99_Hidden", import_column="X", export_column="Y"),  # out of scope
    ]
    avail = date_availability(sources, ["compass.01_Invoice_SAP", "privera.03_Invoice_New"])
    assert avail == {
        "import_date": ["compass.01_Invoice_SAP", "privera.03_Invoice_New"],
        "export_date": ["compass.01_Invoice_SAP"],
    }


def test_date_catalog_entries_shape():
    entries = date_catalog_entries(
        {"import_date": ["b.p", "a.p"]},
        {"import_date": "Import date", "export_date": "Export date"},
    )
    assert entries == [
        {
            "field": "import_date",
            "label": "Import date",
            "type": "date",
            "aggregable": False,
            "sortable": True,
            "filterable": True,
            "grainable": True,
            "processes": ["a.p", "b.p"],
        }
    ]


def test_workitem_availability_filters_nulls_and_scope():
    sources = [
        _source(process="compass.01_Invoice_SAP", workitem_column="WorkItem"),
        _source(process="privera.03_Invoice_New", workitem_column=None),
        _source(process="other.99_Hidden", workitem_column="X"),  # out of scope
    ]
    avail = workitem_availability(sources, ["compass.01_Invoice_SAP", "privera.03_Invoice_New"])
    assert avail == ["compass.01_Invoice_SAP"]


def test_workitem_catalog_entries_shape():
    entries = workitem_catalog_entries(["b.p", "a.p"], "Workitem ID")
    assert entries == [
        {
            "field": "workitem_id",
            "label": "Workitem ID",
            "type": "string",
            "aggregable": False,
            "sortable": True,
            "filterable": True,
            "grainable": False,
            "processes": ["a.p", "b.p"],
        }
    ]


def test_workitem_catalog_entries_empty_when_no_process_exposes_it():
    assert workitem_catalog_entries([], "Workitem ID") == []


def test_build_catalog_merges_meta_labels_and_availability():
    meta_rows = [
        _Row(FieldKey="doctype", DataType="string", Aggregable=0, Sortable=1),
        _Row(FieldKey="pages", DataType="number", Aggregable=1, Sortable=1),
    ]
    label_rows = [
        _Row(
            FieldKey="doctype",
            EnglishLabel="Doc type",
            GermanLabel="Belegart",
            FrenchLabel=None,
            ItalianLabel=None,
        ),
    ]
    availability = {"doctype": ["acme.invoices"], "pages": ["acme.invoices"]}

    cat = build_catalog(meta_rows, label_rows, availability, lang_col="GermanLabel")
    by_key = {f["field"]: f for f in cat}

    assert by_key["doctype"]["label"] == "Belegart"
    assert by_key["doctype"]["type"] == "string"
    assert by_key["doctype"]["sortable"] is True
    assert by_key["doctype"]["aggregable"] is False
    assert by_key["doctype"]["filterable"] is True
    assert by_key["pages"]["label"] == "Pages"  # no label row → titleized key
    assert by_key["pages"]["processes"] == ["acme.invoices"]


def test_build_catalog_excludes_fields_without_availability():
    meta_rows = [_Row(FieldKey="ghost", DataType="string", Aggregable=0, Sortable=0)]
    cat = build_catalog(meta_rows, [], {}, lang_col="EnglishLabel")
    assert cat == []


def test_build_catalog_uses_defaults_when_no_metadata():
    # FieldMetadata absent (e.g. INT) — availability alone drives the field set.
    availability = {"doctype": ["p1"], "pages": ["p1"]}
    cat = build_catalog([], [], availability, lang_col="EnglishLabel")
    by_key = {f["field"]: f for f in cat}

    for fk in ("doctype", "pages"):
        assert by_key[fk]["type"] == "string"
        assert by_key[fk]["aggregable"] is False
        assert by_key[fk]["sortable"] is True
        assert by_key[fk]["filterable"] is True

    # No label row → titleized key.
    assert by_key["doctype"]["label"] == "Doctype"
    assert by_key["pages"]["label"] == "Pages"


# --------------------- fetch_docprocessing_catalog (DB fetch) --------------------- #


def _registry(*, sources=(), mappings=(), labels=None, aliases=None):
    """A MappingRegistry with just the fields fetch_docprocessing_catalog reads."""
    return MappingRegistry(
        sources={(s.client, s.process): s for s in sources},
        mappings=list(mappings),
        labels=labels or {},
        aliases=aliases or {},
    )


class _EmptyFieldMetadataCursor:
    """Fake cursor covering only the untouched FieldMetadata read (D10) --
    fetch_docprocessing_catalog's availability/labels/Statconfig-successor
    reads all go through mapping_config now, not the cursor."""

    def __init__(self, meta_rows=()):
        self._meta_rows = list(meta_rows)
        self._result = []

    def execute(self, sql, *params):
        self._result = self._meta_rows if "FROM FieldMetadata" in sql else []

    def fetchall(self):
        return self._result


def test_fetch_docprocessing_catalog_excludes_ms02_rows(app, monkeypatch):
    # Task 51: an 'ms02'-client ProcessFieldMappings row (pid, process
    # 'sydoc.05_PDBS') must not contribute a phantom field to the default
    # docprocessing catalog, even though 'sydoc.05_PDBS' is itself an allowed
    # process. A sibling 'default' row (doctype, process 'acme.invoices')
    # must still surface normally.
    reg = _registry(
        mappings=[
            FieldMapping(
                client="ms02",
                process="sydoc.05_PDBS",
                field_key="pid",
                column="PidCol",
                column_type=None,
            ),
            FieldMapping(
                client="default",
                process="acme.invoices",
                field_key="doctype",
                column="DocType",
                column_type=None,
            ),
        ]
    )
    monkeypatch.setattr(mapping_config, "registry", lambda: reg)
    engine = MagicMock()
    engine.raw_connection.return_value.cursor.return_value = _EmptyFieldMetadataCursor()
    monkeypatch.setattr(catalog_mod, "engine_nexora_db", engine)

    with app.test_request_context():
        catalog = fetch_docprocessing_catalog(["sydoc.05_PDBS", "acme.invoices"], "en")

    by_field = {c["field"]: c for c in catalog}
    assert "pid" not in by_field
    assert by_field["doctype"]["processes"] == ["acme.invoices"]


def test_fetch_docprocessing_catalog_raises_on_registry_failure(app, monkeypatch):
    """The registry failed to load (NexoraDB outage) -- this must surface as an
    error, never silently degrade to an empty 'no fields configured' catalog
    (see nx_lib/views/dashboard.py's `_statconfig_sources` fail-loud contract)."""
    monkeypatch.setattr(mapping_config, "registry", lambda: None)
    engine = MagicMock()
    engine.raw_connection.return_value.cursor.return_value = _EmptyFieldMetadataCursor()
    monkeypatch.setattr(catalog_mod, "engine_nexora_db", engine)

    with app.test_request_context(), pytest.raises(RuntimeError):
        fetch_docprocessing_catalog(["acme.invoices"], "en")


def test_build_catalog_availability_is_source_of_truth():
    # 'avail_only' has availability but no meta row → included with defaults.
    # 'meta_only' has a meta row but no availability → excluded.
    meta_rows = [
        _Row(FieldKey="meta_only", DataType="number", Aggregable=1, Sortable=0),
    ]
    availability = {"avail_only": ["p1"]}
    cat = build_catalog(meta_rows, [], availability, lang_col="EnglishLabel")
    by_key = {f["field"]: f for f in cat}

    assert "meta_only" not in by_key
    assert by_key["avail_only"]["type"] == "string"
    assert by_key["avail_only"]["aggregable"] is False
    assert by_key["avail_only"]["sortable"] is True
    assert by_key["avail_only"]["filterable"] is True


class _RaisingFieldMetadataCursor(_EmptyFieldMetadataCursor):
    """FieldMetadata raises, as it does everywhere: the table was never created."""

    def execute(self, sql, *params):
        if "FROM FieldMetadata" in sql:
            raise RuntimeError("Invalid object name 'FieldMetadata'.")
        super().execute(sql, *params)


def test_missing_optional_table_warns_once_per_process(app, monkeypatch, caplog):
    """It warned on every reporting request for months -- thousands of identical lines."""
    monkeypatch.setattr(catalog_mod, "_WARNED_TABLES", set())
    reg = _registry(
        mappings=[
            FieldMapping(
                client="default",
                process="acme.invoices",
                field_key="doctype",
                column="DocType",
                column_type=None,
            ),
        ]
    )
    monkeypatch.setattr(mapping_config, "registry", lambda: reg)
    engine = MagicMock()
    engine.raw_connection.return_value.cursor.return_value = _RaisingFieldMetadataCursor()
    monkeypatch.setattr(catalog_mod, "engine_nexora_db", engine)

    with app.test_request_context(), caplog.at_level("WARNING"):
        for _ in range(3):
            fetch_docprocessing_catalog(["acme.invoices"], "en")

    hits = [r for r in caplog.records if "FieldMetadata unavailable" in r.getMessage()]
    assert len(hits) == 1
    # The driver message survives, so a new cause is distinguishable from the
    # expected "table does not exist".
    assert "Invalid object name" in hits[0].getMessage()
