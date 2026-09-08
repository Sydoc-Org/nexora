"""Unit tests for nx_lib.reporting.schema — report-definition (v1) validation."""

import pytest

from nx_lib.reporting.schema import (
    REPORT_SCHEMA_VERSION,
    ReportDefinitionError,
    coerce_definition,
    validate_layout_definition,
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


def test_sql_definition_octopus_target_ok_when_allowed():
    rd = {"kind": "sql", "target": "octopus", "sql": "SELECT 1", "title": "t"}
    validate_sql_definition(rd, allowed_targets={"statistics", "octopus"})  # no raise


def test_sql_definition_missing_sql():
    with pytest.raises(ReportDefinitionError):
        validate_sql_definition(
            {"kind": "sql", "target": "statistics", "sql": "", "title": "t"},
            allowed_targets={"statistics"},
        )


# ---------------------------------------------------------------------------
# metrics validation (Slice 1)
# ---------------------------------------------------------------------------


def test_metrics_unknown_code_rejected():
    d = _valid_def()
    d["metrics"] = [{"metric": "not_a_real_metric"}]
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            d,
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            metric_codes={"doc_count"},
        )


def test_metrics_known_code_passes():
    d = _valid_def()
    d["metrics"] = [{"metric": "doc_count"}]
    validate_report_definition(
        d,
        CATALOG_FIELDS,
        FILTERABLE,
        SORTABLE,
        max_row_limit=50000,
        metric_codes={"doc_count"},
    )


def test_metrics_absent_still_validates_backward_compat():
    d = _valid_def()
    # no "metrics" key — must pass with default empty metric_codes
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


# ---------------------------------------------------------------------------
# coerce_definition — best-effort, whitelist-safe repair of AI-drafted defs.
# Catalog carries human labels so we can prove label->key resolution.
# ---------------------------------------------------------------------------

# Keys are CamelCase like the real curated table sources (ForDate/ParentCategory);
# labels are what a small model tends to emit instead.
CATALOG = [
    {"field": "ForDate", "label": "Date", "filterable": True, "sortable": True},
    {"field": "ParentCategory", "label": "Parent category", "filterable": True, "sortable": True},
    {"field": "RecordCount", "label": "Records", "filterable": False, "sortable": True},
]


def _model_def(**over):
    d = {
        "schemaVersion": 1,
        "visualization": "table",
        "source": "gen_pdqm",
        "title": "By category",
        "columns": [{"field": "ForDate"}],
        "rowLimit": 5000,
    }
    d.update(over)
    return d


def test_coerce_resolves_column_label_to_key():
    d = _model_def(columns=[{"field": "Date"}, {"field": "Parent category"}])
    coerce_definition(d, CATALOG)
    assert [c["field"] for c in d["columns"]] == ["ForDate", "ParentCategory"]


def test_coerce_backfills_header_from_label_on_remap():
    d = _model_def(columns=[{"field": "Date"}])
    coerce_definition(d, CATALOG)
    assert d["columns"][0] == {"field": "ForDate", "header": "Date"}


def test_coerce_keeps_existing_header_on_remap():
    d = _model_def(columns=[{"field": "Date", "header": "When"}])
    coerce_definition(d, CATALOG)
    assert d["columns"][0] == {"field": "ForDate", "header": "When"}


def test_coerce_label_match_is_case_insensitive():
    d = _model_def(columns=[{"field": "DATE"}, {"field": "  parent CATEGORY "}])
    coerce_definition(d, CATALOG)
    assert [c["field"] for c in d["columns"]] == ["ForDate", "ParentCategory"]


def test_coerce_leaves_valid_keys_untouched():
    d = _model_def(columns=[{"field": "ForDate", "header": "Date"}])
    coerce_definition(d, CATALOG)
    assert d["columns"] == [{"field": "ForDate", "header": "Date"}]


def test_coerce_resolves_filter_and_sort_labels():
    d = _model_def(
        filters=[{"field": "Parent category", "op": "eq", "value": "x"}],
        sort=[{"field": "Date", "dir": "asc"}],
    )
    coerce_definition(d, CATALOG)
    assert d["filters"][0]["field"] == "ParentCategory"
    assert d["sort"][0]["field"] == "ForDate"


def test_coerce_resolves_chart_hint_axes():
    d = _model_def(chartHint={"type": "bar", "x": "Parent category", "y": "Records"})
    coerce_definition(d, CATALOG)
    assert d["chartHint"]["x"] == "ParentCategory"
    assert d["chartHint"]["y"] == "RecordCount"


def test_coerce_does_not_invent_unknown_field():
    # A value that is neither a key nor a label is left as-is (validation rejects it).
    d = _model_def(columns=[{"field": "Nonsense"}])
    coerce_definition(d, CATALOG)
    assert d["columns"][0]["field"] == "Nonsense"


def test_coerce_skips_ambiguous_label():
    # Two fields share the label "Total" -> ambiguous -> not remapped (left to fail).
    catalog = [
        {"field": "TotalA", "label": "Total"},
        {"field": "TotalB", "label": "Total"},
    ]
    d = _model_def(columns=[{"field": "Total"}])
    coerce_definition(d, catalog)
    assert d["columns"][0]["field"] == "Total"


def test_coerce_fills_missing_schema_version():
    d = _model_def()
    del d["schemaVersion"]
    coerce_definition(d, CATALOG)
    assert d["schemaVersion"] == REPORT_SCHEMA_VERSION


def test_coerce_normalizes_stringy_schema_version():
    coerced = coerce_definition(_model_def(schemaVersion="1"), CATALOG)
    assert coerced["schemaVersion"] == REPORT_SCHEMA_VERSION


def test_coerce_leaves_unsupported_schema_version_to_fail():
    coerced = coerce_definition(_model_def(schemaVersion=2), CATALOG)
    assert coerced["schemaVersion"] == 2


def test_coerce_fills_missing_visualization():
    d = _model_def()
    del d["visualization"]
    coerce_definition(d, CATALOG)
    assert d["visualization"] == "table"


def test_coerce_normalizes_nontable_visualization():
    coerced = coerce_definition(_model_def(visualization="bar"), CATALOG)
    assert coerced["visualization"] == "table"


def test_coerce_synthesizes_missing_title():
    d = _model_def()
    del d["title"]
    coerce_definition(d, CATALOG, default_title="Generali — PDQM")
    assert d["title"] == "Generali — PDQM"


def test_coerce_title_falls_back_to_report_when_no_default():
    d = _model_def(title="   ")
    coerce_definition(d, CATALOG)
    assert d["title"] == "Report"


def test_coerce_defaults_missing_row_limit():
    d = _model_def()
    del d["rowLimit"]
    coerce_definition(d, CATALOG, default_row_limit=5000)
    assert d["rowLimit"] == 5000


def test_coerce_clamps_oversized_row_limit():
    coerced = coerce_definition(
        _model_def(rowLimit=999999), CATALOG, default_row_limit=5000, max_row_limit=50000
    )
    assert coerced["rowLimit"] == 50000


def test_coerce_non_dict_passthrough():
    assert coerce_definition(None, CATALOG) is None
    assert coerce_definition("nope", CATALOG) == "nope"


def test_coerce_returns_same_object_mutated_in_place():
    d = _model_def(columns=[{"field": "Date"}])
    out = coerce_definition(d, CATALOG)
    assert out is d  # in-place: callers that hold the ref see the fix


def test_coerced_label_definition_passes_validation():
    # The end-to-end point: a model definition that used LABELS and omitted
    # schemaVersion/title becomes valid after coercion.
    d = {
        "source": "gen_pdqm",
        "columns": [{"field": "Date"}, {"field": "Parent category"}],
        "filters": [{"field": "Parent category", "op": "eq", "value": "PDQM"}],
        "sort": [{"field": "Date", "dir": "desc"}],
    }
    coerce_definition(
        d, CATALOG, default_title="Generali", default_row_limit=5000, max_row_limit=50000
    )
    catalog_fields = {c["field"] for c in CATALOG}
    filterable = {c["field"] for c in CATALOG if c.get("filterable")}
    sortable = {c["field"] for c in CATALOG if c.get("sortable")}
    validate_report_definition(d, catalog_fields, filterable, sortable, max_row_limit=50000)


# Case-normalization: small models emit "Month"/"EQ"/"ASC" — coerce should lowercase
_GRAINABLE_CATALOG = [
    {
        "field": "import_date",
        "label": "Import date",
        "filterable": True,
        "sortable": True,
        "grainable": True,
    },
    {"field": "doctype", "label": "Doc type", "filterable": True, "sortable": True},
]


def test_coerce_normalizes_grain_case():
    d = _model_def(columns=[{"field": "import_date", "grain": "Month"}])
    coerce_definition(d, _GRAINABLE_CATALOG)
    assert d["columns"][0]["grain"] == "month"


def test_coerce_normalizes_grain_case_upper():
    d = _model_def(columns=[{"field": "import_date", "grain": "YEAR"}])
    coerce_definition(d, _GRAINABLE_CATALOG)
    assert d["columns"][0]["grain"] == "year"


def test_coerce_leaves_invalid_grain_untouched():
    d = _model_def(columns=[{"field": "import_date", "grain": "fortnight"}])
    coerce_definition(d, _GRAINABLE_CATALOG)
    assert d["columns"][0]["grain"] == "fortnight"  # unknown — left for validator to reject


def test_coerce_normalizes_filter_op_case():
    d = _model_def(filters=[{"field": "ForDate", "op": "EQ", "value": "x"}])
    coerce_definition(d, CATALOG)
    assert d["filters"][0]["op"] == "eq"


def test_coerce_normalizes_filter_op_case_mixed():
    d = _model_def(filters=[{"field": "ForDate", "op": "Contains", "value": "x"}])
    coerce_definition(d, CATALOG)
    assert d["filters"][0]["op"] == "contains"


def test_coerce_normalizes_sort_dir_case():
    d = _model_def(sort=[{"field": "ForDate", "dir": "DESC"}])
    coerce_definition(d, CATALOG)
    assert d["sort"][0]["dir"] == "desc"


def test_coerce_normalizes_sort_dir_case_upper():
    d = _model_def(sort=[{"field": "ForDate", "dir": "ASC"}])
    coerce_definition(d, CATALOG)
    assert d["sort"][0]["dir"] == "asc"


def test_coerce_leaves_invalid_op_untouched():
    d = _model_def(filters=[{"field": "ForDate", "op": "LIKE", "value": "x"}])
    coerce_definition(d, CATALOG)
    assert d["filters"][0]["op"] == "LIKE"  # unknown — left for validator to reject


def test_coerced_mixed_case_definition_passes_validation():
    # End-to-end: a model using uppercase grain/op/dir becomes runnable after coercion.
    catalog = _GRAINABLE_CATALOG
    d = {
        "source": "docprocessing",
        "columns": [{"field": "import_date", "grain": "Month"}, {"field": "doctype"}],
        "filters": [{"field": "doctype", "op": "NE", "value": "unknown"}],
        "sort": [{"field": "doctype", "dir": "ASC"}],
    }
    coerce_definition(d, catalog, default_title="Test", default_row_limit=5000, max_row_limit=50000)
    catalog_fields = {c["field"] for c in catalog}
    filterable = {c["field"] for c in catalog if c.get("filterable")}
    sortable = {c["field"] for c in catalog if c.get("sortable")}
    grainable = {c["field"] for c in catalog if c.get("grainable")}
    validate_report_definition(
        d, catalog_fields, filterable, sortable, max_row_limit=50000, grainable_fields=grainable
    )


# --- date-column grain modifier (Task 5) -------------------------------------

_GRAINABLE = {"date"}  # 'date' is in CATALOG_FIELDS and acts as a date field here


def _grain_def(grain, field="date"):
    d = _valid_def()
    d["columns"] = [{"field": field, "header": "X", "agg": None, "grain": grain}]
    d["sort"] = []
    return d


def test_valid_grain_accepted():
    validate_report_definition(
        _grain_def("month"),
        CATALOG_FIELDS,
        FILTERABLE,
        SORTABLE,
        max_row_limit=50000,
        grainable_fields=_GRAINABLE,
    )


def test_grain_on_non_grainable_field_rejected():
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            _grain_def("month", field="doctype"),
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            grainable_fields=_GRAINABLE,
        )


def test_unknown_grain_rejected():
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            _grain_def("fortnight"),
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            grainable_fields=_GRAINABLE,
        )


def test_absent_grain_accepted():
    d = _valid_def()
    d["columns"] = [{"field": "date", "header": "Raw", "agg": None}]
    d["sort"] = []
    validate_report_definition(
        d,
        CATALOG_FIELDS,
        FILTERABLE,
        SORTABLE,
        max_row_limit=50000,
        grainable_fields=_GRAINABLE,
    )


# --- zero-dimension (grand total) definitions: columns may be empty iff metrics ---


def test_zero_columns_with_metrics_accepted():
    d = _valid_def()
    d["columns"] = []
    d["sort"] = []
    d["metrics"] = [{"metric": "doc_count"}]
    validate_report_definition(
        d,
        CATALOG_FIELDS,
        FILTERABLE,
        SORTABLE,
        max_row_limit=50000,
        metric_codes={"doc_count"},
    )


def test_missing_columns_with_metrics_accepted():
    d = _valid_def()
    del d["columns"]
    d["sort"] = []
    d["metrics"] = [{"metric": "doc_count"}]
    validate_report_definition(
        d,
        CATALOG_FIELDS,
        FILTERABLE,
        SORTABLE,
        max_row_limit=50000,
        metric_codes={"doc_count"},
    )


def test_zero_columns_without_metrics_still_rejected():
    d = _valid_def()
    d["columns"] = []
    d["sort"] = []
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_zero_columns_with_empty_metrics_list_rejected():
    d = _valid_def()
    d["columns"] = []
    d["sort"] = []
    d["metrics"] = []
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            d,
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            metric_codes={"doc_count"},
        )


def test_sort_on_metric_code_accepted_when_metric_selected():
    # The Simple wizard sorts category breakdowns by the metric (e.g. doc_count
    # desc). build_aggregate_sql projects dims + metric codes, so the validator
    # must accept a sort target that is a selected metric code.
    d = _valid_def()
    d["columns"] = [{"field": "doctype", "header": "Type", "agg": None}]
    d["metrics"] = [{"metric": "doc_count"}]
    d["sort"] = [{"field": "doc_count", "dir": "desc"}]
    validate_report_definition(
        d,
        CATALOG_FIELDS,
        FILTERABLE,
        SORTABLE,
        max_row_limit=50000,
        metric_codes={"doc_count"},
    )


def test_sort_on_unselected_metric_code_rejected():
    d = _valid_def()
    d["columns"] = [{"field": "doctype", "header": "Type", "agg": None}]
    d["metrics"] = [{"metric": "doc_count"}]
    d["sort"] = [{"field": "other_metric", "dir": "desc"}]
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            d,
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            metric_codes={"doc_count", "other_metric"},
        )


# ---------------------------------------------------------------------------
# relative-date token filters (F1)
# ---------------------------------------------------------------------------

DATE_FIELDS = {"date"}


def _token_def(value, field="date", op="between"):
    d = _valid_def()
    d["filters"] = [{"field": field, "op": op, "value": value}]
    return d


def test_token_filter_accepted_on_date_field():
    validate_report_definition(
        _token_def({"token": "last_month"}),
        CATALOG_FIELDS,
        FILTERABLE,
        SORTABLE,
        max_row_limit=50000,
        date_fields=DATE_FIELDS,
    )
    validate_report_definition(
        _token_def({"token": "last_n_days", "n": 30}),
        CATALOG_FIELDS,
        FILTERABLE,
        SORTABLE,
        max_row_limit=50000,
        date_fields=DATE_FIELDS,
    )


def test_token_filter_rejected_on_non_date_field():
    with pytest.raises(ReportDefinitionError, match="relative dates"):
        validate_report_definition(
            _token_def({"token": "last_month"}, field="status"),
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            date_fields=DATE_FIELDS,
        )


def test_token_filter_rejected_without_date_fields_param():
    # Default date_fields is empty: callers must opt fields in explicitly.
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            _token_def({"token": "last_month"}),
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
        )


def test_token_filter_rejected_with_non_between_op():
    with pytest.raises(ReportDefinitionError, match="between"):
        validate_report_definition(
            _token_def({"token": "last_month"}, op="eq"),
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            date_fields=DATE_FIELDS,
        )


def test_unknown_token_rejected_with_vocabulary_in_message():
    with pytest.raises(ReportDefinitionError, match="last_fortnight"):
        validate_report_definition(
            _token_def({"token": "last_fortnight"}),
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            date_fields=DATE_FIELDS,
        )


def test_coerce_normalizes_token_case_and_numeric_n():
    catalog = [{"field": "date", "label": "Date"}]
    rd = {
        "filters": [
            {"field": "date", "op": "between", "value": {"token": "Last_Month"}},
            {"field": "date", "op": "between", "value": {"token": "last_n_days", "n": "30"}},
        ]
    }
    coerce_definition(rd, catalog)
    assert rd["filters"][0]["value"]["token"] == "last_month"
    assert rd["filters"][1]["value"]["n"] == 30


def test_coerce_leaves_unknown_token_untouched():
    catalog = [{"field": "date", "label": "Date"}]
    rd = {
        "filters": [
            {"field": "date", "op": "between", "value": {"token": "NOPE", "n": "5"}},
        ]
    }
    coerce_definition(rd, catalog)
    assert rd["filters"][0]["value"]["token"] == "NOPE"  # not lowercased
    assert rd["filters"][0]["value"]["n"] == "5"  # not cast to int


@pytest.mark.parametrize(
    "bad_value",
    [
        {"token": "last_n_days"},  # n missing
        {"token": "last_month", "n": 3},  # stray n
        {"token": "last_n_days", "n": 0},  # n out of range
    ],
)
def test_malformed_token_structure_rejected(bad_value):
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            _token_def(bad_value),
            CATALOG_FIELDS,
            FILTERABLE,
            SORTABLE,
            max_row_limit=50000,
            date_fields=DATE_FIELDS,
        )


# ---------------------------------------------------------------------------
# forecast block (Task 3)
# ---------------------------------------------------------------------------


def test_forecast_block_valid_shapes_accepted():
    d = _valid_def()
    d["forecast"] = {"enabled": True, "horizon": "auto"}
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)
    d["forecast"] = {"enabled": False, "horizon": 12}
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_forecast_block_bad_shapes_rejected():
    for bad in (
        "yes",  # not an object
        {"enabled": "true"},  # non-bool enabled
        {"enabled": True, "horizon": 0},  # below range
        {"enabled": True, "horizon": 61},  # above range
        {"enabled": True, "horizon": True},  # bool masquerading as int
        {"enabled": True, "surprise": 1},  # unknown key
    ):
        d = _valid_def()
        d["forecast"] = bad
        with pytest.raises(ReportDefinitionError):
            validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


# ---------------------------------------------------------------------------
# style block (Simple tab "Colours & axes")
# ---------------------------------------------------------------------------


def test_style_block_valid_shapes_accepted():
    d = _valid_def()
    d["style"] = {
        "colors": {"backlog": "#ef4444"},
        "titleColor": "#4F46E5",
        "rightAxis": ["backlog"],
    }
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)
    d["style"] = {}
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_style_block_bad_shapes_rejected():
    for bad in (
        "red",  # not an object
        {"colors": {"backlog": "red"}},  # named colour, not hex
        {"colors": {"backlog": "#fff"}},  # short hex
        {"colors": {"backlog": "#ef4444; background:url(x)"}},  # CSS injection
        {"colors": ["#ef4444"]},  # list, not map
        {"titleColor": "rgb(0,0,0)"},
        {"rightAxis": "backlog"},  # not a list
        {"rightAxis": [1]},  # non-string key
        {"surprise": 1},  # unknown key
    ):
        d = _valid_def()
        d["style"] = bad
        with pytest.raises(ReportDefinitionError):
            validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def _layout(**over):
    base = {
        "kind": "layout",
        "schemaVersion": 1,
        "title": "Ops standard",
        "measures": [{"id": "m1", "op": "current"}, {"id": "m2", "op": "percentile", "q": 0.95}],
        "tiles": [
            {"id": "t1", "type": "kpi", "measure": "m1", "sparkline": True, "span": 3, "rows": 2},
            {"id": "t2", "type": "chart", "chart": "area", "span": 9, "rows": 4},
            {"id": "t3", "type": "table", "span": 12, "rows": 4},
        ],
    }
    base.update(over)
    return base


def test_valid_layout_passes():
    validate_layout_definition(_layout())


@pytest.mark.parametrize(
    "bad, msg",
    [
        ({"kind": "dashboard"}, "kind"),
        ({"schemaVersion": 2}, "schemaVersion"),
        ({"title": ""}, "title"),
        ({"measures": [{"id": "m1", "op": "delta"}]}, "op"),
        ({"measures": [{"id": "m1", "op": "mean"}, {"id": "m1", "op": "mean"}]}, "duplicate"),
        ({"measures": [{"id": "m1", "op": "percentile", "q": 1.5}]}, "q"),
        ({"tiles": [{"id": "t1", "type": "gauge", "span": 3, "rows": 2}]}, "type"),
        (
            {"tiles": [{"id": "t1", "type": "kpi", "measure": "nope", "span": 3, "rows": 2}]},
            "measure",
        ),
        (
            {"tiles": [{"id": "t1", "type": "chart", "chart": "radar", "span": 3, "rows": 2}]},
            "chart",
        ),
        ({"tiles": [{"id": "t1", "type": "table", "span": 13, "rows": 2}]}, "span"),
        ({"tiles": [{"id": "t1", "type": "table", "span": 12, "rows": 0}]}, "rows"),
        (
            {
                "tiles": [
                    {"id": "t1", "type": "table", "span": 12, "rows": 1},
                    {"id": "t1", "type": "table", "span": 12, "rows": 1},
                ]
            },
            "duplicate",
        ),
        (
            {"tiles": [{"id": 't1"]', "type": "table", "span": 12, "rows": 1}]},
            "tile id",
        ),
        (
            {"tiles": [{"id": "t1]", "type": "table", "span": 12, "rows": 1}]},
            "tile id",
        ),
        (
            {"measures": [{"id": 'm1"]', "op": "mean"}]},
            "measure id",
        ),
        (
            {"measures": [{"id": "m1]", "op": "mean"}]},
            "measure id",
        ),
    ],
)
def test_invalid_layout_rejected(bad, msg):
    with pytest.raises(ReportDefinitionError) as ei:
        validate_layout_definition(_layout(**bad))
    assert msg in str(ei.value)


def test_layout_id_accepted_on_report_definition():
    d = dict(_valid_def(), layoutId=57)
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=10000)


@pytest.mark.parametrize("bad", ["57", 0, -1, True, 1.5])
def test_layout_id_must_be_positive_int(bad):
    d = dict(_valid_def(), layoutId=bad)
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=10000)
