"""Schema serialization for the Reporting AI assistant (Phase 1).

Turns the RO SQL targets' INFORMATION_SCHEMA and the curated source catalogs into
a compact text block for the prompt. Bounded by a character budget and a per-target
table cap; truncation is appended as a visible marker and logged so coverage limits
are never silent. Connection factories are injected so this is unit-testable without
a DB; the connection they yield is closed here so pooled RO connections never leak.
"""

import logging
import re

logger = logging.getLogger(__name__)

DEFAULT_CHAR_BUDGET = 12000
MAX_TABLES_PER_TARGET = 60

_COLUMNS_SQL = (
    "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
    "FROM INFORMATION_SCHEMA.COLUMNS "
    "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
)


def serialize_target(target_name, conn_factory, *, max_tables=MAX_TABLES_PER_TARGET):
    """Serialize one RO target's columns grouped by table. `conn_factory()` -> a DBAPI
    connection (closed here); its cursor runs the INFORMATION_SCHEMA query.

    Returns (text, was_capped) where was_capped is True iff the per-target table cap
    fired (i.e. some tables were dropped from the serialization).
    """
    conn = conn_factory()
    try:
        cur = conn.cursor()
        cur.execute(_COLUMNS_SQL)
        rows = cur.fetchall()
    finally:
        conn.close()
    tables: dict[str, list] = {}
    for r in rows:
        key = f"{r.TABLE_SCHEMA}.{r.TABLE_NAME}"
        tables.setdefault(key, []).append(f"{r.COLUMN_NAME} {r.DATA_TYPE}")
    lines = [f"# Target: {target_name}"]
    was_capped = False
    for i, (tbl, cols) in enumerate(tables.items()):
        if i >= max_tables:
            dropped = len(tables) - max_tables
            noun = "table" if dropped == 1 else "tables"
            lines.append(f"  ... ({dropped} more {noun} truncated)")
            logger.info("ai_schema: target=%s truncated to %d tables", target_name, max_tables)
            was_capped = True
            break
        lines.append(f"TABLE {tbl}({', '.join(cols)})")
    return "\n".join(lines), was_capped


def _serialize_curated(curated):
    lines = []
    for src in curated or []:
        fields = ", ".join(
            f"{f.get('field')} {f.get('type', 'string')}"
            for f in src.get("fields", [])
            if f.get("field")
        )
        label = src.get("label") or "(unnamed)"
        # These curated (table-provider) sources live on databases run_sql cannot
        # reach (run_sql only targets the statistics/octopus RO engines). Spell that
        # out so the explain-data agent uses build_definition for them instead of
        # drafting `SELECT ... FROM <source>` against a run_sql target (→ 208).
        lines.append(
            f"# Curated source (builder-only — answer with build_definition; "
            f"NOT queryable with run_sql): {label}\nFIELDS({fields})"
        )
    return "\n".join(lines)


_PROC_NUM_PREFIX = re.compile(r"^\d+_")


def _humanize_process_id(pid):
    """'privera.03_Invoice_New' -> 'privera Invoice New', so the model can
    match natural-language process names against otherwise-opaque ids."""
    client, _, rest = str(pid).partition(".")
    rest = _PROC_NUM_PREFIX.sub("", rest).replace("_", " ").strip()
    return f"{client} {rest}".strip() if rest else str(pid)


def serialize_sources_catalog(sources, *, char_budget=DEFAULT_CHAR_BUDGET):
    """Compact, bounded text block of the caller's accessible curated sources.

    `sources`: list of {id, label, fields:[{field,label,type,filterable,sortable,
    grainable}], processes:[ids], metrics:[{code,label,aggregation,base_field}]}.
    Each field renders as `key "Human Label":type (flags)` (the label is dropped
    when it equals the key); grainable fields are date fields whose column may
    carry a grain (day/week/month/quarter/year). A source's canonical metrics
    render as one `  metrics: code "Label" = agg(col)` line. Sources with no
    registered metrics render `  metrics: none — this source cannot aggregate`
    so the model never invents metric codes for them. Returns
    (text, truncated_bool); on overflow the text is cut to the budget with a
    visible marker and the truncation is logged.
    """
    lines = []
    for s in sources or []:
        flags_fields = []
        for f in s.get("fields", []):
            flags = []
            if f.get("filterable"):
                flags.append("filterable")
            if f.get("sortable"):
                flags.append("sortable")
            if f.get("grainable"):
                # Date field: a column for it may carry a grain
                # (day/week/month/quarter/year) to bucket it.
                flags.append("grainable")
            flag_txt = f" ({', '.join(flags)})" if flags else ""
            field = f.get("field")
            label = f.get("label")
            # Show the human label next to the key so the model can map a NL
            # question to the right field, while the validator-checked KEY stays
            # the leading token. Omitted when the label is just the key (table
            # sources default label==field) to keep the catalog compact.
            label_txt = f' "{label}"' if label and label != field else ""
            flags_fields.append(f"{field}{label_txt}:{f.get('type', 'string')}{flag_txt}")
        lines.append(f'SOURCE {s.get("id")} "{s.get("label")}": ' + "; ".join(flags_fields))
        procs = s.get("processes") or []
        if procs:
            parts = [f'{p} ("{_humanize_process_id(p)}")' for p in procs]
            lines.append(f"  allowed scope.processes: {', '.join(parts)}")
        mets = s.get("metrics") or []
        if mets:
            parts = []
            for m in mets:
                col = m.get("base_field") or "*"
                label = f' "{m.get("label")}"' if m.get("label") else ""
                # Date-anchored measures count on their own date and share the
                # activity_date axis — the agent prompt keys its "use
                # build_definition, not SQL" rule on this marker.
                anchor = f" anchor={m['anchor']}" if m.get("anchor") else ""
                parts.append(f"{m.get('code')}{label} = {m.get('aggregation')}({col}){anchor}")
            lines.append(f"  metrics: {'; '.join(parts)}")
        else:
            lines.append(
                "  metrics: none — this source cannot aggregate; for"
                " counting/summing questions pick a source that lists metrics"
            )
    text = "\n".join(lines)
    if len(text) > char_budget:
        logger.info(
            "ai_schema: sources catalog truncated from %d to %d chars", len(text), char_budget
        )
        return text[:char_budget] + "\n... (catalog truncated)", True
    return text, False


def serialize_partial_tables(table_processes, union_source_id):
    """Text block marking the per-process statistics tables as PARTIAL views.

    The RO-target dump (`serialize_target`) is a flat INFORMATION_SCHEMA listing,
    so `dbo.Compass_Invoice` looks exactly like a company-wide fact table. It is
    not: each ProcessSources table holds exactly ONE process. Without this block
    the agent answers "our volume" from whichever single table it found first and
    reports the number as the whole company (issue #128) — worst case a confident
    zero from a table that simply had no rows in the window.

    This list is also exhaustive in the other direction: the statistics DB holds
    plenty of tables ProcessSources never registered (dbo.BFH_Statistic,
    dbo.DPSLicenseCounter, …) which the curated source does not read at all. The
    agent reached for exactly those, so the block says so explicitly rather than
    leaving "not listed here" to be inferred.

    `table_processes`: {table_name: {"processes": [...], "import_col": str|None,
    "export_col": str|None, "fields": {field_key: column_name, ...}}} from
    nx_lib/mapping_config.py's ProcessSources + ProcessFieldMappings registry.
    The date/field columns are included because the
    tables do NOT share column names (`ExportDate` vs `ExportEM_dt`, `AnzImagesOut`
    vs `PageCount`, …) — telling the agent to UNION them without saying which
    column is which just moves the failure from "wrong universe" to "invalid
    column name" (issue #154).
    `union_source_id`: the curated source that UNIONs them all (docprocessing).
    Returns "" when there is nothing to mark, so the caller can skip the block.
    """
    if not table_processes:
        return ""
    lines = ["# Per-process PARTIAL tables — each covers ONE process, never the whole company"]
    for tbl in sorted(table_processes):
        cfg = table_processes[tbl]
        line = f"{tbl} = process {', '.join(sorted(cfg.get('processes') or []))}"
        cols = [
            f"{name}: {cfg[key]}"
            for key, name in (("import_col", "import date"), ("export_col", "export date"))
            if cfg.get(key)
        ]
        cols += [f"{fk}: {col}" for fk, col in sorted((cfg.get("fields") or {}).items())]
        if cols:
            line += f" ({'; '.join(cols)})"
        lines.append(line)
    lines.append(
        "Their date and field columns differ per table — use the ones named above,"
        " never assume a shared column name or guess one against"
        " INFORMATION_SCHEMA. A field with no column named for a table is not"
        " available on that process."
        " Querying one of these answers for that process ALONE. A question about"
        ' totals that names no process ("our volume", "the numbers", "how many'
        ' documents") is COMPANY-WIDE: answer it with build_definition on source'
        f" {union_source_id}, which unions every process. If raw SQL is genuinely"
        " needed (percentiles, window functions), UNION every relevant table"
        " above. Either way, name in your answer which processes the numbers"
        " cover. Zero rows from ONE of these tables is NOT evidence of zero"
        " company-wide activity — say which process it was."
        " The list above is COMPLETE: every OTHER table in the target below is"
        f" unregistered and is NOT part of source {union_source_id}. Do not answer"
        " a company-wide question from one of those at all — use"
        " build_definition, or if the user asked for that specific table, say"
        " plainly that it sits outside the reporting universe."
    )
    # Issue #132 case 16: asked for "unique workitems" the agent drafted
    # COUNT(DISTINCT WorkitemID) across several of these tables and reported the
    # result as a company total. Both halves are wrong — the count is already the
    # row count, and the id spaces are per-process, so a cross-table DISTINCT
    # collapses colliding ids from different processes into one.
    lines.append(
        "ONE ROW = ONE WORKITEM in every table above (verified: COUNT(*),"
        " COUNT(WorkitemID) and COUNT(DISTINCT WorkitemID) all return the same"
        " number). So the count of workitems IS the document/row count — use"
        f" doc_count on source {union_source_id}; there is deliberately no"
        " distinct-workitem metric. Workitem ids are unique only WITHIN a"
        " process and collide across these tables, so never COUNT(DISTINCT"
        " WorkitemID) over more than one of them — it silently under-counts."
    )
    return "\n".join(lines)


def serialize_metrics_catalog(metrics):
    """One line per blessed metric: `METRIC <code> "<label>" = <agg>(<col|*>) on <source>`.

    Lets the AI reference canonical metrics by code and get consistent numbers.
    """
    lines = []
    for m in metrics or []:
        col = m.get("base_field") or "*"
        label = f' "{m.get("label")}"' if m.get("label") else ""
        lines.append(
            f"METRIC {m.get('code')}{label} = "
            f"{m.get('aggregation')}({col}) on {m.get('source_id')}"
        )
    return "\n".join(lines)


def serialize_schema(
    *,
    targets,
    curated,
    metrics=None,
    partial_tables=None,
    union_source_id="docprocessing",
    char_budget=DEFAULT_CHAR_BUDGET,
):
    """Combine RO targets + curated catalogs + canonical metrics into a budgeted text block.

    `targets`: {name: conn_factory}. `curated`: list of {label, fields:[{field,type}]}.
    `metrics`: optional list of {code, label, aggregation, base_field, source_id} blessed
    metrics to append under a `# Canonical metrics` header.
    `partial_tables`: optional {table: [process, ...]} marking per-process tables as
    partial views of the whole (see `serialize_partial_tables`); rendered FIRST so the
    coverage rule is read before the table listing it qualifies.
    Returns (text, truncated_bool). truncated_bool is True if the char budget cut the
    text *or* any per-target table cap dropped tables — both are coverage limits the
    caller surfaces to the user. On char overflow the text is cut and a visible marker
    appended; truncation is logged.
    """
    blocks = []
    partial_block = serialize_partial_tables(partial_tables, union_source_id)
    if partial_block:
        blocks.append(partial_block)
    target_capped = False
    for name, factory in (targets or {}).items():
        try:
            block, was_capped = serialize_target(name, factory)
        except Exception as e:  # a missing/unconfigured RO target degrades, not 500s
            logger.warning("ai_schema: target %s unavailable: %s", name, e)
            continue
        blocks.append(block)
        target_capped = target_capped or was_capped
    curated_block = _serialize_curated(curated)
    if curated_block:
        blocks.append(curated_block)
    if metrics:
        metrics_body = serialize_metrics_catalog(metrics)
        if metrics_body:
            blocks.append(f"# Canonical metrics\n{metrics_body}")
    text = "\n\n".join(b for b in blocks if b)
    if len(text) > char_budget:
        logger.info("ai_schema: schema truncated from %d to %d chars", len(text), char_budget)
        return text[:char_budget] + "\n... (schema truncated)", True
    return text, target_capped
