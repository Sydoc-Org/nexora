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

import re

from .tokens import RELATIVE_DATE_TOKENS, validate_token_value

REPORT_SCHEMA_VERSION = 1

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

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

# Date-column bucketing grains. Only fields flagged grainable (date fields) may
# carry one.
GRAINS = {"day", "week", "month", "quarter", "year"}


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
    grainable_fields=frozenset(),
    date_fields=frozenset(),
):
    """Validate `rd` (a dict) against the v1 schema. Raises ReportDefinitionError.

    `catalog_fields`, `filterable_fields`, `sortable_fields` are sets of the
    field keys the chosen source exposes. `max_row_limit` is the server cap.
    `metric_codes` is an optional set of canonical metric codes the source
    exposes; when absent the default is empty (any metrics key is rejected).
    Columns may be empty iff metrics is non-empty (zero-dimension grand totals).

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

    # columns may be empty/missing iff metrics is non-empty (a zero-dimension
    # grand total: SELECT AGG(...) with no GROUP BY).
    columns = rd.get("columns")
    if columns is None:
        columns = []
    metrics_list = rd.get("metrics")
    has_metrics = isinstance(metrics_list, list) and len(metrics_list) > 0
    if not isinstance(columns, list):
        raise ReportDefinitionError("columns must be a list")
    if not columns and not has_metrics:
        raise ReportDefinitionError("at least one column is required")
    for c in columns:
        if not isinstance(c, dict) or c.get("field") not in catalog_fields:
            raise ReportDefinitionError(f"unknown column field: {c.get('field')!r}")
        header = c.get("header")
        if header is not None and not isinstance(header, str):
            raise ReportDefinitionError("column header must be a string or null")
        grain = c.get("grain")
        if grain is not None:
            if c.get("field") not in grainable_fields:
                raise ReportDefinitionError(
                    f"field not grainable: {c.get('field')!r} — only date fields "
                    f"accept a grain (grainable: {sorted(grainable_fields)})"
                )
            if grain not in GRAINS:
                raise ReportDefinitionError(f"unknown grain: {grain!r}")

    filters = rd.get("filters") or []
    if not isinstance(filters, list):
        # The most common AI mistake: a map keyed by field name instead of a list.
        raise ReportDefinitionError(
            "filters must be a LIST of filter objects, e.g. "
            '[{"field": "export_date", "op": "between", '
            '"value": ["2026-01-01", "2026-03-31"]}] — not a map keyed by field'
        )
    for f in filters:
        if not isinstance(f, dict):
            raise ReportDefinitionError(
                "each filter must be an object " '{"field": "<key>", "op": "<op>", "value": <v>}'
            )
        if f.get("field") not in filterable_fields:
            raise ReportDefinitionError(f"field not filterable: {f.get('field')!r}")
        op = f.get("op")
        if op not in FILTER_OPS:
            raise ReportDefinitionError(f"unknown filter op: {op!r}")
        if FILTER_OPS[op]:
            value = f.get("value")
            if value is None:
                raise ReportDefinitionError(f"filter op {op!r} requires a value")
            if isinstance(value, dict):
                # Relative-date token: resolved to absolute dates at run time
                # (nx_lib.reporting.tokens). Only date fields, only 'between'.
                if op != "between":
                    raise ReportDefinitionError(
                        f"a relative-date value requires op 'between', got {op!r}"
                    )
                if f.get("field") not in date_fields:
                    raise ReportDefinitionError(
                        f"field does not accept relative dates: {f.get('field')!r}"
                    )
                err = validate_token_value(value)
                if err:
                    raise ReportDefinitionError(err)
                continue
            if op == "between" and (not isinstance(value, list) or len(value) != 2):
                raise ReportDefinitionError("between value must be a 2-element list")
            if op in ("in", "not_in") and not isinstance(value, list):
                raise ReportDefinitionError(f"filter op {op!r} value must be a list")

    # A sort may target a selected metric code (the aggregate SQL projects
    # dims + metric codes), e.g. a category breakdown sorted by doc_count.
    sort_targets = set(sortable_fields)
    if has_metrics:
        assert isinstance(metrics_list, list)  # has_metrics already confirmed this
        sort_targets |= {m.get("metric") for m in metrics_list if isinstance(m, dict)}
    for s in rd.get("sort") or []:
        if not isinstance(s, dict) or s.get("field") not in sort_targets:
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

    forecast = rd.get("forecast")
    if forecast is not None:
        if not isinstance(forecast, dict):
            raise ReportDefinitionError("forecast must be an object")
        extra = set(forecast) - {"enabled", "horizon"}
        if extra:
            raise ReportDefinitionError(f"unexpected keys in forecast: {sorted(extra)}")
        if not isinstance(forecast.get("enabled", False), bool):
            raise ReportDefinitionError("forecast.enabled must be a boolean")
        horizon = forecast.get("horizon", "auto")
        if horizon != "auto" and (
            isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 60
        ):
            raise ReportDefinitionError("forecast.horizon must be 'auto' or an int in [1, 60]")

    # Presentation overrides (Simple tab "Colours & axes" popover): per-series
    # colours, a title/legend colour and the series plotted on a right-hand
    # Y axis. Keys are the client-side series keys (metric code, or the
    # pivoted series label). Values are rendered into CSS/Chart.js, so hex only.
    style = rd.get("style")
    if style is not None:
        if not isinstance(style, dict):
            raise ReportDefinitionError("style must be an object")
        extra = set(style) - {"colors", "titleColor", "rightAxis"}
        if extra:
            raise ReportDefinitionError(f"unexpected keys in style: {sorted(extra)}")
        colors = style.get("colors", {})
        if not isinstance(colors, dict) or not all(
            isinstance(k, str) and _HEX_COLOR.match(str(v)) for k, v in colors.items()
        ):
            raise ReportDefinitionError("style.colors must map series keys to #rrggbb colours")
        title_color = style.get("titleColor")
        if title_color is not None and not _HEX_COLOR.match(str(title_color)):
            raise ReportDefinitionError("style.titleColor must be a #rrggbb colour")
        right_axis = style.get("rightAxis")
        if right_axis is not None and (
            not isinstance(right_axis, list) or not all(isinstance(k, str) for k in right_axis)
        ):
            raise ReportDefinitionError("style.rightAxis must be a list of series keys")

    row_limit = rd.get("rowLimit")
    if (
        isinstance(row_limit, bool)
        or not isinstance(row_limit, int)
        or row_limit < 1
        or row_limit > max_row_limit
    ):
        raise ReportDefinitionError(f"rowLimit must be an int in [1, {max_row_limit}]")


def coerce_definition(
    rd, catalog, *, default_title=None, default_row_limit=None, max_row_limit=None
):
    """Best-effort, whitelist-safe repair of an AI-drafted report definition.

    Small models routinely emit a definition that is *almost* valid: they use a
    column's human LABEL where the schema wants its field KEY, omit schemaVersion
    or the title, or pick a chart-style visualization. This fixes those classes of
    mistake IN PLACE (and returns the same object) BEFORE validation, so an
    otherwise-correct draft is accepted instead of bounced.

    It never widens the whitelist: a label is only swapped for a key when that
    label maps to exactly one catalog field and the supplied value is not already
    a valid key; an unknown value is left untouched (and validation still rejects
    it). Coercion is a no-op for an already-valid definition, so it is safe to run
    on every AI-drafted definition (Surface A + the agent's build_definition tool).

    `catalog` is the source field-catalog: a list of {field, label, ...} dicts.
    A non-dict `rd` is returned unchanged.
    """
    if not isinstance(rd, dict):
        return rd

    # label (casefolded) -> field key, dropping ambiguous labels and bare keys.
    keys = set()
    label_to_key: dict = {}
    ambiguous = set()
    for c in catalog or []:
        key = c.get("field")
        if not key:
            continue
        keys.add(key)
        label = c.get("label")
        if isinstance(label, str) and label.strip():
            norm = label.strip().casefold()
            if norm in label_to_key and label_to_key[norm] != key:
                ambiguous.add(norm)
            label_to_key.setdefault(norm, key)
    for norm in ambiguous:
        label_to_key.pop(norm, None)

    def _resolve(value):
        """Return (key, original_label) if `value` is a known label, else (value, None)."""
        if not isinstance(value, str) or value in keys:
            return value, None
        key = label_to_key.get(value.strip().casefold())
        return (key, value) if key else (value, None)

    for col in rd.get("columns") or []:
        if not isinstance(col, dict):
            continue
        key, label = _resolve(col.get("field"))
        if label is not None:
            col["field"] = key
            if not (isinstance(col.get("header"), str) and col["header"].strip()):
                col["header"] = label
        grain = col.get("grain")
        if isinstance(grain, str) and grain.lower() in GRAINS:
            col["grain"] = grain.lower()

    for spec in rd.get("filters") or []:
        if isinstance(spec, dict):
            key, label = _resolve(spec.get("field"))
            if label is not None:
                spec["field"] = key
            op = spec.get("op")
            if isinstance(op, str) and op.lower() in FILTER_OPS:
                spec["op"] = op.lower()
            value = spec.get("value")
            if isinstance(value, dict) and isinstance(value.get("token"), str):
                tok = value["token"].strip().lower()
                if tok in RELATIVE_DATE_TOKENS:
                    value["token"] = tok
                    n = value.get("n")
                    if isinstance(n, str) and n.strip().isdigit():
                        value["n"] = int(n.strip())

    for spec in rd.get("sort") or []:
        if isinstance(spec, dict):
            key, label = _resolve(spec.get("field"))
            if label is not None:
                spec["field"] = key
            dir_val = spec.get("dir")
            if isinstance(dir_val, str) and dir_val.lower() in SORT_DIRS:
                spec["dir"] = dir_val.lower()

    chart = rd.get("chartHint")
    if isinstance(chart, dict):
        for axis in ("x", "y"):
            key, label = _resolve(chart.get(axis))
            if label is not None:
                chart[axis] = key

    sv = rd.get("schemaVersion")
    if sv is None or (not isinstance(sv, bool) and str(sv).strip() in ("1", "1.0")):
        rd["schemaVersion"] = REPORT_SCHEMA_VERSION

    if rd.get("visualization") != "table":
        rd["visualization"] = "table"

    title = rd.get("title")
    if not (isinstance(title, str) and title.strip()):
        rd["title"] = (default_title or "").strip() or "Report"

    rl = rd.get("rowLimit")
    if isinstance(rl, bool) or not isinstance(rl, int) or rl < 1:
        if default_row_limit is not None:
            rd["rowLimit"] = default_row_limit
    elif max_row_limit is not None and rl > max_row_limit:
        rd["rowLimit"] = max_row_limit

    return rd


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
