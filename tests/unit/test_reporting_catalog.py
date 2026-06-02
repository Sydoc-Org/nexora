# tests/unit/test_reporting_catalog.py
"""Unit tests for nx_lib.reporting.catalog — pure row→catalog mapping."""

from nx_lib.reporting.catalog import build_catalog


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


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
