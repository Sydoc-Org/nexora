"""Unit tests for nx_lib.reporting.schema — report-definition (v1) validation."""

import pytest

from nx_lib.reporting.schema import (
    REPORT_SCHEMA_VERSION,
    ReportDefinitionError,
    validate_report_definition,
)

CATALOG_FIELDS = {"date", "client", "doctype", "status", "pages"}
FILTERABLE = {"date", "client", "doctype", "status", "pages"}
SORTABLE = {"date", "doctype", "pages"}


def _valid_def():
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "source": "docprocessing",
        "visualization": "table",
        "title": "My report",
        "subtitle": None,
        "columns": [
            {"field": "date", "header": "Date", "agg": None},
            {"field": "doctype", "header": "Type", "agg": None},
        ],
        "groupBy": [],
        "filters": [{"field": "status", "op": "eq", "value": "Done"}],
        "sort": [{"field": "date", "dir": "desc"}],
        "scope": {"clients": ["acme"], "processes": ["acme.invoices"]},
        "rowLimit": 5000,
        "sql": None,
        "sqlTarget": None,
    }


def test_valid_definition_passes():
    validate_report_definition(
        _valid_def(), CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000
    )


def test_wrong_schema_version_rejected():
    d = _valid_def()
    d["schemaVersion"] = 99
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_unknown_column_field_rejected():
    d = _valid_def()
    d["columns"].append({"field": "evil; DROP TABLE", "header": "x", "agg": None})
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_table_requires_at_least_one_column():
    d = _valid_def()
    d["columns"] = []
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_unknown_filter_op_rejected():
    d = _valid_def()
    d["filters"] = [{"field": "status", "op": "regex", "value": "x"}]
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_filter_on_non_filterable_field_rejected():
    d = _valid_def()
    d["filters"] = [{"field": "client", "op": "eq", "value": "x"}]
    # client is filterable here, so flip it: make a field filterable-excluded
    d["filters"] = [{"field": "date", "op": "eq", "value": "x"}]
    # craft a catalog where 'date' is not filterable
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            d, CATALOG_FIELDS, FILTERABLE - {"date"}, SORTABLE, max_row_limit=50000
        )


def test_sort_on_non_sortable_field_rejected():
    d = _valid_def()
    d["sort"] = [{"field": "client", "dir": "asc"}]  # client not in SORTABLE
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_row_limit_capped_and_typed():
    d = _valid_def()
    d["rowLimit"] = 9_999_999
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_is_null_op_allows_missing_value():
    d = _valid_def()
    d["filters"] = [{"field": "status", "op": "is_null"}]
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)
