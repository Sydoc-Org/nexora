"""Unit tests for nx_lib.reporting.schema — report-definition (v1) validation."""

import pytest

from nx_lib.reporting.schema import (
    REPORT_SCHEMA_VERSION,
    ReportDefinitionError,
    validate_report_definition,
    validate_sql_definition,
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
    # craft a catalog where 'date' is not filterable
    d["filters"] = [{"field": "date", "op": "eq", "value": "x"}]
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


def test_non_dict_definition_rejected():
    with pytest.raises(ReportDefinitionError):
        validate_report_definition([], CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_row_limit_zero_rejected():
    d = _valid_def()
    d["rowLimit"] = 0
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_row_limit_bool_rejected():
    d = _valid_def()
    d["rowLimit"] = True
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_schema_version_bool_rejected():
    d = _valid_def()
    d["schemaVersion"] = True
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_scope_falsy_non_dict_rejected():
    d = _valid_def()
    d["scope"] = []
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_scope_none_allowed():
    d = _valid_def()
    d["scope"] = None
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_scope_clients_non_string_list_rejected():
    d = _valid_def()
    d["scope"] = {"clients": [1, 2], "processes": []}
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_value_requiring_op_with_null_value_rejected():
    d = _valid_def()
    d["filters"] = [{"field": "status", "op": "eq", "value": None}]
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_between_with_one_element_list_rejected():
    d = _valid_def()
    d["filters"] = [{"field": "pages", "op": "between", "value": [1]}]
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_between_with_two_element_list_allowed():
    d = _valid_def()
    d["filters"] = [{"field": "pages", "op": "between", "value": [1, 10]}]
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_in_with_non_list_value_rejected():
    d = _valid_def()
    d["filters"] = [{"field": "status", "op": "in", "value": "Done"}]
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_valid_sql_definition_ok():
    rd = {"kind": "sql", "target": "statistics", "sql": "SELECT 1", "title": "t"}
    validate_sql_definition(rd, allowed_targets={"statistics"})  # no raise


def test_sql_definition_bad_kind():
    with pytest.raises(ReportDefinitionError):
        validate_sql_definition(
            {"kind": "table", "target": "statistics", "sql": "SELECT 1", "title": "t"},
            allowed_targets={"statistics"},
        )


def test_sql_definition_bad_target():
    with pytest.raises(ReportDefinitionError):
        validate_sql_definition(
            {"kind": "sql", "target": "octopus", "sql": "SELECT 1", "title": "t"},
            allowed_targets={"statistics"},
        )


def test_sql_definition_missing_sql():
    with pytest.raises(ReportDefinitionError):
        validate_sql_definition(
            {"kind": "sql", "target": "statistics", "sql": "", "title": "t"},
            allowed_targets={"statistics"},
        )
