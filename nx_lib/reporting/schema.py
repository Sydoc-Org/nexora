"""Validation for the v1 report-definition JSON shape.

A report definition is the saved/sent description of a report:
source, visualization, columns (+ custom headers), filters, sort, scope,
a row limit, and an optional metrics list. Validation is whitelist-based:
every field/op/dir/metric must already exist in the source's catalog, so
nothing user-supplied can reach SQL unchecked.

The caller is responsible for resolving `source` to its catalog and passing
the resulting field sets in; this function does not validate that `source`
names a known source.
"""

REPORT_SCHEMA_VERSION = 1

SUPPORTED_VISUALIZATIONS = {"table"}

# op -> whether it requires a `value` key
FILTER_OPS = {
    "eq": True,
    "ne": True,
    "in": True,
    "not_in": True,
    "gt": True,
    "gte": True,
    "lt": True,
    "lte": True,
    "between": True,
    "contains": True,
    "starts_with": True,
    "is_null": False,
    "is_not_null": False,
}

SORT_DIRS = {"asc", "desc"}


class ReportDefinitionError(ValueError):
    """Raised when a report definition does not match the v1 schema."""


def validate_report_definition(
    rd,
    catalog_fields,
    filterable_fields,
    sortable_fields,
    *,
    max_row_limit,
    metric_codes=frozenset(),
):
    """Validate `rd` (a dict) against the v1 schema. Raises ReportDefinitionError.

    `catalog_fields`, `filterable_fields`, `sortable_fields` are sets of the
    field keys the chosen source exposes. `max_row_limit` is the server cap.
    `metric_codes` is an optional set of canonical metric codes the source
    exposes; when absent the default is empty (any metrics key is rejected).

    The caller is responsible for resolving `source` to its catalog (and
    supplying those field sets); this function does not validate that `source`
    names a known source.
    """
    if not isinstance(rd, dict):
        raise ReportDefinitionError("definition must be an object")
    schema_version = rd.get("schemaVersion")
    if isinstance(schema_version, bool) or schema_version != REPORT_SCHEMA_VERSION:
        raise ReportDefinitionError(f"schemaVersion must be {REPORT_SCHEMA_VERSION}")
    if rd.get("visualization") not in SUPPORTED_VISUALIZATIONS:
        raise ReportDefinitionError("visualization must be 'table'")
    if not isinstance(rd.get("source"), str) or not rd["source"]:
        raise ReportDefinitionError("source is required")

    title = rd.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ReportDefinitionError("title is required")
    subtitle = rd.get("subtitle")
    if subtitle is not None and not isinstance(subtitle, str):
        raise ReportDefinitionError("subtitle must be a string or null")

    columns = rd.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ReportDefinitionError("at least one column is required")
    for c in columns:
        if not isinstance(c, dict) or c.get("field") not in catalog_fields:
            raise ReportDefinitionError(f"unknown column field: {c.get('field')!r}")
        header = c.get("header")
        if header is not None and not isinstance(header, str):
            raise ReportDefinitionError("column header must be a string or null")

    for f in rd.get("filters") or []:
        if not isinstance(f, dict):
            raise ReportDefinitionError("filter must be an object")
        if f.get("field") not in filterable_fields:
            raise ReportDefinitionError(f"field not filterable: {f.get('field')!r}")
        op = f.get("op")
        if op not in FILTER_OPS:
            raise ReportDefinitionError(f"unknown filter op: {op!r}")
        if FILTER_OPS[op]:
            value = f.get("value")
            if value is None:
                raise ReportDefinitionError(f"filter op {op!r} requires a value")
            if op == "between" and (not isinstance(value, list) or len(value) != 2):
                raise ReportDefinitionError("between value must be a 2-element list")
            if op in ("in", "not_in") and not isinstance(value, list):
                raise ReportDefinitionError(f"filter op {op!r} value must be a list")

    for s in rd.get("sort") or []:
        if not isinstance(s, dict) or s.get("field") not in sortable_fields:
            raise ReportDefinitionError(f"field not sortable: {s.get('field')!r}")
        if s.get("dir") not in SORT_DIRS:
            raise ReportDefinitionError("sort dir must be 'asc' or 'desc'")

    scope = rd.get("scope")
    if scope is None:
        scope = {}
    if not isinstance(scope, dict):
        raise ReportDefinitionError("scope must be an object")
    for key in ("clients", "processes"):
        val = scope.get(key, [])
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            raise ReportDefinitionError(f"scope.{key} must be a list of strings")

    metrics = rd.get("metrics")
    if metrics is not None:
        if not isinstance(metrics, list):
            raise ReportDefinitionError("metrics must be a list")
        seen_metrics = set()
        for m in metrics:
            if not isinstance(m, dict):
                raise ReportDefinitionError("metric must be an object")
            code = m.get("metric")
            if code not in metric_codes:
                raise ReportDefinitionError(f"unknown metric: {code!r}")
            if code in seen_metrics:
                raise ReportDefinitionError(f"duplicate metric: {code!r}")
            seen_metrics.add(code)

    row_limit = rd.get("rowLimit")
    if (
        isinstance(row_limit, bool)
        or not isinstance(row_limit, int)
        or row_limit < 1
        or row_limit > max_row_limit
    ):
        raise ReportDefinitionError(f"rowLimit must be an int in [1, {max_row_limit}]")


def validate_sql_definition(rd, *, allowed_targets):
    """Validate a saved/exported live-SQL definition shape. Raises ReportDefinitionError.

    Shape: {kind:"sql", target:<str in allowed_targets>, sql:<non-empty str>,
            title:<str>, headers?:<list[str]>}. The SQL text itself is validated
    separately by nx_lib.reporting.sandbox at run time.
    """
    if not isinstance(rd, dict):
        raise ReportDefinitionError("definition must be an object")
    if rd.get("kind") != "sql":
        raise ReportDefinitionError("kind must be 'sql'")
    if rd.get("target") not in allowed_targets:
        raise ReportDefinitionError("unknown SQL target")
    sql = rd.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise ReportDefinitionError("sql is required")
    title = rd.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ReportDefinitionError("title is required")
    headers = rd.get("headers")
    if headers is not None and (
        not isinstance(headers, list) or not all(isinstance(h, str) for h in headers)
    ):
        raise ReportDefinitionError("headers must be a list of strings")
