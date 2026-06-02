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
