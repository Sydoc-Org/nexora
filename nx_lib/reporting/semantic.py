# nx_lib/reporting/semantic.py
"""Resolve canonical metrics into concrete aggregation specs and GROUP BY SQL.

Pure + DB-free: the metric registry rows and the source's whitelisted catalog
are injected, so this is unit-testable without a DB. Security: the aggregated
column and the metric alias are whitelist/identifier-validated; the aggregation
function comes from a fixed enum. This is the same boundary the row builders
(query.py / table_query.py) enforce -- only filter *values* are ever parameters.
"""

import re

AGGREGATIONS = {"count", "count_distinct", "sum", "avg", "min", "max"}
_CODE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MetricResolveError(ValueError):
    """Raised when a report's metrics cannot be resolved safely."""


def resolve_metrics(metric_refs, metric_registry, catalog_fields):
    """Resolve `metric_refs` (rd['metrics'] = [{'metric': code}, ...]).

    metric_registry: {code: {'aggregation', 'base_field'}}.
    catalog_fields: set of the source's whitelisted column keys.
    Returns [{'code', 'aggregation', 'base_field'}] preserving order.
    Raises MetricResolveError on unknown/duplicate/unsafe/whitelist-miss.
    """
    out = []
    seen = set()
    for ref in metric_refs or []:
        if not isinstance(ref, dict):
            raise MetricResolveError("metric ref must be an object")
        code = ref.get("metric")
        if not isinstance(code, str) or not _CODE.match(code):
            raise MetricResolveError(f"unsafe metric code: {code!r}")
        if code in seen:
            raise MetricResolveError(f"duplicate metric: {code!r}")
        spec = metric_registry.get(code)
        if spec is None:
            raise MetricResolveError(f"unknown metric: {code!r}")
        agg = spec.get("aggregation")
        if agg not in AGGREGATIONS:
            raise MetricResolveError(f"unsupported aggregation: {agg!r}")
        base = spec.get("base_field")
        if agg == "count":
            base = None
        elif base not in catalog_fields:
            raise MetricResolveError(f"metric base field not in catalog: {base!r}")
        seen.add(code)
        out.append({"code": code, "aggregation": agg, "base_field": base})
    return out
