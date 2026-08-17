# tests/unit/test_reporting_catalog.py
"""Unit tests for nx_lib.reporting.catalog — pure row→catalog mapping."""

from unittest.mock import MagicMock

import nx_lib.reporting.catalog as catalog_mod
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


def test_date_availability_filters_nulls_and_scope():
    rows = [
        _Row(
            ProcessName="compass.01_Invoice_SAP",
            ImportColumn="ImportDate",
            ExportColumn="UploadDatetime",
        ),
        _Row(ProcessName="privera.03_Invoice_New", ImportColumn="ImportTime", ExportColumn=None),
        _Row(ProcessName="other.99_Hidden", ImportColumn="X", ExportColumn="Y"),  # out of scope
    ]
    avail = date_availability(rows, ["compass.01_Invoice_SAP", "privera.03_Invoice_New"])
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
    rows = [
        _Row(ProcessName="compass.01_Invoice_SAP", WorkitemColumn="WorkItem"),
        _Row(ProcessName="privera.03_Invoice_New", WorkitemColumn=None),
        _Row(ProcessName="other.99_Hidden", WorkitemColumn="X"),  # out of scope
    ]
    avail = workitem_availability(rows, ["compass.01_Invoice_SAP", "privera.03_Invoice_New"])
    assert avail == ["compass.01_Invoice_SAP"]


def test_workitem_availability_tolerates_pre_migration_rows():
    # Statconfig without the WorkitemColumn column (migration 0020 not applied):
    # the field is simply unavailable, never an AttributeError.
    rows = [_Row(ProcessName="compass.01_Invoice_SAP")]
    assert workitem_availability(rows, ["compass.01_Invoice_SAP"]) == []


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


class _SCRow:
    """Stand-in for a pyodbc SearchConfig row: attribute access for
    ProcessName/ClientCode (as read by fetch_docprocessing_catalog directly),
    plus positional index access for the col_* values (the query shape is
    `SELECT ProcessName, {col_cols...} FROM SearchConfig ...` and the code
    reads them by position, `row[i + 1]`)."""

    def __init__(self, process_name, client_code, col_values):
        self.ProcessName = process_name
        self.ClientCode = client_code
        self._row = (process_name, *col_values)

    def __getitem__(self, idx):
        return self._row[idx]


class _FakeCatalogCursor:
    """Fake cursor covering fetch_docprocessing_catalog's query sequence.

    The SearchConfig `WHERE ClientCode = 'default'` branch actually inspects
    the executed SQL text and filters `_searchconfig_rows` accordingly -- so
    this fake only returns 'default' rows if the code under test really added
    the filter, rather than always filtering regardless of the query shape.
    """

    def __init__(self, description, searchconfig_rows):
        self._description = description
        self._searchconfig_rows = searchconfig_rows
        self.description = None
        self._result = []

    def execute(self, sql, *params):
        if "FROM FieldMetadata" in sql or "FROM Search_Field_Labels" in sql:
            self._result = []
        elif "TOP 0 * FROM SearchConfig" in sql:
            self.description = self._description
            self._result = []
        elif "FROM SearchConfig" in sql:
            if "ClientCode = 'default'" in sql:
                self._result = [r for r in self._searchconfig_rows if r.ClientCode == "default"]
            else:
                self._result = list(self._searchconfig_rows)
        elif "FROM Statconfig" in sql:
            self._result = []
        else:
            self._result = []

    def fetchall(self):
        return self._result


def test_fetch_docprocessing_catalog_excludes_ms02_rows(app, monkeypatch):
    # Task 51: an 'ms02'-coded SearchConfig row (col_pid, process
    # 'sydoc.05_PDBS') must not contribute a phantom field to the default
    # docprocessing catalog, even though 'sydoc.05_PDBS' is itself an allowed
    # process. A sibling 'default' row (col_doctype, process 'acme.invoices')
    # must still surface normally.
    description = [("ProcessName",), ("ClientCode",), ("col_pid",), ("col_doctype",)]
    rows = [
        _SCRow("sydoc.05_PDBS", "ms02", ("PidCol", None)),
        _SCRow("acme.invoices", "default", (None, "DocType")),
    ]
    cur = _FakeCatalogCursor(description, rows)
    conn = MagicMock()
    conn.cursor.return_value = cur
    engine = MagicMock()
    engine.raw_connection.return_value = conn
    monkeypatch.setattr(catalog_mod, "engine_nexora_db", engine)

    with app.test_request_context():
        catalog = fetch_docprocessing_catalog(["sydoc.05_PDBS", "acme.invoices"], "en")

    by_field = {c["field"]: c for c in catalog}
    assert "pid" not in by_field
    assert by_field["doctype"]["processes"] == ["acme.invoices"]


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
